# ==============================================================================
# client_gui/ui_lib/layouts.py
#
# Version: V2.9-010 (Log Thread Info)
# 更新日期: 2025-12-13
# 描述:     UI 元件佈局定義庫。
#           [修正]: LogViewer 增加顯示執行緒資訊 (Thread Name)，配合後端日誌升級。
# ==============================================================================

import datetime
import os
import json
import shutil
import importlib
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QTextEdit, QLabel, 
                             QGroupBox, QAbstractItemView, QPushButton, QDialog,
                             QFormLayout, QLineEdit, QDialogButtonBox, QSpinBox,
                             QDoubleSpinBox, QComboBox, QDateEdit, QListWidget,
                             QTabWidget, QListWidgetItem, QCheckBox, QMessageBox,
                             QInputDialog, QFileDialog)
from PyQt6.QtCore import Qt, pyqtSignal, QDate
from PyQt6.QtGui import QColor, QFont, QPixmap

from shared.config_manager import save_config, CONFIG_FILE
from kernel.interface import ISateGuiPlugin
# Import Connection Manager
from ui_lib.connection_manager import ConnectionManagerWidget

class LogViewer(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas, Monospace; font-size: 10pt;")
        self.document().setMaximumBlockCount(1000)
        
    def append_log(self, data):
        ts = data.get('dt', '')
        level = data.get('level', 'INFO')
        msg = data.get('msg', '')
        thread_name = data.get('thread', '') # [NEW] Get thread name
        
        color = "#d4d4d4"
        if level in ["WARN", "WARNING"]: color = "#dcdcaa"
        elif level in ["ERROR", "CRITICAL"]: color = "#f44747"
        elif level == "DEBUG": color = "#569cd6"
        elif "ENTRY" in msg or "Order Sent" in msg: color = "#4ec9b0"
        elif "EXIT" in msg: color = "#c586c0"
        
        # Format: [Time] [Thread] [Level] Message
        thread_part = f'<span style="color:#569cd6">[{thread_name}]</span> ' if thread_name and thread_name != 'MainThread' else ''
        html = f'<span style="color:#808080">[{ts}]</span> {thread_part}<span style="color:{color}"><b>[{level}]</b> {msg}</span>'
        self.append(html)

class StrategyTable(QTableWidget):
    sig_toggle_strategy = pyqtSignal(int)
    sig_remove_strategy = pyqtSignal(str)
    sig_undeploy_strategy = pyqtSignal(int)
    
    def __init__(self):
        super().__init__()
        # [修正]: 增加 Undeploy 欄位
        self.columns = ["No.", "Status", "Name", "Pos", "Last", "PnL", "Entry", "SL", "TP", "Action", "Undeploy"]
        self.setColumnCount(len(self.columns))
        self.setHorizontalHeaderLabels(self.columns)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.setColumnWidth(0, 40)
        self.setColumnWidth(1, 80)
        self.setColumnWidth(2, 150)
        # 固定 Action 與 Undeploy 寬度
        self.setColumnWidth(9, 70)
        self.setColumnWidth(10, 80)
        
    def update_data(self, data_list):
        """
        [修正]: 實作 Start/Stop 切換邏輯與 Undeploy 按鈕產生
        """
        self.setRowCount(len(data_list))
        for i, s in enumerate(data_list):
            sid = s.get('id', 0)
            is_running = s.get('running', False)
            
            # 1-9 欄位填充 (略過，維持原邏輯)
            self.setItem(i, 0, QTableWidgetItem(str(sid)))
            
            status_item = QTableWidgetItem("RUNNING" if is_running else "STOPPED")
            status_item.setForeground(QColor("green") if is_running else QColor("gray"))
            self.setItem(i, 1, status_item)
            
            self.setItem(i, 2, QTableWidgetItem(str(s.get('name', ''))))
            self.setItem(i, 3, QTableWidgetItem(str(s.get('pos', 0))))
            self.setItem(i, 4, QTableWidgetItem(f"{s.get('last', 0):.1f}"))
            
            # PnL 顏色標註
            pnl = s.get('pnl', 0)
            pnl_item = QTableWidgetItem(f"{pnl:.0f}")
            if pnl > 0: pnl_item.setForeground(QColor("red"))
            elif pnl < 0: pnl_item.setForeground(QColor("green"))
            self.setItem(i, 5, pnl_item)
            
            self.setItem(i, 6, QTableWidgetItem(str(s.get('entry', 0))))
            self.setItem(i, 7, QTableWidgetItem(str(s.get('sl', 0))))
            self.setItem(i, 8, QTableWidgetItem(str(s.get('tp', 0))))

            # 9. Action 按鈕: Start/Stop 切換 [修正 7-2-1]
            btn_action = QPushButton("Stop" if is_running else "Start")
            if is_running:
                btn_action.setStyleSheet("background-color: #442222; color: white; font-weight: bold;")
            else:
                btn_action.setStyleSheet("background-color: #224422; color: white; font-weight: bold;")
            
            # 綁定信號
            btn_action.clicked.connect(lambda _, _id=sid: self.sig_toggle_strategy.emit(_id))
            self.setCellWidget(i, 9, btn_action)

            # 10. Undeploy 按鈕: 移除佇列 [修正 7-2-2]
            btn_undeploy = QPushButton("Undeploy")
            btn_undeploy.setStyleSheet("background-color: #333333; color: #aaaaaa;")
            btn_undeploy.clicked.connect(lambda _, _id=sid: self.sig_undeploy_strategy.emit(_id))
            self.setCellWidget(i, 10, btn_undeploy)           
class HistoryDownloadDialog(QDialog):
    def __init__(self, contracts=None, parent=None): 
        super().__init__(parent)
        self.setWindowTitle("Download History")
        self.resize(350, 200)
        layout = QFormLayout(self)
        self.combo_code = QComboBox()
        if contracts:
            for c in contracts: self.combo_code.addItem(f"{c['code']} ({c['name']})", c['code']) 
        else: self.combo_code.addItem("TXFR1", "TXFR1") 
        self.date_start = QDateEdit(QDate.currentDate().addDays(-30))
        self.date_end = QDateEdit(QDate.currentDate())
        self.date_start.setCalendarPopup(True); self.date_start.setDisplayFormat("yyyy-MM-dd")
        self.date_end.setCalendarPopup(True); self.date_end.setDisplayFormat("yyyy-MM-dd")
        layout.addRow("Contract:", self.combo_code)
        layout.addRow("Start Date:", self.date_start)
        layout.addRow("End Date:", self.date_end)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept); self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
    def get_input(self):
        return {"code": self.combo_code.currentData(), "start": self.date_start.date().toString("yyyy-MM-dd"), "end": self.date_end.date().toString("yyyy-MM-dd")}

