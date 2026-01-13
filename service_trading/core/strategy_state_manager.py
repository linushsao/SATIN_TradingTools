# ==============================================================================
# strategy_state_manager.py
#
# Version: V0.4-003 (Retention Rate)
# 更新日期: 2025-11-30
# 描述:     策略狀態持久化管理器。
# ==============================================================================
# 更新日誌:
# V0.4-003: 新增 profit_retention_rate 與 current_retention_rate。
# V0.4-002: 新增 total_realized_pnl。
# ==============================================================================

import json
import os
import threading
from logging_tool import info, error

STATE_FILE = 'data/strategy_state.json'

class StrategyStateManager:
    def __init__(self, file_path=STATE_FILE):
        self.file_path = file_path
        self.lock = threading.Lock()
        self._ensure_dir()

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

    def save_state(self, strategies: list):
        """將所有策略的當前狀態儲存到檔案。"""
        state_data = {}
        for group in strategies:
            state_data[str(group.id)] = {
                "is_running": group.is_running,
                "position_qty": group.position_qty,
                "avg_cost": group.avg_cost,
                
                # Trailing State
                "trailing_active": group.trailing_active,
                "trailing_max_profit": group.trailing_max_profit,
                
                # V0.4-003 NEW: Retention Rates
                "profit_retention_rate": group.profit_retention_rate, # Config setting
                "current_retention_rate": group.current_retention_rate, # Active trade setting
                
                # PnL State
                "total_realized_pnl": group.total_realized_pnl,

                "entry_price": group.current_data.get('entry_price', 0) if group.current_data else 0,
                "sl_price": group.current_data.get('sl_price', 0) if group.current_data else 0,
                "tp_price": group.current_data.get('tp_price', 0) if group.current_data else 0,
                "direction": group.current_data.get('direction', '') if group.current_data else ''
            }
        
        with self.lock:
            try:
                with open(self.file_path, 'w', encoding='utf-8') as f:
                    json.dump(state_data, f, indent=4)
            except Exception as e:
                error(f"Failed to save strategy state: {e}")

    def load_state(self) -> dict:
        """讀取策略狀態。"""
        if not os.path.exists(self.file_path):
            return {}
        
        with self.lock:
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                error(f"Failed to load strategy state: {e}")
                return {}