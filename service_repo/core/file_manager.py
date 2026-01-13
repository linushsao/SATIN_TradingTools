# ==============================================================================
# service_repo/core/file_manager.py
#
# Version: V2.4-004 (Clean Symbols)
# 更新日期: 2025-12-12
# 描述:     檔案管理器
#           [修正]: 移除 Log 中的 Unicode Emoji。
# ==============================================================================

import os
import json
import shutil
import zipfile
import io
import datetime
import base64
from shared.logging_tool import info, error
from shared.security_utils import calculate_hash, sign_data, verify_signature

# --- Templates (Unchanged) ---
TEMPLATE_METADATA = """{{
    "id": "{name}",
    "name": "{name}",
    "version": "1.0.0",
    "author": "User",
    "created_at": "{date}",
    "description": "MA20 Crossover Strategy with Visualization",
    "file_name": "strategy.py",
    "frequency": 15,
    "max_order_qty": 1,
    "max_position_qty": 1,
    "max_slippage": 5,
    "chase_buffer": 1,
    "profit_retention_rate": 0.66,
    "auto_restart": false,
    "is_active": true,
    "execution_mode": "Monitor"
}}"""

TEMPLATE_CORE = """# ==============================================================================
# strategy_core.py
# Description: Shared calculation logic for MA20 Strategy
# ==============================================================================

import pandas as pd
import numpy as np

def calc_indicators(df, period=20):
    \"\"\"
    計算技術指標與關鍵價位
    \"\"\"
    df = df.copy()
    
    # 1. 計算 MA (進場基準線)
    df['entry_line'] = df['Close'].rolling(window=period).mean()
    
    # 2. 定義 SL/TP 線 (示意用，實際策略可能動態計算)
    # SL = MA * 0.99 (綠色)
    # TP = MA * 1.02 (洋紅色)
    df['sl_line'] = df['entry_line'] * 0.99
    df['tp_line'] = df['entry_line'] * 1.02
    
    return df
"""

TEMPLATE_STRATEGY = """# ==============================================================================
# Strategy: {name}
# Description: MA20 Crossover Entry
# ==============================================================================

from strategy_core import calc_indicators

def calculate(df_kbars, parameters):
    \"\"\"
    策略邏輯：當收盤價向上穿越 MA20 時做多
    \"\"\"
    
    # 1. 呼叫 Core
    period = parameters.get('system_ma_period', 20)
    df = calc_indicators(df_kbars, period)
    
    if len(df) < 2:
        return {}
    
    # 2. 取得當前與前一根 K 棒
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 3. 判斷黃金交叉 (Close 向上穿越 Entry Line)
    # 前一根在線下 (或相等)，當前在線上
    crossover = (prev['Close'] <= prev['entry_line']) and (curr['Close'] > curr['entry_line'])
    
    if crossover:
        return {
            'entry_price': curr['Close'],      # 以當前收盤價進場
            'sl_price': curr['sl_line'],       # 停損設在 SL 線
            'tp_price': curr['tp_line'],       # 停利設在 TP 線
            'direction': 'Long',
            'profit_retention': 0.5            # 自訂獲利留存率
        }
        
    return {}
"""

TEMPLATE_VIEW = """# ==============================================================================
# view.py
# Description: Visualization Layer (White/Green/Magenta Lines)
# ==============================================================================

import pandas as pd
import numpy as np
from strategy_core import calc_indicators

# 標準輸出變數 (GUI 將讀取此變數進行繪圖)
ADDPLOT_CONFIG = []

try:
    if 'K_BAR_DATA' in locals() and not K_BAR_DATA.empty:
        
        # 1. 讀取參數
        sys_period = locals().get('SYSTEM_MA_PERIOD', 20)
        
        # 2. 呼叫 Core 計算
        df = calc_indicators(K_BAR_DATA, sys_period)
        
        # 3. 設定繪圖 (三條線)
        
        # 進場線 (白色) - MA20
        ADDPLOT_CONFIG.append({{
            'data': df['entry_line'],
            'kwargs': {{'color': 'white', 'linestyle': '-', 'linewidth': 1.5, 'label': 'Entry(MA)'}}
        }})

        # 停損線 (綠色)
        ADDPLOT_CONFIG.append({{
            'data': df['sl_line'],
            'kwargs': {{'color': 'green', 'linestyle': ':', 'linewidth': 1.0, 'label': 'SL'}}
        }})

        # 停利線 (洋紅色)
        ADDPLOT_CONFIG.append({{
            'data': df['tp_line'],
            'kwargs': {{'color': 'magenta', 'linestyle': '--', 'linewidth': 1.0, 'label': 'TP'}}
        }})

except Exception as e:
    print(f"[View Error] {e}")
"""


