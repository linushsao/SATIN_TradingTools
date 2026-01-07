# ==============================================================================
# client_gui/plugins/pages/strategies/layout.py
#
# Version: V3.4-008 (Editor Toolbar Extension)
# 更新日期: 2025-12-25
# [修正]: 1.新增 EditorOptionsDialog。2.於 Editor 分頁新增工具列。
# ==============================================================================

import os
import json
import shutil  # [新增] 處理指標腳本匯入的複製操作
import pandas as pd
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, 
    QFrame, QFormLayout, QLineEdit, QComboBox, QDateEdit, 
    QTabWidget, QDialog, QDialogButtonBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QGroupBox, QListWidget, QListWidgetItem, QMessageBox, QToolBar, QFileDialog    
)
# from PyQt6.QtCore import Qt, pyqtSignal, QDate
from PyQt6.QtCore import Qt, pyqtSignal, QDate
from PyQt6.QtGui import QAction
from ui_lib.code_editor import CodeEditor
from ui_lib.charts.static_chart import StaticChartWidget 

class EditorOptionsDialog(QDialog):
    """設定外部編輯器執行檔路徑"""
    def __init__(self, current_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editor Options")
        self.resize(500, 120)
        layout = QFormLayout(self)
        self.txt_path = QLineEdit(current_path)
        btn_browse = QPushButton("...")
        btn_browse.setFixedWidth(30)
        btn_browse.clicked.connect(self._on_browse)
        h_box = QHBoxLayout()
        h_box.addWidget(self.txt_path)
        h_box.addWidget(btn_browse)
        layout.addRow("External Editor Path:", h_box)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)

    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Editor", "", "Executable (*.exe);;All Files (*)")
        if path: self.txt_path.setText(path)

    def get_path(self): return self.txt_path.text().strip()


class StrategiesOptionsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Strategies Options")
        self.resize(320, 240)
        layout = QVBoxLayout(self)
        grp = QGroupBox("Chart Display Settings")
        form = QFormLayout()
        self.spin_bars = QSpinBox()
        self.spin_bars.setRange(10, 5000)
        self.spin_bars.setValue(settings.get('display_limit', 200))
        self.spin_bars.setSuffix(" bars")
        form.addRow("Bars Per Page:", self.spin_bars)
        self.spin_y_width = QSpinBox()
        self.spin_y_width.setRange(20, 300)
        self.spin_y_width.setValue(settings.get('y_axis_width', 45))
        self.spin_y_width.setSuffix(" px")
        form.addRow("Y-Axis Align Width:", self.spin_y_width)
        self.spin_padding = QSpinBox()
        self.spin_padding.setRange(0, 100)
        self.spin_padding.setValue(settings.get('auto_scale_padding', 10))
        self.spin_padding.setSuffix(" %")
        form.addRow("Auto-Scale Padding:", self.spin_padding)
        grp.setLayout(form)
        layout.addWidget(grp)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_settings(self):
        return {
            "display_limit": self.spin_bars.value(),
            "y_axis_width": self.spin_y_width.value(),
            "auto_scale_padding": self.spin_padding.value()
        }

