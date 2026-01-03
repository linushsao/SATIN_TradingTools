# ==============================================================================
# strategy.py
#
# Version: V0.1-001
# 更新日期: 2025-12-27
# 描述: 策略模組。接收策略實例參數(參數化)並調用運算核心，產出標準數據總線。
# ==============================================================================
# 更新日誌:
# V0.1-001: 統一使用 df_data 接口，並根據實例參數產出具備狀態延續之交易線數據。
# ==============================================================================

from strategy_core import calc_indicators, calc_trading_lines

def calculate(k_bar_data, parameters):
    """
    [策略模組入口]
    功能: 接收 k_bar_data 與來自 UI/Metadata 的策略實例參數。
    """
    # 1. 策略實例參數提取 (例如頻率、停損比率、合約代碼等)
    period = parameters.get('frequency', 20)
    
    # 2. 執行指標運算 (MA20)
    # 不需解耦的核心運算邏輯
    df_data = calc_indicators(k_bar_data, period)
    
    # 3. 執行交易線運算 (進場/停損/停利)
    # 核心將根據 parameters 產出具備狀態延續特性的交易三線數據
    df_data = calc_trading_lines(df_data, parameters)
    
    # 返回標準化後的數據總線供視圖層使用
    return df_data