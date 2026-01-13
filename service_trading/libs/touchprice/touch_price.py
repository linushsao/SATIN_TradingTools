# ==============================================================================
# libs/touchprice/touch_price.py
#
# Version: V0.2-001 (Server Port)
# 更新日期: 2025-12-05
# 描述:     觸價執行器 (Server-side Adaptation)。
#           修改為被動接收行情 (Passive Tick Receiver)，不再主動訂閱 Shioaji Quote。
# ==============================================================================
from typing import Any  # <--- 修正 NameError: name 'Any' is not defined
from decimal import Decimal # <--- 確保 Decimal 運算正常
import shioaji as sj
import typing
import datetime
from shioaji import TickSTKv1, Exchange, BidAskSTKv1
from pydantic import StrictInt
from touchprice.constant import Trend, PriceType
from touchprice.condition import (
    Price,
    TouchOrderCond,
    StoreCond,
    PriceGap,
    StatusInfo,
    StoreLossProfit,
)

def get_contracts(api: sj.Shioaji):
    contracts = {
        code: contract
        for name, iter_contract in api.Contracts
        for code, contract in iter_contract._code2contract.items()
    }
    return contracts

class TouchOrderExecutor:
    def __init__(self, api: sj.Shioaji):
        self.api: sj.Shioaji = api
        self.conditions: typing.Dict[
            str, typing.List[typing.Union[StoreLossProfit, StoreCond]]
        ] = {}
        self.infos: typing.Dict[str, StatusInfo] = {}
        # 注意：若 API 尚未登入完成，Contracts 可能為空，建議由外部確保已登入
        self.contracts: dict = {} 
        
        # V0.2-001: Removed active subscription setup.
        # The Engine's MarketDataManager will define when to call integration_tick.

    def update_contracts(self):
        """Manually refresh contracts map (Call after login)"""
        try:
            self.contracts = get_contracts(self.api)
        except Exception as e:
            print(f"[TouchExecutor] Update Contracts Failed: {e}")

    def update_snapshot(self, contract: sj.contracts.Contract):
        code = contract.target_code if contract.target_code else contract.code
        if code not in self.infos.keys():
            # V0.2-001: Use try-except for snapshots as it requires network
            try:
                snapshots = self.api.snapshots([contract])
                if snapshots:
                    snapshot = snapshots[0]
                    self.infos[code] = StatusInfo(**snapshot)
                    now = datetime.datetime.now(datetime.timezone.utc)
                    self.infos[code].add_ts = now.timestamp()
            except Exception as e:
                print(f"[TouchExecutor] Snapshot error for {code}: {e}")

    @staticmethod
    def set_price(price_info: Price, contract: sj.contracts.Contract):
        if price_info.price_type == PriceType.LimitUp:
            price_info.price = contract.limit_up
        elif price_info.price_type == PriceType.LimitDown:
            price_info.price = contract.limit_down
        elif price_info.price_type == PriceType.Unchanged:
            price_info.price = contract.reference
        return PriceGap(**dict(price_info))

    def adjust_condition(
        self, condition: TouchOrderCond, contract: sj.contracts.Contract
    ):
        tconds_dict = condition.touch_cmd.dict(exclude={"code"}, exclude_none=True)
        if tconds_dict:
            for key, value in tconds_dict.items():
                if key not in ["volume", "total_volume", "ask_volume", "bid_volume"]:
                    tconds_dict[key] = TouchOrderExecutor.set_price(
                        Price(**value), contract
                    )
            # If order_cmd.code is different, we need to find that contract too.
            # For simplicity, assume self.contracts is populated.
            order_code = condition.order_cmd.code
            # Simple fallback if order contract not found (use touch contract)
            tconds_dict["order_contract"] = self.contracts.get(order_code, contract)
            tconds_dict["order"] = condition.order_cmd.order
            return StoreCond(**tconds_dict)

    def add_condition(self, condition: TouchOrderCond):
        if not self.contracts:
            self.update_contracts()
            
        code = condition.touch_cmd.code
        if code not in self.contracts:
            print(f"[TouchExecutor] Contract {code} not found in cache.")
            return

        touch_contract = self.contracts[code]
        self.update_snapshot(touch_contract)
        
        store_condition = self.adjust_condition(condition, touch_contract)
        if store_condition:
            target_code = (
                touch_contract.target_code
                if touch_contract.target_code
                else touch_contract.code
            )
            if target_code in self.conditions.keys():
                self.conditions[target_code].append(store_condition)
            else:
                self.conditions[target_code] = [store_condition]
            
            # V0.2-001: Removed api.quote.subscribe. Engine handles data feed.
            print(f"[TouchExecutor] Condition added for {target_code}")

    def delete_condition(self, condition: TouchOrderCond):
        code = condition.touch_cmd.code
        if code not in self.contracts: return

        touch_contract = self.contracts[code]
        store_condition = self.adjust_condition(condition, touch_contract)
        if self.conditions.get(code, False) and store_condition:
            if store_condition in self.conditions[code]:
                self.conditions[code].remove(store_condition)
                return self.conditions[code]

    def touch_cond(self, info: typing.Dict, value: typing.Union[StrictInt, float]):
        trend = info.pop("trend")
        if len(info) == 1:
            data = info[list(info.keys())[0]]
            if trend == Trend.Up:
                if data <= value:
                    return True
            elif trend == Trend.Down:
                if data >= value:
                    return True
            elif trend == Trend.Equal:
                if data == value:
                    return True

    def touch(self, code: str):
        conditions = self.conditions.get(code, False)
        if conditions:
            info = self.infos[code].dict()
            for num, conds in enumerate(conditions):
                if not conds.excuted:
                    order_contract = conds.order_contract
                    if isinstance(conds, StoreCond):
                        order = conds.order
                        cond = conds.dict(
                            exclude={
                                "order",
                                "order_contract",
                                "excuted",
                                "excuted_cb",
                                "result", # Exclude result from check
                            },
                            exclude_none=True,
                        )
                        if all(
                            self.touch_cond(value, float(info[key]))
                            for key, value in cond.items()
                        ):
                            print(f"[TouchExecutor] Triggered! Placing order for {code}")
                            self.conditions[code][num].excuted = True
                            
                            # V0.2-001: Execute Order via API
                            try:
                                trade = self.api.place_order(
                                    order_contract,
                                    order,
                                    cb=self.conditions[code][num].excuted_cb,
                                )
                                self.conditions[code][num].result = trade
                            except Exception as e:
                                print(f"[TouchExecutor] Place Order Error: {e}")


    def integration_tick(self, tick: Any):
        """
        [方案 B 修正版] 接收系統報價並處理觸價邏輯。
        修正點：無視代碼字串不匹配，直接將最新價格更新至現有監聽資訊中。
        """
        try:
            # 1. 檢查是否為模擬成交
            is_sim = getattr(tick, 'sim_trade', False)
            if is_sim:
                return

            # 2. 修正核心：尋找目前註冊的第一個 (或對應的) 資訊快取
            # 即使 tick.code (TMFA6) 與 infos 的 key (TXFR1) 不同，也應進行更新
            for registered_code in self.infos.keys():
                info = self.infos[registered_code]
                
                # 更新行情數值
                info.close = Decimal(str(getattr(tick, 'close', 0)))
                info.high = Decimal(str(getattr(tick, 'high', info.close)))
                info.low = Decimal(str(getattr(tick, 'low', info.close)))
                info.total_volume = int(getattr(tick, 'total_volume', 0))
                info.volume = int(getattr(tick, 'volume', 0))
                
                # 內外盤判定
                tick_type = getattr(tick, 'tick_type', 0)
                if tick_type == 1:
                    info.ask_volume = (info.ask_volume + info.volume if info.ask_volume else info.volume)
                    info.bid_volume = 0
                elif tick_type == 2:
                    info.bid_volume = (info.bid_volume + info.volume if info.bid_volume else info.volume)
                    info.ask_volume = 0
                
                # 觸發觸價檢查邏輯
                self.touch(registered_code)
                
        except Exception as e:
            print(f"[TouchOrderExecutor] Tick Process Error: {e}")