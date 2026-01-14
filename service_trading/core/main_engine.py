# ==============================================================================
# service_trading/core/main_engine.py
#
# Version: V2.4-003 (Schema Fix)
# 更新日期: 2025-12-18
# 描述:     交易引擎核心。
#           [修正]: 
#             1. 啟動時載入 strategy_schema.json。
#             2. 在 GET_CAPABILITIES 註冊回應中附加 strategy_schema，
#                解決 Client 端無法產生策略參數表單的問題。
# ==============================================================================

import sys
import time
import threading
import datetime
import os
import pandas as pd
import json

# Shared Modules
from shared.zmq_manager import ZmqServer
from shared.config_manager import load_config
# --- [核心修正] 修正匯入名稱，移除 log_end ---
from shared.logging_tool import init_logger, info, error, warn, init_debug_mode
from shared.constants import CMD_GET_STRATEGY_SCHEMA, TOPIC_SYS_NOTIFICATION, CMD_GET_CAPABILITIES
from shared.protocol_defs import HEALTH_OK, HEALTH_ERROR, HEALTH_WARN
# Core Modules
from market_data_manager import MarketDataManager
from trading_manager import TradingManager
from account_manager import AccountManager
from strategy_executor import StrategyExecutor
from deploy_manager import DeployManager
from broker_factory import BrokerFactory 

try:
    from touchprice.touch_price import TouchOrderExecutor
    HAS_TOUCH = True
except ImportError:
    HAS_TOUCH = False

# Globals
server = None
adapters = {}
primary_adapter = None 
config = None
data_manager = None
trading_manager = None
account_manager = None
strategy_executor = None
deploy_manager = None
touch_executor = None 
restart_required = False 
running = True 
internet_connected = False
last_net_check_time = 0
strategy_schema = {} 
discovered_services = {}  # 格式: {"service_id": last_seen_timestamp}

# 1. 在檔案開頭全域變數區新增註冊表
discovered_services = {}  # 格式: {"service_id": last_seen_timestamp}

def on_heartbeat_received(payload):
    """
    [新增]: 處理來自其他服務的心跳封包。
    """
    global discovered_services
    svc_id = payload.get("service_id") or payload.get("service_name")
    if svc_id:
        # 更新該服務最後一次出現的時間戳記
        discovered_services[svc_id] = time.time()

def is_repo_service_alive():
    """
    [新增]: 判定 Repo 服務目前是否在線。
    判定標準：最後一次心跳更新在 5 秒內。
    """
    global discovered_services
    # 這裡的 ID 需對應 service_repo 的 config.json 設定
    repo_id = "StrategyRepoService" 
    last_seen = discovered_services.get(repo_id, 0)
    return (time.time() - last_seen) < 5.0

def _load_schema():
    """
    [FIX] 載入策略參數定義檔 (Schema)。
    位置預設為 service_trading/strategy_schema.json
    """
    global strategy_schema
    try:
        # 假設 main_engine.py 在 service_trading/core/ 下，schema 在 service_trading/ 下
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        schema_path = os.path.join(base_dir, 'strategy_schema.json')
        
        if os.path.exists(schema_path):
            with open(schema_path, 'r', encoding='utf-8') as f:
                strategy_schema = json.load(f)
            info(f"[Main] Strategy Schema loaded from: {schema_path}")
        else:
            warn(f"[Main] Schema file not found at {schema_path}. Client UI may not render forms correctly.")
            strategy_schema = {}
            
    except Exception as e:
        error(f"[Main] Failed to load strategy schema: {e}")
        strategy_schema = {}

def _run_engine_login(simulation_mode): 
    
    #global adapters, config
    global adapters, config, strategy_executor, account_manager
    info(f"[Engine] Starting multi-broker login process. Simulation: {simulation_mode}")
    results = {}
    success_count = 0
    for name, adapter in adapters.items():
        info(f"[Engine] Connecting to broker: {name}...")
        try:
            if adapter.connect(simulation=simulation_mode):
                info(f"[Engine] Broker '{name}' Connected.")
                success_count += 1
                results[name] = "OK"
            else:
                error(f"[Engine] Broker '{name}' Connect Failed.")
                results[name] = "FAIL"
        except Exception as e:
            error(f"[Engine] Broker '{name}' Exception: {e}")
            results[name] = str(e)

    if account_manager:
        account_manager._refresh_account_map()

    # if success_count > 0 and strategy_executor:
        # strategy_executor.resume_all_strategies()
    if success_count > 0:
        if strategy_executor:
            # 正常啟動流程
            strategy_executor.resume_all_strategies()
        else:
            # 異常：券商連線成功，但執行器物件不存在
            error("[Engine] 策略恢復失敗：strategy_executor 組件尚未初始化。")
    else:
        # 異常：沒有任何券商連線成功
        warn("[Engine] 策略未啟動：沒有任何券商成功連線，請檢查網路或憑證。")
        
    status = "ok" if success_count > 0 else "error"
    return {"status": status, "msg": f"Login finished. {success_count}/{len(adapters)} connected.", "details": results}

