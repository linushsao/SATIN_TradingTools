# ==============================================================================
# client_gui/plugins/pages/live_trading/plugin.py
#
# Version: V2.8-005 (Race Condition Fix)
# 更新日期: 2025-12-16
# 描述:     即時交易外掛。
#           [修正]: 
#             1. refresh_data 優先設定 UI 的商品代碼 (set_code)，解決標題空白的競態問題。
# ==============================================================================

import os
import sys
from datetime import datetime, timedelta 
import pandas as pd
import numpy as np

from kernel.interface import ISateGuiPlugin
# [FIX] Import ServiceTimeoutError to catch connection timeouts
from kernel.services import ServiceError, ServiceTimeoutError
from .layout import LiveTradingWidget, LiveTradingOptionsDialog, ContractManagerDialog
from ui_lib.layouts import HistoryDownloadDialog, IndicatorManagerDialog 
from shared.config_manager import save_config, CONFIG_FILE, load_config

from shared.capabilities import (
    CAP_MARKET_DATA, 
    CAP_ACCOUNT_INFO, 
    CAP_HISTORICAL_DATA, 
    CAP_STRATEGY_HOST
)

class LiveTradingPlugin(ISateGuiPlugin):
    def __init__(self):
        self.widget = None
        self.context = None
        self.current_code = None
        self._checked_codes = set() 
        self.app_data_dir = "" 

    @property
    def plugin_id(self) -> str:
        return "sate.core.live"

    @property
    def display_name(self) -> str:
        return "Live Trading"

    def initialize(self, context):
        self.context = context
        self.widget = LiveTradingWidget()
        
        # Get AppData path
        self.app_data_dir = self.context.get_app_data_dir("01_live_trading")
        
        # Inject Context & Callback
        self.widget.chart_widget.set_context(self.context)
        self.widget.chart_widget.exec_plugin_callback = self._execute_plugin_from_appdata
        
        config = self.context.get_config()
        self.current_code = config.get('last_futures_contract')
        
        self.widget.sig_contract_selected.connect(self.on_contract_selected)
        self.widget.strategy_table.sig_toggle_strategy.connect(self.on_toggle_strategy)
        # [修正]: 連結 Undeploy 信號
        self.widget.strategy_table.sig_undeploy_strategy.connect(self.on_undeploy_strategy)
        
        self.widget.strategy_table.cellDoubleClicked.connect(self.on_table_double_click)
        
        self.widget.sig_config_indicators.connect(self.on_config_indicators)
        self.widget.sig_open_options.connect(self.on_config_options)
        self.widget.sig_download_history.connect(self.on_download_history)
        self.widget.sig_manage_contracts.connect(self.on_manage_contracts)
        
        # [FIX] Fail-Safe Initialization
        try:
            self.refresh_data()
        except Exception as e:
            self.context.log("WARN", f"[Live] Initial data fetch failed (Offline?): {e}")

    def get_widget(self):
        return self.widget

    def on_activate(self):
        # When tab is clicked, try to refresh again
        self.widget.chart_widget.refresh_chart()
        self.refresh_strategies()
        # Also try to refresh market data if it failed previously
        try:
            self.refresh_data()
        except Exception:
            pass 

    def on_zmq_event(self, topic: str, payload: dict):
        if topic == "TICK":
            self.widget.tick_table.add_tick(payload)
            p = payload.get('price'); v = payload.get('vol')
            if p and v: self.widget.chart_widget.process_tick(p, v)
            
        elif topic == "KBAR":
            target_freq = self.context.get_config().get('view_kbar_freq', 15)
            recv_freq = payload.get('freq')
            
            if recv_freq == target_freq:
                data = payload.get('data', [])
                
                # [新增日誌]: 追蹤 00:00 附近資料是否正確抵達
                if data:
                    last_time = data[-1].get('ts', '')
                    if "00:00" in str(last_time):
                        self.context.log("INFO", f"[Live] Midnight K-Bar received: {last_time}, count={len(data)}")
                
                self.widget.chart_widget.update_data(data)
                
                # 原有的不足資料自動回填邏輯...
                if self.current_code and self.current_code not in self._checked_codes:
                    min_bars = self.context.get_config().get('min_display_bars', 1600)
                    if len(data) < min_bars:
                        self._trigger_auto_download(self.current_code)
                    self._checked_codes.add(self.current_code)

        # 處理 Server 端發送的策略狀態廣播
        elif topic == "STRATEGY":
            str_data = payload.get('data', [])
            if str_data and self.widget:
                # 讓表格即時反應最新的 status 與按鈕文字
                self.widget.strategy_table.update_data(str_data)

    def _trigger_auto_download(self, code):
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        try:
            svc = self.context.get_service_by_capability(CAP_HISTORICAL_DATA)
            if svc:
                msg = svc.download_history(code, start_date, end_date)
                self.context.log("INFO", f"[AutoDownload] Request sent: {msg}")
                
                mw = self.context.get_main_window()
                if mw and hasattr(mw, 'status_bar'):
                    mw.status_bar.showMessage(f"[Auto-Fill] Insufficient data. Downloading history for {code}...", 5000)
            else:
                self.context.log("WARN", "No service provides CAP_HISTORICAL_DATA.")
                
        except Exception as e:
            self.context.log("ERROR", f"Auto download failed: {e}")

    def on_download_history(self):
        try:
            md_svc = self.context.get_service_by_capability(CAP_MARKET_DATA)
            hist_svc = self.context.get_service_by_capability(CAP_HISTORICAL_DATA)
            
            if not md_svc or not hist_svc:
                self.context.show_message("Error", "Missing required services (Market/Historical).", "error")
                return

            contracts = md_svc.get_contracts()
            if not contracts:
                self.context.show_message("Warning", "No contract data available", "warning")
                return
                
            dlg = HistoryDownloadDialog(contracts, parent=self.widget)
            if dlg.exec():
                inp = dlg.get_input()
                msg = hist_svc.download_history(inp['code'], inp['start'], inp['end'])
                self.context.show_message("Download Started", msg, "info")
                
        except Exception as e:
            self.context.show_message("Error", f"Failed: {e}", "error")

    def on_config_options(self):
        current_config = self.context.get_config()
        dlg = LiveTradingOptionsDialog(current_config, parent=self.widget)
        if dlg.exec():
            dlg.apply_changes()
            self.context.log("INFO", "Live Trading options updated.")
            self.on_activate() 

    def on_config_indicators(self):
        current_config = self.context.get_config()
        dlg = IndicatorManagerDialog(current_config, self.app_data_dir, mode='LIVE', parent=self.widget)
        if dlg.exec():
            dlg.apply_changes()
            self.context.log("INFO", "Indicators updated.")
            self.on_activate()

    def on_manage_contracts(self):
        try:
            md_svc = self.context.get_service_by_capability(CAP_MARKET_DATA)
            if not md_svc: return
            
            all_contracts = md_svc.get_contracts()
            config = self.context.get_config()
            visible = config.get('visible_contracts', [])
            
            dlg = ContractManagerDialog(all_contracts, visible, parent=self.widget)
            if dlg.exec():
                new_visible = dlg.get_visible_contracts()
                config['visible_contracts'] = new_visible
                save_config(config, CONFIG_FILE)
                self.context.log("INFO", "Visible contracts updated.")
                self.refresh_data()
        except Exception as e:
            self.context.log("ERROR", f"Manage contracts failed: {e}")

    def _execute_plugin_from_appdata(self, filename, local_vars, target_plot, drawing_list, data_collection=None, is_overlay=True):
        subdir = 'overlays' if is_overlay else 'indicators'
        path = os.path.join(self.app_data_dir, subdir, filename)
        
        if not os.path.exists(path):
            return
            
        try:
            with open(path, 'r', encoding='utf-8') as f:
                code_content = f.read()
            
            local_vars['ADDPLOT_CONFIG'] = []
            exec(code_content, local_vars)
            
            configs = local_vars.get('ADDPLOT_CONFIG', [])
            self.widget.chart_widget._render_plots(configs, target_plot, drawing_list, data_collection, filename)
            
        except Exception as e:
            print(f"[Plugin Error] {filename}: {e}")

    def refresh_data(self):
        """
        Refresh UI data. Safe to fail (catches Exceptions) to keep UI responsive.
        """
        # [FIX] Priority 1: Set UI State IMMEDIATELY
        # Ensure the chart widget knows the current code BEFORE any async callbacks (Tick/KBar) arrive.
        if self.current_code:
            self.widget.chart_widget.set_code(self.current_code)

        try:
            acc_svc = self.context.get_service_by_capability(CAP_ACCOUNT_INFO)
            if acc_svc:
                acc_data = acc_svc.get_accounts()
                self.widget.account_widget.update_info(acc_data)
            
            md_svc = self.context.get_service_by_capability(CAP_MARKET_DATA)
            if md_svc:
                con_data = md_svc.get_contracts()
                
                config = self.context.get_config()
                visible = config.get('visible_contracts', [])
                if visible:
                    filtered_con = [c for c in con_data if c['code'] in visible]
                    self.widget.contract_list.update_data(filtered_con)
                else:
                    self.widget.contract_list.update_data(con_data)
                
                # [MOD] Sync Selection and Subscribe
                if self.current_code:
                    # Subscribe initiates data flow from server
                    md_svc.subscribe(self.current_code)
                    
                    # Highlight item in ListWidget
                    list_widget = self.widget.contract_list
                    for i in range(list_widget.count()):
                        item = list_widget.item(i)
                        # Check text startswith code (Item text format: "CODE (Name)")
                        if item.text().startswith(self.current_code):
                            list_widget.setCurrentItem(item)
                            break
                    
        except (ServiceError, ServiceTimeoutError, Exception) as e:
            self.context.log("WARN", f"[Live] Refresh data skipped (Service unavailable): {e}")

        self.refresh_strategies()

    def refresh_strategies(self):
        try:
            strat_svc = self.context.get_service_by_capability(CAP_STRATEGY_HOST)
            if strat_svc:
                str_data = strat_svc.get_strategy_status()
                self.widget.strategy_table.update_data(str_data)
        except Exception:
            pass 

    def on_contract_selected(self, code):
        self.current_code = code
        self.context.log("INFO", f"Switching view to {code}...")
        self.widget.tick_table.setRowCount(0)
        self.widget.chart_widget.clear()
        
        # UI Set
        self.widget.chart_widget.set_code(code)
        
        try:
            md_svc = self.context.get_service_by_capability(CAP_MARKET_DATA)
            if md_svc:
                md_svc.subscribe(code)
        except Exception as e:
            self.context.log("ERROR", f"Subscribe failed: {e}")

        config = self.context.get_config()
        if config.get('last_futures_contract') != code:
            config['last_futures_contract'] = code
            save_config(config, CONFIG_FILE)

    def on_toggle_strategy(self, sid):
        """
        處理策略 Start/Stop 切換按鈕點擊事件
        """
        try:
            strat_svc = self.context.get_service_by_capability(CAP_STRATEGY_HOST)
            if strat_svc:
                # 發送指令至 Server
                msg = strat_svc.toggle_strategy(sid)
                self.context.log("INFO", f"Strategy {sid}: {msg}")
                
                # [修正 4. & 5.]: 指令執行後，立即重新整理列表，使 Action 按鈕與 Status 欄位更新
                self.refresh_strategies()
                
        except Exception as e:
            self.context.log("ERROR", f"Toggle failed: {e}")

    def on_undeploy_strategy(self, sid):
        """
        [新增]: 處理將策略從執行佇列移除的請求 [修正 7-2-2]
        """
        try:
            strat_svc = self.context.get_service_by_capability(CAP_STRATEGY_HOST)
            if strat_svc:
                # 呼叫 TradingProxy 的 delete_strategy (對應後端 STR_DEL)
                msg = strat_svc.delete_strategy(sid)
                self.context.log("INFO", f"Strategy {sid} Undeployed: {msg}")
                # 立即重新整理列表
                self.refresh_strategies()
            else:
                self.context.log("ERROR", "Undeploy failed: Strategy host service not found.")
        except Exception as e:
            self.context.log("ERROR", f"Undeploy Exception: {e}")

    def on_table_double_click(self, row, col):
        pass