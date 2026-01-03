# ==============================================================================
# client_gui/ui_lib/identity_dialog.py
#
# Version: V1.0-001 (Clean Symbols)
# 更新日期: 2025-12-12
# 描述:     數位身分管理員 (Digital Identity Manager)。
#           [修正]: 移除 Unicode Emoji 特殊符號。
# ==============================================================================

import os
import datetime
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, 
                             QLabel, QLineEdit, QPushButton, QFileDialog, 
                             QMessageBox, QFormLayout, QTextEdit)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from shared.config_manager import save_config, CONFIG_FILE
from shared.security_utils import generate_key_pair, calculate_hash, get_public_key_from_private

class IdentityDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Digital Identity Manager")
        self.resize(500, 450)
        self.config = config
        self.identity_config = self.config.get('identity', {})
        
        self.layout = QVBoxLayout(self)
        
        # --- Section 1: Basic Info ---
        self.grp_info = QGroupBox("User Identity")
        form_info = QFormLayout(self.grp_info)
        
        self.txt_user_id = QLineEdit(self.identity_config.get('developer_id', 'Guest'))
        self.txt_user_id.setPlaceholderText("Enter your unique ID (e.g. Dev_Allen)")
        form_info.addRow("User ID / Handle:", self.txt_user_id)
        
        self.lbl_fingerprint = QLabel("Key Fingerprint: --")
        self.lbl_fingerprint.setStyleSheet("color: gray; font-family: Consolas;")
        form_info.addRow("Current Key:", self.lbl_fingerprint)
        
        self.layout.addWidget(self.grp_info)
        
        # --- Section 2: Key Management ---
        self.grp_key = QGroupBox("Private Key Management")
        vbox_key = QVBoxLayout(self.grp_key)
        
        self.txt_key_path = QLineEdit(self.identity_config.get('private_key_path', ''))
        self.txt_key_path.setReadOnly(True)
        self.txt_key_path.setPlaceholderText("No private key loaded")
        vbox_key.addWidget(QLabel("Private Key Path:"))
        vbox_key.addWidget(self.txt_key_path)
        
        hbox_actions = QHBoxLayout()
        
        btn_gen = QPushButton("Generate New")
        btn_gen.setToolTip("Generate a new RSA-2048 key pair")
        btn_gen.clicked.connect(self._on_generate)
        
        btn_load = QPushButton("Load Existing")
        btn_load.setToolTip("Load an existing .pem private key")
        btn_load.clicked.connect(self._on_load)
        
        hbox_actions.addWidget(btn_gen)
        hbox_actions.addWidget(btn_load)
        vbox_key.addLayout(hbox_actions)
        
        self.layout.addWidget(self.grp_key)
        
        # --- Section 3: Export ---
        self.grp_export = QGroupBox("Public Key Export")
        vbox_export = QVBoxLayout(self.grp_export)
        
        lbl_hint = QLabel("Share your PUBLIC key with the Repo Admin to get write access.\nNEVER share your private key.")
        lbl_hint.setStyleSheet("color: #4ec9b0; font-style: italic;")
        vbox_export.addWidget(lbl_hint)
        
        btn_export = QPushButton("Export Public Key (.pem)")
        btn_export.clicked.connect(self._on_export_public)
        vbox_export.addWidget(btn_export)
        
        self.layout.addWidget(self.grp_export)
        
        # --- Footer ---
        self.layout.addStretch()
        
        hbox_footer = QHBoxLayout()
        btn_save = QPushButton("Save & Close")
        btn_save.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold;")
        btn_save.clicked.connect(self._on_save)
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        
        hbox_footer.addStretch()
        hbox_footer.addWidget(btn_save)
        hbox_footer.addWidget(btn_cancel)
        self.layout.addLayout(hbox_footer)
        
        # Init Check
        self._validate_current_key()

    def _validate_current_key(self):
        path = self.txt_key_path.text()
        if os.path.exists(path) and os.path.isfile(path):
            try:
                with open(path, 'rb') as f:
                    raw = f.read()
                # Simple check and fingerprint
                if b"PRIVATE KEY" in raw:
                    fp = calculate_hash(raw)[:8]
                    self.lbl_fingerprint.setText(f"Fingerprint: {fp} (Valid)")
                    self.lbl_fingerprint.setStyleSheet("color: #2ecc71; font-weight: bold;")
                    return True
            except: pass
        
        self.lbl_fingerprint.setText("Fingerprint: Invalid or Missing")
        self.lbl_fingerprint.setStyleSheet("color: #e74c3c;")
        return False

    def _on_generate(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Directory to Save Private Key")
        if not dir_path: return
        
        user_id = self.txt_user_id.text().strip()
        if not user_id: user_id = "user"
        
        filename = f"{user_id}_private.pem"
        full_path = os.path.join(dir_path, filename)
        
        try:
            priv, pub = generate_key_pair()
            with open(full_path, 'wb') as f:
                f.write(priv)
            
            # Also save public key for convenience
            pub_path = os.path.join(dir_path, f"{user_id}_public.pem")
            with open(pub_path, 'wb') as f:
                f.write(pub)
                
            QMessageBox.information(self, "Success", f"Keys generated!\n\nPrivate: {full_path}\nPublic: {pub_path}\n\nKEEP PRIVATE KEY SAFE!")
            self.txt_key_path.setText(full_path)
            self._validate_current_key()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_load(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Private Key", "", "PEM Files (*.pem);;All Files (*)")
        if path:
            self.txt_key_path.setText(path)
            if not self._validate_current_key():
                QMessageBox.warning(self, "Invalid Key", "The selected file does not appear to be a valid private key.")

    def _on_export_public(self):
        priv_path = self.txt_key_path.text()
        if not os.path.exists(priv_path):
            QMessageBox.warning(self, "Error", "No private key loaded to derive public key from.")
            return
            
        try:
            with open(priv_path, 'rb') as f:
                priv_bytes = f.read()
            
            pub_bytes = get_public_key_from_private(priv_bytes)
            
            save_path, _ = QFileDialog.getSaveFileName(self, "Save Public Key", "public_key.pem", "PEM Files (*.pem)")
            if save_path:
                with open(save_path, 'wb') as f:
                    f.write(pub_bytes)
                QMessageBox.information(self, "Success", f"Public key exported to:\n{save_path}")
                
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not derive public key: {e}")

    def _on_save(self):
        new_id = self.txt_user_id.text().strip()
        if not new_id:
            QMessageBox.warning(self, "Validation", "User ID cannot be empty.")
            return
            
        self.identity_config['developer_id'] = new_id
        self.identity_config['private_key_path'] = self.txt_key_path.text()
        
        # Update main config reference
        self.config['identity'] = self.identity_config
        save_config(self.config, CONFIG_FILE)
        self.accept()