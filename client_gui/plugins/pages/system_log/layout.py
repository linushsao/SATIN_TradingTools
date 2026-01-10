# ==============================================================================
# client_gui/plugins/pages/system_log/layout.py
#
# Version: V3.0-013 (Remove Button Removed)
# 更新日期: 2025-12-12
# 描述:     System Monitor 3.0 佈局。
#           [修正]: 移除 Project List Toolbar 中的 <Remove> 按鈕。
# ==============================================================================

import json
import os
from datetime import datetime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QSplitter, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QAbstractItemView, QTextEdit, 
                             QGroupBox, QTabWidget, QFrame, QPushButton, QToolBar)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPixmap, QIcon, QAction

# Protocol Constants
from shared.protocol_defs import (
    ENV_PRODUCTION, RISK_HIGH, 
    HEALTH_OK, HEALTH_WARN, HEALTH_ERROR,
    NOTIFY_LEVEL_ERROR, NOTIFY_LEVEL_CRITICAL, NOTIFY_LEVEL_WARNING
)

# ------------------------------------------------------------------------------
# 1. User Dashboard Widget (Top Left)
# ------------------------------------------------------------------------------
class UserDashboardWidget(QWidget):
    """
    [NEW] 使用者儀表板
    包含: 
    1. 左側 (2/3): 使用者資訊 + 專案列表
    2. 右側 (1/3): 專案詳細資訊/日誌分頁 (QTabWidget)
    """
    sig_project_action = pyqtSignal(str, str) # type (local/team), project_id
    
    # Management Signals
    sig_new_project = pyqtSignal()
    sig_import_project = pyqtSignal()
    sig_export_project = pyqtSignal()
    sig_remove_project = pyqtSignal() # General Remove (Selected)
    #sig_delete_local = pyqtSignal(str) # Specific Delete button
    sig_open_project_folder = pyqtSignal(str) # [新增] 用於通知 Plugin 開啟資料夾
    
    # Settings Signal (Removed from UI, kept for compatibility if needed, but unused)
    # sig_project_settings = pyqtSignal() 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Main Dashboard GroupBox
        self.grp_dashboard = QGroupBox("Dashboard")
        self.grp_dashboard.setStyleSheet("QGroupBox { font-weight: bold; }")
        dash_layout = QVBoxLayout(self.grp_dashboard)
        dash_layout.setContentsMargins(5, 10, 5, 5) 
        
        self.dash_splitter = QSplitter(Qt.Orientation.Horizontal)
        dash_layout.addWidget(self.dash_splitter)
        
        self.layout.addWidget(self.grp_dashboard)
        
        # --- Left Container (User + Projects) ---
        self.left_container = QWidget()
        self.left_layout = QVBoxLayout(self.left_container)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 1. Top: User Info Area
        self.info_frame = QFrame()
        self.info_frame.setStyleSheet("QFrame { background-color: #252526; border-radius: 5px; margin-bottom: 5px; }")
        self.info_layout = QHBoxLayout(self.info_frame)
        
        # Avatar (4.5 : 3.5 ratio, width 80 -> height ~103)
        self.lbl_avatar = QLabel()
        self.lbl_avatar.setFixedSize(80, 103) 
        self.lbl_avatar.setStyleSheet("border: 2px solid #3e3e42; border-radius: 4px; background-color: #1e1e1e;")
        self.lbl_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_avatar.setText("[IMG]")
        self.info_layout.addWidget(self.lbl_avatar)
        
        # Text Info
        self.text_info_layout = QVBoxLayout()
        self.text_info_layout.setSpacing(2)
        
        self.lbl_nickname = QLabel("Guest User")
        self.lbl_nickname.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.lbl_nickname.setStyleSheet("color: #ffffff;")
        
        self.lbl_userid = QLabel("ID: guest")
        self.lbl_userid.setStyleSheet("color: #808080;")
        
        self.text_info_layout.addWidget(self.lbl_nickname)
        self.text_info_layout.addWidget(self.lbl_userid)
        self.text_info_layout.addStretch()
        
        self.info_layout.addLayout(self.text_info_layout)
        self.info_layout.addStretch()
        
        # Right Side Stats (User Info Area)
        self.stats_layout = QVBoxLayout()
        self.lbl_stat_local = QLabel("Local Projects: 0")
        self.lbl_stat_running = QLabel("Active Strategies: 0")
        self.stats_layout.addWidget(self.lbl_stat_local)
        self.stats_layout.addWidget(self.lbl_stat_running)
        self.stats_layout.addStretch()
        self.info_layout.addLayout(self.stats_layout)
        
        self.left_layout.addWidget(self.info_frame)
        
        # 2. Bottom: Project Lists
        self.grp_projects = QGroupBox("Project List")
        layout_projects = QVBoxLayout(self.grp_projects)
        layout_projects.setContentsMargins(5, 10, 5, 5)

        # Management Toolbar
        self.toolbar = QHBoxLayout()
        
        # Define Buttons
        btn_new = QPushButton("New")
        btn_import = QPushButton("Import")
        btn_export = QPushButton("Export")
        # [MOD] Removed Remove button per request
        # btn_remove = QPushButton("Remove")
        
        # Connect Signals
        btn_new.clicked.connect(self.sig_new_project)
        btn_import.clicked.connect(self.sig_import_project)
        btn_export.clicked.connect(self.sig_export_project)
        # btn_remove.clicked.connect(self.sig_remove_project)
        
        # Button Styles
        base_style = "QPushButton { color: white; font-weight: bold; border-radius: 3px; padding: 4px 10px; }"
        btn_new.setStyleSheet(f"background-color: #d35400; {base_style}")
        btn_import.setStyleSheet(f"background-color: #2980b9; {base_style}")
        btn_export.setStyleSheet(f"background-color: #8e44ad; {base_style}")
        # btn_remove.setStyleSheet(f"background-color: #c0392b; {base_style}")

        self.toolbar.addWidget(btn_new)
        self.toolbar.addWidget(btn_import)
        self.toolbar.addWidget(btn_export)
        self.toolbar.addStretch()
        # self.toolbar.addWidget(btn_remove)
        
        layout_projects.addLayout(self.toolbar)

        self.tabs_projects = QTabWidget()
        self.tabs_projects.setStyleSheet("QTabWidget::pane { border: 0; }")
        
        # Tab 1: Local Projects
        self.table_local = self._create_project_table(["Open", "Name", "Path", "Updated"])
        self.tabs_projects.addTab(self.table_local, "[Local Projects]")
        
        # Tab 2: Team Projects
        self.table_team = self._create_project_table(["Name", "Author", "Updated"])
        self.tabs_projects.addTab(self.table_team, "[Team Projects]")
        
        layout_projects.addWidget(self.tabs_projects)
        self.left_layout.addWidget(self.grp_projects)
        
        self.dash_splitter.addWidget(self.left_container)
        
        # --- Right Container (Placeholder Tabs) ---
        self.right_container = QWidget()
        self.right_layout = QVBoxLayout(self.right_container)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Right Tabs with Placeholders
        self.right_tabs = QTabWidget()
        self.right_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #3e3e3e; background-color: #1e1e1e; }
            QTabBar::tab { background: #2d2d2d; color: #808080; padding: 5px; min-width: 60px; }
            QTabBar::tab:selected { background: #1e1e1e; color: #e0e0e0; border-top: 2px solid #007acc; font-weight: bold; }
        """)
        
        # Placeholder Tab 1
        self.tab_reserved_1 = QLabel("Reserved: Project Data")
        self.tab_reserved_1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tab_reserved_1.setStyleSheet("color: #555; font-style: italic;")
        self.right_tabs.addTab(self.tab_reserved_1, "Details")
        
        # Placeholder Tab 2
        self.tab_reserved_2 = QLabel("Reserved: Logs")
        self.tab_reserved_2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tab_reserved_2.setStyleSheet("color: #555; font-style: italic;")
        self.right_tabs.addTab(self.tab_reserved_2, "Logs")

        self.right_layout.addWidget(self.right_tabs)
        self.dash_splitter.addWidget(self.right_container)
        
        # Set Ratio 2:1 (Left takes 2/3, Right takes 1/3)
        self.dash_splitter.setStretchFactor(0, 1)
        self.dash_splitter.setStretchFactor(1, 1)

    def _create_project_table(self, headers):
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        
        table.setStyleSheet("""
            QTableWidget { 
                background-color: #1e1e1e; 
                color: #e0e0e0; 
                gridline-color: #333; 
                border: none; 
            }
            QTableWidget::item {
                padding: 4px;
            }
            QTableWidget::item:selected {
                background-color: #264f78;
                color: #ffffff;
            }
            QHeaderView::section { 
                background-color: #2d2d2d; 
                color: #d4d4d4; 
                padding: 4px; 
                border: 1px solid #3e3e3e;
            }
        """)
        
        table.cellDoubleClicked.connect(lambda r, c, t=table: self._on_table_double_click(t, r))
        table.cellClicked.connect(lambda r, c, t=table: self._on_table_click(t, r))
        return table

    def _on_table_double_click(self, table, row):
        if table.columnCount() > 3 and table.currentColumn() == 3: return
        item = table.item(row, 0)
        if item:
            project_id = item.text()
            tab_idx = self.tabs_projects.currentIndex()
            ptype = "local" if tab_idx == 0 else "team"
            # self.sig_project_action.emit(ptype, project_id)

    # 修正點 B: 點擊表格時，從 UserRole 讀取邏輯 ID
    def _on_table_click(self, table, row):
        name_item = table.item(row, 0)
        if name_item:
            # [修正]: 優先從 UserRole 取得邏輯 ID (101)
            project_id = name_item.data(Qt.ItemDataRole.UserRole)
            if not project_id: project_id = name_item.text()
            
            tab_idx = self.tabs_projects.currentIndex()
            ptype = "local" if tab_idx == 0 else "team"
            self.sig_project_action.emit(ptype, project_id)

    def update_project_messages(self, messages):
        """
        [MOD] Stubbed out as UI components were removed.
        Prevents plugin logic crash.
        """
        pass

    def update_user_info(self, user_data):
        uid = user_data.get('id', 'Guest')
        nick = user_data.get('nickname', uid)
        path = user_data.get('avatar_path', '')
        
        self.lbl_nickname.setText(nick)
        self.lbl_userid.setText(f"ID: {uid}")
        
        if path and os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self.lbl_avatar.setPixmap(pixmap.scaled(76, 99, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
                self.lbl_avatar.setText("")
            else:
                self.lbl_avatar.setText("[IMG]")
        else:
            self.lbl_avatar.setText("[IMG]")

    def update_stats(self, local_count, active_count):
        self.lbl_stat_local.setText(f"Local Projects: {local_count}")
        self.lbl_stat_running.setText(f"Active Strategies: {active_count}")

    def update_local_projects(self, projects):
        self._populate_table(self.table_local, projects, ["Open", "name", "path", "updated_at"])

    def update_team_projects(self, projects):
        self._populate_table(self.table_team, projects, ["name", "author", "updated_at"])

    def _populate_table(self, table, data_list, keys):
        table.setRowCount(0)
        table.setRowCount(len(data_list))
        for i, item in enumerate(data_list):
            pid = item.get('id', item.get('name')) # 取得邏輯 ID 
            
            for j, key in enumerate(keys):
                if key == "Open":
                    # [新增] 在第一欄建立 Open 按鈕
                    w_open = QWidget()
                    l_open = QHBoxLayout(w_open)
                    l_open.setContentsMargins(2, 2, 2, 2)
                    btn_open = QPushButton("Open")
                    btn_open.setStyleSheet("""
                        QPushButton { background-color: #27ae60; color: white; font-weight: bold; border-radius: 2px; }
                        QPushButton:hover { background-color: #2ecc71; }
                    """)
                    	# 按下時發射訊號，帶入專案 ID 
                    btn_open.clicked.connect(lambda checked, x=pid: self.sig_open_project_folder.emit(x))
                    l_open.addWidget(btn_open)
                    table.setCellWidget(i, j, w_open)
                    continue

                val = str(item.get(key, "-"))
                t_item = QTableWidgetItem(val)
                t_item.setForeground(QColor("#e0e0e0"))
                
                	# [新增]: 如果是 Name 欄位，將真正的邏輯 ID (101) 存入隱藏資料中
                if key == "name":
                    t_item.setData(Qt.ItemDataRole.UserRole, item.get('id', val))
                
                table.setItem(i, j, t_item)
# ------------------------------------------------------------------------------
# 2. Event Log Table (Bottom Left)
# ------------------------------------------------------------------------------
class EventLogTable(QTableWidget):
    """統一事件中心表格"""
    def __init__(self):
        super().__init__()
        self.columns = ["Time", "Level", "Source", "Message"]
        self.setColumnCount(len(self.columns))
        self.setHorizontalHeaderLabels(self.columns)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        # Style
        h = self.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # Time
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents) # Level
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents) # Source
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)          # Message
        
        self.setStyleSheet("QTableWidget { background-color: #1e1e1e; color: #d4d4d4; gridline-color: #333; }")

    def add_event(self, data):
        row = self.rowCount()
        self.insertRow(row)
        
        dt = data.get('dt', datetime.now().strftime('%H:%M:%S'))
        level = data.get('level', 'INFO')
        msg = data.get('msg', str(data))
        source = data.get('logger', data.get('source_id', 'Sys'))
        
        color = QColor("#d4d4d4") # Default Grey
        if level in [NOTIFY_LEVEL_ERROR, "ERROR"]: color = QColor("#f44747") 
        elif level in [NOTIFY_LEVEL_CRITICAL, "CRITICAL"]: color = QColor("#ff0000") 
        elif level in [NOTIFY_LEVEL_WARNING, "WARN", "WARNING"]: color = QColor("#cca700") 
        elif "SUCCESS" in level or "OK" in msg: color = QColor("#6A9955") 
        
        self.setItem(row, 0, QTableWidgetItem(str(dt)))
        
        item_lvl = QTableWidgetItem(str(level))
        item_lvl.setForeground(color)
        item_lvl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.setItem(row, 1, item_lvl)
        
        self.setItem(row, 2, QTableWidgetItem(str(source)))
        self.setItem(row, 3, QTableWidgetItem(str(msg)))
        
        self.scrollToBottom()
        if self.rowCount() > 500:
            self.removeRow(0)

# ------------------------------------------------------------------------------
# 3. Service Dashboard Table (Right Top)
# ------------------------------------------------------------------------------
class ServiceDashboardTable(QTableWidget):
    """服務狀態儀表板"""
    def __init__(self, parent_widget):
        super().__init__()
        self.parent_widget = parent_widget
        self.columns = ["Service Name", "Mode", "Status", "Caps"]
        self.setColumnCount(len(self.columns))
        self.setHorizontalHeaderLabels(self.columns)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.cellClicked.connect(self._on_row_clicked)
        
        self._service_map = {} # row -> service_id

    def update_services(self, services_info):
        self.setRowCount(len(services_info))
        self._service_map = {}
        
        for i, info in enumerate(services_info):
            sid = info.get('id', 'Unknown')
            self._service_map[i] = info
            
            self.setItem(i, 0, QTableWidgetItem(sid))
            
            meta = info.get('meta', {})
            mode = meta.get('mode', 'UNKNOWN')
            item_mode = QTableWidgetItem(mode)
            if mode == ENV_PRODUCTION:
                item_mode.setForeground(QColor("#ff5555"))
                item_mode.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            elif mode == "SIMULATION":
                item_mode.setForeground(QColor("#55ff55"))
            self.setItem(i, 1, item_mode)
            
            health = info.get('health', {})
            status = health.get('status', 'UNKNOWN')
            icon = "O"
            if status == HEALTH_OK: icon = "[OK]"
            elif status == HEALTH_WARN: icon = "[WARN]"
            elif status == HEALTH_ERROR: icon = "[ERR]"
            
            item_status = QTableWidgetItem(icon)
            if status == HEALTH_OK: item_status.setForeground(QColor("#2ecc71"))
            elif status == HEALTH_WARN: item_status.setForeground(QColor("#f1c40f"))
            elif status == HEALTH_ERROR: item_status.setForeground(QColor("#e74c3c"))
            self.setItem(i, 2, item_status)
            
            caps = info.get('caps', [])
            self.setItem(i, 3, QTableWidgetItem(f"{len(caps)} Caps"))

    def _on_row_clicked(self, row, col):
        if row in self._service_map:
            data = self._service_map[row]
            self.parent_widget.show_details(data)

    def add_log(self, data):
        self.event_table.add_event(data)

# ------------------------------------------------------------------------------
# 4. Main System Monitor Widget (Root Layout)
# ------------------------------------------------------------------------------
class SystemMonitorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.layout.addWidget(self.splitter)
        
        # --- Left Panel ---
        self.left_panel = QWidget()
        vbox_left = QVBoxLayout(self.left_panel)
        vbox_left.setContentsMargins(0,0,0,0)
        
        self.left_vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 1. Project Dashboard (Top)
        self.dashboard = UserDashboardWidget()
        self.left_vertical_splitter.addWidget(self.dashboard)
        
        # 2. Event Center (Bottom)
        self.event_group = QGroupBox("Unified Event Center")
        vbox_event = QVBoxLayout(self.event_group)
        self.event_table = EventLogTable()
        vbox_event.addWidget(self.event_table)
        self.left_vertical_splitter.addWidget(self.event_group)
        
        self.left_vertical_splitter.setStretchFactor(0, 4)
        self.left_vertical_splitter.setStretchFactor(1, 6)
        
        vbox_left.addWidget(self.left_vertical_splitter)
        self.splitter.addWidget(self.left_panel)
        
        # --- Right Panel ---
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        
        self.dash_group = QGroupBox("Service Registry")
        vbox_dash = QVBoxLayout(self.dash_group)
        self.svc_table = ServiceDashboardTable(self)
        vbox_dash.addWidget(self.svc_table)
        self.right_splitter.addWidget(self.dash_group)
        
        self.insp_group = QGroupBox("Inspector")
        vbox_insp = QVBoxLayout(self.insp_group)
        self.text_inspector = QTextEdit()
        self.text_inspector.setReadOnly(True)
        self.text_inspector.setStyleSheet("font-family: Consolas; font-size: 10pt; background-color: #2b2b2b; color: #a9b7c6;")
        vbox_insp.addWidget(self.text_inspector)
        self.right_splitter.addWidget(self.insp_group)
        
        self.splitter.addWidget(self.right_splitter)
        
        self.splitter.setStretchFactor(0, 5) 
        self.splitter.setStretchFactor(1, 3) 
        
    def show_details(self, service_info):
        display_data = {
            "ID": service_info.get('id'),
            "Capabilities": service_info.get('caps'),
            "Environment Profile (Static)": service_info.get('meta'),
            "Health Status (Dynamic)": service_info.get('health')
        }
        text = json.dumps(display_data, indent=4, ensure_ascii=False)
        self.text_inspector.setText(text)
    
    def update_services(self, services_list):
        self.svc_table.update_services(services_list)

    def add_log(self, data):
        self.event_table.add_event(data)