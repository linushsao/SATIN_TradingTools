# =============================================================================
# 所屬檔案名稱: shared/backtest/engine.py
# 描述: 跨平台通用回測引擎 - 支援 SATIN 三線協定與價格穿透判斷。
# =============================================================================
import pandas as pd
import numpy as np
from .metrics import QuantMetrics

class UniversalBacktestEngine:
    def run_task(self, data: pd.DataFrame, strategy_module, params: dict) -> dict:
        """
        執行單一回測任務。
        :param strategy_module: 具備 calculate 介面的策略模組
        """
        # 1. 執行策略運算，產出數據總線
        df = strategy_module.calculate(data, params)
        
        total_steps = len(df)
        signals = []
        current_pos = 0  # 持倉狀態: 1, -1, 0
        
        # 2. 提取數組進行時序穿透判斷
        highs = df['High'].values
        lows = df['Low'].values
        entries = df['entry_line'].values
        sls = df['sl_line'].values
        tps = df['tp_line'].values

        for i in range(total_steps):
            entry_val = entries[i]
            prev_entry = entries[i-1] if i > 0 else 0
            
            # 判斷新進場 (entry_line 跳變且非 0)
            if entry_val != 0 and entry_val != prev_entry:
                current_pos = 1 if entry_val > 0 else -1
            
            # 持倉中檢查出場 (SL/TP 穿透)
            elif current_pos != 0:
                sl, tp = sls[i], tps[i]
                if current_pos == 1:
                    if lows[i] <= sl or highs[i] >= tp: current_pos = 0
                elif current_pos == -1:
                    if highs[i] <= sl or lows[i] <= tp: current_pos = 0
            
            signals.append(current_pos)

        # 3. 計算績效
        df['signal'] = signals
        log_returns = QuantMetrics.calculate_log_return_series(df['Close'], df['signal'])
        result = QuantMetrics.get_performance_summary(log_returns)
        result['signal_series'] = signals
        return result