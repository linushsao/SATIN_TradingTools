# ==============================================================================
# client_gui/kernel/services/backtest_proxy.py
#
# Version: V1.0-000
# 描述:     回測服務代理 (Backtest Service Proxy)。
# ==============================================================================

from .base_proxy import BaseProxy

class BacktestProxy(BaseProxy):
    def __init__(self, zmq_client):
        super().__init__(zmq_client, "BacktestService")

    def ping(self) -> dict:
        return self._send_cmd("PING")

    def list_tasks(self) -> list:
        return self._send_cmd("BT_LIST").get("data", [])

    def create_task(self, params: dict) -> str:
        """建立回測任務 (支援包含 Code Packet)"""
        reply = self._send_cmd("BT_CREATE", params)
        return reply.get("task_id", "")

    def update_task(self, task_id: str, params: dict) -> str:
        return self._send_cmd("BT_UPDATE", {"task_id": task_id, "params": params}).get("msg", "")

    def run_task(self, task_id: str) -> str:
        return self._send_cmd("BT_RUN", {"task_id": task_id}).get("msg", "")

    def stop_task(self, task_id: str) -> str:
        return self._send_cmd("BT_STOP", {"task_id": task_id}).get("msg", "")

    def delete_task(self, task_id: str) -> str:
        return self._send_cmd("BT_DELETE", {"task_id": task_id}).get("msg", "")

    def get_result(self, task_id: str) -> dict:
        return self._send_cmd("BT_GET_RESULT", {"task_id": task_id}).get("data", {})

    def download_result(self, task_id: str) -> dict:
        """
        [V1.2修正]: 回傳完整回應字典 (含 Base64 資料)，而非僅回傳伺服器路徑。
        """
        return self._send_cmd("BT_DOWNLOAD", {"task_id": task_id})