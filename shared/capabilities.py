# ==============================================================================
# shared/capabilities.py
#
# Version: V1.0-000
# 描述:     SATE 系統能力 (Capabilities) 定義。
#           用於 Service Discovery 階段，Service 向 Client 宣告自身支援的功能。
# ==============================================================================

# 提供即時行情 (Tick/KBar) 訂閱與廣播
CAP_MARKET_DATA = "CAP_MARKET_DATA"

# 提供下單、刪單、改單與回報功能
CAP_TRADE_EXEC = "CAP_TRADE_EXEC"

# 提供帳務查詢 (部位、權益數、損益)
CAP_ACCOUNT_INFO = "CAP_ACCOUNT_INFO"

# 提供歷史數據下載與查詢 (補資料)
CAP_HISTORICAL_DATA = "CAP_HISTORICAL_DATA"

# 提供回測運算引擎
CAP_BACKTEST_ENGINE = "CAP_BACKTEST_ENGINE"

# 提供策略託管與執行 (Server-side Strategy)
CAP_STRATEGY_HOST = "CAP_STRATEGY_HOST"

# 提供專案/檔案儲存庫服務
CAP_REPO_STORAGE = "CAP_REPO_STORAGE"