class IndicatorManagerDialog(QDialog):
    def __init__(self, config, app_data_dir, mode='STRATEGY', parent=None):
        super().__init__(parent)
        self.setWindowTitle("指標管理中心")
        self.resize(720, 520)
        self.config = config
        self.app_data_dir = app_data_dir
        
        # 讀取當前配置
        self.active_overlays = set(config.get('strategy_k_bar_plugins', []))
        self.active_independents = config.get('strategy_independent_plots', []) 
        
        self._init_ui()
        self._load_list()

    def _init_ui(self):
        """初始化 UI 佈局：新增匯入策略視圖按鈕"""
        main_layout = QHBoxLayout(self)

        # --- 左側區域 ---
        list_area = QVBoxLayout()
        list_area.addWidget(QLabel("重疊指標 (Overlay) - ★ 表示策略視圖:"))
        self.list_overlays = QListWidget()
        list_area.addWidget(self.list_overlays)
        
        list_area.addWidget(QLabel("副圖指標 (Sub-graph) - 可拖曳排序:"))
        self.list_independents = QListWidget()
        self.list_independents.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.list_independents.setDefaultDropAction(Qt.DropAction.MoveAction)
        list_area.addWidget(self.list_independents)
        
        main_layout.addLayout(list_area, stretch=3)

        # --- 右側區域 ---
        btn_area = QVBoxLayout()
        btn_area.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.btn_import_ov = QPushButton("匯入重疊指標")
        self.btn_import_ov.clicked.connect(lambda: self._import_logic('overlays'))
        
        # [新增] 匯入策略視圖按鈕
        self.btn_import_view = QPushButton("匯入策略視圖")
        self.btn_import_view.setStyleSheet("background-color: #224422; color: white;")
        self.btn_import_view.clicked.connect(self._on_import_strategy_view)
        
        self.btn_import_ind = QPushButton("匯入副圖指標")
        self.btn_import_ind.clicked.connect(lambda: self._import_logic('indicators'))
        
        self.btn_delete = QPushButton("刪除選定指標")
        self.btn_delete.setStyleSheet("background-color: #442222; color: white;")
        self.btn_delete.clicked.connect(self._on_delete)
        
        btn_refresh = QPushButton("重新整理")
        btn_refresh.clicked.connect(self._load_list)

        btn_area.addWidget(self.btn_import_ov)
        btn_area.addWidget(self.btn_import_view) # 放置於重疊指標下方
        btn_area.addWidget(self.btn_import_ind)
        btn_area.addWidget(self.btn_delete)
        btn_area.addSpacing(15)
        btn_area.addWidget(btn_refresh)
        btn_area.addStretch()
        
        dialog_btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        dialog_btns.accepted.connect(self.accept)
        dialog_btns.rejected.connect(self.reject)
        btn_area.addWidget(dialog_btns)

        main_layout.addLayout(btn_area, stretch=1)

    def _on_import_strategy_view(self):
        """處理策略視圖與核心的同步匯入"""
        import shutil
        # 1. 讓使用者選取視圖檔案
        view_path, _ = QFileDialog.getOpenFileName(
            self, "選取策略視圖 (view.py)", "", "Python Files (view*.py)"
        )
        if not view_path:
            return

        # 2. 檢查同資料夾下是否有策略核心
        src_dir = os.path.dirname(view_path)
        core_path = os.path.join(src_dir, "strategy_core.py")
        
        if not os.path.exists(core_path):
            QMessageBox.critical(
                self, "匯入失敗", 
                "找不到配套的 'strategy_core.py'！\n請確保視圖與核心檔案位於同一個資料夾。"
            )
            return

        # 3. 執行同步匯入至 overlays 目錄
        target_dir = os.path.join(self.app_data_dir, 'overlays')
        os.makedirs(target_dir, exist_ok=True)
        
        try:
            # 複製視圖
            shutil.copy(view_path, os.path.join(target_dir, os.path.basename(view_path)))
            # 複製核心 (隱藏屬性由程式邏輯控制)
            shutil.copy(core_path, os.path.join(target_dir, "strategy_core.py"))
            
            QMessageBox.information(self, "成功", "策略視圖與核心已同步匯入。")
            self._load_list()
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"匯入過程發生異常: {e}")

    def _load_list(self):
        """讀取檔案並過濾隱藏核心，標註策略視圖"""
        self.list_overlays.clear()
        self.list_independents.clear()

        # A. 加載重疊指標
        path_ov = os.path.join(self.app_data_dir, 'overlays')
        if os.path.exists(path_ov):
            files = sorted([f for f in os.listdir(path_ov) if f.endswith(".py")])
            for f in files:
                # [修正]: 隱藏策略核心檔案，不顯示在清單中
                if f == "strategy_core.py":
                    continue
                
                # [修正]: 若檔名包含 view 則視為策略視圖，增加符號標註
                display_name = f"★ {f}" if "view" in f.lower() else f
                
                it = QListWidgetItem(display_name)
                it.setData(Qt.ItemDataRole.UserRole, {'type': 'overlay', 'file': f})
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
                it.setCheckState(Qt.CheckState.Checked if f in self.active_overlays else Qt.CheckState.Unchecked)
                self.list_overlays.addItem(it)

        # B. 加載副圖指標 (維持原邏輯)
        path_ind = os.path.join(self.app_data_dir, 'indicators')
        if os.path.exists(path_ind):
            all_files = set([f for f in os.listdir(path_ind) if f.endswith(".py")])
            ordered = [f for f in self.active_independents if f in all_files]
            remaining = sorted(list(all_files - set(ordered)))
            for f in (ordered + remaining):
                it = QListWidgetItem(f)
                it.setData(Qt.ItemDataRole.UserRole, {'type': 'independent', 'file': f})
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
                it.setCheckState(Qt.CheckState.Checked if f in self.active_independents else Qt.CheckState.Unchecked)
                self.list_independents.addItem(it)

    def _import_logic(self, subdir):
        file_path, _ = QFileDialog.getOpenFileName(self, "選取指標腳本", "", "Python Files (*.py)")
        if file_path:
            target_path = os.path.join(self.app_data_dir, subdir, os.path.basename(file_path))
            try:
                shutil.copy(file_path, target_path)
                self._load_list()
            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"匯入失敗: {e}")

    def _on_delete(self):
        """
        [修正]: 刪除指標邏輯。
        當刪除對象為「策略視圖」(★) 時，一併刪除配套之策略核心檔案。
        """
        it = self.list_overlays.currentItem() or self.list_independents.currentItem()
        if not it:
            QMessageBox.warning(self, "提示", "請先點選清單中的項目。")
            return
            
        data = it.data(Qt.ItemDataRole.UserRole)
        filename = data['file']
        subdir = 'overlays' if data['type'] == 'overlay' else 'indicators'
        path = os.path.join(self.app_data_dir, subdir, filename)
        
        # 判定是否為策略視圖 (Overlay 類型且檔名含 view)
        is_strat_view = (data['type'] == 'overlay' and "view" in filename.lower())
        
        msg = f"確定刪除 {filename}？"
        if is_strat_view:
            msg += "\n\n注意：此為策略組件，將一併刪除配套之 'strategy_core.py'。"

        if QMessageBox.question(self, "刪除", msg) == QMessageBox.StandardButton.Yes:
            try:
                # 1. 執行選定檔案刪除
                if os.path.exists(path):
                    os.remove(path)
                
                # 2. [新增]: 若為策略視圖，聯動刪除策略核心檔案
                if is_strat_view:
                    core_path = os.path.join(self.app_data_dir, subdir, "strategy_core.py")
                    if os.path.exists(core_path):
                        os.remove(core_path)
                
                self._load_list() # 重新整理清單
            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"刪除失敗: {e}")

    def get_selected_indicators(self):
        ovs = [self.list_overlays.item(i).data(Qt.ItemDataRole.UserRole)['file'] 
               for i in range(self.list_overlays.count()) 
               if self.list_overlays.item(i).checkState() == Qt.CheckState.Checked]
        
        # 關鍵：依據目前 UI 上的視覺順序收集副圖清單
        inds = [self.list_independents.item(i).data(Qt.ItemDataRole.UserRole)['file'] 
                for i in range(self.list_independents.count()) 
                if self.list_independents.item(i).checkState() == Qt.CheckState.Checked]
        return ovs, inds

