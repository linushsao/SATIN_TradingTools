# ==============================================================================
# client_gui/kernel/workers.py
#
# Version: V2.8-002 (Exp Backoff)
# 更新日期: 2025-12-13
# 描述:     PyQt6 ZMQ 工作執行緒。
#           [修正]: ZmqSubThread 實作指數退避 (Exponential Backoff) 重連機制。
# ==============================================================================

import zmq
import json
import time
import socket
import os
from PyQt6.QtCore import QThread, pyqtSignal, QObject
from shared.constants import TOPIC_SYS_NOTIFICATION

def _load_key_from_path(key_path: str) -> bytes or None:
    """從檔案路徑安全地載入金鑰內容 (bytes)"""
    if not key_path or not os.path.exists(key_path):
        return None
    try:
        with open(key_path, 'rb') as f:
            return f.read()
    except Exception as e:
        print(f"[KeyLoader] Failed to load key {key_path}: {e}")
        return None

def probe_service(host, port, timeout=1.0) -> bool:
    """
    測試特定 Host:Port 是否可連線 (TCP Connect)。
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, int(port)))
        sock.close()
        return result == 0
    except Exception as e:
        print(f"[Probe] Error probing {host}:{port} - {e}")
        return False

class ZmqSubThread(QThread):
    # Live Trading Signals
    sig_heartbeat = pyqtSignal(dict)
    sig_tick = pyqtSignal(dict)
    sig_kbar = pyqtSignal(dict)
    sig_log = pyqtSignal(dict)
    sig_strategy = pyqtSignal(dict)
    
    # Global Notification Signal
    sig_notification = pyqtSignal(dict)
    
    # Backtest Signals
    sig_bt_heartbeat = pyqtSignal(dict)
    sig_bt_progress = pyqtSignal(dict)
    sig_bt_finished = pyqtSignal(dict) 
    
    def __init__(self, service_config):
        super().__init__()
        self.config = service_config
        self.running = True
        self.socket = None
        self.context = None
        
        # Backoff parameters
        self.retry_interval = 1.0
        self.max_retry_interval = 30.0

    def reconnect(self, new_config):
        self.config = new_config
        if self.socket:
            self.running = False 
            try:
                self.socket.setsockopt(zmq.LINGER, 0)
                self.socket.close()
            except: pass
            
            self.wait(1000)
            
            self.running = True
            self.start()

    def run(self):
        self.context = zmq.Context()
        
        host = self.config.get('host', '127.0.0.1')
        port = self.config.get('pub_port', 5556)
        connect_str = f"tcp://{host}:{port}"
        
        while self.running:
            try:
                if not self.socket:
                    self.socket = self.context.socket(zmq.SUB)
                    self.socket.connect(connect_str)
                    self.socket.setsockopt_string(zmq.SUBSCRIBE, "")
                    print(f"[ZmqSub] Connected to {connect_str}")
                    self.retry_interval = 1.0 # Reset backoff on successful connect init

                if self.socket.poll(1000):
                    msg = self.socket.recv_string()
                    
                    # Handle potential format issues
                    if ' ' in msg:
                        topic, payload_str = msg.split(' ', 1)
                    else:
                        continue
                        
                    try:
                        data = json.loads(payload_str)
                    except: continue
                    
                    # Reset backoff on successful message receive
                    self.retry_interval = 1.0
                    
                    # Main Engine Topics
                    if topic == "HEARTBEAT": self.sig_heartbeat.emit(data)
                    elif topic == "TICK": self.sig_tick.emit(data)
                    elif topic == "KBAR": self.sig_kbar.emit(data)
                    elif topic == "LOG": self.sig_log.emit(data)
                    elif topic == "STRATEGY": self.sig_strategy.emit(data)
                    
                    # System Notification Interception
                    elif topic == TOPIC_SYS_NOTIFICATION: 
                        self.sig_notification.emit(data)
                    
                    # Backtest Service Topics
                    elif topic == "BT_HEARTBEAT": self.sig_bt_heartbeat.emit(data)
                    elif topic == "BT_PROGRESS": self.sig_bt_progress.emit(data)
                    elif topic == "BT_FINISHED": self.sig_bt_finished.emit(data) 
                else:
                    # No message received (Idle), but connection might be fine.
                    # Just continue loop.
                    continue
                        
            except zmq.error.ContextTerminated:
                print("[ZmqSub] Context Terminated.")
                break
            except Exception as e:
                # Connection error or other exception -> Apply Backoff
                print(f"[ZmqSub] Error: {e}. Retrying in {self.retry_interval}s...")
                
                # Close socket to force reconnection logic next loop
                if self.socket:
                    try:
                        self.socket.close()
                    except: pass
                    self.socket = None
                
                if self.running:
                    time.sleep(self.retry_interval)
                    # Exponential Backoff
                    self.retry_interval = min(self.retry_interval * 2, self.max_retry_interval)

        # Cleanup
        try:
            if self.socket: self.socket.close()
            self.context.term()
        except: pass

    def stop(self):
        self.running = False
        self.wait()


class ZmqReqClient:
    def __init__(self, service_config):
        self.context = None
        self.socket = None
        self.update_config(service_config)

    def update_config(self, service_config):
        self.config = service_config
        if self.socket:
            self.socket.close()
        if self.context:
            self.context.term()
            
        self.zmq_host = service_config.get('host', '127.0.0.1')
        self.zmq_port = service_config.get('rep_port', 5557)
        self.timeout = service_config.get('req_timeout_ms', 2000)
        
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, self.timeout)
        self.socket.setsockopt(zmq.LINGER, 0)
        
        try:
            self.socket.connect(f"tcp://{self.zmq_host}:{self.zmq_port}")
            print(f"[ZmqReq] Connected to {self.zmq_host}:{self.zmq_port}")
        except Exception as e:
            print(f"[ZmqReq] Connect Error: {e}")

    def send_command(self, cmd: str, args: dict = None) -> dict:
        try:
            payload = {"cmd": cmd, "args": args or {}}
            self.socket.send_json(payload)
            reply = self.socket.recv_json()
            return reply
        except zmq.error.Again:
            # print(f"[ZmqReq] Timeout on {cmd}, reconnecting...")
            # Silent reconnect for smoother UX
            self.update_config(self.config)
            return {"status": "error", "msg": "Timeout"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}