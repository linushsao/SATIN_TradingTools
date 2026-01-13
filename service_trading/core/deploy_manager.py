# ==============================================================================
# service_trading/core/deploy_manager.py
#
# Version: V1.0-002 (Instance Isolation)
# 描述:     部署管理器 (Server Side)
#           [修正]: 為每個策略實例建立專屬目錄，避免檔案混雜於 plugins 根目錄。
#           [修正]: 將專屬目錄動態加入 sys.path 以支援策略內部引用。
# ==============================================================================

import os
import sys
import importlib
from shared.logging_tool import info, error

class DeployManager:
    def __init__(self, plugin_dir):
        self.plugin_dir = plugin_dir
        if not os.path.exists(self.plugin_dir):
            os.makedirs(self.plugin_dir)

    def handle_deploy(self, args):
        """
        處理 DEPLOY_STRATEGY 指令
        """
        try:
            strat_name = args.get('strategy_name')
            strat_content = args.get('strategy_content')
            core_content = args.get('core_content')

            if not strat_name or not strat_content:
                return {"status": "error", "msg": "Invalid payload"}

            # --- [修正] 建立專屬子目錄 ---
            instance_folder = strat_name.replace(".py", "")
            target_dir = os.path.join(self.plugin_dir, instance_folder)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
            
            # 1. 寫入 strategy_core.py (實例專屬的依賴核心)
            core_path = os.path.join(target_dir, "strategy_core.py")
            with open(core_path, 'w', encoding='utf-8') as f:
                f.write(core_content or "")
            
            # 2. 寫入策略主檔
            strat_path = os.path.join(target_dir, strat_name)
            with open(strat_path, 'w', encoding='utf-8') as f:
                f.write(strat_content)

            # --- [修正] 設定系統搜尋路徑 ---
            abs_target_dir = os.path.abspath(target_dir)
            if abs_target_dir not in sys.path:
                sys.path.insert(0, abs_target_dir) # 優先搜尋此路徑
                info(f"[Deploy] Added to sys.path: {abs_target_dir}")

            # 3. 熱重載 (Hot Reload) 邏輯
            # 由於現在每個策略有自己的目錄，若要重載特定實例的 core，需確保路徑正確
            if "strategy_core" in sys.modules:
                try:
                    import strategy_core
                    importlib.reload(strategy_core)
                    info(f"[Deploy] Reloaded strategy_core for {instance_folder}.")
                except Exception as e:
                    error(f"[Deploy] Reload core failed: {e}")

            info(f"[Deploy] Successfully deployed '{strat_name}' to {instance_folder}/")
            return {"status": "ok", "msg": f"Deployed {strat_name} in dedicated folder."}

        except Exception as e:
            error(f"[Deploy] Error: {e}")
            return {"status": "error", "msg": str(e)}