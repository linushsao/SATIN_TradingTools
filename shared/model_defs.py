# ==============================================================================
# shared/model_defs.py
#
# Version: V1.2-000 (SSTP Impl)
# 更新日期: 2025-12-12
# 描述:     SATIN 系統標準資料模型定義。
#           [新增]: 各 DataClass 新增 to_sstp_dict() 方法，支援 SATIN 標準化協定 (SSTP)。
#           [修正]: StandardPosition 轉換時統一將 'Short' 方向轉為負數數量。
# ==============================================================================

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import datetime

# --- Constants / Enums ---\

class OrderAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    ROD = "ROD"
    IOC = "IOC"
    FOK = "FOK"

class PriceType(str, Enum):
    LMT = "LMT"  # 限價
    MKT = "MKT"  # 市價

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PART_FILLED = "PART_FILLED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"

# --- Data Classes ---\

@dataclass
class StandardTick:
    """標準行情資料 (Tick)"""
    code: str
    ts: float                   # Unix Timestamp
    datetime_str: str           # Format: YYYY-MM-DD HH:MM:SS.ffffff
    close: float
    volume: int
    amount: float = 0.0
    bid_price: float = 0.0
    bid_volume: int = 0
    ask_price: float = 0.0
    ask_volume: int = 0
    sim_trade: bool = False     # 是否為試搓

    def to_sstp_dict(self) -> dict:
        """
        轉換為 SATIN 標準協定 (CAP_DATA_FEED) 格式
        Format: { "ts": float, "code": str, "price": float, "vol": int, "bid": float, "ask": float }
        """
        return {
            "ts": self.ts,
            "code": self.code,
            "price": self.close,
            "vol": self.volume,
            "bid": self.bid_price,
            "ask": self.ask_price
        }

@dataclass
class StandardOrder:
    """標準委託單 (Order)"""
    code: str
    action: OrderAction
    price: float
    quantity: int
    price_type: PriceType = PriceType.LMT
    order_type: OrderType = OrderType.ROD
    id: Optional[str] = None    # Order ID (由券商回傳後填入)
    tag: str = ""               # 策略標記或備註
    status: OrderStatus = OrderStatus.UNKNOWN
    filled_qty: int = 0
    avg_price: float = 0.0
    msg: str = ""

    def to_sstp_request(self) -> dict:
        """
        轉換為 SSTP 下單指令格式
        Format: { "action": "BUY"|"SELL", "code": str, "qty": int, "price": float, "type": "LMT"|"MKT" }
        """
        return {
            "action": self.action.value,
            "code": self.code,
            "qty": self.quantity,
            "price": self.price,
            "type": self.price_type.value
        }

    def to_sstp_report(self) -> dict:
        """
        轉換為 SSTP 回報格式 (CAP_EXECUTION)
        Format: { "id": str, "status": str, "filled_qty": int, "avg_price": float, "msg": str }
        """
        return {
            "id": self.id if self.id else "",
            "status": self.status.value,
            "filled_qty": self.filled_qty,
            "avg_price": self.avg_price,
            "msg": self.msg
        }

@dataclass
class StandardAccount:
    """標準帳戶資金詳情 (Margin/Equity)"""
    account_id: str
    currency: str
    balance: float              # 可用餘額
    equity: float               # 權益數 (期貨) 或 總資產 (現貨)
    margin_used: float = 0.0    # 已用保證金
    realized_pnl: float = 0.0   # 今日已實現損益
    unrealized_pnl: float = 0.0 # 未實現損益

    def to_sstp_dict(self) -> dict:
        """
        轉換為 SSTP 帳務格式 (CAP_ACCOUNT - Equity)
        Format: { "balance": float, "equity": float, "margin_used": float, "currency": "TWD" }
        """
        return {
            "balance": self.balance,
            "equity": self.equity,
            "margin_used": self.margin_used,
            "currency": self.currency
        }

@dataclass
class StandardAccountSummary:
    """標準帳戶摘要 (用於列表顯示)"""
    account_id: str
    login_id: str               # 登入 ID 或 Username
    account_type: str           # "Future", "Stock", "General"
    is_signed: bool             # 是否已簽署/開通
    
@dataclass
class StandardPosition:
    """標準部位資訊"""
    code: str
    direction: str              # 'Long' or 'Short' (或 'Buy'/'Sell')
    quantity: int               # 絕對值
    avg_price: float
    current_price: float
    pnl: float                  # 未實現損益

    def to_sstp_dict(self) -> dict:
        """
        轉換為 SSTP 部位格式 (CAP_ACCOUNT - Position)
        Format: { "code": str, "qty": int(+/-), "avg_cost": float, "pnl": float }
        """
        # 統一處理方向：Short/Sell 為負數
        qty_signed = self.quantity
        dir_upper = self.direction.upper()
        if dir_upper in ["SHORT", "SELL", "S"]:
            qty_signed = -abs(self.quantity)
        else:
            qty_signed = abs(self.quantity)

        return {
            "code": self.code,
            "qty": int(qty_signed),
            "avg_cost": self.avg_price,
            "pnl": self.pnl
        }