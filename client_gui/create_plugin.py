# ==============================================================================
# client_gui/create_plugin.py
#
# Version: V1.1-007 (Final Production Version)
# 描述:     SATIN GUI 外掛模組標準架構產生器。
# 修正紀錄: 
#   1. 預設產生功能性範例代碼（訊號與槽綁定、微核心日誌調用）。
#   2. 強化 UI 佈局 (ui/layout.py) 與 邏輯 (plugin.py) 的交互範例。
# ==============================================================================

import os
import json
import re

# --- 配置區 ---
BASE_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.join(BASE_SCRIPT_DIR, "plugins")
PAGES_DIR = os.path.join(PLUGIN_ROOT, "pages")
CONFIG_FILE = os.path.join(BASE_SCRIPT_DIR, "config.json")

# --- 模板定義 ---

TPL_MANIFEST = """{{
    "plugin_id": "{plugin_id}",
    "display_name": "{display_name}",
    "version": "1.0.0",
    "author": "{author}",
    "description": "Standard SATIN Plugin with functional example."
}}"""

TPL_PLUGIN_PY = """# ==============================================================================
# {display_name} - Plugin Entry
# ==============================================================================

from kernel.interface import ISateGuiPlugin
from .ui.layout import LayoutWidget

class {class_name}Plugin(ISateGuiPlugin):
    def __init__(self):
        self.widget = None
        self.context = None

    @property
    def plugin_id(self) -> str:
        return "{plugin_id}"

    @property
    def display_name(self) -> str:
        return "{display_name}"

    def initialize(self, context):
        \"\"\"
        初始化外掛邏輯。
        context: SateClientContext，提供日誌、資料請求與微核心通訊功能。
        \"\"\"
        self.context = context
        self.widget = LayoutWidget()
        
        # --- 範例: 綁定 UI 事件 ---
        self.widget.action_btn.clicked.connect(self.on_example_action)
        
        self.context.log("INFO", f"Plugin '{{self.display_name}}' Initialized.")

    def on_example_action(self):
        \"\"\"範例事件處理邏輯\"\"\"
        # 1. 在 UI 上顯示更新
        self.widget.info_label.setText("狀態: 已觸發範例動作")
        
        # 2. 透過微核心發送日誌
        self.context.log("DEBUG", f"[{{self.plugin_id}}] 使用者點擊了範例按鈕")

    def get_widget(self):
        return self.widget

    def on_activate(self):
        pass

    def on_zmq_event(self, topic: str, payload: dict):
        \"\"\"處理來自微核心的訂閱訊息 (如 TICK, KBAR)\"\"\"
        pass
"""

TPL_LAYOUT_PY = """from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QHBoxLayout
from PyQt6.QtCore import Qt

class LayoutWidget(QWidget):
    \"\"\"
    標準 UI 佈局類別 (ui/layout.py)
    \"\"\"
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        
        # 標題
        self.title = QLabel("{display_name}")
        self.title.setStyleSheet("font-size: 24px; font-weight: bold; color: #4ec9b0;")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 狀態資訊
        self.info_label = QLabel("Plugin ID: {plugin_id}")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 互動按鈕範例
        self.btn_layout = QHBoxLayout()
        self.action_btn = QPushButton("執行範例動作")
        self.action_btn.setFixedWidth(150)
        self.btn_layout.addStretch()
        self.btn_layout.addWidget(self.action_btn)
        self.btn_layout.addStretch()
        
        # 組裝
        self.layout.addStretch()
        self.layout.addWidget(self.title)
        self.layout.addWidget(self.info_label)
        self.layout.addSpacing(20)
        self.layout.addLayout(self.btn_layout)
        self.layout.addStretch()
"""

def sanitize(name):
    return re.sub(r'[^a-zA-Z0-9_]', '_', name.strip().replace(" ", "_")).lower()

def to_camel_case(text):
    return ''.join(x.capitalize() or '_' for x in text.split('_'))

def ensure_package_structure():
    for path in [PLUGIN_ROOT, PAGES_DIR]:
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        init_file = os.path.join(path, "__init__.py")
        if not os.path.exists(init_file):
            with open(init_file, 'w', encoding='utf-8') as f:
                f.write("# SATIN Framework Package\\n")

def run():
    print(f"=== SATIN Plugin Generator V1.1-007 ===")
    
    xxx = input("1. 請輸入模組名稱 xxx (資料夾名): ").strip()
    if not xxx: return
    
    category = input("2. 功能類別 [core | page | service] (預設: core): ").strip() or "core"
    display_name = input(f"3. 顯示名稱 (預設: {xxx}): ").strip() or xxx
    author = input("4. 作者名稱 (預設: Dev): ").strip() or "Dev"
    
    module_folder = sanitize(xxx)
    plugin_id = f"sate.{category}.{module_folder}" 
    class_name = to_camel_case(module_folder)
    target_path = os.path.join(PAGES_DIR, module_folder)
    
    if os.path.exists(target_path):
        print(f"❌ 錯誤: 目錄 '{module_folder}' 已存在。")
        return

    ensure_package_structure()
    
    try:
        # 建立目錄樹
        sub_dirs = ["", "ui", "logic", "assets"]
        for sd in sub_dirs:
            p = os.path.join(target_path, sd)
            os.makedirs(p, exist_ok=True)
            open(os.path.join(p, "__init__.py"), 'w').close()

        # 寫入包含範例的檔案
        files = {
            "manifest.json": TPL_MANIFEST.format(plugin_id=plugin_id, display_name=display_name, author=author),
            "plugin.py": TPL_PLUGIN_PY.format(plugin_id=plugin_id, display_name=display_name, class_name=class_name),
            "ui/layout.py": TPL_LAYOUT_PY.format(display_name=display_name, plugin_id=plugin_id)
        }
        for rel_path, content in files.items():
            with open(os.path.join(target_path, rel_path), "w", encoding="utf-8") as f:
                f.write(content)

        # 自動註冊
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            if "enabled_plugins" not in config: config["enabled_plugins"] = []
            if plugin_id not in config["enabled_plugins"]:
                config["enabled_plugins"].append(plugin_id)
                with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)
        
        print(f"\\n✅ 標準外掛「{display_name}」建立成功！")
        print(f"   [範例代碼已就緒]：包含按鈕點擊與日誌發送範例。")

    except Exception as e:
        print(f"❌ 建立失敗: {e}")

if __name__ == "__main__":
    run()