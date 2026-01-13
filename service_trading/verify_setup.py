# ==============================================================================
# service_trading/verify_setup.py
#
# Version: V1.0-009 (CLI Arguments)
# 描述:     多券商架構驗證工具。
#           [修正]: 
#             1. 支援命令列參數 --test-contract <CODE> 指定測試標的。
#             2. 若未指定，則維持自動偵測最近月期貨合約的邏輯。
# ==============================================================================

import sys
import os
import time
import argparse  # [NEW] 用於解析命令列參數

# 全域變數：用於儲存測試結果報告
TEST_REPORT = {}

# 取得腳本所在目錄 (service_trading)
current_dir = os.path.dirname(os.path.abspath(__file__))

# 強制切換工作目錄
os.chdir(current_dir)
print(f"[System] Working Directory set to: {os.getcwd()}")

# 設定搜尋路徑
sys.path.append(os.path.join(current_dir, 'core'))
sys.path.append(os.path.join(current_dir, 'libs'))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
if project_root not in sys.path: sys.path.append(project_root)
shared_dir = os.path.join(project_root, 'shared')
if shared_dir not in sys.path: sys.path.append(shared_dir)

# Imports
try:
    from shared.config_manager import load_config
    from core.broker_factory import BrokerFactory
    from core.account_manager import AccountManager
    from core.trading_manager import TradingManager
except ImportError as e:
    print(f"[System] Import Error: {e}")
    sys.exit(1)

# Mock Adapter
class MockAdapter:
    def __init__(self, name): self.name = name
    def initialize(self, config): pass
    def connect(self, **kwargs): return True
    def list_available_accounts(self):
        class Acc: pass
        a = Acc(); a.account_id = "1234567"; a.is_signed=True; a.account_type="F"; a.login_id="MockUser"
        return [a]
    def place_order(self, order): return "ORD-MOCK-999"
    def cancel_order(self, order_id): return True
    def get_positions(self, type): return []
    def get_account_data(self, type): return None
    def set_callbacks(self, t, o): pass
    def get_contracts(self): return [{"code": "TXF202512", "name": "Mock TXF"}]

def log_step(broker_name, step_name, success, message=""):
    """紀錄並印出單一步驟的結果"""
    status_str = "[PASS]" if success else "[FAIL] <<< 錯誤"
    if broker_name not in TEST_REPORT: TEST_REPORT[broker_name] = []
    TEST_REPORT[broker_name].append({"step": step_name, "success": success, "msg": message})
    if success:
        print(f"    -> {status_str} {step_name}: {message}")
    else:
        print(f"    -> {status_str} {step_name}")
        print(f"       原因: {message}")

def get_valid_contract_code(adapter, default="TXF202512"):
    """
    嘗試從 Adapter 獲取一個有效的期貨合約代碼。
    """
    try:
        contracts = adapter.get_contracts()
        if contracts and len(contracts) > 0:
            # 優先尋找 TXF 開頭的合約
            for c in contracts:
                if c['code'].startswith("TXF") and len(c['code']) > 3:
                    return c['code']
            return contracts[0]['code']
    except:
        pass
    return default

def test_single_broker(name, adapter, manual_contract=None):
    """
    針對單一券商執行完整生命週期測試
    :param manual_contract: 若有指定，則強制使用該合約代碼
    """
    print(f"\n{'='*25} 開始測試券商: [{name}] {'='*25}")
    
    # 1. 連線測試
    print(f"[1] 連線中 (Connecting)...")
    try:
        if adapter.connect(simulation=True):
            log_step(name, "連線 (Connect)", True, "連線成功")
        else:
            log_step(name, "連線 (Connect)", False, "回傳 False (請查看上方 Log 詳細錯誤)")
            print(f"{'='*70}")
            return
    except Exception as e:
        log_step(name, "連線 (Connect)", False, f"例外錯誤: {e}")
        print(f"{'='*70}")
        return

    time.sleep(1) # 等待初始化

    # 2. 帳號查詢測試
    print(f"[2] 查詢帳號 (Fetching Accounts)...")
    test_account_id = None
    try:
        acc_mgr = AccountManager({name: adapter})
        accounts = acc_mgr.get_all_accounts()
        if accounts:
            acc_info = f"找到 {len(accounts)} 個帳號 ({accounts[0]['account_id']})"
            log_step(name, "帳號查詢 (Get Accounts)", True, acc_info)
            test_account_id = accounts[0]['account_id']
        else:
            log_step(name, "帳號查詢 (Get Accounts)", False, "未回傳任何帳號")
    except Exception as e:
        log_step(name, "帳號查詢 (Get Accounts)", False, str(e))

    # 3. 下單測試
    print(f"[3] 下單測試 (Testing Order)...")
    if test_account_id:
        try:
            tm = TradingManager({name: adapter})
            
            # [KEY LOGIC] 決定下單合約
            if manual_contract:
                target_code = manual_contract
                source_msg = "使用者指定"
            else:
                target_code = get_valid_contract_code(adapter, default="TXF202512")
                source_msg = "自動偵測"
            
            print(f"    ({source_msg}合約: {target_code}, 帳號: {test_account_id})")
            
            order_id = tm.place_order(
                contract_code=target_code, 
                order_action="Buy", 
                price=20000, 
                quantity=1, 
                account_id=test_account_id
            )
            
            if order_id:
                log_step(name, "下單 (Place Order)", True, f"Code: {target_code}, ID: {order_id}")
                print(f"[4] 刪單測試 (Canceling)...")
                try:
                    tm.cancel_order(order_id)
                    log_step(name, "刪單 (Cancel Order)", True, "請求已發送")
                except Exception as e:
                    log_step(name, "刪單 (Cancel Order)", False, str(e))
            else:
                log_step(name, "下單 (Place Order)", False, f"未回傳 Order ID (合約 {target_code} 可能無效或憑證問題)")
        except Exception as e:
            log_step(name, "下單 (Place Order)", False, f"例外錯誤: {e}")
    else:
        log_step(name, "下單 (Place Order)", False, "跳過 (因無可用帳號)")

    print(f"{'='*70}\n")