def _get_common_contracts_info():
    if primary_adapter: return primary_adapter.get_contracts()
    return []

def _download_worker(code, start_date, end_date):
    # This worker is for explicit DOWNLOAD_HISTORY command
    # For implicit backfill, MarketDataManager handles it synchronously (or internal async)
    global data_manager
    if not data_manager: return
    data_manager._download_and_save_data(code, start_date, end_date)
    info(f"[BgWorker] Explicit download finished for {code}.")

def _download_and_save_history(code, start_date, end_date):
    global data_manager
    if not data_manager: return False, "Database not initialized"
    t = threading.Thread(target=_download_worker, args=(code, start_date, end_date), daemon=True)
    t.start()
    return True, "Download Started (Background)"

def handle_client_command(message: dict):
    global data_manager, trading_manager, account_manager, strategy_executor, restart_required, server, running, strategy_schema
    cmd = message.get('cmd'); args = message.get('args', {})
    info(f"[Engine] CMD: {cmd}")
    
    try:
        if cmd == "PING": 
            payload = {"status": "ok", "msg": "PONG", "time": str(datetime.datetime.now()), "security": {"level": config.get('security', {}).get('level', 'NONE')}}
            return payload
            
        elif cmd == CMD_GET_CAPABILITIES:
            # [FIX] 在註冊回應中包含 strategy_schema
            return {
                "status": "ok", 
                "service_id": config.get('service_name'), 
                "version": "2.4.1", # Updated version
                "capabilities": config.get('capabilities', []), 
                "environment_profile": config.get('environment_profile', {}),
                "strategy_schema": strategy_schema # <--- 關鍵修正：將 Schema 傳送給 Client
            }
            
        elif cmd == CMD_GET_STRATEGY_SCHEMA: return {"status": "ok", "schema": strategy_schema}
        elif cmd == "RESTART": restart_required=True; server.running=False; return {"status": "ok", "msg": "Restarting"}
        elif cmd == "SHUTDOWN": server.running=False; running = False; return {"status": "ok", "msg": "Bye"}
        elif cmd == "LOGIN": return _run_engine_login(args.get('simulation', True))
        elif cmd == "GET_CONTRACTS": return {"status": "ok", "data": _get_common_contracts_info()}
        elif cmd == "GET_ACCOUNTS": 
            data = account_manager.get_all_accounts() if account_manager else []
            return {"status": "ok", "data": data} 
        elif cmd == "GET_POSITIONS":
            if account_manager:
                acc_id = args.get('account_id')
                return {"status": "ok", "data": account_manager.get_positions(acc_id).get('positions', [])}
            return {"status": "error", "msg": "AccountManager not ready"}
        elif cmd == "GET_ACCOUNT_INFO":
            if account_manager:
                acc_id = args.get('account_id')
                return {"status": "ok", "data": account_manager.get_account_info(acc_id)}
            return {"status": "error", "msg": "AccountManager not ready"}
        elif cmd == "DOWNLOAD_HISTORY":
            ok, msg = _download_and_save_history(args.get('code'), args.get('start'), args.get('end'))
            return {"status": "ok" if ok else "error", "msg": msg}
        
        elif cmd == "GET_DB_HISTORY":
            # [MOD] Use get_and_cache_history for Auto-Backfill
            df = data_manager.get_and_cache_history(
                args.get('code'), 
                args.get('start'), 
                args.get('end'), 
                int(args.get('freq', 1))
            )
            data = df.reset_index().to_dict('records')
            for r in data: 
                if hasattr(r.get('Date'), 'strftime'): r['Date'] = r['Date'].strftime('%Y-%m-%d %H:%M:%S')
            return {"status": "ok", "data": data}
        
        elif cmd == "SUBSCRIBE":
            if data_manager: data_manager.start_listening(args.get('code'))
            return {"status": "ok"}
        elif cmd == "UNSUBSCRIBE": 
            if data_manager: data_manager.stop_listening()
            return {"status": "ok"}

        elif cmd == "ENGINE_LOGIN":  # 或是 CMD_ENGINE_LOGIN (視常數定義而定)
            # 取得連線模式參數，預設為模擬 (True)
            is_sim = params.get('sim', True)
            info(f"[Engine] 收到 Client 登入指令: {'模擬' if is_sim else '實盤'}")
            
            # 執行我們修正後的登入函式 (內部已包含策略恢復邏輯)
            reply = _run_engine_login(is_sim)
            
            return {
                "status": "SUCCESS" if reply['status'] == 'ok' else "ERROR",
                "msg": reply['msg'],
                "details": reply.get('details', {})
            }
        
        if strategy_executor:
            if cmd == "STR_STATUS": return {"status": "ok", "data": strategy_executor.get_all_status()}
            elif cmd == "STR_START": return {"status": "ok" if strategy_executor.start_strategy(args.get('id'))[0] else "error", "msg": "Done"}
            elif cmd == "STR_STOP": return {"status": "ok" if strategy_executor.stop_strategy(args.get('id'))[0] else "error", "msg": "Done"}
            
            elif cmd == "STR_TOGGLE":
                success, msg = strategy_executor.toggle_strategy(args.get('id'))
                return {"status": "ok" if success else "error", "msg": msg}
                
            elif cmd == "STR_ADD": return {"status": "ok" if strategy_executor.add_strategy(args)[0] else "error", "msg": "Done"}
            elif cmd == "STR_UPDATE": return {"status": "ok" if strategy_executor.update_strategy(args)[0] else "error", "msg": "Done"}
            elif cmd == "STR_DEL": return {"status": "ok" if strategy_executor.delete_strategy(args.get('id'))[0] else "error", "msg": "Done"}
            elif cmd == "STR_GET_LOGS": 
                return {"status": "ok", "data": list(strategy_executor.event_buffer)}
            elif cmd == "DEPLOY_STRATEGY":
                if deploy_manager:
                    res = deploy_manager.handle_deploy(args)
                    
                    if res.get('status') == 'ok' and strategy_executor:
                        args['file_name'] = args.get('strategy_name')
                        strategy_executor.add_strategy(args)
                        
                        # A. 檢查指定的交易帳號適配器是否在線
                        # 關鍵修正：將參數名改為 'account_id' 以符合 metadata 規範
                        adapter, _ = trading_manager._get_adapter_by_account(args.get('account_id')) 
                        broker_status = "ONLINE" if (adapter and getattr(adapter, 'api', None)) else "OFFLINE"

                        # B. 檢查行情數據是否已成功訂閱
                        # 此處呼叫我們在 MarketDataManager 新增的 is_listening 函式
                        is_sub = data_manager.is_listening(args.get('contract_code'))  
                        
                        # C. 附加診斷結果
                        res['diagnostics'] = {
                            "reload": "SUCCESS",
                            "broker_connection": broker_status,
                            "market_data": "SUBSCRIBED" if is_sub else "PENDING",
                            "mode": config.get('environment_profile', {}).get('mode', 'SIMULATION')
                        }
                        
                        # 若為 PRODUCTION 模式，執行存證同步 (連動修正三)
                        if res['diagnostics']['mode'] == 'PRODUCTION':
                            _sync_instance_to_repo(args)
                            
                    return res
 
    except Exception as e:
        error(f"[Engine] CMD Error: {e}")
        return {"status": "error", "msg": str(e)}
        
    return {"status": "error", "msg": f"Unknown CMD: {cmd}"}

