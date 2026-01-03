# ==============================================================================
# client_gui/ui_lib/role_manager_dialog.py
#
# Version: V1.7-002 (UI Polish)
# 更新日期: 2025-12-12
# 描述:     角色與身分管理員。
#           [修正]: 美化使用者列表的 Actions 按鈕 (圓角、Hover 效果、標準化尺寸)。
# ==============================================================================

import os
import shutil
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, 
                             QLabel, QLineEdit, QPushButton, QFileDialog, 
                             QMessageBox, QFormLayout, QTabWidget, QTableWidget,
                             QTableWidgetItem, QHeaderView, QAbstractItemView, 
                             QInputDialog, QWidget, QDialogButtonBox, QMenu)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QAction

from shared.security_utils import load_private_key_obj, generate_key_pair, get_public_key_from_private
from shared.profile_manager import ProfileManager

class EditProfileDialog(QDialog):
    """使用者編輯中繼資料對話框"""
    def __init__(self, user_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Profile: {user_data['id']}")
        self.resize(400, 250)
        self.data = user_data
        
        layout = QFormLayout(self)
        
        # 1. Nickname
        self.txt_nick = QLineEdit(self.data.get('nickname', self.data['id']))
        self.txt_nick.setPlaceholderText("Display Name")
        layout.addRow("Nickname:", self.txt_nick)

        # 2. Description
        self.txt_desc = QLineEdit(self.data.get('description', ''))
        layout.addRow("Description:", self.txt_desc)
        
        # 3. Avatar Selector
        self.txt_avatar = QLineEdit(self.data.get('avatar_path', ''))
        self.txt_avatar.setReadOnly(False)
        self.txt_avatar.setPlaceholderText("Path to image file (png/jpg)")
        
        btn_browse_avt = QPushButton("...")
        btn_browse_avt.setFixedWidth(30)
        btn_browse_avt.clicked.connect(self._browse_avatar)
        
        h_avt = QHBoxLayout()
        h_avt.addWidget(self.txt_avatar)
        h_avt.addWidget(btn_browse_avt)
        layout.addRow("Avatar:", h_avt)

        if self.data.get('is_admin'):
            lbl_admin = QLabel("[V] Yes (System Admin)")
            lbl_admin.setStyleSheet("color: #f1c40f; font-weight: bold;")
            layout.addRow("Is Admin:", lbl_admin)
        else:
            layout.addRow("Is Admin:", QLabel("[X] No"))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def _browse_avatar(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Avatar Image", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.txt_avatar.setText(path)
        
    def get_data(self):
        return {
            "nickname": self.txt_nick.text().strip(),
            "description": self.txt_desc.text().strip(),
            "avatar_path": self.txt_avatar.text().strip()
        }

class RoleManagerDialog(QDialog):
    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Identity Manager (V1.7-DB)")
        self.resize(950, 600)
        self.context = context
        
        self.profile_manager = ProfileManager()
        
        self.layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        self._init_tab_login()
        self._init_tab_register()
        self.layout.addWidget(self.tabs)
        
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        self.layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)
        
        self._refresh_profile_list()

    def _init_tab_login(self):
        self.tab_login = QWidget()
        layout = QVBoxLayout(self.tab_login)
        
        self.grp_status = QGroupBox("Current Session")
        status_layout = QHBoxLayout(self.grp_status)
        self.lbl_current_user = QLabel("Guest")
        self.lbl_current_user.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        status_layout.addWidget(QLabel("Active User:"))
        status_layout.addWidget(self.lbl_current_user)
        status_layout.addStretch()
        btn_logout = QPushButton("Logout")
        btn_logout.clicked.connect(self._on_logout)
        status_layout.addWidget(btn_logout)
        layout.addWidget(self.grp_status)
        
        layout.addWidget(QLabel("<b>Available Profiles (Double-click to Login):</b>"))
        
        self.table_profiles = QTableWidget()
        self.table_profiles.setColumnCount(6) 
        self.table_profiles.setHorizontalHeaderLabels(["Actions", "User ID", "Nickname", "User Dir", "Description", "Source"])
        self.table_profiles.verticalHeader().setVisible(False)
        self.table_profiles.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_profiles.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        header = self.table_profiles.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) 
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents) 
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents) 
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents) 
        
        self.table_profiles.cellDoubleClicked.connect(self._on_table_double_click)
        layout.addWidget(self.table_profiles)
        
        hbox_actions = QHBoxLayout()
        btn_login = QPushButton("Login / Switch")
        btn_login.setStyleSheet("background-color: #3498db; color: white; font-weight: bold;")
        btn_login.clicked.connect(self._on_login_clicked)
        hbox_actions.addWidget(btn_login)
        
        hbox_actions.addStretch()
        
        self.btn_reset = QPushButton("Factory Reset")
        self.btn_reset.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold;")
        self.btn_reset.clicked.connect(self._on_reset_system)
        self.btn_reset.hide()
        hbox_actions.addWidget(self.btn_reset)
        
        layout.addLayout(hbox_actions)
        
        self.tabs.addTab(self.tab_login, "Login / Switch")

    def _init_tab_register(self):
        self.tab_register = QWidget()
        layout = QVBoxLayout(self.tab_register)
        
        form = QFormLayout()
        
        self.txt_reg_id = QLineEdit()
        self.txt_reg_id.setPlaceholderText("e.g. Trader_Bob")
        form.addRow("User ID *:", self.txt_reg_id)
        
        self.txt_reg_desc = QLineEdit()
        self.txt_reg_desc.setPlaceholderText("(Optional)")
        form.addRow("Description:", self.txt_reg_desc)
        
        self.txt_reg_pass = QLineEdit()
        self.txt_reg_pass.setPlaceholderText("Required: Set password")
        self.txt_reg_pass.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Passphrase *:", self.txt_reg_pass)
        
        dir_layout = QHBoxLayout()
        self.txt_reg_dir = QLineEdit()
        self.txt_reg_dir.setPlaceholderText("Select a workspace directory...")
        self.txt_reg_dir.setReadOnly(True)
        self.btn_browse_dir = QPushButton("[Dir]")
        self.btn_browse_dir.clicked.connect(self._on_browse_dir)
        dir_layout.addWidget(self.txt_reg_dir)
        dir_layout.addWidget(self.btn_browse_dir)
        form.addRow("Workspace *:", dir_layout)
        
        layout.addLayout(form)
        layout.addSpacing(10)
        
        grp_gen = QGroupBox("Method 1: Generate New Key (Save to DB)")
        v_gen = QVBoxLayout(grp_gen)
        btn_gen = QPushButton("Generate & Register")
        btn_gen.clicked.connect(self._on_generate_new)
        v_gen.addWidget(QLabel("Creates a new RSA-2048 key pair and stores it in database."))
        v_gen.addWidget(btn_gen)
        layout.addWidget(grp_gen)
        
        grp_imp = QGroupBox("Method 2: Import Existing Key (Save to DB)")
        v_imp = QVBoxLayout(grp_imp)
        btn_imp = QPushButton("Select .pem File")
        btn_imp.clicked.connect(self._on_import_existing)
        v_imp.addWidget(QLabel("Import an existing private key file into database."))
        v_imp.addWidget(btn_imp)
        layout.addWidget(grp_imp)
        
        layout.addStretch()
        self.tabs.addTab(self.tab_register, "Register / Manage")

    def _on_browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select User Workspace Directory")
        if d:
            self.txt_reg_dir.setText(d)

    def _refresh_profile_list(self):
        self.table_profiles.setRowCount(0)
        
        current_user = self.context.get_current_user()
        is_current_admin = current_user.get('is_admin', False)
        active_id = current_user.get('id')
        has_key = current_user.get('has_key')

        if has_key:
            if is_current_admin:
                self.lbl_current_user.setText(f"{active_id} [Admin]")
                self.lbl_current_user.setStyleSheet("color: #f1c40f; font-weight: bold;")
            else:
                self.lbl_current_user.setText(f"{active_id}")
                self.lbl_current_user.setStyleSheet("color: #2ecc71; font-weight: bold;")
            self.btn_reset.setVisible(is_current_admin)
        else:
            self.lbl_current_user.setText("Guest (No Key)")
            self.lbl_current_user.setStyleSheet("color: #95a5a6;")
            self.btn_reset.setVisible(False)

        profiles = self.profile_manager.get_all_profiles()
        self.table_profiles.setRowCount(len(profiles))
        
        # [NEW] CSS Style for Action Buttons
        btn_base_css = """
            QPushButton {
                color: white; 
                border: none; 
                border-radius: 4px; 
                padding: 2px; 
                font-weight: bold; 
                font-family: 'Segoe UI'; 
                font-size: 11px;
            }
        """
        css_edit = btn_base_css + "QPushButton { background-color: #2980b9; } QPushButton:hover { background-color: #3498db; }"
        css_exp = btn_base_css + "QPushButton { background-color: #8e44ad; } QPushButton:hover { background-color: #9b59b6; }"
        css_del = btn_base_css + "QPushButton { background-color: #c0392b; } QPushButton:hover { background-color: #e74c3c; }"
        
        for i, p in enumerate(profiles):
            pid = p['id']
            # path = p['key_path'] # Not primary anymore
            user_dir = p.get('user_dir', '')
            desc = p['description']
            p_is_admin = p['is_admin']
            nickname = p.get('nickname', pid)
            has_db_key = p.get('has_db_key', False)
            
            # Col 0: Actions
            w_action = QWidget()
            l_action = QHBoxLayout(w_action)
            l_action.setContentsMargins(4, 2, 4, 2)
            l_action.setSpacing(6)
            
            if has_key:
                # Edit Button
                if pid == active_id:
                    btn_edit = QPushButton("Edit")
                    btn_edit.setFixedWidth(55)
                    btn_edit.setStyleSheet(css_edit)
                    btn_edit.clicked.connect(lambda checked, x=p: self._on_edit_profile(x))
                    l_action.addWidget(btn_edit)
                
                # Export Button (If admin or self)
                if pid == active_id or is_current_admin:
                    btn_exp = QPushButton("Export")
                    btn_exp.setFixedWidth(55)
                    btn_exp.setStyleSheet(css_exp)
                    btn_exp.clicked.connect(lambda checked, x=pid: self._on_export_keys(x))
                    l_action.addWidget(btn_exp)

                # Delete Button
                if is_current_admin and pid != active_id:
                    if not p_is_admin: 
                        btn_del = QPushButton("Del")
                        btn_del.setFixedWidth(55)
                        btn_del.setStyleSheet(css_del)
                        btn_del.clicked.connect(lambda checked, x=pid: self._on_delete_profile_by_id(x))
                        l_action.addWidget(btn_del)
                
                if pid == active_id and is_current_admin:
                    pass # Admin cannot delete self
            else:
                l_action.addWidget(QLabel("-"))
            
            self.table_profiles.setCellWidget(i, 0, w_action)

            # Col 1: ID
            id_text = pid
            if p_is_admin: id_text += " [Admin]"
            item_id = QTableWidgetItem(id_text)
            item_id.setData(Qt.ItemDataRole.UserRole, p)
            if has_key and pid == active_id:
                item_id.setForeground(QColor("#3498db")); item_id.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            self.table_profiles.setItem(i, 1, item_id)

            # Col 2: Nickname
            self.table_profiles.setItem(i, 2, QTableWidgetItem(nickname))
            
            # Col 3: User Dir
            self.table_profiles.setItem(i, 3, QTableWidgetItem(user_dir))

            # Col 4: Desc
            self.table_profiles.setItem(i, 4, QTableWidgetItem(desc))

            # Col 5: Source
            src_text = "DB (Secure)" if has_db_key else "File (Legacy)"
            item_src = QTableWidgetItem(src_text)
            if has_db_key: item_src.setForeground(QColor("#27ae60"))
            else: item_src.setForeground(QColor("#e67e22"))
            self.table_profiles.setItem(i, 5, item_src)

    def _on_table_double_click(self, row, col):
        item = self.table_profiles.item(row, 1) 
        if item:
            profile = item.data(Qt.ItemDataRole.UserRole)
            self._perform_login(profile)

    def _on_login_clicked(self):
        row = self.table_profiles.currentRow()
        if row < 0: return
        item = self.table_profiles.item(row, 1)
        if item:
            profile = item.data(Qt.ItemDataRole.UserRole)
            self._perform_login(profile)

    def _perform_login(self, profile_summary):
        """
        [MOD] Login flow supporting DB BLOBs
        """
        pid = profile_summary['id']
        
        # 1. Fetch Full Profile (blobs)
        profile = self.profile_manager.get_profile(pid)
        if not profile: return

        role = profile['default_role']
        is_admin = profile['is_admin']
        user_dir = profile.get('user_dir', '')
        
        key_bytes = profile.get('private_key_blob')
        path = profile.get('key_path', '')
        
        # 2. Check source: DB > File
        source_type = "DB"
        if not key_bytes:
            # Fallback to file
            if os.path.exists(path):
                try:
                    with open(path, 'rb') as f: key_bytes = f.read()
                    source_type = "FILE"
                except: pass
        
        if not key_bytes:
            QMessageBox.critical(self, "Error", f"Private key missing for {pid}.\n(Not in DB, and file path invalid)")
            return

        # 3. Decrypt
        try:
            try:
                key_obj = load_private_key_obj(key_bytes, password=None)
            except TypeError: 
                pwd, ok = QInputDialog.getText(self, "Password Required", 
                                               f"Enter passphrase for {pid} ({source_type}):", 
                                               QLineEdit.EchoMode.Password)
                if not ok: return 
                key_obj = load_private_key_obj(key_bytes, password=pwd)
            except ValueError as ve:
                QMessageBox.critical(self, "Login Failed", f"Invalid key format or password: {ve}")
                return

            self.context.login(pid, role, key_obj, is_admin, user_dir)
            self.profile_manager.set_last_active(pid)
            print(f"[RoleManager] Login success: {pid} (Source: {source_type}). Closing dialog.")
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Login failed: {e}")

    def _on_logout(self):
        self.context.logout()
        self.profile_manager.set_last_active(None)
        self._refresh_profile_list()

    def _on_generate_new(self):
        uid = self.txt_reg_id.text().strip()
        user_dir = self.txt_reg_dir.text().strip()
        pwd = self.txt_reg_pass.text()
        desc = self.txt_reg_desc.text().strip()

        if not uid: QMessageBox.warning(self, "Validation", "User ID is required."); return
        if not pwd: QMessageBox.warning(self, "Validation", "Passphrase is required."); return
        if not user_dir: QMessageBox.warning(self, "Validation", "Workspace directory is required."); return
        
        if self.profile_manager.get_profile(uid):
            QMessageBox.warning(self, "Validation", f"User ID '{uid}' already exists.")
            return
        
        # [MOD] Generate keys in memory and store to DB directly (Also save file for backup/legacy?)
        # Let's save file for backup as per user convention, but rely on DB.
        
        key_dir = os.path.join(user_dir, "key")
        try:
            if not os.path.exists(key_dir): os.makedirs(key_dir)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create key directory:\n{e}")
            return

        filename = f"{uid}_private.pem"
        full_path = os.path.join(key_dir, filename)
        
        try:
            priv, pub = generate_key_pair(password=pwd)
            
            # Save to Disk (Backup)
            with open(full_path, 'wb') as f: f.write(priv)
            pub_path = os.path.join(key_dir, f"{uid}_public.pem")
            with open(pub_path, 'wb') as f: f.write(pub)
            
            # Save to DB (Primary)
            ok, msg = self.profile_manager.add_profile(
                uid, full_path, desc, user_dir, 
                private_key_bytes=priv, 
                public_key_bytes=pub
            )
            
            if ok:
                QMessageBox.information(self, "Success", f"Identity '{uid}' created & stored in DB!\nBackup keys saved to: {key_dir}")
                self.txt_reg_id.clear(); self.txt_reg_pass.clear(); self.txt_reg_desc.clear(); self.txt_reg_dir.clear()
                self._refresh_profile_list()
                self.tabs.setCurrentIndex(0)
            else:
                QMessageBox.critical(self, "DB Error", msg)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_import_existing(self):
        uid = self.txt_reg_id.text().strip()
        user_dir = self.txt_reg_dir.text().strip()
        desc = self.txt_reg_desc.text().strip()

        if not uid: QMessageBox.warning(self, "Validation", "User ID is required."); return
        if not user_dir: QMessageBox.warning(self, "Validation", "Workspace directory is required."); return
            
        path, _ = QFileDialog.getOpenFileName(self, "Select Private Key", "", "PEM Files (*.pem)")
        if not path: return
        
        if self.profile_manager.get_profile(uid):
            if QMessageBox.question(self, "Overwrite", "User ID exists. Overwrite?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return

        # [MOD] Read key bytes
        try:
            with open(path, 'rb') as f: priv_bytes = f.read()
            
            # Try to derive public key (Requires password if encrypted)
            pwd = self.txt_reg_pass.text() # Optional password from UI
            
            pub_bytes = None
            try:
                # Test load to verify password and get public key
                load_private_key_obj(priv_bytes, password=pwd) # Verification
                pub_bytes = get_public_key_from_private(priv_bytes, password=pwd)
            except TypeError:
                # Password incorrect or missing for encrypted key
                 QMessageBox.warning(self, "Password Required", "Key is encrypted. Please enter correct passphrase in 'Passphrase' field to import.")
                 return
            except ValueError:
                 QMessageBox.warning(self, "Invalid Key", "Key password incorrect or format invalid.")
                 return

            # Save to DB
            ok, msg = self.profile_manager.add_profile(
                uid, path, desc, user_dir,
                private_key_bytes=priv_bytes,
                public_key_bytes=pub_bytes
            )
            
            if ok:
                QMessageBox.information(self, "Success", f"Profile '{uid}' imported to DB.")
                self.txt_reg_id.clear(); self.txt_reg_desc.clear(); self.txt_reg_dir.clear(); self.txt_reg_pass.clear()
                self._refresh_profile_list()
                self.tabs.setCurrentIndex(0)
            else:
                QMessageBox.critical(self, "DB Error", msg)
        except Exception as e:
            QMessageBox.critical(self, "File Error", str(e))

    def _on_export_keys(self, target_id):
        """[NEW] Export keys from DB to file"""
        profile = self.profile_manager.get_profile(target_id)
        if not profile: return
        
        menu = QMenu(self)
        act_priv = QAction("Export Private Key", self)
        act_pub = QAction("Export Public Key", self)
        menu.addAction(act_priv)
        menu.addAction(act_pub)
        
        action = menu.exec(self.cursor().pos())
        if not action: return
        
        is_private = (action == act_priv)
        blob = profile.get('private_key_blob') if is_private else profile.get('public_key_blob')
        
        if not blob:
            QMessageBox.warning(self, "No Data", "Key data not found in DB (Legacy profile?).")
            return
            
        # Security Check for Private Key Export
        if is_private:
            pwd, ok = QInputDialog.getText(self, "Security Check", "Enter passphrase to verify export:", QLineEdit.EchoMode.Password)
            if not ok: return
            try:
                load_private_key_obj(blob, password=pwd)
            except:
                QMessageBox.critical(self, "Access Denied", "Incorrect passphrase.")
                return

        default_name = f"{target_id}_private.pem" if is_private else f"{target_id}_public.pem"
        path, _ = QFileDialog.getSaveFileName(self, "Save Key", default_name, "PEM Files (*.pem)")
        if path:
            try:
                with open(path, 'wb') as f: f.write(blob)
                QMessageBox.information(self, "Success", f"Key exported to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _on_delete_profile_by_id(self, target_id):
        if QMessageBox.question(self, "Confirm Delete", f"Remove profile '{target_id}'?\n(Files will NOT be deleted)", 
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.profile_manager.delete_profile(target_id)
            self._refresh_profile_list()

    def _on_edit_profile(self, user_data):
        dlg = EditProfileDialog(user_data, self)
        if dlg.exec():
            data = dlg.get_data()
            ok, msg = self.profile_manager.update_profile_meta(
                user_data['id'], 
                data['description'],
                nickname=data['nickname'],
                avatar_path=data['avatar_path']
            )
            if ok:
                self._refresh_profile_list()
            else:
                QMessageBox.critical(self, "Update Failed", msg)

    def _on_reset_system(self):
        current_user = self.context.get_current_user()
        if not current_user.get('is_admin', False): return
        if QMessageBox.warning(self, "SYSTEM RESET", "Wipe ALL profiles?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            pwd, ok = QInputDialog.getText(self, "Verify", "Enter passphrase:", QLineEdit.EchoMode.Password)
            if not ok: return
            profile = self.profile_manager.get_profile(current_user['id'])
            try:
                # Try DB blob first
                blob = profile.get('private_key_blob')
                if blob:
                    load_private_key_obj(blob, password=pwd)
                else:
                    # Fallback
                    with open(profile['key_path'], 'rb') as f: key_bytes = f.read()
                    load_private_key_obj(key_bytes, password=pwd)
                
                self.profile_manager.reset_all()
                self.context.logout()
                QMessageBox.information(self, "Reset Complete", "System reset.")
                self._refresh_profile_list()
            except Exception as e: QMessageBox.critical(self, "Failed", str(e))