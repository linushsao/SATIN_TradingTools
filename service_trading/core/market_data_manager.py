# ==============================================================================
# service_trading/core/market_data_manager.py
#
# Version: V2.1-001 (Auto-Backfill)
# 更新日期: 2025-12-17
# 描述:     交易資料引擎。
#           [修正]: 
#             1. 新增 get_and_cache_history 實作 Read-Through Caching 機制。
#             2. 自動檢查本地 DB，若無資料自動向 Adapter 下載並回寫。
# ==============================================================================

import pandas as pd
import numpy as np
import datetime
import os
import sys
import queue
import time
import threading
from logging_tool import info, error, warn, debug
from zmq_manager import ZmqServer
from database_manager import DatabaseManager
from service_trading.core.interfaces import IBrokerAdapter
from shared.model_defs import StandardTick
from shared.data_transform import resample_kbar

# Configuration constants
BASE_FREQ = 15 

class TickAggregator:
    """Real-time Tick data aggregator. Aggregates Ticks into N-min OHLCV bars."""
    def __init__(self, base_freq: int, buffer_size: int, tz_offset: int = 8): 
        self.base_freq = base_freq
        self.buffer_size = buffer_size
        self.tz_offset = tz_offset # [NEW] Timezone Offset (Hours)
        
        self.kbars = pd.DataFrame(
            columns=['Open', 'High', 'Low', 'Close', 'Volume', 'Amount'],
            index=pd.DatetimeIndex([], name='timestamp')
        )
        self.current_bar = None 
        self.just_closed_bar = False 

    def _start_new_bar(self, timestamp: pd.Timestamp, price, volume, amount):
        new_timestamp = timestamp.floor(f'{self.base_freq}min')
        
        # [修正]: 強化 TXF 08:45 開盤點 Snap 邏輯
        # 確保在開盤首個週期內 (08:45 ~ 08:45+Freq) 的 Tick 標籤絕對等於 08:45
        session_start = timestamp.replace(hour=8, minute=45, second=0, microsecond=0)
        session_first_interval_end = session_start + pd.Timedelta(minutes=self.base_freq)
        
        if session_start <= timestamp < session_first_interval_end:
            new_timestamp = session_start

        self.current_bar = {
            'Open': price, 'High': price, 'Low': price, 'Close': price,
            'Volume': volume, 'Amount': amount, 'timestamp': new_timestamp
        }

    def _close_current_bar(self):
        if self.current_bar is None: return
        completed_bar = pd.Series(
            [self.current_bar['Open'], self.current_bar['High'], self.current_bar['Low'],
             self.current_bar['Close'], self.current_bar['Volume'], self.current_bar['Amount']],
            index=['Open', 'High', 'Low', 'Close', 'Volume', 'Amount'],
            name=self.current_bar['timestamp']
        )
        self.kbars.loc[completed_bar.name] = completed_bar
        self.kbars = self.kbars.sort_index()
        if len(self.kbars) > self.buffer_size:
            self.kbars = self.kbars.iloc[len(self.kbars) - self.buffer_size:]
        self.just_closed_bar = True 
        self.current_bar = None 

    def add_tick(self, tick: StandardTick):
        self.just_closed_bar = False 
        
        # Ignore Quote Ticks (Price=0)
        if tick.close <= 0: return

        # [Fix] Convert UTC timestamp to Local Time based on offset
        timestamp = pd.to_datetime(tick.ts, unit='s') + pd.Timedelta(hours=self.tz_offset)
        
        price = tick.close
        volume = tick.volume
        amount = tick.amount
        
        bar_time = timestamp.floor(f'{self.base_freq}min')
        
        # [修正]: 修正邊界判定邏輯，確保 session_open_boundary 與當前 Tick 日期同步
        session_open_boundary = timestamp.replace(hour=8, minute=45, second=0, microsecond=0)
        
        is_session_cross = False
        if self.current_bar:
            # 判斷是否跨越了 08:45 開盤線 (從夜盤 05:00 結束後到日盤開盤的跨越)
            if self.current_bar['timestamp'] < session_open_boundary and timestamp >= session_open_boundary:
                is_session_cross = True

        if self.current_bar is None:
            self._start_new_bar(timestamp, price, volume, amount)
        elif is_session_cross:
            self._close_current_bar()
            self._start_new_bar(timestamp, price, volume, amount)
        elif bar_time > self.current_bar['timestamp']:
            self._close_current_bar()
            self._start_new_bar(timestamp, price, volume, amount)
        else:
            # 更新現有 K 棒
            self.current_bar['High'] = max(self.current_bar['High'], price)
            self.current_bar['Low'] = min(self.current_bar['Low'], price)
            self.current_bar['Close'] = price
            self.current_bar['Volume'] += volume
            self.current_bar['Amount'] += amount

    def get_kbars(self):
        df = self.kbars.copy()
        if self.current_bar:
            current_bar_df = pd.DataFrame(
                [self.current_bar],
                index=pd.DatetimeIndex([self.current_bar['timestamp']], name='Date') 
            )
            df = pd.concat([df, current_bar_df.drop(columns=['timestamp'])])
        if len(df) > self.buffer_size:
            df = df.iloc[len(df) - self.buffer_size:]
        df.index.name = 'Date'
        return df

    def get_current_bar(self):
        if self.current_bar: return self.current_bar
        return None

