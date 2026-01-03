# =============================================================================
# 所屬檔案名稱: shared/backtest/metrics.py
# 描述: 量化分析專用績效計算模組 (支援資產曲線與回撤曲線)
# =============================================================================
import numpy as np
import pandas as pd

class QuantMetrics:
    @staticmethod
    def calculate_log_return_series(price_series: pd.Series, signal_series: pd.Series) -> pd.Series:
        """
        計算策略的對數報酬序列。
        公式: r_t = Signal_{t-1} * ln(P_t / P_{t-1})
        """
        market_log_returns = np.log(price_series / price_series.shift(1))
        strategy_log_returns = signal_series.shift(1) * market_log_returns
        return strategy_log_returns.fillna(0.0)

    @staticmethod
    def get_performance_summary(log_returns: pd.Series):
        """
        產出統計摘要與完整的曲線序列。
        """
        # 1. 計算資產曲線 (Equity Curve)
        cum_log_return_series = log_returns.cumsum()
        equity_curve = np.exp(cum_log_return_series)
        
        # 2. 計算回撤曲線 (Drawdown Curve)
        running_max = equity_curve.cummax()
        drawdown_curve = (equity_curve / running_max) - 1
        
        # 3. 彙整指標
        total_return = equity_curve.iloc[-1] - 1 if not equity_curve.empty else 0
        max_drawdown = drawdown_curve.min() if not drawdown_curve.empty else 0
        
        return {
            "total_return": float(total_return),
            "cum_log_return": float(cum_log_return_series.iloc[-1]) if not log_returns.empty else 0,
            "max_drawdown": float(max_drawdown),
            "volatility": float(log_returns.std() * np.sqrt(252 * 24)) if len(log_returns) > 0 else 0,
            "equity_curve": equity_curve.tolist(),
            "drawdown_curve": drawdown_curve.tolist()
        }