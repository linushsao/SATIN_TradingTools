# ==============================================================================
# client_gui/kernel/context.py
#
# Version: V2.9-004 (Workspace API)
# 更新日期: 2025-12-12
# 描述:     Client Context (微核心邏輯)。
#           [修正]: 新增 get_workspace_path()，作為專案路徑的唯一真理來源 (Single Source of Truth)。
# ==============================================================================

import os
from shared.config_manager import save_config, CONFIG_FILE
from kernel.workers import probe_service
from kernel.services import ServiceError
from shared.capabilities import CAP_REPO_STORAGE, CAP_STRATEGY_HOST
from shared.protocol_defs import ENV_PRODUCTION, RISK_HIGH, ROLE_TRADER

class SateClientContext:
    def __init__(self, main_window):
        self._main_window = main_window
        
        # Service Store
        self._service_store = {}
        self._capability_map = {}
        
        # Caches
        self.indicator_cache = None  
        self.file_cache = {}         
        
        # User Session State
        self._active_user_id = "Guest"
        self._active_role = ROLE_TRADER 
        self._private_key_obj = None 
        self._is_admin = False 
        self._user_dir = "" # User Workspace Directory (Injected by Login)

    # --- Session Management ---
    
    def login(self, user_id: str, role: str, private_key_obj, is_admin: bool = False, user_dir: str = "") -> None:
        """
        執行登入：更新記憶體狀態並通知 UI。
        Args:
            user_id: 使用者 ID
            role: 權限角色
            private_key_obj: 已解密的 cryptography Key Object
            is_admin: 是否為管理者
            user_dir: 使用者專屬目錄路徑
        """
        self._active_user_id = user_id
        self._active_role = role
        self._private_key_obj = private_key_obj
        self._is_admin = is_admin
        self._user_dir = user_dir
        
        admin_tag = " [Admin]" if is_admin else ""
        dir_tag = f" @ {user_dir}" if user_dir else ""
        self.log("INFO", f"User logged in: {user_id} ({role}){admin_tag}{dir_tag}")
        
        if hasattr(self._main_window, 'on_user_login'):
            self._main_window.on_user_login()

    def logout(self) -> None:
        """登出：清除私鑰物件，重置為 Guest"""
        self._active_user_id = "Guest"
        self._active_role = ROLE_TRADER
        self._private_key_obj = None
        self._is_admin = False
        self._user_dir = ""
        
        self.log("INFO", "User logged out.")
        
        if hasattr(self._main_window, 'on_user_login'):
            self._main_window.on_user_login()

    def get_current_user(self):
        return {
            "id": self._active_user_id,
            "role": self._active_role,
            "has_key": (self._private_key_obj is not None),
            "is_admin": self._is_admin,
            "user_dir": self._user_dir 
        }

    def get_user_dir(self) -> str:
        """取得當前使用者的根目錄 (Raw)"""
        return self._user_dir
        
    def get_workspace_path(self) -> str:
        """
        [Architecture] Single Source of Truth for Project Location.
        Plugins should call this instead of managing their own paths.
        Returns:
            str: Absolute path to the 'projects' directory for current context.
        """
        # 1. 優先使用登入者的專屬目錄
        if self._user_dir and os.path.exists(self._user_dir):
            target = os.path.join(self._user_dir, "projects")
        else:
            # 2. 訪客模式：使用系統預設的共享工作區
            config = self.get_config()
            root_rel = config.get('user_data_root', '../AppData')
            base_path = os.path.abspath(os.path.join(os.getcwd(), root_rel))
            target = os.path.join(base_path, "shared_workspace", "projects")
            
        if not os.path.exists(target):
            try:
                os.makedirs(target)
            except Exception as e:
                self.log("ERROR", f"[Context] Failed to ensure workspace dir: {e}")
        
        return target

    def get_private_key(self):
        return self._private_key_obj

    # --- Existing Methods (Unchanged) ---

    def get_config(self):
        return self._main_window.config

    def get_app_data_dir(self, module_name: str) -> str:
        config = self.get_config()
        root_rel = config.get('user_data_root', '../AppData')
        base_path = os.path.abspath(os.path.join(os.getcwd(), root_rel))
        module_path = os.path.join(base_path, module_name)
        
        if not os.path.exists(module_path):
            try:
                os.makedirs(module_path)
            except Exception as e:
                self.log("ERROR", f"[Context] Failed to create AppData dir: {e}")
        
        os.makedirs(os.path.join(module_path, 'overlays'), exist_ok=True)
        os.makedirs(os.path.join(module_path, 'indicators'), exist_ok=True)
        return module_path

    def register_service(self, service_id: str, proxy_obj, capabilities: list, metadata: dict = None):
        self._service_store[service_id] = {
            'proxy': proxy_obj,
            'caps': capabilities,
            'meta': metadata or {},
            'health': {} 
        }
        for cap in capabilities:
            if cap not in self._capability_map:
                self._capability_map[cap] = []
            if service_id not in self._capability_map[cap]:
                self._capability_map[cap].append(service_id)
        mode = (metadata or {}).get('mode', 'UNKNOWN')
        self.log("DEBUG", f"Registered {service_id} [{mode}]")

    def update_service_health(self, service_id: str, health_data: dict):
        if service_id in self._service_store:
            self._service_store[service_id]['health'] = health_data

    def get_service_by_capability(self, capability: str):
        candidates = self._capability_map.get(capability, [])
        if not candidates:
            raise ServiceError(f"No service found with capability: {capability}")
        service_id = candidates[0]
        return self._service_store[service_id]['proxy']

    def get_all_services_by_capability(self, capability: str) -> list:
        candidates = self._capability_map.get(capability, [])
        return [self._service_store[sid]['proxy'] for sid in candidates]
        
    def get_all_services_info(self) -> list:
        results = []
        for sid, data in self._service_store.items():
            info = {
                'id': sid,
                'caps': data['caps'],
                'meta': data['meta'],
                'health': data.get('health', {})
            }
            results.append(info)
        return results
        
    def update_health_cache(self, service_name, health_payload):
        self.update_service_health(service_name, health_payload)

    def get_aggregated_risk_level(self) -> str:
        for sid, data in self._service_store.items():
            meta = data.get('meta', {})
            if meta.get('mode') == ENV_PRODUCTION:
                return RISK_HIGH
            if meta.get('risk_level') == RISK_HIGH:
                return RISK_HIGH
        return "LOW"

    def clear_services(self):
        self._service_store.clear()
        self._capability_map.clear()

    def get_active_profile(self):
        config = self.get_config()
        pid = config.get('active_profile_id', 'local_dev')
        profiles = config.get('service_profiles', {})
        if pid not in profiles and profiles:
            pid = list(profiles.keys())[0]
        return profiles.get(pid, {})

    def probe_profile(self, profile_data: dict) -> dict:
        results = {}
        services = profile_data.get('services', [])
        for svc in services:
            name = svc.get('name', 'Unknown')
            host = svc.get('host', '127.0.0.1')
            port = svc.get('rep_port', 5557)
            results[name] = probe_service(host, port)
        return results

    def activate_profile(self, profile_id: str):
        config = self.get_config()
        if profile_id not in config.get('service_profiles', {}):
            return False, "Profile ID not found"
        config['active_profile_id'] = profile_id
        save_config(config, CONFIG_FILE)
        return True, "Profile Activated. Please restart application."

    def get_remote_indicators(self, force_refresh=False):
        if self.indicator_cache is not None and not force_refresh:
            return self.indicator_cache
        try:
            repo = self.get_service_by_capability(CAP_REPO_STORAGE)
            data = repo.get_indicator_list()
            self.indicator_cache = data
            return data
        except Exception as e:
            self.log("ERROR", f"Fetch indicators failed: {e}")
            return []

    def get_file_content(self, path: str, force_refresh=False) -> str:
        if path in self.file_cache and not force_refresh:
            return self.file_cache[path]
        try:
            repo = self.get_service_by_capability(CAP_REPO_STORAGE)
            content = repo.download_file(path)
            self.file_cache[path] = content
            return content
        except Exception as e:
            self.log("ERROR", f"Download file '{path}' failed: {e}")
            return ""

    def get_strategy_view_code(self, strategy_id: str, force_refresh=False) -> str:
        """
        [修正] 將請求路徑從 projects/{id}/ 修正為 service_repo/instance_{id}/。
        並且除非使用者手動觸發還原 (force_refresh=True)，否則不執行遠端下載。
        """
        # 修正後的路徑：指向 service_trading 產生的災難還原備份區
        path = f"service_repo/instance_{strategy_id}/view.py"
        
        if force_refresh:
            return self.get_file_content(path, force_refresh=True)
            
        # 平時僅嘗試從本地快取讀取，確保啟動流程不被網路請求阻塞
        return self.file_cache.get(path, "")

    def recover_project_from_remote(self, strategy_id: str):
        """
        [新增功能] 手動災難還原：從 Service 端的備份倉庫下載該實例的所有執行副本並存入開發區。
        """
        import os
        # 定義需要找回的核心檔案
        files_to_recover = ["strategy.py", "strategy_core.py", "view.py", "instance_config.json"]
        results = {}
        
        ws = self.get_workspace_path()
        local_dir = os.path.join(ws, str(strategy_id))
        
        if not os.path.exists(local_dir):
            os.makedirs(local_dir)

        for f_name in files_to_recover:
            # 遠端路徑映射至 service_repo/instance_{id}/
            remote_path = f"service_repo/instance_{strategy_id}/{f_name}"
            
            try:
                # 執行強制下載，更新本地開發區內容
                content = self.get_file_content(remote_path, force_refresh=True)
                if content:
                    local_path = os.path.join(local_dir, f_name)
                    with open(local_path, 'w', encoding='utf-8') as f_obj:
                        f_obj.write(content)
                    results[f_name] = "SUCCESS"
                else:
                    results[f_name] = "NOT_FOUND"
            except Exception as e:
                results[f_name] = f"ERROR: {str(e)}"
                
        return results

    def log(self, level: str, message: str):
        if hasattr(self._main_window, 'plugins'):
            for plugin in self._main_window.plugins:
                if plugin.plugin_id == "sate.core.syslog":
                    try:
                        plugin.get_widget().log_viewer.append_log({"level": level, "msg": message, "dt": ""})
                        return
                    except: pass
        print(f"[{level}] {message}")

    def show_message(self, title: str, msg: str, level="info"):
        from PyQt6.QtWidgets import QMessageBox
        if level == "error": QMessageBox.critical(self._main_window, title, msg)
        elif level == "warning": QMessageBox.warning(self._main_window, title, msg)
        else: QMessageBox.information(self._main_window, title, msg)

    def get_main_window(self):
        return self._main_window

    def notify_project_update(self):
        self.clear_cache()
        if self._main_window:
            self._main_window.sig_project_updated.emit()
            
    def clear_cache(self):
        self.file_cache = {}
        self.indicator_cache = None