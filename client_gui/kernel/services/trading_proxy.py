# ==============================================================================
# client_gui/kernel/services/trading_proxy.py
#
# Version: V1.1-003 (Add History Query)
# 更新日期: 2025-12-16
# 描述:     交易引擎服務代理 (Trading Engine Proxy)。
#           [修正]: 新增 get_history_data 以支援從 DB 撈取 K 棒資料 (SSTP)。
# ==============================================================================

from .base_proxy import BaseProxy
from shared.constants import CMD_GET_STRATEGY_SCHEMA

class TradingProxy(BaseProxy):
    def __init__(self, zmq_client):
        super().__init__(zmq_client, "TradingEngine")

    # --- System ---
    def ping(self) -> dict:
        return self._send_cmd("PING")

    def restart(self) -> str:
        return self._send_cmd("RESTART").get("msg", "Restarting")

    def login(self, simulation: bool = True) -> dict:
        return self._send_cmd("LOGIN", {"simulation": simulation})

    # --- Market Data ---
    def get_contracts(self) -> list:
        return self._send_cmd("GET_CONTRACTS").get("data", [])

    def subscribe(self, code: str) -> str:
        return self._send_cmd("SUBSCRIBE", {"code": code}).get("status", "error")

    def unsubscribe(self) -> str:
        return self._send_cmd("UNSUBSCRIBE").get("status", "error")

    def download_history(self, code: str, start: str, end: str) -> str:
        """下載並回補歷史資料到 DB"""
        return self._send_cmd("DOWNLOAD_HISTORY", {
            "code": code, "start": start, "end": end
        }).get("msg", "")

    def get_history_data(self, code: str, start: str, end: str, freq: int = 1) -> list:
        """
        [NEW] 從後端 DB 查詢歷史 K 棒數據
        Returns: List of dicts [{'ts':..., 'Open':..., ...}]
        """
        return self._send_cmd("GET_DB_HISTORY", {
            "code": code, "start": start, "end": end, "freq": freq
        }).get("data", [])

    # --- Account (SSTP Updated) ---
    def get_accounts(self) -> list:
        """
        取得可用帳號列表
        Returns: [ { "account_id": "...", "is_signed": bool, ... }, ... ]
        """
        return self._send_cmd("GET_ACCOUNTS").get("data", [])

    def get_positions(self) -> list:
        """
        [NEW] 取得部位列表 (SSTP)
        Returns: [ { "code": "TXF", "qty": 1, "avg_cost": 20000, "pnl": 500 }, ... ]
        """
        return self._send_cmd("GET_POSITIONS").get("data", [])

    def get_available_instances(self) -> list:
        """
        [重構]: 直接從 Trading Service 獲取目前記憶體中運作的實例 ID 清單。
        解除原先透過 Context 轉向 Repo 請求檔案列表的依賴。
        """
        resp = self.get_strategy_status() # 呼叫現有的 STR_STATUS 指令
        if isinstance(resp, list):
            return [str(s.get('id')) for s in resp]
        return []

    def get_account_info(self) -> dict:
        """
        [NEW] 取得帳戶權益 (SSTP)
        Returns: { "balance": ..., "equity": ..., "margin_used": ... }
        """
        return self._send_cmd("GET_ACCOUNT_INFO").get("data", {})

    # --- Strategy Management ---
    def get_strategy_status(self) -> list:
        return self._send_cmd("STR_STATUS").get("data", [])

    def start_strategy(self, strategy_id: int) -> str:
        return self._send_cmd("STR_START", {"id": strategy_id}).get("msg", "")

    def stop_strategy(self, strategy_id: int) -> str:
        return self._send_cmd("STR_STOP", {"id": strategy_id}).get("msg", "")

    def toggle_strategy(self, strategy_id: int) -> str:
        return self._send_cmd("STR_TOGGLE", {"id": strategy_id}).get("msg", "")

    def add_strategy(self, config: dict) -> str:
        return self._send_cmd("STR_ADD", config).get("msg", "")

    def update_strategy(self, config: dict) -> str:
        return self._send_cmd("STR_UPDATE", config).get("msg", "")

    def delete_strategy(self, strategy_id: int) -> str:
        return self._send_cmd("STR_DEL", {"id": strategy_id}).get("msg", "")

    def get_strategy_logs(self) -> list:
        return self._send_cmd("STR_GET_LOGS").get("data", [])

    def get_strategy_schema(self) -> dict:
        return self._send_cmd(CMD_GET_STRATEGY_SCHEMA).get("schema", {})