class MarketDataManager:
    def __init__(self, adapter: IBrokerAdapter, config: dict, zmq_server: ZmqServer):
        self.adapter = adapter
        self.config = config
        self.server = zmq_server 
        self.db = DatabaseManager(config)
        #self._active_downloads = set()  # 追蹤正在下載中的合約代碼
        self._download_lock = threading.Lock() #多執行緒安全鎖
        #self._last_download_time = {} #紀錄最後一次成功檢查的時間
        
        # [NEW] Timezone Configuration
        self.tz_offset = 8 # Default to Taiwan (+8)
        self._init_timezone_settings()
        
        # [Config] Min Read Bars
        self.min_display_bars = config.get('min_display_bars', 1600)
        self.active_frequencies = sorted(list(set(config.get('active_frequencies', [15]))))
        self.aggregators = {} 

        self._active_downloads = set()      # 正在下載中的合約
        self._download_cv = threading.Condition() # 使用條件變量處理同步等待
        self._last_download_time = {}
        
        for freq in self.active_frequencies:
            self.aggregators[freq] = TickAggregator(
                base_freq=freq, 
                buffer_size=self.min_display_bars,
                tz_offset=self.tz_offset 
            )
        
        self.is_running = False
        self.current_contract_code = None
        self.external_tick_handlers = []
        
        self.download_handler = None 
        self._last_download_trigger = {} 

    def _init_timezone_settings(self):
        """讀取並初始化時區設定"""
        tz_conf = self.config.get('system_settings', {}).get('timezone', {'mode': 'MANUAL', 'offset': 8})
        mode = tz_conf.get('mode', 'MANUAL')
        
        if mode == 'AUTO':
            try:
                local_now = datetime.datetime.now().astimezone()
                self.tz_offset = int(local_now.utcoffset().total_seconds() / 3600)
                info(f"[Timezone] Mode: AUTO. Detected System Offset: UTC+{self.tz_offset}")
            except Exception as e:
                warn(f"[Timezone] Auto-detect failed ({e}). Fallback to +8.")
                self.tz_offset = 8
        else:
            self.tz_offset = int(tz_conf.get('offset', 8))
            info(f"[Timezone] Mode: MANUAL. Configured Offset: UTC+{self.tz_offset}")

    def set_download_handler(self, handler):
        self.download_handler = handler

    def set_adapter(self, adapter: IBrokerAdapter):
        self.adapter = adapter

    def register_tick_handler(self, handler):
        if handler not in self.external_tick_handlers:
            self.external_tick_handlers.append(handler)

    def start_listening(self, contract_code: str):
        """
        [優化版] 啟動監聽改為異步補全，不阻塞啟動流程
        """
        if self.current_contract_code == contract_code and self.is_running:
            self._reload_and_broadcast_history(contract_code)
            return

        self.current_contract_code = contract_code
        
        # 1. 立即啟動 API 訂閱 (確保即時 Tick 能先進來)
        if self.adapter:
            if self.adapter.subscribe_market_data(contract_code):
                self.is_running = True
                info(f"MarketDataManager subscribed to {contract_code}")
            else:
                error(f"Failed to subscribe to {contract_code}")

        # 2. [優化] 將歷史補全移至後台執行緒，不阻塞主流程
        download_thread = threading.Thread(
            target=self._reload_and_broadcast_history, 
            args=(contract_code,),
            name=f"Backfill-{contract_code}"
        )
        download_thread.daemon = True
        download_thread.start()

    def stop_listening(self):
        if self.current_contract_code and self.adapter:
            self.adapter.unsubscribe_market_data(self.current_contract_code)
            info(f"MarketDataManager unsubscribed from {self.current_contract_code}")
            self.is_running = False
            self.current_contract_code = None

    def is_listening(self, contract_code: str) -> bool:
        """
        [新增]: 檢查目前是否正在監聽特定合約的行情。
        """
        return self.is_running and self.current_contract_code == contract_code

    def on_tick(self, tick: StandardTick):
        """
        行情中心報價入口。
        此處維持廣播模式，由 Executor 端決定是否「無條件接收」。
        """
        # 儲存至資料庫
        if self.config.get('ticks_save_enabled', False) and tick.close > 0:
            tick_dict = {
                'datetime': tick.datetime_str,
                'code': tick.code,
                'close': tick.close,
                'volume': tick.volume,
                'amount': tick.amount,
                'bid_price': tick.bid_price,
                'ask_price': tick.ask_price
            }
            self.db.save_tick(tick_dict)

        # 更新聚合器 (KBar 產生)
        for freq, agg in self.aggregators.items():
            agg.add_tick(tick)
            if agg.just_closed_bar:
                self._publish_kbar_update(freq)

        # [關鍵]: 通知外部處理器 (如 StrategyExecutor 與 TouchOrderExecutor)
        # 此處已是無條件分發給所有註冊的 Handler
        for handler in self.external_tick_handlers:
            try:
                handler(tick)
            except Exception as e:
                error(f"External tick handler error: {e}")

        # 廣播至 UI
        ui_tick_payload = tick.to_sstp_dict()
        self.server.publish("TICK", ui_tick_payload)
    
    def _publish_kbar_update(self, freq):
        if not self.current_contract_code: return

        try:
            # 1. Save last bar
            agg = self.aggregators.get(freq)
            if agg:
                df_agg = agg.get_kbars()
                if not df_agg.empty:
                    last_bar = df_agg.iloc[-1].copy()
                    last_bar['timestamp'] = df_agg.index[-1]
                    last_bar['code'] = self.current_contract_code
                    last_bar['freq'] = freq
                    self.db.save_bar(last_bar.to_dict())

            # 2. Read Snapshot
            now = datetime.datetime.now()
            required_minutes = self.min_display_bars * freq * 1.5 
            query_start_dt = now - datetime.timedelta(minutes=required_minutes)
            query_start_str = query_start_dt.strftime('%Y-%m-%d %H:%M:%S')
            query_end_str = now.strftime('%Y-%m-%d %H:%M:%S')
            
            df_1min = self.db.get_bars(self.current_contract_code, query_start_str, query_end_str, 1)
            
            if df_1min.empty: return

            # Rename & Resample
            rename_map = {}
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
                if col in df_1min.columns:
                    rename_map[col] = col.capitalize()
            if rename_map: df_1min.rename(columns=rename_map, inplace=True)
            
            if freq == 1:
                df_target = df_1min
            else:
                df_target = resample_kbar(df_1min, freq)

            # Clean
            df_target['Volume'] = df_target['Volume'].fillna(0)
            df_target[['Open', 'High', 'Low', 'Close']] = df_target[['Open', 'High', 'Low', 'Close']].ffill().bfill().fillna(0)

            # Convert to SSTP
            data_list = []
            for idx, row in df_target.iterrows():
                ts_str = idx.strftime('%Y-%m-%d %H:%M:%S') if hasattr(idx, 'strftime') else str(idx)
                bar = {
                    "ts": ts_str,
                    "o": float(row['Open']),
                    "h": float(row['High']),
                    "l": float(row['Low']),
                    "c": float(row['Close']),
                    "v": int(row['Volume']) 
                }
                data_list.append(bar)
            
            self.server.publish("KBAR", {"freq": freq, "data": data_list})
            
        except Exception as e:
            error(f"K-Bar publish error: {e}")
            
    def _reload_and_broadcast_history(self, code):
        """
        即時行情啟動後的背景補全，同樣呼叫統一入口。
        """
        now = datetime.datetime.now()
        # 預設補全最近 30 天的範圍 (可由 config 調整)
        start_dt = now - datetime.timedelta(days=30)
        
        # 1. 呼叫統一入口
        self._ensure_data_range(code, start_dt, now)
        
        # 2. 推送資料給 UI
        self._broadcast_db_data_only(code)
    def _publish_dataframe(self, df, freq):
        try:
            df = df.copy()
            df['Volume'] = df['Volume'].fillna(0)
            df[['Open', 'High', 'Low', 'Close']] = df[['Open', 'High', 'Low', 'Close']].ffill().bfill().fillna(0)

            data_list = []
            for idx, row in df.iterrows():
                ts_str = idx.strftime('%Y-%m-%d %H:%M:%S') if hasattr(idx, 'strftime') else str(idx)
                bar = {
                    "ts": ts_str,
                    "o": float(row['Open']), "h": float(row['High']), "l": float(row['Low']),
                    "c": float(row['Close']), "v": int(row['Volume']) 
                }
                data_list.append(bar)
            
            self.server.publish("KBAR", {"freq": freq, "data": data_list})
        except Exception as e:
            error(f"Publish DF failed: {e}")

    def get_and_cache_history(self, code, start_date, end_date, freq=1):
        req_start = pd.to_datetime(start_date)
        req_end = pd.to_datetime(end_date)
        
        # 1. 呼叫統一入口 (會等待下載完成)
        self._ensure_data_range(code, req_start, req_end)
        
        # 2. 確定有資料後才從 DB 讀取
        return self.db.get_bars(code, start_date, end_date, freq)

    def _download_and_save_data(self, code, start_date, end_date) -> bool:
        """
        [Internal] 呼叫 Adapter 下載並存入 DB。
        """
        if not self.adapter:
            error("[MarketData] No adapter available for download.")
            return False
            
        try:
            df_remote = self.adapter.download_history(code, start_date, end_date)
            
            if df_remote.empty:
                return False
            
            # 標準化欄位與索引
            if 'ts' in df_remote.columns:
                df_remote['ts'] = pd.to_datetime(df_remote['ts'])
                df_remote.set_index('ts', inplace=True)
            elif 'Date' in df_remote.columns:
                df_remote['Date'] = pd.to_datetime(df_remote['Date'])
                df_remote.set_index('Date', inplace=True)
            
            rename_map = {'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume', 'amount': 'Amount'}
            df_remote.rename(columns=rename_map, inplace=True)
            
            # 準備存入 DB 的格式
            df_to_save = df_remote.copy()
            df_to_save['timestamp'] = df_to_save.index
            df_to_save['code'] = code
            df_to_save['freq'] = 1 # 假設 Broker 下載的都是 1分K
            
            self.db.save_bar(df_to_save.to_dict('records'))
            return True
            
        except Exception as e:
            error(f"[MarketData] Download exception: {e}")
            return False
            
    def _broadcast_db_data_only(self, code):
        """實作：讀取 DB 並將各頻率歷史資料推送至 UI"""
        try:
            now = datetime.datetime.now()
            max_freq = max(self.active_frequencies)
            # 讀取足夠顯示的 1 分 K 資料
            required_minutes = self.min_display_bars * max_freq * 2 
            query_start_dt = now - datetime.timedelta(minutes=required_minutes)
            query_start_str = query_start_dt.strftime('%Y-%m-%d %H:%M:%S')
            query_end_str = now.strftime('%Y-%m-%d %H:%M:%S')

            df_1min = self.db.get_bars(code, query_start_str, query_end_str, 1)
            if df_1min.empty: return

            # 標準化欄位名稱
            rename_map = {col: col.capitalize() for col in ['open', 'high', 'low', 'close', 'volume', 'amount']}
            df_1min.rename(columns=rename_map, inplace=True, errors='ignore')

            # 針對每個啟用的頻率進行重採樣與發送
            for freq in self.active_frequencies:
                df_target = df_1min if freq == 1 else resample_kbar(df_1min, freq)
                self._publish_dataframe(df_target, freq)
                
            info(f"[MarketData] History broadcasted for {code} from DB.")
        except Exception as e:
            error(f"[MarketData] Broadcast DB data failed: {e}")    

    def _ensure_data_range(self, code: str, start_dt: pd.Timestamp, end_dt: pd.Timestamp):
        """
        [核心封裝] 統一判定區段並觸發下載的閘口。
        1. 處理併發請求 (Locking/Waiting)
        2. 執行區段智慧判定 (Head/Tail Patching)
        """
        # --- 步驟 1: 併發控制 ---
        with self._download_cv:
            # 如果該合約正在被其他執行緒下載，則等待其完成
            while code in self._active_downloads:
                info(f"[MarketData] Waiting for existing download of {code}...")
                self._download_cv.wait()
            
            # 標記開始下載
            self._active_downloads.add(code)

        try:
            # --- 步驟 2: 區段判斷 (智慧補丁邏輯) ---
            db_min = self.db.get_min_timestamp(code, 1)
            db_max = self.db.get_max_timestamp(code, 1)

            # A. 補頭 (Head Fill)
            if db_min is None or start_dt < db_min:
                d_start = start_dt.strftime('%Y-%m-%d')
                d_end = db_min.strftime('%Y-%m-%d') if db_min else end_dt.strftime('%Y-%m-%d')
                if d_start != d_end:
                    info(f"[SmartPatch] HEAD: {code} ({d_start} ~ {d_end})")
                    self._download_and_save_data(code, d_start, d_end)

            # B. 補尾 (Tail Fill)
            # 重新檢查 max (因為補頭後可能改變)
            db_max = self.db.get_max_timestamp(code, 1)
            # 若請求結束時間大於 DB 最後一筆，且距離現在超過一定時間(避免下載正在形成的K棒)
            if db_max is None or end_dt > (db_max + pd.Timedelta(minutes=5)):
                d_start = db_max.strftime('%Y-%m-%d') if db_max else start_dt.strftime('%Y-%m-%d')
                d_end = end_dt.strftime('%Y-%m-%d')
                if d_start != d_end:
                    info(f"[SmartPatch] TAIL: {code} ({d_start} ~ {d_end})")
                    self._download_and_save_data(code, d_start, d_end)

        finally:
            with self._download_cv:
                self._active_downloads.remove(code)
                self._download_cv.notify_all() # 通知所有正在等待此合約的執行緒            