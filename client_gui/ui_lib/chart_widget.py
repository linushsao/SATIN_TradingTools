# ==============================================================================
# client_gui/ui_lib/chart_widget.py
#
# Version: V1.3-002 (Fix KeyError)
# 更新日期: 2025-12-16
# 描述: 通用靜態 K 線圖表元件 (Static K-Line Chart Component)。
#           [修正]: 
#             1. load_dataframe 增加欄位正規化，自動將 open/close 等轉為 Open/Close。
#             2. 增加必要欄位檢查，防止 KeyError。
# ==============================================================================

import sys
import os
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QSplitter, QApplication)
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QColor, QFont, QPen, QBrush

# 嘗試引用專案內的 chart_items
try:
    from .chart_items import CandlestickItem, DateAxisItem
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    try:
        from chart_items import CandlestickItem, DateAxisItem
    except ImportError:
        print("[ChartWidget] Error: chart_items.py not found.")
        sys.exit(1)

# 設定全域顏色
COLOR_UP = "#FF5555"   # 紅K (漲)
COLOR_DOWN = "#55FF55" # 綠K (跌)
COLOR_BG = "#000000"   # 背景黑
COLOR_FG = "#d4d4d4"   # 前景灰
Y_AXIS_WIDTH = 60

# 顏色名稱映射
COLOR_MAP = {
    'cyan': '#00FFFF', 'magenta': '#FF00FF', 'yellow': '#FFFF00', 'white': '#FFFFFF',
    'red': '#FF0000', 'green': '#00FF00', 'blue': '#0000FF', 'orange': '#FFA500', 
    'gray': '#808080', 'black': '#000000'
}

