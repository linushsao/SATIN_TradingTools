# ==============================================================================
# client_gui/plugins/pages/strategies/plugin.py
#
# Version: V3.8-009 (External Editor Integration)
# 更新日期: 2025-12-25
# [修正]: 實作外部編輯器啟動邏輯與路徑設定儲存。
# ==============================================================================

import os
import json
import subprocess
import pandas as pd
import numpy as np
from PyQt6.QtWidgets import QTableWidgetItem
from kernel.interface import ISateGuiPlugin
# from .layout import StrategiesWidget, IndicatorManagerDialog, StrategiesOptionsDialog
from .layout import (
    StrategiesWidget, IndicatorManagerDialog, StrategiesOptionsDialog, EditorOptionsDialog
)
from shared.config_manager import save_config, CONFIG_FILE

class StrategiesPlugin(ISateGuiPlugin):
    def __init__(self):
        self.widget = None
        self.context = None
        self.app_data_dir = ""

    @property
    def plugin_id(self) -> str:
        return "sate.core.strategies"

    @property
    def display_name(self) -> str:
        return "Strategies"

    def initialize(self, context):
        self.context = context
        self.widget = StrategiesWidget()
        self.app_data_dir = self.context.get_app_data_dir("02_strategies")
        
        cfg = self.context.get_config()
        self.widget.display_limit = cfg.get('strategy_chart_limit', 200)
        
        y_width = cfg.get('strategy_chart_y_width', 45)
        self.widget.chart_view.set_y_axis_width(y_width)
        
        padding = cfg.get('strategy_chart_padding', 10)
        self.widget.chart_view.set_auto_scale_padding(padding)
        
        ovs = cfg.get('strategy_k_bar_plugins', [])
        inds = cfg.get('strategy_independent_plots', [])
        self.widget.update_active_indicators(ovs, inds)

        self.widget.sig_preview_data.connect(self._on_preview_data)
        self.widget.sig_local_select.connect(self._on_local_select)
        self.widget.sig_refresh.connect(self.refresh_ui)
        self.widget.sig_open_indicators.connect(self._on_open_indicators)
        self.widget.sig_open_options.connect(self._on_open_options)
        self.widget.sig_file_selected.connect(self._on_f_sel)
        self.widget.sig_save_file.connect(self._on_save_f)
        self.widget.sig_save_project.connect(self._on_save_project)
        self.widget.sig_open_external.connect(self._on_open_external)
        self.widget.sig_editor_options.connect(self._on_editor_options)  
        self.widget.sig_deploy_req.connect(self._on_deploy_to_server)  
        self.widget.sig_stop_strategy_req.connect(self._on_stop_strategy)
        # [新增] 監聽參數頁面的 Active 變化，即時反饋到按鈕
        self.widget.config_form.sig_active_changed.connect(self.widget.set_deploy_status)        
        #---
        self.widget.chart_view.exec_plugin_callback = self._execute_plugin_from_appdata
        self.refresh_ui()

    def _on_stop_strategy(self, pid):
        """
        發送停止指令至伺服器端。
        """
        from shared.capabilities import CAP_STRATEGY_HOST
        
        # 1. 確認連線服務
        svc = self.context.get_service_by_capability(CAP_STRATEGY_HOST)
        if not svc:
            self.context.show_message("操作失敗", "找不到具備策略託管能力的服務。", "error")
            return

        # 2. 執行停止指令 (STR_STOP)
        try:
            self.context.log("INFO", f"[Strategies] Requesting stop for strategy ID: {pid}")
            # 根據 service_trading 協定，停止指令需要 id 參數 
            response = svc.call("STR_STOP", {"id": pid})
            
            if response and response.get('status') == 'ok':
                self.context.show_message("停止成功", f"策略 (ID: {pid}) 已發送停止指令。", "info")
            else:
                msg = response.get('msg', 'Unknown error')
                self.context.show_message("停止失敗", f"伺服器回應: {msg}", "error")
        except Exception as e:
            self.context.log("ERROR", f"Stop Strategy Exception: {e}")
            self.context.show_message("操作異常", str(e), "error")

    def _on_deploy_to_server(self):
        """
        [完整覆蓋版本]: 打包策略檔案、推送至服務端並顯示實時診斷結果。
        """
        import os
        from shared.capabilities import CAP_STRATEGY_HOST
        from PyQt6.QtWidgets import QMessageBox

        # 1. 基本校驗：是否選擇專案
        pid = self.widget.config_form.current_editing_id
        if not pid:
            self.context.show_message("部署失敗", "請先選擇一個專案。", "warn")
            return

        # 2. 取得目標服務 (具備策略執行能力)
        svc = self.context.get_service_by_capability(CAP_STRATEGY_HOST)
        if not svc:
            self.context.show_message("部署失敗", "找不到具備策略託管能力 (CAP_STRATEGY_HOST) 的服務。", "error")
            return

        # 3. 讀取專案檔案內容
        ws = self.context.get_workspace_path()
        base_path = os.path.join(ws, pid)
        strat_path = os.path.join(base_path, "strategy.py")
        core_path = os.path.join(base_path, "strategy_core.py")

        if not os.path.exists(strat_path):
            self.context.show_message("部署失敗", f"找不到進入點檔案: strategy.py", "error")
            return

        try:
            with open(strat_path, 'r', encoding='utf-8') as f:
                strat_content = f.read()
            
            core_content = ""
            if os.path.exists(core_path):
                with open(core_path, 'r', encoding='utf-8') as f:
                    core_content = f.read()

            # 4. 收集表單參數與組合封包
            form_data = self.widget.config_form.get_form_data()
            payload = {
                "cmd": "DEPLOY_STRATEGY",
                "args": {
                    "id": pid,
                    "strategy_name": f"strategy_{pid}.py",
                    "strategy_content": strat_content,
                    "core_content": core_content,
                    **form_data
                }
            }

            # 5. 發送部署指令
            self.context.log("INFO", f"[Strategies] Deploying project {pid} to server...")
            response = svc.call("DEPLOY_STRATEGY", payload['args'])
            
            if response and response.get('status') == 'ok':
                # --- 診斷看板邏輯開始 ---
                diag = response.get('diagnostics', {})
                broker_conn = diag.get('broker_connection', 'Unknown')
                market_data = diag.get('market_data', 'Unknown')
                env_mode = diag.get('mode', 'SIMULATION')
                
                # 判定圖示與警告訊息
                status_icon = "✅"
                warning_msg = ""
                
                # 安全警示：真實環境但沒登入
                if env_mode == 'PRODUCTION' and broker_conn != 'ONLINE':
                    status_icon = "❌"
                    warning_msg = "\n⚠️ 警告：目前為真實交易模式，但券商帳號尚未登入！"
                elif market_data == 'PENDING':
                    status_icon = "⚠️"
                    warning_msg = "\nℹ️ 提示：策略已就緒，但行情數據尚未訂閱成功 (可能非交易時段)。"

                diag_text = (
                    f"{status_icon} 策略部署成功！\n\n"
                    f"--- 服務端診斷報告 ---\n"
                    f"● 運行環境：{env_mode}\n"
                    f"● 程式重載：{diag.get('reload', 'SUCCESS')}\n"
                    f"● 券商連線：{broker_conn}\n"
                    f"● 行情訂閱：{market_data}\n"
                    f"----------------------\n"
                    f"{warning_msg}"
                )

                # 顯示診斷對話框
                msg_box = QMessageBox(self.widget)
                msg_box.setWindowTitle("部署結果診斷")
                msg_box.setText(diag_text)
                msg_box.setIcon(QMessageBox.Icon.Information if status_icon == "✅" else QMessageBox.Icon.Warning)
                msg_box.exec()
                # --- 診斷看板邏輯結束 ---

                self.context.log("INFO", f"[Strategies] Project {pid} deployed with diagnostics: {diag}")
            else:
                msg = response.get('msg', 'Unknown error')
                self.context.show_message("部署失敗", f"伺服器回應: {msg}", "error")

        except Exception as e:
            self.context.log("ERROR", f"Deployment Exception: {e}")
            self.context.show_message("部署異常", str(e), "error")
    def get_widget(self):
        return self.widget

    def on_activate(self):
        self.refresh_ui()

    def refresh_ui(self):
        ws = self.context.get_workspace_path()
        ps = {}
        if os.path.exists(ws):
            for d in os.listdir(ws):
                m_path = os.path.join(ws, d, "metadata.json")
                if os.path.exists(m_path):
                    try:
                        with open(m_path, 'r', encoding='utf-8') as f:
                            ps[d] = json.load(f)
                    except:
                        pass
        
        self.widget.table_local.setRowCount(0)
        for pid, meta in ps.items():
            r = self.widget.table_local.rowCount()
            self.widget.table_local.insertRow(r)
            self.widget.table_local.setItem(r, 0, QTableWidgetItem(pid))
            self.widget.table_local.setItem(r, 1, QTableWidgetItem(meta.get('name', '')))

    def _on_local_select(self, pid):
        # [Step 1: 專案點擊 Log]
        self.context.log("DEBUG", f"[StrategiesPlugin] User clicked project: '{pid}'")
        
        ws = self.context.get_workspace_path()
        base = os.path.join(ws, pid)
        if not os.path.exists(base):
            return
            
        # [Step 2 & 3: 解析規格 (含快取檢查與 Metadata 提取)]
        schema = self._resolve_schema(pid)
        
        ctx = {}
        try:
            from shared.capabilities import CAP_MARKET_DATA, CAP_TRADE_EXEC
            m_svc = self.context.get_service_by_capability(CAP_MARKET_DATA)
            if m_svc:
                ctx['contracts'] = m_svc.get_contracts()
            a_svc = self.context.get_service_by_capability(CAP_TRADE_EXEC)
            if a_svc:
                #ctx['accounts'] = a_svc.get_accounts()
                # [FIX] 統一資料格式：將 account_id 轉換為 layout.py 期待的 code 欄位
                raw_accounts = a_svc.get_accounts()
                ctx['accounts'] = [{'code': a.get('account_id')} for a in raw_accounts if a.get('account_id')]
                self.context.log("DEBUG", f"[Strategies] Formatted {len(ctx['accounts'])} accounts for ctx.")                
            # 獲取專案目錄下的腳本檔案供動態下拉選單使用
            ctx['strategy_files'] = [f for f in sorted(os.listdir(base)) if f.endswith('.py')]
        except:
            pass
            
        self.widget.config_form.build_from_schema(schema, ctx)
        self.widget.config_form.current_editing_id = pid
        
        m_path = os.path.join(base, "metadata.json")
        if os.path.exists(m_path):
            with open(m_path, 'r', encoding='utf-8') as f:
                d = json.load(f)
                d['id'] = pid
                self.widget.config_form.set_form_data(d)
                # [新增] 載入專案時，立即根據 metadata 中的 is_active 決定部署按鈕狀態
                is_active = d.get('is_active', True) # 預設為 True 
                self.widget.set_deploy_status(is_active)                
        cfg = self.context.get_config()
        hidden_files = cfg.get('strategy_hidden_files', ['metadata.json', 'schema_cache.json'])
        
        self.widget.file_list.setRowCount(0)
        files = [f for f in sorted(os.listdir(base)) if f not in hidden_files]
        for f in files:
            r = self.widget.file_list.rowCount()
            self.widget.file_list.insertRow(r)
            self.widget.file_list.setItem(r, 0, QTableWidgetItem(f))

    def _resolve_schema(self, pid):
        from shared.capabilities import CAP_STRATEGY_HOST
        import traceback
        
        # 1. 本地快取路徑
        p = os.path.join(self.context.get_workspace_path(), pid, "schema_cache.json")
        
        # --- 第一階段：本地優先 (Step 2 Log) ---
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    self.context.log("INFO", f"[ProjectManager] Checking cache... Status: FOUND for {pid}")
                    return json.load(f)
            except Exception: pass

        self.context.log("INFO", f"[ProjectManager] Checking cache... Status: MISSING. (Project: {pid})")

        # --- 第二階段：微核心動態獲取 (Step 3 Log) ---
        try:
            self.context.log("INFO", f"[KernelConnector] Requesting metadata from micro-kernel for {pid}")
            all_info = self.context.get_all_services_info()
            self.context.log("DEBUG", f"[KernelConnector] Total services found: {len(all_info)}")
            # 尋找具備策略管理能力的服務 (CAP_STRATEGY_HOST)
            # 優先從 metadata.json 或是註冊資訊中提取 strategy_schema
            target_service = next((s for s in all_info if CAP_STRATEGY_HOST in s.get('caps', [])), None)
            
            if target_service:
                # 根據日誌結構，規格表可能位於元資料欄位中
                #raw_spec = target_service.get("strategy_schema")
                # [DEBUG] 檢查 info 結構的 Key
                self.context.log("DEBUG", f"[KernelConnector] Service Info Keys: {list(target_service.keys())}")
                
                # [FIX] 修正路徑：strategy_schema 位於 meta 字典內
                meta_data = target_service.get("meta", {})
                raw_spec = meta_data.get("strategy_schema")
                
                self.context.log("DEBUG", f"[KernelConnector] Meta Keys: {list(meta_data.keys())}")                
                #
                if raw_spec:
                    # [Step 4: 轉換規格 Log]
                    #self.context.log("DEBUG", f"[SchemaAdapter] Converting metadata to schema cache...")
                    converted_schema = self._convert_spec_to_schema(raw_spec)
                    #--------------
                    # [NEW] 功能新增：抓取帳號並注入到規格中
                    live_accounts = self._fetch_accounts_from_kernel()
                    self.context.log("INFO", f"[live_accounts]:{live_accounts}")
                    if live_accounts:
                        self.context.log("INFO", f"[live_accounts] fill using:{live_accounts}")
                        converted_schema = self._inject_dynamic_accounts(converted_schema, live_accounts)
                        self.context.log("INFO", f"[live_accounts] after inject:{converted_schema}")
                    #--------------
                    # [Step 5: 寫入快取 Log]
                    self._save_to_local_cache(pid, converted_schema)
                    self.context.log("INFO", f"[ProjectManager] Successfully wrote 'schema_cache.json' to {pid}.")
                    return converted_schema
                else:
                    self.context.log("WARNING", f"Service '{target_service.get('id')}' found but strategy_schema is missing.")
            else:
                self.context.log("ERROR", "No service with CAP_STRATEGY_HOST is currently registered.")
                
        except Exception as e:
            self.context.log("ERROR", f"Failed to resolve metadata: {e}")

        # 失敗進入降級模式
        self.context.log("CRITICAL", f"[ProjectManager] Failed to resolve schema. Entering DEGRADED MODE for {pid}.")
        return {"properties": {"name": {"type": "string", "title": "Name"}}, "x-status": "error"}

    def _convert_spec_to_schema(self, raw_spec: dict) -> dict:
        """
        轉換器：完整保留分組、驗證規則與動態來源，確保型別資訊不丟失。
        [修正]: 增加對 options 的提取，映射至 enum 供 UI 產生下拉選單。        
        """
        target_schema = {
            "title": "Strategy Parameters (V2.4.1 Corrected)",
            "type": "object",
            "properties": {},
            "required": []
        }

        try:
            for group in raw_spec.get("groups", []):
                group_title = group.get("title", "General")
                for field in group.get("fields", []):
                    key = field.get("key")
                    if not key : continue
                    
                    raw_type = field.get("type", "string")
                    prop = {
                        "title": field.get("label", key),
                        "type": self._map_type(raw_type),
                        "default": field.get("default"),
                        "x-group": group_title,
                        "x-ui-type": raw_type # 保留原始 UI 型別供 layout.py 判斷
                    }
                    
                    # 數值限制
                    if "min" in field: prop["minimum"] = field["min"]
                    if "max" in field: prop["maximum"] = field["max"]
                    
                    # 動態來源處理
                    if raw_type == "dynamic_select":
                        prop["x-source"] = field.get("source")
                    #-------------
                    # [修正]: 處理靜態下拉選單 options -> enum
                    if "options" in field:
                        prop["enum"] = field["options"]

                    #-------------
                    # 必填項
                    if field.get("required"):
                        target_schema["required"].append(key)
                    
                    target_schema["properties"][key] = prop
            
            if not target_schema["required"]: del target_schema["required"]
        except Exception as e:
            print(f"Conversion failed: {e}")
            
        return target_schema

    def _map_type(self, t: str) -> str:
        m = {
            "string": "string", "integer": "integer", "number": "number",
            "float": "number", "boolean": "boolean", "dynamic_select": "string"
        }
        return m.get(t, "string")

    def _save_to_local_cache(self, pid, schema):
        try:
            target_dir = os.path.join(self.context.get_workspace_path(), pid)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
            path = os.path.join(target_dir, "schema_cache.json")
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(schema, f, indent=4, ensure_ascii=False)
        except Exception: pass
            
    def _on_preview_data(self, data):
        """
        [修正] 依據 PM 指令修正流程：
        1. 先動態讀取左側表單參數 (Contract/Freq)。
        2. 接著依參數 contract_code 下載 1 分 K 原始資料。
        3. 最後執行頻率轉換並傳送至顯示工具。
        """
        from shared.capabilities import CAP_MARKET_DATA
        from shared.data_transform import resample_kbar
        import pandas as pd
        
        # 1. 先動態讀取左側 strategy parameters 的參數
        form_data = self.widget.config_form.get_form_data()
        code = form_data.get('contract_code')
        # 讀取使用者設定的目標頻率 (來自 freq 欄位)
        target_freq = form_data.get('frequency', 1) 
        
        if not code:
            self.context.log("WARNING", "[Strategies] 未設定合約代碼 (contract_code)，無法載入。")
            return

        svc = self.context.get_service_by_capability(CAP_MARKET_DATA)
        if svc:
            # 2. 接著依參數 contract_code 下載原始資料 (5-1. 預設下載 1 分 K)
            self.context.log("INFO", f"[Strategies] 下載 {code} 的 1m 原始歷史資料...")
            hist_list = svc.get_history_data(code, data['start'], data['end'], freq=1)
            
            if hist_list:
                # 轉換為 DataFrame
                df = pd.DataFrame(hist_list)
                
                # 標準化欄位名稱為首字大寫 (以符合 resample_kbar 的要求)
                map_cols = {'open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume','amount':'Amount'}
                df.rename(columns=lambda x: map_cols.get(x.lower(), x), inplace=True)
                
                # 處理時間索引，確保重採樣功能運作
                time_key = 'ts' if 'ts' in df.columns else ('timestamp' if 'timestamp' in df.columns else None)
                if time_key:
                    df[time_key] = pd.to_datetime(df[time_key])
                    df.set_index(time_key, inplace=True)
                
                # 5-2. 依照讀取到的 freq 頻率設定轉換資料
                if target_freq > 1:
                    try:
                        print(f"[DB] enter df resample")
                        df = resample_kbar(df, target_freq)
                        self.context.log("INFO", f"[Strategies] 資料已轉換為 {target_freq} 分 K。")
                        print(f"[DB] left df resample")
                    except Exception as e:
                        self.context.log("ERROR", f"[Strategies] 頻率轉換失敗: {e}")
                print(f"[DB] target_freq:{target_freq}, type:{type(target_freq)}")
                print(f"[DB] df \n {df}")
                
                df = df.reset_index().rename(columns={df.index.name: 'Date'})
                self.widget.load_data(df, code=code, freq=f"{target_freq}m")
            else:
                self.context.log("WARNING", f"[Strategies] 服務未回傳 {code} 的資料。")
                
    def _on_open_indicators(self):
        cfg = self.context.get_config()
        dlg = IndicatorManagerDialog(cfg, self.app_data_dir, parent=self.widget)
        if dlg.exec():
            ovs, inds = dlg.get_selected_indicators()
            cfg['strategy_k_bar_plugins'] = ovs
            cfg['strategy_independent_plots'] = inds
            save_config(cfg, CONFIG_FILE)
            self.widget.update_active_indicators(ovs, inds)
            self.widget.refresh_chart()


    def _on_open_external(self):
        """呼叫外部編輯器開啟當前編輯檔案"""
        cfg = self.context.get_config()
        exe_path = cfg.get('external_editor_path', '')
        if not exe_path or not os.path.exists(exe_path):
            self.context.show_message("設定提示", "請先設定外部編輯器執行檔路徑。", "info")
            self._on_editor_options()
            return
        
        curr_file = self.widget.code_editor.current_file_path
        if not curr_file or not os.path.exists(curr_file):
            self.context.log("WARNING", "No active file to open in external editor.")
            return
            
        try:
            subprocess.Popen([exe_path, curr_file])
            self.context.log("INFO", f"Opened external editor: {exe_path}")
        except Exception as e:
            self.context.show_message("執行錯誤", f"無法啟動編輯器: {e}", "error")

    def _on_editor_options(self):
        """開啟外部編輯器路徑設定頁面"""
        cfg = self.context.get_config()
        dlg = EditorOptionsDialog(cfg.get('external_editor_path', ''), self.widget)
        if dlg.exec():
            cfg['external_editor_path'] = dlg.get_path()
            save_config(cfg, CONFIG_FILE)
            self.context.log("INFO", "External editor path updated.")

    def _on_open_options(self):
        cfg = self.context.get_config()
        cur = {
            'display_limit': self.widget.display_limit,
            'y_axis_width': self.widget.chart_view.y_axis_width,
            'auto_scale_padding': int(self.widget.chart_view.y_axis_padding * 100)
        }
        dlg = StrategiesOptionsDialog(cur, self.widget)
        if dlg.exec():
            new = dlg.get_settings()
            self.widget.display_limit = new['display_limit']
            self.widget.chart_view.set_y_axis_width(new['y_axis_width'])
            self.widget.chart_view.set_auto_scale_padding(new['auto_scale_padding'])
            
            cfg['strategy_chart_limit'] = new['display_limit']
            cfg['strategy_chart_y_width'] = new['y_axis_width']
            cfg['strategy_chart_padding'] = new['auto_scale_padding']
            save_config(cfg, CONFIG_FILE)
            self.widget.refresh_chart()

    def _execute_plugin_from_appdata(self, filename, local_vars, _unused, drawing_list, is_overlay=True):
        """
        [修正]: 解決 No module named 'strategy_core' 錯誤。
        在執行插件前，將對應的 app_data 目錄加入 sys.path。
        """
        import sys
        
        subdir = 'overlays' if is_overlay else 'indicators'
        path = os.path.join(self.app_data_dir, subdir, filename)
        
        if not os.path.exists(path):
            return
            
        # --- 關鍵修正：動態路徑注入 ---
        target_dir = os.path.dirname(path)
        if target_dir not in sys.path:
            # 將目錄加入搜尋路徑的最前面
            sys.path.insert(0, target_dir)
        # ----------------------------

        chart = self.widget.chart_view
        if is_overlay:
            target_plot = chart.p_main
        else:
            target_plot = chart.add_subplot(filename)
            
        try:
            with open(path, 'r', encoding='utf-8') as f:
                code = f.read()
            
            local_vars['ADDPLOT_CONFIG'] = []
            
            # 執行指標腳本：此時 Python 已能正確 import 同目錄下的 strategy_core.py
            exec(code, local_vars, local_vars)
            
            configs = local_vars.get('ADDPLOT_CONFIG', [])
            
            # 確保數據轉換為 Numpy 陣列
            for cfg in configs:
                import pandas as pd
                if isinstance(cfg.get('data'), (pd.Series, pd.DataFrame)):
                    cfg['data'] = cfg['data'].values
            
            # 執行渲染
            if hasattr(chart, '_render_plots'):
                chart._render_plots(configs, target_plot, drawing_list, None, filename)
                
        except Exception as e:
            # 若發生錯誤，將錯誤訊息印出至控制台
            print(f"Plugin Engine Error: {filename}: {e}")
            
    def _on_f_sel(self, f):
        pid = self.widget.config_form.current_editing_id
        if pid:
            p = os.path.join(self.context.get_workspace_path(), pid, f)
            with open(p, 'r', encoding='utf-8') as f_obj:
                content = f_obj.read()
                self.widget.code_editor.load_file(p, content)
            self.widget.tabs_content.setCurrentIndex(1)

    def _on_save_f(self, n, c):
        pid = self.widget.config_form.current_editing_id
        if pid:
            p = os.path.join(self.context.get_workspace_path(), pid, n)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(c)

    def _on_save_project(self, data):
        pid = data.get('id')
        if not pid:
            return
        p = os.path.join(self.context.get_workspace_path(), pid, "metadata.json")
        try:
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            self.context.log("INFO", f"Project {pid} saved with strict type casting.")
        except Exception as e:
            self.context.log("ERROR", f"Save failed: {e}")
    #--------------------
    def _fetch_accounts_from_kernel(self):
        """[修正] 透過能力標籤向微核心請求帳號清單"""
        self.context.log("INFO", "[Strategies] Requesting accounts from Trading Service...")
        try:
            from shared.capabilities import CAP_TRADE_EXEC
            # 正確做法：透過 CAP_TRADE_EXEC 找到交易服務代理 (TradingProxy)
            proxy = self.context.get_service_by_capability(CAP_TRADE_EXEC)
            
            if proxy:
                # 呼叫 TradingProxy 內建的 get_accounts()
                accounts_data = proxy.get_accounts() 
                
                # 提取 ID 並過濾空值，回傳純字串列表
                return [a.get('account_id') for a in accounts_data if a.get('account_id')]
            
            return []
        except Exception as e:
            self.context.log("ERROR", f"[Strategies] Failed to fetch accounts: {str(e)}")
            return []

    def _inject_dynamic_accounts(self, schema, accounts):
        """[修正版] 針對轉換後的 flat properties 結構注入帳號"""
        properties = schema.get("properties", {})
        for key, prop in properties.items():
            # 檢查轉換後的標籤 x-source
            if prop.get("x-source") == "accounts":
                prop["options"] = [{"value": acc, "text": acc} for acc in accounts]
                self.context.log("DEBUG", f"[Strategies] Injected {len(accounts)} options into '{key}'")
        return schema  
    #--------------------
    def cleanup(self):
        pass