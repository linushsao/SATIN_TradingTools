# ==============================================================================
# tests/history_downloader_tool.py
#
# 描述: 歷史資料下載工具程式。
#      1. 自動偵測並連線 SATIN 服務組件。
#      2. 提供互動介面輸入下載參數。
#      3. 支援自動重採樣與 CSV 匯出。
# ==============================================================================

import os
import sys
import time
import pandas as pd
from datetime import datetime

# [1] 環境路徑初始化
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
client_gui_path = os.path.join(project_root, "client_gui")
sys.path.append(project_root)
sys.path.append(client_gui_path)

from client_gui.kernel.context import SateClientContext
from client_gui.kernel.workers import ZmqReqClient
from client_gui.kernel.services import TradingProxy
from shared.get_historydata import HistoryDownloader
from shared.capabilities import CAP_HISTORICAL_DATA, CAP_MARKET_DATA
from shared.config_manager import load_config
from shared.constants import CMD_GET_CAPABILITIES

def init_satin_environment():
    """模擬系統啟動流程，建立與後端服務的連線"""
    print(">>> 正在初始化 SATIN 核心連線...")
    
    # 建立 Context
    class MockMW: 
        def __init__(self): self.config = load_config(os.path.join(client_gui_path, "config.json"))
    
    context = SateClientContext(MockMW())
    config = context._main_window.config
    
    # 取得當前活躍的設定設定檔
    profile_id = config.get('active_profile_id', 'local_dev')
    services = config.get('service_profiles', {}).get(profile_id, {}).get('services', [])
    
    connected_any = False
    for svc_conf in services:
        try:
            client = ZmqReqClient(svc_conf)
            reply = client.send_command(CMD_GET_CAPABILITIES)
            
            if reply.get('status') == 'ok':
                caps = reply.get('capabilities', [])
                # 只有具備行情或歷史能力才註冊為 TradingProxy
                if CAP_MARKET_DATA in caps or CAP_HISTORICAL_DATA in caps:
                    proxy = TradingProxy(client)
                    context.register_service(svc_conf['name'], proxy, caps, {})
                    print(f"    [+] 成功連接服務: {svc_conf['name']} (能力: {caps})")
                    connected_any = True
        except Exception:
            continue
            
    return context if connected_any else None

def main():
    print("="*50)
    print(" SATIN 歷史資料下載工具 V1.0")
    print("="*50)

    # 1. 啟動連線
    context = init_satin_environment()
    if not context:
        print("\n[-] 錯誤: 無法連線至任何服務組件。請確保後端 Server 已啟動。")
        return

    # 2. 互動式輸入
    try:
        print("\n[請輸入下載參數]")
        code = input("1. 合約編號 (例如 TXFR1): ").strip().upper()
        if not code: code = "TXFR1"
        
        start_date = input("2. 開始日期 (YYYY-MM-DD): ").strip()
        end_date = input("3. 結束日期 (YYYY-MM-DD, 留空代表今天): ").strip()
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
            
        freq = input("4. K線分鐘頻率 (預設 1): ").strip()
        freq = int(freq) if freq else 1

        print(f"\n[執行中] 正在從服務端獲取 {code} 資料...")
        
        # 3. 呼叫共用下載組件
        df = HistoryDownloader.fetch_and_resample(
            context=context,
            code=code,
            start=start_date,
            end=end_date,
            target_freq=freq,
            progress_callback=lambda p: print(f"    進度: {p:.1f}%", end='\r')
        )

        # 4. 結果處理
        if df is not None and not df.empty:
            print(f"\n\n[成功] 已取得 {len(df)} 筆資料。")
            
            # 自動儲存 CSV
            output_dir = os.path.join(project_root, "downloads")
            if not os.path.exists(output_dir): os.makedirs(output_dir)
            
            filename = f"{code}_{start_date.replace('-','')}_{end_date.replace('-','')}_{freq}m.csv"
            file_path = os.path.join(output_dir, filename)
            
            df.to_csv(file_path)
            print(f">>> 檔案已儲存至: {file_path}")
            print("-" * 30)
            print(df.tail(5))
            print("-" * 30)
        else:
            print("\n\n[-] 下載失敗: 伺服器回傳空資料。")

    except KeyboardInterrupt:
        print("\n[!] 使用者取消操作。")
    except Exception as e:
        print(f"\n[錯誤] 執行失敗: {e}")

if __name__ == "__main__":
    main()