class StrategyConfigForm(QWidget):
    def __init__(self):
        super().__init__()
        self.current_editing_id = None
        self.current_schema = {} # [NEW] 儲存當前規格定義
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0,0,0,0)
        self.grp_basic = QGroupBox("Project Info")
        self.form_basic = QFormLayout()
        self.input_id = QLineEdit(); self.input_id.setReadOnly(True)
        self.input_name = QLineEdit()
        self.form_basic.addRow("ID:", self.input_id)
        self.form_basic.addRow("Name:", self.input_name)
        self.grp_basic.setLayout(self.form_basic)
        self.main_layout.addWidget(self.grp_basic)
        self.grp_params = QGroupBox("Strategy Parameters")
        self.form_params = QFormLayout()
        self.grp_params.setLayout(self.form_params)
        self.main_layout.addWidget(self.grp_params)
        self.dynamic_widgets = {}

    def build_from_schema(self, schema, context_data):
        self.current_schema = schema or {} # 儲存規格供儲存時參考
        while self.form_params.count():
            item = self.form_params.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.dynamic_widgets = {}
        if not schema or not schema.get('properties'):
            lbl = QLabel("⚠️ No parameters defined")
            lbl.setStyleSheet("color: red;")
            self.form_params.addRow(lbl)
            return
        props = schema.get('properties', {})
        for key in props.keys():
            # [修正點]：關鍵過濾邏輯
            # 即使 schema 物件中包含了 'name' (可能來自 plugin.py 的降級回傳), 
            # 這裡也必須跳過，因為 'name' 已經在 self.input_name 處理過了。
            if key.lower() in ['id', 'name']:
                continue            
            details = props[key]
            dtype = details.get('type', 'string')
            ui_type = details.get('x-ui-type', dtype) # 支援自定義 UI 型別
            title = details.get('title', key)
            if 'enum' in details:
                widget = QComboBox()
                for opt in details['enum']:
                    widget.addItem(str(opt))
            elif ui_type == 'dynamic_select': # [NEW] 處理動態來源下拉選單
                widget = QComboBox()
                widget.setEditable(True)
                source_key = details.get('x-source')
                items = context_data.get(source_key, [])
                for it in items:
                    val = it.get('code') if isinstance(it, dict) else str(it)
                    widget.addItem(val)
            elif key == 'account' and 'accounts' in context_data:
                widget = QComboBox()
                for acc in context_data['accounts']:
                    widget.addItem(acc.get('account_id',''))
            elif key == 'contract_code' and 'contracts' in context_data:
                widget = QComboBox()
                widget.setEditable(True)
                for c in context_data['contracts']:
                    widget.addItem(c.get('code',''))
            elif dtype == 'integer':
                widget = QSpinBox()
                widget.setRange(-999999, 999999)
            elif dtype == 'number':
                widget = QDoubleSpinBox()
                widget.setRange(-999999.0, 999999.0)
                widget.setDecimals(4)
            elif dtype == 'boolean':
                widget = QCheckBox()
            else:
                widget = QLineEdit()
            self.form_params.addRow(f"{title}:", widget)
            self.dynamic_widgets[key] = widget

    def set_form_data(self, data):
        self.input_id.setText(str(data.get('id', '')))
        self.input_name.setText(str(data.get('name', '')))
        
        for key, widget in self.dynamic_widgets.items():
            val = data.get(key)
            if val is None: 
                continue
                
            if isinstance(widget, QComboBox):
                idx = widget.findText(str(val))
                if idx >= 0: 
                    widget.setCurrentIndex(idx)
                elif widget.isEditable(): 
                    widget.setCurrentText(str(val))
            elif isinstance(widget, QSpinBox):
                try:
                    widget.setValue(int(float(val)))
                except (ValueError, TypeError):
                    pass
            elif isinstance(widget, QDoubleSpinBox):
                try:
                    widget.setValue(float(val))
                except (ValueError, TypeError):
                    pass
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(val))
            else:
                widget.setText(str(val))

    def get_form_data(self):
        """
        [修正] 類型嚴格轉型：對照 current_schema 進行 cast，確保儲存為正確數值型別
        """
        d = {"id": self.input_id.text(), "name": self.input_name.text()}
        props = self.current_schema.get('properties', {})
        for key, widget in self.dynamic_widgets.items():
            spec = props.get(key, {})
            target_type = spec.get('type', 'string')
            
            if isinstance(widget, QSpinBox): 
                v = widget.value()
            elif isinstance(widget, QDoubleSpinBox): 
                v = widget.value()
            elif isinstance(widget, QCheckBox): 
                v = bool(widget.isChecked())
            elif isinstance(widget, QComboBox): 
                v = widget.currentText()
            else: 
                v = widget.text()
            
            # 根據規格執行轉型
            try:
                if target_type == 'integer': d[key] = int(float(v))
                elif target_type == 'number': d[key] = float(v)
                elif target_type == 'boolean': d[key] = bool(v)
                else: d[key] = str(v)
            except (ValueError, TypeError):
                d[key] = v # 轉換失敗保留原值
        return d

