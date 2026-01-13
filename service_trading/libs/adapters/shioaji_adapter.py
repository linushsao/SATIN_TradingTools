# ==============================================================================
# service_trading/libs/adapters/shioaji_adapter.py
#
# Version: V1.4-007 (Add Micro TAIEX)
# 更新日期: 2025-12-15
# 描述:     Shioaji API 適配器。
#           [修正]: 新增 TMFR1 (微型台指近一) 至預設合約列表。
# ==============================================================================

import shioaji as sj
from shioaji import constant
from typing import Dict, List, Any, Callable, Optional
from datetime import datetime
import pandas as pd
import os
import glob

# Shared Utils
from shared.config_manager import _load_key_from_file
from service_trading.core.interfaces import IBrokerAdapter
from shared.model_defs import (
    StandardTick, StandardOrder, StandardAccount, StandardPosition, StandardAccountSummary,
    OrderAction, OrderType, PriceType, OrderStatus
)

class ShioajiAdapter(IBrokerAdapter):
    def __init__(self, config: Dict[str, Any] = None):
        self.api = None 
        self.simulation = True
        self.config = config or {}
        self.contracts_map = {} 
        self.cb_on_tick = None
        self.cb_on_order_update = None

    def initialize(self, config: Dict[str, Any]):
        self.config = config

    def _find_ca_path(self, configured_path: str) -> str:
        # 強制轉換為絕對路徑
        if configured_path:
            abs_path = os.path.abspath(configured_path)
            if os.path.exists(abs_path):
                return abs_path
        
        # 搜尋備用路徑
        local_key_pfx = glob.glob(os.path.join(os.getcwd(), "key", "*.pfx"))
        if local_key_pfx: return os.path.abspath(local_key_pfx[0])
        
        cwd_pfx = glob.glob(os.path.join(os.getcwd(), "*.pfx"))
        if cwd_pfx: return os.path.abspath(cwd_pfx[0])
        
        return ""

    def connect(self, api_key: str = None, secret_key: str = None, simulation: bool = True) -> bool:
        self.simulation = simulation
        
        # 取得設定檔中的路徑
        api_key_path = self.config.get('api_key_path', '')
        secret_key_path = self.config.get('secret_key_path', '')
        ca_passwd_path = self.config.get('ca_passwd_path', '')
        raw_ca_path = self.config.get('ca_path', '')

        # 1. 載入檔案內容
        if not api_key: api_key = _load_key_from_file(api_key_path)
        if not secret_key: secret_key = _load_key_from_file(secret_key_path)
        ca_passwd = _load_key_from_file(ca_passwd_path)

        # 2. 清理空白符號
        if api_key: api_key = api_key.strip()
        if secret_key: secret_key = secret_key.strip()
        if ca_passwd: ca_passwd = ca_passwd.strip()

        # [DEBUG INFO] 強制顯示讀取路徑與狀態
        print(f"[ShioajiAdapter] Loading Credentials (Config Check):")
        print(f"  > API Key Path:     '{api_key_path}' [{'OK' if api_key else 'EMPTY/MISSING'}]")
        print(f"  > Secret Key Path:  '{secret_key_path}' [{'OK' if secret_key else 'EMPTY/MISSING'}]")
        print(f"  > CA PFX Path:      '{raw_ca_path}'")
        print(f"  > CA Password Path: '{ca_passwd_path}' [{'OK' if ca_passwd else 'Using Secret Key (Fallback)'}]")

        # 決定最終使用的 CA 密碼
        final_ca_passwd = ca_passwd if ca_passwd else secret_key

        if not api_key or not secret_key:
            print("[ShioajiAdapter] Error: API Key or Secret Key missing.")
            return False

        try:
            if self.api:
                try: self.api.logout()
                except: pass
            
            print(f"[ShioajiAdapter] Initializing (Sim={simulation})...")
            self.api = sj.Shioaji(simulation=simulation)
            
            self.api.quote.set_on_tick_fop_v1_callback(self._on_sj_tick)
            self.api.quote.set_on_tick_stk_v1_callback(self._on_sj_tick)
            self.api.quote.set_on_bidask_fop_v1_callback(self._on_sj_bidask)
            self.api.quote.set_on_bidask_stk_v1_callback(self._on_sj_bidask)
            self.api.set_order_callback(self._on_sj_order_callback)
            
            self.api.login(api_key=api_key, secret_key=secret_key)
            
            # CA Activation
            if self.simulation:
                # 尋找 CA 檔案絕對路徑
                ca_path = self._find_ca_path(raw_ca_path)
                
                if ca_path:
                    # 再次確認 CA 路徑
                    print(f"[ShioajiAdapter] Activating CA...")
                    print(f"  > Actual CA File:   {ca_path}")
                    
                    try:
                        self.api.activate_ca(ca_path=ca_path, ca_passwd=final_ca_passwd, person_id=api_key)
                        print(f"[ShioajiAdapter] CA Activated Successfully.")
                    except Exception as e:
                        print(f"[ShioajiAdapter] CA Activation Warning: {e}")
                        if "mac verify failure" in str(e):
                            print("  -> Hint: Password incorrect. Please check content of .config/shioaji/shioaji_ca_passwd.txt")
                else:
                    print(f"[ShioajiAdapter] Warning: CA file not found! Searched at '{raw_ca_path}'")
            
            print("[ShioajiAdapter] Connected.")
            return True
            
        except Exception as e:
            print(f"[ShioajiAdapter] Connect Error: {e}")
            return False

    def set_callbacks(self, on_tick: Callable[[StandardTick], None], on_order_update: Callable[[Dict], None]):
        self.cb_on_tick = on_tick
        self.cb_on_order_update = on_order_update

    def _get_contract(self, code: str):
        if code in self.contracts_map: return self.contracts_map[code]
        c = None
        try: c = self.api.Contracts.Futures[code]
        except: pass
        if not c:
            try: c = self.api.Contracts.Stocks[code]
            except: pass
        if c: self.contracts_map[code] = c
        return c

    def subscribe_market_data(self, contract_code: str) -> bool:
        c = self._get_contract(contract_code)
        if c:
            try:
                self.api.quote.subscribe(c, quote_type=sj.constant.QuoteType.Tick)
                self.api.quote.subscribe(c, quote_type=sj.constant.QuoteType.BidAsk)
                return True
            except Exception as e:
                print(f"[ShioajiAdapter] Subscribe failed for {contract_code}: {e}")
                return False
        return False

    def unsubscribe_market_data(self, contract_code: str) -> bool:
        c = self._get_contract(contract_code)
        if c:
            try:
                self.api.quote.unsubscribe(c, quote_type=sj.constant.QuoteType.Tick)
                self.api.quote.unsubscribe(c, quote_type=sj.constant.QuoteType.BidAsk)
                return True
            except Exception as e:
                print(f"[ShioajiAdapter] Unsubscribe failed for {contract_code}: {e}")
                return False
        return False

    def _on_sj_tick(self, exchange, tick):
        if not self.cb_on_tick: return
        ts = datetime.now().timestamp()
        dt_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        if hasattr(tick, 'datetime'):
            ts = tick.datetime.timestamp()
            dt_str = tick.datetime.strftime('%Y-%m-%d %H:%M:%S.%f')
        std_tick = StandardTick(
            code=tick.code, ts=ts, datetime_str=dt_str,
            close=float(tick.close), volume=int(tick.volume),
            amount=float(getattr(tick, 'amount', 0.0)),
            bid_price=0.0, bid_volume=0, ask_price=0.0, ask_volume=0,
            sim_trade=bool(getattr(tick, 'simtrade', 0))
        )
        self.cb_on_tick(std_tick)

    def _on_sj_bidask(self, exchange, bidask):
        if not self.cb_on_tick: return
        ts = datetime.now().timestamp()
        dt_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        if hasattr(bidask, 'datetime'):
            ts = bidask.datetime.timestamp()
            dt_str = bidask.datetime.strftime('%Y-%m-%d %H:%M:%S.%f')
        best_bid = float(bidask.bid_price[0]) if bidask.bid_price else 0.0
        best_ask = float(bidask.ask_price[0]) if bidask.ask_price else 0.0
        bid_vol = int(bidask.bid_volume[0]) if bidask.bid_volume else 0
        ask_vol = int(bidask.ask_volume[0]) if bidask.ask_volume else 0
        std_tick = StandardTick(
            code=bidask.code, ts=ts, datetime_str=dt_str,
            close=0.0, volume=0, amount=0.0,
            bid_price=best_bid, bid_volume=bid_vol,
            ask_price=best_ask, ask_volume=ask_vol,
            sim_trade=bool(getattr(bidask, 'simtrade', 0))
        )
        self.cb_on_tick(std_tick)

    def _on_sj_order_callback(self, state, msg):
        if not self.cb_on_order_update: return
        data = {"raw_status": str(state), "msg": msg}
        sj_order = getattr(msg, 'order', None)
        if sj_order:
            data['id'] = str(sj_order.id)
            data['seqno'] = str(sj_order.seqno)
            data['action'] = str(sj_order.action)
            data['price'] = float(sj_order.price)
            data['qty'] = int(sj_order.quantity)
        sj_status = getattr(msg, 'status', None)
        if sj_status:
            s_val = str(sj_status.status)
            if "Filled" in s_val: data['status'] = "Filled"
            elif "Cancelled" in s_val: data['status'] = "Cancelled"
            elif "Submitted" in s_val: data['status'] = "Submitted"
            elif "Failed" in s_val: data['status'] = "Failed"
            else: data['status'] = "Pending"
            if hasattr(sj_status, 'deals') and sj_status.deals:
                total_qty = sum([d.quantity for d in sj_status.deals])
                avg_price = sum([d.price * d.quantity for d in sj_status.deals]) / total_qty if total_qty else 0
                data['deal_qty'] = total_qty
                data['deal_price'] = avg_price
        self.cb_on_order_update(data)

    def download_history(self, contract_code: str, start_date: str, end_date: str) -> Any:
        contract = self._get_contract(contract_code)
        if not contract: return pd.DataFrame()
        try:
            kbars = self.api.kbars(contract, start=start_date, end=end_date)
            df = pd.DataFrame({**kbars})
            if not df.empty: df.ts = pd.to_datetime(df.ts)
            return df
        except Exception as e:
            print(f"[ShioajiAdapter] Download Error: {e}")
            return pd.DataFrame()

    def get_contracts(self) -> List[Dict[str, Any]]:
        # [MOD] 新增 TMFR1 (微台)
        contracts_list = [
            {"code": "TXFR1", "name": "台指期近一 (連續)", "exchange": "TAIFEX"},
            {"code": "MXFR1", "name": "小台指近一 (連續)", "exchange": "TAIFEX"},
            {"code": "TMFR1", "name": "微型台指近一 (連續)", "exchange": "TAIFEX"}
        ]
        if self.api:
            try:
                targets = ["TXF", "MXF", "TMF"]
                for category in targets:
                    if hasattr(self.api.Contracts.Futures, category):
                        c_iter = getattr(self.api.Contracts.Futures, category)
                        for c in c_iter:
                            contracts_list.append({"code": c.code, "name": c.name, "exchange": c.exchange.value})
                            break
            except: pass
        return contracts_list

    def place_order(self, order_spec: StandardOrder) -> str:
        contract = self._get_contract(order_spec.code)
        if not contract: raise ValueError(f"Contract {order_spec.code} not found")
        action = constant.Action.Buy if order_spec.action == OrderAction.BUY else constant.Action.Sell
        ptype = constant.FuturesPriceType.LMT
        if order_spec.price_type == PriceType.MKT: ptype = constant.FuturesPriceType.MKT
        otype = constant.OrderType.ROD
        if order_spec.order_type == OrderType.IOC: otype = constant.OrderType.IOC
        elif order_spec.order_type == OrderType.FOK: otype = constant.OrderType.FOK
        target_account = self.api.futopt_account
        if contract.security_type in [constant.SecurityType.Stock, constant.SecurityType.Index]:
            target_account = self.api.stock_account
            ptype = constant.StockPriceType.LMT if order_spec.price_type == PriceType.LMT else constant.StockPriceType.MKT
        if not target_account: raise ValueError("No valid account found.")
        sj_order = self.api.Order(
            price=order_spec.price, quantity=order_spec.quantity,
            action=action, price_type=ptype, order_type=otype,
            octype=constant.FuturesOCType.Auto, account=target_account
        )
        trade = self.api.place_order(contract, sj_order)
        return str(trade.order.id)

    def cancel_order(self, order_id: str) -> bool:
        print(f"[ShioajiAdapter] Cancel order {order_id} requested.")
        return False

    def list_available_accounts(self) -> List[StandardAccountSummary]:
        results = []
        if not self.api: return results
        try:
            accounts = self.api.list_accounts()
            for acc in accounts:
                atype = "Future" if acc.account_type.value == 'F' else "Stock"
                results.append(StandardAccountSummary(
                    account_id=acc.account_id, login_id=acc.username,
                    account_type=atype, is_signed=acc.signed
                ))
        except: pass
        return results

    def get_account_data(self, account_type: str = "future") -> StandardAccount:
        acc_id = "Unknown"; equity = 0.0
        if account_type == "future" and self.api.futopt_account:
            acc_id = self.api.futopt_account.account_id
            try:
                margin = self.api.margin(self.api.futopt_account)
                equity = float(margin.equity)
            except: pass
        return StandardAccount(account_id=acc_id, currency="TWD", balance=equity, equity=equity)

    def get_positions(self, account_type: str = "future") -> List[StandardPosition]:
        results = []
        if account_type == "future" and self.api.futopt_account:
            try:
                positions = self.api.list_positions(self.api.futopt_account)
                for p in positions:
                    results.append(StandardPosition(
                        code=p.code, direction="Long" if p.direction == constant.Action.Buy else "Short",
                        quantity=int(p.quantity), avg_price=float(p.price),
                        current_price=float(p.last_price), pnl=float(p.pnl)
                    ))
            except: pass
        return results