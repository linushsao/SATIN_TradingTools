# ==============================================================================
# test_deploy_flow.py
#
# 描述: 針對「部署、註冊、手動停止」完整生命週期的整合測試腳本。
#       模擬 StrategiesPlugin 與 MainEngine 之間的 ZMQ 指令往返。
# ==============================================================================

import zmq
import json
import time

# 測試配置
REP_PORT = 5557
TARGET_URL = f"tcp://127.0.0.1:{REP_PORT}"
TEST_ID = "999"

def run_integration_test():
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.setsockopt(zmq.RCVTIMEO, 5000)
    
    print(f"[Test] Connecting to Trading Engine at {TARGET_URL}...")
    socket.connect(TARGET_URL)

    # --- 1. 測試連線 ---
    print("\n[Step 1] Sending PING...")
    socket.send_json({"cmd": "PING", "args": {}})
    resp = socket.recv_json()
    if resp.get('status') != 'ok':
        print("    [FAIL] Engine not responding.")
        return
    print("    [PASS] Connection OK.")

    # --- 2. 部署並自動註冊 ---
    print(f"\n[Step 2] Sending DEPLOY_STRATEGY for ID {TEST_ID}...")
    deploy_payload = {
        "cmd": "DEPLOY_STRATEGY",
        "args": {
            "id": TEST_ID,
            "name": "Stop_Test_Strategy",
            "strategy_name": f"strategy_{TEST_ID}.py",
            "strategy_content": "def calculate(k, p): return {}",
            "core_content": "",
            "contract_code": "TXFR1",
            "account_id": "shioaji:F0000000",
            "frequency": 1,
            "is_active": True
        }
    }
    socket.send_json(deploy_payload)
    deploy_resp = socket.recv_json()
    print(f"    Deployment Response: {deploy_resp}")

    # --- 3. 驗證目前為運行狀態 ---
    print("\n[Step 3] Verifying Initial Running Status...")
    time.sleep(1)
    socket.send_json({"cmd": "STR_STATUS", "args": {}})
    status_resp = socket.recv_json()
    strategies = status_resp.get('data', [])
    test_strat = next((s for s in strategies if str(s.get('id')) == TEST_ID), None)
    
    if test_strat and test_strat.get('running') is True:
        print(f"    [PASS] Strategy {TEST_ID} is now RUNNING.")
    else:
        print(f"    [FAIL] Strategy status incorrect: {test_strat}")
        return

    # --- 4. 測試手動停止指令 (新增測試案例) ---
    print(f"\n[Step 4] Sending STR_STOP for ID {TEST_ID}...")
    # 模擬 StrategiesPlugin._on_stop_strategy 的行為
    stop_payload = {
        "cmd": "STR_STOP",
        "args": {"id": TEST_ID}
    }
    socket.send_json(stop_payload)
    stop_resp = socket.recv_json()
    print(f"    Stop Response: {stop_resp}")

    if stop_resp.get('status') == 'ok':
        print("    [PASS] Stop command acknowledged by server.")
    else:
        print(f"    [FAIL] Stop command rejected: {stop_resp.get('msg')}")
        return

    # --- 5. 最終驗證狀態是否變更為停止 ---
    print("\n[Step 5] Final Status Verification...")
    time.sleep(1)
    socket.send_json({"cmd": "STR_STATUS", "args": {}})
    final_resp = socket.recv_json()
    final_strategies = final_resp.get('data', [])
    final_strat = next((s for s in final_strategies if str(s.get('id')) == TEST_ID), None)

    if final_strat and final_strat.get('running') is False:
        print(f"    [PASS] Strategy {TEST_ID} has successfully STOPPED.")
    else:
        print(f"    [FAIL] Strategy is still running or not found. Status: {final_strat}")

    print("\n=== Full Lifecycle Test Finished ===")

if __name__ == "__main__":
    run_integration_test()