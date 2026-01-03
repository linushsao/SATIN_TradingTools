# ==============================================================================
# shared/data_transform.py
#
# Version: V0.1-000f (Fix Import)
# 更新日期: 2025-12-08
# 描述:     外部數據源轉換工具集。
#           V0.1-000f: 修正 logging_tool/config_manager 引用路徑為絕對路徑。
# ==============================================================================

import pandas as pd
import numpy as np
import datetime
import os
import sys
import re
import math
import time

# [FIX] Use absolute import path
from shared.config_manager import _log_input
from shared.logging_tool import debug, info, warn, error 

# Configuration constants
DATA_DIR = 'data' 
BASE_FREQ = 15 # K-bar base frequency (minutes) - Default 15 minutes


def resample_kbar(df_1min, freq_min):
    """Resamples a 1-minute DataFrame to the target frequency."""
    # debug(f"[ENTER] {sys._getframe(0).f_code.co_name}", print_to_console=False)
    
    if freq_min == 1:
        return df_1min

    # 建立副本，避免修改到原始 df (預防 SettingWithCopyWarning)
    df_working = df_1min.copy()

    # 1. 確保 Date 欄位是 datetime 物件
    # 如果 Date 已經是 Index，這行會報錯，所以加個檢查
    if 'Date' in df_working.columns:
        df_working['Date'] = pd.to_datetime(df_working['Date'])
        # 2. 將 Date 設定為 Index
        df_working = df_working.set_index('Date')
    elif not isinstance(df_working.index, pd.DatetimeIndex):
        # 如果 Date 不在 Columns，檢查 Index 是不是時間，如果不是就轉換
        df_working.index = pd.to_datetime(df_working.index)
        
    # 3. 執行重採樣
    resampled_data = df_working.resample(f'{freq_min}T').agg({  # 'T' 或 'min' 均可
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum',
        'Amount': 'sum'
    }).dropna()

    return resampled_data


def save_to_csv_external(df, default_filename):
    """Saves DataFrame to CSV in the DATA_DIR, asking user for filename."""
    debug(f"[ENTER] {sys._getframe(0).f_code.co_name}", print_to_console=False)
    
    filename = _log_input(f"\nEnter filename [Default: {default_filename}]: ").strip() or default_filename
    
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        file_path = os.path.join(DATA_DIR, filename)
        
        df.to_csv(file_path, encoding='utf-8', index=df.index.name is not None)
        info(f"External data successfully transformed and saved to: {os.path.abspath(file_path)}")
        print(f"\n✨ External data successfully transformed and saved to: {os.path.abspath(file_path)}")
    except Exception as e:
        error(f"Error saving external file: {e}")
        print(f"\nError saving external file: {e}")


def _determine_data_type(series: pd.Series) -> str:
    """Determines if a cleaned series column is numeric or string."""
    debug(f"[ENTER] {sys._getframe(0).f_code.co_name}", print_to_console=False)
    
    cleaned_series = series.astype(str).str.strip().str.replace(',', '')
    numeric_series = pd.to_numeric(cleaned_series, errors='coerce')
    
    non_nan_ratio = numeric_series.count() / len(numeric_series)
    
    if non_nan_ratio > 0.9: 
        has_decimal = cleaned_series[numeric_series.notna()].str.contains('\\.').any()
        
        if has_decimal:
            return "<浮點數>"
            
        if (numeric_series.dropna() == numeric_series.dropna().astype(int)).all():
            return "<整數>"
            
        return "<浮點數>"
        
    return "<字串>"

def _normalize_time_string(series: pd.Series) -> pd.Series:
    """
    Normalizes time component in strings to enforce hhmmss format (left padding). 
    """
    debug(f"[ENTER] {sys._getframe(0).f_code.co_name}", print_to_console=False)
    series = series.astype(str)
    
    def pad_time(match):
        time_part = match.group(2)
        return f"{match.group(1)}{time_part.zfill(6)}"

    series = series.str.replace(r'(\s)(\d{1,5})$', pad_time, regex=True)
    
    def pad_full_string(match):
        full_string = match.group(0)
        return full_string.zfill(6)
        
    series = series.str.replace(r'^\d{1,5}$', pad_full_string, regex=True)

    return series

