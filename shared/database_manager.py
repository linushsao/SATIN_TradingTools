# ==============================================================================
# shared/database_manager.py
#
# Version: V0.5-004 (Get Last TS)
# 更新日期: 2025-12-13
# 描述:     資料庫管理模組 (SQLite)。
#           [修正]: 新增 get_last_timestamp 用於偵測資料缺口。
# ==============================================================================

import sqlite3
import os
import datetime
import pandas as pd
from shared.logging_tool import info, error, debug

class DatabaseManager:
    def __init__(self, config):
        self.db_path = config.get('db_path', 'dbase/market_data.db')
        self._ensure_dir()
        self._init_db()

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _get_conn(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        """初始化資料庫結構"""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS kbars (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    code TEXT NOT NULL,
                    freq INTEGER NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    amount REAL,
                    UNIQUE(code, freq, timestamp)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ticks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    code TEXT NOT NULL,
                    close REAL,
                    volume INTEGER,
                    bid_price REAL,
                    ask_price REAL,
                    amount REAL
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_kbars_query ON kbars (code, freq, timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ticks_query ON ticks (code, timestamp)')
            conn.commit()
            info(f"[DB] Initialized at {self.db_path}", print_to_console=True)
        except Exception as e:
            error(f"[DB] Init failed: {e}")
        finally:
            conn.close()

    def save_bar(self, bar_data):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if isinstance(bar_data, dict):
                data_list = [bar_data]
            else:
                data_list = bar_data
                
            to_insert = []
            for b in data_list:
                ts = b['timestamp']
                if hasattr(ts, 'strftime'):
                    ts = ts.strftime('%Y-%m-%d %H:%M:%S')
                
                to_insert.append((
                    ts, b['code'], b['freq'],
                    b.get('Open'), b.get('High'), b.get('Low'), b.get('Close'),
                    b.get('Volume'), b.get('Amount', 0)
                ))
            
            cursor.executemany('''
                INSERT OR REPLACE INTO kbars 
                (timestamp, code, freq, open, high, low, close, volume, amount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', to_insert)
            conn.commit()
        except Exception as e:
            error(f"[DB] Save bar error: {e}")
        finally:
            conn.close()

    def save_tick(self, tick_data):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if isinstance(tick_data, dict):
                data_list = [tick_data]
            else:
                data_list = tick_data
            
            to_insert = []
            for t in data_list:
                to_insert.append((
                    t['datetime'], t['code'], 
                    t['close'], t['volume'], 
                    t.get('bid_price', 0), t.get('ask_price', 0), t.get('amount', 0)
                ))
            
            cursor.executemany('''
                INSERT INTO ticks 
                (timestamp, code, close, volume, bid_price, ask_price, amount)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', to_insert)
            conn.commit()
        except Exception as e:
            error(f"[DB] Save tick error: {e}")
        finally:
            conn.close()

    def get_last_timestamp(self, code: str, freq: int = 1) -> datetime.datetime:
        """
        [NEW] 查詢最後一筆 K 棒的時間 (用於回補判斷)。
        Returns: datetime object or None
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT timestamp FROM kbars 
                WHERE code=? AND freq=? 
                ORDER BY timestamp DESC LIMIT 1
            ''', (code, freq))
            row = cursor.fetchone()
            if row:
                try:
                    return pd.to_datetime(row[0]).to_pydatetime()
                except:
                    return None
            return None
        except Exception as e:
            error(f"[DB] Get last timestamp error: {e}")
            return None
        finally:
            conn.close()

    def get_bars(self, code: str, start: str, end: str, freq: int):
        """查詢指定區間 K 棒，回傳 DataFrame。"""
        conn = self._get_conn()
        try:
            query = '''
                SELECT timestamp, open, high, low, close, volume, amount 
                FROM kbars 
                WHERE code=? AND freq=? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
            '''
            df = pd.read_sql_query(query, conn, params=(code, freq, start, end))
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
                df.index.name = 'Date'
            return df
        except Exception as e:
            error(f"[DB] Get bars error: {e}")
            return pd.DataFrame()
        finally:
            conn.close()

    def get_recent_bars(self, code: str, freq: int, limit: int):
        """
        取得最近 N 筆 K 棒 (用於初始化 Aggregator)。
        回傳: DataFrame (索引為 Date)
        """
        conn = self._get_conn()
        try:
            # 使用子查詢先取最後 N 筆，再用外層查詢轉回時間正序
            query = f'''
                SELECT * FROM (
                    SELECT timestamp, open, high, low, close, volume, amount 
                    FROM kbars 
                    WHERE code=? AND freq=?
                    ORDER BY timestamp DESC
                    LIMIT {limit}
                ) ORDER BY timestamp ASC
            '''
            df = pd.read_sql_query(query, conn, params=(code, freq))
            
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
                df.index.name = 'Date'
                # 重新命名欄位以符合 Pandas 習慣 (首字大寫)
                df.columns = [c.capitalize() for c in df.columns]
                
            return df
        except Exception as e:
            error(f"[DB] Get recent bars error: {e}")
            return pd.DataFrame()
        finally:
            conn.close()
            
    def execute_query(self, query: str, params: tuple = ()):
        """[新增] 通用的查詢輔助函式，解決 AttributeError"""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            return cursor.fetchall()
        except Exception as e:
            error(f"[DB] Query execution error: {e}")
            return []
        finally:
            conn.close()

    def get_min_timestamp(self, code: str, freq: int = 1):
        """[修正] 取得特定合約最早的 K 棒時間 (注意：表名為 kbars)"""
        res = self.execute_query(
            "SELECT MIN(timestamp) FROM kbars WHERE code = ? AND freq = ?", (code, freq)
        )
        return pd.to_datetime(res[0][0]) if res and res[0][0] else None

    def get_max_timestamp(self, code: str, freq: int = 1):
        """[修正] 取得特定合約最晚的 K 棒時間"""
        res = self.execute_query(
            "SELECT MAX(timestamp) FROM kbars WHERE code = ? AND freq = ?", (code, freq)
        )
        return pd.to_datetime(res[0][0]) if res and res[0][0] else None          