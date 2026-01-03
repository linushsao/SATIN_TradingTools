# ==============================================================================
# client_gui/plugins/pages/system_log/plugin.py
#
# Version: V3.1-007 (Strict Workspace)
# 更新日期: 2025-12-12
# 描述:     Project Monitor (原 System Monitor) 外掛邏輯。
#           [修正]: 建立新專案時，強制使用 Kernel 提供的 Workspace Path，忽略 UI 回傳值。
# ==============================================================================

import os
import json
import zipfile
import shutil
import importlib 
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from kernel.interface import ISateGuiPlugin
from kernel.services import ServiceError
from .layout import SystemMonitorWidget

# Helper for DB Access
from shared.profile_manager import ProfileManager
from shared.capabilities import CAP_REPO_STORAGE, CAP_STRATEGY_HOST

# UI Dialogs
from ui_lib.layouts import NewProjectDialog

# [Cross-Plugin Import] Reuse ProjectManager from Strategies
try:
    from plugins.pages.strategies.project_manager import ProjectManager
except ImportError:
    print("[ProjectMonitor] Warning: Could not import ProjectManager from strategies plugin.")
    class ProjectManager:
        def __init__(self, r): 
            self.projects_dir = r 
        def set_root_dir(self, r): 
            self.projects_dir = r
        def get_projects(self): return {}
        def get_project_path(self, pid): return ""
        def create_project(self, name, target, desc): return False, "Mock: Manager not loaded"
        def delete_project(self, pid, delete_files): return False, "Mock: Manager not loaded"

