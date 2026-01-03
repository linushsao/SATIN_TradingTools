# ==============================================================================
# client_gui/ui_lib/code_editor.py
#
# Version: V1.1-001 (Shortcut Support)
# 更新日期: 2025-12-24
# 描述:     進階程式碼編輯器組件。
#           [新增]: 實作 PythonHighlighter 提供語法著色功能。
#           [新增]: 實作 is_dirty 狀態追蹤與 sig_changed 訊號。
#           [新增]: 實作 Ctrl+S 快捷鍵發送儲存請求。
# ==============================================================================

#from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit
#from PyQt6.QtGui import QFont, QColor, QFontMetrics
#from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QTextEdit
#from PyQt6.QtGui import (QFont, QColor, QFontMetrics, QSyntaxHighlighter, 
#                         QTextCharFormat, QColor, QPainter, QTextFormat)
from PyQt6.QtGui import (QFont, QColor, QFontMetrics, QSyntaxHighlighter, 
                         QTextCharFormat, QColor, QPainter, QTextFormat,
                         QKeySequence, QShortcut)
from PyQt6.QtCore import Qt, QRect, QSize, pyqtSignal
import re

class PythonHighlighter(QSyntaxHighlighter):
    """Python 語法高亮度著色器"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []

        # 關鍵字樣式
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569cd6")) # Blue
        keyword_format.setFontWeight(QFont.Weight.Bold)
        keywords = [
            "and", "as", "assert", "break", "class", "continue", "def", "del",
            "elif", "else", "except", "False", "finally", "for", "from", "global",
            "if", "import", "in", "is", "lambda", "None", "nonlocal", "not",
            "or", "pass", "raise", "return", "True", "try", "while", "with", "yield"
        ]
        for word in keywords:
            pattern = re.compile(r'\b' + word + r'\b')
            self.highlighting_rules.append((pattern, keyword_format))

        # 字串樣式
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#ce9178")) # Orange/Brown
        self.highlighting_rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'), string_format))
        self.highlighting_rules.append((re.compile(r"'[^'\\]*(\\.[^'\\]*)*'"), string_format))

        # 註解樣式
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6a9955")) # Green
        self.highlighting_rules.append((re.compile(r'#[^\n]*'), comment_format))

        # 類別/函式定義
        def_format = QTextCharFormat()
        def_format.setForeground(QColor("#dcdcaa")) # Yellow
        self.highlighting_rules.append((re.compile(r'\bdef\s+(\w+)'), def_format))
        self.highlighting_rules.append((re.compile(r'\bclass\s+(\w+)'), def_format))

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), format)

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.lineNumberAreaPaintEvent(event)

class CodeEditor(QPlainTextEdit):
    sig_changed = pyqtSignal(bool) # 發送是否有未儲存變更的訊號
    sig_save_request = pyqtSignal() # 發送儲存請求 (Ctrl+S)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.highlighter = PythonHighlighter(self.document())
        self.is_dirty = False
        self.current_file_path = ""
        
        # 設定字型
        #font = QFont("Consolas", 10)
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        
        # 設定 Tab 寬度 (4個空格)
        self.setTabStopDistance(QFontMetrics(font).horizontalAdvance(' ') * 4)
        
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.textChanged.connect(self._on_text_changed)
        # 設定快捷鍵
        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_save.activated.connect(self.sig_save_request.emit)
        
        self.update_line_number_area_width(0)
        self.highlight_current_line()

    def line_number_area_width(self):
        digits = 1
        max_value = max(1, self.blockCount())
        while max_value >= 10:
            max_value //= 10
            digits += 1
        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def lineNumberAreaPaintEvent(self, event):
        #from PyQt6.QtGui import QPainter, QColor
        painter = QPainter(self.line_number_area)
        #painter.fillRect(event.rect(), QColor("#f0f0f0")) # 背景色
        painter.fillRect(event.rect(), QColor("#2b2b2b")) # 行號區背景 (深色)

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                #painter.setPen(Qt.GlobalColor.black)
                painter.setPen(QColor("#858585")) # 行號字體顏色
                painter.drawText(0, top, self.line_number_area.width() - 2, self.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight, number)
            
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def highlight_current_line(self):
        #from PyQt6.QtWidgets import QTextEdit
        #from PyQt6.QtGui import QTextFormat, QColor
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            #line_color = QColor("#e8f2fe")
            line_color = QColor("#2c2c2c") # 當前行高亮
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        self.setExtraSelections(extra_selections)

    def _on_text_changed(self):
        if not self.is_dirty:
            self.is_dirty = True
            self.sig_changed.emit(True)

    # --- 介面方法供外部呼叫 ---
    def load_file(self, path, content):
        self.current_file_path = path        
        self.setPlainText(content)
        self.is_dirty = False
        self.sig_changed.emit(False)

    def set_saved(self):
        self.is_dirty = False
        self.sig_changed.emit(False)

    def get_content(self):
        return self.toPlainText()