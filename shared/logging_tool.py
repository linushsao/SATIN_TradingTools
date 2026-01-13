# ==============================================================================
# shared/logging_tool.py
#
# Version: V0.3-005 (Full Timestamp Patch)
# 更新日期: 2026-01-14
# 描述:     通用日誌工具。
#           [修正]: 
#             1. log 函式增加時間戳記，確保 Logger 未初始化前的 print 訊息包含時間。
#             2. ZmqLogHandler 增加日期資訊至 dt 欄位，確保廣播日誌完整性。
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
            if record.name.startswith("ZMQ"): 
                return

            msg = self.format(record)
            
            # --- [修正] 增加日期資訊至 dt 欄位 ---
            payload = {
                "level": record.levelname,
                "msg": str(msg),
                "dt": datetime.datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S'),
                "module": record.module,
                "func": record.funcName,
                "logger": record.name,
                "thread": record.threadName
            }
            
            if self.zmq_server and hasattr(self.zmq_server, 'publish'):
                self.zmq_server.publish("LOG", payload)
                
        except Exception:
            self.handleError(record)

def _get_unique_log_path(folder, base_name, date_str, ext):
    """產生不重複的檔案路徑"""
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)
        
    prefix = f"{base_name}_{date_str}_"
    existing_files = [f for f in os.listdir(folder) if f.startswith(prefix) and f.endswith(ext)]
    
    max_serial = 0
    for f in existing_files:
        try:
            serial_part = f.split('_')[-1].split('.')[0]
            serial_num = int(serial_part)
            if serial_num > max_serial:
                max_serial = serial_num
        except (ValueError, IndexError):
            continue
    
    new_serial = f"{(max_serial + 1):03d}"
    return os.path.join(folder, f"{prefix}{new_serial}{ext}")

def init_logger(config_data=None, zmq_server=None, **kwargs):
    """
    初始化全域 Logger
    [修正]: 
      1. 支援 **kwargs 以接收 log_dir 等參數防止崩潰。
      2. 增加對 config_data 為 None 的容錯處理。
    """
    global _logger
    if _logger:
        return

    # 安全地讀取設定字典
    cfg = config_data or {}
    
    # 優先序: kwargs 傳入值 > config_data 字典值 > 預設值
    log_dir = kwargs.get('log_dir') or cfg.get('log_dir', 'logs/system')
    base_filename = kwargs.get('log_filename') or cfg.get('log_filename', 'system').replace('.log', '')
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    
    log_file_path = _get_unique_log_path(log_dir, base_filename, today_str, ".log")

    _logger = logging.getLogger("TradingEngine")
    _logger.setLevel(logging.DEBUG)

    max_bytes = cfg.get('log_max_bytes', DEFAULT_MAX_BYTES)
    backup_count = cfg.get('log_backup_count', DEFAULT_BACKUP_COUNT)
    
    file_handler = logging.handlers.RotatingFileHandler(
        log_file_path, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
    )
    
    formatter = logging.Formatter(
        '[%(asctime)s.%(msecs)03d] [%(threadName)s] [%(levelname)-5s] %(message)s', 
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    _logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    console_handler.setLevel(logging.INFO)
    _logger.addHandler(console_handler)

    if zmq_server:
        zmq_handler = ZmqLogHandler(zmq_server)
        zmq_handler.setFormatter(formatter)
        _logger.addHandler(zmq_handler)

    _logger.info(f"=== Application Started (Log: {log_file_path}) ===")
    init_debug_mode(cfg)
    return log_file_path

# 增加別名以相容舊版匯入名稱
init_logging = init_logger

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
    """
    [修正] 通用日誌入口。
    增加時間戳記處理邏輯，確保在 Logger 初始化前的 print 也能顯示時間。
    """
    if not _logger:
        if print_to_console:
            # --- [新增] 初始化前訊息的時間戳記 ---
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            print(f"[{now}] [{level_name}] {message}")
        return

    lvl = level_name.upper()
    if lvl == 'INFO': _logger.info(message)
    elif lvl == 'ERROR': _logger.error(message)
    elif lvl == 'WARN' or lvl == 'WARNING': _logger.warning(message)
    elif lvl == 'DEBUG': _logger.debug(message)
    else: _logger.info(f"[{lvl}] {message}")

def info(message: str, print_to_console=True): log('INFO', message, print_to_console)
def error(message: str, print_to_console=True): log('ERROR', message, print_to_console)
def warn(message: str, print_to_console=True): log('WARN', message, print_to_console)
def debug(message: str, print_to_console=False): log('DEBUG', message, print_to_console)
def log_end():
    if _logger: _logger.info("--- Application Finished ---")