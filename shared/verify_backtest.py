# =============================================================================
# 檔案名稱: verify_backtest.py
# 描述: [報告自動化版] 支援 CSV 選擇、三線回測、曲線計算與 ZIP 壓縮存檔。
# =============================================================================
import pandas as pd
import os
import sys
import glob
import argparse
import importlib
import json
import zipfile
from datetime import datetime

def setup_env(str_dir):
    """配置環境與搜尋路徑"""
    script_path = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_path) if os.path.basename(script_path) == 'shared' else script_path
    
    for path in [project_root, os.path.abspath(str_dir)]:
        if path not in sys.path: 
            sys.path.insert(0, path)
    return project_root

def get_next_serial(report_dir):
    """掃描目錄，產生下一個三碼流水號 (例如 001, 002)"""
    existing_zips = glob.glob(os.path.join(report_dir, "*.zip"))
    return f"{len(existing_zips) + 1:03d}"

def create_report_zip(report_dir, files_to_zip):
    """將結果檔案壓縮至 reports 目錄下"""
    if not os.path.exists(report_dir):
        os.makedirs(report_dir)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    serial = get_next_serial(report_dir)
    zip_name = f"{timestamp}_{serial}.zip"
    zip_path = os.path.join(report_dir, zip_name)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in files_to_zip:
            if os.path.exists(file):
                zipf.write(file, os.path.basename(file))
                # 壓縮後刪除原始臨時檔，保持目錄整潔
                os.remove(file)
                
    return zip_path

def run():
    parser = argparse.ArgumentParser(description="SATIN Backtest Verifier with ZIP Reports")
    parser.add_argument("--str-dir", type=str, default=".", help="策略目錄 (預設為當前目錄)")
    parser.add_argument("--kbar-dir", type=str, default=".", help="K棒資料目錄 (預設為當前目錄)")
    args = parser.parse_args()

    root = setup_env(args.str_dir)
    csv_files = [f for f in glob.glob(os.path.join(args.kbar_dir, "*.csv")) if "verification" not in f]

    if not csv_files:
        print(f"❌ 錯誤: 在 {args.kbar_dir} 找不到 CSV 數據檔案。")
        return

    print("\n--- 可用的數據檔案列表 ---")
    for i, f in enumerate(csv_files, 1): 
        print(f"  [{i}] {os.path.basename(f)}")
    
    try:
        idx = int(input(f"\n請選取檔案編號 (1-{len(csv_files)}): ")) - 1
        selected_csv = csv_files[idx]
    except (ValueError, IndexError):
        print("❌ 選取無效。")
        return

    # 動態載入引擎與策略
    from shared.backtest.engine import UniversalBacktestEngine
    import strategy
    importlib.reload(strategy)

    print(f"\n[1/3] 執行回測: {os.path.basename(selected_csv)}...")
    df = pd.read_csv(selected_csv)
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)
    
    # 執行回測邏輯 (20MA)
    params = {"frequency": 20, "stop_loss_pct": 0.02, "take_profit_pct": 0.05}
    engine = UniversalBacktestEngine()
    res = engine.run_task(df, strategy, params)

    # 2. 整合與準備數據
    print(f"\n{'='*40}")
    print(f"  總報酬率 (Total Return):    {res['total_return']:.2%}")
    print(f"  最大回撤 (Max Drawdown):   {res['max_drawdown']:.2%}")
    print(f"{'='*40}")

    # 準備 CSV 詳細日誌
    df_detail = df.copy()
    df_detail['signal'] = res['signal_series']
    df_detail['equity_curve'] = res['equity_curve']
    df_detail['drawdown_curve'] = res['drawdown_curve']
    
    detailed_csv = "verification_detailed_log.csv"
    df_detail.to_csv(detailed_csv)

    # 準備摘要 JSON
    summary_data = {
        "metadata": params,
        "performance": {
            "total_return": res['total_return'],
            "max_drawdown": res['max_drawdown'],
            "volatility": res['volatility']
        },
        "source_file": os.path.basename(selected_csv)
    }
    summary_json = "backtest_summary.json"
    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=4)

    # 3. 壓縮報告
    report_dir = os.path.join(os.getcwd(), "reports")
    zip_path = create_report_zip(report_dir, [detailed_csv, summary_json])
    
    print(f"\n[2/3] 報告壓縮完成！")
    print(f"儲存路徑: {zip_path}")
    print(f"[3/3] 驗證程序結束。")

if __name__ == "__main__":
    run()