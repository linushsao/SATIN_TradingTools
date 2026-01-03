# ==============================================================================
# client_gui/kernel/main.py
#
# Version: V3.0-004 (Unified Session Log)
# 更新日期: 2025-12-17
# 描述: SATIN GUI 主程式。
#           [修正]: 移除 PyQt6 已廢棄的 AA_EnableHighDpiScaling 屬性以解決啟動崩潰問題。
#           [新增]: 實作 Session-based 註冊日誌，每次啟動產生單一 Log 檔，並依序記錄各 Service 註冊內容。
# ==============================================================================

import sys
import time
import os
import json
import importlib # Added for dynamic loading
from PyQt6.QtWidgets import (QApplication, QMainWindow, QLabel, QStatusBar, 
                             QVBoxLayout, QHBoxLayout, QWidget, QMessageBox, 
                             QToolBar, QTabWidget, QSizePolicy, QMenu, QSystemTrayIcon,
                             QMenuBar)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QPixmap, QColor, QPainter

# Shared Libraries
from shared.config_manager import load_config, save_config, CONFIG_FILE
from shared.logging_tool import init_logging
from shared.constants import CMD_GET_CAPABILITIES
from shared.capabilities import (
    CAP_MARKET_DATA, CAP_TRADE_EXEC, CAP_ACCOUNT_INFO, 
    CAP_BACKTEST_ENGINE, CAP_REPO_STORAGE, CAP_HISTORICAL_DATA
)
from shared.protocol_defs import RISK_HIGH, NOTIFY_DISPLAY_MODAL, NOTIFY_DISPLAY_TOAST, ROLE_DEVELOPER
from shared.security_utils import load_private_key_obj
from shared.profile_manager import ProfileManager

# GUI Core Components
from kernel.workers import ZmqSubThread, ZmqReqClient
from kernel.context import SateClientContext
from kernel.interface import ISateGuiPlugin
from kernel.services import (
    ServiceError, TradingProxy, BacktestProxy, RepoProxy, BaseProxy
)

# UI Components
from ui_lib.layouts import AboutDialog, PluginManagerDialog, SystemConfigDialog
from ui_lib.connection_manager import ConnectionManagerDialog
from ui_lib.role_manager_dialog import RoleManagerDialog

def create_placeholder_icon(color="#4ec9b0"):
    """產生一個簡單的色塊圖示 (避免缺少 ico 檔案導致報錯)"""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, 28, 28)
    painter.end()
    return QIcon(pixmap)

