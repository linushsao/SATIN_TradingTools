# ==============================================================================
# service_trading/core/setting_manager.py
#
# Version: V1.1-001 (Timezone Setting)
# 更新日期: 2025-12-16
# 描述:     設定模式管理器 (TUI)。
#           [新增]: 支援系統時區設定 (Auto/Manual)。
# ==============================================================================

import os
import json
import glob
import sys
import datetime

# 嘗試引用 shared (假設 sys.path 已由啟動腳本設定)
try:
    from shared.config_manager import load_config, save_config, CONFIG_FILE
except ImportError:
    # Fallback for standalone testing
    print("[SettingManager] Warning: Shared modules not found. Using local fallback.")
    CONFIG_FILE = 'config.json'
    def load_config(path):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f: return json.load(f)
        return {}
    def save_config(data, path):
        with open(path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

class SettingManager:
    def __init__(self, config_path=CONFIG_FILE):
        self.config_path = config_path
        self.config = {}
        # 定位 libs/adapters 目錄
        self.adapters_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'libs', 'adapters'))
        
        self._load_and_migrate_config()

    def _load_and_migrate_config(self):
        """讀取設定檔並執行必要的格式遷移"""
        print(f"[Setting] Loading config from: {self.config_path}")
        self.config = load_config(self.config_path) or {}
        
        # --- Migration: Active Adapter (Str) -> Enabled Adapters (List) ---
        is_dirty = False
        
        # 1. 確保 enabled_adapters 存在
        if 'enabled_adapters' not in self.config:
            print("[Migration] 'enabled_adapters' list not found. Creating...")
            active = self.config.get('active_adapter')
            self.config['enabled_adapters'] = [active] if active else []
            is_dirty = True
            
        # 2. 確保 adapters 設定區塊存在
        if 'adapters' not in self.config:
            self.config['adapters'] = {}
            is_dirty = True

        # 3. 確保 system_settings 存在 [NEW]
        if 'system_settings' not in self.config:
            self.config['system_settings'] = {
                'timezone': {'mode': 'MANUAL', 'offset': 8} # Default Taiwan
            }
            is_dirty = True

        if is_dirty:
            print("[Migration] Config structure updated. Saving changes...")
            self._save_config()

    def _save_config(self):
        try:
            save_config(self.config, self.config_path)
            print("[Setting] Configuration saved.")
        except Exception as e:
            print(f"[Setting] Error saving config: {e}")

    def _scan_adapters(self):
        """掃描實體檔案以識別可用的 Adapter 模組"""
        if not os.path.exists(self.adapters_dir):
            print(f"[Setting] Warning: Adapters directory not found: {self.adapters_dir}")
            return []
            
        files = glob.glob(os.path.join(self.adapters_dir, "*_adapter.py"))
        adapters = []
        for f in files:
            filename = os.path.basename(f)
            # 排除 __init__.py 或其他非 adapter 命名
            if filename == "__init__.py": continue
            
            # 解析名稱: shioaji_adapter.py -> shioaji
            name = filename.replace('_adapter.py', '')
            adapters.append(name)
        return sorted(adapters)

    def run(self):
        """進入互動式主選單"""
        while True:
            self._clear_screen()
            print("========================================")
            print("   SATIN Service Trading - Config Mode  ")
            print("========================================")
            print(f"Config File: {self.config_path}")
            print("----------------------------------------")
            print(" 1. 卷商設定 (Broker Settings)")
            print(" 2. 顯示完整設定 (View Raw Config)")
            print(" 3. 系統時區設定 (System Timezone)")
            print("----------------------------------------")
            print(" Q. 儲存並離開 (Save & Exit)")
            print(" X. 放棄並離開 (Discard & Exit)")
            print("========================================")
            
            choice = input("請輸入指令 [1/2/3/Q/X]: ").strip().upper()
            
            if choice == '1':
                self._menu_brokers()
            elif choice == '2':
                print(json.dumps(self.config, indent=4, ensure_ascii=False))
                input("\nPress Enter to continue...")
            elif choice == '3':
                self._menu_timezone()
            elif choice == 'Q':
                self._save_config()
                print("Exiting...")
                break
            elif choice == 'X':
                print("Exiting without saving (unless migrated)...")
                break

    def _menu_brokers(self):
        """卷商設定子選單"""
        while True:
            self._clear_screen()
            available = self._scan_adapters()
            enabled_list = self.config.get('enabled_adapters', [])
            
            print("\n--- 卷商模組設定 (Broker Settings) ---")
            print("說明: 輸入編號以 切換 (Toggle) 啟用狀態。\n")
            
            if not available:
                print("  (No adapters found in libs/adapters/)")
            
            for idx, name in enumerate(available):
                status = "[v] ENABLED " if name in enabled_list else "[ ] Disabled"
                # 簡單的高亮標示
                if name in enabled_list:
                    status = f"\033[92m{status}\033[0m" # Green
                else:
                    status = f"\033[90m{status}\033[0m" # Grey
                    
                print(f" {idx+1}. {status}  - {name}")
                
            print("\n 0. 返回上一層 (Back)")
            print("----------------------------------------")
            
            sel = input("請輸入編號 [0-{}]: ".format(len(available))).strip()
            
            if sel == '0':
                break
            
            try:
                idx = int(sel) - 1
                if 0 <= idx < len(available):
                    target = available[idx]
                    if target in enabled_list:
                        enabled_list.remove(target)
                    else:
                        enabled_list.append(target)
                        if len(enabled_list) == 1:
                            self.config['active_adapter'] = target
                    
                    self.config['enabled_adapters'] = enabled_list
                    if enabled_list:
                        self.config['active_adapter'] = enabled_list[0]
                    else:
                        self.config['active_adapter'] = ""
                        
                else:
                    pass # Invalid number
            except ValueError:
                pass

    def _menu_timezone(self):
        """[NEW] 時區設定子選單"""
        while True:
            self._clear_screen()
            
            tz_conf = self.config.get('system_settings', {}).get('timezone', {'mode': 'MANUAL', 'offset': 8})
            current_mode = tz_conf.get('mode', 'MANUAL')
            current_offset = tz_conf.get('offset', 8)
            
            # Auto Detect Preview
            try:
                local_now = datetime.datetime.now().astimezone()
                auto_offset = local_now.utcoffset().total_seconds() / 3600
                auto_preview = f"(Detected: {int(auto_offset)})"
            except:
                auto_preview = "(Detected: Unknown)"

            print("\n--- 系統時區設定 (System Timezone) ---")
            print(f"Current Status: [{current_mode}] Offset: UTC+{current_offset}")
            print("----------------------------------------")
            print(f" A. 自動偵測 (Auto Detect) {auto_preview}")
            print(f" M. 手動設定 (Manual Set)  [Current: {current_offset}]")
            print("----------------------------------------")
            print(" 0. 返回上一層 (Back)")
            print("========================================")
            
            sel = input("請輸入指令 [A/M/0]: ").strip().upper()
            
            if sel == '0':
                break
            
            if sel == 'A':
                self.config.setdefault('system_settings', {})['timezone'] = {
                    'mode': 'AUTO',
                    'offset': int(auto_offset) # Save snapshot just in case
                }
                print("Setting changed to AUTO.")
                
            elif sel == 'M':
                try:
                    val = input("請輸入 UTC 偏移小時數 (例如 8): ").strip()
                    offset_val = int(val)
                    self.config.setdefault('system_settings', {})['timezone'] = {
                        'mode': 'MANUAL',
                        'offset': offset_val
                    }
                    print("Setting changed to MANUAL.")
                except ValueError:
                    print("Invalid input. Must be integer.")
                    input("Press Enter...")

    def _clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')

if __name__ == "__main__":
    # Standalone Test
    mgr = SettingManager()
    mgr.run()