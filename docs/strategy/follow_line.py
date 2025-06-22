import pandas as pd
import numpy as np

def follow_line(df):
    """
    Follow Line 전략 계산
    :param df: DataFrame (BBUpper, BBLower, atr_100, high, low가 포함되어야 함)
    :return: DataFrame with follow line signals
    """
    # 변수 초기화
    df['bb_signal'] = 0
    df['follow_line'] = np.nan
    df['trend'] = 0
    
    # BB Signal 계산
    df.loc[df['close'] > df['BBUpper'], 'bb_signal'] = 1
    df.loc[df['close'] < df['BBLower'], 'bb_signal'] = -1
    
    # Follow Line 계산
    for i in range(len(df)):
        current_signal = df['bb_signal'].iloc[i]
        
        # 첫 번째 데이터 포인트의 경우
        if i == 0:
            if current_signal == 1:
                current_line = df['low'].iloc[i] - df['atr_100'].iloc[i]
            elif current_signal == -1:
                current_line = df['high'].iloc[i] + df['atr_100'].iloc[i]
            else:
                current_line = df['close'].iloc[i]  # 신호가 없을 때는 종가 사용
        else:
            prev_line = df['follow_line'].iloc[i-1]
            
            if current_signal == 1:  # Buy signal logic
                current_line = df['low'].iloc[i] - df['atr_100'].iloc[i]
                if not np.isnan(prev_line) and current_line < prev_line:
                    current_line = prev_line
            
            elif current_signal == -1:  # Sell signal logic
                current_line = df['high'].iloc[i] + df['atr_100'].iloc[i]
                if not np.isnan(prev_line) and current_line > prev_line:
                    current_line = prev_line
            
            else:  # No signal, keep previous value
                current_line = prev_line
        
        df.loc[df.index[i], 'follow_line'] = current_line
    
    # Trend direction determination
    for i in range(1, len(df)):
        current_line = df['follow_line'].iloc[i]
        prev_line = df['follow_line'].iloc[i-1]
        
        if not np.isnan(current_line) and not np.isnan(prev_line):
            if current_line > prev_line:
                df.loc[df.index[i], 'trend'] = 1
            elif current_line < prev_line:
                df.loc[df.index[i], 'trend'] = -1
            else:
                df.loc[df.index[i], 'trend'] = df['trend'].iloc[i-1]
    
    # Position signals
    df['fl_position'] = None
    
    # Long signal: previous trend was -1 and current trend is 1
    long_condition = (df['trend'].shift(1) == -1) & (df['trend'] == 1)
    df.loc[long_condition, 'fl_position'] = 'Long'
    
    # Short signal: previous trend was 1 and current trend is -1
    short_condition = (df['trend'].shift(1) == 1) & (df['trend'] == -1)
    df.loc[short_condition, 'fl_position'] = 'Short'
    
    return df