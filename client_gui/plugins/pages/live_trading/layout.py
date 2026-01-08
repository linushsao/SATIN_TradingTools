# ==============================================================================
# client_gui/plugins/pages/live_trading/layout.py
#
# Version: V2.8-002 (Fix Label Persistence)
# 更新日期: 2025-12-16
# 描述:     即時交易頁面佈局。
#           [修正]: rebuild_layout 後立即還原商品代碼顯示，避免標題空白。
# ==============================================================================

import os
import sys
import pandas as pd
import numpy as np
import pyqtgraph as pg
import types 
import datetime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, 
                             QTabWidget, QListWidget, QTableWidget, QToolBar,
                             QDialog, QFormLayout, QSpinBox, QComboBox, QCheckBox, 
                             QDialogButtonBox, QPushButton, QHeaderView, QTableWidgetItem,
                             QAbstractItemView)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont, QAction

from ui_lib.chart_items import CandlestickItem, DateAxisItem
from ui_lib.layouts import StrategyTable, HistoryDownloadDialog, ContractList
from shared.config_manager import load_config, save_config, CONFIG_FILE

COLOR_MAP = {
    'cyan': '#00FFFF', 'magenta': '#FF00FF', 'yellow': '#FFFF00', 'white': '#FFFFFF',
    'red': '#FF0000', 'green': '#00FF00', 'blue': '#0000FF', 'orange': '#FFA500', 'gray': '#808080'
}
Y_AXIS_WIDTH = 60 

