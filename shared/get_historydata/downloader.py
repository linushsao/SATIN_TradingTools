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
        獲取資料並執行重採樣。
        [修正]: 
          1. 實作服務降級策略 (Optimization B): 優先尋找 CAP_HISTORICAL_DATA，
             若無則降級尋找 CAP_MARKET_DATA。
          2. 解決 15TT 導致的頻率解析崩潰問題。
        """
        # 延遲匯入以避免潛在的循環引用，並確保使用正確的常數
        from shared.capabilities import CAP_HISTORICAL_DATA, CAP_MARKET_DATA
        
        try:
            # [Optimization B] 降級尋找策略 (Fallback Discovery)
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
            
            # 2. 逐段下載與類型轉換
            for i, (c_start, c_end) in enumerate(chunks):
                chunk_df = pd.DataFrame()
                retry_count = 0
                max_retries = 10
                
                while retry_count < max_retries:
                    info(f"[Downloader] Chunk {i+1}/{total_chunks}: {c_start} ~ {c_end}")
                    # 使用具備 SSTP 協議的 get_history_data 介面
                    result = svc.get_history_data(code=code, start=c_start, end=c_end, freq=1)
                    
                    # 處理非同步同步狀態
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
                    # 標準化欄位：首字大寫化以匹配 resample_kbar 要求
                    chunk_df.columns = [c.capitalize() for c in chunk_df.columns]
                    all_dfs.append(chunk_df)
                
                if progress_callback:
                    current_progress = ((i + 1) / total_chunks) * 80.0
                    progress_callback(current_progress)

            if not all_dfs:
                warn(f"[Downloader] 最終未取得任何有效資料 ({code})")
                return pd.DataFrame()

            # 3. 合併、排序與清理重複值 (確保 Pandas resample 不會崩潰)
            full_raw_df = pd.concat(all_dfs)
            if 'Timestamp' in full_raw_df.columns:
                full_raw_df['Timestamp'] = pd.to_datetime(full_raw_df['Timestamp'])
                full_raw_df.set_index('Timestamp', inplace=True)
            elif not isinstance(full_raw_df.index, pd.DatetimeIndex):
                full_raw_df.index = pd.to_datetime(full_raw_df.index)
            
            full_raw_df.index.name = 'Date'
            full_raw_df = full_raw_df.sort_index()
            full_raw_df = full_raw_df[~full_raw_df.index.duplicated(keep='first')]

            # 4. 執行本地重採樣 (僅在需要大於 1m 的頻率時)
            if target_freq > 1:
                info(f"[Downloader] Executing local resample to {target_freq}m")
                # 這裡僅傳入整數，由 data_transform 內部的 rule = f"{freq_min}T" 處理
                return resample_kbar(full_raw_df, target_freq).dropna()
            
            return full_raw_df

        except Exception as e:
            error(f"[Downloader] fetch_and_resample 關鍵崩潰: {str(e)}")
            return pd.DataFrame()