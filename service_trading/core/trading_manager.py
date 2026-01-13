# ==============================================================================
# service_trading/core/trading_manager.py
#
# Version: V0.6-000 (Order Routing)
# 更新日期: 2025-12-13
# 描述:     交易管理員 (Router Version)。
#           [修正]: 
#             1. 支援多 Adapter 實例。
#             2. place_order 接收 'account_id' 並進行路由。
#             3. cancel_order 根據訂單 ID 前綴進行路由。
# ==============================================================================

import pandas as pd
from typing import Dict, Optional
from logging_tool import info, error, warn
from service_trading.core.interfaces import IBrokerAdapter
from shared.model_defs import StandardOrder, OrderAction, OrderType, PriceType

class TradingManager:
    """
    Manages trading operations across multiple adapters.
    Implements Order Routing based on Account ID.
    """

    # [修正]: 增加 engine_mode 參數
    def __init__(self, adapters: Dict[str, IBrokerAdapter], engine_mode: str = "SIMULATION"):
        self.adapters = adapters
        self.engine_mode = engine_mode.upper() # 儲存全域環境模式 (SIMULATION/PRODUCTION)
        
    def _get_adapter_by_account(self, account_id: str):
        """根據 account_id (Format: 'Broker:ID') 取得 Adapter"""
        if not account_id:
            # 若未指定，且只有一個 Adapter，則使用預設
            if len(self.adapters) == 1:
                return list(self.adapters.values())[0], list(self.adapters.keys())[0]
            return None, None
            
        if ":" in account_id:
            broker_name = account_id.split(":")[0]
            return self.adapters.get(broker_name), broker_name
        
        # Legacy/Fallback: 嘗試直接匹配 Adapter Name
        if account_id in self.adapters:
            return self.adapters[account_id], account_id
            
        return None, None

    # [新增]: 環境校驗私有函式
    def _validate_environment(self, broker_name: str, adapter: IBrokerAdapter):
        """
        驗證券商連線模式是否與引擎全域環境一致。
        """
        # 取得該 Adapter 目前的連線模式 (預設為 True/模擬)
        adapter_sim = getattr(adapter, 'simulation', True)
        is_engine_sim = (self.engine_mode == "SIMULATION")

        if is_engine_sim != adapter_sim:
            error_msg = f"[Security] Environment Mismatch! Engine is {self.engine_mode}, but Broker '{broker_name}' is {'SIMULATION' if adapter_sim else 'PRODUCTION'}."
            return False, error_msg
        return True, ""

    def place_order(self, contract_code: str, order_action: str, price: float, quantity: int, 
                   account_id: str, # [NEW] Required for routing
                   price_type: str = "LMT", order_type: str = "ROD") -> Optional[str]:
        """
        執行下單操作 (Routed)。
        Returns: Global Order ID (BrokerName:RawID)
        """
        adapter, broker_name = self._get_adapter_by_account(account_id)
        
        if not adapter:
            error(f"[Trading] No adapter found for account: {account_id}")
            return None

        # [新增攔截檢查]
        is_valid, err_msg = self._validate_environment(broker_name, adapter)
        if not is_valid:
            error(err_msg)
            return None

        try:
            # 1. Map Enums
            action_enum = OrderAction.BUY if order_action.upper() in ['BUY', 'B'] else OrderAction.SELL
            
            ptype_upper = price_type.upper()
            ptype_enum = PriceType.MKT if ptype_upper == 'MKT' else PriceType.LMT
            
            otype_upper = order_type.upper()
            if otype_upper == 'IOC': otype_enum = OrderType.IOC
            elif otype_upper == 'FOK': otype_enum = OrderType.FOK
            else: otype_enum = OrderType.ROD

            # 2. Create Standard Order
            order = StandardOrder(
                code=contract_code,
                action=action_enum,
                price=float(price),
                quantity=int(quantity),
                price_type=ptype_enum,
                order_type=otype_enum
            )
            
            info(f"[Trading] Routing order to {broker_name}: {contract_code} {action_enum.value} {quantity}")
            
            # 3. Send to Adapter
            raw_id = adapter.place_order(order)
            
            if raw_id:
                # Return prefixed ID for global uniqueness
                return f"{broker_name}:{raw_id}"
            return None

        except Exception as e:
            error(f"[Trading] Place order error: {e}")
            return None

    def cancel_order(self, global_order_id: str) -> bool:
        """
        取消訂單。
        Args:
            global_order_id: "BrokerName:RawID"
        """
        if ":" not in global_order_id:
            # Legacy fallback
            if len(self.adapters) == 1:
                adapter = list(self.adapters.values())[0]
                return adapter.cancel_order(global_order_id)
            error(f"[Trading] Invalid Order ID format: {global_order_id}")
            return False
            
        broker_name, raw_id = global_order_id.split(":", 1)
        adapter = self.adapters.get(broker_name)
        
        if not adapter:
            error(f"[Trading] Adapter '{broker_name}' not found for cancel.")
            return False
            
        try:
            result = adapter.cancel_order(raw_id)
            info(f"[Trading] Cancel sent to {broker_name} for {raw_id}: {result}")
            return result
        except Exception as e:
            error(f"[Trading] Cancel error: {e}")
            return False