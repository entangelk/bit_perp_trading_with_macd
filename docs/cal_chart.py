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
    df['TR'] = np.maximum(df['high'] - df['low'], 
                        np.maximum(abs(df['high'] - df['close'].shift(1)), 
                                    abs(df['low'] - df['close'].shift(1))))

    # 기존 TR을 활용하여 ATR 계산
    # df['atr_10'] = wilder_smoothing(df['TR'], 10)
    # df['atr_100'] = wilder_smoothing(df['TR'], 100)
    # df['atr_200'] = wilder_smoothing(df['TR'], 200)

   # 기존 TR을 활용하여 SMA 방식으로 ATR 계산
    df['atr_10'] = df['TR'].rolling(window=10).mean()
    df['atr_100'] = df['TR'].rolling(window=100).mean()
    df['atr_200'] = df['TR'].rolling(window=200).mean()

    ''' 수퍼트랜드 계산 파일로 이동동
    # 3. Supertrend 계산
    multiplier = 4
    # df['UpperBand'] = (df['high'] + df['low']) / 2 - multiplier * df['atr_100']
    # df['LowerBand'] = (df['high'] + df['low']) / 2 + multiplier * df['atr_100']


    # ATR 계산 후 UpperBand 및 LowerBand 계산
    df['UpperBand'] = df['close'] + (multiplier * df['atr_100'])
    df['LowerBand'] = df['close'] - (multiplier * df['atr_100'])

    # 상한선과 하한선 갱신 로직
    df['UpperBand'] = np.where(df['close'].shift(1) > df['UpperBand'].shift(1), 
                                np.maximum(df['UpperBand'], df['UpperBand'].shift(1)), 
                                df['UpperBand'])

    df['LowerBand'] = np.where(df['close'].shift(1) < df['LowerBand'].shift(1), 
                                np.minimum(df['LowerBand'], df['LowerBand'].shift(1)), 
                                df['LowerBand'])

    print(f"upper : {df['UpperBand'].tail(1).values[0]}, lower : {df['LowerBand'].tail(1).values[0]}")
    '''


    # adx di
    adx_period = 14

    # 조정치 정의
    adjust_di_plus = 0  # DI+에 추가할 조정치
    adjust_di_minus = 0  # DI-에 추가할 조정치


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


    # 7. DI 이동평균선 계산
    df['DI+_MA7'] = df['DI+'].rolling(window=7).mean()
    df['DI-_MA7'] = df['DI-'].rolling(window=7).mean()

    # 필요없는 중간 계산 열 삭제
    df.drop(columns=['DM+', 'DM-', 'DX'], inplace=True)

    # Length 설정
    length = 1

    # Pine Script와 동일한 동작을 구현
    if length == 1:
        # 기간이 1이면 EMA 대신 close 값을 그대로 사용
        df['ema'] = df['close']
    else:
        # 기간이 1이 아니면 ta 라이브러리의 EMA 계산
        df['ema'] = ta.trend.ema_indicator(df['close'], window=length)

    # HMA (Hull Moving Average) 계산 추가
    def weighted_moving_average(series, period):
        weights = np.arange(1, period + 1)
        wma = series.rolling(window=period).apply(
            lambda x: np.sum(weights * x) / weights.sum(), raw=True
        )
        return wma

    def hull_moving_average(series, period):
        wma_half_period = weighted_moving_average(series, period // 2)
        wma_full_period = weighted_moving_average(series, period)
        hull = 2 * wma_half_period - wma_full_period
        hma = weighted_moving_average(hull, int(np.sqrt(period)))
        return hma

    # Intraday HMA 계산
    df['hma1'] = hull_moving_average(df['close'], 20)
    df['hma2'] = hull_moving_average(df['close'], 50)
    df['hma3'] = hull_moving_average(df['close'], 100)

    # HMA 신호 계산
    df['hma_buy_signal'] = (df['hma3'] < df['hma2']) & \
                          (df['hma3'] < df['hma1']) & \
                          (df['hma1'] > df['hma2'])
    
    df['hma_sell_signal'] = (df['hma3'] > df['hma2']) & \
                           (df['hma3'] > df['hma1']) & \
                           (df['hma2'] > df['hma1'])


    # Squeeze Momentum Oscillator 계산 추가
    momentum_length = 12
    swing_length = 20
    squeeze_period = 14
    squeeze_smooth = 7
    squeeze_length = 20
    hyper_squeeze_length = 5
    
    # ATR 관련 계산은 기존 코드 활용
    # TR은 이미 계산되어 있으므로 재사용
    
   
    
    # ATR과 EMA 계산
    df['squeeze_atr'] = df['TR'].ewm(span=squeeze_period, adjust=False).mean()
    df['squeeze_atr_ema'] = df['squeeze_atr'].ewm(span=squeeze_period*2, adjust=False).mean()
    df['volatility'] = df['squeeze_atr_ema'] - df['squeeze_atr']
    
    df['high_low_diff'] = df['high'] - df['low']
    df['ema_hl_diff'] = df['high_low_diff'].ewm(span=squeeze_period*2, adjust=False).mean()
    df['squeeze_value'] = (df['volatility'] / df['ema_hl_diff'] * 100).ewm(span=squeeze_smooth, adjust=False).mean()
    df['squeeze_ma'] = df['squeeze_value'].ewm(span=squeeze_length, adjust=False).mean()  # 여기서 20 사용
    
    # Hyper squeeze 계산
    df['rising_squeeze'] = df['squeeze_value'].diff(hyper_squeeze_length) > 0
    df['hypersqueeze'] = (df['squeeze_value'] > 0) & df['rising_squeeze']
    
    # 모멘텀 오실레이터 계산
    df['lowest'] = df['low'].rolling(window=momentum_length).min()
    df['highest'] = df['high'].rolling(window=momentum_length).max()
    df['ema_lowest'] = df['lowest'].ewm(span=momentum_length, adjust=False).mean()
    df['ema_highest'] = df['highest'].ewm(span=momentum_length, adjust=False).mean()
    
    # Direction 계산
    df['squeeze_d'] = 0
    df.loc[df['close'] > df['ema_highest'], 'squeeze_d'] = 1
    df.loc[df['close'] < df['ema_lowest'], 'squeeze_d'] = -1
    
    # Value 계산
    df['squeeze_val'] = np.where(df['squeeze_d'] == 1, df['ema_lowest'], df['ema_highest'])
    df['squeeze_val1'] = df['close'] - df['squeeze_val']
    
    # Hull Moving Average는 이미 구현되어 있으므로 재사용
    df['squeeze_val2'] = hull_moving_average(df['squeeze_val1'], momentum_length)
    df['squeeze_vf'] = (df['squeeze_val2'] / (df['high_low_diff'].ewm(span=momentum_length*2, adjust=False).mean()) * 100) / 8
    
    # Z-score 계산
    df['squeeze_basis'] = df['squeeze_vf'].rolling(window=swing_length).mean()
    df['squeeze_stdev'] = df['squeeze_vf'].rolling(window=swing_length).std()
    df['squeeze_zscore'] = ((df['squeeze_vf'] - df['squeeze_basis']) / df['squeeze_stdev']) * 66
    df['squeeze_zscore'] = df['squeeze_zscore'].ewm(span=swing_length, adjust=False).mean()
    
    # 불필요한 중간 계산 컬럼 제거
    squeeze_cols_to_drop = ['lowest', 'highest', 'ema_lowest', 'ema_highest', 
                           'squeeze_d', 'squeeze_val', 'squeeze_val1', 
                           'squeeze_basis', 'squeeze_stdev']
    df.drop(columns=squeeze_cols_to_drop, inplace=True)


    return df