class TickTable(QTableWidget):
    def __init__(self):
        super().__init__()
        self.columns = ["Time", "Price", "Vol"]
        self.setColumnCount(len(self.columns))
        self.setHorizontalHeaderLabels(self.columns)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.setColumnWidth(0, 80) 
        self.setColumnWidth(1, 80)
        
        font_height = self.fontMetrics().height()
        compact_height = font_height + 4
        self.verticalHeader().setDefaultSectionSize(compact_height)
        
    def add_tick(self, tick_data):
        row_idx = self.rowCount()
        self.insertRow(row_idx)
        time_str = tick_data.get('t', '').split(' ')[1].split('.')[0]
        self.setItem(row_idx, 0, QTableWidgetItem(time_str))
        price = tick_data.get('c', 0)
        price_item = QTableWidgetItem(f"{price:.0f}")
        price_item.setForeground(QColor("blue")) 
        self.setItem(row_idx, 1, price_item)
        vol = tick_data.get('v', 0)
        self.setItem(row_idx, 2, QTableWidgetItem(str(vol)))
        if self.rowCount() > 50: self.removeRow(0)
        self.scrollToBottom()

class ContractList(QListWidget):
    def __init__(self):
        super().__init__()
    def update_data(self, contracts):
        self.clear()
        for c in contracts: self.addItem(f"{c['code']} ({c['name']})")

