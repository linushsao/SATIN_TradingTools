# ==============================================================================
# shared/constants.py
#
# Version: V1.3-001 (Dynamic Schema)
# 更新日期: 2025-12-09
# 描述:     系統共用常數定義
#           V1.3-001: 新增策略參數 Schema 相關常數 (Phase 8)。
#           V1.2-001: 新增 TOPIC_SYS_NOTIFICATION。
# ==============================================================================

# ZMQ Commands (General)
CMD_DEPLOY_STRATEGY = "DEPLOY_STRATEGY"
CMD_GET_CAPABILITIES = "GET_CAPABILITIES" 
CMD_GET_STRATEGY_SCHEMA = "GET_STRATEGY_SCHEMA" # [NEW]

# ZMQ Pub Topics
TOPIC_SYS_NOTIFICATION = "SYS_NOTIFICATION" 

# Deployment Modes
DEPLOY_MODE_BROADCAST = "BROADCAST"    
DEPLOY_MODE_TASK = "TASK_BASED"        

# Backtest Packet Keys
PACKET_KEY_SOURCE_ID = "source_id"      
PACKET_KEY_STRAT_CODE = "strat_code"    
PACKET_KEY_CORE_CODE = "core_code"      
PACKET_KEY_PARAMS = "params"            
PACKET_KEY_CREATED_AT = "created_at"    

# Schema Field Types [NEW]
TYPE_STR = "string"
TYPE_INT = "integer"
TYPE_FLOAT = "float"
TYPE_BOOL = "boolean"
TYPE_SELECT = "select"          # 固定選項下拉
TYPE_DYNAMIC_SELECT = "dynamic_select" # 動態資料源下拉 (如帳號列表)

# Schema Dynamic Sources [NEW]
SOURCE_CONTRACTS = "contracts"      # 來自 MarketData 的合約列表
SOURCE_ACCOUNTS = "accounts"        # 來自 AccountInfo 的帳號列表
SOURCE_STRATEGY_FILES = "strategy_files" # 來自本地的工作區檔案