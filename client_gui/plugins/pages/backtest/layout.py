# ==============================================================================
# client_gui/plugins/pages/03_backtest/layout.py
#
# Version: V3.4-005 (Final Corrected Merged)
# 修正說明: 1. 修正 ReportDialog 內容錯位。
#          2. 補齊 BacktestWidget 內的 pw_equity 定義與 Splitter 佈局。
#          3. 確保 refresh_chart 與 show_result 能正確存取雙圖表物件。
# ==============================================================================

import datetime
import os
import sys
import pyqtgraph as pg
import numpy as np
import pandas as pd
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QGroupBox, 
    QFormLayout, QLabel, QComboBox, QDateEdit, QDoubleSpinBox, 
    QTableWidget, QTableWidgetItem, QAbstractItemView, QTabWidget, 
    QPushButton, QDialog, QTextEdit, QHeaderView, QCheckBox, QScrollBar,
    QListWidget, QListWidgetItem, QFileDialog, QDialogButtonBox, QMessageBox # <--- 修正: 補齊缺失元件
)                             
from PyQt6.QtCore import Qt, QDate, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush

# ---  專用於 Backtest 的指標管理對話框 (安插在 BacktestWidget 之前) ---
import shutil

class BacktestIndicatorManager(QDialog):
    def __init__(self, config, app_data_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("指標管理員 (Backtest)")
        self.resize(600, 450)
        self.config = config
        self.app_data_dir = app_data_dir
        self.key_ov = 'backtest_k_bar_plugins'
        self.fixed_item = "view.py" # 固定項
        
        self.layout = QVBoxLayout(self)
        
        # 列表區域
        self.layout.addWidget(QLabel("重疊指標列表 (★ 表示策略專屬視圖):"))
        self.list_widget = QListWidget()
        self.layout.addWidget(self.list_widget)
        
        # 按鈕區域
        btn_layout = QHBoxLayout()
        self.btn_import = QPushButton("匯入指標 (.py)")
        self.btn_import.clicked.connect(self._on_import)
        self.btn_delete = QPushButton("刪除指標")
        self.btn_delete.setStyleSheet("background-color: #442222; color: white;")
        self.btn_delete.clicked.connect(self._on_delete)
        btn_layout.addWidget(self.btn_import)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addStretch()
        self.layout.addLayout(btn_layout)
        
        # 確認按鈕
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)
        
        self._refresh_list()

    def _refresh_list(self):
        self.list_widget.clear()
        active_list = self.config.get(self.key_ov, [])
        
        # 1. 加入固定項 (策略視圖)
        item = QListWidgetItem(f"★ {self.fixed_item} (策略視圖)")
        item.setData(Qt.ItemDataRole.UserRole, {'name': self.fixed_item, 'fixed': True})
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if self.fixed_item in active_list else Qt.CheckState.Unchecked)
        self.list_widget.addItem(item)
        
        # 2. 加入 AppData 中的手動指標
        ov_dir = os.path.join(self.app_data_dir, 'overlays')
        if os.path.exists(ov_dir):
            for f in sorted(os.listdir(ov_dir)):
                # : 增加判斷式排除 self.fixed_item ("view.py")，避免重複顯示
                if f.endswith('.py') and f != "strategy_core.py" and f != self.fixed_item:
                    item = QListWidgetItem(f)
                    item.setData(Qt.ItemDataRole.UserRole, {'name': f, 'fixed': False})
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
                    item.setCheckState(Qt.CheckState.Checked if f in active_list else Qt.CheckState.Unchecked)
                    self.list_widget.addItem(item)

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(self, "選取指標腳本", "", "Python Files (*.py)")
        if path:
            target = os.path.join(self.app_data_dir, 'overlays', os.path.basename(path))
            shutil.copy(path, target)
            self._refresh_list()

    def _on_delete(self):
        item = self.list_widget.currentItem()
        if not item: return
        data = item.data(Qt.ItemDataRole.UserRole)
        if data.get('fixed'):
            QMessageBox.warning(self, "禁止刪: 策略視圖為核心組件，不可刪除。")
            return
        if QMessageBox.question(self, "刪除", f"確定刪除 {data['name']}？") == QMessageBox.StandardButton.Yes:
            os.remove(os.path.join(self.app_data_dir, 'overlays', data['name']))
            self._refresh_list()

    def _on_accept(self):
        selected = []
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                selected.append(it.data(Qt.ItemDataRole.UserRole)['name'])
        self.config[self.key_ov] = selected
        from shared.config_manager import save_config
        save_config(self.config)
        self.accept()

