# ==============================================================================
# start_trading.py
#
# Version: V1.8-000 (Config Mode)
# 更新日期: 2025-12-13
# 描述:     [Server A] 交易引擎啟動入口。
#           [修正]: 新增 --setting 參數，支援進入設定模式而不啟動引擎。
# ==============================================================================
import sys
import os
import time
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="SATE Trading Engine Launcher")
    
    parser.add_argument(
        '--config', type=str, default='config.json',
        help='Path to configuration file (default: config.json)'
    )
    parser.add_argument(
        '--security', type=str, choices=['NONE', 'CHECKSUM', 'STRICT'],
        help='Override security level (NONE/CHECKSUM/STRICT)'
    )
    parser.add_argument(
        '--host', type=str,
        help='Override bind IP address'
    )
    parser.add_argument(
        '--mode', type=str, choices=['1', '2'],
        help='Override login mode (1: Production, 2: Simulation)'
    )
    # [NEW] Setting Mode Flag
    parser.add_argument(
        '--setting', action='store_true',
        help='Enter interactive configuration mode (TUI)'
    )

    return parser.parse_args()

def check_environment_mode(config_path, config_overrides):
    """
    啟動前檢查環境設定，並印出醒目提示。
    """
    # [FIX] Delayed import
    from shared.config_manager import load_config
    
    try:
        config = load_config(config_path)
        
        mode = str(config_overrides.get('last_login_mode', config.get('last_login_mode', '2')))
        
        print("\n" + "="*80)
        if mode == '1':
            print("\033[91m  [!]警告：目前設定為【正式環境 (PRODUCTION)】！\033[0m")
            print("\033[91m  將進行真實資金交易，請務必確認您的程式邏輯無誤。\033[0m")
            time.sleep(1) 
        else:
            print("\033[92m  [V]提示：目前設定為【模擬環境 (SIMULATION)】\033[0m")
            print("\033[92m  您可以安全地進行測試。\033[0m")
            
        print("-" * 80)
        print(f"🔧 啟動參數覆蓋模式: Security: {config_overrides.get('security', {}).get('level', 'N/A')}, Mode: {mode}")
        print("="*80 + "\n")

    except Exception as e:
        print(f"[Launcher] Config check warning: {e}")

def main():
    # 1. 解析參數
    args = parse_args()
    
    # 2. 設定路徑
    project_root = os.path.dirname(os.path.abspath(__file__))
    sys.path.append(os.path.join(project_root, 'shared'))
    service_root = os.path.join(project_root, 'service_trading')
    sys.path.append(service_root)
    sys.path.append(os.path.join(service_root, 'core'))
    sys.path.append(os.path.join(service_root, 'libs'))
    os.chdir(service_root)

    # 3. 構造覆蓋字典
    config_overrides = {}
    if args.security:
        config_overrides['security'] = {'level': args.security}
    if args.host:
        config_overrides['zmq'] = {'bind_ip': args.host}
    if args.mode:
        config_overrides['last_login_mode'] = args.mode

    # [NEW] Branch to Setting Mode
    if args.setting:
        print(f"[Launcher] Entering Configuration Mode...")
        try:
            from core.setting_manager import SettingManager
            # SettingManager will handle config loading/migration internally
            manager = SettingManager(args.config)
            manager.run()
            print("[Launcher] Configuration session ended.")
            sys.exit(0)
        except ImportError as e:
            print(f"[Error] Could not import SettingManager: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"[Error] Setting Mode crashed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    # 4. 檢查環境 (此時 sys.path 已設定，可以安全引用 shared)
    check_environment_mode(args.config, config_overrides)
    
    print(f"[Launcher] Starting Trading Engine in {os.getcwd()}...")
    
    # 5. 啟動主程式
    try:
        import main_engine 
        main_engine.main(config_path=args.config, config_overrides=config_overrides)
    except Exception as e:
        print(f"[Launcher] Runtime Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()