def heartbeat_loop():
    global running, server, config, adapters
    while running and server and server.running:
        try:
            # Check components health
            md_ok = data_manager.is_running if data_manager else False
            
            payload = {
                "t": time.time(),
                "dt": datetime.datetime.now().strftime('%H:%M:%S'),
                "status": "RUNNING",
                "health": {
                    "status": HEALTH_OK if md_ok else HEALTH_WARN,
                    "detail": {
                        "md_listening": md_ok,
                        "strategies": len(strategy_executor.strategies) if strategy_executor else 0
                    }
                }
            }
            server.publish("HEARTBEAT", payload)
        except Exception as e:
            error(f"[Engine] Heartbeat Error: {e}")
        time.sleep(1)

def _sync_instance_to_repo(strategy_args):
    """
    [修正]: 增加動態感測與降級邏輯。
    """
    global config
    
    # 1. 優先檢查：Repo 服務現在是否在線上？
    if not is_repo_service_alive():
        warn("[Registry] Service Repo is currently OFFLINE. Skipping instance archival.")
        return

    # 2. 如果在線，執行同步存證
    payload = {
        "cmd": "REQ_REGISTER_INSTANCE", # 配合 V2.6 規範
        "args": {
            "id": strategy_args.get('id'),
            "name": strategy_args.get('name'),
            "timestamp": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "config": strategy_args,
            "env": "PRODUCTION"
        }
    }
    
    # 這裡未來應透過 ZmqClient 調用，目前先標註邏輯路徑
    info(f"[Registry] Repo Service detected ONLINE. Archiving instance {strategy_args.get('id')}...")
    # TODO: zmq_repo_client.call(payload)
    
