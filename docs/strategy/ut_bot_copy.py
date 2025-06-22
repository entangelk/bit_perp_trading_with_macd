import pandas as pd
import numpy as np

def calculate_atr(df, period=14):
    """
    ATR(Average True Range) 계산
    """
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift(1))
    low_close = np.abs(df['low'] - df['close'].shift(1))
    
    true_range = np.maximum(high_low, np.maximum(high_close, low_close))
    atr = true_range.rolling(window=period).mean()
    return atr

def ut_bot_alerts(df, atr_period=14, factor=3):
    df['ATR'] = calculate_atr(df, period=atr_period)
    df['Buy_Stop'] = df['low'] - (df['ATR'] * factor)
    df['Sell_Stop'] = df['high'] + (df['ATR'] * factor)
    
    df['Signal'] = None  # 신호 열 초기화

    for i in range(1, len(df)):
        # 디버깅: 현재 상태 출력
        print(f"Index: {i}, Close: {df['close'].iloc[i]}, "
              f"Buy_Stop: {df['Buy_Stop'].iloc[i - 1]}, "
              f"Sell_Stop: {df['Sell_Stop'].iloc[i - 1]}")

        # 이전 신호 유지
        if i > 1:
            df.iloc[i, df.columns.get_loc('Signal')] = df.iloc[i - 1, df.columns.get_loc('Signal')]

        # 매수 신호 조건 (Buy Signal)
        if df['close'].iloc[i] > df['Buy_Stop'].iloc[i - 1]:
            print(f"Buy Signal at Index {i}")
            df.iloc[i, df.columns.get_loc('Signal')] = 'Buy'
            # Buy_Stop 갱신
            df.iloc[i, df.columns.get_loc('Buy_Stop')] = max(
                df['Buy_Stop'].iloc[i], df['low'].iloc[i] - df['ATR'].iloc[i] * factor)

        # 매도 신호 조건 (Sell Signal)
        elif df['close'].iloc[i] < df['Sell_Stop'].iloc[i - 1]:
            print(f"Sell Signal at Index {i}")
            df.iloc[i, df.columns.get_loc('Signal')] = 'Sell'
            # Sell_Stop 갱신
            df.iloc[i, df.columns.get_loc('Sell_Stop')] = min(
                df['Sell_Stop'].iloc[i], df['high'].iloc[i] + df['ATR'].iloc[i] * factor)

    return df



if __name__ == "__main__":
    # 예제 데이터프레임
    data = {
        'close': [100, 102, 101, 105, 107, 103, 106, 110, 108, 112, 115, 117, 119, 118, 116],
        'high': [102, 103, 104, 107, 108, 104, 107, 111, 110, 113, 116, 118, 120, 119, 117],
        'low': [98, 101, 100, 103, 105, 101, 104, 109, 107, 111, 114, 116, 117, 116, 115],
    }
    df = pd.DataFrame(data)

    # UT Bot Alerts 계산
    result_df = ut_bot_alerts(df,atr_period=3)

    # 결과 출력
    print(result_df)
