import pandas as pd
import ta  # 기술적 지표 라이브러리
import numpy as np

def process_chart_data(df):

    # 1. MACD (Moving Average Convergence Divergence)
    # SMA 초기값을 사용하는 EMA 함수
    def ema_with_sma_init(series, period):
        sma = series.rolling(window=period, min_periods=period).mean()
        ema = series.ewm(span=period, adjust=False).mean()
        ema[:period] = sma[:period]  # 초기값을 SMA로 설정
        return ema

    # MACD 계산
    fast_period = 12
    slow_period = 26
    signal_period = 9

    df['EMA_fast'] = ema_with_sma_init(df['close'], fast_period)
    df['EMA_slow'] = ema_with_sma_init(df['close'], slow_period)
    df['macd'] = df['EMA_fast'] - df['EMA_slow']
    df['macd_signal'] = ema_with_sma_init(df['macd'], signal_period)
    df['macd_diff'] = df['macd'] - df['macd_signal']


    # 1++ MACD stragy 용 계산 (사용자 정의 파라미터 적용)

    fast_length=4
    slow_length=100
    macd_length=21

    df['macd_stg'] = ta.trend.ema_indicator(df['close'], window=fast_length) - ta.trend.ema_indicator(df['close'], window=slow_length)
    df['macd_signal_stg'] = ta.trend.ema_indicator(df['macd'], window=macd_length)
    df['macd_diff_stg'] = df['macd'] - df['macd_signal']

    # Wilder 방식 스무딩 함수
    def wilder_smoothing(series, period):
        return series.ewm(alpha=1/period, adjust=False).mean()

    # 2. RSI (Relative Strength Index)
    df['rsi'] = ta.momentum.rsi(df['close'], window=14).fillna(50)

    # Bollinger Bands
    df['BBUpper'] = (df['close'].rolling(window=21).mean() + 
                    df['close'].rolling(window=21).std() * 1.00).bfill()
    df['BBLower'] = (df['close'].rolling(window=21).mean() - 
                    df['close'].rolling(window=21).std() * 1.00).bfill()

    # Moving Averages
    df['maFast'] = df['close'].rolling(window=50).mean().bfill()
    df['maSlow'] = df['close'].rolling(window=200).mean().bfill()


    # 2. RSI의 21기간 SMA
    df['rsi_sma'] = df['rsi'].rolling(window=21).mean()

    # 3. ATR 계산
    tr = np.maximum(df['high'] - df['low'], 
                    np.maximum(abs(df['high'] - df['close'].shift(1)), 
                            abs(df['low'] - df['close'].shift(1))))
    df['atr_10'] = wilder_smoothing(tr, 10)
    df['atr_100'] = wilder_smoothing(tr, 100)
    df['atr_200'] = wilder_smoothing(tr, 200)





    # adx di
    adx_period = 14

    # 조정치 정의
    adjust_di_plus = 0  # DI+에 추가할 조정치
    adjust_di_minus = 0  # DI-에 추가할 조정치

    # 1. True Range (TR) 계산
    df['TR'] = np.maximum(df['high'] - df['low'], 
                        np.maximum(abs(df['high'] - df['close'].shift(1)), 
                                    abs(df['low'] - df['close'].shift(1))))
    df['TR'] = df['TR'].fillna(0)

    # 2. Directional Movement (DM+ 및 DM-) 계산
    df['DM+'] = np.where((df['high'] - df['high'].shift(1)) > (df['low'].shift(1) - df['low']),
                        np.maximum(df['high'] - df['high'].shift(1), 0), 0)
    df['DM-'] = np.where((df['low'].shift(1) - df['low']) > (df['high'] - df['high'].shift(1)),
                        np.maximum(df['low'].shift(1) - df['low'], 0), 0)

    # 동시 활성화 방지
    df.loc[df['DM+'] > 0, 'DM-'] = 0
    df.loc[df['DM-'] > 0, 'DM+'] = 0
    df[['DM+', 'DM-']] = df[['DM+', 'DM-']].fillna(0)

    # 3. Wilder 스무딩
    def wilder_smoothing(series, period):
        smoothed = [series.iloc[0]]  # 초기값
        for i in range(1, len(series)):
            prev = smoothed[-1]
            current = series.iloc[i]
            smoothed.append(prev - (prev / period) + current)
        return pd.Series(smoothed, index=series.index)

    df['Smoothed_TR'] = wilder_smoothing(df['TR'], adx_period)
    df['Smoothed_DM+'] = wilder_smoothing(df['DM+'], adx_period)
    df['Smoothed_DM-'] = wilder_smoothing(df['DM-'], adx_period)

    # 4. DI+ 및 DI- 계산 (조정치 추가)
    df['DI+'] = np.where(df['Smoothed_TR'] > 0, 100 * (df['Smoothed_DM+'] / df['Smoothed_TR']), 0) + adjust_di_plus
    df['DI-'] = np.where(df['Smoothed_TR'] > 0, 100 * (df['Smoothed_DM-'] / df['Smoothed_TR']), 0) + adjust_di_minus

    # 5. DX 계산
    df['DX'] = np.where((df['DI+'] + df['DI-']) > 0,
                        100 * abs(df['DI+'] - df['DI-']) / (df['DI+'] + df['DI-']),
                        0)

    # 6. ADX 계산
    df['ADX'] = df['DX'].rolling(window=adx_period).mean()




    # 필요없는 중간 계산 열 삭제
    df.drop(columns=['TR', 'DM+', 'DM-', 'DX'], inplace=True)

    length = 4
    df['ema'] = ta.trend.ema_indicator(df['close'], window=length)

    return df
