# ==============================================================================
# shared/protocol_defs.py
#
# Version: V1.2-000 (SSTP Caps)
# 描述:     SATE 系統協定定義檔。
#           定義環境模式、風險等級、健康狀態與通知級別的標準常數。
#           [新增]: SATIN 標準化協定 (SSTP) 之 Capabilities 定義。
# ==============================================================================

# --- Environment Modes (環境模式) ---
# 用於 metadata.mode，決定 Client 的全域主題顏色與警示強度
ENV_PRODUCTION = "PRODUCTION"   # 正式環境 (紅/高風險)
ENV_SIMULATION = "SIMULATION"   # 模擬環境 (綠/低風險)
ENV_BACKTEST = "BACKTEST"       # 回測環境 (灰/無風險)
ENV_DEVELOPMENT = "DEVELOPMENT" # 開發環境 (藍/中性)

# --- Risk Levels (風險等級) ---
# 用於 metadata.risk_level，決定 Client 是否開啟「二次確認」保護
RISK_HIGH = "HIGH"    # 高風險 (涉及真實資金)
RISK_LOW = "LOW"      # 低風險 (模擬資金)
RISK_NONE = "NONE"    # 無風險 (歷史數據/唯讀)

# --- Health Status (健康狀態) ---
# 用於 heartbeat.health.status，決定 System Monitor 的燈號
HEALTH_OK = "OK"       # 正常 (綠燈)
HEALTH_WARN = "WARN"   # 警告 (黃燈 - 功能降級或延遲高)
HEALTH_ERROR = "ERROR" # 錯誤 (紅燈 - 斷線或服務崩潰)

# --- Notification Levels (通知等級) ---
# 用於 SYS_NOTIFICATION 的 level
NOTIFY_LEVEL_INFO = "INFO"
NOTIFY_LEVEL_WARNING = "WARNING"
NOTIFY_LEVEL_ERROR = "ERROR"
NOTIFY_LEVEL_CRITICAL = "CRITICAL"

# --- Notification Display Types (通知展示方式) ---
# 用於 SYS_NOTIFICATION 的 display_type，指示 Kernel 如何打斷使用者
NOTIFY_DISPLAY_LOG = "LOG_ONLY"      # 僅寫入 Log，不打擾
NOTIFY_DISPLAY_TOAST = "TOAST"       # 右下角氣泡通知 (自動消失)
NOTIFY_DISPLAY_MODAL = "MODAL_ALERT" # 置頂彈窗 (必須點擊確認)

# --- User Roles (使用者角色) ---
# 用於 config.user_role，決定 Client GUI 的功能權限
ROLE_DEVELOPER = "DEVELOPER"       # 開發者 (全權限：編輯程式碼、部署、設定)
ROLE_TRADING_MANAGER = "MANAGER"   # 交易經理 (監控、風控、策略啟停、但不可改 Code)
ROLE_TRADER = "TRADER"             # 一般交易員 (僅操作特定策略或手動下單)

# --- [NEW] SATIN Standardized Capabilities (SSTP) ---
# 用於 Service 向 Client 宣告自身支援的 SSTP 協定模組
CAP_DATA_FEED = "CAP_DATA_FEED"             # 行情數據協定 (Tick/KBar 廣播)
CAP_EXECUTION = "CAP_EXECUTION"             # 交易執行協定 (下單/回報)
CAP_ACCOUNT = "CAP_ACCOUNT"                 # 帳務狀態協定 (權益/部位查詢)
CAP_HISTORY_BACKTEST = "CAP_HISTORY_BACKTEST" # 歷史數據與回測協定 (回補/任務/結果)
CAP_STRATEGY_HOST = "CAP_STRATEGY_HOST"     # 策略託管協定 (生命週期/參數/狀態)