class SystemLogPlugin(ISateGuiPlugin):
    def __init__(self):
        self.widget = None
        self.context = None
        self.refresh_timer = None
        self.profile_mgr = None
        self.project_mgr = None
        self.refresh_counter = 0 
        self._current_user_dir = None
        self.default_strategies_dir = "" 

    @property
    def plugin_id(self) -> str:
        return "sate.core.syslog"

    @property
    def display_name(self) -> str:
        return "Project Monitor"

    def initialize(self, context):
        self.context = context
        self.widget = SystemMonitorWidget()
        self.profile_mgr = ProfileManager()
        
        # [MOD] Use Kernel Workspace API
        self.default_strategies_dir = self.context.get_workspace_path()
        self.project_mgr = ProjectManager(self.default_strategies_dir)
        
        # --- Connect UI Signals ---
        self.widget.dashboard.sig_project_action.connect(self.on_project_action)
        
        self.widget.dashboard.sig_new_project.connect(self._on_new_project)
        self.widget.dashboard.sig_import_project.connect(self._on_import_project)
        self.widget.dashboard.sig_export_project.connect(self._on_export_project)
        self.widget.dashboard.sig_remove_project.connect(self._on_remove_project_btn)
        
        self.widget.dashboard.sig_delete_local.connect(self._on_delete_local)
        
        self.context.log("INFO", "Project Monitor 3.1 (Strict WS) Initialized.")
        
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._on_tick)
        self.refresh_timer.start(1000)
        
        self._check_and_switch_workspace()

    def get_widget(self):
        return self.widget
    
    def on_activate(self):
        self._check_and_switch_workspace()
        self._refresh_services()
        self._refresh_user_info()
        self._refresh_projects()
        self._refresh_stats()

    def _check_and_switch_workspace(self):
        # [MOD] Use Kernel API for path detection
        target_dir = self.context.get_workspace_path()
        current_norm = os.path.normpath(self._current_user_dir) if self._current_user_dir else ""
        target_norm = os.path.normpath(target_dir) if target_dir else ""
        
        if current_norm != target_norm:
            self._current_user_dir = target_dir
            # Ensure path exists
            if not os.path.exists(target_dir):
                try: os.makedirs(target_dir)
                except: pass
            
            self.project_mgr.set_root_dir(target_dir)
            self._refresh_projects()

    def _on_tick(self):
        if not self.widget or not self.widget.isVisible(): return
        self._refresh_services()
        self.refresh_counter += 1
        if self.refresh_counter >= 5:
            self._refresh_user_info()
            self._refresh_projects()
            self._refresh_stats()
            self.refresh_counter = 0

    def _refresh_services(self):
        services_info = self.context.get_all_services_info()
        self.widget.update_services(services_info)

    def _refresh_user_info(self):
        user = self.context.get_current_user()
        uid = user.get('id', 'Guest')
        display_data = {
            'id': uid, 'role': user.get('role', 'Viewer'),
            'nickname': uid, 'avatar_path': ''
        }
        if user.get('has_key'):
            profile = self.profile_mgr.get_profile(uid)
            if profile:
                display_data['nickname'] = profile.get('nickname', uid)
                display_data['avatar_path'] = profile.get('avatar_path', '')
        self.widget.dashboard.update_user_info(display_data)

    def _refresh_projects(self):
        # [FIX] Reload registry to ensure we see file system changes
        if hasattr(self.project_mgr, 'load_registry'):
            self.project_mgr.load_registry()
            
        local_projects = self.project_mgr.get_projects()
        local_list = []
        for pid, info in local_projects.items():
            local_list.append({
                "name": pid, "path": info.get('path', ''),
                "updated_at": info.get('updated_at', '-')
            })
        self.widget.dashboard.update_local_projects(local_list)
        self.last_local_count = len(local_list)

        team_projects = []
        try:
            repo_svc = self.context.get_service_by_capability(CAP_REPO_STORAGE)
            if repo_svc:
                raw_list = repo_svc.get_project_list()
                for p in raw_list:
                    team_projects.append({
                        "name": p.get('name', p.get('id', '?')),
                        "author": p.get('author', 'Remote'),
                        "updated_at": p.get('updated_at', '-')
                    })
        except ServiceError: pass
        self.widget.dashboard.update_team_projects(team_projects)

    def _refresh_stats(self):
        local_count = getattr(self, 'last_local_count', 0)
        active_count = 0
        try:
            strat_svc = self.context.get_service_by_capability(CAP_STRATEGY_HOST)
            if strat_svc:
                status_list = strat_svc.get_strategy_status()
                active_count = sum(1 for s in status_list if s.get('running'))
        except: pass
        self.widget.dashboard.update_stats(local_count, active_count)

    def _on_new_project(self):
        # [MOD] Use Kernel Workspace Path as default
        default_path = self.context.get_workspace_path()
        dlg = NewProjectDialog(default_path, self.widget)
        
        if dlg.exec():
            data = dlg.get_data()
            name = data['name']; desc = data['description']
            
            # [MOD] Enforce Strict Mode: Ignore any path from UI if it was somehow editable
            # Always query kernel again for the authoritative path
            target_dir = self.context.get_workspace_path()
            
            ok, result = self.project_mgr.create_project(name, target_dir, desc)
            if ok:
                self.context.log("INFO", f"Project '{name}' created successfully at {target_dir}.")
                self._refresh_projects()
            else:
                self.context.show_message("Create Failed", result, "error")

    def _on_delete_local(self, project_id):
        reply = QMessageBox.question(self.widget, "Delete Project", 
                                     f"Permanently delete local project '{project_id}'?\n(Files will be removed)",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            ok, msg = self.project_mgr.delete_project(project_id, delete_files=True)
            if ok:
                self.context.log("INFO", f"Project '{project_id}' deleted.")
                self._refresh_projects()
            else:
                self.context.show_message("Delete Failed", msg, "error")

    def _on_import_project(self):
        file_path, _ = QFileDialog.getOpenFileName(self.widget, "Import Project", "", "Zip Files (*.zip)")
        if not file_path: return
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                target_path = os.path.join(self.project_mgr.projects_dir, base_name)
                if os.path.exists(target_path):
                    reply = QMessageBox.question(self.widget, "Overwrite", f"Project '{base_name}' exists. Overwrite?",
                                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    if reply != QMessageBox.StandardButton.Yes: return
                    shutil.rmtree(target_path)
                os.makedirs(target_path)
                zf.extractall(target_path)
                self.context.log("INFO", f"Imported project '{base_name}' from {file_path}")
                self._refresh_projects()
        except Exception as e: self.context.show_message("Import Error", str(e), "error")

    def _on_export_project(self):
        table = self.widget.dashboard.table_local
        row = table.currentRow()
        if row < 0:
            self.context.show_message("Export Info", "Please select a local project to export.", "info")
            return
        pid_item = table.item(row, 0)
        if not pid_item: return
        pid = pid_item.text()
        src_path = self.project_mgr.get_project_path(pid)
        if not src_path or not os.path.exists(src_path): return
        save_path, _ = QFileDialog.getSaveFileName(self.widget, "Export Project", f"{pid}.zip", "Zip Files (*.zip)")
        if save_path:
            try:
                shutil.make_archive(save_path.replace('.zip', ''), 'zip', src_path)
                self.context.log("INFO", f"Exported '{pid}' to {save_path}")
            except Exception as e: self.context.show_message("Export Error", str(e), "error")

    def _on_remove_project_btn(self):
        tab_idx = self.widget.dashboard.tabs_projects.currentIndex()
        if tab_idx == 0: 
            table = self.widget.dashboard.table_local
            row = table.currentRow()
            if row >= 0: self._on_delete_local(table.item(row, 0).text())
            else: self.context.show_message("Info", "Select a local project to remove.", "info")
        elif tab_idx == 1: 
            table = self.widget.dashboard.table_team
            row = table.currentRow()
            if row >= 0:
                pid = table.item(row, 0).text()
                reply = QMessageBox.question(self.widget, "Delete Remote", f"Delete '{pid}' from Cloud Repo? (Requires Permission)", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes: self._delete_remote_project(pid)
            else: self.context.show_message("Info", "Select a remote project to remove.", "info")

    def _delete_remote_project(self, project_id):
        try:
            repo_svc = self.context.get_service_by_capability(CAP_REPO_STORAGE)
            if repo_svc:
                msg = repo_svc.delete_project(project_id)
                self.context.log("INFO", f"Repo Delete: {msg}")
                self._refresh_projects()
        except Exception as e: self.context.show_message("Error", str(e), "error")

    def on_project_action(self, ptype, project_id):
        msg = f"Selected {ptype} project: {project_id}"
        self.context.log("INFO", msg)
        self._update_mock_messages(project_id)

    def _update_mock_messages(self, project_id):
        user = self.context.get_current_user()
        uid = user.get('id', 'Guest')
        avatar_path = ""
        if user.get('has_key'):
            profile = self.profile_mgr.get_profile(uid)
            if profile: avatar_path = profile.get('avatar_path', '')
            
        mock_messages = [
            {'avatar': avatar_path, 'title': 'Owner', 'nickname': uid, 'status': '[V]'},
            {'avatar': avatar_path, 'title': 'Trader', 'nickname': 'Alice', 'status': '[!]'},
            {'avatar': avatar_path, 'title': 'Risk', 'nickname': 'Bob', 'status': '[?]'}
        ]
        # self.widget.dashboard.update_project_messages(mock_messages)

    def on_zmq_event(self, topic: str, payload: dict):
        if topic == "LOG":
            self.widget.add_log(payload)
        elif topic == "SYS_NOTIFICATION":
            log_entry = {
                "dt": "", "level": payload.get("level", "INFO"),
                "source_id": payload.get("source_id", "SYS"), "msg": payload.get("message", "")
            }
            self.widget.add_log(log_entry)

    def cleanup(self):
        if self.refresh_timer: self.refresh_timer.stop()