def _preview_int_conversion(df, column_map, max_cols):
    """Performs cleanup and integer conversion on the first row of data for preview."""
    debug(f"[ENTER] {sys._getframe(0).f_code.co_name}", print_to_console=False)
    try:
        ohlcv_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        preview_results = {} 
        
        for kbar_col in ohlcv_columns:
            if kbar_col in column_map:
                col_index = column_map[kbar_col] - 1
                series = df.iloc[:, col_index] 
                
                cleaned_series = series.astype(str).str.strip().str.replace(',', '')
                numeric_series = pd.to_numeric(cleaned_series, errors='coerce')
                
                if pd.isna(numeric_series.iloc[0]):
                    int_value = pd.NA
                else:
                    int_value = int(round(numeric_series.iloc[0]))
                
                preview_results[kbar_col] = pd.Series([int_value], dtype='Int64')
                
        df_test = pd.DataFrame(preview_results)
        df_test.index = [''] 
        df_test.columns.name = None
        
        return df_test
    except Exception as e:
        error(f"Error during integer conversion preview: {e}")
        return None

def _do_conversion(file_path, df, column_map, to_int_conversion): 
    """Handles the actual data conversion, cleaning, and indexing."""
    debug(f"[ENTER] {sys._getframe(0).f_code.co_name}", print_to_console=False)
    
    datetime_series = None
    ohlcv_data = {}
    
    # --- Date/Time Handling ---
    has_datetime_keys = ('datetime' in column_map or ('date' in column_map and 'time' in column_map))
    
    if has_datetime_keys: 
        if 'datetime' in column_map:
            datetime_col = df.iloc[:, column_map['datetime'] - 1]
            datetime_col = _normalize_time_string(datetime_col)
            try:
                datetime_series = pd.to_datetime(datetime_col, format='%Y%m%d %H%M%S', errors='coerce')
            except Exception as e:
                error(f"Datetime column parsing failed: {e}")
                print(f"❌ 錯誤: 日期時間欄位解析失敗 ({e})。請檢查欄位編號或資料格式。")
                return None
                
        elif 'date' in column_map and 'time' in column_map:
            date_col = df.iloc[:, column_map['date'] - 1]
            time_col = df.iloc[:, column_map['time'] - 1]
            time_col = _normalize_time_string(time_col)
            datetime_series_combined = date_col.astype(str) + ' ' + time_col.astype(str)
            try:
                datetime_series = pd.to_datetime(datetime_series_combined, errors='coerce')
            except Exception as e:
                error(f"Date/Time column parsing failed: {e}")
                print(f"❌ 錯誤: 日期/時間欄位合併解析失敗 ({e})。請檢查欄位編號或資料格式。")
                return None
        
        if datetime_series is not None and datetime_series.isna().all():
             error("All date/time entries resulted in NaT (Not a Time).")
             print("❌ 錯誤: 所有日期時間條目皆解析失敗。")
             return None
             
    # --- OHLCV Mapping and Cleaning ---
    ohlcv_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    
    all_process_columns = ohlcv_columns + (['__ROW_ID__'] if '__ROW_ID__' in column_map else [])
    
    for kbar_col in all_process_columns:
        if kbar_col in column_map:
            col_index = column_map[kbar_col] - 1
            series = df.iloc[:, col_index]
            
            if kbar_col == '__ROW_ID__': 
                 series = series.astype('Int64')
                 ohlcv_data[kbar_col] = series
                 continue
                 
            series_str = series.astype(str).str.strip() 
            series_cleaned = series_str.str.replace(',', '')
            
            debug(f"[DEBUG] Conversion Cleaned String Preview for {kbar_col}: {series_cleaned.iloc[:5].to_list()}")
            series_numeric = pd.to_numeric(series_cleaned, errors='coerce')
            debug(f"[DEBUG] Conversion Numeric Result Preview for {kbar_col}: {series_numeric.iloc[:5].to_list()}")
            
            if to_int_conversion:
                series = series_numeric.round().astype('Int64') 
            else:
                series = series_numeric.astype(np.float64) 
                
            ohlcv_data[kbar_col] = series 
        else:
            if kbar_col in ohlcv_columns:
                warn(f"Missing required K-bar column: {kbar_col}. It will be added as NaN.")
                ohlcv_data[kbar_col] = np.nan 

    # --- 行數一致性檢查 ---
    if has_datetime_keys:
        dt_valid_count = datetime_series.notna().sum()
        
        ohlcv_max_valid_count = 0
        valid_ohlcv_series = [s for k, s in ohlcv_data.items() if isinstance(s, pd.Series) and k in ohlcv_columns]
        if valid_ohlcv_series:
            ohlcv_max_valid_count = max(s.count() for s in valid_ohlcv_series)
            
        if dt_valid_count != ohlcv_max_valid_count:
             warn(f"Data inconsistency detected. Datetime valid rows ({dt_valid_count}) != Max OHLCV valid rows ({ohlcv_max_valid_count}). Conversion stopped.")
             print(f"❌ 警告: 資料行數不一致。日期/時間有效行數 ({dt_valid_count}) 與 OHLCV 最大有效行數 ({ohlcv_max_valid_count}) 不符。轉換已中止。")
             return None
        
        info(f"Datetime/OHLCV row check passed. Valid rows: {dt_valid_count}.")


    # --- 3. 組裝最終 DataFrame ---
    if not ohlcv_data:
        error("No OHLCV columns were successfully mapped.")
        return None
        
    df_new = pd.DataFrame(ohlcv_data) 
    
    if '__ROW_ID__' in df_new.columns:
         cols = [col for col in df_new.columns if col != '__ROW_ID__'] + ['__ROW_ID__'] 
         df_new = df_new[cols]
    
    if has_datetime_keys: 
        df_new.index = datetime_series 
        df_new.index.name = 'Date'
        df_new = df_new[df_new.index.notna()]
        
        if not isinstance(df_new.index, pd.DatetimeIndex):
             df_new.index = pd.to_datetime(df_new.index, errors='coerce')
             df_new = df_new[df_new.index.notna()]

        df_new.index = df_new.index.strftime('%Y-%m-%d %H:%M:%S')
        df_new.index.name = 'Date' 
    else:
         df_new.index.name = "INDEX" 
        
    if df_new.empty:
        error("Processed DataFrame is empty after cleaning.")
        return None

    return df_new

