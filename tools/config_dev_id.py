# =============================================================================
# tools/config_dev_id.py
#
# 描述:     開發者身分配置工具 (Client Side)。
#           產生 developer_keys.json 供 GUI Client 讀取。
# 用法:     python tools/config_dev_id.py --id <DevID> --key-path <PathToPrivatePEM>
# =============================================================================

import sys
import os
import json
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="Configure Developer Identity for SATIN Client")
    parser.add_argument('--id', required=True, help="Unique Developer ID (e.g., Dev_Allen)")
    parser.add_argument('--key-path', required=True, help="Path to your private key (.pem)")
    parser.add_argument('--output', default=None, help="Custom output path for developer_keys.json")
    return parser.parse_args()

def main():
    args = parse_args()
    
    # 1. 驗證私鑰是否存在
    key_path = os.path.abspath(args.key_path)
    if not os.path.exists(key_path):
        print(f"[Error] Private key not found at: {key_path}")
        sys.exit(1)
        
    # 2. 決定輸出路徑
    # 預設路徑邏輯：嘗試寫入 client_gui/AppData/sate.core.strategies/
    # 若目錄不存在，則寫入當前目錄
    if args.output:
        target_path = os.path.abspath(args.output)
    else:
        # 推測預設 AppData 路徑 (相對於專案根目錄)
        # 假設結構: SATE_Project/client_gui/AppData/sate.core.strategies/
        # 注意: 這裡的路徑結構需配合 GUI 的 Context.get_app_data_dir 邏輯
        # 簡單起見，我們寫入 client_gui/plugins/pages/02_strategies/ 以便測試，或建議使用者指定
        
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # 嘗試標準 AppData 路徑 (參考 context.py: ../AppData)
        # 但這取決於 GUI 執行時的工作目錄。
        # 為了保險，我們產生到 tools/output/ 並提示使用者移動，
        # 或者嘗試寫入 client_gui/sate.core.strategies/ (若存在)
        
        # 策略 1: 寫入當前目錄，讓使用者自行移動 (最安全)
        target_path = "developer_keys.json"
        
        # 策略 2: 嘗試智慧偵測
        possible_dir = os.path.join(project_root, "AppData", "sate.core.strategies")
        if os.path.exists(possible_dir):
            target_path = os.path.join(possible_dir, "developer_keys.json")

    # 3. 產生設定內容
    config_data = {
        "developer_id": args.id,
        "private_key_path": key_path,
        "updated_at": str(os.path.getmtime(key_path))
    }
    
    # 4. 寫入檔案
    try:
        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4)
            
        print(f"✅ Identity configured for '{args.id}'")
        print(f"📂 Configuration saved to: {os.path.abspath(target_path)}")
        
        if not args.output and "AppData" not in target_path:
            print("\n⚠️  NOTE: If you are using the default GUI setup, please move this file to:")
            print("   SATE_Project/AppData/sate.core.strategies/developer_keys.json")
            
    except Exception as e:
        print(f"[Error] Failed to save config: {e}")

if __name__ == "__main__":
    main()