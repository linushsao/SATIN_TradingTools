import json
import pandas as pd
import os
import tkinter as tk
from tkinter import filedialog, messagebox

def process_backtest_data():
    # 1. 初始化 tkinter 並隱藏主視窗
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    # 2. 選擇 JSON 檔案
    file_path = filedialog.askopenfilename(
        title="請選擇要解包的 JSON 檔案",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
    )
    if not file_path: return

    # 3. 選擇儲存目錄
    save_dir = filedialog.askdirectory(title="請選擇解包檔案的存放目錄")
    if not save_dir: return

    try:
        # 4. 讀取 JSON
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        meta = data.get('metadata', {})
        perf = data.get('performance_summary', {})
        initial_cash = meta.get('initial_cash', 100.0)
        serial_id = data.get('serial', '_000')

        # 5. 取得核心序列 (修正標籤為 signal_series 與 drawdown_curve)
        equity_curve = perf.get('equity_curve', [])
        signal_series = perf.get('signal_series') or data.get('signal_series') or []
        
        # 優先找 JSON 內的 drawdown_curve
        json_drawdown = perf.get('drawdown_curve') or data.get('drawdown_curve')

        # 6. 確保資料長度對齊
        min_len = min(len(equity_curve), len(signal_series)) if signal_series else len(equity_curve)
        equity_curve = equity_curve[:min_len]
        signal_series = signal_series[:min_len] if signal_series else [0] * min_len

        # 7. 建立時間序列 (預設頻率與起點)
        time_index = pd.date_range(
            start=meta.get('start', '2025-10-01'), 
            periods=min_len, 
            freq=f"{meta.get('freq', '15')}T"
        )

        # 8. 建立 DataFrame
        df_ts = pd.DataFrame({
            'DateTime': time_index,
            'Equity_Ratio': equity_curve,
            'Equity_Value': [float(x) * initial_cash for x in equity_curve],
            'Signal': signal_series
        })

        # --- 處理 Drawdown_Curve ---
        if json_drawdown and len(json_drawdown) >= min_len:
            # 如果 JSON 內有數據，直接讀取並轉為 float
            df_ts['Drawdown_Curve'] = [float(x) for x in json_drawdown[:min_len]]
        else:
            # 如果沒有，則根據 Equity 自動計算精確值 (防止變成 0)
            running_max = df_ts['Equity_Ratio'].cummax()
            df_ts['Drawdown_Curve'] = (df_ts['Equity_Ratio'] / running_max) - 1

        # 9. 處理統計結果 (Summary)
        summary_data = {
            'Project_Name': data.get('display_name', 'Unknown'),
            'Execution_Time': data.get('timestamp', 'Unknown'),
            'Serial': serial_id,
            'Symbol': meta.get('code', 'Unknown'),
            'Timeframe': meta.get('freq', '15'),
            'Initial_Cash': initial_cash,
            'Total_Return': float(perf.get('total_return', 0)),
            'Max_Drawdown': float(perf.get('max_drawdown', 0)),
            'Volatility': float(perf.get('volatility', 0))
        }
        df_summary = pd.DataFrame([summary_data])

        # 10. 輸出檔案 (符合 V0.1-000 規範)
        ts_path = os.path.join(save_dir, f'V0.1-000_EquityCurve{serial_id}.csv')
        sum_path = os.path.join(save_dir, f'V0.1-000_Strategy_Summary{serial_id}.csv')

        # 使用 float_format='%.6f' 確保小數點不被切掉
        df_ts.to_csv(ts_path, index=False, encoding='utf-8-sig', float_format='%.6f')
        df_summary.to_csv(sum_path, index=False, encoding='utf-8-sig', float_format='%.6f')

        messagebox.showinfo("成功", f"解包完成！\n標籤已更名為 'Drawdown_Curve' 並保留 6 位小數。\n目錄：{save_dir}")

    except Exception as e:
        messagebox.showerror("錯誤", f"處理失敗：{str(e)}")

if __name__ == "__main__":
    process_backtest_data()