def print_summary():
    """印出最終總結報告"""
    print("\n\n")
    print("#" * 70)
    print("###              測試總結報告 (FINAL REPORT)             ###")
    print("#" * 70)
    all_pass = True
    for broker, steps in TEST_REPORT.items():
        print(f"\n券商: [{broker}]")
        print("-" * 50)
        for s in steps:
            status = "[PASS]" if s['success'] else "[FAIL]"
            msg = s['msg']
            if not s['success']:
                all_pass = False
            print(f"  {status} {s['step']:<25} | {msg}")
    return all_pass

def print_fix_suggestions():
    """產生待辦事項"""
    print("\n")
    print("############################################################")
    print("###           錯誤修復待辦清單 (FIX TO-DO LIST)          ###")
    print("############################################################")
    has_issues = False
    for broker, steps in TEST_REPORT.items():
        failures = [s for s in steps if not s['success']]
        if not failures: continue
        has_issues = True
        print(f"\n[{broker}] 發現錯誤，請依序檢查以下項目：")
        
        connect_fail = any(f['step'] == "連線 (Connect)" for f in failures)
        if connect_fail:
            if broker == 'shioaji':
                print("  [ ] 1. 檢查 .config/shioaji/Sinopac.pfx 是否存在。")
                print("  [ ] 2. 確認是否為維護時段 (Error: Sign data is timeout)。")
            elif broker == 'fubon':
                print("  [ ] 1. 檢查憑證 (.pfx) 是否過期 (Error: Cert Expired)。")
                print("  [ ] 2. 確認 .config/fubon/ 下的密碼檔內容無誤。")

        order_fail = any(f['step'] == "下單 (Place Order)" for f in failures)
        if order_fail:
            print("  [ ] 1. 檢查該帳號是否有交易權限。")
            print("  [ ] 2. 若為 'Contract not found'，請確認 Adapter 合約下載是否完成。")
            print("  [ ] 3. 嘗試使用 --test-contract 指定其他有效合約。")

    if not has_issues:
        print("\n  (無) 系統運作正常，隨時可以開始交易！")
    print("\n" + "#" * 60)

def run_verification():
    # [NEW] 解析參數
    parser = argparse.ArgumentParser(description='SATIN Multi-Broker Architecture Verification Tool')
    parser.add_argument('--test-contract', type=str, help='指定要測試下單的合約代碼 (例如: MXF202512)', default=None)
    args = parser.parse_args()

    print(f"=== SATIN 多券商架構 獨立驗證工具 (V1.0-009) ===")
    if args.test_contract:
        print(f"[設定] 強制測試合約: {args.test_contract}")
    else:
        print(f"[設定] 測試合約: 自動偵測")
    print("\n")

    config_path = 'config.json'
    if not os.path.exists(config_path):
        print(f"[Error] 找不到設定檔: {os.path.abspath(config_path)}")
        return
    config = load_config(config_path)
    try:
        adapters = BrokerFactory.get_adapters(config)
    except Exception as e:
        print(f"[Error] BrokerFactory 載入失敗: {e}")
        return

    if not adapters:
        adapters = {"mock_shioaji": MockAdapter("MockShioaji")}

    for name, adapter in adapters.items():
        # [KEY] 傳入參數
        test_single_broker(name, adapter, manual_contract=args.test_contract)

    if not print_summary():
        print_fix_suggestions()

if __name__ == "__main__":
    run_verification()