class CandlestickItem(pg.GraphicsObject):
    def __init__(self, data):
        super().__init__()
        self.data = data  # format: [idx, open, high, low, close]
        self.generatePicture()

    def generatePicture(self):
        self.picture = pg.QtGui.QPicture()
        p = QPainter(self.picture)
        
        w = 0.4  
        
        for t, open, high, low, close in self.data:
            color = QColor('#e74c3c') if close >= open else QColor('#2ecc71')
            
            pen = QPen(color, 1)
            pen.setCosmetic(True) 
            p.setPen(pen)
            p.setBrush(QBrush(color))
            
            p.drawLine(pg.QtCore.QPointF(t, low), pg.QtCore.QPointF(t, high))
            
            if open == close:
                # 若平盤，畫一條橫線避免看不見
                p.drawLine(pg.QtCore.QPointF(t - w/2, open), pg.QtCore.QPointF(t + w/2, open))
            else:
                p.drawRect(pg.QtCore.QRectF(t - w/2, open, w, close - open))
        p.end()

    def paint(self, p, *args):
        p.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return pg.QtCore.QRectF(self.picture.boundingRect())

class TimeAxisItem(pg.AxisItem):
    """
    自定義時間座標軸，將整數索引轉換為 HHMM 格式。
    """
    def __init__(self, orientation, parent_widget, *args, **kwargs):
        super().__init__(orientation, *args, **kwargs)
        self.parent_widget = parent_widget

    def tickStrings(self, values, scale, spacing):
        """[偵錯強化版]: 輸出 time_labels 的 head 與 tail 以確認資料可存取性"""
        if not self.parent_widget:
            return super().tickStrings(values, scale, spacing)
            
        time_labels = getattr(self.parent_widget, 'time_labels', [])
        
        # [偵錯訊息]: 顯示清單的 head (前5項) 和 tail (後5項)
        if time_labels:
            head = time_labels[:5]
            tail = time_labels[-5:]
        else:
            return super().tickStrings(values, scale, spacing)

        labels = []
        for v in values:
            # 使用 round 處理索引偏差
            idx = int(round(v))
            if 0 <= idx < len(time_labels):
                labels.append(time_labels[idx])
            else:
                labels.append("") 
        return labels

class ChartSettingsDialog(QDialog):
    """
    用於控制圖層顯示/隱藏，以及設定分頁 K 棒根數。
    """
    def __init__(self, layers_dict, visible_bars, parent=None):
        super().__init__(parent)
        self.setWindowTitle("圖表設置")
        self.setMinimumWidth(300)
        self.layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        
        # --- 分頁 1: 圖層控制 ---
        self.tab_layers = QWidget()
        self.layers_layout = QVBoxLayout(self.tab_layers)
        self.layers_layout.addWidget(QLabel("勾選以顯示/隱藏圖層:"))
        
        self.checkboxes = {}
        for layer_name, item in layers_dict.items():
            cb = QCheckBox(layer_name)
            cb.setChecked(item.isVisible())
            cb.stateChanged.connect(lambda state, name=layer_name: self._on_layer_toggle(name, state))
            self.layers_layout.addWidget(cb)
            self.checkboxes[layer_name] = cb
            
        self.layers_layout.addStretch()
        self.tabs.addTab(self.tab_layers, "圖層控制")
        
        # --- 分頁 2: 一般設定 ---
        self.tab_general = QWidget()
        self.gen_layout = QFormLayout(self.tab_general)
        self.spin_bars = QDoubleSpinBox() # 使用 SpinBox 設定根數
        self.spin_bars.setRange(10, 5000)
        self.spin_bars.setDecimals(0)
        self.spin_bars.setValue(visible_bars)
        self.gen_layout.addRow("每頁顯示 K 棒根數:", self.spin_bars)
        self.tabs.addTab(self.tab_general, "一般設定")
        
        # 確認按鈕
        self.btn_ok = QPushButton("確定")
        self.btn_ok.clicked.connect(self.accept)
        self.layout.addWidget(self.btn_ok)

    def _on_layer_toggle(self, name, state):
        # 這裡會由父視窗的字典引用的物件直接控制可見性
        pass

    def get_visible_bars(self):
        return int(self.spin_bars.value())

class ReportDialog(QDialog):
    """
    : 恢復正確的報告彈窗顯示邏輯。
    """
    def __init__(self, task_id, report_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"資料解析報告 - Task: {task_id}")
        self.setMinimumSize(600, 500)
        layout = QVBoxLayout(self)
        
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(report_text)
        text_edit.setStyleSheet("font-family: 'Consolas', 'Monospace'; font-size: 11px;")
        layout.addWidget(text_edit)
        
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

