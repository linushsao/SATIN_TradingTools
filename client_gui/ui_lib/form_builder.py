# ==============================================================================
# client_gui/ui_lib/form_builder.py
#
# Version: V1.1-000 (ReadOnly Support)
# 更新日期: 2025-12-13
# 描述:     動態表單建構器。
#           [修正]: 支援 field schema 中的 'readonly' 屬性。
# ==============================================================================

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QGroupBox, 
                             QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, 
                             QComboBox, QCheckBox, QHBoxLayout, QPushButton)
from PyQt6.QtCore import Qt, pyqtSignal

class DynamicFormBuilder(QWidget):
    """
    通用動態表單元件。
    """
    sig_action_triggered = pyqtSignal(str, str) # key, action_type

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.widgets = {} # key -> widget
        self.schema = {}
        self.context_data = {}

    def build_form(self, schema: dict, context_data: dict = None):
        """
        根據 Schema 建構 UI。
        """
        # Clear existing
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.widgets = {}
        self.schema = schema
        self.context_data = context_data or {}
        
        groups = schema.get('groups', [])
        
        if not groups and 'fields' in schema:
            groups = [{"title": "General", "fields": schema['fields']}]
            
        for group_def in groups:
            group_box = QGroupBox(group_def.get('title', 'Settings'))
            form_layout = QFormLayout(group_box)
            
            for field in group_def.get('fields', []):
                key = field['key']
                label = field.get('label', key)
                widget = self._create_widget(field)
                
                self.widgets[key] = widget
                form_layout.addRow(label, widget)
                
            self.layout.addWidget(group_box)
            
        self.layout.addStretch()

    def _create_widget(self, field):
        dtype = field.get('type', 'string')
        default_val = field.get('default')
        is_readonly = field.get('readonly', False) # [NEW] Readonly flag
        
        widget = None
        
        if dtype == 'boolean':
            widget = QComboBox()
            widget.addItems(["True", "False"])
            is_true = bool(default_val)
            widget.setCurrentIndex(0 if is_true else 1)
            
        elif dtype == 'select':
            widget = QComboBox()
            opts = field.get('options', [])
            widget.addItems(opts)
            if default_val and default_val in opts:
                widget.setCurrentText(default_val)
            
        elif dtype == 'dynamic_select':
            source_key = field.get('source')
            items = self.context_data.get(source_key, [])
            
            widget = QComboBox()
            for item in items:
                if isinstance(item, dict):
                    val = item.get('code') or item.get('account_id') or item.get('id') or str(item)
                    disp = item.get('name') or item.get('username') or val
                    widget.addItem(f"{val} ({disp})", val)
                else:
                    widget.addItem(str(item), str(item))
            
            if key := field.get('key'):
                if key == 'file_name':
                    container = QWidget()
                    l = QHBoxLayout(container); l.setContentsMargins(0,0,0,0)
                    l.addWidget(widget)
                    btn = QPushButton("▶")
                    btn.setFixedWidth(30)
                    btn.setToolTip("Load Script")
                    btn.clicked.connect(lambda: self.sig_action_triggered.emit(key, "load"))
                    # If field implies readonly, disable parts
                    if is_readonly: 
                        widget.setEnabled(False)
                        btn.setEnabled(False)
                    l.addWidget(btn)
                    container.data_widget = widget 
                    return container

        elif dtype == 'integer':
            widget = QSpinBox()
            widget.setRange(field.get('min', -999999), field.get('max', 999999))
            widget.setValue(int(default_val) if default_val is not None else 0)
            
        elif dtype == 'float':
            widget = QDoubleSpinBox()
            widget.setRange(field.get('min', -999999.0), field.get('max', 999999.0))
            widget.setSingleStep(field.get('step', 0.1))
            decimals = 2
            if 'step' in field and isinstance(field['step'], float):
                 if field['step'] < 0.1: decimals = 4
            widget.setDecimals(decimals)
            widget.setValue(float(default_val) if default_val is not None else 0.0)
            
        else: # string or unknown
            widget = QLineEdit()
            if default_val: widget.setText(str(default_val))
            if is_readonly: # [NEW] Apply ReadOnly
                widget.setReadOnly(True)
                widget.setStyleSheet("color: gray; background-color: #f0f0f0;")

        # General ReadOnly handling for non-QLineEdit widgets
        if is_readonly and not isinstance(widget, QLineEdit):
            widget.setEnabled(False)

        return widget

    def get_form_data(self) -> dict:
        data = {}
        for key, widget in self.widgets.items():
            real_widget = getattr(widget, 'data_widget', widget)
            
            if isinstance(real_widget, QComboBox):
                if real_widget.currentData():
                    data[key] = real_widget.currentData()
                else:
                    txt = real_widget.currentText()
                    if "(" in txt: txt = txt.split("(")[0].strip()
                    if txt == "True": data[key] = True
                    elif txt == "False": data[key] = False
                    else: data[key] = txt
                    
            elif isinstance(real_widget, (QSpinBox, QDoubleSpinBox)):
                data[key] = real_widget.value()
            elif isinstance(real_widget, QLineEdit):
                data[key] = real_widget.text()
                
        return data

    def set_form_data(self, data: dict):
        for key, val in data.items():
            if key in self.widgets:
                widget = self.widgets[key]
                real_widget = getattr(widget, 'data_widget', widget)
                
                if isinstance(real_widget, QComboBox):
                    idx = real_widget.findData(val)
                    if idx < 0:
                        txt = str(val)
                        if isinstance(val, bool): txt = "True" if val else "False"
                        idx = real_widget.findText(txt, Qt.MatchFlag.MatchStartsWith)
                    if idx >= 0: real_widget.setCurrentIndex(idx)
                    
                elif isinstance(real_widget, (QSpinBox, QDoubleSpinBox)):
                    real_widget.setValue(val)
                elif isinstance(real_widget, QLineEdit):
                    real_widget.setText(str(val))