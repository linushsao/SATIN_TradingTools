import pandas as pd
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSplitter, QLabel
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import Qt

# --- 關鍵修正：從共用庫引用 ---
from ui_lib.chart_items import DateAxisItem, CandlestickItem

COLOR_MAP = {
    'red': '#ff3333', 'green': '#00cc00', 'blue': '#3366ff',
    'yellow': '#ffff33', 'white': '#ffffff', 'cyan': '#00ffff',
    'magenta': '#ff00ff', 'gray': '#808080', 'orange': '#ffa500'
}

class StaticChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.layout.addWidget(self.splitter)
        
        self.y_axis_width = 45
        self.y_axis_padding = 0.1 
        self.subchart_buffer = 1.25 
        self.current_code = "--"
        self.current_freq = "--"
        self.timestamps = []
        self.df_data = None  # 關鍵修正：確保屬性存在於實體中
        self.indicator_items = [] # 新增：追蹤插件產生的圖元，便於清理
        
        # --- 建立自定義時間軸 ---
        self.axis_date = DateAxisItem(orientation='bottom')
        self.p_main_widget = pg.PlotWidget(axisItems={'bottom': self.axis_date})
        self.p_main = self.p_main_widget.getPlotItem()
        self.p_main.showGrid(x=True, y=True, alpha=0.3)
        self.p_main.getAxis('left').setWidth(self.y_axis_width)
        
        # HUD 標籤初始化
        self.info_label = QLabel(self.p_main_widget)
        self.info_label.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 180);
                color: #e0e0e0;
                font-family: 'Consolas', 'Monospace';
                font-size: 12px;
                padding: 6px;
                border-radius: 4px;
            }
        """)
        self.info_label.move(50, 5)
        
        self.p_main.sigXRangeChanged.connect(self._on_x_range_changed)
        self.proxy = pg.SignalProxy(self.p_main.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved)
        
        self.splitter.addWidget(self.p_main_widget)
        self.subplots_items = {}
        self.subplots_widgets = {}
        self.subplots_data = {}  # [NEW] 紀錄副圖資料，用於自動縮放 Y 軸

    # --- 補回缺失的 API 函式 ---
    def set_info_meta(self, code, freq):
        self.current_code = str(code)
        self.current_freq = str(freq)
        self._update_hud_text()

    def set_y_axis_width(self, width):
        """補回 Loader 需要的屬性"""
        self.y_axis_width = int(width)
        self.p_main.getAxis('left').setWidth(self.y_axis_width)
        self.info_label.move(self.y_axis_width + 5, 5)
        for p in self.subplots_items.values():
            p.getAxis('left').setWidth(self.y_axis_width)

    def set_auto_scale_padding(self, padding_percent):
        """補回 Loader 需要的屬性"""
        self.y_axis_padding = float(padding_percent) / 100.0
        self._on_x_range_changed()

    def add_subplot(self, name):
        """補回子圖支援，子圖也需要自己的 DateAxisItem 以保持同步"""
        if name in self.subplots_items:
            return self.subplots_items[name]
        
        # 子圖也掛載 DateAxisItem 以確保 X 軸標籤一致
        sub_axis = DateAxisItem(orientation='bottom')
        w_sub = pg.PlotWidget(axisItems={'bottom': sub_axis})
        p_sub = w_sub.getPlotItem()
        p_sub.setXLink(self.p_main)
        p_sub.showGrid(x=True, y=True, alpha=0.3)
        p_sub.getAxis('left').setWidth(self.y_axis_width)
        
        self.splitter.addWidget(w_sub)
        self.subplots_items[name] = p_sub
        self.subplots_widgets[name] = w_sub
        self._balance_splitter()
        
        # 如果已有時間資料，立即同步給子圖
        if self.timestamps:
            sub_axis.update_timestamps(self.timestamps)
            
        return p_sub

    def _balance_splitter(self):
        total = self.splitter.count()
        if total > 1:
            height = self.height() if self.height() > 0 else 600
            main_h = int(height * 0.7)
            sub_h = int((height * 0.3) / (total - 1))
            self.splitter.setSizes([main_h] + [sub_h] * (total - 1))

# --- 資料載入核心 (修正重複覆蓋版) ---
    def load_dataframe(self, df):
        """
        修正資料載入流程，確保 df_data 優先被定義。
        """
        self.clear()
        if df is None or df.empty:
            return

        # 步驟 1: 提取時間戳記
        possible_time_cols = ['Date', 'datetime', 'date', 'Time', 'time']
        target_col = next((c for c in possible_time_cols if c in df.columns), None)

        if target_col:
            self.timestamps = df[target_col].tolist()
        elif isinstance(df.index, pd.DatetimeIndex):
            self.timestamps = df.index.tolist()
        else:
            self.timestamps = [str(x) for x in df.index.tolist()]

        # 步驟 2: 統一屬性賦值
        self.df_data = df.reset_index(drop=True)
        
        # 步驟 3: 同步座標軸
        self.axis_date.update_timestamps(self.timestamps)
        for p in self.subplots_items.values():
            p.getAxis('bottom').update_timestamps(self.timestamps)

        # 步驟 4: 繪製 K 線
        d = self.df_data
        data_list = []
        for i in range(len(d)):
            data_list.append((float(i), float(d['Open'][i]), float(d['Close'][i]), 
                              float(d['Low'][i]), float(d['High'][i])))
            
        candle = CandlestickItem(data_list)
        self.p_main.addItem(candle)
        self.p_main.autoRange()
        self._update_hud_text(len(self.df_data) - 1)

    def clear(self):
        """
        完整清理主圖、子圖及所有動態指標。
        """
        # 清理追蹤的指標圖元
        for item in self.indicator_items:
            try:
                self.p_main.removeItem(item)
            except:
                pass
        self.indicator_items.clear()
        
        # 清理主圖與子圖 Widget
        self.p_main.clear()
        for widget in self.subplots_widgets.values():
            widget.setParent(None)
            widget.deleteLater()
            
        self.subplots_items = {}
        self.subplots_widgets = {}
        self.subplots_data = {}  # [NEW] 清理副圖資料追蹤        
        self.timestamps = []
        self.df_data = None

    def _on_mouse_moved(self, evt):
        pos = evt[0]
        if self.p_main.sceneBoundingRect().contains(pos):
            mouse_point = self.p_main.vb.mapSceneToView(pos)
            index = int(np.round(mouse_point.x()))
            self._update_hud_text(index)

    def _update_hud_text(self, index=None):
        """
        [修正] 更新 HUD 文字內容：
        1. 時間顯示修正為統一格式：日期 + 時間 (YYYY-MM-DD HH:MM)。
        2. 移除秒數顯示。
        """
        if self.df_data is None or self.df_data.empty:
            self.info_label.setText(f"[{self.current_code}] No Data")
            return
            
        # 確保索引在有效範圍內
        if index is None or index < 0 or index >= len(self.df_data):
            index = len(self.df_data) - 1
            
        # 取得該索引的數據行與時間戳記
        row = self.df_data.iloc[index]
        o, h, l, c = row['Open'], row['High'], row['Low'], row['Close']
        
        # 取得對應索引的時間戳記
        ts_val = self.timestamps[index]
        
        # 統一格式化為：YYYY-MM-DD HH:MM
        if hasattr(ts_val, 'strftime'):
            ts_str = ts_val.strftime('%Y-%m-%d %H:%M')
        else:
            # 防禦性處理：若為字串則嘗試擷取前 16 碼 (YYYY-MM-DD HH:MM)
            ts_str = str(ts_val)[:16]
        
        # 決定收盤價顏色 (漲紅跌綠)
        color_hex = "#ff5555" if c >= o else "#55ff55"
        
        # 建構統一格式的 HUD 字串 
        info_str = (
            f"<span style='color:#ffffff; font-weight:bold;'>{self.current_code}</span> "
            f"<span style='color:#cccccc;'>{self.current_freq}</span> "
            f"<span style='color:#cccccc;'>({ts_str})</span> "
            f"O:{o:.2f} H:{h:.2f} L:{l:.2f} "
            f"C:<span style='color:{color_hex};'>{c:.2f}</span>"
        )
        
        self.info_label.setText(f"<html>{info_str}</html>")
        self.info_label.adjustSize()
        
    def _on_x_range_changed(self):
        """
        [修正] X 軸範圍變動事件：
        1. 自動縮放主圖 Y 軸 (OHLC)。
        2. 自動縮放副圖 Y 軸，並針對 Volume 進行顯示優化。
        """
        if self.df_data is None or self.df_data.empty: return
        x_range = self.p_main.getViewBox().viewRange()[0]
        idx_min = max(0, int(np.floor(x_range[0])))
        idx_max = min(len(self.df_data), int(np.ceil(x_range[1])))
        if idx_min >= idx_max: return
        
        # 1. 縮放主圖
        visible_data = self.df_data.iloc[idx_min:idx_max]
        v_high, v_low = visible_data['High'].max(), visible_data['Low'].min()
        p_range = v_high - v_low
        if p_range == 0: p_range = 1.0
        padding = p_range * self.y_axis_padding
        self.p_main.setYRange(v_low - padding, v_high + padding, padding=0)
        
        # 2. 縮放副圖 (Subplots)
        for name, p_sub in self.subplots_items.items():
            if p_sub in self.subplots_data:
                data_list = self.subplots_data[p_sub]
                s_min, s_max = float('inf'), float('-inf')
                found_valid = False
                
                for ds in data_list:
                    # 擷取可視範圍數據
                    v_ds = ds[idx_min:idx_max]
                    valid_mask = ~np.isnan(v_ds)
                    if np.any(valid_mask):
                        s_min = min(s_min, np.min(v_ds[valid_mask]))
                        s_max = max(s_max, np.max(v_ds[valid_mask]))
                        found_valid = True
                
                if found_valid:
                    # 針對成交量 (Volume) 副圖進行優化
                    if "VOLUME" in name.upper():
                        # 成交量固定從 0 開始，並在上方預留空間 (s_max * self.subchart_buffer) 確保不頂格
                        p_sub.setYRange(0, s_max * self.subchart_buffer, padding=0)
                    else:
                        diff = s_max - s_min
                        if diff == 0: diff = 1.0
                        sub_pad = diff * self.y_axis_padding
                        p_sub.setYRange(s_min - sub_pad, s_max + sub_pad, padding=0)

    def _render_plots(self, configs, target_plot, drawing_list, data_collection=None, label_prefix=""):
        """
        [修正] 從 Backtest 移植並優化的通用繪圖渲染器。
        增加副圖資料追蹤功能。
        """
        import numpy as np
        import pyqtgraph as pg
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QColor

        # 建立 X 軸索引
        x_axis = np.arange(len(self.df_data))
        
        # 建立內部顏色對照表 (確保繪圖引擎獨立運作)
        INTERNAL_COLOR_MAP = {
            'cyan': '#00FFFF', 'magenta': '#FF00FF', 'yellow': '#FFFF00', 'white': '#FFFFFF',
            'red': '#FF0000', 'green': '#00FF00', 'blue': '#0000FF', 'orange': '#FFA500', 
            'gray': '#808080', 'black': '#000000'
        }

        # [NEW] 若為副圖，初始化資料列表
        if target_plot != self.p_main:
            if target_plot not in self.subplots_data:
                self.subplots_data[target_plot] = []

        for cfg in configs:
            data = cfg.get('data')
            kwargs = cfg.get('kwargs', {})
            if data is None or len(data) == 0: continue
            
            label = kwargs.get('label', label_prefix)
            mpl_color = kwargs.get('color', 'white')
            
            # 顏色名稱解析
            if isinstance(mpl_color, (list, np.ndarray)):
                pg_color = '#FFFFFF' # 預設色
            else:
                pg_color = INTERNAL_COLOR_MAP.get(mpl_color, mpl_color)
            
            width = kwargs.get('linewidth', kwargs.get('width', 1))
            style_str = kwargs.get('linestyle', '-')
            plot_type = kwargs.get('type', 'line')
            item = None

            # --- Bar 繪製邏輯 ---
            if plot_type == 'bar':
                if isinstance(mpl_color, (list, np.ndarray)):
                    brushes = [pg.mkBrush(INTERNAL_COLOR_MAP.get(c, c)) for c in mpl_color]
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
                # [NEW] 紀錄副圖數據供後續縮放計算
                if target_plot != self.p_main:
                    self.subplots_data[target_plot].append(data)