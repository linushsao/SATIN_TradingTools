# ==============================================================================
# client_gui/plugins/pages/03_backtest/plugin.py
#
# Version: V3.4-004 (Data Sync & Schema Fix)
# 更新日期: 2025-12-25
# 1. refresh_ui 現在會完整同步磁碟專案至 self.imported_projects (修復按 <run> 無反應問題)。
# 2. 新增 path 與 script 欄位，確保回測執行時 DependencyPacker 能正確定位。
# 3. 優化 UI 刷新時的運行狀態保留邏輯。
# ==============================================================================

import os
import json
import time
from datetime import datetime
from PyQt6.QtWidgets import QMessageBox

from kernel.interface import ISateGuiPlugin
from kernel.services import ServiceError
from kernel.dep_packer import DependencyPacker
# Use generic manager
from ui_lib.layouts import IndicatorManagerDialog
from .layout import BacktestWidget

from shared.config_manager import load_config
from shared.constants import (
    PACKET_KEY_SOURCE_ID, 
    PACKET_KEY_STRAT_CODE, 
    PACKET_KEY_CORE_CODE
)
from shared.capabilities import CAP_BACKTEST_ENGINE, CAP_MARKET_DATA

#---
from PyQt6.QtCore import QThread, pyqtSignal
import importlib.util
import pandas as pd
import numpy as np
from shared.backtest.metrics import QuantMetrics
from shared.backtest.storage import ResultStorage
from shared.database_manager import DatabaseManager

class LocalBacktestThread(QThread):
    """本地回測執行緒"""
    sig_progress = pyqtSignal(str, float) # project_id, progress
    sig_finished = pyqtSignal(str, dict, str) # project_id, result_packet, file_path
    sig_error = pyqtSignal(str, str) # project_id, error_msg
    # 當發現資料庫缺件時，發送 (project_id, code, start, end)
    sig_missing_data = pyqtSignal(str, str, str, str)
    
    def __init__(self, project_id, proj_info, context):
        """[修正]: 增加傳入 context 以供 HistoryDownloader 調用服務"""
        super().__init__()
        self.project_id = project_id
        self.proj_info = proj_info
        self.context = context # 保存 context
        self.db_config = context.get_config()

    def _wait_for_service(self, capability, timeout=10):
        """使用 get_all_services_by_capability 判定服務活性"""
        import time
        start_time = time.time()
        while time.time() - start_time < timeout:
            # 調用正確的 Context API 檢查能力清單
            services = self.context.get_all_services_by_capability(capability)
            if services and len(services) > 0:
                return True
            time.sleep(1)
        return False

    def run(self):
        """強制指定重置索引後的欄位名稱為 'datetime_index'，確保前後端 Key 值對齊"""
        try:
            from shared.capabilities import CAP_HISTORICAL_DATA
            from shared.get_historydata.downloader import HistoryDownloader
            from shared.logging_tool import info as log_info, error as log_error
            from datetime import datetime
            import sys
            import os
            
            # --- 1. 參數提取與防錯處理 ---
            params = self.proj_info.get('params', {})
            c_code = params.get('code') or "TXFR1"
            c_start = params.get('start') or datetime.now().strftime('%Y-01-01')
            c_end = params.get('end') or datetime.now().strftime('%Y-%m-%d')
            raw_freq = params.get('freq')
            c_freq = int(raw_freq) if raw_freq is not None else 15

            # --- 2. 獲取資料 ---
            self.sig_progress.emit(self.project_id, 10.0)
            df = HistoryDownloader.fetch_and_resample(
                context=self.context, 
                code=c_code, 
                start=c_start, 
                end=c_end, 
                target_freq=c_freq,
                progress_callback=lambda p: self.sig_progress.emit(self.project_id, 10 + p * 0.4)
            )

            if df is None or df.empty:
                self.sig_missing_data.emit(self.project_id, c_code, c_start, c_end)
                return

            self.sig_progress.emit(self.project_id, 60.0)

            # --- 3. 執行策略 ---
            from shared.backtest.engine import UniversalBacktestEngine
            import importlib.util
            
            proj_path = self.proj_info.get('path')
            strat_script = self.proj_info.get('script', 'strategy.py')
            strat_path = os.path.join(proj_path, strat_script)
            
            if proj_path not in sys.path:
                sys.path.insert(0, proj_path)

            spec = importlib.util.spec_from_file_location("local_strat", strat_path)
            strat_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(strat_mod)
            
            # --- 4. 啟動引擎運算 ---
            engine = UniversalBacktestEngine()
            result_bundle = engine.run_task(df, strat_mod, params)
            
            # --- 5. 結果持久化 確保 index 轉換為名為 'datetime_index' 的 list ---
            from shared.backtest.storage import ResultStorage
            packet, file_path = ResultStorage.save_run(
                strategy_name=self.proj_info.get('name', self.project_id),
                metadata=params,
                performance=result_bundle,
                log_returns=[] 
            )
            # 強制將 TimeIndex 重置並命名
            df_reset = df.reset_index()
            df_reset.rename(columns={df_reset.columns[0]: 'datetime_index'}, inplace=True)
            packet['full_data'] = df_reset.to_dict(orient='list')

            self.sig_progress.emit(self.project_id, 100.0)
            self.sig_finished.emit(self.project_id, packet, file_path)

        except Exception as e:
            log_error(f"[LocalThread] Critical Failure: {str(e)}")
            self.sig_error.emit(self.project_id, f"策略載入或執行失敗: {str(e)}")

