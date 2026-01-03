# =============================================================================
# 所屬檔案名稱: shared/backtest/runner.py
# 描述: 多執行緒回測任務管理器
# =============================================================================
from concurrent.futures import ThreadPoolExecutor
from .engine import UniversalBacktestEngine

class BacktestTaskRunner:
    """
    管理多個回測任務同時執行。
    """
    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.engine = UniversalBacktestEngine()

    def run_batch(self, tasks: list):
        """
        一次接收多個回測任務。
        tasks 格式: [{'data': df, 'strategy': obj, 'params': {}, 'n': 5, 'callback': func}, ...]
        """
        futures = []
        for t in tasks:
            f = self.executor.submit(
                self.engine.run_task,
                data=t['data'],
                strategy_instance=t['strategy'],
                params=t['params'],
                n_threshold=t.get('n', 1.0),
                on_progress=t.get('callback')
            )
            futures.append(f)
            
        # 取得所有執行結果
        results = [f.result() for f in futures]
        return results