# =============================================================================
# 所屬檔案名稱: shared/backtest/lite_runner.py
# 描述: 精簡型回測成果產生工具。支援以命令列參數指定 CSV 檔案路徑。
# 
# [使用方式]:
#   1. 隨機資料模式: python shared/backtest/lite_runner.py
#   2. 指定檔案模式: python shared/backtest/lite_runner.py --csv ./my_data.csv
#
# [CSV 檔案格式要求]:
#   - 檔案編碼: UTF-8，需含標題列 (Header)。
#   - 第一欄為日期時間 (DateTime)，格式如 'YYYY-MM-DD HH:MM:SS'。
#   - 必備欄位 (不分大小寫): Open, High, Low, Close。
# =============================================================================
import pandas as pd
import numpy as np
import sys
import os
import json
import zipfile
import argparse
import importlib.util
from datetime import datetime

# 環境路徑設定
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
SAMPLE_DIR = os.path.join(ROOT_DIR, "shared", "sample")

# 引用回測核心指標組件
try:
    from metrics import QuantMetrics
except ImportError:
    from .metrics import QuantMetrics

class LiteBacktester:
    """精簡型回測成果產生器 (CLI 支援版)"""
    
    def __init__(self, sample_path=SAMPLE_DIR):
        self.sample_path = sample_path
        self.output_json = os.path.join(self.sample_path, "result_packet.json")
        self.output_zip = os.path.join(self.sample_path, "result_bundle.zip")

    def _show_step1_data_spec(self, data, metadata, source_name):
        """【STEP 1: 顯示傳入基礎資料規格】"""
        print("="*70)
        print("【STEP 1: 顯示傳入基礎資料規格】")
        print(f"▶ 資料來源: {source_name}")
        print(f"▶ 合約編號: {metadata.get('contract_code', 'N/A')}")
        print(f"▶ 總筆數: {len(data)} 筆")
        
        if not data.empty and isinstance(data.index, pd.DatetimeIndex):
            start_t = data.index[0]
            end_t = data.index[-1]
            print(f"▶ 資料範圍: {start_t} 至 {end_t}")
            print(f"▶ 回測總時長: {end_t - start_t}")
        
        print(f"▶ 欄位清單: {list(data.columns)}")
        print("▶ 前 3 筆資料範例:")
        print(data[['Open', 'High', 'Low', 'Close']].head(3))
        print("-" * 70)

    def _show_step2_interface_params(self, data, metadata):
        """【STEP 2: 顯示回測介面接收參數】"""
        print("【STEP 2: 顯示回測介面接收參數】")
        print(f"▶ 策略 ID  : {metadata.get('id', 'Unknown')}")
        print(f"▶ 合約編號 : {metadata.get('contract_code', 'N/A')}")
        print(f"▶ 頻率設定 : {metadata.get('frequency', 'N/A')} min")
        
        if not data.empty and isinstance(data.index, pd.DatetimeIndex):
            print(f"▶ 開始日期時間: {data.index[0]}")
            print(f"▶ 結束日期時間: {data.index[-1]}")
        
        print("-" * 70)

    def run(self, csv_path=None, n_threshold=10.0):
        # 1. 載入 Metadata 與 策略腳本
        if not os.path.exists(os.path.join(self.sample_path, "strategy.py")):
            print(f"[Error] 找不到策略檔案於: {self.sample_path}")
            return

        metadata = self._load_metadata()
        
        # 2. 決定資料來源
        if csv_path:
            if not os.path.exists(csv_path):
                print(f"[Error] 指定的 CSV 路徑不存在: {csv_path}")
                return
            data = self._load_csv_data(csv_path)
            source_name = f"外部檔案 ({os.path.basename(csv_path)})"
        else:
            data = self._generate_mock_data()
            source_name = "隨機產生 (Mock Data)"
        
        # 顯示資訊看板
        self._show_step1_data_spec(data, metadata, source_name)
        self._show_step2_interface_params(data, metadata)

        print("【STEP 3: 執行回測運算與進度】")
        strat_module = self._load_strategy_module()
        
        # 執行策略運算
        df_result = strat_module.calculate(data, metadata)
        
        # 績效計算
        signals = np.sign(df_result['entry_line'])
        log_returns = QuantMetrics.calculate_log_return_series(data['close'], signals)
        summary = QuantMetrics.get_performance_summary(log_returns)

        # 進度回報
        for p in np.arange(0, 101, n_threshold):
            print(f"[Progress] 回測進度: {p:.1f}%")

        # 3. 封裝資料包
        result_packet = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "metadata": metadata,
            "performance": summary,
            "source_info": source_name
        }

        # 4. 產出檔案
        with open(self.output_json, 'w', encoding='utf-8') as f:
            json.dump(result_packet, f, indent=4, ensure_ascii=False)
        
        self._create_zip(result_packet)
        print(f"\n✓ 成功產出 JSON 資料包: {self.output_json}")
        print(f"✓ 成功產出 ZIP 壓縮包: {self.output_zip}")
        print("="*70)

    def _load_csv_data(self, path):
        df = pd.read_csv(path, parse_dates=True, index_col=0)
        if 'Close' in df.columns and 'close' not in df.columns:
            df['close'] = df['Close']
        return df

    def _generate_mock_data(self):
        np.random.seed(42)
        n = 200
        prices = 10000 + np.cumsum(np.random.randn(n) * 10)
        df = pd.DataFrame({
            'Open': prices, 'High': prices+5, 'Low': prices-5, 'Close': prices, 'close': prices
        }, index=pd.date_range(start="2025-01-01", periods=n, freq='15T'))
        return df

    def _load_strategy_module(self):
        strat_path = os.path.join(self.sample_path, "strategy.py")
        if self.sample_path not in sys.path:
            sys.path.append(self.sample_path)
        spec = importlib.util.spec_from_file_location("strategy", strat_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _load_metadata(self):
        with open(os.path.join(self.sample_path, "metadata.json"), 'r', encoding='utf-8') as f:
            return json.load(f)

    def _create_zip(self, result_packet):
        with zipfile.ZipFile(self.output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("result_packet.json", json.dumps(result_packet, indent=4, ensure_ascii=False))
            zf.write(os.path.join(self.sample_path, "metadata.json"), "metadata_origin.json")

if __name__ == "__main__":
    # 使用 argparse 處理命令列參數
    parser = argparse.ArgumentParser(description="SATIN Lite 回測成果產生工具")
    parser.add_argument("--csv", type=str, help="指定回測用的 CSV 資料路徑 (若不填則隨機產生)")
    parser.add_argument("--step", type=float, default=20.0, help="進度回報百分比門檻 (預設 20.0)")
    
    args = parser.parse_args()
    
    tester = LiteBacktester()
    tester.run(csv_path=args.csv, n_threshold=args.step)