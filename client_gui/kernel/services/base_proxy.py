# ==============================================================================
# client_gui/kernel/services/base_proxy.py
#
# Version: V1.2-005 (CSV Log Format)
# 更新日期: 2025-12-15
# 描述:     服務代理基底類別 (Base Proxy)。
#           [修正]: 
#             1. 日誌格式改為 CSV: Time,Type,Source,Target,Category,Cmd,Msg。
#             2. 訊息內容中的逗號會被替換，確保格式正確。
# ==============================================================================\n
import logging
import os
import sys
import datetime
import inspect
from typing import Optional

class ServiceError(Exception):
    """通用服務錯誤"""
    pass

class ServiceTimeoutError(Exception):
    """服務連線逾時"""
    pass

class SecurityError(ServiceError):
    """安全驗證失敗"""
    pass

# 全域變數
_interaction_logger = None

def _get_interaction_logger():
    """單例模式取得互動日誌 Logger (純訊息模式)"""
    global _interaction_logger
    if _interaction_logger:
        return _interaction_logger

    logger_name = "Kernel_Interaction"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False 

    if not logger.handlers:
        log_dir = os.path.join(os.getcwd(), 'logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = os.path.join(log_dir, f'kernel_interaction_{ts}.csv') # 改為 .csv 副檔名

        handler = logging.FileHandler(log_file, encoding='utf-8')
        # Formatter 只輸出 message，時間戳記與 CSV 結構由程式邏輯控制
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        # 寫入 CSV Header
        logger.info("Timestamp,Type,Source,Target,Category,Command,Message")

    _interaction_logger = logger
    return _interaction_logger

class BaseProxy:
    def __init__(self, zmq_client, service_name="UnknownService"):
        self._client = zmq_client
        self._service_name = service_name
        self._logger = logging.getLogger(f"Proxy.{service_name}") 
        self._int_log = _get_interaction_logger()
        self._security_info = {'level': 'NONE'}

    def _get_caller_identity(self):
        """取得呼叫來源"""
        try:
            stack = inspect.stack()
            if len(stack) >= 4:
                frame = stack[3]
                module = inspect.getmodule(frame[0])
                mod_name = module.__name__ if module else "Unknown"
                
                if "plugins.pages" in mod_name:
                    parts = mod_name.split('.')
                    try:
                        idx = parts.index("pages")
                        return f"Plugin({parts[idx+1]})"
                    except: pass
                
                if 'self' in frame[0].f_locals:
                    return frame[0].f_locals['self'].__class__.__name__
        except: pass
        return "ClientSystem"

    def _classify_category(self, cmd: str) -> str:
        cmd = cmd.upper()
        if any(x in cmd for x in ['HISTORY', 'KBAR', 'TICK', 'QUOTE', 'CONTRACT']):
            return "OHLCV"
        if any(x in cmd for x in ['ORDER', 'TRADE', 'POSITION', 'ACCOUNT', 'LOGIN']):
            return "TRADE"
        if any(x in cmd for x in ['STR_', 'STRATEGY']):
            return "STRATEGY"
        if any(x in cmd for x in ['PROJECT', 'FILE', 'INDICATOR']):
            return "REPO"
        return "SYSTEM"

    def _clean_csv_msg(self, msg: str) -> str:
        """清理訊息以符合 CSV 格式 (移除換行與逗號)"""
        return str(msg).replace(",", ";").replace("\n", " ").replace("\r", "")

    def _send_cmd(self, cmd: str, args: dict = None) -> dict:
        if args is None: args = {}
        
        caller = self._get_caller_identity()
        target = self._service_name
        category = self._classify_category(cmd)
        
        # ISO 8601 Timestamp
        ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        # 1. 紀錄請求 (REQ)
        # CSV: Timestamp,Type,Source,Target,Category,Command,Message
        msg_req = f"{ts},REQ,{caller},{target},{category},{cmd},Args:{self._clean_csv_msg(str(args))}"
        self._int_log.info(msg_req)
        
        try:
            reply = self._client.send_command(cmd, args)
            
            if reply.get('status') == 'error':
                msg = reply.get('msg', 'Unknown')
                
                ts_err = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                msg_err = f"{ts_err},ERR,{target},{caller},{category},{cmd},{self._clean_csv_msg(msg)}"
                self._int_log.info(msg_err)
                
                if msg == 'Timeout': raise ServiceTimeoutError(f"Timeout: {target}")
                if "[SECURITY]" in msg.upper(): raise SecurityError(msg)
                raise ServiceError(msg)
            
            # 2. 紀錄回覆 (REP)
            ts_rep = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            
            # 簡化內容
            summary = "DataPayload" if "data" in reply or "content" in reply else (reply.get("msg") or "OK")
            msg_rep = f"{ts_rep},REP,{target},{caller},{category},{cmd},{self._clean_csv_msg(summary)}"
            self._int_log.info(msg_rep)
            
            return reply
            
        except Exception as e:
            ts_exc = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            msg_exc = f"{ts_exc},EXC,{target},{caller},{category},{cmd},{self._clean_csv_msg(str(e))}"
            self._int_log.info(msg_exc)
            
            self._logger.error(f"CMD '{cmd}' failed: {e}")
            raise

    def negotiate_security(self, force_refresh=False):
        if self._security_info['level'] != 'NONE' and not force_refresh:
            if self._security_info.get('last_check', 0) > time.time() - 30:
                return self._security_info

        try:
            reply = self._send_cmd("PING")
            self._security_info.update(reply.get('security', {'level': 'NONE'}))
            self._security_info['last_check'] = time.time()
            return self._security_info
        except Exception:
            return {'level': 'NONE'}

    @property
    def security_info(self):
        return self._security_info