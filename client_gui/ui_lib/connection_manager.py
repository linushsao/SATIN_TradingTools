# ==============================================================================
# client_gui/ui_lib/connection_manager.py
#
# Version: V2.5-002 (Clean Symbols)
# 更新日期: 2025-12-12
# 描述:     服務連線管理員 (UI Component)。
#           [修正]: 移除 Unicode Emoji 特殊符號。
# ==============================================================================

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                             QFormLayout, QLabel, QLineEdit, QSpinBox, 
                             QPushButton, QListWidget, QListWidgetItem,
                             QMessageBox, QDialog, QDialogButtonBox, QCheckBox,
                             QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView)
from PyQt6.QtCore import Qt, pyqtSignal

from shared.config_manager import save_config, CONFIG_FILE

class ServiceEditDialog(QDialog):
    """編輯單一服務節點的對話框"""
    def __init__(self, service_data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Service Node")
        self.resize(300, 250)
        self.data = service_data or {}
        
        layout = QFormLayout(self)
        
        self.inp_name = QLineEdit(self.data.get('name', 'New Service'))
        layout.addRow("Name:", self.inp_name)
        
        self.inp_host = QLineEdit(self.data.get('host', '127.0.0.1'))
        layout.addRow("Host:", self.inp_host)
        
        self.inp_rep = QSpinBox(); self.inp_rep.setRange(1, 65535)
        self.inp_rep.setValue(int(self.data.get('rep_port', 5557)))
        layout.addRow("REP Port (Cmd):", self.inp_rep)
        
        self.inp_pub = QSpinBox(); self.inp_pub.setRange(0, 65535)
        self.inp_pub.setValue(int(self.data.get('pub_port', 0)))
        layout.addRow("PUB Port (Sub):", self.inp_pub)
        
        self.chk_auto = QCheckBox("Auto Connect")
        self.chk_auto.setChecked(self.data.get('auto_connect', True))
        layout.addRow("", self.chk_auto)
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        
    def get_data(self):
        return {
            "name": self.inp_name.text(),
            "host": self.inp_host.text(),
            "rep_port": self.inp_rep.value(),
            "pub_port": self.inp_pub.value(),
            "auto_connect": self.chk_auto.isChecked()
        }

class ConnectionManagerWidget(QWidget):
    sig_profile_activated = pyqtSignal(str)

    def __init__(self, context, config, parent=None):
        super().__init__(parent)
        self.context = context
        self.config = config
        self.profiles = self.config.get('service_profiles', {})
        self.current_pid = self.config.get('active_profile_id', 'local_dev')
        
        # Temp storage for editing
        self.editing_services = [] 
        
        self._init_ui()
        self._load_profiles()

    def _init_ui(self):
        self.layout = QHBoxLayout(self)
        
        # --- Left: Profile List ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0,0,0,0)
        
        left_layout.addWidget(QLabel("Profiles"))
        self.list_profiles = QListWidget()
        self.list_profiles.currentItemChanged.connect(self._on_profile_selected)
        left_layout.addWidget(self.list_profiles)
        
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("+"); btn_add.clicked.connect(self._add_profile)
        btn_del = QPushButton("-"); btn_del.clicked.connect(self._del_profile)
        btn_layout.addWidget(btn_add); btn_layout.addWidget(btn_del)
        left_layout.addLayout(btn_layout)
        
        self.layout.addWidget(left_panel, 1)
        
        # --- Right: Service List ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0,0,0,0)
        
        self.grp_details = QGroupBox("Services in Profile")
        v_box = QVBoxLayout(self.grp_details)
        
        # Service Table
        self.table_services = QTableWidget()
        self.table_services.setColumnCount(4)
        self.table_services.setHorizontalHeaderLabels(["Name", "Host", "Port (REP/PUB)", "Auto"])
        self.table_services.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_services.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_services.doubleClicked.connect(self._edit_service)
        v_box.addWidget(self.table_services)
        
        # Service Actions
        svc_btn_layout = QHBoxLayout()
        btn_add_svc = QPushButton("Add Service"); btn_add_svc.clicked.connect(self._add_service)
        btn_edit_svc = QPushButton("Edit"); btn_edit_svc.clicked.connect(self._edit_service)
        btn_del_svc = QPushButton("Remove"); btn_del_svc.clicked.connect(self._del_service)
        svc_btn_layout.addWidget(btn_add_svc); svc_btn_layout.addWidget(btn_edit_svc); svc_btn_layout.addWidget(btn_del_svc)
        v_box.addLayout(svc_btn_layout)
        
        right_layout.addWidget(self.grp_details)
        
        # Bottom Actions
        action_layout = QHBoxLayout()
        self.btn_test = QPushButton("[Test All]")
        self.btn_test.clicked.connect(self._on_test_connection)
        
        self.btn_save = QPushButton("[Save]")
        self.btn_save.clicked.connect(self._on_save)
        
        self.btn_connect = QPushButton("[Activate]")
        self.btn_connect.setStyleSheet("background-color: #d35400; color: white; font-weight: bold;")
        self.btn_connect.clicked.connect(self._on_activate)
        
        action_layout.addWidget(self.btn_test)
        action_layout.addWidget(self.btn_save)
        action_layout.addWidget(self.btn_connect)
        right_layout.addLayout(action_layout)
        
        self.lbl_result = QLabel("")
        self.lbl_result.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self.lbl_result)
        
        self.layout.addWidget(right_panel, 3)

    def _load_profiles(self):
        self.list_profiles.clear()
        for pid, pdata in self.profiles.items():
            name = pdata.get('name', pid)
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, pid)
            self.list_profiles.addItem(item)
            if pid == self.current_pid:
                self.list_profiles.setCurrentItem(item)

    def _on_profile_selected(self, current, previous):
        if not current: return
        pid = current.data(Qt.ItemDataRole.UserRole)
        profile_data = self.profiles.get(pid, {})
        self.current_editing_pid = pid
        
        # Load services
        self.editing_services = profile_data.get('services', [])
        self._refresh_service_table()
        self.lbl_result.setText("")

    def _refresh_service_table(self):
        self.table_services.setRowCount(0)
        self.table_services.setRowCount(len(self.editing_services))
        for i, s in enumerate(self.editing_services):
            self.table_services.setItem(i, 0, QTableWidgetItem(s.get('name')))
            self.table_services.setItem(i, 1, QTableWidgetItem(s.get('host')))
            
            ports = f"{s.get('rep_port')}"
            if s.get('pub_port'): ports += f" / {s.get('pub_port')}"
            self.table_services.setItem(i, 2, QTableWidgetItem(ports))
            
            auto = "Yes" if s.get('auto_connect') else "No"
            self.table_services.setItem(i, 3, QTableWidgetItem(auto))

    def _add_service(self):
        dlg = ServiceEditDialog(parent=self)
        if dlg.exec():
            self.editing_services.append(dlg.get_data())
            self._refresh_service_table()

    def _edit_service(self):
        row = self.table_services.currentRow()
        if row < 0: return
        
        svc_data = self.editing_services[row]
        dlg = ServiceEditDialog(svc_data, parent=self)
        if dlg.exec():
            self.editing_services[row] = dlg.get_data()
            self._refresh_service_table()

    def _del_service(self):
        row = self.table_services.currentRow()
        if row >= 0:
            del self.editing_services[row]
            self._refresh_service_table()

    def _add_profile(self):
        pid = f"profile_{len(self.profiles)+1}"
        self.profiles[pid] = {
            "name": "New Profile",
            "services": []
        }
        self._load_profiles()
        self.list_profiles.setCurrentRow(self.list_profiles.count()-1)

    def _del_profile(self):
        row = self.list_profiles.currentRow()
        if row < 0: return
        pid = self.list_profiles.currentItem().data(Qt.ItemDataRole.UserRole)
        if len(self.profiles) <= 1:
            QMessageBox.warning(self, "Error", "Cannot delete last profile.")
            return
        del self.profiles[pid]
        self._load_profiles()

    def _on_save(self):
        if not hasattr(self, 'current_editing_pid'): return
        
        # Update current profile
        self.profiles[self.current_editing_pid]['services'] = self.editing_services
        self.config['service_profiles'] = self.profiles
        save_config(self.config, CONFIG_FILE)
        QMessageBox.information(self, "Saved", "Configuration saved.")

    def _on_test_connection(self):
        self.lbl_result.setText("Probing...")
        self.repaint()
        
        # Temp profile dict for probing
        temp_profile = {"services": self.editing_services}
        results = self.context.probe_profile(temp_profile)
        
        html = ""
        for name, ok in results.items():
            color = "green" if ok else "red"
            icon = "[OK]" if ok else "[FAIL]"
            html += f"<span style='color:{color}'>{icon} {name}</span>  "
        self.lbl_result.setText(html)

    def _on_activate(self):
        self._on_save()
        success, msg = self.context.activate_profile(self.current_editing_pid)
        if success:
            self.sig_profile_activated.emit(self.current_editing_pid)
            QMessageBox.information(self, "Activated", "Profile activated. Restart required to apply fully.")
        else:
            QMessageBox.critical(self, "Error", msg)

class ConnectionManagerDialog(QDialog):
    def __init__(self, context, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Service Connection Manager (V2.5)")
        self.resize(800, 600)
        layout = QVBoxLayout(self)
        self.widget = ConnectionManagerWidget(context, config)
        self.widget.sig_profile_activated.connect(self.accept)
        layout.addWidget(self.widget)