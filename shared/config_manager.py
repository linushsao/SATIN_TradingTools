# ==============================================================================
# shared/config_manager.py
#
# Version: V0.1-010 (Remove JSON Identity)
# 更新日期: 2025-12-10
# 描述:     應用程式設定管理類別。
#           [修正]: 移除 identity_manager 的 JSON 結構，資料已遷移至 SQLite。
# ==============================================================================

import sys
import time
import os
import json
import datetime
from shared.logging_tool import debug, info, warn, error, set_debug_mode 
from shared.protocol_defs import ROLE_DEVELOPER

CONFIG_FILE = 'config.json'

def clear_screen():
    debug(f"[ENTER] {sys._getframe(0).f_code.co_name}", print_to_console=False)
    os.system('cls' if os.name == 'nt' else 'clear')

def _log_input(prompt: str) -> str:
    debug(f"[ENTER] {sys._getframe(0).f_code.co_name}", print_to_console=False) 
    user_input = input(prompt)
    return user_input

def save_config(config_data, file_path=CONFIG_FILE):
    debug(f"[ENTER] {sys._getframe(0).f_code.co_name}", print_to_console=False)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            config_to_save = config_data.copy()
            config_to_save.pop('api_key', None)
            config_to_save.pop('secret_key', None)
            
            # Type safety
            config_to_save['debug_mode'] = bool(config_to_save.get('debug_mode', False))
            config_to_save['last_save_frequency'] = int(config_to_save.get('last_save_frequency', 15))
            config_to_save['system_ma_period'] = int(config_to_save.get('system_ma_period', 20))
            config_to_save['auto_login'] = bool(config_to_save.get('auto_login', False))
            
            # Ensure lists are sorted/clean
            for k in ['live_k_bar_plugins', 'strategy_k_bar_plugins', 
                      'backtest_k_bar_plugins', 'backtest_independent_plots']: 
                 if k in config_to_save: config_to_save[k] = sorted(list(config_to_save[k]))

            json.dump(config_to_save, f, indent=4, ensure_ascii=False)
    except Exception as e:
        error(f"Error saving config: {e}")
        print(f"Error saving configuration file: {e}")

def _load_key_from_file(key_path):
    if not key_path: return ""
    filename = os.path.basename(key_path)
    search_paths = [
        key_path,
        os.path.join("..", key_path),
        os.path.join(".config", filename),
        os.path.join("..", ".config", filename),
        os.path.join("..", "..", ".config", filename)
    ]
    for path in search_paths:
        if os.path.exists(path) and os.path.isfile(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content: return ""
                    return content
            except: continue
    return "" 

def load_config(file_path=CONFIG_FILE):
    debug(f"[ENTER] {sys._getframe(0).f_code.co_name}", print_to_console=False)
    
    default_config = {
        "api_key_path": ".config/api_key.txt", 
        "secret_key_path": ".config/secret_key.txt", 
        "db_path": "dbase/market_data.db",
        "last_start_date": datetime.date.today().strftime('%Y-%m-%d'),
        "last_end_date": datetime.date.today().strftime('%Y-%m-%d'),
        "last_save_frequency": 15,
        "debug_mode": False, 
        "ticks_save_enabled": False, 
        "system_ma_period": 20, 
        "min_display_bars": 1600, 
        "page_display_bars": 200,
        "active_frequencies": [1, 5, 15, 30, 60],
        
        # User Role Default
        "user_role": ROLE_DEVELOPER,
        
        # Role Manager: Data moved to SQLite, removed from JSON
        
        "live_k_bar_plugins": ["simple_ma.py", "bollinger_bands.py"], 
        "live_independent_plots": ["volume_plot.py", "example_macd.py", "rsi_plot.py"], 
        "backtest_k_bar_plugins": ["bt_strategy_ma.py", "bt_cost_line.py"],
        "backtest_independent_plots": ["bt_equity.py", "bt_mdd.py"], 
        "strategy_k_bar_plugins": [],     
        "strategy_independent_plots": [], 
        "last_strategy_source": None,
        "last_strategy_path": None,
        "last_futures_contract": 'TXF', 
        "auto_login": False, 
        "last_login_mode": "2",
        "logging": {
            "max_bytes": 10485760,
            "backup_count": 5,
            "encoding": "utf-8"
        }
    }

    if not os.path.exists(file_path):
        warn(f"Config {file_path} not found. Using defaults.")
        default_config['api_key'] = _load_key_from_file(default_config['api_key_path'])
        default_config['secret_key'] = _load_key_from_file(default_config['secret_key_path'])
        return default_config
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            loaded_config = json.load(f)
            # Merge with default
            final_config = {**default_config, **loaded_config}
            
            # Remove legacy identity_manager if exists in JSON
            if "identity_manager" in final_config:
                final_config.pop("identity_manager")

            final_config['api_key'] = _load_key_from_file(final_config.get('api_key_path'))
            final_config['secret_key'] = _load_key_from_file(final_config.get('secret_key_path'))
            
            return final_config 
    except Exception as e:
        error(f"Config load error: {e}")
        return None

class ConfigManager:
    """Console interface for managing application-wide configurations."""
    def __init__(self, config):
        self.config = config
    # ... (Console logic omitted) ...
    def display_config(self): pass
    def run_config_manager_loop(self): pass