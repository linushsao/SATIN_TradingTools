import pyqtgraph as pg
from PyQt6.QtGui import QPicture, QPainter, QColor, QPen, QBrush
from PyQt6.QtCore import QRectF, QPointF, Qt
import datetime
import pandas as pd
import numpy as np

class DateAxisItem(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timestamps = []

    def update_timestamps(self, ts_list):
        """同步時間戳清單"""
        self.timestamps = ts_list
        self.update()

    def tickStrings(self, values, scale, spacing):
        """
        [修正]: 當 K 棒時間為 00:00 時，顯示日期 (年月日)，否則顯示時間。
        """
        strings = []
        for v in values:
            idx = int(v)
            if 0 <= idx < len(self.timestamps):
                ts = self.timestamps[idx]
                dt_obj = None
                
                try:
                    if isinstance(ts, (pd.Timestamp, datetime.datetime)):
                        dt_obj = ts
                    elif isinstance(ts, str):
                        # 處理帶有毫秒或秒的字串 (例如 2025-12-24 20:40:00)
                        clean_ts = ts.split('.')[0] # 去掉可能存在的毫秒
                        if ' ' in clean_ts:
                            dt_obj = datetime.datetime.strptime(clean_ts, '%Y-%m-%d %H:%M:%S')
                        else:
                            dt_obj = datetime.datetime.strptime(clean_ts, '%Y-%m-%d')
                    elif isinstance(ts, np.datetime64):
                        dt_obj = pd.Timestamp(ts).to_pydatetime()
                except Exception as e:
                    # 如果解析失敗，dt_obj 會是 None，下方會直接 strings.append(str(ts))
                    pass

                if dt_obj:
                    # 判斷是否為 00:00 (跨日點)
                    if dt_obj.hour == 0 and dt_obj.minute == 0:
                        # 顯示年月日 (例如 2025-12-27)
                        strings.append(dt_obj.strftime('%Y-%m-%d'))
                    elif dt_obj.minute % 5 == 0:
                        # 非跨日點，維持每 5 分鐘顯示一次時間標籤
                        strings.append(dt_obj.strftime('%H:%M'))
                    else:
                        strings.append("")
                else:
                    # 如果解析失敗，至少把原始資料轉字串顯示出來，不要顯示空白
                    strings.append(str(ts))
            else:
                strings.append("")
        return strings

class CandlestickItem(pg.GraphicsObject):
    def __init__(self, data):
        pg.GraphicsObject.__init__(self)
        self.data = data # 格式: [(idx, O, C, L, H), ...]
        self.picture = QPicture()
        self.generatePictureStatic()

    def generatePictureStatic(self):
        p = QPainter(self.picture)
        pen_up = QPen(QColor("#ff3333"), 0)
        brush_up = QBrush(QColor("#ff3333"))
        pen_down = QPen(QColor("#00cc00"), 0)
        brush_down = QBrush(QColor("#00cc00"))
        w = 0.3
        
        for (t, open, close, low, high) in self.data:
            if close >= open:
                p.setPen(pen_up); p.setBrush(brush_up)
            else:
                p.setPen(pen_down); p.setBrush(brush_down)
            
            p.drawLine(QPointF(t, low), QPointF(t, high))
            body_h = close - open
            if abs(body_h) < 1e-9:
                p.drawLine(QPointF(t - w, open), QPointF(t + w, open))
            else:
                p.drawRect(QRectF(t - w, open, w * 2, body_h))
        p.end()

    def update_last_bar(self, t, open_val, close_val, low_val, high_val):
        """
        即時更新最後一根 K 棒的數據並重繪圖層。
        """
        # 尋找現有資料中索引值為 t 的項目 (通常是最後一個)
        found = False
        for i in range(len(self.data)-1, -1, -1):
            if self.data[i][0] == t:
                self.data[i] = (t, open_val, close_val, low_val, high_val)
                found = True
                break
        
        # 如果是全新的索引（新 K 棒誕生），則追加
        if not found:
            self.data.append((t, open_val, close_val, low_val, high_val))
            
        # 由於此元件使用 QPicture 緩存，更新數據後必須重新生成 Picture
        self.generatePictureStatic()
        self.update()

    def update_data(self, data):
        self.data = data
        self.generatePictureStatic()
        self.update()

    def paint(self, p, *args):
        self.picture.play(p)

    def boundingRect(self):
        return QRectF(self.picture.boundingRect())