def _get_column_index(prompt, max_cols, allow_empty=False):
    debug(f"[ENTER] {sys._getframe(0).f_code.co_name}", print_to_console=False) 
    while True:
        try:
            user_input = _log_input(f"   請輸入 {prompt} 欄位編號 (1-{max_cols})" + (", 或按 Enter 分開輸入日期/時間" if allow_empty else "") + ": ").strip()
            
            if allow_empty and not user_input:
                return None 
            
            col_index = int(user_input)
            if 1 <= col_index <= max_cols:
                return col_index
            else:
                print(f"❌ 錯誤: 請輸入 1 到 {max_cols} 之間的有效數字。")
        except ValueError:
            print("❌ 錯誤: 請輸入有效的數字。")
            
def _map_data_columns_and_process(file_path, config): 
    """Steps through the column mapping and conversion process."""
    debug(f"[ENTER] {sys._getframe(0).f_code.co_name}", print_to_console=False) 
    
    info(f"Starting external data conversion for: {file_path}") 
    print("\n======== Data Conversion Hub (T) - External Source Conversion ========")
    print(f"1. 來源檔案: {os.path.basename(file_path)}")
    
    try:
        df = pd.read_csv(file_path)
        df.columns = [f'Col{i+1}' for i in range(len(df.columns))] 
        
    except Exception as e:
        error(f"Error reading file {file_path}: {e}") 
        print(f"❌ 錯誤: 無法讀取檔案或檔案格式不符 CSV 要求: {e}")
        _log_input("Press Enter to返回主選單...")
        return

    max_cols = len(df.columns)
    column_map = {}
    
    if df.empty:
        warn(f"File {file_path} is empty.") 
        print("❌ 錯誤: 檔案內容為空。")
        _log_input("Press Enter to返回主選單...")
        return
        
    # [FIX] Use local import to avoid circular dependency if needed, 
    # though shared.config_manager is already imported as current module context
    from shared.config_manager import clear_screen
    clear_screen()
    print("================================================================================")
    print("2. 欄位對應:")
    print("--------------------------------------------------------------------------------")
    print(f"總欄位數: {max_cols}")
    print("範例資料 (第一筆 - 格式: [編號] 欄位值 <型態>):") 
    
    for i, col_data in enumerate(df.iloc[0].values):
        col_series = df.iloc[:, i]
        data_type = _determine_data_type(col_series)
        print(f"  [#{i+1}] {str(col_data)} {data_type}")
    
    print("--------------------------------------------------------------------------------")

    datetime_col = _get_column_index("<日期時間>", max_cols, allow_empty=True)
    
    if datetime_col is not None:
        column_map['datetime'] = datetime_col
    else:
        date_col = _get_column_index("<日期>", max_cols)
        time_col = _get_column_index("<時間>", max_cols)
        column_map['date'] = date_col
        column_map['time'] = time_col

    column_map['Open'] = _get_column_index("<開盤價>", max_cols)
    column_map['High'] = _get_column_index("<最高價>", max_cols)
    column_map['Low'] = _get_column_index("<最低價>", max_cols)
    column_map['Close'] = _get_column_index("<收盤價>", max_cols)
    column_map['Volume'] = _get_column_index("<成交量>", max_cols)
    
    print("--------------------------------------------------------------------------------")

    debug(f"[DEBUG] Column Mapping: {column_map}")

    print("3. 數值清理預覽 (移除空白/逗號後):")
    preview_data = []
    preview_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    
    for kbar_col in preview_cols:
        col_index = column_map.get(kbar_col)
        if col_index is not None and col_index <= len(df.columns): 
            series = df.iloc[:, col_index - 1]
            cleaned_series = series.astype(str).str.strip().str.replace(',', '')
            cleaned_value = cleaned_series.iloc[0]
            data_type = _determine_data_type(cleaned_series)
            preview_data.append(f"[{kbar_col}:{cleaned_value}{data_type}]") 
    
    if preview_data:
        print("   " + ", ".join(preview_data))
    else:
        print("   (未選取任何數值欄位)")
    print("--------------------------------------------------------------------------------")

    to_int_conversion = False
    
    clean_input = _log_input("   是否將所有數字欄位取整數 (y/N)? ").strip().lower()
    
    if clean_input == 'y':
        df_test = _preview_int_conversion(df, column_map, max_cols)
        
        if df_test is not None and not df_test.empty:
            print("\n   ✨ 整數轉換預覽 (第一筆資料):")
            display_cols = [col for col in ['Open', 'High', 'Low', 'Close', 'Volume'] if col in df_test.columns]
            print(df_test.iloc[0][display_cols].to_string()) 
            
            confirm_input = _log_input("   ✅ 確認對所有資料執行整數轉換嗎 (Y/n)? ").strip().lower()
            if confirm_input == 'y' or confirm_input == '':
                to_int_conversion = True
                debug("[DEBUG] Integer conversion confirmed by user (Y).")
            else:
                debug("Integer conversion cancelled by user (N).")
        else:
            print("   預覽失敗（可能是選取欄位非數字），將不會執行整數轉換。")
            debug("[DEBUG] Integer conversion preview failed, conversion cancelled.")
    else:
         debug("[DEBUG] Integer conversion skipped by user (N).")
    
    print("--------------------------------------------------------------------------------")
    info(f"Mapping: {column_map}, To Int: {to_int_conversion}") 
    print("4. 開始轉換資料結構...")
    
    df_final = _do_conversion(file_path, df, column_map, to_int_conversion)
    
    if df_final is None:
        print("❌ 轉換失敗，請參閱日誌獲取詳細資訊。")
        _log_input("Press Enter to返回主選單...")
        return
        
    print("\n5. 轉換成功! 最終資料範例 (前五筆):")
    
    df_display = df_final.head().copy()
    
    if df_display.index.name:
         df_display.index.name = f"[*]{df_display.index.name}"
    
    print(df_display.to_string()) 
    
    print(f"   總共轉換了 {len(df_final)} 筆資料。")

    default_filename = os.path.basename(file_path).replace('.csv', f'_CONVERTED.csv')
        
    save_to_csv_external(df_final, default_filename)


