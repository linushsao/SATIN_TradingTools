# ==============================================================================
# client_gui/kernel/services/repo_proxy.py
#
# Version: V1.1-002 (Fix Delete)
# 更新日期: 2025-12-09
# 描述:     策略資料庫服務代理 (Repo Service Proxy)。
#           [修正]: 完善 delete_project 實作，加入安全協商。
# ==============================================================================

from .base_proxy import BaseProxy, SecurityError
from shared.security_utils import calculate_hash, sign_data, verify_signature
import base64

class RepoProxy(BaseProxy):
    def __init__(self, zmq_client):
        super().__init__(zmq_client, "RepoService")

    def create_project(self, name: str) -> str:
        """建立新專案"""
        self.negotiate_security() # 握手，但 CREATE 不傳代碼，無需簽章
        reply = self._send_cmd("REQ_CREATE_PROJECT", {"name": name})
        return reply.get("msg", "Created")

    def delete_project(self, name: str) -> str:
        """刪除專案"""
        # [NEW] Ensure security context is established before deletion
        self.negotiate_security()
        reply = self._send_cmd("REQ_DELETE_PROJECT", {"name": name})
        return reply.get("msg", "Deleted")

    def get_project_list(self) -> list:
        """取得專案列表"""
        reply = self._send_cmd("REQ_GET_PROJECT_LIST")
        return reply.get("data", [])

    def update_project(self, name: str, zip_bytes: bytes, developer_id: str, private_key_pem: bytes) -> str:
        """
        [修正] 上傳/更新專案 (Zip Bytes)，並根據安全等級進行簽章。
        Args:
            zip_bytes: 專案的 zip 檔案內容 (bytes)
            developer_id: 開發者 ID
            private_key_pem: 開發者的私鑰 (bytes)
        """
        sec_info = self.negotiate_security()
        sec_level = sec_info.get('level', 'NONE')
        
        checksum = calculate_hash(zip_bytes)
        signature = None
        
        # 1. 執行簽章 (若等級為 STRICT)
        if sec_level == 'STRICT':
            if not private_key_pem:
                raise SecurityError("STRICT mode enabled on Server, but developer private key not found locally.")
            
            try:
                signature = sign_data(private_key_pem, zip_bytes)
                self._logger.info(f"Signed upload payload with developer key {developer_id}.")
            except Exception as e:
                raise SecurityError(f"Failed to sign data: {e}")

        payload = {
            "name": name, 
            "payload_b64": base64.b64encode(zip_bytes).decode('utf-8'),
            "checksum": checksum,
            "signature": signature,
            "developer_id": developer_id, # 傳遞 ID 供 Server 查詢公鑰
        }
        
        # 2. 發送請求，Server 會執行驗證
        reply = self._send_cmd("REQ_UPDATE_PROJECT", payload)
        return reply.get("msg", "Updated")

    def download_project(self, name: str) -> bytes:
        """
        [修正] 下載專案，並進行安全驗證。
        Returns: zip_bytes (bytes)
        """
        sec_info = self.negotiate_security()
        sec_level = sec_info.get('level', 'NONE')
        
        reply = self._send_cmd("REQ_DOWNLOAD_PROJECT", {"name": name})
        
        payload_b64 = reply.get("payload_b64", "")
        checksum = reply.get("checksum")
        signature = reply.get("signature")
        
        if not payload_b64:
            raise ServiceError("No content returned from download request.")
            
        zip_bytes = base64.b64decode(payload_b64)
        
        # 1. 檢查 Checksum (Level 1+)
        if sec_level in ['CHECKSUM', 'STRICT']:
            expected_checksum = calculate_hash(zip_bytes)
            if expected_checksum != checksum:
                raise SecurityError(f"Security check failed: Checksum mismatch. Required: {checksum[:8]}, Calculated: {expected_checksum[:8]}")

        # 2. 檢查 Signature (Level 2: STRICT)
        if sec_level == 'STRICT':
            server_public_key_path = self._client.config.get('security', {}).get('repo_public_key_path')
            server_public_key_pem = self._load_key_from_path(server_public_key_path)
            
            if not server_public_key_pem:
                raise SecurityError("STRICT mode enabled on Server, but local Server Public Key path is missing or invalid.")
                
            if not verify_signature(server_public_key_pem, zip_bytes, signature):
                raise SecurityError("Security check failed: Invalid Server Signature. Code may be compromised.")

            self._logger.info("Server Signature verification passed.")

        return zip_bytes

    def get_indicator_list(self) -> list:
        """取得遠端指標列表"""
        reply = self._send_cmd("REQ_GET_INDICATOR_LIST")
        return reply.get("data", [])

    def download_file(self, path: str) -> str:
        """下載單一檔案內容 (Text)"""
        # 一般文件下載 (非執行檔)，僅檢查 Checksum 即可
        reply = self._send_cmd("REQ_DOWNLOAD_FILE", {"path": path})
        content = reply.get("content", "")
        
        # 未實作單檔案驗證，這裡僅作為簡單下載通道
        # 如果需要，這裡也應執行握手與驗證邏輯
        return content
        
    def _load_key_from_path(self, key_path):
        # 由於 Proxy 類別無法直接存取 MainWindow，這裡調用 workers.py 的輔助函式
        from kernel.workers import _load_key_from_path 
        return _load_key_from_path(key_path)