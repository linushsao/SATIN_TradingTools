import pandas as pd
import time
# [修正]: 補全 timedelta 匯入，解決日期位移運算時的 NameError
from datetime import datetime, timedelta 
from shared.logging_tool import info, warn, error
from shared.data_transform import resample_kbar
from shared.capabilities import CAP_MARKET_DATA

class HistoryDownloader:
    """
    [V0.2.1] 通用分段式歷史資料下載器
    修正 timedelta 匯入錯誤並優化日期切分邏輯。
    """
    @staticmethod
    def fetch_and_resample(context, code: str, start: str, end: str, target_freq: int, progress_callback=None):
        """
        [修正] 強化欄位識別與時間索引處理：
        1. 支援多種時間欄位名稱 (ts, Ts, timestamp, Date) 的識別。
        2. 強制將 OHLCV 轉換為 resample_kbar 所需的首字大寫格式。
        3. 解決 pd.to_datetime(index) 將 RangeIndex 轉為 1970-01-01 的 Bug。
        """
        from shared.capabilities import CAP_HISTORICAL_DATA, CAP_MARKET_DATA
        import pandas as pd
        
        try:
            # [Optimization B] 降級尋找策略
            svc = context.get_service_by_capability(CAP_HISTORICAL_DATA)
            if not svc:
                svc = context.get_service_by_capability(CAP_MARKET_DATA)
            
            if not svc:
                error("[Downloader] 系統中找不到支援歷史資料或行情服務的組件")
                return pd.DataFrame()

            # 1. 準備日期區間 (以 30 天為一單位分段)
            start_dt = pd.to_datetime(start)
            end_dt = pd.to_datetime(end)
            chunks = []
            curr = start_dt
            while curr <= end_dt:
                next_curr = min(curr + timedelta(days=30), end_dt)
                chunks.append((curr.strftime('%Y-%m-%d'), next_curr.strftime('%Y-%m-%d')))
                if next_curr == end_dt: break
                curr = next_curr + timedelta(days=1)

            total_chunks = len(chunks)
            all_dfs = []
            
            # 定義欄位映射表，確保與後端 Service 回傳格式對齊
            TIME_COLS = ['ts', 'Ts', 'timestamp', 'Timestamp', 'Date', 'date']
            OHLCV_MAP = {
                'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close', 'v': 'Volume',
                'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'
            }
            
            # 2. 逐段下載與類型轉換
            for i, (c_start, c_end) in enumerate(chunks):
                chunk_df = pd.DataFrame()
                retry_count = 0
                max_retries = 10
                
                while retry_count < max_retries:
                    info(f"[Downloader] Chunk {i+1}/{total_chunks}: {c_start} ~ {c_end}")
                    result = svc.get_history_data(code=code, start=c_start, end=c_end, freq=1)
                    
                    if isinstance(result, str) and "Download Started" in result:
                        info(f"[Downloader] Server syncing... Retry {retry_count+1}/{max_retries}")
                        time.sleep(5)
                        retry_count += 1
                        continue
                    
                    if result is not None:
                        if isinstance(result, list):
                            chunk_df = pd.DataFrame(result)
                        elif isinstance(result, pd.DataFrame):
                            chunk_df = result
                        break
                
                if not chunk_df.empty:
                    # --- [修正點] 強化欄位正規化 ---
                    # 優先處理 OHLCV 大寫化
                    chunk_df.rename(columns=OHLCV_MAP, inplace=True)
                    # 如果欄位名稱是首字大寫，也將其統一 (例如 Amount)
                    chunk_df.columns = [c[0].upper() + c[1:] if len(c) > 0 else c for c in chunk_df.columns]
                    all_dfs.append(chunk_df)
                
                if progress_callback:
                    current_progress = ((i + 1) / total_chunks) * 80.0
                    progress_callback(current_progress)

            if not all_dfs:
                warn(f"[Downloader] 最終未取得任何有效資料 ({code})")
                return pd.DataFrame()

            # 3. 合併、排序與清理重複值
            full_raw_df = pd.concat(all_dfs)
            
            # --- [修正點] 智慧時間索引識別 ---
            time_col = next((c for c in full_raw_df.columns if c in TIME_COLS), None)
            
            if time_col:
                full_raw_df[time_col] = pd.to_datetime(full_raw_df[time_col])
                full_raw_df.set_index(time_col, inplace=True)
            elif not isinstance(full_raw_df.index, pd.DatetimeIndex):
                # 如果沒有明確時間欄位且 index 不是時間，這才是真正的錯誤
                error(f"[Downloader] 無法在回傳資料中找到時間欄位。Columns: {list(full_raw_df.columns)}")
                return pd.DataFrame()
            
            full_raw_df.index.name = 'Date'
            full_raw_df = full_raw_df.sort_index()
            full_raw_df = full_raw_df[~full_raw_df.index.duplicated(keep='first')]

            # 4. 執行本地重採樣 (僅在需要大於 1m 的頻率時)
            if target_freq > 1:
                info(f"[Downloader] Executing local resample to {target_freq}m")
                # 確保必要欄位存在，避免 resample_kbar KeyError
                req_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
                for col in req_cols:
                    if col not in full_raw_df.columns:
                        full_raw_df[col] = 0.0 # 補空位防止崩潰
                
                if 'Amount' not in full_raw_df.columns:
                    full_raw_df['Amount'] = full_raw_df['Close'] * full_raw_df['Volume']

                return resample_kbar(full_raw_df, target_freq).dropna()
            
            return full_raw_df

        except Exception as e:
            import traceback
            error(f"[Downloader] fetch_and_resample 關鍵崩潰: {str(e)}")
            traceback.print_exc()
            return pd.DataFrame()