class BacktestWidget(QWidget):
    # --- [1. 類別信號宣告] ---
    sig_refresh = pyqtSignal()
    sig_run_task = pyqtSignal(str)
    sig_stop_task = pyqtSignal(str)
    sig_download_result = pyqtSignal(str)
    sig_remove_import = pyqtSignal(str)
    sig_show_result = pyqtSignal(str) 
    sig_config_indicators = pyqtSignal()
    sig_import_selected = pyqtSignal(str)
    sig_save_settings = pyqtSignal() # 儲存設定信號
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.context = None 
        self.exec_plugin_callback = None 
        self.current_edit_id = None
        self.last_result_data = None
        self.time_labels = []
        
        self.layout = QHBoxLayout(self)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.layout.addWidget(self.splitter)

        self.chart_layers = {}   
        self.visible_bars = 200   
        
        self.layer_visibility_states = {
            "K棒": True,
            "價位線": False
        }        
        #圖層控制與分頁參數初始化 ---
        self.chart_layers = {}   # 格式: {"圖層名稱": pg_item_object}
        self.visible_bars = 200  # 預設每頁 200 根
        
        # --- Left Panel: 控制區域 ---
        self.control_panel = QWidget()
        self.control_layout = QVBoxLayout(self.control_panel)
        
        self.grp_settings = QGroupBox("Task Settings")
        self.form_layout = QFormLayout(self.grp_settings)
        
        self.lbl_edit_id = QLabel("Select a project below...")
        self.lbl_edit_id.setStyleSheet("font-weight: bold; color: #4ec9b0;")
        
        self.combo_strategy = QComboBox() 
        self.combo_contract = QComboBox(); self.combo_contract.setEditable(True)
        self.combo_freq = QComboBox(); self.combo_freq.addItems(['1', '5', '15', '30', '60']); self.combo_freq.setCurrentText('15')
        self.date_start = QDateEdit(QDate.currentDate().addDays(-30)); self.date_start.setCalendarPopup(True); self.date_start.setDisplayFormat("yyyy-MM-dd")
        self.date_end = QDateEdit(QDate.currentDate()); self.date_end.setCalendarPopup(True); self.date_end.setDisplayFormat("yyyy-MM-dd")
        self.spin_cash = QDoubleSpinBox(); self.spin_cash.setRange(1.0, 1000000.0); self.spin_cash.setValue(100.0)
        
        self.form_layout.addRow(self.lbl_edit_id)
        self.form_layout.addRow("Project Name:", self.combo_strategy)
        self.form_layout.addRow("Contract:", self.combo_contract)
        self.form_layout.addRow("Frequency (min):", self.combo_freq)
        self.form_layout.addRow("Start Date:", self.date_start)
        self.form_layout.addRow("End Date:", self.date_end)
        self.form_layout.addRow("Init Perf Base:", self.spin_cash)
        
        # 按鈕列：Refresh 與 Save
        self.layout_local_actions = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(lambda: self.sig_refresh.emit())
        self.btn_save = QPushButton("Save")
        self.btn_save.setStyleSheet("background-color: #2d2d2d; color: #4ec9b0; font-weight: bold;")
        self.btn_save.clicked.connect(lambda: self.sig_save_settings.emit())
        
        self.layout_local_actions.addWidget(self.btn_refresh)
        self.layout_local_actions.addWidget(self.btn_save)
        self.form_layout.addRow(self.layout_local_actions)
        
        self.control_layout.addWidget(self.grp_settings)

        # 專案列表
        self.import_widget = QWidget()
        self.import_layout = QVBoxLayout(self.import_widget)
        # ---  在 "Project list" 標籤右方 <Run><Plot><Open> 按鍵 ---
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Project list"))
        header_layout.addStretch()
        
        self.btn_bulk_run = QPushButton("Run")
        self.btn_bulk_plot = QPushButton("Plot")
        self.btn_bulk_open = QPushButton("Open")
        
        # 設定按鍵樣式與連動
        for btn in [self.btn_bulk_run, self.btn_bulk_plot, self.btn_bulk_open]:
            btn.setFixedWidth(50)
            btn.setStyleSheet("QPushButton { font-size: 10px; padding: 2px; }")
            header_layout.addWidget(btn)
            
        self.btn_bulk_run.clicked.connect(self._on_bulk_run)
        self.btn_bulk_plot.clicked.connect(self._on_bulk_plot)
        self.btn_bulk_open.clicked.connect(self._on_bulk_open)
        
        self.import_layout.addLayout(header_layout)
        
        self.table_imports = QTableWidget()
        #  最左邊勾選欄位，並刪除原有的 Run/Plot/DL 欄位
        self.import_cols = ['', 'ID', 'Status']
        self.table_imports.setColumnCount(len(self.import_cols))
        self.table_imports.setHorizontalHeaderLabels(self.import_cols)
        self.table_imports.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table_imports.setColumnWidth(0, 30)  
        #--
        # 【以下這一行】連接點擊信號
        self.table_imports.cellClicked.connect(self._on_import_cell_clicked)

        # 【建議】設定整列選取，優化使用者體驗
        self.table_imports.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_imports.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers) # 禁止直接編輯文字
        #--
        self.import_layout.addWidget(self.table_imports) # : 確保表格顯示在 UI 上        
        # ---  將配置完成的 import_widget 加入左側控制面板佈局，使其正常顯示 ---
        self.control_layout.addWidget(self.import_widget)
        # --- Right Panel: 結果區域 ---
        self.result_panel = QWidget()
        self.result_layout = QVBoxLayout(self.result_panel)
        
        # 1. 先建立 Tab 物件
        self.result_tabs = QTabWidget()
        self.result_layout.addWidget(self.result_tabs)

        # 在 result_tabs 右上角增加設置按鈕 ---
        self.corner_widget = QWidget()
        self.corner_layout = QHBoxLayout(self.corner_widget)
        self.corner_layout.setContentsMargins(0, 0, 5, 0)

        # : 指標管理員按鈕
        self.btn_indicators = QPushButton("📊 指標管理")
        self.btn_indicators.setFixedWidth(80)
        self.btn_indicators.setStyleSheet("QPushButton { border: none; background: transparent; color: #888888; } QPushButton:hover { color: #4ec9b0; }")
        self.btn_indicators.clicked.connect(self.sig_config_indicators.emit)
        self.corner_layout.addWidget(self.btn_indicators)
        
        self.btn_settings = QPushButton("⚙️ 設置")
        self.btn_settings.setFixedWidth(60)
        self.btn_settings.setStyleSheet("QPushButton { border: none; background: transparent; color: #888888; } QPushButton:hover { color: #4ec9b0; }")
        self.btn_settings.clicked.connect(self.on_open_settings)
        self.corner_layout.addWidget(self.btn_settings)
        
        self.result_tabs.setCornerWidget(self.corner_widget, Qt.Corner.TopRightCorner)
        
        # 分頁 1: 圖表 (雙圖層)
        self.tab_chart = QWidget(); self.chart_layout = QVBoxLayout(self.tab_chart)
        self.chart_layout.setContentsMargins(0,0,0,0)
        self.chart_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 必須傳入 axisItems 才能啟用 TimeAxisItem 邏輯
        self.pw_kline = pg.PlotWidget(
            title="Price & Signal View",
            axisItems={'bottom': TimeAxisItem(orientation='bottom', parent_widget=self)}
        )
        # 建立資訊列標籤 (HUD)
        self.info_label = QLabel(self.pw_kline)
        self.info_label.setStyleSheet("""
            QLabel { 
                background-color: rgba(0, 0, 0, 160); 
                color: #FFFFFF; 
                padding: 5px; 
                border-radius: 3px; 
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
            }
        """)
        self.info_label.move(65, 10) 
        self.info_label.setText("No data loaded.")
        # Equity & MDD 繪圖元件與資訊列 ---
        self.pw_equity = pg.PlotWidget(
            title="Equity Curve",
            axisItems={'bottom': TimeAxisItem(orientation='bottom', parent_widget=self)}
        )
        self.info_label_equity = QLabel(self.pw_equity)
        self.info_label_equity.setStyleSheet(self.info_label.styleSheet())
        self.info_label_equity.move(65, 10)
        self.info_label_equity.setText("Equity: --")

        self.pw_mdd = pg.PlotWidget(
            title="Maximum Drawdown",
            axisItems={'bottom': TimeAxisItem(orientation='bottom', parent_widget=self)}
        )
        self.info_label_mdd = QLabel(self.pw_mdd)
        self.info_label_mdd.setStyleSheet(self.info_label.styleSheet())
        self.info_label_mdd.move(65, 10)
        self.info_label_mdd.setText("MDD: --")

        # 座標軸連動與對齊
        self.pw_equity.setXLink(self.pw_kline)
        self.pw_mdd.setXLink(self.pw_kline)
        self.pw_kline.getAxis('left').setWidth(60)
        self.pw_equity.getAxis('left').setWidth(60)
        self.pw_mdd.getAxis('left').setWidth(60)
        
        # 加入 Splitter 確保可動態調整高度
        self.chart_splitter.addWidget(self.pw_kline)
        self.chart_splitter.addWidget(self.pw_equity)
        self.chart_splitter.addWidget(self.pw_mdd)
        # 設定預設比例 (K線 60%, 其他均分 20%)
        self.chart_splitter.setStretchFactor(0, 6) # Index 0: K線
        self.chart_splitter.setStretchFactor(1, 2) # Index 1: 資產曲線
        self.chart_splitter.setStretchFactor(2, 2) # Index 2: 最大回撤
        
        # 設置滑鼠移動監聽代理
        self.proxy_kline = pg.SignalProxy(
            self.pw_kline.scene().sigMouseMoved, 
            rateLimit=60, 
            slot=self._on_mouse_moved
        )
        self.chart_layout.addWidget(self.chart_splitter)
        self.result_tabs.addTab(self.tab_chart, "Performance Chart")

        # 水平捲軸控制項 (Pagination ScrollBar)
        self.scrollbar = QScrollBar(Qt.Orientation.Horizontal)
        self.scrollbar.setFixedHeight(15) # 設定合適高度
        self.scrollbar.setStyleSheet("QScrollBar:horizontal { height: 15px; background: #2d2d2d; }")
        self.scrollbar.valueChanged.connect(self.on_scrollbar_changed)
        self.chart_layout.addWidget(self.scrollbar)
        
        # 分頁 2: 摘要
        self.tab_summary = QWidget(); self.summary_layout = QVBoxLayout(self.tab_summary)
        self.table_metrics = QTableWidget(0, 2)
        self.table_metrics.setHorizontalHeaderLabels(["Metric", "Value"])
        self.table_metrics.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.summary_layout.addWidget(self.table_metrics)
        self.result_tabs.addTab(self.tab_summary, "Result Summary")
        
        self.splitter.addWidget(self.control_panel)
        self.splitter.addWidget(self.result_panel)
        self.splitter.setStretchFactor(0, 3); self.splitter.setStretchFactor(1, 7)

    # --- 功能函式 ---
    def set_context(self, context):
        self.context = context

    def on_open_settings(self):
        """將勾選結果保存至狀態字典，再執行刷新"""
        dlg = ChartSettingsDialog(self.chart_layers, self.visible_bars, self)
        if dlg.exec():
            self.visible_bars = dlg.get_visible_bars()
            
            # 1. 將 Dialog 中的勾選狀態同步回「狀態字典」
            for name, cb in dlg.checkboxes.items():
                self.layer_visibility_states[name] = cb.isChecked()
            
            # 2. 重新執行渲染 (refresh_chart 會依據狀態字典來設定 setVisible)
            self.refresh_chart()

    def update_options(self, strategies, contracts):
        """更新 Task Settings 中的下拉選單選項"""
        # 1. 更新策略下拉選單 (若有提供)
        if strategies:
            self.combo_strategy.clear()
            self.combo_strategy.addItems(strategies)
            
        # 2. 更新合約下拉選單 (Contract)
        if contracts:
            # 記錄當前輸入值，避免被 clear 沖掉
            current_text = self.combo_contract.currentText()
            self.combo_contract.clear()
            
            # 處理 contracts 格式 (支援字串列表或具備 code 鍵的字典列表)
            items = []
            for c in contracts:
                if isinstance(c, dict):
                    # 依據常見 Schema 獲取合約代碼
                    code = c.get('code') or c.get('contract_code')
                    if code: items.append(str(code))
                else:
                    items.append(str(c))
            
            # 過濾重複並排序
            unique_items = sorted(list(set(items)))
            self.combo_contract.addItems(unique_items)
            
            # 恢復原本選取的內容，確保使用者體驗連貫
            if current_text:
                self.combo_contract.setCurrentText(current_text)
                
    def update_imports_table(self, imported_list):
        """: 在 ID 欄位項目中存入 strategy_name 以供 _on_bulk_open 使用"""
        self.table_imports.setRowCount(0)
        for i, item in enumerate(imported_list):
            self.table_imports.insertRow(i)

            # ---  最左邊 "勾選" 欄位項目 ---
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Unchecked)
            self.table_imports.setItem(i, 0, chk_item)
            
            pid = str(item.get('id', 'Unknown'))
            id_item = QTableWidgetItem(pid)
            
            # : 將專案名稱 (策略名稱) 存入 UserRole，確保開啟資料夾時能精準對應磁碟目錄
            strategy_name = item.get('name', pid)
            id_item.setData(Qt.ItemDataRole.UserRole, strategy_name)
            
            self.table_imports.setItem(i, 1, id_item) # ID 移至索引 1
            
            status = item.get('status', 'Ready')
            item_status = QTableWidgetItem(status)
            if "RUNNING" in status: item_status.setForeground(QColor("#f1c40f"))
            elif status == "FINISHED": item_status.setForeground(QColor("#2ecc71"))
            self.table_imports.setItem(i, 2, item_status) # Status 移至索引 2

    def show_result(self, data):
        """確保時間標籤更新後，強制觸發座標軸重繪"""
        if not data: return
        self.last_result_data = data
        
        fd = data.get('full_data', {})
        raw_times = fd.get('datetime_index', [])
        self.time_labels = []
        
        for t in raw_times:
            try:
                dt = pd.to_datetime(t)
                self.time_labels.append(dt.strftime('%H%M'))
            except:
                self.time_labels.append(str(t))

        # [關鍵]: 強制讓兩個 PlotWidget 的 X 軸更新，清除內部快取
        self.pw_kline.getAxis('bottom').update()
        self.pw_equity.getAxis('bottom').update()
        self.pw_mdd.getAxis('bottom').update() # : 強制 MDD 軸重繪

        summary = data.get('performance_summary', {})
        metrics = [
            ("Total Return", f"{summary.get('total_return', 0):.2%}"),
            ("Max Drawdown", f"{summary.get('max_drawdown', 0):.2%}"),
            ("Volatility", f"{summary.get('volatility', 0):.2%}"),
            ("Sharpe", f"{summary.get('sharpe_ratio', 0):.2f}"),
            ("Run Time", data.get('timestamp', 'N/A'))
        ]
        self.table_metrics.setRowCount(len(metrics))
        for i, (k, v) in enumerate(metrics):
            self.table_metrics.setItem(i, 0, QTableWidgetItem(k))
            self.table_metrics.setItem(i, 1, QTableWidgetItem(v))
        
        self.refresh_chart()

        total_bars = len(fd.get('Close', []))
        if total_bars > self.visible_bars:
            self.scrollbar.setMinimum(0)
            self.scrollbar.setMaximum(total_bars - self.visible_bars)
            self.scrollbar.setPageStep(self.visible_bars)
            self.scrollbar.setValue(total_bars - self.visible_bars)
        else:
            self.scrollbar.setMaximum(0)        
        # 靜態數據載入完成後，預設顯示回測範圍最後一筆數據
        total_bars = len(fd.get('Close', []))
        if total_bars > 0:
            self._update_info_label(total_bars - 1)
        self.result_tabs.setCurrentIndex(0)
    
    def _on_mouse_moved(self, evt):
        """計算滑鼠位置對應的歷史 K 棒索引"""
        if not self.last_result_data:
            return
            
        pos = evt[0]
        if self.pw_kline.sceneBoundingRect().contains(pos):
            mouse_point = self.pw_kline.plotItem.vb.mapSceneToView(pos)
            index = int(round(mouse_point.x()))
            self._update_info_label(index)

    def _update_info_label(self, index):
        """將 <合約編號><k頻率><OHCLV> 渲染至資訊列"""
        if not self.last_result_data:
            return
            
        fd = self.last_result_data.get('full_data', {})
        if not fd or 'Close' not in fd:
            return
            
        # 邊界限制
        if index < 0 or index >= len(fd['Close']):
            return

        # 取得 UI 設定值
        contract = self.combo_contract.currentText()
        freq = self.combo_freq.currentText()
        
        # 取得對應索引的數值
        o = fd['Open'][index]
        h = fd['High'][index]
        l = fd['Low'][index]
        c = fd['Close'][index]
        v = fd['Volume'][index]
        
        # 漲跌顏色判定 (紅漲綠跌)
        color = "#ff4d4d" if c >= o else "#00ff44"
        
        # HTML 內容格式化
        info_html = (
            f"<span style='color: #4ec9b0; font-weight: bold;'>{contract}</span> "
            f"({freq}m) | "
            f"O: {o:.2f} H: {h:.2f} L: {l:.2f} "
            f"C: <span style='color: {color};'>{c:.2f}</span> "
            f"V: {int(v)}"
        )
        
        self.info_label.setText(info_html)
        self.info_label.adjustSize()
        # 更新 Equity 與 MDD 的資訊列內容 ---
        summary = self.last_result_data.get('performance_summary', {})
        equity_data = summary.get('equity_curve', [])
        mdd_data = summary.get('drawdown_curve', [])

        if index >= 0 and index < len(equity_data):
            eq_val = equity_data[index]
            self.info_label_equity.setText(f"<html><span style='color:#f1c40f; font-weight:bold;'>Equity: {eq_val:.4f}</span></html>")
            self.info_label_equity.adjustSize()
        
        if index >= 0 and index < len(mdd_data):
            mdd_val = mdd_data[index]
            self.info_label_mdd.setText(f"<html><span style='color:#e74c3c; font-weight:bold;'>MDD: {mdd_val:.2%}</span></html>")
            self.info_label_mdd.adjustSize()
        
    def on_scrollbar_changed(self, value):
        """當捲軸拖動時，觸發顯示範圍更新"""
        self.update_view_range(value)

    def update_view_range(self, start_idx):
        """
        [核心算法]: 根據捲軸位置進行 X 軸跳轉，並自動計算 Y 軸最適縮放比例。
        1. 僅分析目前『勾選顯示』的圖層。
        2. 過濾掉所有價格 <= 0 的異常值。
        """
        if not self.last_result_data: 
            return
        
        fd = self.last_result_data.get('full_data', {})
        if not fd: 
            return
            
        end_idx = start_idx + self.visible_bars
        # 1. 設定 X 軸顯示範圍 (連動資產曲線)
        self.pw_kline.setXRange(start_idx, end_idx, padding=0)
        
        # --- 2. 智慧 Y 軸縮放算法 ---
        y_min = float('inf')
        y_max = float('-inf')
        found_valid_data = False

        # A. 分析 K 線圖層數據 (High/Low)
        if self.layer_visibility_states.get("K棒", True) and 'High' in fd and 'Low' in fd:
            h_slice = fd['High'][start_idx : end_idx]
            l_slice = fd['Low'][start_idx : end_idx]
            # 過濾無效值並找出區間極值
            valid_h = [v for v in h_slice if v > 0]
            valid_l = [v for v in l_slice if v > 0]
            if valid_h and valid_l:
                y_max = max(y_max, max(valid_h))
                y_min = min(y_min, min(valid_l))
                found_valid_data = True

        # B. 分析價位線圖層數據 (Close)
        if self.layer_visibility_states.get("價位線", False) and 'Close' in fd:
            c_slice = fd['Close'][start_idx : end_idx]
            valid_c = [v for v in c_slice if v > 0]
            if valid_c:
                y_max = max(y_max, max(valid_c))
                y_min = min(y_min, min(valid_c))
                found_valid_data = True

        # C. 分析動態指標圖層數據 (Indicators)
        indicators = self.last_result_data.get('indicators', [])
        for ind in indicators:
            name = ind.get('name')
            # 僅當該指標圖層被勾選時才列入 Y 軸計算
            if name and self.layer_visibility_states.get(name, True):
                i_slice = ind.get('data', [])[start_idx : end_idx]
                valid_i = [v for v in i_slice if v > 0]
                if valid_i:
                    y_max = max(y_max, max(valid_i))
                    y_min = min(y_min, min(valid_i))
                    found_valid_data = True

        # 3. 執行縮放 (增加 10% 的上下緩衝空間讓畫面更美觀)
        if found_valid_data and y_max > y_min:
            padding = (y_max - y_min) * 0.1
            self.pw_kline.setYRange(y_min - padding, y_max + padding, padding=0)
        else:
            # 若無效數據，回歸自動縮放
            self.pw_kline.enableAutoRange(axis='y', enable=True)

        # --- []: Equity Curve 與 MDD 的智慧 Y 軸縮放 ---
        summary = self.last_result_data.get('performance_summary', {})
        eq_curve = summary.get('equity_curve', [])
        dd_curve = summary.get('drawdown_curve', [])

        # Equity 縮放
        if eq_curve:
            eq_slice = eq_curve[start_idx : end_idx]
            if eq_slice:
                e_min, e_max = min(eq_slice), max(eq_slice)
                e_pad = (e_max - e_min) * 0.1 if e_max > e_min else 0.1
                self.pw_equity.setYRange(e_min - e_pad, e_max + e_pad, padding=0)
        
        # MDD 縮放
        if dd_curve:
            dd_slice = dd_curve[start_idx : end_idx]
            if dd_slice:
                d_min, d_max = min(dd_slice), max(dd_slice)
                # MDD 通常為負值，給予固定緩衝確保 0 水平線可見度
                d_pad = (d_max - d_min) * 0.1 if d_max > d_min else 0.02
                self.pw_mdd.setYRange(d_min - d_pad, d_max + d_pad, padding=0)
                
    def refresh_chart(self):
        if not self.last_result_data: return
        
        self.pw_kline.clear()
        self.pw_equity.clear()
        self.pw_mdd.clear()
        self.chart_layers.clear() 
        
        fd = self.last_result_data.get('full_data', {})
        if not fd: return
        
        # --- A. 基礎價格圖層 ---
        # A1. K棒
        if all(k in fd for k in ['Open', 'High', 'Low', 'Close']):
            candles = np.column_stack((np.arange(len(fd['Close'])), fd['Open'], fd['High'], fd['Low'], fd['Close']))
            candle_item = CandlestickItem(candles)
            self.pw_kline.addItem(candle_item)
            self.chart_layers["K棒"] = candle_item
            candle_item.setVisible(self.layer_visibility_states.get("K棒", True))
        
        # A2. 價位線 (預設隱藏)
        price_line = self.pw_kline.plot(fd['Close'], pen=pg.mkPen(color='#3498db', width=1))
        self.chart_layers["價位線"] = price_line
        price_line.setVisible(self.layer_visibility_states.get("價位線", False))

        # --- B. 買賣訊號圖層 (基於 signal_series 變化) ---
        summary = self.last_result_data.get('performance_summary', {})
        signals = summary.get('signal_series', [])
        offset  = 20
        if signals:
            signal_group = pg.ItemGroup() # 使用群組管理所有箭頭
            for i in range(len(signals)):
                # 取得前一根訊號，若為第一根則視為 0 (平倉)
                prev_sig = signals[i-1] if i > 0 else 0
                curr_sig = signals[i]
                
                # 訊號未跳變則跳過，僅在進場點標示
                if curr_sig == prev_sig:
                    continue
                
                # 判定進場點與繪製三角形 (依要求調整位置：多:High, 空:Low)
                if curr_sig == 1: # 多單進場
                    arrow = pg.ArrowItem(
                        pos=(i, fd['High'][i]+offset), # 標示於最高點
                        angle=90,             # 向上箭頭
                        brush='#e74c3c',       # 
                        headLen=20
                    )
                    signal_group.addItem(arrow)
                elif curr_sig == -1: # 空單進場
                    arrow = pg.ArrowItem(
                        pos=(i, fd['Low'][i]-offset),  # 標示於最低點
                        angle=-90,              # 向下箭頭
                        brush='#3498db',       # 
                        headLen=20
                    )
                    signal_group.addItem(arrow)
            
            self.pw_kline.addItem(signal_group)
            self.chart_layers["買賣訊號"] = signal_group
            signal_group.setVisible(self.layer_visibility_states.get("買賣訊號", True))

        # --- C. 動態指標圖層 (基於 view.py 產出的 indicators) ---
        indicators = self.last_result_data.get('indicators', [])
        
        style_map = {
            '--': Qt.PenStyle.DashLine,
            ':': Qt.PenStyle.DotLine,
            '-.': Qt.PenStyle.DashDotLine,
            '-': Qt.PenStyle.SolidLine
        }

        for ind in indicators:
            data = ind.get('data', [])
            if data is None or len(data) == 0: 
                continue
            
            kwargs = ind.get('kwargs', {})
            name = ind.get('name') or kwargs.get('label') or 'Unknown'
            color = kwargs.get('color') or ind.get('color', '#ffffff')
            width = kwargs.get('width') or ind.get('width', 1.5)
            
            raw_style = kwargs.get('linestyle') or kwargs.get('style') or ind.get('linestyle') or ind.get('style', '-')
            pen_style = style_map.get(raw_style, Qt.PenStyle.SolidLine)
            
            line = self.pw_kline.plot(
                data, 
                pen=pg.mkPen(color=color, width=width, style=pen_style),
                name=name
            )
            
            self.chart_layers[name] = line
            line.setVisible(self.layer_visibility_states.get(name, True))

        # --- D. 績效圖層 (拆分繪製至獨立視窗) ---
        equity = summary.get('equity_curve', [])
        dd = summary.get('drawdown_curve', [])
        if equity: 
            self.pw_equity.plot(equity, pen=pg.mkPen(color='#f1c40f', width=2))
        if dd: 
            self.pw_mdd.plot(dd, pen=pg.mkPen(color='#e74c3c', width=1, style=Qt.PenStyle.DashLine))
        
        self.pw_kline.autoRange()
        # 初始載入時先執行一次智慧範圍更新
        self.update_view_range(self.scrollbar.value())

    def get_params(self):
        return {
            'strategy_file': self.combo_strategy.currentText(),
            'code': self.combo_contract.currentText(),
            'freq': self.combo_freq.currentText(),
            'start': self.date_start.date().toString("yyyy-MM-dd"),
            'end': self.date_end.date().toString("yyyy-MM-dd"),
            'initial_cash': self.spin_cash.value()
        }

    def set_params(self, params):
        if not params: return
        
        # ---  補齊策略與資金設定，確保 Task Settings 完全帶出 ---
        strategy = params.get('strategy_file', '')
        s_idx = self.combo_strategy.findText(strategy)
        if s_idx >= 0: 
            self.combo_strategy.setCurrentIndex(s_idx)
        else:
            self.combo_strategy.setCurrentText(strategy)

        self.combo_contract.setCurrentText(str(params.get('code', '')))
        
        freq = str(params.get('freq', '15'))
        f_idx = self.combo_freq.findText(freq)
        if f_idx >= 0: self.combo_freq.setCurrentIndex(f_idx)
        
        self.date_start.setDate(QDate.fromString(params.get('start', ''), "yyyy-MM-dd"))
        self.date_end.setDate(QDate.fromString(params.get('end', ''), "yyyy-MM-dd"))
        
        self.spin_cash.setValue(float(params.get('initial_cash', 100.0)))

    def _on_import_cell_clicked(self, row, col):
        # ---  改為抓取索引 1 (ID 欄位)，並更新上方提示標籤 ---
        item = self.table_imports.item(row, 1) 
        if item: 
            project_id = item.text()
            self.current_edit_id = project_id
            self.lbl_edit_id.setText(f"Editing Project: {project_id}")
            self.sig_import_selected.emit(project_id)

    def show_parse_report_ui(self, task_id, content):
        dlg = ReportDialog(task_id, content, self)
        dlg.exec()
        
    # --- : 批次處理邏輯 ---
    def _get_checked_ids(self):
        """獲取所有被勾選的專案 ID"""
        checked_ids = []
        for row in range(self.table_imports.rowCount()):
            item = self.table_imports.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                id_item = self.table_imports.item(row, 1)
                if id_item:
                    checked_ids.append(id_item.text())
        return checked_ids

    def _on_bulk_run(self):
        """針對勾選 ID 批次執行任務"""
        for pid in self._get_checked_ids():
            self.sig_run_task.emit(pid)

    def _on_bulk_plot(self):
        """針對勾選 ID 批次繪製圖表 (僅針對 FINISHED 狀態)"""
        for pid in self._get_checked_ids():
            # 尋找該 ID 對應列的狀態
            for row in range(self.table_imports.rowCount()):
                if self.table_imports.item(row, 1).text() == pid:
                    status = self.table_imports.item(row, 2).text()
                    if status == "FINISHED":
                        self.sig_show_result.emit(pid)
                    break

    def _on_bulk_open(self):
        """: 使用 ResultStorage 獲取正確路徑 (SSTP 標準)，並加入查無資料夾的提示"""
        import os
        from shared.backtest.storage import ResultStorage
        from PyQt6.QtWidgets import QMessageBox
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        
        # 1. 收集勾選專案的資訊
        target_infos = []
        for row in range(self.table_imports.rowCount()):
            chk_item = self.table_imports.item(row, 0)
            if chk_item and chk_item.checkState() == Qt.CheckState.Checked:
                id_item = self.table_imports.item(row, 1)
                if id_item:
                    target_infos.append({
                        'pid': id_item.text(),
                        'name': id_item.data(Qt.ItemDataRole.UserRole)
                    })
        
        if not target_infos:
            # 若無勾選，開啟回測結果的根目錄
            base_root = ResultStorage.get_base_dir("")
            QDesktopServices.openUrl(QUrl.fromLocalFile(base_root))
            return

        # 2. 逐一開啟對應資料夾
        for info in target_infos:
            strategy_name = info['name']
            # 從 ResultStorage 獲取標準化路徑 (位於 %LOCALAPPDATA%)
            target_dir = ResultStorage.get_base_dir(strategy_name)

            if os.path.exists(target_dir):
                QDesktopServices.openUrl(QUrl.fromLocalFile(target_dir))
            else:
                # : 增加 UI 錯誤提示
                QMessageBox.warning(
                    self, "資料夾未找到", 
                    f"專案 {info['pid']} ({strategy_name}) 尚未產生回測結果資料夾。"
                )