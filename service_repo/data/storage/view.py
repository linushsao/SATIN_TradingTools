
import pandas as pd
from strategy_core import calc_indicators

ADDPLOT_CONFIG = []

if 'K_BAR_DATA' in locals():
    period = locals().get('SYSTEM_MA_PERIOD', 20)
    df = calc_indicators(K_BAR_DATA, period)
    
    ADDPLOT_CONFIG.append({
        'data': df['ma'],
        'kwargs': {'color': 'yellow', 'width': 1.5, 'label': 'MA'}
    })