class MainWindow(QMainWindow):
    sig_project_updated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.config = load_config()
        if not self.config: sys.exit(1)
        
        self.setWindowTitle("SATIN Client (Kernel V3.0)")
        self.resize(1400, 900)
        self.setWindowIcon(create_placeholder_icon("#3498db"))
        
        # Initialize Context FIRST (Dependency Injection)
        self.context = SateClientContext(self)

        # [NEW] Initialize Registration Log (Session based)
        self.registration_log_path = self._init_registration_log()

        # --- System Tray ---
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(create_placeholder_icon("#3498db"))
        self.tray_icon.setVisible(True)
        self.tray_icon.show()
        
        # Menu Bar
        self._init_menubar()
        
        # Toolbar
        self._init_toolbar()
        
        self.central_tabs = QTabWidget()
        self.central_tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.central_tabs)
        
        # Status Bar
        self._init_statusbar()

        self.plugins = [] 
        self.sub_threads = [] 
        
        self._init_services()
        
        if not self._perform_capability_check():
            pass # Continue anyway, maybe offline mode
            
        self._load_plugins_dynamically()
        
        # Startup Login Flow
        QTimer.singleShot(100, self._startup_login_check)

    def _init_menubar(self):
        menubar = self.menuBar()
        
        # File
        file_menu = menubar.addMenu("&File")
        act_exit = QAction("E&xit", self)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)
        
        # View (Plugins)
        view_menu = menubar.addMenu("&Plugin")
        act_plugins = QAction("Plugin Manager...", self)
        act_plugins.triggered.connect(lambda: PluginManagerDialog(self.config, self).exec())
        view_menu.addAction(act_plugins)

        # System
        sys_menu = menubar.addMenu("&System")
        act_config = QAction("Settings...", self)
        act_config.triggered.connect(lambda: SystemConfigDialog(self.config, self).exec())
        sys_menu.addAction(act_config)
        
        #act_con = QAction("Connection Manager...", self)
        #act_con.triggered.connect(lambda: ConnectionManagerDialog(self.context, self.config, self).exec())
        #sys_menu.addAction(act_con)
        
        # Role / Identity
        role_menu = menubar.addMenu("&Role Manager")
        act_role_mgr = QAction("Switch Role / Login...", self)
        act_role_mgr.triggered.connect(lambda: self.open_role_manager())
        role_menu.addAction(act_role_mgr)
        
        # Help
        help_menu = menubar.addMenu("&Help")
        act_about = QAction("&About", self)
        act_about.triggered.connect(self.on_about_click)
        help_menu.addAction(act_about)

    def _init_toolbar(self):
        self.toolbar = QToolBar("System Control")
        # self.addToolBar(self.toolbar) 

    def open_role_manager(self):
        dlg = RoleManagerDialog(self.context, self)
        dlg.exec()

    def _startup_login_check(self):
        """
        Application Startup Login Flow
        1. Try Auto Login (if enabled)
        2. If failed/disabled, Force Modal Dialog Loop until login success or exit.
        """
        # 1. Try Auto Login
        if self.config.get('auto_login', False):
            self._try_auto_login()
        
        # 2. Check Login Status
        user = self.context.get_current_user()
        
        if not user['has_key']:
            print("[Startup] Login required. Opening Role Manager...")
            # Force Modal Loop
            while not self.context.get_current_user()['has_key']:
                dlg = RoleManagerDialog(self.context, self)
                # Remove close button hint to encourage login (optional)
                dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
                dlg.exec()
                
                # Check again after dialog closes
                if self.context.get_current_user()['has_key']:
                    break # Success
                else:
                    # User closed dialog without logging in -> Exit Application
                    reply = QMessageBox.question(self, "Login Required", 
                                                 "You must log in to use SATIN.\nExit application?",
                                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Retry)
                    if reply == QMessageBox.StandardButton.Yes:
                        sys.exit(0)

    def _try_auto_login(self):
        """嘗試自動登入上次的使用者 (From SQLite)"""
        pm = ProfileManager()
        last_id = pm.get_last_active()
        
        if not last_id: return
        
        profile = pm.get_profile(last_id)
        if not profile: return
        
        path = profile['key_path']
        if not os.path.exists(path):
            print(f"[AutoLogin] Key file missing for {last_id}")
            return
        
        try:
            with open(path, 'rb') as f: key_bytes = f.read()
            
            try:
                key_obj = load_private_key_obj(key_bytes, password=None)
                
                is_admin = profile['is_admin']
                user_dir = profile.get('user_dir', '')
                
                self.context.login(last_id, profile['default_role'], key_obj, is_admin, user_dir)
                
                msg = f"Welcome back, {last_id}!"
                if is_admin: msg += " (Admin)"
                self.status_bar.showMessage(msg, 5000)
            except TypeError:
                print(f"[AutoLogin] Key for {last_id} is encrypted. Skipping auto-login.")
                self.status_bar.showMessage(f"[LOCK] {last_id} requires login (Encrypted Key)", 5000)
                
        except Exception as e:
            print(f"[AutoLogin] Failed: {e}")

    def on_user_login(self):
        self._update_status_role()
        user = self.context.get_current_user()
        if user['has_key']:
            print(f"[Main] User Logged In: {user['id']} (Dir: {user['user_dir']})")
        else:
            print("[Main] User Logged Out (Guest)")
        
        # Force refresh current tab to reflect login state
        idx = self.central_tabs.currentIndex()
        if 0 <= idx < len(self.plugins):
            try:
                self.plugins[idx].on_activate()
            except Exception as e:
                print(f"[Main] Refresh UI failed: {e}")

    def _update_status_role(self):
        user = self.context.get_current_user()
        uid = user['id']
        role = user['role']
        has_key = user['has_key']
        is_admin = user['is_admin']
        
        key_icon = "[KEY]" if has_key else "[NO_KEY]"
        role_display = "DEV" if role == ROLE_DEVELOPER else "USR"
        
        display_text = f"User: {uid} ({role_display}) {key_icon}"
        if is_admin:
            display_text += " [Admin]"
        
        self.lbl_user_role.setText(display_text)
        
        if has_key:
            if is_admin:
                self.lbl_user_role.setStyleSheet("color: #f1c40f; font-weight: bold;") # Gold for Admin
            else:
                self.lbl_user_role.setStyleSheet("color: #2ecc71; font-weight: bold;") # Green for User
        else:
            self.lbl_user_role.setStyleSheet("color: #bdc3c7; font-weight: normal;") # Grey for Guest

    def _init_registration_log(self):
        """
        [NEW] 初始化註冊日誌檔案 (單一檔案模式)。
        開機時建立一個新的 Log 檔，例如: logs/registation/Registration_Session_001.log
        """
        try:
            log_root = os.path.join(os.getcwd(), "logs", "registation")
            if not os.path.exists(log_root):
                os.makedirs(log_root)
            
            # 計算流水號
            max_seq = 0
            prefix = "Registration_Session_"
            suffix = ".log"
            
            if os.path.exists(log_root):
                for fname in os.listdir(log_root):
                    if fname.startswith(prefix) and fname.endswith(suffix):
                        try:
                            # Parse: Registration_Session_001.log -> 001
                            number_part = fname[len(prefix):-len(suffix)]
                            seq = int(number_part)
                            if seq > max_seq:
                                max_seq = seq
                        except ValueError:
                            continue
            
            next_seq = max_seq + 1
            filename = f"{prefix}{next_seq:03d}{suffix}"
            full_path = os.path.join(log_root, filename)
            
            # Create empty file with header
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(f"=== SATIN Client Registration Log (Session {next_seq}) ===\n")
                f.write(f"Created at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
            print(f"[Kernel] Registration log initialized: {filename}")
            return full_path
            
        except Exception as e:
            print(f"[Kernel] Failed to init registration log: {e}")
            return None

    def _append_registration_log(self, service_name, data):
        """
        [NEW] 將 Service 註冊內容追加到當次 Session 的 Log 檔。
        """
        if not self.registration_log_path: return
        
        try:
            with open(self.registration_log_path, 'a', encoding='utf-8') as f:
                f.write(f"==================================================\n")
                f.write(f" SERVICE: {service_name}\n")
                f.write(f" TIME:    {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"==================================================\n")
                json.dump(data, f, indent=4, ensure_ascii=False)
                f.write("\n\n")
            print(f"[Kernel] Appended registration info for '{service_name}'")
        except Exception as e:
            print(f"[Kernel] Failed to append log: {e}")

    def _init_services(self):
        print("[Kernel] Initializing services...")
        self.context.clear_services()
        for t in self.sub_threads: 
            if t.isRunning(): t.stop()
        self.sub_threads = []
        
        profile = self.context.get_active_profile()
        services = profile.get('services', [])
        active_count = 0
        
        for svc_conf in services:
            if not svc_conf.get('auto_connect', True): continue
            name = svc_conf.get('name', 'Unknown')
            print(f"[Kernel] Connecting to service node: {name}...")
            
            try:
                client = ZmqReqClient(svc_conf)
                reply = client.send_command(CMD_GET_CAPABILITIES)
                
                if reply.get('status') == 'ok':
                    caps = reply.get('capabilities', [])
                    #meta = reply.get('environment_profile', {})
                    
                    # 修改：合併 environment_profile 與 strategy_schema
                    #meta = reply.get('environment_profile', {}).copy()
                    #if 'strategy_schema' in reply:
                    #    meta['strategy_schema'] = reply['strategy_schema']
 
                    # [FIX] 強化元數據合併邏輯：確保從多個潛在路徑獲取 strategy_schema
                    # 1. 建立環境配置副本
                    meta = reply.get('environment_profile', {}).copy()
              
                    # 2. 優先從 reply 最外層獲取，若無則嘗試從 environment_profile 內獲取
                    schema = reply.get('strategy_schema') or meta.get('strategy_schema')
                    
                    if schema:
                        meta['strategy_schema'] = schema
                    else:
                        # 增加警告日誌，對應 [WARNING] 日誌需求
                        print(f"[Kernel] [WARN] Service '{name}' connected but no strategy_schema found in reply.") 
 
                    #
                    proxy = self._create_proxy_for_caps(client, caps, name)
                    self.context.register_service(name, proxy, caps, meta)
                    active_count += 1
                    print(f"[Kernel] [OK] Registered '{name}' with meta: {meta}")
                    
                    # [NEW] 執行註冊內容存檔 (追加模式)
                    self._append_registration_log(name, reply)
                    
                    pub_port = svc_conf.get('pub_port')
                    if pub_port and int(pub_port) > 0:
                        self._start_sub_thread(svc_conf)
                else:
                    print(f"[Kernel] [WARN] Handshake failed for '{name}': {reply.get('msg')}")
            except Exception as e:
                print(f"[Kernel] [ERR] Failed to connect to '{name}': {e}")
        
        self._update_global_theme()
        self._update_status_role()
        profile_name = profile.get('name', 'Unknown')
        self.lbl_profile.setText(f"Profile: {profile_name} ({active_count} Active)")

    def _update_global_theme(self):
        risk_level = self.context.get_aggregated_risk_level()
        if risk_level == RISK_HIGH:
            self.setStyleSheet("""
                QMainWindow { border: 2px solid #e74c3c; }
                QStatusBar { background-color: #3e1b1b; color: #e74c3c; font-weight: bold; }
            """)
            self.setWindowTitle("[!!] [PRODUCTION] SATIN Client - REAL MONEY AT RISK [!!]")
            self.tray_icon.setIcon(create_placeholder_icon("#e74c3c")) 
        else:
            self.setStyleSheet("")
            self.setWindowTitle("SATIN Client (Simulation/Backtest)")
            self.tray_icon.setIcon(create_placeholder_icon("#3498db"))

    def _create_proxy_for_caps(self, client, caps, service_name):
        if any(c in caps for c in [CAP_MARKET_DATA, CAP_TRADE_EXEC, CAP_ACCOUNT_INFO]):
            return TradingProxy(client)
        if CAP_BACKTEST_ENGINE in caps:
            return BacktestProxy(client)
        if CAP_REPO_STORAGE in caps:
            return RepoProxy(client)
        return BaseProxy(client, service_name)

    def _start_sub_thread(self, svc_config):
        sub_thread = ZmqSubThread(svc_config)
        sub_thread.sig_heartbeat.connect(lambda d: self.on_heartbeat(d, svc_config.get('name')))
        sub_thread.sig_tick.connect(lambda d: self._broadcast_event("TICK", d))
        sub_thread.sig_kbar.connect(lambda d: self._broadcast_event("KBAR", d))
        sub_thread.sig_log.connect(lambda d: self._broadcast_event("LOG", d))
        sub_thread.sig_strategy.connect(lambda d: self._broadcast_event("STRATEGY", d))
        sub_thread.sig_notification.connect(self.on_sys_notification)
        
        sub_thread.sig_bt_heartbeat.connect(lambda d: self.on_heartbeat(d, svc_config.get('name'))) 
        sub_thread.sig_bt_progress.connect(lambda d: self._broadcast_event("BT_PROGRESS", d))
        sub_thread.sig_bt_finished.connect(lambda d: self._broadcast_event("BT_FINISHED", d))

        sub_thread.start()
        self.sub_threads.append(sub_thread)

    def on_sys_notification(self, payload):
        """
        處理系統通知 (SYS_NOTIFICATION)
        Payload: { "level": "INFO|ERROR", "display_type": "TOAST|MODAL", "title": "...", "msg": "..." }
        """
        data = payload.get('data', {})
        level = data.get('level', 'INFO')
        dtype = data.get('display_type', NOTIFY_DISPLAY_TOAST)
        title = data.get('title', 'System Notification')
        msg = data.get('msg', '')
        
        # 1. Log Always
        print(f"[SYS_NOTIFY] [{level}] {title}: {msg}")
        
        # 2. UI Display
        icon = QSystemTrayIcon.MessageIcon.Information
        if level == 'WARNING': icon = QSystemTrayIcon.MessageIcon.Warning
        elif level in ['ERROR', 'CRITICAL']: icon = QSystemTrayIcon.MessageIcon.Critical
        
        if dtype == NOTIFY_DISPLAY_TOAST:
            self.tray_icon.showMessage(title, msg, icon, 5000)
            self.status_bar.showMessage(f"[{title}] {msg}", 5000)
            
        elif dtype == NOTIFY_DISPLAY_MODAL:
            mbox_icon = QMessageBox.Icon.Information
            if level == 'WARNING': mbox_icon = QMessageBox.Icon.Warning
            elif level in ['ERROR', 'CRITICAL']: mbox_icon = QMessageBox.Icon.Critical
            
            QMessageBox.information(self, title, msg) # Simplification, can be strict based on icon

    def on_heartbeat(self, data, service_name):
        self.context.update_health_cache(service_name, data.get('health', {}))
        # Optional: Update UI specifically if needed, otherwise handled by Timer polling Context

    def _broadcast_event(self, topic, data):
        # Dispatch to active page
        idx = self.central_tabs.currentIndex()
        if 0 <= idx < len(self.plugins):
            plugin = self.plugins[idx]
            if hasattr(plugin, 'on_zmq_event'):
                plugin.on_zmq_event(topic, data)
                
        # Dispatch to ProjectMonitor if it's loaded (System Log)
        # TODO: Refactor to proper EventBus
        for p in self.plugins:
            if p.plugin_id == "sate.core.syslog" and hasattr(p, 'on_global_event'):
                p.on_global_event(topic, data)

    def _on_tab_changed(self, index):
        if 0 <= index < len(self.plugins):
            try:
                self.plugins[index].on_activate()
            except Exception as e:
                print(f"[Main] Tab Activate Error: {e}")

    def on_about_click(self):
        dlg = AboutDialog(self)
        dlg.exec()

    def closeEvent(self, event):
        print("[Main] Shutting down...")
        for t in self.sub_threads:
            t.stop()
        event.accept()

    def show_message(self, title, msg, level="info"):
        if level == "error":
            QMessageBox.critical(self, title, msg)
        elif level == "warning":
            QMessageBox.warning(self, title, msg)
        else:
            QMessageBox.information(self, title, msg)
            
        self.status_bar.showMessage(f"[{title}] {msg}", 5000)

    def _perform_capability_check(self) -> bool:
        try:
            self.context.get_service_by_capability(CAP_MARKET_DATA)
            self.context.get_service_by_capability(CAP_TRADE_EXEC)
            return True
        except ServiceError:
            msg = "Missing critical services.\nPlease configure your service profile."
            QMessageBox.warning(self, "Startup Check", msg)
            dlg = ConnectionManagerDialog(self.context, self.config, self)
            if dlg.exec():
                self.config = load_config()
                self._init_services()
                return self._perform_capability_check()
            else:
                return False

    def _init_statusbar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.lbl_connection = QLabel("[O] System Ready")
        self.lbl_info = QLabel("")
        self.lbl_profile = QLabel(f"Profile: Initializing...")
        self.lbl_profile.setStyleSheet("color: #4ec9b0; padding-right: 10px;")
        
        self.lbl_user_role = QLabel("Role: --")
        self.lbl_user_role.setStyleSheet("color: #bdc3c7; padding-left: 10px; font-weight: bold;")
        
        self.status_bar.addPermanentWidget(self.lbl_user_role)
        self.status_bar.addPermanentWidget(self.lbl_profile)
        self.status_bar.addPermanentWidget(self.lbl_connection)
        self.status_bar.addPermanentWidget(self.lbl_info)
        
        self._update_status_role()

    def _load_plugins_dynamically(self):
        """
        [MOD] Load plugins based on the order defined in config.json.
        """
        plugin_base_dir = os.path.join(os.getcwd(), "plugins", "pages")
        if not os.path.exists(plugin_base_dir):
            os.makedirs(plugin_base_dir)
            return
        
        # 1. Discovery Phase: Find all available plugins
        available_plugins = {} # {id: instance}
        
        subdirs = sorted([d for d in os.listdir(plugin_base_dir) if os.path.isdir(os.path.join(plugin_base_dir, d))])
        
        for d in subdirs:
            try:
                module_path = f"plugins.pages.{d}.plugin"
                mod = importlib.import_module(module_path)
                
                plugin_instance = None
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if isinstance(attr, type) and issubclass(attr, ISateGuiPlugin) and attr is not ISateGuiPlugin:
                        plugin_instance = attr()
                        break
                
                if plugin_instance:
                    pid = plugin_instance.plugin_id
                    available_plugins[pid] = plugin_instance
                    print(f"[Loader] Discovered plugin: {pid} ({plugin_instance.display_name})")
            except Exception as e:
                print(f"[Loader] Failed to load {d}: {e}")

        # 2. Loading Phase: Initialize based on config order
        enabled_list = self.config.get("enabled_plugins", [])
        
        # If config is empty or missing, fallback to loading all discovered (legacy behavior)
        if not enabled_list:
            print("[Loader] No load order in config. Loading all discovered plugins...")
            for pid, p in available_plugins.items():
                self._mount_plugin(p)
        else:
            print(f"[Loader] Loading plugins in order: {enabled_list}")
            # Load enabled ones in order
            for pid in enabled_list:
                if pid in available_plugins:
                    self._mount_plugin(available_plugins[pid])
                else:
                    print(f"[Loader] Warning: Plugin ID '{pid}' enabled in config but not found.")
            
            # (Optional) You might want to load remaining plugins that are not in the list but exist?
            # For now, we strictly follow the enabled list to allow hiding plugins.

    def _mount_plugin(self, plugin_instance):
        try:
            plugin_instance.initialize(self.context)
            widget = plugin_instance.get_widget()
            self.central_tabs.addTab(widget, plugin_instance.display_name)
            self.plugins.append(plugin_instance)
            print(f"[Loader] Mounted: {plugin_instance.display_name}")
        except Exception as e:
            print(f"[Loader] Error mounting {plugin_instance.plugin_id}: {e}")

def main():
    # High DPI support (PyQt6 default enabled, removed obsolete Attribute)
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    
    # 1. Init Logging
    init_logging()
    
    app = QApplication(sys.argv)
    
    # Default Font
    font = app.font()
    font.setFamily("Segoe UI")
    font.setPointSize(9)
    app.setFont(font)
    
    # Dark Theme
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()