# [NEW] Contract Manager Dialog
class ContractManagerDialog(QDialog):
    def __init__(self, all_contracts, visible_codes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Contract Selection")
        self.resize(500, 600)
        self.layout = QVBoxLayout(self)
        
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Show", "Code", "Name"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.layout.addWidget(self.table)
        
        self.all_contracts = all_contracts
        self.visible_codes = set(visible_codes) if visible_codes else set()
        
        self._populate_table()
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_all = QPushButton("Select All")
        btn_all.clicked.connect(self._select_all)
        btn_none = QPushButton("Select None")
        btn_none.clicked.connect(self._select_none)
        btn_layout.addWidget(btn_all)
        btn_layout.addWidget(btn_none)
        btn_layout.addStretch()
        
        self.btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.btn_box.accepted.connect(self.accept)
        self.btn_box.rejected.connect(self.reject)
        
        self.layout.addLayout(btn_layout)
        self.layout.addWidget(self.btn_box)

    def _populate_table(self):
        self.table.setRowCount(len(self.all_contracts))
        for i, c in enumerate(self.all_contracts):
            code = c['code']
            name = c.get('name', '')
            
            # Checkbox Item
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            # If visible_codes is empty, it means "Show All" by default or config logic
            is_checked = (code in self.visible_codes) or (not self.visible_codes)
            chk_item.setCheckState(Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
            self.table.setItem(i, 0, chk_item)
            
            self.table.setItem(i, 1, QTableWidgetItem(code))
            self.table.setItem(i, 2, QTableWidgetItem(name))

    def _select_all(self):
        for i in range(self.table.rowCount()):
            self.table.item(i, 0).setCheckState(Qt.CheckState.Checked)

    def _select_none(self):
        for i in range(self.table.rowCount()):
            self.table.item(i, 0).setCheckState(Qt.CheckState.Unchecked)

    def get_visible_contracts(self):
        result = []
        for i in range(self.table.rowCount()):
            if self.table.item(i, 0).checkState() == Qt.CheckState.Checked:
                code = self.table.item(i, 1).text()
                result.append(code)
        return result

# ... (LiveTradingOptionsDialog unchanged) ...
class LiveTradingOptionsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Live Trading Options")
        self.resize(500, 450)
        self.config = config
        
        self.layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        
        self.tab_general = QWidget()
        form = QFormLayout(self.tab_general)
        
        self.spin_min_bars = QSpinBox(); self.spin_min_bars.setRange(100, 99999)
        self.spin_min_bars.setValue(int(config.get('min_display_bars', 1600)))
        form.addRow("Min Read Bars (Buffer):", self.spin_min_bars)
        
        self.spin_page_bars = QSpinBox(); self.spin_page_bars.setRange(10, 9999)
        self.spin_page_bars.setValue(int(config.get('page_display_bars', 200)))
        form.addRow("Page Display Bars:", self.spin_page_bars)
        
        self.combo_freq = QComboBox()
        self.combo_freq.addItems(['1', '5', '15', '30', '60'])
        self.combo_freq.setCurrentText(str(config.get('view_kbar_freq', 15)))
        form.addRow("K-Bar Freq (min):", self.combo_freq)
        
        self.spin_ma = QSpinBox(); self.spin_ma.setRange(1, 500)
        self.spin_ma.setValue(int(config.get('system_ma_period', 20)))
        form.addRow("System MA Period:", self.spin_ma)
        
        self.chk_hud = QCheckBox("Show Floating HUD")
        self.chk_hud.setChecked(config.get('show_hud', True))
        form.addRow("Chart HUD:", self.chk_hud)
        
        self.chk_crosshair = QCheckBox("Show Crosshair")
        self.chk_crosshair.setChecked(config.get('show_crosshair', True))
        form.addRow("Chart Crosshair:", self.chk_crosshair)
        
        form.addRow(QLabel("<b>[Engine Settings]</b>"))
        self.chk_save_ticks = QCheckBox("Save Ticks to DB")
        self.chk_save_ticks.setChecked(config.get('ticks_save_enabled', False))
        form.addRow("Engine Recording:", self.chk_save_ticks)
        
        self.chk_auto_login = QCheckBox("Auto Login on Start")
        self.chk_auto_login.setChecked(config.get('auto_login', False))
        form.addRow("Startup Login:", self.chk_auto_login)
        
        self.tabs.addTab(self.tab_general, "General")
        
        self.tab_contracts = QWidget()
        layout_con = QVBoxLayout(self.tab_contracts)
        self.table_mult = QTableWidget()
        self.table_mult.setColumnCount(2)
        self.table_mult.setHorizontalHeaderLabels(["Code Prefix", "Multiplier"])
        self.table_mult.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("+"); btn_add.clicked.connect(self._add_mult_row)
        btn_del = QPushButton("-"); btn_del.clicked.connect(self._del_mult_row)
        btn_layout.addWidget(btn_add); btn_layout.addWidget(btn_del); btn_layout.addStretch()
        layout_con.addLayout(btn_layout)
        layout_con.addWidget(self.table_mult)
        
        self._load_multipliers()
        self.tabs.addTab(self.tab_contracts, "Contracts")
        
        self.layout.addWidget(self.tabs)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.layout.addWidget(buttons)

    def _load_multipliers(self):
        default_mults = {"TXF": 200, "MTX": 50, "TMF": 10, "MXF": 50, "GTF": 50, "TE": 4000, "TF": 1000}
        mults = self.config.get('contract_multipliers', default_mults)
        self.table_mult.setRowCount(len(mults))
        for i, (code, val) in enumerate(mults.items()):
            self.table_mult.setItem(i, 0, QTableWidgetItem(str(code)))
            self.table_mult.setItem(i, 1, QTableWidgetItem(str(val)))

    def _add_mult_row(self):
        row = self.table_mult.rowCount(); self.table_mult.insertRow(row)
        self.table_mult.setItem(row, 0, QTableWidgetItem("CODE"))
        self.table_mult.setItem(row, 1, QTableWidgetItem("1"))

    def _del_mult_row(self):
        row = self.table_mult.currentRow()
        if row >= 0: self.table_mult.removeRow(row)

    def _save_multipliers(self):
        new_mults = {}
        for i in range(self.table_mult.rowCount()):
            code_item = self.table_mult.item(i, 0); val_item = self.table_mult.item(i, 1)
            if code_item and val_item:
                try:
                    code = code_item.text().strip().upper(); val = float(val_item.text().strip())
                    if code: new_mults[code] = val
                except: pass
        self.config['contract_multipliers'] = new_mults

    def apply_changes(self):
        self.config['min_display_bars'] = self.spin_min_bars.value()
        self.config['page_display_bars'] = self.spin_page_bars.value()
        self.config['view_kbar_freq'] = int(self.combo_freq.currentText())
        self.config['show_hud'] = self.chk_hud.isChecked()
        self.config['show_crosshair'] = self.chk_crosshair.isChecked()
        self.config['system_ma_period'] = self.spin_ma.value()
        self.config['ticks_save_enabled'] = self.chk_save_ticks.isChecked()
        self.config['auto_login'] = self.chk_auto_login.isChecked()
        self._save_multipliers()
        save_config(self.config, CONFIG_FILE)

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
            acc = accounts[0] # Take first available
            aid = acc.get('account_id', 'N/A')
            is_signed = acc.get('is_signed', False)
            
            self.lbl_id.setText(f"Account: {aid}")
            
            status_text = "[V] Signed" if is_signed else "[!] Unsigned"
            self.lbl_status.setText(f"Status: {status_text}")
            
            if is_signed: self.lbl_status.setStyleSheet("color: green")
            else: self.lbl_status.setStyleSheet("color: red")
        else:
            self.lbl_id.setText("Account: N/A")
            self.lbl_status.setText("Status: No Data")

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
        # SSTP Tick: { "ts": float, "price": float, "vol": int }
        price = tick_data.get('price', 0)
        if price <= 0: return

        row_idx = self.rowCount()
        self.insertRow(row_idx)
        
        ts_val = tick_data.get('ts', 0)
        try:
            dt_obj = datetime.datetime.fromtimestamp(ts_val)
            time_str = dt_obj.strftime('%H:%M:%S')
        except:
            time_str = "--:--:--"

        self.setItem(row_idx, 0, QTableWidgetItem(time_str))
        
        price_item = QTableWidgetItem(f"{price:.0f}")
        price_item.setForeground(QColor("blue")) 
        self.setItem(row_idx, 1, price_item)
        
        vol = tick_data.get('vol', 0)
        self.setItem(row_idx, 2, QTableWidgetItem(str(vol)))
        
        if self.rowCount() > 50: self.removeRow(0)
        self.scrollToBottom()


class KLineChartWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.context = None 
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        pg.setConfigOption('background', 'k')
        pg.setConfigOption('foreground', 'd')
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.layout.addWidget(self.splitter)
        self.df_kbars = pd.DataFrame()
        self.timestamps = [] 
        self.indicator_data = {} 
        self.idx_open = None; self.idx_high = None; self.idx_low = None; self.idx_close = None; self.idx_volume = None
        self.config = load_config()
        self.display_bars = int(self.config.get('page_display_bars', 200))
        self.target_freq = self.config.get('view_kbar_freq', 15)
        self.current_code = ""
        self.plot_main = None; self.axis_main = None; self.indep_plots = []    
        self.candle_item = None; self.main_drawings = []; self.indicator_items = []
        self.is_rebuilding = False; self.hud_label = None; self.v_line = None; self.h_line = None; self.main_info_label = None
        
        self.dirty = False
        self.throttle_timer = QTimer(self)
        self.throttle_timer.setInterval(100)
        self.throttle_timer.timeout.connect(self._update_ui_from_tick)
        self.throttle_timer.start()

        self.rebuild_layout()

    def set_context(self, context):
        self.context = context

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.hud_label: self.hud_label.move(10, 10); self.hud_label.adjustSize()

    def set_code(self, code):
        self.current_code = code
        if self.main_info_label: self.main_info_label.setText(f"<html><span style='color:#FFFFFF; font-weight:bold'>{code}</span></html>")

    def _create_info_label(self, parent_widget):
        lbl = QLabel(parent_widget)
        lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lbl.setStyleSheet("QLabel { background-color: rgba(0, 0, 0, 0); color: #e0e0e0; font-family: Consolas, Monospace; font-size: 12px; font-weight: bold; padding: 2px; }")
        lbl.move(Y_AXIS_WIDTH + 10, 3) 
        lbl.show()
        return lbl

    def rebuild_layout(self):
        self.is_rebuilding = True
        self.plot_main = None; self.indep_plots = []; self.main_drawings = []
        while self.splitter.count() > 0: w = self.splitter.widget(0); w.hide(); w.deleteLater(); w.setParent(None)
        if self.hud_label: self.hud_label.deleteLater()
        self.hud_label = QLabel(self)
        self.hud_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) 
        self.hud_label.setStyleSheet("QLabel { background-color: rgba(0,0,0,180); color: #d4d4d4; font-family: Consolas; font-size: 12px; padding: 8px; border: 1px solid #555; border-radius: 6px; }")
        self.hud_label.setText("Waiting for data..."); self.hud_label.hide()
        self.v_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('gray', style=Qt.PenStyle.DashLine, width=0.8))
        self.h_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('gray', style=Qt.PenStyle.DashLine, width=0.8))
        self.axis_main = DateAxisItem(orientation='bottom')
        widget_main = pg.PlotWidget(axisItems={'bottom': self.axis_main})
        self.plot_main = widget_main.getPlotItem()
        self.plot_main.showGrid(x=True, y=True, alpha=0.3)
        self.plot_main.setLabel('left', 'Price'); self.plot_main.getAxis('left').setWidth(Y_AXIS_WIDTH)
        self.plot_main.addItem(self.v_line, ignoreBounds=True); self.plot_main.addItem(self.h_line, ignoreBounds=True)
        self.proxy = pg.SignalProxy(self.plot_main.scene().sigMouseMoved, rateLimit=60, slot=self.mouse_moved)
        self.main_info_label = self._create_info_label(widget_main)
        self.splitter.addWidget(widget_main)
        
        indep_list = self.config.get('live_independent_plots', [])
        if indep_list: self.plot_main.hideAxis('bottom')
        for i, plugin_name in enumerate(indep_list):
            axis_sub = DateAxisItem(orientation='bottom')
            widget_sub = pg.PlotWidget(axisItems={'bottom': axis_sub})
            plot_sub = widget_sub.getPlotItem()
            plot_sub.showGrid(x=True, y=True, alpha=0.3)
            label = plugin_name.replace('.py', '').replace('_plot', '').upper()
            plot_sub.setLabel('left', label); plot_sub.getAxis('left').setWidth(Y_AXIS_WIDTH)
            plot_sub.setXLink(self.plot_main)
            if i < len(indep_list) - 1: plot_sub.hideAxis('bottom')
            v_line_sub = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('gray', style=Qt.PenStyle.DashLine, width=0.8))
            plot_sub.addItem(v_line_sub, ignoreBounds=True)
            info_lbl = self._create_info_label(widget_sub)
            self.splitter.addWidget(widget_sub)
            self.indep_plots.append({'plot': plot_sub, 'axis': axis_sub, 'name': plugin_name, 'vline': v_line_sub, 'info_label': info_lbl, 'drawings': [], 'data_series': []})
        
        count = len(indep_list); total_height = self.height() if self.height() > 100 else 800
        if count > 0:
            main_h = int(total_height * 0.5); sub_h = int((total_height * 0.5) / count)
            sizes = [main_h] + [sub_h] * count
            self.splitter.setSizes(sizes)
            self.splitter.setStretchFactor(0, count) 
            for i in range(count): self.splitter.setStretchFactor(i + 1, 1)
        else: self.splitter.setSizes([total_height])
        
        # [Fix] Restore the code label immediately after rebuilding UI
        if self.current_code:
            self.set_code(self.current_code)
            
        self.is_rebuilding = False

    def refresh_chart(self):
        self.config = load_config()
        self.target_freq = self.config.get('view_kbar_freq', 15)
        self.display_bars = int(self.config.get('page_display_bars', 200))
        self.rebuild_layout()
        if not self.df_kbars.empty: self.draw_kline(); self.draw_indicators()

    def clear_data_items(self):
        for item in self.main_drawings:
            if item in self.plot_main.items: self.plot_main.removeItem(item)
        self.main_drawings = []
        for item in self.indep_plots:
            for child in item['drawings']:
                if child in item['plot'].items: item['plot'].removeItem(child)
            item['drawings'] = []; item['data_series'] = []

    def clear(self):
        if self.is_rebuilding: return
        self.df_kbars = pd.DataFrame(); self.timestamps = []; self.indicator_data = {}
        self.clear_data_items()
        self.axis_main.update_timestamps([])
        for item in self.indep_plots: item['axis'].update_timestamps([])
        self.main_info_label.setText(""); self.hud_label.hide() 
        for item in self.indep_plots: item['info_label'].setText("")

    def update_data(self, data):
        """
        [修正]: 增加強制排序邏輯，解決 00:00 跨日 K 線停止更新問題。
        """
        if self.is_rebuilding or self.plot_main is None or not data: return
        try:
            df = pd.DataFrame(data)
            
            # 1. 強化時間戳記處理
            if 'ts' in df.columns: 
                # 強制轉換為 datetime 並處理時區/格式
                df['ts'] = pd.to_datetime(df['ts'])
                df.set_index('ts', inplace=True)
                
                # [核心修正]: 必須執行排序，確保 00:00 (隔日) 接在 23:45 之後
                df.sort_index(inplace=True)
            
            # 2. 欄位更名與數值轉換
            rename_map = {'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close', 'v': 'Volume'}
            df.rename(columns=rename_map, inplace=True)

            cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            for c in cols:
                if c in df.columns: 
                    df[c] = pd.to_numeric(df[c], errors='coerce')
                
            # 3. 填充空值並過濾重複 (保留最新的資料)
            df[cols] = df[cols].replace(0, np.nan).ffill().bfill()
            df = df[~df.index.duplicated(keep='last')]
            
            # 4. 重新取得欄位索引位置
            try:
                self.idx_open = df.columns.get_loc('Open')
                self.idx_high = df.columns.get_loc('High')
                self.idx_low = df.columns.get_loc('Low')
                self.idx_close = df.columns.get_loc('Close')
                self.idx_volume = df.columns.get_loc('Volume')
            except KeyError: pass 
            
            self.df_kbars = df
            # 更新顯示用時間字串列表
            self.timestamps = df.index.strftime('%Y-%m-%d %H:%M:%S').tolist()
            
            # 5. 重新繪圖並確保視窗捲動到最末端
            self.draw_kline()
            self.draw_indicators()
            self.update_text_content(len(df) - 1)
            self.dirty = False 
            
        except Exception as e: 
            print(f"[Chart Rebuild Error at {datetime.datetime.now()}]: {e}")

    def process_tick(self, price, volume):
        if self.is_rebuilding or self.plot_main is None or self.df_kbars.empty or price <= 0 or self.idx_close is None: return
        try:
            curr_h = self.df_kbars.iloc[-1, self.idx_high]
            curr_l = self.df_kbars.iloc[-1, self.idx_low]
            
            new_h = max(curr_h, price) if not pd.isna(curr_h) else price
            new_l = min(curr_l, price) if not pd.isna(curr_l) else price
            
            self.df_kbars.iloc[-1, self.idx_close] = price
            self.df_kbars.iloc[-1, self.idx_high] = new_h
            self.df_kbars.iloc[-1, self.idx_low] = new_l
            self.df_kbars.iloc[-1, self.idx_volume] += volume
            
            self.dirty = True
        except Exception as e: print(f"[Chart] Tick Error: {e}")

    def _update_ui_from_tick(self):
        if not self.dirty or self.df_kbars.empty or not self.candle_item:
            return
            
        try:
            last_idx = len(self.df_kbars) - 1
            row = self.df_kbars.iloc[-1]
            
            self.candle_item.update_last_bar(
                last_idx, row['Open'], row['Close'], row['Low'], row['High']
            )
            
            self.update_text_content(last_idx)
            
            self.dirty = False
        except Exception as e:
            print(f"[UI Refresh] Error: {e}")

    def draw_kline(self, keep_range=False):
        if self.is_rebuilding or self.plot_main is None: return
        if not keep_range: self.clear_data_items()
        if self.candle_item and self.candle_item in self.plot_main.items: self.plot_main.removeItem(self.candle_item)
        quotes = []
        for i, (idx, row) in enumerate(self.df_kbars.iterrows()): quotes.append((i, row['Open'], row['Close'], row['Low'], row['High']))
        self.candle_item = CandlestickItem(quotes); self.plot_main.addItem(self.candle_item)
        if not keep_range: self.main_drawings.append(self.candle_item)
        self.candle_item.setZValue(1); self.v_line.setZValue(10); self.h_line.setZValue(10)
        self.axis_main.update_timestamps(self.timestamps)
        for item in self.indep_plots: item['axis'].update_timestamps(self.timestamps)
        if not keep_range: 
            total = len(self.df_kbars); start = max(0, total - self.display_bars)
            self.plot_main.setXRange(start, total); self.update_views(start, total)
            for item in self.indep_plots: item['plot'].enableAutoRange(axis='y', enable=True)

    def _prepare_remote_core(self, project_id):
        if not self.context or not project_id: return False
        try:
            core_code = self.context.get_file_content(f"projects/{project_id}/strategy_core.py")
            if not core_code: return False
            
            mod = types.ModuleType("strategy_core")
            exec(core_code, mod.__dict__)
            
            sys.modules["strategy_core"] = mod
            return True
        except Exception as e:
            print(f"[RemoteCore] Injection failed for {project_id}: {e}")
            return False

    def draw_indicators(self):
        if self.is_rebuilding or self.plot_main is None or self.df_kbars.empty: return
        self.indicator_data = {}; self.plot_indicators_map = {self.plot_main: []}
        for item in self.indep_plots: self.plot_indicators_map[item['plot']] = []
        
        overlay_list = self.config.get('live_k_bar_plugins', [])
        local_vars = {'K_BAR_DATA': self.df_kbars.copy(), 'SYSTEM_MA_PERIOD': self.config.get('system_ma_period', 20), 'BASE_FREQ': self.target_freq, 'ADDPLOT_CONFIG': [], 'pd': pd, 'np': np}
        
        if hasattr(self, 'exec_plugin_callback'):
            for filename in overlay_list: 
                self.exec_plugin_callback(filename, local_vars, self.plot_main, self.main_drawings, is_overlay=True)
                
            for item in self.indep_plots: 
                self.exec_plugin_callback(item['name'], local_vars, item['plot'], item['drawings'], item['data_series'], is_overlay=False)
        
        if self.context:
            try:
                from shared.capabilities import CAP_STRATEGY_HOST
                strat_svc = self.context.get_service_by_capability(CAP_STRATEGY_HOST)
                
                if strat_svc:
                    str_status = strat_svc.get_strategy_status()
                    target_strat = next((s for s in str_status if s.get('contract') == self.current_code and s.get('running')), None)
                    if not target_strat:
                        target_strat = next((s for s in str_status if s.get('contract') == self.current_code), None)
                    
                    if target_strat:
                        sid = str(target_strat.get('id'))
                        if self._prepare_remote_core(sid):
                            view_code = self.context.get_strategy_view_code(sid)
                            if view_code:
                                self._exec_view_code(view_code, local_vars, self.plot_main, self.main_drawings)
            except Exception: pass

        total = len(self.df_kbars); start = max(0, total - self.display_bars); self.update_views(start, total)

    def update_views(self, start_idx, total_bars):
        visible_df = self.df_kbars.iloc[start_idx:]
        if not visible_df.empty:
            y_min = visible_df['Low'].min(); y_max = visible_df['High'].max()
            if not pd.isna(y_min) and not pd.isna(y_max) and y_max > 0:
                diff = y_max - y_min; padding = diff * 0.05 if diff != 0 else y_max * 0.01
                self.plot_main.setYRange(y_min - padding, y_max + padding); self.plot_main.disableAutoRange(axis='y')
        for item in self.indep_plots:
            plot = item['plot']; data_list = item['data_series']
            if not data_list: continue
            g_min = float('inf'); g_max = float('-inf'); found = False
            for ds in data_list:
                if len(ds) == total_bars:
                    valid = ds[start_idx:][~np.isnan(ds[start_idx:])]
                    if len(valid) > 0: g_min = min(g_min, np.min(valid)); g_max = max(g_max, np.max(valid)); found = True
            if found:
                diff = g_max - g_min; padding = diff * 0.05 if diff != 0 else (abs(g_max)*0.01 if g_max!=0 else 1.0)
                if "VOLUME" in item['name'].upper(): plot.setYRange(0, g_max + padding)
                else: plot.setYRange(g_min - padding, g_max + padding)
                plot.disableAutoRange(axis='y')

    def _exec_view_code(self, code_content, local_vars, target_plot, drawing_list):
        try:
            local_vars['ADDPLOT_CONFIG'] = []
            exec(code_content, local_vars)
            self._render_plots(local_vars.get('ADDPLOT_CONFIG', []), target_plot, drawing_list)
        except Exception as e:
            print(f"[View Exec Error] {e}")

    def _render_plots(self, configs, target_plot, drawing_list, data_collection=None, label_prefix=""):
        x_axis = np.arange(len(self.df_kbars))
        for cfg in configs:
            data = cfg.get('data'); kwargs = cfg.get('kwargs', {})
            if data is None or len(data) == 0: continue
            label = kwargs.get('label', label_prefix)
            
            # [修正]: 提前解析顏色資訊
            mpl_color = kwargs.get('color', 'white')
            if isinstance(mpl_color, (list, np.ndarray)): pg_color = '#FFFFFF' 
            else: pg_color = COLOR_MAP.get(mpl_color, '#FFFFFF')

            # [修正]: 將顏色資訊 (pg_color) 存入映射表，供 UI 標籤使用
            if target_plot in self.plot_indicators_map: 
                self.plot_indicators_map[target_plot].append((label, data.values, pg_color))
            
            if data_collection is not None: data_collection.append(data.values)
            
            # [修正]: 將顏色資訊一併存入 indicator_data 供 HUD 使用
            self.indicator_data[label] = (data.values, pg_color) 
            
            width = kwargs.get('linewidth', 1)
            style_str = kwargs.get('linestyle', '-')
            fill_level = kwargs.get('fillLevel', None) 
            plot_type = kwargs.get('type', 'line')
            item = None 

            if plot_type == 'bar':
                    if isinstance(mpl_color, (list, np.ndarray)):
                        # brushes = [COLOR_MAP.get(c, '#FFFFFF') for c in mpl_color]
                        brushes = [COLOR_MAP.get(c, c) for c in mpl_color]
                        item = pg.BarGraphItem(x=x_axis, height=data.values, width=0.6, brushes=brushes)
                    else:
                        brush = pg.mkBrush(pg_color)
                        item = pg.BarGraphItem(x=x_axis, height=data.values, width=0.6, brush=brush)
                    target_plot.addItem(item)
                    
            elif plot_type == 'scatter':
                symbol_map = {'t': 't', 't1': 't1', 'o': 'o', 's': 's'}
                symbol = symbol_map.get(kwargs.get('symbol', 'o'), 'o')
                size = kwargs.get('size', 10)
                brush = pg.mkBrush(pg_color)
                
                spots = []
                vals = data.values
                for i in range(len(vals)):
                    val = vals[i]
                    if not np.isnan(val) and val != 0:
                        spots.append({'pos': (x_axis[i], val), 'data': 1, 'brush': brush, 'symbol': symbol, 'size': size})
                
                if spots:
                    item = pg.ScatterPlotItem(spots=spots)
                    target_plot.addItem(item)
            
            else: # Line
                style = Qt.PenStyle.SolidLine
                if style_str in ['--', ':']: style = Qt.PenStyle.DashLine
                pen = pg.mkPen(color=pg_color, width=width, style=style)
                
                if fill_level is not None:
                    brush_color = QColor(pg_color); brush_color.setAlpha(50)
                    item = target_plot.plot(x_axis, data.values, pen=pen, fillLevel=fill_level, brush=brush_color) 
                else:
                    item = target_plot.plot(x_axis, data.values, pen=pen, name=label) 
            
            if item: drawing_list.append(item)
            if kwargs.get('invertY', False): target_plot.invertY(True)

    def update_text_content(self, index):
        if index < 0 or index >= len(self.df_kbars): return
        row = self.df_kbars.iloc[index]; ts_str = self.timestamps[index]; c_color = "#FF5555" if row['Close'] >= row['Open'] else "#55FF55"
        freq = self.target_freq
        main_info = f"<span style='color:#FFFFFF; font-weight:bold'>{self.current_code}</span>&nbsp;<span style='color:#E6DB74; font-weight:bold'>[{freq}m]</span>&nbsp;&nbsp;<span style='color:#DDD'>{ts_str}</span>&nbsp;&nbsp;O:<span style='color:#EEE'>{row['Open']:.0f}</span>&nbsp;H:<span style='color:#EEE'>{row['High']:.0f}</span>&nbsp;L:<span style='color:#EEE'>{row['Low']:.0f}</span>&nbsp;C:<span style='color:{c_color}'>{row['Close']:.0f}</span>&nbsp;V:<span style='color:#EEE'>{int(row['Volume'])}</span>"
        if self.plot_main in self.plot_indicators_map:
            # [修正]: 解構 tuple 並套用 color 至 HTML 標籤
            for label, values, color in self.plot_indicators_map[self.plot_main]:
                if index < len(values) and not np.isnan(values[index]): main_info += f"&nbsp;&nbsp;{label}:<span style='color:{color}'>{values[index]:.2f}</span>"
        if self.main_info_label: self.main_info_label.setText(f"<html>{main_info}</html>"); self.main_info_label.adjustSize()
        for item in self.indep_plots:
            plot = item['plot']; sub_info = ""
            if plot in self.plot_indicators_map:
                # [修正]: 解構 tuple 並套用 color 至 HTML 標籤
                for label, values, color in self.plot_indicators_map[plot]:
                    if index < len(values) and not np.isnan(values[index]): sub_info += f"{label}:<span style='color:{color}'>{values[index]:.2f}</span>  "
            item['info_label'].setText(f"<html>{sub_info}</html>"); item['info_label'].adjustSize()
        if self.config.get('show_hud', True) and self.hud_label.isVisible():
            hud_html = f"<div>{self.current_code} [{freq}m]</div><div style='font-weight:bold; color:#DDD'>{ts_str}</div><div>O: <span style='color:#EEE'>{row['Open']:.0f}</span></div><div>H: <span style='color:#EEE'>{row['High']:.0f}</span></div><div>L: <span style='color:#EEE'>{row['Low']:.0f}</span></div><div>C: <span style='color:{c_color}'>{row['Close']:.0f}</span></div><div>V: <span style='color:#EEE'>{int(row['Volume'])}</span></div>"
            # [修正]: 迭代 indicator_data 時解構 (values, color)
            for name, (values, color) in self.indicator_data.items():
                if index < len(values) and not np.isnan(values[index]): hud_html += f"<div>{name}: <span style='color:{color}'>{values[index]:.2f}</span></div>"
            self.hud_label.setText(f"<html>{hud_html}</html>"); self.hud_label.adjustSize()

    def mouse_moved(self, evt):
        if self.is_rebuilding or self.plot_main is None: return
        pos = evt[0]
        if self.plot_main.sceneBoundingRect().contains(pos):
            mouse_point = self.plot_main.vb.mapSceneToView(pos); index = int(mouse_point.x())
            if self.config.get('show_crosshair', True):
                self.v_line.setPos(mouse_point.x()); self.h_line.setPos(mouse_point.y()); self.v_line.show(); self.h_line.show()
                for item in self.indep_plots: item['vline'].setPos(mouse_point.x()); item['vline'].show()
            else:
                self.v_line.hide(); self.h_line.hide()
                for item in self.indep_plots: item['vline'].hide()
            if 0 <= index < len(self.df_kbars):
                self.update_text_content(index)
                if self.config.get('show_hud', True):
                    local_pos = self.plot_main.mapFromScene(pos); x_off = 15; y_off = 15
                    if local_pos.x() + self.hud_label.width() > self.width(): x_off = -self.hud_label.width() - 15
                    self.hud_label.move(int(local_pos.x()) + x_off, int(local_pos.y()) + y_off); self.hud_label.show()
                else: self.hud_label.hide()
            else: self.hud_label.hide()
        else: self.hud_label.hide()


