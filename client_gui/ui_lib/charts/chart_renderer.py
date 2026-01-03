import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt

# 統一配色定義，便於未來維護主題切換
RENDER_COLOR_MAP = {
    'cyan': '#00FFFF', 'magenta': '#FF00FF', 'yellow': '#FFFF00', 'white': '#FFFFFF',
    'red': '#FF0000', 'green': '#00FF00', 'blue': '#0000FF', 'orange': '#FFA500', 
    'gray': '#808080', 'black': '#000000'
}

def render_indicator_plots(target_plot, configs, data_len, drawing_list=None):
    """
    解耦後的公用渲染引擎。
    負責將插件生成的配置轉換為 pyqtgraph 物件。
    """
    x_axis = np.arange(data_len)
    
    for cfg in configs:
        data = cfg.get('data')
        kwargs = cfg.get('kwargs', {})
        if data is None or len(data) == 0:
            continue
            
        mpl_color = kwargs.get('color', 'white')
        plot_type = kwargs.get('type', 'line')
        label = kwargs.get('label', '')
        
        # 顏色與畫刷解析
        if isinstance(mpl_color, (list, np.ndarray)):
            brushes = [pg.mkBrush(RENDER_COLOR_MAP.get(c, c)) for c in mpl_color]
            brush = None
        else:
            pg_color = RENDER_COLOR_MAP.get(mpl_color, mpl_color)
            brush = pg.mkBrush(pg_color)
            brushes = None

        item = None
        if plot_type == 'bar':
            # 支援成交量等變色柱狀圖
            item = pg.BarGraphItem(x=x_axis, height=data, width=0.6, brush=brush, brushes=brushes)
        elif plot_type == 'scatter':
            item = pg.ScatterPlotItem(x=x_axis, y=data, size=kwargs.get('size', 8), brush=brush, symbol=kwargs.get('symbol', 'o'))
        else:
            # 線條樣式解析
            style_str = kwargs.get('linestyle', '-')
            pen_style = Qt.PenStyle.SolidLine
            if style_str == '--': pen_style = Qt.PenStyle.DashLine
            elif style_str == ':': pen_style = Qt.PenStyle.DotLine
            
            pen = pg.mkPen(color=pg_color if brush else 'white', width=kwargs.get('width', 1), style=pen_style)
            item = target_plot.plot(x_axis, data, pen=pen, name=label)
            
        if item:
            target_plot.addItem(item)
            if drawing_list is not None:
                drawing_list.append(item)