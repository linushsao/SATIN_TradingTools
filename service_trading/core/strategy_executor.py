# ==============================================================================
# service_trading/core/strategy_executor.py
#
# Version: V2.3-000 (Multi-Broker Router)
# 更新日期: 2025-12-13
# 描述:     策略執行器 (Router Version)。
#           [修正]: 
#             1. 接收 adapters 字典。
#             2. _execute_order 時傳遞 account_id 進行路由。
#             3. on_order_update 處理 Global ID。
# ==============================================================================

import sys
import time
import os
import datetime
import importlib.util
import logging
import logging.handlers
import threading
from collections import deque 
from shared.logging_tool import info, error, debug, warn
from trading_manager import TradingManager
from strategy_state_manager import StrategyStateManager
from config_manager import save_config, CONFIG_FILE
from service_trading.core.interfaces import IBrokerAdapter
from shared.model_defs import StandardTick

PACKET_KEY_STRAT_CODE = "strat_code"
PACKET_KEY_CORE_CODE = "core_code"
STRATEGY_DIR = 'plugins'
STRATEGY_LOG_DIR = 'logs/strategies'

class StrategyGroup:
    
    def __init__(self, group_id, config_dict, sys_default_retention=0.66):
        self.id = group_id
        self.name = config_dict.get('name', f'Strategy_{group_id}')
        self.file_name = config_dict.get('file_name')
        self.frequency = config_dict.get('frequency', 15)
        self.max_order_qty = config_dict.get('max_order_qty', 1)
        self.max_position_qty = config_dict.get('max_position_qty', 1)
        self.contract_code = config_dict.get('contract_code')
        self.account_id = config_dict.get('account_id') # [NEW] Format: "Broker:ID"
        self.max_slippage = int(config_dict.get('max_slippage', 5)) 
        self.chase_buffer = abs(int(config_dict.get('chase_buffer', 1))) 
        self.profit_retention_rate = float(config_dict.get('profit_retention_rate', sys_default_retention))
        self.auto_restart = bool(config_dict.get('auto_restart', False))
        self.is_active = bool(config_dict.get('is_active', True))
        self.execution_mode = config_dict.get('execution_mode', 'Monitor') 
        
        self.sys_default_retention = sys_default_retention
        self.is_running = False
        self.module = None
        self.current_data = None 
        self.position_qty = 0
        self.last_calc_time = None
        self.last_price = 0.0
        self.avg_cost = 0.0
        self.exit_signal_triggered = False
        self.trailing_active = False
        self.trailing_max_profit = 0.0
        self.current_retention_rate = self.profit_retention_rate
        self.pending_order_id = None 
        self.initial_signal_price = 0.0
        self.total_realized_pnl = 0.0
        self.active_sl_condition = None 
        self.logger = None
        self.active_orders = set() # 用來追蹤進行中的訂單 ID
        
    def _get_unique_filepath(self, folder, name, date_str, ext):
        """
        [新增] 根據格式產生不重複的檔案路徑：<NAME>_<日期>_<三碼流水號>.<ext>
        """
        prefix = f"{name}_{date_str}_"
        # 取得目錄下所有符合該名稱與日期的檔案
        existing_files = [f for f in os.listdir(folder) if f.startswith(prefix) and f.endswith(ext)]
        
        max_serial = 0
        for f in existing_files:
            try:
                # 提取流水號 (檔名格式: NAME_YYYYMMDD_XXX.ext)
                serial_part = f.split('_')[-1].split('.')[0]
                serial_num = int(serial_part)
                if serial_num > max_serial:
                    max_serial = serial_num
            except (ValueError, IndexError):
                continue
        
        # 產生下一個流水號 (如 001, 002)
        new_serial = f"{(max_serial + 1):03d}"
        new_filename = f"{prefix}{new_serial}{ext}"
        return os.path.join(folder, new_filename)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'file_name': self.file_name, 'frequency': self.frequency,
            'max_order_qty': self.max_order_qty, 'max_position_qty': self.max_position_qty,
            'contract_code': self.contract_code, 'account_id': self.account_id,
            'max_slippage': self.max_slippage, 'chase_buffer': self.chase_buffer,
            'profit_retention_rate': self.profit_retention_rate, 'auto_restart': self.auto_restart, 
            'is_active': self.is_active, 'execution_mode': self.execution_mode
        }
    
    def get_status_dict(self):
        entry = self.current_data.get('entry_price', 0) if self.current_data else 0
        sl = self.current_data.get('sl_price', 0) if self.current_data else 0
        tp = self.current_data.get('tp_price', 0) if self.current_data else 0
        status_flags = ""
        if self.pending_order_id: status_flags += " [Pending]"
        if self.trailing_active: status_flags += f" [Trail {self.trailing_max_profit:.0f}]"
        if self.auto_restart: status_flags += " [Auto]"
        if self.execution_mode == 'TouchOrder': status_flags += " [Touch]"
        if self.active_sl_condition: status_flags += " [SL Protected]"
        
        display_name = f"{self.name} (${self.total_realized_pnl:.0f}){status_flags}"
        return {
            'id': self.id, 'name': display_name, 'running': self.is_running,
            'pos': self.position_qty, 'last': self.last_price, 'avg_cost': self.avg_cost,
            'entry': entry, 'sl': sl, 'tp': tp, 'contract': self.contract_code, 'account_id': self.account_id,
            'is_active': self.is_active
        }
    
    def start_logging(self):
        """
        [修正] 每次啟動產生全新的流水號日誌與數據檔
        """
        if not os.path.exists(STRATEGY_LOG_DIR): 
            os.makedirs(STRATEGY_LOG_DIR)
            
        safe_name = "".join([c for c in self.name if c.isalnum() or c in (' ', '_', '-')]).strip()
        today_str = datetime.datetime.now().strftime("%Y%m%d")

        # 1. 取得本次啟動專屬的 .log 路徑
        unique_log_path = self._get_unique_filepath(STRATEGY_LOG_DIR, safe_name, today_str, ".log")
        
        self.logger = logging.getLogger(f"Strategy.{self.id}.{unique_log_path}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False 
        
        if self.logger.hasHandlers(): 
            self.logger.handlers.clear()
            
        handler = logging.handlers.RotatingFileHandler(unique_log_path, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
        handler.setFormatter(logging.Formatter('[%(asctime)s.%(msecs)03d] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
        self.logger.addHandler(handler)
        self.log("INFO", f"=== Strategy Instance Started: {self.name} ===")

        # 2. 取得本次啟動專屬的 .csv 路徑
        self.csv_path = self._get_unique_filepath(STRATEGY_LOG_DIR, safe_name, today_str, ".csv")
        
        # 初始化 CSV 並寫入標題
        with open(self.csv_path, 'w', encoding='utf-8') as f:
            header = "ts,o,h,l,c,v,entry,sl,tp,pos,avg_cost,unrealized_pnl\n"
            f.write(header)
            
        self.log("INFO", f"CSV Data path initialized: {os.path.basename(self.csv_path)}")
                
    def stop_logging(self):
        if self.logger:
            self.log("INFO", "=== Strategy Stopped ===")
            for h in self.logger.handlers: h.close(); self.logger.removeHandler(h)
            self.logger = None

    def log(self, level, message):
        if self.logger: self.logger.log(getattr(logging, level.upper(), logging.INFO), message)

    def load_module(self):
        """
        [修正版] 實作模組隔離載入與路徑清理
        """
        import os, sys, importlib.util
        
        file_name_only = self.file_name
        folder_name = file_name_only.replace(".py", "")
        
        possible_paths = [
            os.path.join(STRATEGY_DIR, file_name_only),
            os.path.join(STRATEGY_DIR, folder_name, file_name_only)
        ]
        
        target_path = next((p for p in possible_paths if os.path.exists(p)), None)
        
        if not target_path:
            info(f"[Loader] ERROR: Cannot find strategy file {file_name_only}")
            return False

        try:
            # 【關鍵修正 1】：使用唯一的實例 ID 作為模組名稱，防止 sys.modules 衝突
            unique_mod_name = f"strat_instance_{self.id}"
            abs_dir = os.path.abspath(os.path.dirname(target_path))
            
            # 【關鍵修正 2】：保存原始路徑，確保載入後可還原，防止路徑膨脹
            original_path = sys.path.copy()
            if abs_dir not in sys.path:
                sys.path.insert(0, abs_dir)
            
            try:
                info(f"[Loader] Isolated loading: {unique_mod_name} from {target_path}")
                spec = importlib.util.spec_from_file_location(unique_mod_name, target_path)
                module = importlib.util.module_from_spec(spec)
                
                # 註冊到系統模組中以支援內部 import (例如 strategy_core)
                sys.modules[unique_mod_name] = module
                spec.loader.exec_module(module)
                
                if not hasattr(module, 'calculate'):
                    info(f"[Loader] ERROR: '{file_name_only}' missing 'calculate' function.")
                    return False
                    
                self.module = module
                return True
            finally:
                # 【關鍵修正 3】：無論成功或失敗，皆還原路徑環境
                sys.path = original_path
                
        except Exception as e:
            import traceback
            error(f"[Loader] EXCEPTION: {e}\n{traceback.format_exc()}")
            return False

class StrategyExecutor:
    
    def __init__(self, adapters: dict, config, data_manager, zmq_server, touch_executor=None):
        self.adapters = adapters # [MOD] Now receiving Dict[str, IBrokerAdapter]
        self.config = config
        self.data_manager = data_manager
        self.server = zmq_server 
        self.touch_executor = touch_executor 
        self.state_manager = StrategyStateManager()
        self.strategies = []
        self.data_buffers = {} 
        log_conf = self.config.get('logging', {})
        buffer_size = int(log_conf.get('buffer_size', 20))
        self.event_buffer = deque(maxlen=buffer_size)
        self._load_strategies()
        self._restore_strategy_state()

        self._config_dirty = False   # 這是我們新創的「便條紙」
        self._save_interval = 10     # 設定每 10 秒檢查一次
        # 啟動一個後台清潔工（線程），它會一直執行 _periodic_save_worker 函式
        threading.Thread(target=self._periodic_save_worker, daemon=True).start()
        self.trading_manager = TradingManager(self.adapters)
        
    def _periodic_save_worker(self):
        """【這是新函式】後台清潔工：負責定期檢查便條紙"""
        import time
        while True:
            if self._config_dirty: # 如果看到便條紙 (True)
                try:
                    self._do_real_save() # 執行真正的存檔
                    self._config_dirty = False # 存完後把便條紙撕掉 (False)
                    debug("[Executor] 背景自動存檔完成。")
                except Exception as e:
                    error(f"[Executor] 背景存檔失敗: {e}")
            time.sleep(self._save_interval) # 休息 10 秒再檢查下一次

    def _do_real_save(self):
        """【這是新函式】真正把資料寫進硬碟的邏輯"""
        # 這部分是把原本 _save_config 裡面的寫入邏輯搬過來
        groups_data = [s.to_dict() for s in self.strategies]
        self.config['strategy_groups'] = groups_data
        # 假設你有 save_config 這個工具函式與 CONFIG_FILE 路徑
        # from shared.config_manager import save_config 
        save_config(self.config, CONFIG_FILE) # 使用匯入的常數

    def _load_strategies(self):
        groups_data = self.config.get('strategy_groups', [])
        sys_default = float(self.config.get('default_profit_retention', 0.66))
        self.strategies = []
        for data in groups_data:
            if 'id' in data and 'file_name' in data:
                group = StrategyGroup(data['id'], data, sys_default)
                self.strategies.append(group)
    
    def _restore_strategy_state(self):
        saved_state = self.state_manager.load_state()
        for group in self.strategies:
            state = saved_state.get(str(group.id))
            should_run = False
            if state:
                should_run = state.get('is_running', False)
                group.position_qty = state.get('position_qty', 0)
                group.avg_cost = state.get('avg_cost', 0)
                group.trailing_active = state.get('trailing_active', False)
                group.trailing_max_profit = state.get('trailing_max_profit', 0.0)
                group.total_realized_pnl = state.get('total_realized_pnl', 0.0)
                if state.get('entry_price'):
                    group.current_data = {
                        'entry_price': state['entry_price'], 'sl_price': state['sl_price'],
                        'tp_price': state['tp_price'], 'direction': state['direction']
                    }
            else:
                if group.auto_restart: should_run = True

            if should_run:
                group.is_running = True
                self._activate_strategy(group, restore=True)
            else:
                group.is_running = False

    def _activate_strategy(self, group, restore=False):
        """
        [修正版] 調整啟動順序，防止首筆行情丟失
        """
        info(f"[Executor] Starting Activation: {group.name}")
        
        if group.load_module():
            # 【關鍵修正】：先設定運行狀態標記
            group.is_running = True 
            
            # 隨後才啟動行情監聽
            self.data_manager.start_listening(group.contract_code)
            group.start_logging()
            
            info(f"[Executor] {group.name} is now ACTIVE and listening.")
            
            msg = f"Strategy '{group.name}' {'RESTORED' if restore else 'STARTED'}."
            self._log_ui(msg, "SUCCESS", group=group)
        else:
            group.is_running = False
            msg = f"Failed to activate strategy '{group.name}'."
            self._log_ui(msg, "ERROR")
 
    def _save_state(self): self.state_manager.save_state(self.strategies); self._broadcast_status()
    
    def _save_config(self):
        """【修改原有的函式】現在不直接存檔了，只貼便條紙"""
        self._config_dirty = True  # 貼上便條紙：標記為髒資料
        self._broadcast_status()   # 仍然即時通知 UI 介面更新狀態
        
    def _broadcast_status(self): 
        if self.server:
            status_list = [s.get_status_dict() for s in self.strategies]
            self.server.publish("STRATEGY", {"data": status_list})
            
    def _log_ui(self, msg, level="INFO", group=None):
        """
        [修正] 將日誌同步輸出至 UI、系統日誌與該策略專屬實體檔案。
        """
        # 1. 寫入該策略專屬的實體檔案 (logs/strategies/{name}.log)
        if group:
            group.log(level, msg)
            
        # 2. 系統控制台與 ZMQ 廣播
        info(f"[StrategyExecutor] {msg}")
        if self.server:
            self.server.publish("SYS_NOTIFICATION", {
                "type": "STRATEGY",
                "level": level,
                "message": msg,
                "strategy_id": group.name if group else "SYSTEM"
            })

    def on_order_update(self, data: dict):
        """
        Handles Global Order Update (with Broker Prefix).
        Format: {'id': 'Shioaji:123', 'status': 'Filled', ...}
        """
        order_id = data.get('id')
        status = data.get('status')
        
        for group in self.strategies:
            # Match against the stored pending ID (which should also be prefixed)
            if group.pending_order_id == order_id:
                self._handle_group_order_update(group, data)
                return
    
    def _handle_group_order_update(self, group, data):
        status = data.get('status')
        
        if status == 'Filled':
            deal_qty = data.get('deal_qty', group.max_order_qty) 
            avg_price = data.get('deal_price', data.get('price', 0))
            action = data.get('action') 
            is_buy = "Buy" in str(action)
            
            if group.position_qty == 0:
                group.avg_cost = avg_price
                group.position_qty += deal_qty if is_buy else -deal_qty
                self._log_ui(f"[{group.name}] Entry Filled: {deal_qty} @ {avg_price:.0f}")
                
                if group.execution_mode == 'Monitor' and group.current_data:
                    sl_price = group.current_data.get('sl_price', 0)
                    if sl_price != 0: self._register_sl_touch_order(group, avg_price, sl_price)
            else:
                old_pos = group.position_qty
                group.position_qty += deal_qty if is_buy else -deal_qty
                pnl = 0
                if old_pos > 0: pnl = (avg_price - group.avg_cost) * deal_qty
                else: pnl = (group.avg_cost - avg_price) * deal_qty
                group.total_realized_pnl += pnl
                self._log_ui(f"[{group.name}] Exit Filled. PnL: ${pnl:.0f}", "INFO")
                
                if group.position_qty == 0:
                    group.current_data = None; group.exit_signal_triggered = False; group.avg_cost = 0
                    group.trailing_active = False; group.trailing_max_profit = 0.0; group.initial_signal_price = 0.0                    
                    if group.active_sl_condition and self.touch_executor:
                        self.touch_executor.delete_condition(group.active_sl_condition)
                        group.active_sl_condition = None

            group.pending_order_id = None 
            self._save_state()
            
        elif status == 'Cancelled' or status == 'Failed':
            self._log_ui(f"[{group.name}] Order {status}. {data.get('msg', '')}", "WARN")
            group.pending_order_id = None
            if group.position_qty == 0: group.initial_signal_price = 0.0
            self._save_state()

    def _register_sl_touch_order(self, group, entry_price, sl_price):
        # ... Omitted for brevity (TouchExecutor integration needs careful testing later) ...
        pass 

              
    # def _record_data_snapshot(self, group, tick, data_manager):
        # """
        # 將每筆 Tick 觸發後的策略狀態寫入 CSV
        # """
        # try:
            # # 取得即時行情數據
            # agg = data_manager.aggregators.get(group.frequency)
            # bar = agg.current_bar if agg and agg.current_bar else None
            
            # close_price = float(tick.close)
            # o = f"{bar['Open']:.2f}" if bar else f"{close_price:.2f}"
            # h = f"{bar['High']:.2f}" if bar else f"{close_price:.2f}"
            # l = f"{bar['Low']:.2f}" if bar else f"{close_price:.2f}"
            # c = f"{close_price:.2f}"
            # v = str(bar['Volume']) if bar else str(tick.volume)

            # # 取得策略線位
            # lines = group.current_data if group.current_data else {}
            # entry = f"{lines.get('entry_price', 0):.2f}"
            # sl = f"{lines.get('sl_price', 0):.2f}"
            # tp = f"{lines.get('tp_price', 0):.2f}"

            # # 計算未實現損益
            # pnl = 0.0
            # if group.position_qty != 0:
                # pnl = (close_price - group.avg_cost) * group.position_qty

            # # 寫入 CSV 檔案
            # row = f"{tick.datetime_str},{o},{h},{l},{c},{v},{entry},{sl},{tp},{group.position_qty},{group.avg_cost:.2f},{pnl:.2f}\n"
            
            # with open(group.csv_path, 'a', encoding='utf-8') as f:
                # f.write(row)
                
        # except Exception as e:
            # # 靜默處理錯誤以防阻塞交易主線程
            # pass

    # def _record_numeric_log(self, group, tick, data_manager):
        # print(f"[DB] into _record_numeric_log")
        # """
        # 產生純數字格式日誌，用於後續比對策略線位與行情之誤差。
        # 格式: TIMESTAMP|O|H|L|C|V|ENTRY|SL|TP|POS|AVG_COST
        # """
        # try:
            # # 獲取當前 KBar (OHCLV)
            # agg = data_manager.aggregators.get(group.frequency)
            # if agg and agg.current_bar:
                # bar = agg.current_bar
                # o, h, l, c, v = bar['Open'], bar['High'], bar['Low'], bar['Close'], bar['Volume']
            # else:
                # # 若 Aggregator 尚未產生 KBar，則以當前 Tick 價格填充
                # o = h = l = c = float(tick.close)
                # v = int(tick.volume)

            # # 獲取三線協定線位
            # lines = group.current_data if group.current_data else {}
            # entry_line = lines.get('entry_price', 0.0)
            # sl_line = lines.get('sl_price', 0.0)
            # tp_line = lines.get('tp_price', 0.0)

            # # 組合紀錄字串
            # log_fields = [
                # tick.datetime_str,          # 時間戳記
                # f"{o:.2f}", f"{h:.2f}", f"{l:.2f}", f"{c:.2f}", str(v), # OHCLV
                # f"{entry_line:.2f}",        # 策略進場線
                # f"{sl_line:.2f}",           # 策略停損線
                # f"{tp_line:.2f}",           # 策略停利線
                # str(group.position_qty),    # 倉位
                # f"{group.avg_cost:.2f}"     # 平均成本
            # ]
            
            # # 寫入該策略專屬日誌，標記為 DATA 類別以便過濾
            # group.log("INFO", f"DATA_SNAPSHOT|{'|'.join(log_fields)}")
            
        # except Exception as e:
            # # 確保日誌紀錄失敗不會干擾主交易流程
            # pass

    def _monitor_entry(self, group, tick: StandardTick, bar_open):
        entry_price = group.current_data.get('entry_price', 0)
        if entry_price == 0: return
        current_price = float(tick.close)
        action = ""
        if entry_price > 0 and current_price >= entry_price: action = "Buy"
        elif entry_price < 0 and current_price <= abs(entry_price): action = "Sell"
        if not action: return 
        target_entry = abs(entry_price)
        
        if group.pending_order_id:
             pass 
        else:
            slippage_init = abs(current_price - target_entry)
            if slippage_init <= group.max_slippage:
                self._log_ui(f"[{group.name}] ENTRY Triggered: {action} @ {target_entry}")
                group.initial_signal_price = target_entry
                self._execute_order(group, action, target_entry, group.max_order_qty)

    def _execute_order(self, group, action, price, qty, reason=""):
        """
        執行下單操作，並將過程記錄到該策略的專屬日誌中。
        """
        # --- 步驟 1: 記錄訊號觸發 ---
        # 加上 group=group 參數，讓這條訊息寫入 logs/strategies/{名稱}.log
        self._log_ui(
            f"SIGNAL Triggered: {action} {qty} @ {price} (Reason: {reason})", 
            "INFO", 
            group=group
        )
        
        # --- 步驟 2: 執行實體下單 ---
        # 呼叫 TradingManager 進行路由下單
        order_id = self.trading_manager.place_order(
            group.contract_code, action, price, qty, group.account_id
        )
        
        # --- 步驟 3: 根據下單結果記錄日誌 ---
        if order_id:
            # 下單成功：記錄訂單 ID
            self._log_ui(
                f"Order Sent: {action} {qty} @ {price} (ID: {order_id})", 
                "SUCCESS", 
                group=group
            )
            group.active_orders.add(order_id)
        else:
            # 下單失敗：記錄錯誤
            self._log_ui(
                f"Order Placement Failed: {action} {qty} @ {price}", 
                "ERROR", 
                group=group
            )

    def _cancel_order(self, group):
        if not group.pending_order_id: return
        try: 
            # Cancel also needs routing, handled by TM parsing the ID prefix
            #TradingManager(self.adapters).cancel_order(group.pending_order_id)
            self.trading_manager.cancel_order(group.pending_order_id)
        except Exception as e: error(f"Cancel failed: {e}")

    # Standard management methods (start/stop/etc.) unchanged...
    def start_strategy(self, group_id):
        group = next((s for s in self.strategies if s.id == int(group_id)), None)
        if group:
            group.is_running = True
            self._activate_strategy(group)
            self._save_state()
            return True, f"Strategy {group_id} started."
        return False, "ID not found."
    
    def stop_strategy(self, group_id):
        group = next((s for s in self.strategies if s.id == int(group_id)), None)
        if group:
            group.stop_logging()
            group.is_running = False
            self._log_ui(f"Strategy '{group.name}' STOPPED.")
            self._save_state()
            return True, f"Strategy {group_id} stopped."
        return False, "ID not found."
        
    def toggle_strategy(self, group_id):
        """
        [強化] 切換指令追蹤
        """
        info(f"[Executor] CMD Received: TOGGLE ID={group_id}")
        
        group = next((s for s in self.strategies if s.id == int(group_id)), None)
        if not group:
            warn(f"[Executor] Toggle failed: Strategy ID {group_id} not found.")
            return False, f"ID {group_id} not found"
            
        if group.is_running:
            info(f"[Executor] Stopping strategy: {group.name}")
            return self.stop_strategy(group_id)
        else:
            info(f"[Executor] Starting strategy: {group.name}")
            return self.start_strategy(group_id)

    def add_strategy(self, config_data):
        new_id = 1
        if self.strategies: new_id = max(s.id for s in self.strategies) + 1
        config_data['id'] = new_id
        sys_default = float(self.config.get('default_profit_retention', 0.66))
        group = StrategyGroup(new_id, config_data, sys_default)
        self.strategies.append(group)
        self._save_config()
        self._log_ui(f"Strategy {new_id} added.")
        return True, "Added"
        
    def update_strategy(self, config_data):
        gid = int(config_data.get('id'))
        group = next((s for s in self.strategies if s.id == gid), None)
        if group:
            # Basic update logic (omitted full mapping for brevity, same as V2.2)
            # In real impl, map all fields from config_data to group properties
            if 'account_id' in config_data: group.account_id = config_data['account_id']
            if 'contract_code' in config_data: group.contract_code = config_data['contract_code']
            # ... update other fields ...
            self._save_config()
            return True, "Updated"
        return False, "Not Found"

    def delete_strategy(self, group_id):
        """
        [修正]: 將函式名稱由 remove_strategy 改為 delete_strategy 以符合 main_engine 呼叫邏輯。
        將策略從執行列表與設定檔中徹底移除 [修正 7-2-2]。
        """
        group = next((s for s in self.strategies if s.id == int(group_id)), None)
        if group:
            if group.is_running: 
                return False, "Stop first."
            self.strategies.remove(group)
            self._save_config()
            self._log_ui(f"Strategy {group_id} removed.")
            return True, "Removed"
        return False, "Not Found"
        
    def get_all_status(self): return [s.get_status_dict() for s in self.strategies]
    def get_all_configs(self): return [s.to_dict() for s in self.strategies]
    
    def get_available_modules(self): 
        """
        [修正] 支援掃描 plugins 根目錄與一級子目錄。
        """
        if not os.path.exists(STRATEGY_DIR): return []
        
        found_modules = []
        # 1. 掃描根目錄 (相容舊版)
        for f in os.listdir(STRATEGY_DIR):
            if f.endswith(".py") and f not in ["__init__.py", "strategy_core.py"]:
                found_modules.append(f)
        
        # 2. 掃描子目錄 (新版架構)
        for d in os.listdir(STRATEGY_DIR):
            d_path = os.path.join(STRATEGY_DIR, d)
            if os.path.isdir(d_path):
                for f in os.listdir(d_path):
                    if f.endswith(".py") and f not in ["__init__.py", "strategy_core.py"]:
                        # 我們回傳檔名，load_module 會負責尋找正確路徑
                        found_modules.append(f)
                        
        return sorted(list(set(found_modules)))
        
    def get_event_logs(self): return list(self.event_buffer)
    
    def _record_csv_data(self, group, tick, data_manager):
        """
        將每筆 Tick 觸發後的策略與行情狀態寫入 CSV。
        """
        try:
            # 1. 取得即時 OHCLV 數據
            agg = data_manager.aggregators.get(group.frequency)
            bar = agg.current_bar if agg and agg.current_bar else None
            
            close_price = float(tick.close)
            o = f"{bar['Open']:.2f}" if bar else f"{close_price:.2f}"
            h = f"{bar['High']:.2f}" if bar else f"{close_price:.2f}"
            l = f"{bar['Low']:.2f}" if bar else f"{close_price:.2f}"
            c = f"{close_price:.2f}"
            v = str(bar['Volume']) if bar else str(tick.volume)

            # 2. 取得策略三線數值
            lines = group.current_data if group.current_data else {}
            entry = f"{lines.get('entry_price', 0):.2f}"
            sl = f"{lines.get('sl_price', 0):.2f}"
            tp = f"{lines.get('tp_price', 0):.2f}"

            # 3. 計算即時未實現損益 (Unrealized PnL)
            upnl = 0.0
            if group.position_qty != 0:
                # 簡單計算：(現價 - 成本) * 口數 (多正空負需注意計算邏輯)
                # 假設多頭時 pos > 0, 空頭時 pos < 0
                upnl = (close_price - group.avg_cost) * group.position_qty

            # 4. 組合 CSV 列數據
            # 格式: ts,o,h,l,c,v,entry,sl,tp,pos,avg_cost,unrealized_pnl
            row_data = [
                tick.datetime_str, o, h, l, c, v,
                entry, sl, tp,
                str(group.position_qty), f"{group.avg_cost:.2f}", f"{upnl:.2f}"
            ]
            
            # 5. 寫入檔案 (採用附加模式 'a')
            with open(group.csv_path, 'a', encoding='utf-8') as f:
                f.write(",".join(row_data) + "\n")
                
        except Exception as e:
            # 增加 try-except 避免日誌錯誤影響到交易核心邏輯
            # 僅在系統日誌記錄錯誤
            error(f"[CSV Log Error] {group.name}: {e}")   

    def _evaluate_tick(self, tick):
        """
        [修正]: 將 self.strategies 的遍歷方式由 .items() 改為 list 直接迭代。
        """
        if not self.strategies:
            return

        # 因為 self.strategies 是 list，直接遍歷物件即可
        for strategy in self.strategies:
            # 1. 檢查策略是否處於運行狀態
            if not getattr(strategy, 'is_running', False):
                continue
            
            # 2. 檢查商品代碼是否匹配
            # 註: 支援 contract_code 或 symbol 屬性名
            strat_symbol = getattr(strategy, 'contract_code', getattr(strategy, 'symbol', None))
            
            if strat_symbol == tick.code:
                try:
                    # 3. 更新策略實例的最新價格快照
                    strategy.last_price = tick.close
                    
                    # 4. 觸發策略內部的邏輯計算
                    if hasattr(strategy, 'on_tick'):
                        strategy.on_tick(tick)
                    elif hasattr(strategy, 'update_tick'):
                        strategy.update_tick(tick)
                        
                except Exception as e:
                    # 避免單一策略報錯導致整個執行器崩潰
                    #from shared.logging_tool import error
                    error(f"[Executor] Strategy {getattr(strategy, 'id', 'Unknown')} logic error: {e}")

    # 同樣確保別名函式也存在
    def on_tick_update(self, tick, data_manager=None):
        self._evaluate_tick(tick)                   