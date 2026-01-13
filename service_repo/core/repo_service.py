# ==============================================================================
# service_repo/core/repo_service.py
#
# Version: V2.6-002 (Startup Check)
# 更新日期: 2025-12-09
# 描述:     策略資料庫服務
#           [修正]: 啟動時增加 Config 讀取狀態檢查日誌。
# ==============================================================================

import sys
import zmq
import base64
import os
import threading
import time
import datetime

from shared.config_manager import load_config
from shared.logging_tool import init_logger, info, error, log_end
from shared.zmq_manager import ZmqServer
from shared.constants import CMD_GET_CAPABILITIES
from shared.protocol_defs import HEALTH_OK # [NEW]

from file_manager import FileManager

file_manager = None
server = None
current_config = None 
running = True 

def handle_command(message: dict):
    global file_manager, current_config
    cmd = message.get('cmd')
    args = message.get('args', {})
    
    sec_config = current_config.get('security', {})
    sec_level = sec_config.get('level', 'NONE')

    info(f"[Repo] CMD: {cmd}, Sec Level: {sec_level}")
    
    try:
        if cmd == "PING":
            payload = {"status": "ok", "msg": "PONG (Repo)", "security": {"level": sec_level}}
            return payload
        # [新增] 處理來自 Trading Service 的實例存證請求
        elif cmd == "REQ_REGISTER_INSTANCE":
            # 建立實例紀錄存放目錄
            instance_dir = os.path.join(current_config.get('storage_dir'), "instances")
            if not os.path.exists(instance_dir): os.makedirs(instance_dir)
            
            instance_id = args.get('id')
            file_path = os.path.join(instance_dir, f"{instance_id}_registry.json")
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(args, f, indent=4, ensure_ascii=False)
            
            info(f"[Repo] Instance {instance_id} registered successfully.")
            return {"status": "ok", "msg": "Instance archived"}
        # [Modified] Phase 5 Handshake
        elif cmd == CMD_GET_CAPABILITIES:
             return {
                 "status": "ok",
                 "service_id": current_config.get('service_name', 'RepoService'),
                 "version": "2.6.0",
                 "capabilities": current_config.get('capabilities', []),
                 "environment_profile": current_config.get('environment_profile', {})
             }
            
        elif cmd == "REQ_CREATE_PROJECT":
            ok, msg = file_manager.create_project(args.get('name'))
            return {"status": "ok" if ok else "error", "msg": msg}
            
        elif cmd == "REQ_GET_PROJECT_LIST":
            data = file_manager.get_project_list()
            return {"status": "ok", "data": data}

        elif cmd == "REQ_UPDATE_PROJECT":
            name = args.get('name')
            b64_data = args.get('payload_b64')
            checksum = args.get('checksum')
            signature = args.get('signature')
            developer_id = args.get('developer_id')
            
            if not name or not b64_data: return {"status": "error", "msg": "Missing data"}
            zip_bytes = base64.b64decode(b64_data)
            
            if not file_manager.verify_update_payload(sec_level, developer_id, zip_bytes, checksum, signature):
                return {"status": "error", "msg": f"[SECURITY] Code upload verification failed. Required level: {sec_level}"}

            ok, msg = file_manager.update_project(name, zip_bytes)
            return {"status": "ok" if ok else "error", "msg": msg}

        elif cmd == "REQ_DOWNLOAD_PROJECT":
            name = args.get('name')
            if not name: return {"status": "error", "msg": "Missing name"}
            try:
                server_key_path = sec_config.get('server_private_key_path')
                payload_data = file_manager.pack_project_to_bytes(name, sec_level, server_key_path)
                b64_data = base64.b64encode(payload_data['zip_bytes']).decode('utf-8')
                return {
                    "status": "ok", 
                    "payload_b64": b64_data,
                    "checksum": payload_data.get('checksum'),
                    "signature": payload_data.get('signature')
                }
            except Exception as e: return {"status": "error", "msg": str(e)}

        elif cmd == "REQ_GET_INDICATOR_LIST":
            data = file_manager.list_indicators()
            return {"status": "ok", "data": data}

        elif cmd == "REQ_DOWNLOAD_FILE":
            try:
                content = file_manager.get_file_content(args.get('path'))
                return {"status": "ok", "content": content}
            except Exception as e: return {"status": "error", "msg": str(e)}

        elif cmd == "REQ_DELETE_PROJECT":
            name = args.get('name')
            if not name: return {"status": "error", "msg": "Missing name"}
            ok, msg = file_manager.delete_project(name)
            return {"status": "ok" if ok else "error", "msg": msg}

        else:
            return {"status": "error", "msg": f"Unknown CMD: {cmd}"}
            
    except Exception as e:
        error(f"[Repo] Handle Error: {e}")
        return {"status": "error", "msg": str(e)}