def main(config_path='config.json', config_overrides=None):
    global server, config, adapters, primary_adapter, data_manager, trading_manager, account_manager, strategy_executor, restart_required, deploy_manager, touch_executor, running
    
    # 1. 優先載入 Config (修正點：需先有設定才能初始化具備流水號的日誌)
    if os.path.exists(config_path):
        config = load_config(config_path)
        # 暫時使用 print，直到 logger 初始化完成
        print(f"[Main] Config loaded from {config_path}") 
    else:
        print(f"[CRITICAL] Config not found: {config_path}")
        return

    # 套用覆蓋設定
    if config_overrides:
        for k, v in config_overrides.items():
            if k in config and isinstance(config[k], dict) and isinstance(v, dict):
                config[k].update(v)
            else:
                config[k] = v

    # 2. ZMQ 初始化 (修正點：先初始化以便日誌能透過 ZMQ 廣播至 UI)
    try:
        server = ZmqServer(config)
    except Exception as e:
        print(f"[CRITICAL] ZMQ Server Init Failed: {e}")
        return

    # 3. 初始化日誌 (修正點：改用 init_logger 並傳入 config 與 server)
    try:
        # init_logger 內部已包含「=== Application Started ===」訊息與流水號判定
        log_file_path = init_logger(config, server)
    except Exception as e:
        print(f"Logging Initialization Failed: {e}")
        return

    init_debug_mode(config)
    
    # 4. 載入 Schema
    _load_schema()

    # 5. Broker Adapters 初始化 (Multi-Broker)
    try:
        adapters = BrokerFactory.get_adapters(config)
        if not adapters:
            error("No adapters loaded! Check 'enabled_adapters' in config.")
        else:
            primary_name = list(adapters.keys())[0]
            primary_adapter = adapters[primary_name]
            info(f"Primary Adapter: {primary_name}")
    except Exception as e:
        error(f"Broker Factory Failed: {e}")
        return

    # 6. 核心組件初始化
    try:
        env_mode = config.get('environment_profile', {}).get('mode', 'SIMULATION')  
        
        # Market Data Manager (修正點：內部現在支援異步補全與去重)
        data_manager = MarketDataManager(primary_adapter, config, server)
        
        # Trading & Account Managers
        trading_manager = TradingManager(adapters, engine_mode=env_mode)
        account_manager = AccountManager(adapters)
        
        # Touch Order Executor (修正點：對接 Schema B 修正後的 1 參數簽章)
        if HAS_TOUCH and primary_adapter:
            if hasattr(primary_adapter, 'api'): 
                touch_executor = TouchOrderExecutor(primary_adapter.api)
                data_manager.register_tick_handler(touch_executor.integration_tick)
                info("TouchOrderExecutor attached.")
        
        # Strategy Executor (修正點：內部支援 CSV 數據快照與流水號日誌)
        strategy_executor = StrategyExecutor(adapters, config, data_manager, server, touch_executor)
        # 註冊策略執行器至行情中心，並使用 lambda 帶入 data_manager ---
        data_manager.register_tick_handler(
            lambda tick: strategy_executor.on_tick_update(tick, data_manager)
        )
        
        # 設定所有 Adapter 的回呼 (Callback)
        for name, adapter in adapters.items():
            adapter.set_callbacks(
                on_tick=data_manager.on_tick,
                on_order_update=strategy_executor.on_order_update
            )
            
        deploy_manager = DeployManager(os.path.join(os.getcwd(), 'plugins'))
        info("All components initialized.")

    except Exception as e:
        error(f"Core Init Failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # 7. 啟動循環與登入
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    
    if config.get('auto_login', False):
        mode_str = str(config.get('last_login_mode', '2'))
        is_sim = (mode_str == '2')
        _run_engine_login(is_sim)

    # 8. 命令監聽 (Blocking)
    try:
        server.start_command_listener(handle_client_command)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        error(f"Runtime Error: {e}")
    finally:
        if server: 
            server.close()
        
        # 修正點：移除不存在的 log_end()
        
        if restart_required:
            info("RESTARTING SYSTEM...")
            # 確保使用目前執行的 Python 直譯器重啟
            os.execv(sys.executable, ['python'] + sys.argv)
        else:
            info("Service stopped.")
            sys.exit(0)
if __name__ == "__main__":
    main()