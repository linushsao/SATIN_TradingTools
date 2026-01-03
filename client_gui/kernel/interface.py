# ==============================================================================
# client_gui/kernel/interface.py
#
# Version: V2.3-000 (Moved)
# 描述:     SATE GUI 外掛標準介面 (原 plugin_interface.py)。
# ==============================================================================

from abc import ABC, abstractmethod
from PyQt6.QtWidgets import QWidget

class ISateGuiPlugin(ABC):
    """SATE GUI 外掛介面規範"""

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """唯一識別碼 (e.g. 'sate.core.live')"""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """顯示在 Tab 上的名稱 (e.g. '🔴 Live Trading')"""
        pass
        
    @property
    def default_area(self) -> str:
        """建議掛載區域: 'main', 'left', 'right', 'bottom' (預設 'main')"""
        return 'main'

    @abstractmethod
    def initialize(self, context):
        """
        初始化外掛。
        Args:
            context (SateClientContext): 提供主程式 API 的上下文物件
        """
        pass

    @abstractmethod
    def get_widget(self) -> QWidget:
        """回傳此功能頁面的主要 Widget 實體"""
        pass

    def on_activate(self):
        """當使用者切換到此分頁時觸發"""
        pass

    def on_deactivate(self):
        """當使用者離開此分頁時觸發"""
        pass

    def on_zmq_event(self, topic: str, payload: dict):
        """
        接收 ZMQ 廣播訊息。
        Args:
            topic: 'TICK', 'KBAR', 'STRATEGY', 'LOG', etc.
            payload: 資料字典
        """
        pass
        
    def cleanup(self):
        """程式關閉時的資源清理"""
        pass