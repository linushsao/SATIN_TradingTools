# ==============================================================================
# view.py (WYSIWYG 邏輯同步版)
#
# 描述: 
#   1. 作為重疊指標執行，直接載入 strategy_core 以確保資料生產方式與策略模組一致。
#   2. 實現「所見即所得」，在預覽介面即可看到由核心產出的狀態延續交易線。
# ==============================================================================

import numpy as np
import pandas as pd

# 1. 以相同方式載入策略核心
try:
    # 確保 strategy_core.py 與此檔案位於相同路徑或已加入 sys.path
    from strategy_core import calc_indicators, calc_trading_lines
except ImportError:
    calc_indicators = None
    calc_trading_lines = None

# 2. 獲取原始數據 (由指標引擎傳入之 K_BAR_DATA)
df = K_BAR_DATA.copy()

# 3. 執行與「策略模組」完全相同的數據產出流程
if calc_indicators and calc_trading_lines:
    # 這裡使用的參數應與策略實例 (metadata.json) 中的設定趨於一致
    # 在指標預覽模式下，我們使用標準預設值或從全域配置獲取
    default_params = {
        'frequency': 20, 
        'stop_loss_pct': 0.02, 
        'take_profit_pct': 0.05
    }
    
    # 調用核心運算：產生 ma, entry_line, sl_line, tp_line 等欄位
    df = calc_indicators(df, period=default_params['frequency'])
    print(f"after calc_indicators")
    print(df.columns)
    df = calc_trading_lines(df, default_params)
    print(f"after calc_trading_lines")
    print(df.columns)
# 4. 視圖渲染：將計算結果注入渲染總線 ADDPLOT_CONFIG
# 此部分僅負責「顯示內容」的定義，不涉及業務邏輯
# 4. [修正]: 匯出 CSV 邏輯
print(f"[DB] Ready to export CSV...")
try:
    # 確保路徑存在或使用相對路徑防止權限問題
    output_path = 'C:/Temp/result_strcore.csv'
    # 檢查資料夾是否存在，若不存在則嘗試建立
    import os
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    print(f"顯示 df.columns")
    print(df.columns)
    df.to_csv(output_path)
    print(f"[DB] Export successful: {output_path}")
except Exception as e:
    # [修正]: 改用 Exception 擷取所有可能的錯誤 (如檔案被佔用或權限不足)
    print(f"[Error] 匯出 CSV 失敗: {e}")
# A. 基礎指標渲染
if 'ma' in df.columns:
    ADDPLOT_CONFIG.append({
        'data': df['ma'].values,
        'kwargs': {'color': 'gray', 'width': 1, 'label': 'MA'}
    })

# B. 交易狀態延續線渲染 (正多負空，0則不顯示)
if 'entry_line' in df.columns:
    # 將 0 替換為 NaN 確保連線在出場時斷開
    entry_data = df['entry_line'].abs().replace(0, np.nan).values
    ADDPLOT_CONFIG.append({
        'data': entry_data,
        'kwargs': {'color': 'magenta', 'width': 2, 'label': 'Entry Level'}
    })

if 'sl_line' in df.columns:
    sl_data = df['sl_line'].replace(0, np.nan).values
    ADDPLOT_CONFIG.append({
        'data': sl_data,
        'kwargs': {'color': 'red', 'width': 1, 'linestyle': '--', 'label': 'SL'}
    })

if 'tp_line' in df.columns:
    tp_data = df['tp_line'].replace(0, np.nan).values
    ADDPLOT_CONFIG.append({
        'data': tp_data,
        'kwargs': {'color': 'green', 'width': 1, 'linestyle': '--', 'label': 'TP'}
    })