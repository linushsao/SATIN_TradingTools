# ==============================================================================
# service_trading/core/account_manager.py
#
# Version: V0.5-000 (Multi-Broker Aggregation)
# 更新日期: 2025-12-13
# 描述:     帳務查詢管理員 (Router Version)。
#           [修正]: 
#             1. 接收 adapters 字典，匯總所有帳號。
#             2. 帳號 ID 格式化為 "BrokerName:AccountID"。
# ==============================================================================

from typing import Dict, List, Any
from shared.logging_tool import info, error, warn
from service_trading.core.interfaces import IBrokerAdapter
from shared.model_defs import StandardAccount, StandardPosition

class AccountManager:
    """
    Aggregation layer for multiple broker adapters.
    Routes queries to the correct adapter based on Account ID prefix.
    """

    def __init__(self, adapters: Dict[str, IBrokerAdapter]):
        self.adapters = adapters
        self._account_routing_map = {} # "Broker:AccID" -> "Broker"
        self._refresh_account_map()

    def _refresh_account_map(self):
        """建立 Account ID -> Adapter Name 的路由表"""
        self._account_routing_map = {}
        for name, adapter in self.adapters.items():
            try:
                accounts = adapter.list_available_accounts()
                for acc in accounts:
                    # 組合全域唯一 ID: "Shioaji:9809268"
                    global_id = f"{name}:{acc.account_id}"
                    self._account_routing_map[global_id] = name
            except Exception as e:
                error(f"[AccountManager] Failed to list accounts for {name}: {e}")

    def get_all_accounts(self) -> List[Dict]:
        """
        取得所有券商的帳號列表 (供 UI 顯示)。
        ID 會加上前綴。
        """
        result_list = []
        for name, adapter in self.adapters.items():
            try:
                accounts = adapter.list_available_accounts()
                for acc in accounts:
                    # Clone and modify ID
                    acc_dict = acc.__dict__.copy()
                    acc_dict['account_id'] = f"{name}:{acc.account_id}"
                    acc_dict['broker_id'] = name # 額外資訊
                    result_list.append(acc_dict)
            except Exception as e:
                error(f"[AccountManager] List error ({name}): {e}")
        return result_list

    def _parse_routing_id(self, global_account_id: str):
        """解析 "Broker:ID" -> (Broker, ID)"""
        if ":" in global_account_id:
            broker, raw_id = global_account_id.split(":", 1)
            return broker, raw_id
        
        # Fallback: 如果只有一個 Adapter，且 ID 沒前綴，嘗試直接匹配
        if len(self.adapters) == 1:
            return list(self.adapters.keys())[0], global_account_id
            
        return None, None

    def get_positions(self, global_account_id: str = None) -> Dict:
        """
        查詢部位。
        Args:
            global_account_id: 指定帳號 ID (如 "Shioaji:123")。若為 None，則查詢所有。
        """
        if not self.adapters:
            return {"positions": [], "msg": "No adapters"}

        sstp_positions = []
        
        # 若指定帳號，只查該券商
        target_adapters = self.adapters.items()
        if global_account_id:
            broker_name, _ = self._parse_routing_id(global_account_id)
            if broker_name and broker_name in self.adapters:
                target_adapters = [(broker_name, self.adapters[broker_name])]
        
        for name, adapter in target_adapters:
            try:
                # 這裡假設 Adapter 的 get_positions 會回傳該 Connection 下的所有部位
                # 未來若 Adapter 支援多帳號，需傳入 raw_account_id
                fut_pos = adapter.get_positions("future")
                for p in fut_pos:
                    # 標記來源券商
                    p_dict = p.to_sstp_dict()
                    p_dict['account_id'] = f"{name}:Default" # 暫時標記
                    sstp_positions.append(p_dict)
            except Exception as e:
                error(f"[AccountManager] Pos error ({name}): {e}")

        return {"positions": sstp_positions}
            
    def get_account_info(self, global_account_id: str = None) -> Dict:
        """
        取得資金權益。
        """
        # 簡化處理：如果沒指定，回傳第一個 Adapter 的資訊 (或匯總？通常 UI 會指定)
        target_adapter = None
        if global_account_id:
            broker, _ = self._parse_routing_id(global_account_id)
            target_adapter = self.adapters.get(broker)
        
        if not target_adapter and self.adapters:
            target_adapter = list(self.adapters.values())[0]
            
        if target_adapter:
            try:
                acc = target_adapter.get_account_data("future")
                return acc.to_sstp_dict()
            except Exception as e:
                error(f"Error querying account info: {e}")
        
        return {}