def heartbeat_loop():
    """[NEW] Phase 5: Repo Heartbeat for System Monitor"""
    global running, server, current_config
    while running and server and server.running:
        try:
            sec_level = current_config.get('security', {}).get('level', 'NONE')
            projects_count = len(file_manager.get_project_list()) if file_manager else 0
            
            payload = {
                "topic": "HEARTBEAT",
                "t": time.time(), 
                "dt": datetime.datetime.now().strftime('%H:%M:%S'), 
                "status": "RUNNING", 
                "security": {"level": sec_level},
                "health": {
                    "status": HEALTH_OK,
                    "detail": {
                        "projects": projects_count,
                        "storage_path": current_config.get('storage_dir')
                    }
                }
            }
            server.publish("HEARTBEAT", payload)
        except Exception as e: error(f"[Repo] HB Error: {e}")
        time.sleep(1)

# service_repo/core/repo_service.py

# service_repo/core/repo_service.py

def main(config_path='config.json', config_overrides=None):
    """
    Repo Service 主進入點
    [修正]: 
      1. 調整啟動鏈順序：先讀取設定 -> 初始化日誌 -> 初始化 ZMQ -> 啟動 FileManager。
      2. 修正 FileManager 初始化時缺少 config_root_dir 參數的問題。
    """
    global server, current_config, running, file_manager
    
    # 1. 優先載入 Config (確保後續組件能讀取到正確的路徑設定)
    if os.path.exists(config_path):
        current_config = load_config(config_path)
        print(f"[Repo] Config loaded from {config_path}")
    else:
        # 容錯處理：若無設定檔則建立基本字典
        current_config = {
            'service_name': 'StrategyRepoService',
            'log_dir': 'logs',
            'storage_dir': 'storage'
        }
        print(f"[Repo] Warning: {config_path} not found. Using internal defaults.")

    # 套用參數覆蓋 (Overrides)
    if config_overrides:
        for k, v in config_overrides.items():
            if isinstance(v, dict) and k in current_config:
                current_config[k].update(v)
            else:
                current_config[k] = v

    # 2. 初始化日誌 (直接傳入載入後的 config 字典)
    try:
        from shared.logging_tool import init_logger
        init_logger(current_config)
        info("=== Repo Service Starting (V2.6-Fixed) ===")
    except Exception as e:
        print(f"Logging Initialization Failed: {e}")
        return

    # 3. 初始化 ZMQ Server (用於與 Client 端通訊)
    try:
        server = ZmqServer(current_config)
    except Exception as e:
        error(f"ZMQ Server Init Failed: {e}")
        return

    # 4. 初始化檔案管理員 [關鍵錯誤修正處]
    try:
        from file_manager import FileManager
        storage_root = current_config.get('storage_dir', 'storage')
        
        # [修正點]: 補齊缺失的 config_root_dir 參數。
        # 在 Repo Service 中，通常設定路徑與儲存路徑一致，或指向當前工作目錄。
        # 這裡將 storage_root 同時作為資料儲存與註冊表(Registry)的根目錄。
        file_manager = FileManager(storage_root, config_root_dir=storage_root)
        
        info(f"FileManager initialized. Storage: {os.path.abspath(storage_root)}")
    except TypeError as te:
        error(f"FileManager Init Failed (Parameter Mismatch): {te}")
        return
    except Exception as e:
        error(f"FileManager Init Failed: {e}")
        return

    # 5. 啟動背景執行緒 (心跳等)
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    info("Repo Service Ready and listening for commands.")

    # 6. 進入命令監聽循環 (由 ZMQ Server 驅動)
    try:
        server.start_command_listener(handle_command)
    except KeyboardInterrupt:
        info("Repo Service received KeyboardInterrupt.")
    finally:
        if server:
            server.close()
        log_end()
        info("Repo Service Stopped.")
        sys.exit(0)

if __name__ == "__main__":
    main()