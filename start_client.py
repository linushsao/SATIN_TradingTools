# ==============================================================================
# start_client.py
#
# Version: V1.0-002 (Disable Cache)
# 更新日期: 2025-12-08
# 描述:     [Client] GUI 啟動入口。
#           [修正]: 禁用 .pyc 生成 (dont_write_bytecode) 以確保讀取最新代碼。
#           [新增]: 印出核心模組載入路徑以供除錯。
# ==============================================================================
import sys
import os

# [IMPORTANT] 在開發階段強制禁用 bytecode，避免讀取到舊的 .pyc 檔案
sys.dont_write_bytecode = True

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    sys.path.append(os.path.join(project_root, 'shared'))
    client_root = os.path.join(project_root, 'client_gui')
    sys.path.append(client_root)
    
    # Kernel and Plugins path
    sys.path.append(os.path.join(client_root, 'kernel'))
    sys.path.append(os.path.join(client_root, 'plugins'))
    
    os.chdir(client_root)
    print(f"[Launcher] Starting GUI Client in {os.getcwd()}...")
    
    try:
        # Delayed import after sys.path setup
        from kernel import main as app_main
        
        # [DEBUG] Verify which file is actually being loaded
        try:
            import core.main_gui
            print(f"[DEBUG] Actual MainGUI File: {core.main_gui.__file__}")
        except ImportError:
            print("[DEBUG] Could not pre-verify MainGUI path (ImportError)")

        app_main.main() 
    except Exception as e:
        print(f"[Launcher] Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()