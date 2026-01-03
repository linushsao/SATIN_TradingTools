# ==============================================================================
# tests/test_file_manager.py
#
# Version: V1.0-000
# 描述:     針對 FileManager 的單元測試。
# ==============================================================================

import os
import json
import pytest
from file_manager import FileManager

def test_init_file_manager(temp_workspace):
    """測試 FileManager 初始化是否正確建立目錄結構"""
    fm = FileManager(temp_workspace)
    
    assert os.path.exists(os.path.join(temp_workspace, 'projects'))
    assert os.path.exists(os.path.join(temp_workspace, 'libs', 'indicators'))
    assert os.path.exists(os.path.join(temp_workspace, 'libs', 'analysis'))

def test_create_project(temp_workspace):
    """測試建立專案功能"""
    fm = FileManager(temp_workspace)
    proj_name = "TestStrategy_01"
    
    # 1. 執行建立
    ok, msg = fm.create_project(proj_name)
    assert ok is True
    assert msg == "Created"
    
    # 2. 驗證檔案是否存在
    proj_dir = os.path.join(temp_workspace, 'projects', proj_name)
    assert os.path.exists(proj_dir)
    assert os.path.exists(os.path.join(proj_dir, 'metadata.json'))
    assert os.path.exists(os.path.join(proj_dir, 'strategy.py'))
    assert os.path.exists(os.path.join(proj_dir, 'strategy_core.py'))
    assert os.path.exists(os.path.join(proj_dir, 'view.py'))

    # 3. 驗證 Metadata 內容
    with open(os.path.join(proj_dir, 'metadata.json'), 'r') as f:
        meta = json.load(f)
        assert meta['id'] == proj_name
        assert meta['name'] == proj_name

def test_create_duplicate_project(temp_workspace):
    """測試建立重複專案應失敗"""
    fm = FileManager(temp_workspace)
    name = "DupTest"
    fm.create_project(name)
    
    ok, msg = fm.create_project(name)
    assert ok is False
    assert "exists" in msg

def test_delete_project(temp_workspace):
    """測試刪除專案功能"""
    fm = FileManager(temp_workspace)
    name = "DeleteMe"
    fm.create_project(name)
    
    # 確保已建立
    assert os.path.exists(os.path.join(temp_workspace, 'projects', name))
    
    # 執行刪除
    ok, msg = fm.delete_project(name)
    assert ok is True
    
    # 驗證資料夾已消失
    assert not os.path.exists(os.path.join(temp_workspace, 'projects', name))

def test_get_project_list(temp_workspace):
    """測試取得專案列表"""
    fm = FileManager(temp_workspace)
    fm.create_project("Alpha")
    fm.create_project("Beta")
    
    projects = fm.get_project_list()
    assert len(projects) == 2
    
    names = [p['name'] for p in projects]
    assert "Alpha" in names
    assert "Beta" in names