class LiveTradingWidget(QWidget):
    sig_contract_selected = pyqtSignal(str)
    sig_config_indicators = pyqtSignal()
    sig_open_options = pyqtSignal() 
    sig_download_history = pyqtSignal() 
    sig_manage_contracts = pyqtSignal() # [NEW] Signal

    def __init__(self):
        super().__init__()
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.left_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # --- Left Top: Info Tabs ---
        self.info_tabs = QTabWidget()
        self.strategy_table = StrategyTable()
        self.info_tabs.addTab(self.strategy_table, "Strategies")
        self.account_widget = AccountInfoWidget()
        self.info_tabs.addTab(self.account_widget, "Account")
        self.left_splitter.addWidget(self.info_tabs)
        
        # --- Left Bottom: Chart & Toolbar ---
        self.chart_container = QWidget()
        self.chart_layout = QVBoxLayout(self.chart_container)
        self.chart_layout.setContentsMargins(0, 0, 0, 0)
        self.chart_layout.setSpacing(0)
        
        self.chart_toolbar = QToolBar()
        self.chart_toolbar.setStyleSheet("""
            QToolBar { background-color: #2b2b2b; border-bottom: 1px solid #3e3e3e; }
            QToolButton { color: #ffffff; font-weight: bold; } 
            QToolButton:hover { background-color: #3e3e3e; }
        """)
        
        self.act_indicators = QAction("Indicators", self)
        self.act_indicators.triggered.connect(lambda: self.sig_config_indicators.emit())
        self.chart_toolbar.addAction(self.act_indicators)
        
        self.act_download = QAction("Download", self)
        self.act_download.triggered.connect(lambda: self.sig_download_history.emit())
        self.chart_toolbar.addAction(self.act_download)

        self.act_options = QAction("Options", self)
        self.act_options.triggered.connect(lambda: self.sig_open_options.emit())
        self.chart_toolbar.addAction(self.act_options)
        
        self.chart_layout.addWidget(self.chart_toolbar)

        self.chart_widget = KLineChartWidget()
        self.chart_layout.addWidget(self.chart_widget)
        
        self.left_splitter.addWidget(self.chart_container)
        
        self.left_splitter.setStretchFactor(0, 1)
        self.left_splitter.setStretchFactor(1, 3)
        self.main_splitter.addWidget(self.left_splitter)
        
        # --- Right Panel ---
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.tick_table = TickTable()
        self.right_splitter.addWidget(self.tick_table)
        
        # [MOD] Contract Section (List + Settings Button)
        self.contract_container = QWidget()
        layout_contract = QVBoxLayout(self.contract_container)
        layout_contract.setContentsMargins(0,0,0,0)
        layout_contract.setSpacing(1)
        
        self.contract_list = ContractList()
        self.contract_list.itemClicked.connect(lambda item: self.sig_contract_selected.emit(item.text().split(' ')[0]))
        layout_contract.addWidget(self.contract_list)
        
        btn_settings = QPushButton("⚙️ Settings")
        btn_settings.setStyleSheet("background-color: #2d2d2d; color: #808080; border: none; padding: 4px;")
        btn_settings.clicked.connect(lambda: self.sig_manage_contracts.emit())
        layout_contract.addWidget(btn_settings)
        
        self.right_splitter.addWidget(self.contract_container)
        
        self.main_splitter.addWidget(self.right_splitter)
        self.main_splitter.setStretchFactor(0, 7)
        self.main_splitter.setStretchFactor(1, 3)
        
        self.layout.addWidget(self.main_splitter)