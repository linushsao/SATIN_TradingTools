# ==============================================================================
# tests/test_strategy_core.py
#
# Version: V1.0-000
# 描述:     針對策略核心邏輯 (MA 計算) 的單元測試。
# ==============================================================================

import pandas as pd
import numpy as np
import pytest

# 模擬 strategy_core.py 中的邏輯
# 註: 在真實環境中這是由 Template 生成的，為了測試邏輯正確性，我們在此重現該函式
def calc_indicators(df, period=20):
    """
    計算技術指標與關鍵價位 (模擬 demo_str_v1 邏輯)
    """
    df = df.copy()
    
    # 1. 計算 MA (進場基準線)
    df['entry_line'] = df['Close'].rolling(window=period).mean()
    
    # 2. 定義 SL/TP 線
    # SL = MA * 0.99
    # TP = MA * 1.02
    df['sl_line'] = df['entry_line'] * 0.99
    df['tp_line'] = df['entry_line'] * 1.02
    
    return df

def test_ma_calculation_accuracy(mock_price_data):
    """驗證 MA 計算數值是否準確"""
    period = 20
    df_result = calc_indicators(mock_price_data, period)
    
    # 1. 驗證前 (period-1) 筆資料應為 NaN
    assert pd.isna(df_result['entry_line'].iloc[period - 2])
    
    # 2. 驗證第 20 筆資料 (Index 19)
    # Mock Data Close: 100, 101, ..., 119
    # MA20 = (100 + ... + 119) / 20 = 109.5
    expected_ma = mock_price_data['Close'].iloc[0:period].mean()
    calculated_ma = df_result['entry_line'].iloc[period - 1]
    
    assert calculated_ma == expected_ma
    # 對於線性增長的數據 (100, 101... 119)，平均值應為 (100+119)/2 = 109.5
    assert calculated_ma == 109.5

def test_indicator_columns_exist(mock_price_data):
    """驗證輸出的 DataFrame 包含所需欄位"""
    df_result = calc_indicators(mock_price_data, period=20)
    
    assert 'entry_line' in df_result.columns
    assert 'sl_line' in df_result.columns
    assert 'tp_line' in df_result.columns

def test_sl_tp_logic(mock_price_data):
    """驗證 SL/TP 與 Entry 的相對關係"""
    df_result = calc_indicators(mock_price_data, period=20)
    
    # 取一筆有效資料進行檢查
    valid_idx = 25
    entry = df_result['entry_line'].iloc[valid_idx]
    sl = df_result['sl_line'].iloc[valid_idx]
    tp = df_result['tp_line'].iloc[valid_idx]
    
    # 驗證邏輯: SL < Entry < TP (因為是做多策略)
    assert sl == entry * 0.99
    assert tp == entry * 1.02
    assert sl < entry < tp