def parse_frequency_from_filename(filename):
    """Attempts to parse K-bar frequency (e.g., '15minK') from a filename."""
    debug(f"[ENTER] {sys._getframe(0).f_code.co_name}", print_to_console=False)
    match = re.search(r'(\d+)minK\.csv$', filename, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return BASE_FREQ 

def transform_data_frequency(fm):
    """Transforms the frequency of a selected K-bar CSV file."""
    debug(f"[ENTER] {sys._getframe(0).f_code.co_name}", print_to_console=False)
    
    file_path = list(fm.selected_files.values())[0]
    filename = os.path.basename(file_path)

    info(f"Starting frequency transformation for: {file_path}")
    print("\n======== Data Conversion Hub (T) - Frequency Transformation ========\n")
    print(f"1. 來源檔案: {filename}")
    
    try:
        original_freq = parse_frequency_from_filename(filename)
    except Exception:
        original_freq = BASE_FREQ

    if original_freq != BASE_FREQ:
        print(f"   從檔名解析到原始頻率: {original_freq} 分鐘。")
    
    while True:
        target_freq_input = _log_input(f"   請輸入目標 K 棒頻率 (分鐘) [大於 {BASE_FREQ}] (Q 結束): ").strip().upper()
        
        if target_freq_input == 'Q':
            info("Frequency transformation cancelled by user.")
            return
            
        try:
            target_freq = int(target_freq_input)
            if target_freq <= original_freq:
                 print(f"❌ 錯誤: 目標頻率必須大於原始頻率 ({original_freq})。")
                 continue
            if target_freq % BASE_FREQ != 0:
                 print(f"❌ 警告: 建議目標頻率為 {BASE_FREQ} 的倍數。")
            
            break
        except ValueError:
            print("❌ 錯誤: 請輸入有效的數字。")
            
    print(f"   目標頻率: {target_freq} 分鐘。")
    print("--------------------------------------------------------------------------------")

    print("2. 讀取並重採樣 K 棒數據...")
    try:
        df_1min = pd.read_csv(file_path, index_col=0, parse_dates=True)
        df_1min.index.name = 'Date'
        df_final = resample_kbar(df_1min, target_freq)
        
    except Exception as e:
        error(f"Error reading or resampling file: {e}")
        print(f"❌ 錯誤: 讀取或重採樣檔案失敗: {e}")
        _log_input("Press Enter to返回主選單...")
        return
        
    print("\n3. 重採樣成功! 最終資料範例 (前五筆):")
    df_display = df_final.head().copy()
    df_display.index.name = f"[*]{df_display.index.name}"
    print(df_display.to_string())
    print(f"   總共產生了 {len(df_final)} 筆資料。")
    
    date_part_match = re.search(r'(\d{8}_\d{8})', filename)
    date_part = date_part_match.group(1) if date_part_match else 'NODATE'
    default_filename = f"{filename.split('_')[0]}_{date_part}_{target_freq}minK.csv"
    
    save_to_csv_external(df_final, default_filename)


def transform_other_source(fm, config): 
    debug(f"[ENTER] {sys._getframe(0).f_code.co_name}", print_to_console=False) 
    
    info("Starting conversion of other historical data sources.") 
    
    file_path = fm.run_file_selection(prompt="請選擇要轉換的 CSV 檔案 (輸入數字選取, Q 結束):")
    
    if file_path is None:
        info("External Source Conversion cancelled by user.") 
        return
        
    _map_data_columns_and_process(file_path, config)
    
    _log_input("Press Enter to返回主選單...")


def data_transformation_hub(fm, config): 
    debug(f"[ENTER] {sys._getframe(0).f_code.co_name}", print_to_console=False) 
    while True:
        from shared.config_manager import clear_screen
        clear_screen()
        print("================================================================================")
        print("Data Transformation Hub (T) - Select Mode")
        print("================================================================================")
        print("1: 轉換 K 棒檔案頻率 (Transform Frequency) - 適用於已選取的 K 棒檔案")
        print("2: 轉換其他歷史資料源 (External Source Conversion)")
        print("Q: Return to Main Menu")
        
        default_choice = '1' if len(fm.selected_files) == 1 else '2'
        
        print("--------------------------------------------------------------------------------")
        
        user_input = _log_input(f"Enter command (1/2/Q) [Default: {default_choice}]: ").strip().upper() or default_choice

        if user_input == 'Q':
            return
        
        elif user_input == '1':
            if len(fm.selected_files) != 1:
                warn("Frequency Transform selected, but not exactly one file is chosen.") 
                print("❌ 錯誤: 選擇『1. 轉換 K 棒檔案頻率』功能，請確保**只選取一個** K 棒檔案。")
                _log_input("Press Enter to continue...")
                continue
            transform_data_frequency(fm)
            return
            
        elif user_input == '2':
            transform_other_source(fm, config)
            return
        
        else:
            warn(f"Invalid transformation command: {user_input}") 
            print(f"Invalid command: {user_input}")
            time.sleep(1)