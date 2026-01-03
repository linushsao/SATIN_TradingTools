# ==============================================================================
# tests/conftest.py
#
# Version: V1.0-000
# 描述:     Pytest 配置與 Fixtures 定義。
#           1. 設定 sys.path 以便引用專案模組。
#           2. 提供 mock_price_data (模擬 K 棒數據)。
#           3. 提供 temp_workspace (臨時檔案系統)。
# ==============================================================================

import sys
import os
import pytest
import pandas as pd
import numpy as np
import tempfile
import shutil

# 1. 設定專案路徑 (Project Root)
# 假設 tests/ 位於專案根目錄下，因此向上兩層找到根目錄
# (如果 tests/ 在根目錄，則是一層: os.path.dirname(os.path.abspath(__file__)))
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)

# 將相關 Service 與 Shared 加入 Path
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'shared'))
sys.path.append(os.path.join(PROJECT_ROOT, 'service_repo', 'core'))
sys.path.append(os.path.join(PROJECT_ROOT, 'service_trading', 'core'))

@pytest.fixture
def mock_price_data():
    """
    產生 100 筆標準的測試用 K 棒數據 (DataFrame)。
    趨勢為線性上升，方便計算驗證。
    """
    count = 100
    dates = pd.date_range(start='2025-01-01', periods=count, freq='15min')
    
    # 價格從 100 開始，每筆增加 1
    close_price = np.linspace(100, 100 + count - 1, count)
    
    df = pd.DataFrame({
        'Open': close_price,
        'High': close_price + 5,
        'Low': close_price - 5,
        'Close': close_price,
        'Volume': 1000
    }, index=dates)
    
    return df

@pytest.fixture
def temp_workspace():
    """
    建立一個臨時目錄作為 Mock Storage，測試結束後自動刪除。
    用於測試 FileManager 的檔案操作，避免汙染真實環境。
    """
    tmp_dir = tempfile.mkdtemp()
    yield tmp_dir
    # Teardown
    shutil.rmtree(tmp_dir)