# ==============================================================================
# service_trading/libs/adapters/fubon_adapter.py
#
# Version: V1.0-006 (Strip & Cert Expiry Fix)
# 更新日期: 2025-12-14
# 描述:     富邦證券 (Fubon) API 適配器。
#           [修正]: 
#             1. 對所有憑證執行 .strip()，避免格式錯誤。
#             2. 增加對 'Cert Expired' 錯誤的友好提示。
# ==============================================================================

import time
import datetime
import threading
import os
from typing import Dict, List, Any, Callable, Optional

# Shared Utilities
from shared.config_manager import _load_key_from_file
from shared.logging_tool import info, error, warn
from service_trading.core.interfaces import IBrokerAdapter
from shared.model_defs import (
    StandardTick, StandardOrder, StandardAccount, StandardPosition, StandardAccountSummary,
    OrderAction, OrderType, PriceType, OrderStatus
)

# SDK Import with Compatibility Fix
HAS_FUBON_SDK = False
try:
    from fubon_neo.sdk import FubonSDK, Order, Mode, Condition
    try:
        from fubon_neo.sdk import Direction
        from fubon_neo.sdk import OrderType as FubonOrderType
        from fubon_neo.sdk import PriceType as FubonPriceType
    except ImportError:
        print("[System] Fubon SDK: 'Direction/OrderType' import failed. Using local fallback.")
        class Direction:
            Buy = "Buy"
            Sell = "Sell"
        class FubonOrderType:
            ROD = "ROD"
            IOC = "IOC"
            FOK = "FOK"
        class FubonPriceType:
            Limit = "Limit"
            Market = "Market"

    HAS_FUBON_SDK = True

except ImportError as e:
    print(f"[System] Fubon SDK Critical Import Error: {e}")
    class FubonSDK: pass
    HAS_FUBON_SDK = False

