
import pandas as pd
import numpy as np

def calc_indicators(df: pd.DataFrame, period: int):
    df = df.copy()
    df['ma'] = df['Close'].rolling(window=period).mean()
    return df
