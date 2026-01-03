# ==============================================================================
# strategy_core.py
# Version: V0.1-001
# 描述: 策略運算核心。實作 MA20 突破邏輯，並產出狀態延續的交易三線。
# ==============================================================================

import pandas as pd
import numpy as np

def calc_indicators(df: pd.DataFrame, period: int):
    """
    [基礎指標運算]
    計算 MA20。
    """
    df = df.copy()
    df['ma'] = df['Close'].rolling(window=period).mean()
    df['std'] = df['Close'].rolling(window=period).std()
    return df

def calc_trading_lines(df: pd.DataFrame, parameters: dict):
    """
    [交易線狀態延續運算]
    核心任務：產出 entry_line (正負號分多空), sl_line, tp_line。
    
    狀態延續邏輯：一旦進場，三條線的值會持續延伸到觸發出場為止。
    """
    df = df.copy()
    _period = parameters.get('frequency', 20)
    # 初始化輸出數組 (全為 0)
    entry_arr = np.zeros(len(df))
    sl_arr = np.zeros(len(df))
    tp_arr = np.zeros(len(df))
    
    # 狀態機變數
    # 0: 空手, 1: 多頭持倉, -1: 空頭持倉
    current_state = 0  
    last_entry, last_sl, last_tp = 0.0, 0.0, 0.0

    # 時序遍歷，建立狀態延續
    for i in range(1, len(df)):
        price = df['Close'].iloc[i]
        p_high = df['High'].iloc[i]
        p_low = df['Low'].iloc[i]
        ma_val = df['ma'].iloc[i]
        prev_price = df['Close'].iloc[i-1]
        prev_ma = df['ma'].iloc[i-1]
        std_tp = df['std'].iloc[i]*1.654
        std_sl = df['std'].iloc[i]*0.657
        
        # --- 判斷進場 (狀態 0 -> 1 或 -1) ---
        if i > _period:
            if p_high > ma_val and prev_price <= prev_ma:  # 向上突破
                current_state = 1
                last_entry = ma_val          # 多頭進場為正值
                last_sl = ma_val + std_tp
                last_tp = ma_val - std_sl
            elif p_low < ma_val and prev_price >= prev_ma: # 向下突破
                current_state = -1
                last_entry = -ma_val         # 空頭進場為負值
                last_sl = ma_val - std_tp
                last_tp = ma_val + std_sl

        entry_arr[i] = last_entry
        sl_arr[i] = last_sl
        tp_arr[i] = last_tp

    # df['entry_line'] = entry_arr
    # df['sl_line'] = sl_arr
    # df['tp_line'] = tp_arr
# 3. 狀態延續處理
    df['entry_line'] = pd.Series(entry_arr).replace(0, np.nan).ffill().fillna(0).values
    df['sl_line'] = pd.Series(sl_arr).replace(0, np.nan).ffill().fillna(0).values
    df['tp_line'] = pd.Series(tp_arr).replace(0, np.nan).ffill().fillna(0).values  
    
    return df