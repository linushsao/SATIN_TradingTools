
from strategy_core import calc_indicators

def calculate(k_bar_data, parameters):
    # 1. Get Params
    period = parameters.get('frequency', 20)
    
    # 2. Calc Core
    df = calc_indicators(k_bar_data, period)
    if len(df) < 2: return {}
    
    # 3. Logic (Sample)
    # curr = df.iloc[-1]
    # if curr['Close'] > curr['ma']:
    #     return {"action": "Buy", "entry_price": curr['Close']}
        
    return {}
