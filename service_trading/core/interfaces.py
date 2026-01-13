# ==============================================================================
# service_trading/core/interfaces.py
#
# Version: V1.2-001 (SSTP Type Hint)
# 更新日期: 2025-12-12
# 描述:     定義 Broker Adapter 標準介面 (IBrokerAdapter)。
#           [修正]: 明確定義 set_callbacks 接收 StandardTick 與 Dict。
# ==============================================================================

from abc import ABC, abstractmethod
from typing import Dict, List, Callable, Any, Optional
from shared.model_defs import StandardOrder, StandardTick, StandardAccount, StandardPosition, StandardAccountSummary

class IBrokerAdapter(ABC):
    """
    Broker Adapter Interface
    定義 SATIN 交易引擎與底層券商 API 之間的標準合約。
    符合 SATIN Standardized Protocol (SSTP)。
    """

    @abstractmethod
    def initialize(self, config: Dict[str, Any]):
        """初始化適配器"""
        pass

    @abstractmethod
    def connect(self, api_key: str, secret_key: str, simulation: bool = True) -> bool:
        """建立 API 連線"""
        pass
    
    @abstractmethod
    def set_callbacks(self, on_tick: Callable[[StandardTick], None], on_order_update: Callable[[Dict], None]):
        """
        設定全域回調函數
        Args:
            on_tick: 接收 StandardTick 物件 (SSTP CAP_DATA_FEED)
            on_order_update: 接收標準化訂單狀態 Dict (SSTP CAP_EXECUTION)
        """
        pass

    # --- Market Data Methods ---

    @abstractmethod
    def subscribe_market_data(self, contract_code: str) -> bool:
        """訂閱行情"""
        pass

    @abstractmethod
    def unsubscribe_market_data(self, contract_code: str) -> bool:
        """取消訂閱行情"""
        pass
    
    @abstractmethod
    def download_history(self, contract_code: str, start_date: str, end_date: str) -> Any:
        """下載歷史數據"""
        pass

    @abstractmethod
    def get_contracts(self) -> List[Dict[str, Any]]:
        """取得可交易商品列表"""
        pass

    # --- Trading Methods ---

    @abstractmethod
    def place_order(self, order: StandardOrder) -> str:
        """下單"""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """刪單"""
        pass

    # --- Account Methods ---

    @abstractmethod
    def get_account_data(self, account_type: str = "future") -> StandardAccount:
        """取得帳戶資金與權益"""
        pass

    @abstractmethod
    def get_positions(self, account_type: str = "future") -> List[StandardPosition]:
        """取得部位列表"""
        pass
        
    @abstractmethod
    def list_available_accounts(self) -> List[StandardAccountSummary]:
        """列出該連線下所有可用帳號"""
        pass