class StaticChartWidget(QWidget):
    """
    靜態 K 線圖表元件。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 1. 基礎佈局
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # 全域設定
        pg.setConfigOption('background', COLOR_BG)
        pg.setConfigOption('foreground', COLOR_FG)
        pg.setConfigOption('antialias', False) 
        
        # [NEW] Top Info Bar
        self.lbl_top_info = QLabel("")
        self.lbl_top_info.setStyleSheet("""
            QLabel {
                background-color: #1e1e1e; 
                color: #d4d4d4; 
                padding: 4px;
                font-family: Consolas, Monospace;
                font-size: 13px;
                border-bottom: 1px solid #333;
            }
        """)
        self.lbl_top_info.setFixedHeight(28)
        self.layout.addWidget(self.lbl_top_info)
        
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.layout.addWidget(self.splitter)
        
        # 2. 資料容器
        self.df_data = pd.DataFrame()
        self.timestamps = []
        self.info_code = ""
        self.info_freq = ""
        
        self.main_drawings = [] 
        self.indicator_plots = [] 
        
        # 3. 建立圖表元件
        self._init_charts()
        
        # 4. 建立互動元件
        self._init_overlays()

    def _init_charts(self):
        # --- 主圖 (K線) ---
        self.axis_date = DateAxisItem(orientation='bottom')
        self.pw_main = pg.PlotWidget(axisItems={'bottom': self.axis_date})
        self.plot_main = self.pw_main.getPlotItem()
        self.plot_main.showGrid(x=True, y=True, alpha=0.2)
        self.plot_main.getAxis('left').setWidth(Y_AXIS_WIDTH)
        self.plot_main.setLabel('left', 'Price')
        
        self.splitter.addWidget(self.pw_main)
        # [MOD] 移除預設 Volume 副圖 (改由 add_indicator 動態產生)
        
    def _init_overlays(self):
        # 十字線
        self.v_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('gray', style=Qt.PenStyle.DashLine, width=0.8))
        self.h_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('gray', style=Qt.PenStyle.DashLine, width=0.8))
        self.plot_main.addItem(self.v_line, ignoreBounds=True)
        self.plot_main.addItem(self.h_line, ignoreBounds=True)
        self.v_line.hide()
        self.h_line.hide()
        
        self.proxy = pg.SignalProxy(self.plot_main.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_move)

    def set_info(self, code, freq):
        """設定合約與週期資訊"""
        self.info_code = code
        self.info_freq = freq
        # 若有資料，更新顯示最後一根
        if not self.df_data.empty:
            self._update_hud(len(self.df_data) - 1)

    def clear(self):
        self.df_data = pd.DataFrame()
        self.timestamps = []
        
        self.plot_main.clear()
        self.main_drawings = []
        
        for widget in self.indicator_plots:
            widget.hide()
            widget.deleteLater()
        self.indicator_plots = []
        
        self.plot_main.addItem(self.v_line, ignoreBounds=True)
        self.plot_main.addItem(self.h_line, ignoreBounds=True)
        
        self.lbl_top_info.setText("")

    def _add_subplot(self, label="Ind"):
        axis = DateAxisItem(orientation='bottom')
        pw = pg.PlotWidget(axisItems={'bottom': axis})
        plot = pw.getPlotItem()
        plot.showGrid(x=True, y=True, alpha=0.2)
        plot.getAxis('left').setWidth(Y_AXIS_WIDTH)
        plot.setLabel('left', label)
        plot.setMaximumHeight(150)
        plot.setXLink(self.plot_main)
        
        v_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('gray', style=Qt.PenStyle.DashLine, width=0.8))
        plot.addItem(v_line, ignoreBounds=True)
        v_line.hide()
        
        pw.v_line = v_line 
        self.indicator_plots.append(pw)
        self.splitter.addWidget(pw)
        self.splitter.setStretchFactor(self.splitter.count()-1, 1)
        
        if self.timestamps:
            axis.update_timestamps(self.timestamps)
        
        return plot

    def add_indicator(self, data_series, **kwargs):
        if self.df_data.empty: return

        panel = kwargs.get('panel', 'main')
        label = kwargs.get('label', 'Ind')
        
        target_plot = self.plot_main
        if panel == 'lower':
            target_plot = self._add_subplot(label)
        
        c_name = kwargs.get('color', 'white')
        color_hex = COLOR_MAP.get(c_name, c_name)
        if not str(color_hex).startswith('#'): color_hex = '#FFFFFF'
        
        line_width = kwargs.get('width', kwargs.get('linewidth', 1))
        style_str = kwargs.get('linestyle', '-')
        
        pen_style = Qt.PenStyle.SolidLine
        if style_str == '--': pen_style = Qt.PenStyle.DashLine
        elif style_str == ':': pen_style = Qt.PenStyle.DotLine
        
        pen = pg.mkPen(color=color_hex, width=line_width, style=pen_style)
        brush = pg.mkBrush(color=color_hex)
        
        x_axis = np.arange(len(data_series))
        if hasattr(data_series, 'values'):
            y_values = data_series.values
        else:
            y_values = np.array(data_series)
        
        if len(y_values) < len(self.df_data):
            pad = np.full(len(self.df_data) - len(y_values), np.nan)
            y_values = np.concatenate((pad, y_values))
        elif len(y_values) > len(self.df_data):
            y_values = y_values[-len(self.df_data):]

        plot_type = kwargs.get('type', 'line')
        try:
            if plot_type == 'bar':
                item = pg.BarGraphItem(x=x_axis, height=y_values, width=0.6, brush=brush)
                target_plot.addItem(item)
            elif plot_type == 'scatter':
                mask = ~np.isnan(y_values)
                if np.any(mask):
                    item = pg.ScatterPlotItem(x=x_axis[mask], y=y_values[mask], size=8, brush=brush, pen=None)
                    target_plot.addItem(item)
            else: 
                item = target_plot.plot(x_axis, y_values, pen=pen, name=label)
        except Exception as e:
            print(f"[Chart] Add indicator failed: {e}")

    def zoom_to_last(self, n_bars=300):
        if self.df_data.empty: return
        total = len(self.df_data)
        start = max(0, total - n_bars)
        self.plot_main.setXRange(start, total, padding=0)
        
        visible_df = self.df_data.iloc[start:total]
        if not visible_df.empty:
            y_min = visible_df['Low'].min()
            y_max = visible_df['High'].max()
            if not pd.isna(y_min) and not pd.isna(y_max):
                self.plot_main.setYRange(y_min, y_max, padding=0.05)

    def load_dataframe(self, df):
        """
        載入 Pandas DataFrame (Index 為 datetime, 欄位需含 Open,High,Low,Close)
        """
        self.clear()
        if df is None or df.empty: return
        
        # [FIX] 欄位正規化 (Standardization)
        df_clean = df.copy()
        
        # 1. 處理 Index (若 ts 在欄位中)
        if 'ts' in df_clean.columns and not isinstance(df_clean.index, pd.DatetimeIndex):
            df_clean['ts'] = pd.to_datetime(df_clean['ts'])
            df_clean.set_index('ts', inplace=True)
            
        # 2. 統一欄位名稱為 Title Case (Open, High, Low, Close, Volume)
        col_map = {
            'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 
            'volume': 'Volume', 'vol': 'Volume', 'amount': 'Amount',
            'OPEN': 'Open', 'HIGH': 'High', 'LOW': 'Low', 'CLOSE': 'Close', 'VOLUME': 'Volume'
        }
        df_clean.rename(columns=col_map, inplace=True)
        
        # 3. 檢查必要欄位
        req_cols = ['Open', 'High', 'Low', 'Close']
        if not all(c in df_clean.columns for c in req_cols):
            missing = [c for c in req_cols if c not in df_clean.columns]
            print(f"[ChartWidget] Error: Missing required columns: {missing}. Available: {list(df_clean.columns)}")
            return # Abort loading to prevent partial state and future crash

        self.df_data = df_clean
        
        # 處理時間軸
        if 'ts' in df_clean.columns: # fallback if index failed
            self.timestamps = df_clean['ts'].tolist()
        else:
            self.timestamps = df_clean.index.tolist()
            
        self.axis_date.update_timestamps(self.timestamps)
        for w in self.indicator_plots:
            w.getPlotItem().getAxis('bottom').update_timestamps(self.timestamps)
            
        # 繪製 K 線
        quotes = []
        try:
            for i in range(len(df_clean)):
                row = df_clean.iloc[i]
                quotes.append((i, row['Open'], row['Close'], row['Low'], row['High']))
                
            candle_item = CandlestickItem(quotes)
            self.plot_main.addItem(candle_item)
            self.main_drawings.append(candle_item)
            
            # 更新 Top Bar
            self._update_hud(len(df_clean)-1)
            
        except Exception as e:
            print(f"[ChartWidget] Draw K-Line failed: {e}")
            self.clear() # Rollback

    def _on_mouse_move(self, evt):
        if self.df_data.empty: return
        pos = evt[0]
        if self.plot_main.sceneBoundingRect().contains(pos):
            mouse_point = self.plot_main.vb.mapSceneToView(pos)
            index = int(mouse_point.x())
            
            if 0 <= index < len(self.df_data):
                self._update_hud(index)
                
                # 同步十字線
                self.v_line.setPos(mouse_point.x())
                self.h_line.setPos(mouse_point.y())
                self.v_line.show()
                self.h_line.show()
                
                for w in self.indicator_plots:
                    if hasattr(w, 'v_line'):
                        w.v_line.setPos(mouse_point.x())
                        w.v_line.show()
            else:
                self.v_line.hide(); self.h_line.hide()
                for w in self.indicator_plots:
                    if hasattr(w, 'v_line'): w.v_line.hide()

    def _update_hud(self, index):
        if index < 0 or index >= len(self.df_data): return
        
        try:
            row = self.df_data.iloc[index]
            
            ts_val = self.timestamps[index]
            if isinstance(ts_val, (pd.Timestamp, pd.DatetimeIndex)):
                ts_str = ts_val.strftime('%Y-%m-%d %H:%M')
            else:
                ts_str = str(ts_val)
            
            # [FIX] Use .get or ensure 'Close' exists via load_dataframe validation
            close_price = row.get('Close', 0)
            open_price = row.get('Open', 0)
            
            c_color = COLOR_UP if close_price >= open_price else COLOR_DOWN
            
            # 格式化 Top Bar
            # [CODE] [FREQ] TIME | O: H: L: C: V:
            txt = f"<span style='color: #4ec9b0; font-weight: bold;'>{self.info_code}</span> "
            txt += f"<span style='color: #dcdcaa;'>[{self.info_freq}]</span> "
            txt += f"<span style='color: #cccccc;'>{ts_str}</span> &nbsp;|&nbsp; "
            txt += f"O: <span style='color: #d4d4d4;'>{open_price:.0f}</span> "
            txt += f"H: <span style='color: #d4d4d4;'>{row.get('High', 0):.0f}</span> "
            txt += f"L: <span style='color: #d4d4d4;'>{row.get('Low', 0):.0f}</span> "
            txt += f"C: <span style='color: {c_color}; font-weight: bold;'>{close_price:.0f}</span> "
            
            if 'Volume' in row:
                txt += f"V: <span style='color: #d4d4d4;'>{int(row['Volume'])}</span>"
                
            self.lbl_top_info.setText(txt)
        except Exception as e:
            # Silent fail for HUD updates to prevent spamming errors during mouse move
            pass
            
    def _render_plots(self, configs, target_plot, drawing_list, data_collection=None, label_prefix=""):
            """
            [NEW] 從 Backtest 移植並優化的通用繪圖渲染器
            支援處理 ADDPLOT_CONFIG 結構，並解決 Bar 無法變色或顯示的問題。
            """
            import numpy as np
            import pyqtgraph as pg
            from PyQt6.QtCore import Qt
            from PyQt6.QtGui import QColor

            # 建立 X 軸索引
            x_axis = np.arange(len(self.df_data))
            
            for cfg in configs:
                data = cfg.get('data')
                kwargs = cfg.get('kwargs', {})
                if data is None or len(data) == 0: continue
                
                label = kwargs.get('label', label_prefix)
                mpl_color = kwargs.get('color', 'white')
                
                # 顏色處理
                if isinstance(mpl_color, (list, np.ndarray)):
                    pg_color = '#FFFFFF' # 預設色
                else:
                    pg_color = COLOR_MAP.get(mpl_color, mpl_color)
                
                width = kwargs.get('linewidth', kwargs.get('width', 1))
                style_str = kwargs.get('linestyle', '-')
                plot_type = kwargs.get('type', 'line')
                item = None

                # --- Bar 繪製邏輯 (支持動態變色) ---
                if plot_type == 'bar':
                    if isinstance(mpl_color, (list, np.ndarray)):
                        # 將指標腳本傳入的顏色名稱陣列轉為十六進位清單
                        brushes = [pg.mkBrush(COLOR_MAP.get(c, c)) for c in mpl_color]
                        item = pg.BarGraphItem(x=x_axis, height=data, width=0.6, brushes=brushes)
                    else:
                        brush = pg.mkBrush(pg_color)
                        item = pg.BarGraphItem(x=x_axis, height=data, width=0.6, brush=brush)
                    target_plot.addItem(item)

                # --- Scatter 繪製邏輯 ---
                elif plot_type == 'scatter':
                    symbol = kwargs.get('symbol', 'o')
                    size = kwargs.get('size', 8)
                    brush = pg.mkBrush(pg_color)
                    item = pg.ScatterPlotItem(x=x_axis, y=data, size=size, brush=brush, symbol=symbol)
                    target_plot.addItem(item)
                    
                # --- Line 繪製邏輯 ---
                else:
                    pen_style = Qt.PenStyle.SolidLine
                    if style_str == '--': pen_style = Qt.PenStyle.DashLine
                    elif style_str == ':': pen_style = Qt.PenStyle.DotLine
                    
                    pen = pg.mkPen(color=pg_color, width=width, style=pen_style)
                    item = target_plot.plot(x_axis, data, pen=pen, name=label)
                
                if item:
                    drawing_list.append(item)            