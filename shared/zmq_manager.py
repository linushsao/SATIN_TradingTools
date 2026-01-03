# ==============================================================================
# shared/zmq_manager.py
#
# Version: V0.3-002 (Fix Import)
# 更新日期: 2025-12-08
# 描述:     ZeroMQ 通訊管理器。
#           V0.3-002: 修正 logging_tool 引用路徑為絕對路徑 (shared.logging_tool)。
# ==============================================================================

import zmq
import json
import threading
import time
# [FIX] Use absolute import path
from shared.logging_tool import debug, error, info

class ZmqServer:
    """
    Engine 使用的 ZMQ 伺服器端。
    - PUB Socket: 用於廣播行情、心跳、狀態。
    - REP Socket: 用於接收 UI 的指令並回覆。
    """
    def __init__(self, config):
        self.context = zmq.Context()
        self.config = config
        
        # 設定 Ports
        # Config 結構可能在 'zmq' (Trading) 或 'zmq_backtest' (Backtest) 下，由呼叫者傳入對應區塊
        # 為了通用性，這裡假設 config 已經是那一層，或是 root config
        # 修正：通常傳入的是 root config，我們需判斷 key
        
        # 嘗試偵測 config 中是否有 'zmq' (Trading) 或 'zmq_backtest' (Backtest)
        # 若傳入的是子字典，直接取值
        target_conf = config.get('zmq', {}) if 'zmq' in config else config
        # 若是 Backtest，傳入的可能是含有 zmq_backtest 的 root，這會比較混亂
        # 為了保持相容性，我們依賴外部傳入「正確的子配置」或是「包含 zmq 鍵的 Root」
        # 最佳解：Engine 傳入 config['zmq']，Backtest 傳入 config['zmq_backtest']
        # 但為了不改動 main_engine 太多，我們維持讀取 root 的邏輯，優先找 'zmq'
        
        if 'zmq_backtest' in config:
            target_conf = config['zmq_backtest']
        elif 'zmq' in config:
            target_conf = config['zmq']
        else:
            target_conf = config # 假設傳入的就是子配置
            
        self.pub_port = target_conf.get('pub_port', 5556)
        self.rep_port = target_conf.get('rep_port', 5557)
        self.bind_ip = target_conf.get('bind_ip', '*') 
        
        # 初始化 Sockets
        try:
            # Publisher (Broadcaster)
            self.pub_socket = self.context.socket(zmq.PUB)
            
            bind_str_pub = f"tcp://{self.bind_ip}:{self.pub_port}"
            self.pub_socket.bind(bind_str_pub)
            
            # Replier (Command Listener)
            self.rep_socket = self.context.socket(zmq.REP)
            bind_str_rep = f"tcp://{self.bind_ip}:{self.rep_port}"
            self.rep_socket.bind(bind_str_rep)
            
            # 設定接收超時為 1000ms (讓 Ctrl+C 可中斷)
            self.rep_socket.setsockopt(zmq.RCVTIMEO, 1000)
            
            info(f"[ZMQ Server] Bound PUB:{bind_str_pub}, REP:{bind_str_rep}", print_to_console=True)
        except Exception as e:
            error(f"[ZMQ Server] Init failed: {e}")
            raise

        self.running = True

    def publish(self, topic: str, data: dict):
        """廣播訊息給所有訂閱者 (UI)。"""
        try:
            # 格式: Topic + 空格 + JSON String
            payload = json.dumps(data, default=str)
            self.pub_socket.send_string(f"{topic} {payload}")
        except Exception as e:
            error(f"[ZMQ PUB Error] {e}")

    def start_command_listener(self, handler_callback):
        """啟動指令監聽迴圈 (Blocking)。"""
        info("[ZMQ Server] Command listener started.")
        while self.running:
            try:
                # 接收請求
                message = self.rep_socket.recv_json()
                
                # 處理請求
                response = handler_callback(message)
                
                # 回傳結果
                self.rep_socket.send_json(response)
            except zmq.error.Again:
                continue
            except Exception as e:
                error(f"[ZMQ REP Error] {e}")
                try:
                    self.rep_socket.send_json({"status": "error", "msg": str(e)})
                except:
                    pass

    def close(self):
        self.running = False
        self.pub_socket.close()
        self.rep_socket.close()
        self.context.term()
        info("[ZMQ Server] Closed.")


class ZmqClient:
    """
    UI 使用的 ZMQ 客戶端。
    """
    def __init__(self, config, config_key='zmq'):
        self.context = zmq.Context()
        self.config = config
        
        # Support dynamic config key reading
        target_conf = config.get(config_key, {})
        
        self.host = target_conf.get('host', '127.0.0.1')
        self.pub_port = target_conf.get('pub_port', 5556)
        self.rep_port = target_conf.get('rep_port', 5557)
        self.req_timeout = target_conf.get('req_timeout_ms', 10000)
        
        try:
            # Subscriber
            self.sub_socket = self.context.socket(zmq.SUB)
            self.sub_socket.connect(f"tcp://{self.host}:{self.pub_port}")
            
            # Requester
            self.req_socket = self.context.socket(zmq.REQ)
            self.req_socket.connect(f"tcp://{self.host}:{self.rep_port}")
            
            # 設定超時
            self.req_socket.setsockopt(zmq.RCVTIMEO, self.req_timeout) 
            self.req_socket.setsockopt(zmq.LINGER, 0)
            
            info(f"[ZMQ Client] Connected to {self.host} (PUB:{self.pub_port}, REQ:{self.rep_port})", print_to_console=False)
        except Exception as e:
            error(f"[ZMQ Client] Init failed: {e}")
            raise

        self.running = True
        self.callbacks = {} 

    def subscribe(self, topic: str, callback):
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, topic)
        self.callbacks[topic] = callback
        debug(f"[ZMQ SUB] Subscribed to {topic}")

    def start_listening_thread(self):
        self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listen_thread.start()

    def _listen_loop(self):
        while self.running:
            try:
                msg = self.sub_socket.recv_string()
                topic, payload_str = msg.split(' ', 1)
                if topic in self.callbacks:
                    data = json.loads(payload_str)
                    self.callbacks[topic](data)
            except Exception as e:
                time.sleep(0.1)

    def send_command(self, cmd: str, args: dict = None):
        request = {"cmd": cmd, "args": args or {}}
        try:
            self.req_socket.send_json(request)
            reply = self.req_socket.recv_json()
            return reply
        except zmq.error.Again:
            error(f"[ZMQ REQ] Request timed out ({self.req_timeout}ms).")
            # Reconnect on timeout
            self.req_socket.close()
            self.req_socket = self.context.socket(zmq.REQ)
            self.req_socket.connect(f"tcp://{self.host}:{self.rep_port}")
            self.req_socket.setsockopt(zmq.RCVTIMEO, self.req_timeout)
            return {"status": "error", "msg": "Timeout"}
        except Exception as e:
            error(f"[ZMQ REQ Error] {e}")
            return {"status": "error", "msg": str(e)}

    def close(self):
        self.running = False
        self.sub_socket.close()
        self.req_socket.close()
        self.context.term()