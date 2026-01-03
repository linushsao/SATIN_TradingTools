# ==============================================================================
# shared/logging_tool.py
#
# Version: V0.3-003 (Thread Info)
# 更新日期: 2025-12-13
# 描述:     通用日誌工具。
#           [修正]: 
#             1. Log Formatter 增加 threadName 以識別非同步來源。
#             2. ZmqLogHandler 增加強制字串轉換，防止 JSON 序列化錯誤。
# ==============================================================================

import logging
import logging.handlers
import os
import sys
import datetime
import json

# 全域 Logger 物件
_logger = None

# 預設配置
DEFAULT_MAX_BYTES = 10 * 1024 * 1024 
DEFAULT_BACKUP_COUNT = 5

class ZmqLogHandler(logging.Handler):
    """
    自定義 Logging Handler，將日誌訊息發送至 ZMQ Publisher。
    """
    def __init__(self, zmq_server):
        super().__init__()
        self.zmq_server = zmq_server

    def emit(self, record):
        try:
            # 避免無窮遞迴：如果 ZMQ 發送過程本身產生 Log，則忽略
            if record.name.startswith("ZMQ"): 
                return

            msg = self.format(record)
            
            # 準備 payload
            payload = {
                "level": record.levelname,
                "msg": str(msg), # 強制轉字串，避免非基本型別導致 JSON Error
                "dt": datetime.datetime.fromtimestamp(record.created).strftime('%H:%M:%S'),
                "module": record.module,
                "func": record.funcName,
                "logger": record.name,
                "thread": record.threadName # [NEW] 加入執行緒資訊
            }
            
            # 透過 ZmqServer 發送 (Topic: LOG)
            if self.zmq_server and hasattr(self.zmq_server, 'publish'):
                self.zmq_server.publish("LOG", payload)
                
        except Exception:
            self.handleError(record)

def init_logging(config_data=None, log_dir='logs', zmq_publisher=None):
    """
    初始化系統日誌 (System Logger)。
    Args:
        config_data: 設定檔字典 (可選)
        log_dir: 日誌輸出目錄 (預設為當前工作目錄下的 logs)
        zmq_publisher: (選填) ZmqServer 實例，若傳入則啟用 ZMQ 轉發功能
    """
    global _logger
    
    # 1. 準備目錄
    base_log_path = os.path.abspath(log_dir)
    system_log_dir = os.path.join(base_log_path, 'system')
    os.makedirs(system_log_dir, exist_ok=True)
    
    log_file_path = os.path.join(system_log_dir, 'system.log')

    # 2. 讀取配置
    max_bytes = DEFAULT_MAX_BYTES
    backup_count = DEFAULT_BACKUP_COUNT
    
    if config_data and 'logging' in config_data:
        max_bytes = config_data['logging'].get('max_bytes', DEFAULT_MAX_BYTES)
        backup_count = config_data['logging'].get('backup_count', DEFAULT_BACKUP_COUNT)

    # 3. 設定 Logger
    _logger = logging.getLogger("System")
    _logger.setLevel(logging.DEBUG) 
    _logger.propagate = False 

    if _logger.hasHandlers():
        _logger.handlers.clear()

    # Formatter [MOD] Added threadName
    file_formatter = logging.Formatter(
        '[%(asctime)s.%(msecs)03d] [%(threadName)s] [%(levelname)-5s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = logging.Formatter(
        '[%(asctime)s.%(msecs)03d] [%(threadName)s] [%(levelname)-5s] %(message)s',
        datefmt='%H:%M:%S'
    )

    # Handler 1: Rotating File
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file_path, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG) 
        _logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to create log file handler: {e}")

    # Handler 2: Console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO) 
    _logger.addHandler(console_handler)

    # Handler 3: ZMQ
    if zmq_publisher:
        try:
            zmq_handler = ZmqLogHandler(zmq_publisher)
            zmq_handler.setLevel(logging.INFO) 
            _logger.addHandler(zmq_handler)
            _logger.info("ZMQ Log Handler attached.")
        except Exception as e:
            print(f"Failed to attach ZMQ handler: {e}")

    _logger.info(f"=== Application Started (Log: {log_file_path}) ===")
    
    if config_data:
        init_debug_mode(config_data)

    return log_file_path

def init_debug_mode(config_data):
    is_debug = config_data.get('debug_mode', False)
    set_debug_mode(is_debug)

def set_debug_mode(enabled: bool):
    global _logger
    if not _logger: return

    for h in _logger.handlers:
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            h.setLevel(logging.DEBUG if enabled else logging.INFO)
            
    mode_str = "ON" if enabled else "OFF"
    try:
        _logger.info(f"Debug Mode switched to: {mode_str}")
    except: pass

def log(level_name, message, print_to_console=True):
    if not _logger:
        if print_to_console: print(f"[{level_name}] {message}")
        return

    lvl = level_name.upper()
    if lvl == 'INFO': _logger.info(message)
    elif lvl == 'ERROR': _logger.error(message)
    elif lvl == 'WARN' or lvl == 'WARNING': _logger.warning(message)
    elif lvl == 'DEBUG': _logger.debug(message)
    else: _logger.info(f"[{lvl}] {message}")

def info(message: str, print_to_console=True):
    log('INFO', message, print_to_console)

def error(message: str, print_to_console=True):
    log('ERROR', message, print_to_console)

def warn(message: str, print_to_console=True):
    log('WARN', message, print_to_console)

def debug(message: str, print_to_console=False):
    log('DEBUG', message, print_to_console)

def log_end():
    if _logger: _logger.info("--- Application Finished ---")