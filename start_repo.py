# ==============================================================================
# start_repo.py
#
# Version: V1.1-002 (Fix Import)
# 更新日期: 2025-12-08
# 描述:     [Service B] 策略資料庫服務啟動入口。
#           [修正]: 確保 sys.path 設定優先於模組引用。
# ==============================================================================
import sys
import os
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="SATE Repo Service Launcher")
    
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

    return parser.parse_args()

def main():
    # 1. 解析參數
    args = parse_args() 
    
    # 2. 設置路徑
    project_root = os.path.dirname(os.path.abspath(__file__))
    sys.path.append(os.path.join(project_root, 'shared'))
    service_root = os.path.join(project_root, 'service_repo')
    sys.path.append(service_root)
    sys.path.append(os.path.join(service_root, 'core'))
    os.chdir(service_root)
    
    # 3. 構造覆蓋字典
    config_overrides = {}
    if args.security:
        config_overrides['security'] = {'level': args.security}
    if args.host:
        config_overrides['zmq_repo'] = {'bind_ip': args.host}
    
    print(f"[Launcher] Starting Repo Service in {os.getcwd()}...")
    
    try:
        import repo_service
        # 4. 傳遞配置給服務主體
        repo_service.main(config_path=args.config, config_overrides=config_overrides)
    except Exception as e:
        print(f"[Launcher] Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()