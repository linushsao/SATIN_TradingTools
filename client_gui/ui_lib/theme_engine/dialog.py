from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QLabel, QColorDialog
from PyQt6.QtCore import pyqtSignal

class ThemeConfigDialog(QDialog):
    theme_updated = pyqtSignal(dict) # 監聽更新信號，實現即時預覽

    def __init__(self, theme_mgr, parent=None):
        super().__init__(parent)
        self.theme_mgr = theme_mgr
        self.setWindowTitle("SATIN 主題配置中心")
        self.resize(400, 500)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        self.theme_list = QListWidget()
        self.theme_list.addItems(self.theme_mgr.all_themes.keys())
        self.theme_list.currentTextChanged.connect(self._on_selection_changed)
        
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("儲存並套用")
        save_btn.clicked.connect(self._save_exit)
        cancel_btn = QPushButton("放棄")
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        
        layout.addWidget(QLabel("選擇預設主題:"))
        layout.addWidget(self.theme_list)
        layout.addLayout(btn_layout)

    def _on_selection_changed(self, name):
        theme = self.theme_mgr.all_themes.get(name)
        if theme:
            self.theme_updated.emit(theme) # 發射更新信號

    def _save_exit(self):
        name = self.theme_list.currentItem().text()
        self.theme_mgr.save_current(name)
        self.accept()