class FileManager:
    def __init__(self, storage_root, config_root_dir):
        self.root = os.path.abspath(storage_root)
        self.projects_dir = os.path.join(self.root, 'projects')
        self.libs_dir = os.path.join(self.root, 'libs')
        
        self.indicators_dir = os.path.join(self.libs_dir, 'indicators') 
        self.analysis_dir = os.path.join(self.libs_dir, 'analysis')    
        
        self._ensure_dir(self.projects_dir)
        self._ensure_dir(self.libs_dir)
        self._ensure_dir(self.indicators_dir)
        self._ensure_dir(self.analysis_dir)

        self.config_root = config_root_dir
        self.authorized_keys = self._load_authorized_keys()

    def _ensure_dir(self, path):
        if not os.path.exists(path): os.makedirs(path)

    def _load_authorized_keys(self):
        """讀取已授權的公鑰清單 (用於驗證 Client 上傳)"""
        keys_path = os.path.join(self.config_root, 'authorized_keys')
        keys = {}
        if os.path.exists(keys_path):
            with open(keys_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        try:
                            # 格式: developer_id|base64_public_key
                            dev_id, pub_key_b64 = line.split('|', 1)
                            # 存儲 PEM 格式的 bytes
                            keys[dev_id.strip()] = base64.b64decode(pub_key_b64.strip())
                        except Exception as e:
                            error(f"[Repo] Failed to parse authorized key line: {line}. Error: {e}")
        return keys

    def create_project(self, project_name):
        safe_name = "".join([c for c in project_name if c.isalnum() or c in ('_', '-')])
        if not safe_name: return False, "Invalid name"
        
        p_dir = os.path.join(self.projects_dir, safe_name)
        if os.path.exists(p_dir): return False, "Project already exists"
        
        try:
            os.makedirs(p_dir)
            
            # 1. Write Metadata
            meta_content = TEMPLATE_METADATA.format(
                name=safe_name, 
                date=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            with open(os.path.join(p_dir, "metadata.json"), 'w', encoding='utf-8') as f:
                f.write(meta_content)
                
            # 2. Write Strategy
            strat_content = TEMPLATE_STRATEGY.format(name=safe_name)
            with open(os.path.join(p_dir, "strategy.py"), 'w', encoding='utf-8') as f:
                f.write(strat_content)
                
            # 3. Write Core
            with open(os.path.join(p_dir, "strategy_core.py"), 'w', encoding='utf-8') as f:
                f.write(TEMPLATE_CORE)

            # 4. Write View
            with open(os.path.join(p_dir, "view.py"), 'w', encoding='utf-8') as f:
                f.write(TEMPLATE_VIEW)
                
            info(f"[Repo] Created project '{safe_name}' with templates.")
            return True, "Created"
        except Exception as e:
            error(f"[Repo] Create failed: {e}")
            try: shutil.rmtree(p_dir)
            except: pass
            return False, str(e)

    def delete_project(self, project_name):
        safe_name = "".join([c for c in project_name if c.isalnum() or c in ('_', '-')])
        if not safe_name: return False, "Invalid name"

        p_dir = os.path.join(self.projects_dir, safe_name)
        if not os.path.exists(p_dir): return False, "Project not found"
        
        try:
            shutil.rmtree(p_dir)
            info(f"[Repo] Project '{safe_name}' deleted.")
            return True, "Deleted"
        except Exception as e:
            error(f"[Repo] Delete failed: {e}")
            return False, str(e)

    def get_project_list(self):
        projects = []
        if os.path.exists(self.projects_dir):
            for d in os.listdir(self.projects_dir):
                path = os.path.join(self.projects_dir, d)
                if os.path.isdir(path):
                    meta_path = os.path.join(path, "metadata.json")
                    p_info = {"id": d, "name": d}
                    if os.path.exists(meta_path):
                        try:
                            with open(meta_path, 'r', encoding='utf-8') as f:
                                meta = json.load(f)
                                p_info.update(meta)
                        except: pass
                    projects.append(p_info)
        return projects

    def list_indicators(self):
        """
        列出所有可用的指標 (Overlay 與 Independent)。
        """
        result = []
        
        # 1. Analysis Plugins (Overlay) - e.g. MA, BBands
        if os.path.exists(self.analysis_dir):
            for f in os.listdir(self.analysis_dir):
                if f.endswith(".py") and f != "__init__.py":
                    result.append({
                        "name": f,
                        "type": "overlay",
                        "path": f"libs/analysis/{f}"
                    })

        # 2. Indicator Plugins (Independent) - e.g. MACD, RSI
        if os.path.exists(self.indicators_dir):
            for f in os.listdir(self.indicators_dir):
                if f.endswith(".py") and f != "__init__.py":
                    result.append({
                        "name": f,
                        "type": "independent",
                        "path": f"libs/indicators/{f}"
                    })
        
        return result

    def update_project(self, project_name, zip_bytes):
        # [FIX] 使用 projects_dir 作為目標，而非 root
        safe_name = "".join([c for c in project_name if c.isalnum() or c in ('_', '-')])
        if not safe_name: return False, "Invalid name"
        
        target_dir = os.path.join(self.projects_dir, safe_name)
        
        # [FIX] 如果目錄不存在 (首次 Push)，自動建立
        if not os.path.exists(target_dir):
            try:
                os.makedirs(target_dir)
            except Exception as e:
                error(f"[Repo] Failed to create project dir: {e}")
                return False, f"Create dir failed: {e}"

        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
                for name in zf.namelist():
                    if name.startswith("/") or ".." in name:
                        return False, "Security Error"
                zf.extractall(target_dir)
            info(f"[Repo] Project '{safe_name}' updated.")
            return True, "Updated successfully"
        except Exception as e:
            error(f"[Repo] Update failed: {e}")
            return False, str(e)

    def pack_project_to_bytes(self, project_id: str, security_level: str, server_key_path: str = None) -> dict:
        project_path = os.path.join(self.projects_dir, project_id)
        if not os.path.exists(project_path):
            raise FileNotFoundError(f"Project '{project_id}' not found.")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(project_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, self.root)
                    zf.write(full_path, arcname=rel_path)
            
            if os.path.exists(self.libs_dir):
                for root, dirs, files in os.walk(self.libs_dir):
                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, self.root)
                        zf.write(full_path, arcname=rel_path)
                        
        zip_bytes = buffer.getvalue()
        
        # 1. 計算 Checksum (Level 1+)
        checksum = calculate_hash(zip_bytes) if security_level != 'NONE' else None
        signature = None

        # 2. 計算 Signature (Level 2: STRICT)
        if security_level == 'STRICT':
            if not server_key_path or not os.path.exists(server_key_path):
                error("[Repo] STRICT mode requires server private key, but key not found.")
                signature = None
            else:
                try:
                    with open(server_key_path, 'rb') as f:
                        server_private_key = f.read()
                    signature = sign_data(server_private_key, zip_bytes)
                except Exception as e:
                    error(f"[Repo] Signing failed: {e}")
                    signature = None
            
        return {
            "zip_bytes": zip_bytes, 
            "checksum": checksum, 
            "signature": signature
        }

    def verify_update_payload(self, security_level: str, developer_id: str, payload_zip_bytes: bytes, payload_checksum: str, payload_signature: str) -> bool:
        if security_level == 'NONE':
            return True

        # 1. 檢查 Checksum (Level 1+)
        expected_checksum = calculate_hash(payload_zip_bytes)
        if expected_checksum != payload_checksum:
            error(f"[Repo/Security] Checksum mismatch! Expected: {expected_checksum[:8]}, Received: {payload_checksum[:8]}")
            return False

        if security_level == 'CHECKSUM':
            return True

        # 2. 檢查 Signature (Level 2: STRICT)
        if security_level == 'STRICT':
            if not developer_id or not payload_signature:
                error("[Repo/Security] STRICT mode validation failed: Missing Developer ID or Signature.")
                return False

            dev_public_key = self.authorized_keys.get(developer_id)
            if not dev_public_key:
                error(f"[Repo/Security] STRICT mode validation failed: Developer ID '{developer_id}' not authorized.")
                return False

            if not verify_signature(dev_public_key, payload_zip_bytes, payload_signature):
                error(f"[Repo/Security] STRICT mode validation failed: Invalid Signature for developer {developer_id}.")
                return False
                
            info(f"[Repo/Security] [OK] Signature verified for developer: {developer_id}")
            return True
        
        return False

    def get_file_content(self, rel_path: str):
        if ".." in rel_path or rel_path.startswith("/"):
             raise ValueError("Security Error: Invalid path")
        full_path = os.path.join(self.root, rel_path)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"File not found: {rel_path}")
        with open(full_path, 'r', encoding='utf-8') as f:
            return f.read()