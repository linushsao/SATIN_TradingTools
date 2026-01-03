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
        """[修正]: 解決 NameError 並確保偵錯訊息正確輸出"""
        import os
        import pandas as pd
        # 確保匯入專案專用的日誌工具
        from shared.logging_tool import info, warn, error
        
        abs_db_path = os.path.abspath(self.db_path)
        
        info(f"[DB Diagnostic] Accessing database at: {abs_db_path}")
        info(f"[DB Diagnostic] Query Params -> Code: {code}, Freq: {freq}, Start: {start}, End: {end}")

        if not os.path.exists(abs_db_path):
            error(f"[DB Error] Database file does not exist at {abs_db_path}")
            return pd.DataFrame()
            
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
                df.columns = [c.capitalize() for c in df.columns]
                info(f"[DB Success] Retrieved {len(df)} bars.")
            else:
                # 診斷邏輯
                diag_query = "SELECT MIN(timestamp), MAX(timestamp) FROM kbars WHERE code=? AND freq=?"
                cursor = conn.cursor()
                cursor.execute(diag_query, (code, freq))
                db_range = cursor.fetchone()
                
                # 修正後的 warn 呼叫
                if db_range and db_range[0]:
                    warn(f"[DB Discovery] Target range empty. Data for '{code}' in DB exists from {db_range[0]} to {db_range[1]}")
                else:
                    warn(f"[DB Discovery] No data found for code '{code}' with freq {freq} in this database.")
                    
            return df
        except Exception as e:
            # 此處 e 現在會被正確轉發，不會再因為 'error' 未定義而再次崩潰
            error(f"[DB Error] Get bars failed: {str(e)}")
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