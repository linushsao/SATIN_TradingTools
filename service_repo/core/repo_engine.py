# ==============================================================================
# service_repo/core/repo_engine.py
#
# Version: V1.0-001 (Registry Impl)
# 描述:     Repo 服務核心邏輯。
#           [修正]: 實作 registry.json 的讀寫，確保 get_project_list 能回傳資料。
# ==============================================================================

import os
import json
import base64
import time
from datetime import datetime

# Define storage location
REPO_DATA_DIR = "storage"
REGISTRY_FILE = os.path.join(REPO_DATA_DIR, "registry.json")

class RepoEngine:
    def __init__(self):
        # Ensure storage directory exists
        if not os.path.exists(REPO_DATA_DIR):
            os.makedirs(REPO_DATA_DIR)
        
        # Load existing registry
        self.registry = self._load_registry()

    def _load_registry(self):
        if os.path.exists(REGISTRY_FILE):
            try:
                with open(REGISTRY_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[Repo] Load registry error: {e}")
                return {}
        return {}

    def _save_registry(self):
        try:
            with open(REGISTRY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.registry, f, indent=4)
        except Exception as e:
            print(f"[Repo] Save registry error: {e}")

    def handle_command(self, cmd, args):
        """Main entry point for ZMQ handler"""
        if cmd == "UPDATE_PROJECT":
            return self.update_project(args)
        elif cmd == "GET_PROJECT_LIST":
            return self.get_project_list()
        elif cmd == "DOWNLOAD_PROJECT":
            return self.download_project(args)
        elif cmd == "DELETE_PROJECT":
            return self.delete_project(args)
        return {"status": "error", "msg": f"Unknown Repo CMD: {cmd}"}

    def update_project(self, args):
        pid = args.get('project_id')
        b64_data = args.get('zip_data')
        
        if not pid or not b64_data:
            return {"status": "error", "msg": "Missing ID or Data"}
            
        # 1. Write Zip File to Disk
        file_path = os.path.join(REPO_DATA_DIR, f"{pid}.zip")
        try:
            with open(file_path, 'wb') as f:
                f.write(base64.b64decode(b64_data))
        except Exception as e:
            return {"status": "error", "msg": f"Write failed: {e}"}
            
        # 2. Update Registry [KEY STEP]
        # This records the project so it appears in the list
        self.registry[pid] = {
            "project_id": pid,
            "version": f"v{int(time.time())}", # Simple timestamp versioning
            "updated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "file_path": file_path,
            "size": os.path.getsize(file_path)
        }
        self._save_registry()
        
        print(f"[Repo] Updated project: {pid}")
        return {"status": "ok", "msg": "Updated successfully"}

    def get_project_list(self):
        # Convert registry dict to list for client
        data_list = list(self.registry.values())
        # Sort by updated_at desc
        data_list.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
        return {"status": "ok", "data": data_list}

    def download_project(self, args):
        pid = args.get('project_id')
        if pid not in self.registry:
            return {"status": "error", "msg": "Project not found"}
            
        info = self.registry[pid]
        path = info.get('file_path')
        
        if path and os.path.exists(path):
            try:
                with open(path, 'rb') as f:
                    raw = f.read()
                return {
                    "status": "ok", 
                    "zip_data": base64.b64encode(raw).decode('utf-8')
                }
            except Exception as e:
                return {"status": "error", "msg": f"Read error: {e}"}
                
        return {"status": "error", "msg": "File missing on disk"}

    def delete_project(self, args):
        pid = args.get('project_id')
        if pid in self.registry:
            info = self.registry[pid]
            path = info.get('file_path')
            
            # Remove file
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except: pass
            
            # Remove from registry
            del self.registry[pid]
            self._save_registry()
            print(f"[Repo] Deleted project: {pid}")
            return {"status": "ok", "msg": "Deleted"}
            
        return {"status": "error", "msg": "Project not found"}