class StrategiesWidget(QWidget):
    sig_preview_data = pyqtSignal(dict)
    sig_request_code_load = pyqtSignal(str)
    sig_save_project = pyqtSignal(dict)
    sig_save_file = pyqtSignal(str, str)
    sig_new_project_req = pyqtSignal()
    sig_delete_project = pyqtSignal(str)
    sig_local_select = pyqtSignal(str)
    sig_refresh = pyqtSignal()
    sig_open_options = pyqtSignal()
    sig_open_indicators = pyqtSignal()
    sig_file_selected = pyqtSignal(str)
    sig_open_external = pyqtSignal() 
    sig_editor_options = pyqtSignal()
    sig_deploy_req = pyqtSignal()
    sig_stop_strategy_req = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.full_df = None
        self.display_limit = 200
        self.current_file_name = None
        self.active_indicators = [] 
        self.indicator_items = []
        self._init_ui()

    def _init_ui(self):
        ly = QHBoxLayout(self)
        split_main = QSplitter(Qt.Orientation.Horizontal)
        split_left = QSplitter(Qt.Orientation.Vertical)
        self.tabs_info = QTabWidget()
        self.tab_config = QWidget()
        v_cfg = QVBoxLayout(self.tab_config)
        self.config_form = StrategyConfigForm()
        v_cfg.addWidget(self.config_form)
        self.btn_save = QPushButton("Save Settings")
        self.btn_save.clicked.connect(lambda: self.sig_save_project.emit(self.config_form.get_form_data()))
        v_cfg.addWidget(self.btn_save)
        v_cfg.addStretch()
        self.tabs_info.addTab(self.tab_config, "Settings")
        self.tab_files = QWidget()
        v_f = QVBoxLayout(self.tab_files)
        self.file_list = QTableWidget()
        self.file_list.setColumnCount(1)
        self.file_list.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.file_list.cellClicked.connect(self._on_f_table_click)
        v_f.addWidget(self.file_list)
        self.tabs_info.addTab(self.tab_files, "Files")
        split_left.addWidget(self.tabs_info)
        self.tabs_manage = QTabWidget()
        self.tab_local = QWidget()
        v_loc = QVBoxLayout(self.tab_local)
        self.table_local = QTableWidget()
        self.table_local.setColumnCount(2)
        self.table_local.setHorizontalHeaderLabels(["ID", "Name"])
        self.table_local.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_local.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_local.cellClicked.connect(self._on_local_table_click)
        v_loc.addWidget(self.table_local)
        self.tabs_manage.addTab(self.tab_local, "Projects")
        split_left.addWidget(self.tabs_manage)
        self.tabs_content = QTabWidget()
        self.tab_chart = QWidget()
        v_chart = QVBoxLayout(self.tab_chart)
        ctrl = QHBoxLayout()
        self.date_s = QDateEdit()
        self.date_s.setCalendarPopup(True)
        self.date_s.setDate(QDate.currentDate().addDays(-30))
        self.date_e = QDateEdit()
        self.date_e.setCalendarPopup(True)
        self.date_e.setDate(QDate.currentDate())
        btn_load = QPushButton("Render")
        btn_load.clicked.connect(self._on_load)
        btn_ind = QPushButton("Indicators")
        btn_ind.clicked.connect(self.sig_open_indicators.emit)
        btn_opt = QPushButton("Options")
        btn_opt.clicked.connect(self.sig_open_options.emit)
        ctrl.addWidget(QLabel("S:"))
        ctrl.addWidget(self.date_s)
        ctrl.addWidget(QLabel("E:"))
        ctrl.addWidget(self.date_e)
        ctrl.addWidget(btn_load)
        ctrl.addWidget(btn_ind)
        ctrl.addStretch()
        ctrl.addWidget(btn_opt)
        v_chart.addLayout(ctrl)
        self.chart_view = StaticChartWidget()
        v_chart.addWidget(self.chart_view)
        self.tabs_content.addTab(self.tab_chart, "Chart")
        self.tab_code = QWidget()
        v_code = QVBoxLayout(self.tab_code)
        #-------------------------
        
        # --- Toolbar ---
        self.editor_toolbar = QToolBar()
        #---
        # [新增部署按鈕]
        self.act_deploy = QAction("Deploy to Server", self)
        self.act_deploy.setToolTip("將此專案部署並註冊至交易服務")
        self.act_deploy.triggered.connect(self.sig_deploy_req.emit)
        self.editor_toolbar.addAction(self.act_deploy)
        self.editor_toolbar.addSeparator() 
        #---
        # [新增停止按鈕]
        self.act_stop = QAction("Stop Strategy", self)
        self.act_stop.setToolTip("停止目前正在伺服器端執行的策略實例")
        self.act_stop.triggered.connect(self._on_stop_req)
        self.editor_toolbar.addAction(self.act_stop)
        self.editor_toolbar.addSeparator()

        self.act_deploy = QAction("Deploy to Server", self)        
        #---
        self.act_open_ext = QAction("External Editor", self)
        self.act_open_ext.triggered.connect(self.sig_open_external.emit)
        self.editor_toolbar.addAction(self.act_open_ext)
        self.editor_toolbar.addSeparator()
        self.act_ed_opt = QAction("options", self)
        self.act_ed_opt.triggered.connect(self.sig_editor_options.emit)
        self.editor_toolbar.addAction(self.act_ed_opt)
        v_code.addWidget(self.editor_toolbar)
        
        #-------------------------
        self.code_editor = CodeEditor()
        self.code_editor.sig_changed.connect(self._on_editor_dirty_changed)     
        self.code_editor.sig_save_request.connect(self._on_save_f)   
        v_code.addWidget(self.code_editor)
        self.btn_save_f = QPushButton("Save File")
        self.btn_save_f.clicked.connect(self._on_save_f)
        v_code.addWidget(self.btn_save_f)
        self.tabs_content.addTab(self.tab_code, "Editor")
        split_main.addWidget(split_left)
        split_main.addWidget(self.tabs_content)
        split_main.setStretchFactor(1, 3)
        ly.addWidget(split_main)

    def _on_local_table_click(self, r, c):
        it = self.table_local.item(r, 0)
        if it:
            self.sig_local_select.emit(it.text())
            
    def _on_editor_dirty_changed(self, is_dirty):
        if is_dirty:
            self.btn_save_f.setText("Save File * (Unsaved)")
            self.btn_save_f.setStyleSheet("background-color: #d35400; color: white; font-weight: bold;")
        else:
            self.btn_save_f.setText("Save File")
            self.btn_save_f.setStyleSheet("")

    def _on_f_table_click(self, r, c):
        it = self.file_list.item(r, 0)
        if it:
            f = it.text()
            self.current_file_name = f
            self.sig_file_selected.emit(f)

    def _on_load(self):
        s_str = self.date_s.date().toString("yyyy-MM-dd")
        e_str = self.date_e.date().toString("yyyy-MM-dd")
        self.sig_preview_data.emit({"start": s_str, "end": e_str})
    
    def _on_save_f(self):
        if self.current_file_name:
            content = self.code_editor.get_content()
            self.sig_save_file.emit(self.current_file_name, content)
    
    def load_data(self, df, code="--", freq="1m"):
        """
        [修正] 載入資料至顯示工具，確保 'Date' 欄位被正確保留。
        """
        if df is not None:
            # 標準化欄位名稱
            map_cols = {'open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume'}
            df.rename(columns=lambda x: map_cols.get(x.lower(), x), inplace=True)
            
            # 修正：若 'Date' 已存在則不再強制從索引重置，避免資料遺失
            if 'Date' not in df.columns and not isinstance(df.index, pd.RangeIndex):
                df = df.reset_index().rename(columns={df.index.name: 'Date'})
            else:
                # 僅重置索引位置，不丟棄內容 (drop=True 在此是為了清除重複的 RangeIndex)
                df = df.reset_index(drop=True)
        
        # 更新圖表 HUD 元標籤資訊
        self.chart_view.set_info_meta(code, freq)
        self.full_df = df
        
        # 執行圖表重繪
        self.refresh_chart()
        
    def update_active_indicators(self, ovs, inds):
        """
        [更新]: 接收指標配置。
        ovs: 重疊指標列表 (list)
        inds: 副圖指標列表 (list, 已包含排序資訊)
        """
        # 這裡將順序資訊整合進渲染隊列中，確保重疊指標先畫，副圖指標依序後畫
        self.active_indicators = [(True, f) for f in ovs] + [(False, f) for f in inds]
    def refresh_chart(self):
        """
        [修正]: 修正 K 線圖顯示邏輯。
        依據需求：必須先從頭開始計算指標完畢後，再決定顯示範圍。
        1. 全量載入資料以確保計算上下文完整。
        2. 執行指標渲染。
        3. 最後設定 X 軸顯示範圍。
        """
        if self.full_df is None or self.full_df.empty:
            return

        # 1. 執行完整計算：將完整數據載入圖表視圖，不進行預先切片
        # 這樣可確保 render 過程中 K_BAR_DATA 擁有完整歷史，解決指標計算偏移問題
        self.chart_view.load_dataframe(self.full_df)
        self.indicator_items = []

        # 2. 執行指標渲染：傳入 full_df 進行全量計算
        self._render_active_indicators(self.full_df)

        # 3. 決定顯示範圍：在計算完畢後，依據 display_limit 設定最終可視區間
        limit = self.display_limit
        total_bars = len(self.full_df)

        if total_bars > limit:
            # 計算最後 N 根 K 線的索引範圍 (考慮 PyQtGraph 座標偏移量 0.5)
            start_idx = total_bars - limit
            self.chart_view.p_main.setXRange(start_idx - 0.5, total_bars - 0.5, padding=0)
        else:
            # 若資料筆數不足，則顯示全部
            self.chart_view.p_main.setXRange(-0.5, total_bars - 0.5, padding=0)

    def _render_active_indicators(self, df):
        if not self.chart_view.exec_plugin_callback:
            return
        v = {'K_BAR_DATA': df, 'pd': pd, 'np': np, 'ADDPLOT_CONFIG': []}
        for is_ov, f in self.active_indicators:
            try:
                self.chart_view.exec_plugin_callback(f, v, None, self.indicator_items, is_overlay=is_ov)
            except Exception as e:
                print(f"Render Error: {e}")
                
    def _on_stop_req(self):
        """觸發停止請求，帶入目前的專案 ID"""
        pid = self.config_form.current_editing_id
        if pid:
            self.sig_stop_strategy_req.emit(str(pid))                