class BacktestPlugin(ISateGuiPlugin):
    def __init__(self):
        self.widget = None
        self.context = None
        self.app_data_dir = ""
        
        # In-Memory Storage for Imported Projects
        self.imported_projects = {} 

    @property
    def plugin_id(self) -> str:
        return "sate.core.backtest"

    @property
    def display_name(self) -> str:
        return "Backtest"

    def initialize(self, context):
        """[全量覆蓋]: 增加 sig_save_settings 信號連接"""
        self.context = context
        self.widget = BacktestWidget()
        self.app_data_dir = self.context.get_app_data_dir("03_backtest")
        
        self.widget.set_context(self.context)
        self.widget.exec_plugin_callback = self._execute_plugin_from_appdata
        
        self.widget.sig_refresh.connect(self.refresh_ui)
        self.widget.sig_config_indicators.connect(self.on_config_indicators)
        self.widget.sig_import_selected.connect(self.on_import_selected)
        
        self.widget.sig_run_task.connect(self.on_run_task)
        self.widget.sig_save_settings.connect(self.on_save_params) # [新增連線]
        self.widget.sig_stop_task.connect(self.on_stop_task)
        self.widget.sig_remove_import.connect(self.on_remove_import)
        self.widget.sig_download_result.connect(self.on_download_result)
        self.widget.sig_show_result.connect(self.on_manual_plot_request)
        
        self.refresh_ui()
        
    def get_widget(self):
        return self.widget
    
    def on_activate(self):
        self.refresh_ui()

    # --- Interface for External Calls (from Strategies) ---
    def import_strategy(self, project_info: dict):
        pid = project_info.get('id')
        if not pid: return
        
        # Initialize
        project_info['status'] = "Ready"
        project_info['active_task_id'] = None
        # Default Params
        project_info['params'] = {
            'code': project_info.get('contract', 'TXFR1'),
            'freq': project_info.get('freq', 15),
            'start': datetime.now().strftime('%Y-01-01'),
            'end': datetime.now().strftime('%Y-%m-%d'),
            'initial_cash': 1000000
        }
        
        self.imported_projects[pid] = project_info
        self.context.log("INFO", f"[Backtest] Imported project: {pid}")
        
        self.refresh_ui()
        self.widget.table_imports.selectRow(self.widget.table_imports.rowCount() - 1)
        self.on_import_selected(pid)

    def _on_restore_settings(self):
        """重新帶入當前專案的原始設定 (從 metadata.json)"""
        if self.widget.current_edit_id:
            self.on_import_selected(self.widget.current_edit_id)
            self.context.log("INFO", f"Restored settings for project: {self.widget.current_edit_id}")
        else:
            self.refresh_ui()

    # --- UI Logic ---
    
    def on_import_selected(self, project_id):
        # info = self.imported_projects.get(project_id)
        # if not info: return
        """[MOD] 讀取本地目錄下的 metadata.json 並填入 UI"""
        ws_path = self.context.get_workspace_path()
        meta_path = os.path.join(ws_path, project_id, "metadata.json")
        
        if not os.path.exists(meta_path):
            return

        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                info = json.load(f)
        except Exception as e:
            self.context.log("ERROR", f"Failed to load metadata: {e}")
            return
        
        self.widget.current_edit_id = project_id
        self.widget.lbl_edit_id.setText(f"Selected: {info.get('name')} ({project_id})")
        
        # Fill Form
        self.widget.combo_strategy.clear()
        # self.widget.combo_strategy.addItem(info.get('name', project_id))
        # self.widget.combo_strategy.setCurrentIndex(0)
        
        # # Load stored params if any
        # if 'params' in info:
            # self.widget.set_params(info['params'])
        self.widget.combo_strategy.addItem(info.get('name', project_id)) # 僅供顯示
        
        # [MOD] Mapping fields from metadata.json
        params = {
            'code': info.get('contract_code', 'TXFR1'),
            'freq': info.get('frequency', 15),
            'start': info.get('last_start_date', datetime.now().strftime('%Y-01-01')),
            'end': info.get('last_end_date', datetime.now().strftime('%Y-%m-%d')),
        }
        self.widget.set_params(params)

    def on_save_params(self):
        """[全量覆蓋]: 實作持久化儲存至 metadata.json"""
        pid = self.widget.current_edit_id
        if not pid or pid not in self.imported_projects:
            self.context.show_message("Error", "No project selected.", "warning")
            return
            
        new_params = self.widget.get_params()
        self.imported_projects[pid]['params'] = new_params
        
        try:
            ws_path = self.context.get_workspace_path()
            meta_path = os.path.join(ws_path, pid, "metadata.json")
            
            if os.path.exists(meta_path):
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta_data = json.load(f)
                
                # 同步 UI 數值至 metadata 欄位
                meta_data['contract_code'] = new_params.get('code')
                meta_data['frequency'] = int(new_params.get('freq', 15))
                meta_data['last_start_date'] = new_params.get('start')
                meta_data['last_end_date'] = new_params.get('end')
                
                with open(meta_path, 'w', encoding='utf-8') as f:
                    json.dump(meta_data, f, indent=4, ensure_ascii=False)
                
                self.context.log("INFO", f"[Backtest] Settings persisted to {meta_path}")
                self.context.show_message("Save Success", f"Settings for {pid} updated.")
        except Exception as e:
            self.context.log("ERROR", f"Failed to persist settings: {e}")

    def on_run_task(self, project_id):
        """[全量覆蓋]: 啟動前自動同步目前 UI 參數"""
        if not project_id or project_id not in self.imported_projects: return
        
        if not self.context.get_all_services_info():
            self.context.show_message("Warning", "Service disconnected.", "warning")
            return

        # 自動同步：確保不用按 Save 也能抓到畫面上最新的參數
        if self.widget.current_edit_id == project_id:
            self.context.log("INFO", f"[Backtest] Auto-syncing UI params for {project_id}")
            self.imported_projects[project_id]['params'] = self.widget.get_params()

        proj_info = self.imported_projects[project_id]
        worker = LocalBacktestThread(project_id, proj_info, self.context)
        
        if not hasattr(self, '_active_workers'): self._active_workers = {}
        self._active_workers[project_id] = worker
        
        worker.sig_progress.connect(self._on_local_progress)
        worker.sig_finished.connect(self._on_local_finished)
        worker.sig_error.connect(self._on_local_error)
        worker.sig_missing_data.connect(self._on_local_missing_data)
        
        proj_info['status'] = "WARMING UP..."
        self.refresh_ui()
        worker.start()

    def _on_local_missing_data(self, pid, code, start, end):
        """[新增]: 向微核心請求下載並更新 UI 狀態"""
        from shared.capabilities import CAP_HISTORICAL_DATA
        
        try:
            # 1. 尋找具備下載能力的服務
            svc = self.context.get_service_by_capability(CAP_HISTORICAL_DATA)
            if svc:
                # 2. 發起下載請求
                msg = svc.download_history(code, start, end)
                self.context.log("INFO", f"[Backtest] Auto-download triggered: {msg}")
                
                # 3. 更新 UI 顯示為同步中
                if pid in self.imported_projects:
                    self.imported_projects[pid]['status'] = "SYNCING_DATA"
                    self.refresh_ui()
                
                # 4. 在狀態列給予提示
                mw = self.context.get_main_window()
                if mw and hasattr(mw, 'status_bar'):
                    mw.status_bar.showMessage(f"[Auto-Fill] Requesting data for {code} ({start} to {end})...", 5000)
            else:
                self.context.log("ERROR", "[Backtest] Cannot auto-download: No Historical Data service found.")
                QMessageBox.warning(self.widget, "下載失敗", "系統中找不到支援歷史資料下載的服務。")
        except Exception as e:
            self.context.log("ERROR", f"[Backtest] Failed to request download: {e}")

    def _on_local_progress(self, pid, val):
        if pid in self.imported_projects:
            self.imported_projects[pid]['status'] = f"RUNNING ({val:.1f}%)"
            self.refresh_ui()

    def _on_local_finished(self, pid, packet, file_path):
        if pid in self.imported_projects:
            proj = self.imported_projects[pid]
            proj['status'] = "FINISHED"
            proj['last_result_path'] = file_path # 暫存結果路徑供 Plot 使用
            self.refresh_ui()
            self.context.log("INFO", f"[Backtest] {pid} finished. Saved to {file_path}")
            
            # 自動顯示結果 (直接帶入運算產出的 packet)
            self.widget.show_result(packet)

    def _on_local_error(self, pid, msg):
        if pid in self.imported_projects:
            self.imported_projects[pid]['status'] = "ERROR"
            self.refresh_ui()
            QMessageBox.critical(self.widget, "回測錯誤", f"專案 {pid} 執行失敗: {msg}")
    #---
    
    def on_stop_task(self, project_id):
        proj_info = self.imported_projects.get(project_id)
        if not proj_info: return
        task_id = proj_info.get('active_task_id')
        if not task_id: return
        
        try:
            bt_svc = self.context.get_service_by_capability(CAP_BACKTEST_ENGINE)
            if bt_svc:
                msg = bt_svc.stop_task(task_id)
                self.context.log("INFO", f"Stop sent: {msg}")
        except Exception as e:
            self.context.log("WARN", f"Stop failed: {e}")

    def on_download_result(self, project_id):
        """使用靜態方法觸發數據下載/預取"""
        proj_info = self.imported_projects.get(project_id)
        if not proj_info: return
        params = proj_info.get('params', {})
        
        from shared.get_historydata.downloader import HistoryDownloader
        # 直接調用靜態方法 (這會引導 Server 進行同步)
        # 注意: 這裡在主執行緒執行會稍微阻塞，建議生產環境改用 Thread
        HistoryDownloader.fetch_and_resample(
            self.context, params.get('code'), params.get('start'), params.get('end'), 1
        )
        self.context.show_message("下載成功", f"合約 {params.get('code')} 的歷史數據已完成預取。")

    def on_remove_import(self, project_id):
        """增加對 ResultStorage 本地目錄的清理"""
        if project_id not in self.imported_projects: return
        
        proj_name = self.imported_projects[project_id].get('name', project_id)
        reply = QMessageBox.question(
            self.widget, "移除專案", 
            f"確定移除 '{project_id}'？\n點擊 'Yes' 將一併清除 AppData 下的所有回測報告檔案。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
        )
        
        if reply == QMessageBox.StandardButton.Cancel: return

        if reply == QMessageBox.StandardButton.Yes:
            from shared.backtest.storage import ResultStorage
            import shutil
            path = ResultStorage.get_base_dir(proj_name)
            if os.path.exists(path):
                shutil.rmtree(path)
                self.context.log("INFO", f"[Backtest] Purged local storage for {proj_name}")

        del self.imported_projects[project_id]
        self.refresh_ui()

    def refresh_ui(self):
        # project_list = list(self.imported_projects.values())
        # self.widget.update_imports_table(project_list)
        """[MOD] 掃描使用者本地專案目錄"""
        """[MOD] 掃描使用者本地專案目錄並同步至記憶體"""        
        ws = self.context.get_workspace_path()
        local_list = []
        
        if os.path.exists(ws):
            # 遍歷工作區目錄
            for d in sorted(os.listdir(ws)):
                m_path = os.path.join(ws, d, "metadata.json")
                if os.path.exists(m_path):
                    try:
                        with open(m_path, 'r', encoding='utf-8') as f:
                            meta = json.load(f)
                            # local_list.append({
                                # 'id': d,
                                # 'name': meta.get('name', d),
                                # 'status': self.imported_projects.get(d, {}).get('status', 'Ready')
                            # })
                    # except: pass
                            
                            # [FIX] 獲取絕對路徑 (Data Schema 補完)
                            proj_path = os.path.abspath(os.path.join(ws, d))
                            
                            # [FIX] 完整填入 imported_projects 字典，確保 on_run_task 有資料可用
                            # 若專案已在記憶體中，保留其 runtime 資訊 (如 active_task_id, status)
                            existing_info = self.imported_projects.get(d, {})
                            
                            proj_info = {
                                'id': d,
                                'name': meta.get('name', d),
                                'path': proj_path,                # 供 DependencyPacker 使用
                                'script': meta.get('strategy_file', 'strategy.py'), # 腳本檔名
                                'status': existing_info.get('status', 'Ready'),
                                'active_task_id': existing_info.get('active_task_id'),
                                'params': existing_info.get('params', {})
                            }
                            
                            # 更新記憶體核心字典
                            self.imported_projects[d] = proj_info
                            local_list.append(proj_info)
                    except Exception as e:
                        print(f"[Backtest] Skip invalid project {d}: {e}")
         
        # 更新 UI 表格顯示        
        self.widget.update_imports_table(local_list)

        try:
            md_svc = self.context.get_service_by_capability(CAP_MARKET_DATA)
            if md_svc:
                con_data = md_svc.get_contracts()
                self.widget.update_options([], con_data)
        except ServiceError: pass

    def on_zmq_event(self, topic: str, message: dict):
        """
        處理系統通知主題，並將百分比進度導向 UI 更新函式。
        """
        # 根據 shared/constants.py 定義的 TOPIC_SYS_NOTIFICATION
        if topic == "SYS_NOTIFICATION":
            # 判斷是否為回測相關的進度更新
            if "strat_code" in message and "progress" in message:
                self._update_status_display(message)

    def _update_status_display(self, payload: dict):
        """
        改用 task_id 進行 Table Row 的比對。
        """
        from PyQt6.QtWidgets import QTableWidgetItem
        from PyQt6.QtGui import QColor

        # 後端現在傳送 task_id (例如: bt_1767053498_21)
        target_id = payload.get("task_id")
        status = payload.get("status")
        progress = payload.get("progress", 0)

        table = self.layout.table_projects
        for row in range(table.rowCount()):
            # 假設第一欄存放的是 Task ID (與後端對應)
            id_item = table.item(row, 0) 
            if id_item and id_item.text() == target_id:
                
                if status == "RUNNING":
                    display_text = f"Running ({progress}%)"
                    color = QColor("#00AAFF")
                elif status == "COMPLETED":
                    display_text = "Completed"
                    color = QColor("#00FF00")
                else:
                    display_text = status
                    color = QColor("#FF5555")

                status_item = QTableWidgetItem(display_text)
                status_item.setForeground(color)
                table.setItem(row, 2, status_item)
                break

    def _fetch_and_show_result(self, task_id):
        """
        增加對代理層回傳值的有效性檢查，避免後端異常導致 NoneType 錯誤。
        """
        try:
            bt_svc = self.context.get_service_by_capability(CAP_BACKTEST_ENGINE)
            if bt_svc:
                # 調用代理層獲取資料
                data = bt_svc.get_result(task_id)
                
                # [新增]: 檢查回傳資料是否為有效字典，避免 NoneType.get() 錯誤
                if not data or not isinstance(data, dict):
                    self.context.log("WARN", f"Server returned empty or invalid data for task {task_id}")
                    return

                # 提取參數並更新 UI
                self.widget.bt_context['BT_PARAMS'] = data.get('params', {})
                self.widget.show_result(data)
                self.context.log("INFO", f"Result loaded for task {task_id}")
        except Exception as e: 
            self.context.log("WARN", f"Auto-fetch result failed: {e}")
    def on_config_indicators(self):
        current_config = self.context.get_config()
        dlg = IndicatorManagerDialog(current_config, self.app_data_dir, mode='BACKTEST', parent=self.widget)
        if dlg.exec():
            dlg.apply_changes()
            if self.widget.last_result_data: self.widget.refresh_chart()

    def _execute_plugin_from_appdata(self, filename, local_vars, target_plot, drawing_list, data_collection=None, is_overlay=True):
        subdir = 'overlays' if is_overlay else 'indicators'
        path = os.path.join(self.app_data_dir, subdir, filename)
        if not os.path.exists(path): return
        try:
            with open(path, 'r', encoding='utf-8') as f: code_content = f.read()
            local_vars['ADDPLOT_CONFIG'] = []
            exec(code_content, local_vars)
            configs = local_vars.get('ADDPLOT_CONFIG', [])
            if hasattr(self.widget, '_render_plots'):
                self.widget._render_plots(configs, target_plot, drawing_list, data_collection, filename)
        except Exception as e: print(f"[Backtest Plugin Error] {filename}: {e}")

    def cleanup(self): pass
    
    def handle_bt_finished(self, data):
        """[修正]: 修正 self.tasks 引用錯誤，應為 self.imported_projects"""
        task_id = data.get('task_id')
        status = data.get('status')
        report_content = data.get('parse_report', "") 
        
        print(f"[BacktestPlugin] Task {task_id} Finished. Status: {status}")
        
        # [修正]: 統一使用 __init__ 中定義的 self.imported_projects 變數
        if task_id in self.imported_projects:
            self.imported_projects[task_id]['status'] = "FINISHED" if status == "ok" else "ERROR"
            self.imported_projects[task_id]['report'] = report_content 
        
        # 刷新 UI 表格顯示
        if self.widget:
            self.widget.update_imports_table(list(self.imported_projects.values()))
        
        if status == "ok" and report_content:
            self.widget.show_parse_report_ui(task_id, report_content)
        elif status == "error":
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self.widget, "回測錯誤", f"任務 {task_id} 執行失敗: {data.get('msg')}")   
             
    def on_view_report_clicked(self, task_id):
        """
        當點選檢視歷史報告時，觸發顯示稽核報告。
        """
        task_info = self.tasks.get(task_id)
        if not task_info:
            return
            
        # 若本地已存有解析報告內容，直接顯示
        if 'report' in task_info and task_info['report']:
            self.widget.show_parse_report_ui(task_id, task_info['report'])
        else:
            # 若無報告，向後端請求完整結果 (會觸發另一組接收邏輯更新 self.tasks)
            print(f"[BacktestPlugin] Requesting results from server for {task_id}...")
            self.proxy.send_command("BT_GET_RESULT", {"task_id": task_id}) 

    def on_manual_plot_request(self, project_id):
        """載入結果時同時執行專案目錄下的 view.py 指標設定"""
        proj_info = self.imported_projects.get(project_id)
        if not proj_info: return
            
        file_path = proj_info.get('last_result_path')
        if not file_path or not os.path.exists(file_path):
            base_dir = ResultStorage.get_base_dir(proj_info.get('name', project_id))
            import glob
            files = sorted(glob.glob(os.path.join(base_dir, "run_*.json")), reverse=True)
            if not files: return
            file_path = files[0]

        try:
            data = ResultStorage.load_detail(file_path)
            
            # --- [新增]: 執行專案 view.py 並獲取指標配置 ---
            proj_path = proj_info.get('path')
            view_path = os.path.join(proj_path, "view.py")
            data['indicators'] = [] # 初始化指標桶

            if os.path.exists(view_path):
                try:
                    # 建立執行環境，模擬策略視覺化邏輯
                    local_vars = {
                        'data': pd.DataFrame(data.get('full_data', {})), # 傳入完整行情
                        'ADDPLOT_CONFIG': []
                    }
                    with open(view_path, 'r', encoding='utf-8') as f:
                        exec(f.read(), {}, local_vars)
                    
                    # 提取 view.py 中定義的 ADDPLOT_CONFIG
                    # 預期格式: ADDPLOT_CONFIG.append({'name': 'MA', 'data': self.ma, 'color': 'yellow'})
                    data['indicators'] = local_vars.get('ADDPLOT_CONFIG', [])
                    self.context.log("INFO", f"[Backtest] Executed view.py from {project_id}, found {len(data['indicators'])} indicators.")
                except Exception as ve:
                    self.context.log("ERROR", f"Failed to execute view.py: {ve}")

            self.widget.show_result(data)
        except Exception as e:
            self.context.log("ERROR", f"載入結果失敗: {e}")