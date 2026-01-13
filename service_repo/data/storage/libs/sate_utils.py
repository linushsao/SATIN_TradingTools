# ==============================================================================
# libs/sate_utils.py
# 描述: SATE 策略通用工具庫
# ==============================================================================
import pandas as pd
import numpy as np

def apply_std_output(df: pd.DataFrame, 
                     sig_long: pd.Series, long_e, long_sl, long_tp,
                     sig_short: pd.Series, short_e, short_sl, short_tp):
    """
    [標準輸出轉換器]
    將策略的多空條件轉換為 SATE 標準的三線格式 (Entry/SL/TP) + 訊號 (Signal)。
    並執行狀態延續 (Latching) 處理。
    """
    # 1. 初始化標準欄位
    df['trend_signal'] = 0
    df['entry_line'] = np.nan
    df['sl_line'] = np.nan
    df['tp_line'] = np.nan
    
    # 2. 寫入多頭觸發 (Signal = 1)
    df.loc[sig_long, 'trend_signal'] = 1
    df.loc[sig_long, 'entry_line'] = long_e
    df.loc[sig_long, 'sl_line'] = long_sl
    df.loc[sig_long, 'tp_line'] = long_tp
    
    # 3. 寫入空頭觸發 (Signal = -1)
    df.loc[sig_short, 'trend_signal'] = -1
    
    # 確保空單 Entry 為負值 (符合 U4-1 規範)
    if isinstance(short_e, pd.Series):
        df.loc[sig_short, 'entry_line'] = -short_e.abs()
    else:
        df.loc[sig_short, 'entry_line'] = -abs(short_e)
        
    df.loc[sig_short, 'sl_line'] = short_sl
    df.loc[sig_short, 'tp_line'] = short_tp
    
    # 4. 狀態延續 (Latching with Forward Fill)
    # 消除 NaN，形成連續階梯線
    df['entry_line'] = df['entry_line'].ffill()
    df['sl_line'] = df['sl_line'].ffill()
    df['tp_line'] = df['tp_line'].ffill()
    
    return df
