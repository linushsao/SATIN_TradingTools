# ==============================================================================
# service_repo/core/main_repo.py
#
# Version: V1.1-001 (Command Routing Fix)
# 更新日期: 2025-12-09
# 描述:     Repo 服務入口。
#           [修正]: 將 Repo 相關指令正確轉發給 RepoEngine。
# ==============================================================================

import sys
import time
import threading
import datetime
import os
import json

# Shared Modules
from shared.zmq_manager import ZmqServer
from shared.config_manager import load_config
from shared.logging_tool import init_logging, info, error, log_end, init_debug_mode
from shared.constants import (
    CMD_GET_CAPABILITIES,
    CMD_UPDATE_PROJECT,
    CMD_DOWNLOAD_PROJECT,
    CMD_GET_PROJECT_LIST,
    CMD_DELETE_PROJECT_REPO
)
from shared.protocol_defs import HEALTH_OK

# Core Modules
from repo_engine import RepoEngine

# Globals
server = None
config = None
repo_engine = None
running = True

def handle_client_command(message: dict):
    global repo_engine, server, config
    cmd = message.get('cmd')
    args = message.get('args', {})
    
    # Log less for high-frequency polls if needed, but log all for now
    info(f"[Repo] CMD: {cmd}")
    
    try:
        # --- System Commands ---
        if cmd == "PING":
            return {
                "status": "ok", 
                "msg": "PONG", 
                "time": str(datetime.datetime.now())
            }

        elif cmd == CMD_GET_CAPABILITIES:
            return {
                "status": "ok",
                "service_id": config.get('service_name', 'RepoService'),
                "version": "1.1.0",
                "capabilities": config.get('capabilities', []),
                "supported_products": [],
                "environment_profile": config.get('environment_profile', {})
            }

        elif cmd == "SHUTDOWN":
            server.running = False
            global running
            running = False
            return {"status": "ok", "msg": "Bye"}

        # --- Repo Business Logic (Forward to Engine) ---
        elif cmd in [CMD_UPDATE_PROJECT, CMD_GET_PROJECT_LIST, CMD_DOWNLOAD_PROJECT, CMD_DELETE_PROJECT_REPO]:
            if repo_engine:
                return repo_engine.handle_command(cmd, args)
            else:
                return {"status": "error", "msg": "Repo Engine not initialized"}

    except Exception as e:
        error(f"[Repo] CMD Error: {e}")
        return {"status": "error", "msg": str(e)}

    return {"status": "error", "msg": f"Unknown CMD: {cmd}"}

def heartbeat_loop():
    global running, server
    while running and server and server.running:
        try:
            payload = {
                "t": time.time(),
                "dt": datetime.datetime.now().strftime('%H:%M:%S'),
                "status": "RUNNING",
                "health": {"status": HEALTH_OK, "detail": {}}
            }
            server.publish("HEARTBEAT", payload)
        except: pass
        time.sleep(1)

def main(config_path='config.json'):
    global server, config, repo_engine, running
    
    init_logging(config_data=None, log_dir='logs')
    info("=== Repo Service Starting (V1.1 - Routing Fix) ===")
    
    config = load_config(config_path)
    if not config: error("Config not found."); return

    init_debug_mode(config)
    
    try:
        server = ZmqServer(config)
    except Exception as e:
        error(f"ZMQ Init Failed: {e}"); return

    # Init Core Engine
    try:
        repo_engine = RepoEngine()
        info("Repo Engine Initialized.")
    except Exception as e:
        error(f"Repo Engine Failed: {e}"); return

    threading.Thread(target=heartbeat_loop, daemon=True).start()
    info("Repo Service Ready.")
    
    try:
        server.start_command_listener(handle_client_command)
    except KeyboardInterrupt:
        pass
    finally:
        if server: server.close()
        log_end()
        sys.exit(0)

if __name__ == "__main__":
    main()