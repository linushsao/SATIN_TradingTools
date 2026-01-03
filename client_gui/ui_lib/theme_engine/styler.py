# ==============================================================================
# ui_lib/theme_engine/styler.py (V0.1-033 Patch)
# ==============================================================================

class ThemeStyler:
    @staticmethod
    def get_qss(theme: dict):
        base_qss = f"""
            QMainWindow, QDialog, QWidget {{
                background-color: {theme['bg']};
                color: {theme['text']};
                font-family: "Segoe UI", "Microsoft JhengHei";
                font-size: 10pt;
            }}
            
            QLabel#PanelHeader {{
                background-color: {theme['panel']};
                color: {theme['accent']};
                font-weight: bold;
                padding-left: 10px;
                border-bottom: 1px solid {theme['border']};
            }}
            
            QWidget#ControlBar, QWidget#InjectionBar {{
                background-color: {theme['panel']};
                border: 1px solid {theme['border']};
            }}

            /* --- 表格隱形問題修正區 --- */
            QTableWidget {{
                background-color: {theme['bg']};
                alternate-background-color: {theme['panel']};
                color: {theme['text']};
                gridline-color: {theme['border']};
                border: none;
            }}
            QHeaderView::section {{
                background-color: {theme['panel']};
                color: {theme['accent']};
                padding: 4px;
                border: 1px solid {theme['border']};
                font-weight: bold;
            }}
            /* ------------------------ */

            QPushButton {{
                background-color: {theme['panel']};
                border: 1px solid {theme['border']};
                padding: 5px 15px;
                border-radius: 3px;
            }}
            QPushButton:hover {{
                background-color: {theme['accent']};
                color: white;
            }}

            QSplitter::handle {{ background-color: {theme['border']}; }}
            QSplitter::handle:horizontal {{ width: 2px; }}
            QSplitter::handle:vertical {{ height: 2px; }}
            
            QTextEdit, QLineEdit {{
                background-color: #000000;
                color: #00ff00;
                font-family: "Consolas";
                border: 1px solid {theme['border']};
            }}
        """
        return base_qss