# ==============================================================================
# project_manager.py
#
# Version: V0.1-001
# 更新日期: 2025-12-27
# 描述: 策略專案管理器。
# [修正]: 1. 移除硬編碼樣板字串，改用實體目錄複製機制。
#        2. 配合 V0.1-001 解耦架構，統一使用實體樣板管理。
#        3. 維持 strategy.py, strategy_core.py, view.py 之原始命名規範。
# ==============================================================================

import os
import json
import shutil
from datetime import datetime

class ProjectManager:
    def __init__(self, root_dir):
        """
        初始化管理器並設定實體樣板路徑。
        樣板預期存放於：client_gui/plugins/pages/strategies/templates/default_strategy/
        """
        self.template_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 
            "templates", "default_strategy"
        )
        self.set_root_dir(root_dir)

    def set_root_dir(self, new_root_dir):
        """ 設定專案儲存的根目錄與註冊表路徑 """
        self.root_dir = os.path.abspath(new_root_dir)
        
        # 判斷目錄層級以決定專案存放位置
        if os.path.basename(self.root_dir) == "project":
             self.projects_dir = self.root_dir
        else:
             self.projects_dir = os.path.join(self.root_dir, "projects")

        self.registry_file = os.path.join(os.path.dirname(self.projects_dir), "projects.json")
        self.registry = {}
        self._ensure_workspace()
        self.load_registry()

    def _ensure_workspace(self):
        """ 確保專案存放目錄存在 """
        if not os.path.exists(self.projects_dir):
            try:
                os.makedirs(self.projects_dir)
            except Exception as e:
                print(f"[ProjectManager] Failed to create dir {self.projects_dir}: {e}")

    def load_registry(self):
        """ 載入 projects.json 註冊表 """
        if os.path.exists(self.registry_file):
            try:
                with open(self.registry_file, 'r', encoding='utf-8') as f:
                    self.registry = json.load(f)
            except Exception as e:
                print(f"[ProjectManager] Load registry failed: {e}")
                self.registry = {}
        else:
            self.registry = {}

    def _save_registry(self):
        """ 儲存註冊表資訊 """
        try:
            with open(self.registry_file, 'w', encoding='utf-8') as f:
                json.dump(self.registry, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[ProjectManager] Save registry failed: {e}")

    def get_projects(self):
        """ 取得所有已註冊的專案清單 """
        return self.registry

    def get_project_path(self, project_id):
        """ 根據 ID 取得專案實體路徑 """
        info = self.registry.get(str(project_id))
        return info.get('path') if info else None

    def list_files(self, project_id):
        """ 掃描專案目錄下的程式檔案 """
        path = self.get_project_path(project_id)
        if not path or not os.path.exists(path):
            return []
            
        files = []
        try:
            for f in os.listdir(path):
                if os.path.isfile(os.path.join(path, f)):
                    if f.endswith(('.py', '.json', '.txt', '.md')):
                        files.append(f)
        except Exception as e:
            print(f"[ProjectManager] Scan files failed: {e}")
            
        return sorted(files)

    def create_project(self, name, target_dir, description=""):
        """
        [核心修正] create_project:
        1. 透過 shutil.copytree 複製實體樣板目錄。
        2. 自動產生專屬 metadata.json。
        """
        # 1. 檢查專案名稱是否重複
        for pid, info in self.registry.items():
            if info.get('name') == name:
                return False, f"Project name '{name}' already exists (ID: {pid})."
        
        # 2. 生成新 ID (自動遞增，從 101 開始)
        existing_ids = [int(k) for k in self.registry.keys() if k.isdigit()]
        next_id = max(existing_ids) + 1 if existing_ids else 101
        str_id = str(next_id)

        # 3. 準備目標路徑
        if not target_dir or target_dir == ".":
            target_dir = self.projects_dir
        project_path = os.path.join(target_dir, name).replace("\\", "/")
        
        if os.path.exists(project_path):
            return False, f"Directory '{project_path}' already exists."

        try:
            # --- 複製實體樣板 ---
            if not os.path.exists(self.template_path):
                return False, f"樣板目錄不存在: {self.template_path}"
                
            shutil.copytree(self.template_path, project_path)
            
            # --- 產生並覆蓋 Metadata ---
            meta = {
                "id": str_id,
                "name": name,
                "description": description,
                "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "file_name": "strategy.py", # 預設進入點
                "contract_code": "TXFR1",
                "frequency": 1
            }
            with open(os.path.join(project_path, "metadata.json"), 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=4)

            # 4. 更新註冊表
            self.registry[str_id] = {
                "name": name,
                "path": project_path,
                "description": description,
                "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            self._save_registry()
            
            return True, str_id

        except Exception as e:
            if os.path.exists(project_path):
                shutil.rmtree(project_path)
            return False, str(e)

    def delete_project(self, project_id, delete_files=False):
        """ 刪除專案並可選是否移除實體檔案 """
        if str(project_id) not in self.registry:
            return False, "Project not found"
        
        info = self.registry[str(project_id)]
        path = info.get('path')
        name = info.get('name', 'Unknown')
        
        try:
            if delete_files and path and os.path.exists(path):
                # 安全檢查：確保路徑末尾與專案名稱一致才刪除
                if path.replace("\\", "/").rstrip("/").endswith(name):
                    shutil.rmtree(path)
            
            del self.registry[str(project_id)]
            self._save_registry()
            return True, "Project deleted"
        except Exception as e:
            return False, str(e)