# =============================================================================
# 所屬檔案名稱: shared/backtest/storage.py
# 描述: 負責回測結果在 AppData 的儲存、流水號管理與磁碟讀取。
# =============================================================================
import os
import json
import glob
from datetime import datetime

class ResultStorage:
    """處理回測結果的持久化儲存"""

    @staticmethod
    def get_base_dir(strategy_name):
        """取得 AppData 內的專案子目錄"""
        app_data = os.getenv('LOCALAPPDATA')
        path = os.path.join(app_data, 'SATIN_LITE', 'backtest_results', strategy_name)
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def generate_next_serial(base_dir):
        """掃描目錄，產生下一個三碼流水號 (例如 _003)"""
        files = glob.glob(os.path.join(base_dir, "run_*.json"))
        return f"_{len(files) + 1:03d}"

    @classmethod
    def save_run(cls, strategy_name, metadata, performance, log_returns):
        """
        執行完畢後將完整資料存入磁碟。
        """
        base_dir = cls.get_base_dir(strategy_name)
        serial = cls.generate_next_serial(base_dir)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        file_name = f"run_{timestamp}{serial}.json"
        file_path = os.path.join(base_dir, file_name)
        
        # 建立封裝包
        packet = {
            "display_name": f"{strategy_name}{serial}",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "serial": serial,
            "metadata": metadata,
            "performance_summary": performance,
            "log_return_series": log_returns  # 完整序列存在磁碟中
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(packet, f, indent=4, ensure_ascii=False)
            
        return packet, file_path

    @staticmethod
    def rename_display_name(file_path, new_name):
        """修改 JSON 內的顯示名稱，不更動實體檔名"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data['display_name'] = new_name
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    @staticmethod
    def load_detail(file_path):
        """當需要繪圖時，才從磁碟載入完整序列資料"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)