class AccountInfoWidget(QWidget): 
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        self.lbl_id = QLabel("Account: --")
        self.lbl_id.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.lbl_status = QLabel("Status: --")
        self.lbl_status.setFont(QFont("Arial", 10))
        layout.addWidget(self.lbl_id)
        layout.addWidget(self.lbl_status)
        layout.addStretch()
        self.setLayout(layout)
    def update_info(self, accounts):
        if accounts:
            acc = accounts[0]
            self.lbl_id.setText(f"Account: {acc.get('account_id', 'N/A')}")
            signed = "[V] Signed" if acc.get('signed') else "[!] Unsigned"
            self.lbl_status.setText(f"Status: {signed}")
            if acc.get('signed'): self.lbl_status.setStyleSheet("color: green")
            else: self.lbl_status.setStyleSheet("color: red")
        else:
            self.lbl_id.setText("Account: N/A"); self.lbl_status.setText("Status: No Data")

class PluginManagerDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Plugins")
        self.resize(600, 450)
        self.config = config
        # Use a list to preserve order from config
        self.enabled_plugins = config.get('enabled_plugins', [])
        if self.enabled_plugins is None: self.enabled_plugins = []
        self.is_first_setup = (config.get('enabled_plugins') is None)
        
        self.plugin_base_dir = os.path.join(os.getcwd(), "plugins", "pages")
        
        self.layout = QHBoxLayout(self)
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Available Plugins (Drag to Reorder):"))
        
        self.list_plugins = QListWidget()
        # Enable Drag and Drop for Reordering
        self.list_plugins.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_plugins.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_plugins.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        
        left_layout.addWidget(self.list_plugins)
        
        lbl_hint = QLabel("Note: Check to enable. Drag items to change Tab order.\nChanges require application restart.")
        lbl_hint.setStyleSheet("color: gray; font-size: 10px;")
        left_layout.addWidget(lbl_hint)
        self.layout.addLayout(left_layout, 2)
        
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("<b>Actions</b>"))
        btn_import = QPushButton("[Import Plugin]")
        btn_import.clicked.connect(self._on_import_plugin)
        right_layout.addWidget(btn_import)
        btn_remove = QPushButton("[Remove Plugin]")
        btn_remove.setStyleSheet("color: #ff5555;")
        btn_remove.clicked.connect(self._on_remove_plugin)
        right_layout.addWidget(btn_remove)
        right_layout.addStretch()
        self.btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.btn_box.accepted.connect(self.accept)
        self.btn_box.rejected.connect(self.reject)
        right_layout.addWidget(self.btn_box)
        self.layout.addLayout(right_layout, 1)
        
        self._scan_and_populate()

    def _scan_and_populate(self):
        self.list_plugins.clear()
        if not os.path.exists(self.plugin_base_dir): return
        
        # 1. Scan and instantiate all valid plugins
        found_plugins = {} # {id: (instance, dir_name)}
        subdirs = sorted([d for d in os.listdir(self.plugin_base_dir) if os.path.isdir(os.path.join(self.plugin_base_dir, d))])
        
        for d in subdirs:
            try:
                # Use importlib to handle folder names
                module_path = f"plugins.pages.{d}.plugin"
                mod = importlib.import_module(module_path)
                importlib.reload(mod)
                
                plugin_instance = None
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if isinstance(attr, type) and issubclass(attr, ISateGuiPlugin) and attr is not ISateGuiPlugin:
                        plugin_instance = attr()
                        break
                
                if plugin_instance:
                    found_plugins[plugin_instance.plugin_id] = (plugin_instance, d)
                else:
                    print(f"No plugin class found in {d}")
                    
            except Exception as e:
                # Add broken plugin to list immediately
                item = QListWidgetItem(f"[!] Broken: {d}")
                item.setData(Qt.ItemDataRole.UserRole, f"broken.{d}")
                item.setData(Qt.ItemDataRole.ToolTipRole, d)
                item.setForeground(QColor("red"))
                self.list_plugins.addItem(item)

        # 2. Add enabled plugins FIRST (in preserved order)
        processed_ids = set()
        
        if self.is_first_setup:
            # If first setup, just add everything sorted by dir name (which is what we got from subdirs)
            pass 
        else:
            for pid in self.enabled_plugins:
                if pid in found_plugins:
                    instance, d_name = found_plugins[pid]
                    self._add_plugin_item(instance, d_name, checked=True)
                    processed_ids.add(pid)

        # 3. Add remaining plugins (disabled or new)
        # Iterate through subdirs to maintain some deterministic order for new items
        for d in subdirs:
            # Find which plugin_id corresponds to this dir
            target_pid = None
            target_inst = None
            
            for pid, (inst, dname) in found_plugins.items():
                if dname == d:
                    target_pid = pid
                    target_inst = inst
                    break
            
            if target_pid and target_pid not in processed_ids:
                # Default checked if first setup, else unchecked
                is_checked = True if self.is_first_setup else False
                self._add_plugin_item(target_inst, d, checked=is_checked)

    def _add_plugin_item(self, instance, dir_name, checked=False):
        pid = instance.plugin_id
        pname = instance.display_name
        item = QListWidgetItem(f"{pname} ({pid})")
        item.setData(Qt.ItemDataRole.UserRole, pid) 
        item.setData(Qt.ItemDataRole.ToolTipRole, dir_name) 
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.list_plugins.addItem(item)

    def _on_import_plugin(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Plugin Directory")
        if not dir_path: return
        if not os.path.exists(os.path.join(dir_path, "plugin.py")):
            QMessageBox.critical(self, "Error", "Invalid plugin structure.\n'plugin.py' not found.")
            return
        dirname = os.path.basename(dir_path)
        target_path = os.path.join(self.plugin_base_dir, dirname)
        if os.path.exists(target_path):
            QMessageBox.warning(self, "Warning", f"Plugin directory '{dirname}' already exists.")
            return
        try:
            shutil.copytree(dir_path, target_path)
            QMessageBox.information(self, "Success", f"Plugin '{dirname}' imported.\nIt is disabled by default.")
            self._scan_and_populate()
        except Exception as e:
            QMessageBox.critical(self, "Import Failed", str(e))

    def _on_remove_plugin(self):
        item = self.list_plugins.currentItem()
        if not item: return
        plugin_id = item.data(Qt.ItemDataRole.UserRole)
        dir_name = item.data(Qt.ItemDataRole.ToolTipRole)
        confirm = QMessageBox.question(self, "Confirm Remove", 
                                       f"Are you sure you want to permanently delete plugin?\n\nID: {plugin_id}\nDir: {dir_name}",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.Yes:
            target_path = os.path.join(self.plugin_base_dir, dir_name)
            try:
                if os.path.exists(target_path): shutil.rmtree(target_path)
                self._scan_and_populate()
            except Exception as e: QMessageBox.critical(self, "Remove Failed", str(e))

    def apply_changes(self):
        new_enabled = []
        # Iterate by Visual Order (0 to count)
        for i in range(self.list_plugins.count()):
            item = self.list_plugins.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                pid = item.data(Qt.ItemDataRole.UserRole)
                if not pid.startswith("broken."): 
                    new_enabled.append(pid)
        
        self.config['enabled_plugins'] = new_enabled
        save_config(self.config, CONFIG_FILE)
        QMessageBox.information(self, "Plugins Updated", "Changes saved (Order Preserved).\nPlease restart the application to apply changes.")

class SystemConfigDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("System Options")
        self.resize(600, 450)
        self.config = config
        self.context = parent.context if parent and hasattr(parent, 'context') else None
        self.layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        
        self.tab_general = QWidget()
        form = QFormLayout(self.tab_general)
        
        self.chk_debug = QCheckBox("Enable Debug Mode")
        self.chk_debug.setChecked(config.get('debug_mode', False))
        form.addRow("Debug Log:", self.chk_debug)
        
        self.tabs.addTab(self.tab_general, "General")
        
        if self.context:
            self.conn_manager = ConnectionManagerWidget(self.context, self.config)
            self.tabs.addTab(self.conn_manager, "Network / Service")
        else: self.tabs.addTab(QLabel("Context not available"), "Network")
        self.layout.addWidget(self.tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        self.layout.addWidget(buttons)

    def apply_changes(self):
        self.config['debug_mode'] = self.chk_debug.isChecked()
        save_config(self.config, CONFIG_FILE)

class IndicatorManagerDialog(QDialog):
    def __init__(self, config, app_data_dir, mode='LIVE', parent=None):
        super().__init__(parent)
        self.mode = mode.upper()
        self.setWindowTitle(f"Manage Indicators ({self.mode})")
        self.resize(700, 600)
        self.config = config
        self.app_data_dir = app_data_dir
        if self.mode == 'BACKTEST':
            self.key_overlay = 'backtest_k_bar_plugins'; self.key_indep = 'backtest_independent_plots'
        else:
            self.key_overlay = 'live_k_bar_plugins'; self.key_indep = 'live_independent_plots'
        self.layout = QHBoxLayout(self)
        left_layout = QVBoxLayout()
        grp_overlay = QGroupBox("Main Chart Overlays (No Sort)")
        v_overlay = QVBoxLayout(grp_overlay)
        self.list_overlays = QListWidget()
        v_overlay.addWidget(self.list_overlays)
        left_layout.addWidget(grp_overlay)
        grp_indep = QGroupBox("Sub Chart Indicators (Drag to Sort)")
        v_indep = QVBoxLayout(grp_indep)
        self.list_independents = QListWidget()
        self.list_independents.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_independents.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        v_indep.addWidget(self.list_independents)
        left_layout.addWidget(grp_indep)
        self.layout.addLayout(left_layout, 3)
        layout_btns = QVBoxLayout()
        layout_btns.addWidget(QLabel("<b>Actions</b>"))
        btn_imp_overlay = QPushButton("[Import Overlay]")
        btn_imp_overlay.clicked.connect(lambda: self._on_import_plugin('overlay'))
        layout_btns.addWidget(btn_imp_overlay)
        btn_imp_indep = QPushButton("[Import Sub-Chart]")
        btn_imp_indep.clicked.connect(lambda: self._on_import_plugin('independent'))
        layout_btns.addWidget(btn_imp_indep)
        layout_btns.addStretch()
        btn_del_plugin = QPushButton("[Delete File]")
        btn_del_plugin.setStyleSheet("color: #ff5555;")
        btn_del_plugin.clicked.connect(self._on_delete_plugin)
        layout_btns.addWidget(btn_del_plugin)
        layout_btns.addStretch()
        self.btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.btn_box.accepted.connect(self.accept); self.btn_box.rejected.connect(self.reject)
        layout_btns.addWidget(self.btn_box)
        self.layout.addLayout(layout_btns, 1)
        self._refresh_plugin_list()

    def _refresh_plugin_list(self):
        self.list_overlays.clear(); self.list_independents.clear()
        ov_dir = os.path.join(self.app_data_dir, 'overlays')
        if os.path.exists(ov_dir):
            files = sorted([f for f in os.listdir(ov_dir) if f.endswith('.py')])
            for f in files:
                item = QListWidgetItem(f)
                item.setData(Qt.ItemDataRole.UserRole, {'name': f, 'type': 'overlay'})
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                checked = f in self.config.get(self.key_overlay, [])
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                self.list_overlays.addItem(item)
        ind_dir = os.path.join(self.app_data_dir, 'indicators')
        if os.path.exists(ind_dir):
            files = [f for f in os.listdir(ind_dir) if f.endswith('.py')]
            saved_order = self.config.get(self.key_indep, []); ordered_files = []
            for saved_f in saved_order:
                if saved_f in files: ordered_files.append(saved_f)
            remaining = sorted(list(set(files) - set(ordered_files)))
            ordered_files.extend(remaining)
            for f in ordered_files:
                item = QListWidgetItem(f)
                item.setData(Qt.ItemDataRole.UserRole, {'name': f, 'type': 'independent'})
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
                checked = f in saved_order
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                self.list_independents.addItem(item)

    def _on_import_plugin(self, ptype):
        files, _ = QFileDialog.getOpenFileNames(self, "Import Python Script", "", "Python Files (*.py)")
        if not files: return
        target_dir = os.path.join(self.app_data_dir, 'overlays' if ptype == 'overlay' else 'indicators')
        if not os.path.exists(target_dir): os.makedirs(target_dir)
        for fpath in files:
            try:
                fname = os.path.basename(fpath)
                shutil.copy(fpath, os.path.join(target_dir, fname))
            except Exception as e: print(f"Import failed: {e}")
        self._refresh_plugin_list()

    def _on_delete_plugin(self):
        item = None; ptype = None
        if self.list_overlays.hasFocus(): item = self.list_overlays.currentItem(); ptype = 'overlay'
        elif self.list_independents.hasFocus(): item = self.list_independents.currentItem(); ptype = 'independent'
        if not item:
            if self.list_overlays.currentItem(): item = self.list_overlays.currentItem(); ptype = 'overlay'
            elif self.list_independents.currentItem(): item = self.list_independents.currentItem(); ptype = 'independent'
        if not item: QMessageBox.information(self, "Info", "Please select an item to delete."); return
        data = item.data(Qt.ItemDataRole.UserRole); fname = data['name']
        if QMessageBox.question(self, "Confirm Delete", f"Delete {fname} permanently?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            target_dir = os.path.join(self.app_data_dir, 'overlays' if ptype == 'overlay' else 'indicators')
            full_path = os.path.join(target_dir, fname)
            try:
                if os.path.exists(full_path): os.remove(full_path)
                self._refresh_plugin_list()
            except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def apply_changes(self):
        new_overlays = []; new_indeps = []
        for i in range(self.list_overlays.count()):
            item = self.list_overlays.item(i)
            if item.checkState() == Qt.CheckState.Checked: new_overlays.append(item.data(Qt.ItemDataRole.UserRole)['name'])
        for i in range(self.list_independents.count()):
            item = self.list_independents.item(i)
            if item.checkState() == Qt.CheckState.Checked: new_indeps.append(item.data(Qt.ItemDataRole.UserRole)['name'])
        self.config[self.key_overlay] = new_overlays
        self.config[self.key_indep] = new_indeps
        save_config(self.config, CONFIG_FILE)

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About SATIN")
        self.resize(400, 300)
        layout = QVBoxLayout(self)
        title = QLabel("Scalable Algorithmic Trading Interface Nexus(SATIN)")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = title.font(); font.setPointSize(14); font.setBold(True); title.setFont(font)
        layout.addWidget(title)
        layout.addWidget(QLabel("Version: V2.9-010 (Stable)"))
        layout.addWidget(QLabel("Core: Python, Shioaji, ZeroMQ"))
        layout.addWidget(QLabel("GUI: PyQt6, PyQtGraph"))
        layout.addWidget(QLabel("\\nDeveloper: LinusHSAO & AI Assistant"))
        disclaimer = QLabel("\\n[Disclaimer]\\nThis software is for educational and research purposes only. \\nUse at your own risk.")
        disclaimer.setWordWrap(True); disclaimer.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(disclaimer)
        layout.addStretch()
        btn_ok = QPushButton("Close"); btn_ok.clicked.connect(self.accept); layout.addWidget(btn_ok)

class NewProjectDialog(QDialog):
    def __init__(self, default_dir="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Strategy Project")
        self.resize(400, 250)
        
        layout = QVBoxLayout(self)
        
        # --- Form Area ---
        form = QFormLayout()
        
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("e.g. MyAlgo_01")
        form.addRow("Project Name *:", self.txt_name)
        
        self.txt_desc = QTextEdit()
        self.txt_desc.setPlaceholderText("Brief description of your strategy...")
        self.txt_desc.setMaximumHeight(60)
        form.addRow("Description:", self.txt_desc)
        
        # Path Selection (ReadOnly & No Browse)
        self.txt_path = QLineEdit(default_dir)
        self.txt_path.setReadOnly(True) 
        self.txt_path.setPlaceholderText("System managed path...")
        self.txt_path.setStyleSheet("color: gray; background-color: #2e2e2e; border: 1px solid #3e3e3e;")
        
        form.addRow("Target Location (Fixed):", self.txt_path)
        
        layout.addLayout(form)
        
        # --- Hint ---
        lbl_hint = QLabel("This will create a new project in your active workspace with standard templates.")
        lbl_hint.setWordWrap(True)
        lbl_hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(lbl_hint)
        
        layout.addStretch()
        
        # --- Buttons ---
        self.btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.btn_box.accepted.connect(self._validate_and_accept)
        self.btn_box.rejected.connect(self.reject)
        layout.addWidget(self.btn_box)

    def _validate_and_accept(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Project Name is required.")
            self.txt_name.setFocus()
            return
        
        # Basic validation for folder name characters
        if any(c in name for c in r'<>:"/\|?*'):
             QMessageBox.warning(self, "Validation", "Invalid characters in project name.")
             return
             
        self.accept()

    def get_data(self):
        return {
            "name": self.txt_name.text().strip(),
            "description": self.txt_desc.toPlainText().strip(),
            "target_dir": self.txt_path.text().strip()
        }