class FubonAdapter(IBrokerAdapter):
    def __init__(self):
        self.api = None
        self.connected = False
        self.config = {}
        self.active_account = None
        self.cb_on_tick = None
        self.cb_on_order_update = None
        self.subscribed_codes = set()

    def initialize(self, config: Dict[str, Any]):
        self.config = config
        info(f"[FubonAdapter] Initialized.")

    def connect(self, api_key: str = "", secret_key: str = "", simulation: bool = True) -> bool:
        if not HAS_FUBON_SDK:
            error("[FubonAdapter] Fubon SDK not installed or import failed.")
            return False

        # 1. 讀取設定 (從檔案載入)
        user_id_path = self.config.get('user_id_path', '')
        user_id = _load_key_from_file(user_id_path)
        if not user_id: user_id = self.config.get('user_id') or api_key

        password_path = self.config.get('password_path', '')
        password = _load_key_from_file(password_path)
        if not password: password = self.config.get('password') or secret_key

        cert_path = self.config.get('cert_path', '')
        cert_pass_path = self.config.get('cert_pass_path', '')
        cert_pass = _load_key_from_file(cert_pass_path)

        # [CRITICAL FIX] 去除空白符號
        if user_id: user_id = user_id.strip()
        if password: password = password.strip()
        if cert_pass: cert_pass = cert_pass.strip()

        # [DEBUG INFO]
        info(f"[FubonAdapter] Loading Credentials:")
        info(f"  > ID Path: {user_id_path} [{'OK' if user_id else 'EMPTY'}]")
        info(f"  > PWD Path: {password_path} [{'OK' if password else 'EMPTY'}]")
        info(f"  > Cert Path: {cert_path}")
        
        if not user_id or not password:
            error(f"[FubonAdapter] Missing User ID or Password.")
            return False
            
        try:
            masked_id = user_id[:3] + "****" if user_id and len(user_id) > 3 else "User"
            info(f"[FubonAdapter] Connecting as {masked_id}...")
            
            self.api = FubonSDK()
            login_res = self.api.login(user_id, password, cert_path, cert_pass)
            
            # 檢查結果
            is_success = getattr(login_res, 'is_success', False)
            message = getattr(login_res, 'message', '')
            
            # [ERROR HANDLING] 特別處理憑證過期
            if not is_success and "Cert Expired" in str(message):
                error(f"[FubonAdapter] CRITICAL: Your Certificate (.pfx) has EXPIRED. Please renew it from Fubon Securities.")
                error(f"[FubonAdapter] Path: {cert_path}")
                return False

            if is_success or login_res is True:
                self.connected = True
                info("[FubonAdapter] Login Successful.")
                
                accounts = getattr(self.api, 'accounts', [])
                if accounts:
                    self.active_account = next((a for a in accounts if getattr(a, 'account_type', '') == 'F'), accounts[0])
                    info(f"[FubonAdapter] Active Account: {self.active_account}")
                else:
                    warn("[FubonAdapter] No accounts found.")
                
                if hasattr(self.api, 'set_on_filled'):
                    self.api.set_on_filled(self._on_fubon_filled)
                if hasattr(self.api, 'set_on_order_changed'):
                    self.api.set_on_order_changed(self._on_fubon_order_changed)
                return True
            else:
                error(f"[FubonAdapter] Login Failed: {login_res}")
                return False

        except Exception as e:
            error(f"[FubonAdapter] Connect Exception: {e}")
            import traceback
            traceback.print_exc()
            return False

    def set_callbacks(self, on_tick: Callable[[StandardTick], None], on_order_update: Callable[[Dict], None]):
        self.cb_on_tick = on_tick
        self.cb_on_order_update = on_order_update

    def subscribe_market_data(self, contract_code: str) -> bool:
        if not self.connected: return False
        try:
            if hasattr(self.api, 'marketdata'):
                self.api.marketdata.subscribe(contract_code, callback=self._on_fubon_quote)
                self.subscribed_codes.add(contract_code)
                info(f"[FubonAdapter] Subscribed to {contract_code}")
                return True
            return False
        except Exception as e:
            error(f"[FubonAdapter] Subscribe Failed: {e}")
            return False

    def unsubscribe_market_data(self, contract_code: str) -> bool:
        if contract_code in self.subscribed_codes:
            try:
                if hasattr(self.api, 'marketdata'):
                    self.api.marketdata.unsubscribe(contract_code)
                self.subscribed_codes.remove(contract_code)
                return True
            except: pass
        return False

    def _on_fubon_quote(self, topic, message):
        if not self.cb_on_tick: return
        try:
            code = message.get('symbol') or message.get('code')
            ts = float(message.get('ts', time.time())) / 1000000 if message.get('ts') and message.get('ts') > 10000000000 else float(message.get('ts', time.time()))
            close = float(message.get('close', 0))
            vol = int(message.get('volume', 0))
            
            std_tick = StandardTick(
                code=code, ts=ts,
                datetime_str=datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S.%f'),
                close=close, volume=vol, amount=0.0,
                bid_price=float(message.get('bid_price', [0])[0]),
                ask_price=float(message.get('ask_price', [0])[0]),
                sim_trade=False
            )
            self.cb_on_tick(std_tick)
        except Exception:
            # 【關鍵修正】：不再沈默失敗
            import traceback
            error(f"[FubonAdapter] Quote processing error: {traceback.format_exc()}")
            
    def download_history(self, contract_code: str, start_date: str, end_date: str) -> Any:
        return None

    def get_contracts(self) -> List[Dict[str, Any]]:
        return []

    def place_order(self, order_spec: StandardOrder) -> str:
        if not self.connected or not self.active_account:
            raise ValueError("[FubonAdapter] Not connected.")

        try:
            action = Direction.Buy if order_spec.action == OrderAction.BUY else Direction.Sell
            price_type = FubonPriceType.Limit if order_spec.price_type == PriceType.LMT else FubonPriceType.Market
            order_type = FubonOrderType.ROD
            if order_spec.order_type == OrderType.IOC: order_type = FubonOrderType.IOC
            elif order_spec.order_type == OrderType.FOK: order_type = FubonOrderType.FOK
            
            fubon_order = Order(
                code=order_spec.code, symbol=order_spec.code,
                action=action, price=order_spec.price, quantity=order_spec.quantity,
                order_type=order_type, price_type=price_type, account=self.active_account
            )
            
            result = self.api.place_order(self.active_account, fubon_order)
            if hasattr(result, 'order_id'): return str(result.order_id)
            return str(result)
        except Exception as e:
            error(f"[FubonAdapter] Place Order Error: {e}")
            return ""

    def cancel_order(self, order_id: str) -> bool:
        try:
            self.api.cancel_order(self.active_account, order_id)
            return True
        except Exception as e:
            error(f"[FubonAdapter] Cancel Failed: {e}")
            return False

    def _on_fubon_order_changed(self, data):
        if not self.cb_on_order_update: return
        status_map = {"Filled": "Filled", "Cancelled": "Cancelled", "Pending": "Pending", "Error": "Failed"}
        raw_status = getattr(data, 'status', 'Unknown')
        if hasattr(data, 'order_status'): raw_status = str(data.order_status)
        std_status = status_map.get(raw_status, "Unknown")
        
        update_data = {
            "id": getattr(data, 'order_id', ''),
            "status": std_status,
            "qty": getattr(data, 'quantity', 0),
            "price": getattr(data, 'price', 0),
            "action": getattr(data, 'action', ''),
            "msg": getattr(data, 'message', '')
        }
        if std_status == "Filled":
            update_data['deal_qty'] = getattr(data, 'filled_quantity', 0)
            update_data['deal_price'] = getattr(data, 'filled_price', 0)
        self.cb_on_order_update(update_data)

    def _on_fubon_filled(self, data):
        self._on_fubon_order_changed(data)

    def list_available_accounts(self) -> List[StandardAccountSummary]:
        results = []
        if not self.connected: return results
        try:
            accounts = getattr(self.api, 'accounts', [])
            for acc in accounts:
                acc_id = getattr(acc, 'account', 'Unknown')
                acc_type_raw = getattr(acc, 'account_type', 'G')
                type_str = "Future" if acc_type_raw == 'F' else ("Stock" if acc_type_raw == 'S' else "General")
                user_id = self.config.get('user_id')
                if not user_id:
                     path = self.config.get('user_id_path', '')
                     user_id = _load_key_from_file(path)

                results.append(StandardAccountSummary(
                    account_id=str(acc_id), login_id=user_id or 'User',
                    account_type=type_str, is_signed=True
                ))
        except Exception as e:
            error(f"[FubonAdapter] List Accounts Error: {e}")
        return results

    def get_account_data(self, account_type: str = "future") -> StandardAccount:
        equity = 0.0
        acc_id = "Unknown"
        if self.active_account:
            acc_id = str(getattr(self.active_account, 'account', 'Unknown'))
            try:
                margin = self.api.get_margin(self.active_account)
                equity = getattr(margin, 'equity', 0.0)
            except: pass
            
        return StandardAccount(account_id=acc_id, currency="TWD", balance=equity, equity=equity)

    def get_positions(self, account_type: str = "future") -> List[StandardPosition]:
        results = []
        if not self.active_account: return results
        try:
            positions = self.api.get_positions(self.active_account)
            for p in positions:
                results.append(StandardPosition(
                    code=getattr(p, 'symbol', ''),
                    direction="Long" if getattr(p, 'direction', '') == 'Buy' else "Short",
                    quantity=int(getattr(p, 'quantity', 0)),
                    avg_price=float(getattr(p, 'price', 0)),
                    current_price=float(getattr(p, 'last_price', 0)),
                    pnl=float(getattr(p, 'pnl', 0))
                ))
        except Exception as e:
            error(f"[FubonAdapter] Get Positions Error: {e}")
        return results