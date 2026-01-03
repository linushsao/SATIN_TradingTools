# ==============================================================================
# client_gui/kernel/dep_packer.py
#
# Version: V2.3-000 (Moved)
# 描述:     依賴打包器 (原 core/utils/dep_packer.py)。
# ==============================================================================

import os
import io
import zipfile

class DependencyPacker:
    def __init__(self, workspace_dir):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.projects_dir = os.path.join(self.workspace_dir, "projects")
        self.libs_dir = os.path.join(self.workspace_dir, "libs")

    def pack_project(self, project_id: str) -> bytes:
        project_path = os.path.join(self.projects_dir, project_id)
        if not os.path.exists(project_path):
            raise FileNotFoundError(f"Project '{project_id}' not found in workspace.")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(project_path):
                for file in files:
                    if file.endswith((".py", ".json", ".md")):
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, self.workspace_dir)
                        zf.write(full_path, arcname=rel_path)
            
            if os.path.exists(self.libs_dir):
                for root, dirs, files in os.walk(self.libs_dir):
                    for file in files:
                        if file.endswith(".py"):
                            full_path = os.path.join(root, file)
                            rel_path = os.path.relpath(full_path, self.workspace_dir)
                            zf.write(full_path, arcname=rel_path)

        buffer.seek(0)
        return buffer.read()

    def unpack_project(self, zip_bytes: bytes):
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
                for name in zf.namelist():
                    if name.startswith("/") or ".." in name:
                        raise ValueError("Security Error: Illegal path in zip")
                zf.extractall(self.workspace_dir)
            return True
        except Exception as e:
            print(f"[Packer] Unpack failed: {e}")
            raise

    @staticmethod
    def scan_local_strategies(workspace_dir):
        strategies = []
        ws_path = os.path.abspath(workspace_dir)
        
        if not os.path.exists(ws_path):
            return []

        # 1. Scan Legacy
        for f in os.listdir(ws_path):
            if f.endswith(".py") and f != "__init__.py":
                strategies.append(f)
        
        # 2. Scan Projects
        p_dir = os.path.join(ws_path, "projects")
        if os.path.exists(p_dir):
            for d in os.listdir(p_dir):
                strat_path = os.path.join(p_dir, d, "strategy.py")
                if os.path.exists(strat_path):
                    strategies.append(f"projects/{d}/strategy.py")
        
        return sorted(strategies)
            
    def pack(self, filename):
        return {"strategy_content": "", "core_content": ""}