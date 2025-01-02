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
    size_ratio = 1.2

    df['EMA_fast'] = ema_with_sma_init(df['close'], fast_period)
    df['EMA_slow'] = ema_with_sma_init(df['close'], slow_period)
    df['macd'] = df['EMA_fast'] - df['EMA_slow']
    df['macd_signal'] = ema_with_sma_init(df['macd'], signal_period)
    df['hist'] = df['macd'] - df['macd_signal']
    

    # MACD Size 분석
    df['hist_size'] = abs(df['hist'])
    df['candle_size'] = abs(df['close'] - df['open'])
    df['candle_size_ma'] = df['candle_size'].rolling(window=slow_period).mean()
    df['normalized_candle_size'] = df['candle_size'] / df['candle_size_ma']
    df['hist_size_ma'] = df['hist_size'].rolling(window=slow_period).mean()
    df['normalized_hist_size'] = df['hist_size'] / df['hist_size_ma']

    # === 두 번째 전략 추가 계산 (MACD Direction) ===
    df['hist_direction'] = df['hist'] - df['hist'].shift(1)

    # STC는 조금더 연구해 본 이후 사용용
    '''
    df['STC_fast_ma'] = df['close'].ewm(span=fast_length, adjust=False).mean()
    df['STC_slow_ma'] = df['close'].ewm(span=slow_length, adjust=False).mean()
    df['STC_macd'] = df['STC_fast_ma'] - df['STC_slow_ma']
    
    

    # STC 파라미터 설정
    stc_length = 12           # Stochastic 계산 기간
    stc_fast_length = 26      # 빠른 EMA 기간
    stc_slow_length = 50      # 느린 EMA 기간
    stc_smooth_constant = 0.5 # 스무딩 상수

    # Fast & Slow EMA 계산
    df['STC_fast_ma'] = df['close'].ewm(span=stc_fast_length, adjust=False).mean()
    df['STC_slow_ma'] = df['close'].ewm(span=stc_slow_length, adjust=False).mean()
    df['STC_macd'] = df['STC_fast_ma'] - df['STC_slow_ma']

    # 첫 번째 Stochastic
    df['STC_stoch1'] = 0.0
    for i in range(stc_length-1, len(df)):
        window = df['STC_macd'].iloc[i-stc_length+1:i+1]
        lowest_low = window.min()
        highest_high = window.max()
        
        if highest_high - lowest_low > 0:
            df.iloc[i, df.columns.get_loc('STC_stoch1')] = (
                (df['STC_macd'].iloc[i] - lowest_low) / (highest_high - lowest_low) * 100
            )
        else:
            df.iloc[i, df.columns.get_loc('STC_stoch1')] = df['STC_stoch1'].iloc[i-1] if i > 0 else 0

    # 첫 번째 Smoothing
    df['STC_stoch1_smooth'] = 0.0
    for i in range(len(df)):
        if i == 0:
            df.iloc[i, df.columns.get_loc('STC_stoch1_smooth')] = df['STC_stoch1'].iloc[i]
        else:
            prev_smooth = df['STC_stoch1_smooth'].iloc[i-1]
            current_value = df['STC_stoch1'].iloc[i]
            df.iloc[i, df.columns.get_loc('STC_stoch1_smooth')] = (
                prev_smooth + stc_smooth_constant * (current_value - prev_smooth)
            )

    # 두 번째 Stochastic
    df['STC_stoch2'] = 0.0
    for i in range(stc_length-1, len(df)):
        window = df['STC_stoch1_smooth'].iloc[i-stc_length+1:i+1]
        lowest_low = window.min()
        highest_high = window.max()
        
        if highest_high - lowest_low > 0:
            df.iloc[i, df.columns.get_loc('STC_stoch2')] = (
                (df['STC_stoch1_smooth'].iloc[i] - lowest_low) / (highest_high - lowest_low) * 100
            )
        else:
            df.iloc[i, df.columns.get_loc('STC_stoch2')] = df['STC_stoch2'].iloc[i-1] if i > 0 else 0

    # 최종 STC (두 번째 Smoothing)
    df['STC'] = 0.0
    for i in range(len(df)):
        if i == 0:
            df.iloc[i, df.columns.get_loc('STC')] = df['STC_stoch2'].iloc[i]
        else:
            prev_smooth = df['STC'].iloc[i-1]
            current_value = df['STC_stoch2'].iloc[i]
            df.iloc[i, df.columns.get_loc('STC')] = (
                prev_smooth + stc_smooth_constant * (current_value - prev_smooth)
            )

    # 매수/매도 신호 생성
    df['STC_signal'] = 'none'
    for i in range(3, len(df)):
        # 매수 신호: 25 이하에서 상승 반전
        if (df['STC'].iloc[i-3] >= df['STC'].iloc[i-2] and 
            df['STC'].iloc[i-2] < df['STC'].iloc[i-1] and 
            df['STC'].iloc[i] < 25):
            df.iloc[i, df.columns.get_loc('STC_signal')] = 'buy'
        
        # 매도 신호: 75 이상에서 하락 반전
        elif (df['STC'].iloc[i-3] <= df['STC'].iloc[i-2] and 
                df['STC'].iloc[i-2] > df['STC'].iloc[i-1] and 
                df['STC'].iloc[i] > 75):
            df.iloc[i, df.columns.get_loc('STC_signal')] = 'sell'

    # 중간 계산 컬럼 삭제
    columns_to_drop = ['STC_fast_ma', 'STC_slow_ma', 'STC_macd', 'STC_stoch1', 
                    'STC_stoch1_smooth', 'STC_stoch2']
    df.drop(columns=columns_to_drop, inplace=True)
    '''

 
    # Wilder 방식 스무딩 함수
    def wilder_smoothing(series, period):
        return series.ewm(alpha=1/period, adjust=False).mean()



    # Bollinger Bands
    df['BBUpper'] = (df['close'].rolling(window=21).mean() + 
                    df['close'].rolling(window=21).std() * 1.00).bfill()
    df['BBLower'] = (df['close'].rolling(window=21).mean() - 
                    df['close'].rolling(window=21).std() * 1.00).bfill()

    # Moving Averages
    df['maFast'] = df['close'].rolling(window=50).mean().bfill()
    df['maSlow'] = df['close'].rolling(window=200).mean().bfill()

    # 2. RSI (Relative Strength Index)
    rsi_length = 14
    df['rsi'] = ta.momentum.rsi(df['close'], window=rsi_length).fillna(50)

    # 2. RSI의 21기간 SMA
    df['rsi_sma'] = df['rsi'].rolling(window=21).mean()


    # === DI Calculation ===
    len_di = 14
    slope_len = 4
    min_slope_threshold = 12

    # 3. ATR 계산
    df['TR'] = np.maximum(df['high'] - df['low'], 
                        np.maximum(abs(df['high'] - df['close'].shift(1)), 
                                    abs(df['low'] - df['close'].shift(1))))

    # 기존 TR을 활용하여 ATR 계산
    # df['atr_10'] = wilder_smoothing(df['TR'], 10)
    # df['atr_100'] = wilder_smoothing(df['TR'], 100)
    # df['atr_200'] = wilder_smoothing(df['TR'], 200)

   # 기존 TR을 활용하여 SMA 방식으로 ATR 계산
    # df['atr_10'] = df['TR'].rolling(window=10).mean()
    # df['atr_35'] = df['TR'].rolling(window=35).mean()
    # df['atr_100'] = df['TR'].rolling(window=100).mean()
    # df['atr_200'] = df['TR'].rolling(window=200).mean()


    # RMA 함수 정의
    def rma(series, period):
        alpha = 1/period
        return series.ewm(alpha=alpha, adjust=False).mean()

    # 기존 TR을 활용하여 ATR 계산 (SMA와 RMA 모두)
    df['atr_10'] = rma(df['TR'], 10)  # RMA로 변경
    df['atr_35'] = rma(df['TR'], 35)  # RMA로 변경
    df['atr_100'] = rma(df['TR'], 100)  # RMA로 변경
    df['atr_200'] = rma(df['TR'], 200)  # RMA로 변경


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
    len_di = 14


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
        # 첫 번째 유효한 값을 찾아 초기값으로 사용
        first_valid = series.first_valid_index()
        if first_valid is None:
            return pd.Series(index=series.index)
        
        smoothed = []
        # 첫 번째 유효값 이전은 NaN으로 채움
        first_valid_loc = series.index.get_loc(first_valid)
        smoothed.extend([np.nan] * first_valid_loc)
        smoothed.append(series[first_valid])
        
        for i in range(first_valid_loc + 1, len(series)):
            prev = smoothed[i-1] if not pd.isna(smoothed[i-1]) else series.iloc[i]
            current = series.iloc[i]
            if pd.isna(current):
                smoothed.append(prev)
            else:
                smoothed.append(prev - (prev / period) + current)
        
        return pd.Series(smoothed, index=series.index)

    df['Smoothed_TR'] = wilder_smoothing(df['TR'], len_di)
    df['Smoothed_DM+'] = wilder_smoothing(df['DM+'], len_di)
    df['Smoothed_DM-'] = wilder_smoothing(df['DM-'], len_di)

    # DI+ 및 DI- 계산
    df['DI+'] = 100 * (df['Smoothed_DM+'] / df['Smoothed_TR'])
    df['DI-'] = 100 * (df['Smoothed_DM-'] / df['Smoothed_TR'])

    # DI Slopes
    df['DIPlus_slope1'] = df['DI+'] - df['DI+'].shift(slope_len)
    df['DIMinus_slope1'] = df['DI-'] - df['DI-'].shift(slope_len)
    
    # === 두 번째 전략의 DI Slope (slope_len=3) ===
    df['DIPlus_slope2'] = df['DI+'] - df['DI+'].shift(3)
    df['DIMinus_slope2'] = df['DI-'] - df['DI-'].shift(3)
    df['slope_diff'] = df['DIPlus_slope2'] - df['DIMinus_slope2']

    # 5. DX 계산
    df['DX'] = np.where((df['DI+'] + df['DI-']) > 0,
                        100 * abs(df['DI+'] - df['DI-']) / (df['DI+'] + df['DI-']),
                        0)

    # 6. ADX 계산
    df['ADX'] = df['DX'].rolling(window=len_di).mean()


    # 불필요한 중간 계산 컬럼 제거
    columns_to_drop = ['TR', 'DM+', 'DM-', 'Smoothed_TR', 'Smoothed_DM+', 'Smoothed_DM-']
    df.drop(columns=columns_to_drop, inplace=True)
    
    
    
    '''
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
    squeeze_period = 20
    squeeze_smooth = 7
    squeeze_length = 14
    hyper_squeeze_length = 5
    
    # ATR 관련 계산은 기존 코드 활용
    # TR은 이미 계산되어 있으므로 재사용
    
    def precise_pine_ema(series, length):
        alpha = 2 / (length + 1)
        ema = series.copy()
        
        # 첫 번째 값은 그대로 사용
        for i in range(1, len(series)):
            if pd.notna(series.iloc[i]) and pd.notna(ema.iloc[i-1]):
                # Pine Script의 EMA 로직을 더 정확하게 재현
                ema.iloc[i] = alpha * series.iloc[i] + (1 - alpha) * ema.iloc[i-1]
        
        return ema

    # ATR과 EMA 계산

    df['squeeze_atr'] = precise_pine_ema(df['TR'], squeeze_period)
    df['squeeze_atr_ema'] = precise_pine_ema(df['squeeze_atr'], squeeze_period*2)
    df['volatility'] = df['squeeze_atr_ema'] - df['squeeze_atr']

    df['high_low_diff'] = df['high'] - df['low']
    df['ema_hl_diff'] = precise_pine_ema(df['high_low_diff'], squeeze_period*2)

    # Squeeze 값 계산에만 Wilder 스무딩 적용
    df['squeeze_value'] = precise_pine_ema(df['volatility'] / df['ema_hl_diff'] * 100, squeeze_smooth)
    df['squeeze_ma'] = precise_pine_ema(df['squeeze_value'], squeeze_length)

    def is_rising_for(series, length):
        for i in range(len(series) - length + 1):
            if all(series.iloc[i+j] > series.iloc[i+j-1] for j in range(1, length)):
                return True
        return False

    # DataFrame에 적용
    df['rising_squeeze'] = False  # 초기화
    
    df.iloc[-1, df.columns.get_loc('rising_squeeze')] = is_rising_for(df['squeeze_value'][len(df)-hyper_squeeze_length:len(df)], hyper_squeeze_length)
    
    
    
    
    df['hypersqueeze'] = (df['squeeze_value'] > 0) & df['rising_squeeze']

    # 모멘텀 오실레이터 계산
    df['lowest'] = df['low'].rolling(window=momentum_length).min()
    df['highest'] = df['high'].rolling(window=momentum_length).max()

    # EMA 스무딩에 precise_pine_ema 적용
    df['ema_lowest'] = precise_pine_ema(df['lowest'], momentum_length)
    df['ema_highest'] = precise_pine_ema(df['highest'], momentum_length)

    # Direction 계산
    df['squeeze_d'] = 0  # 초기화

    # crossover/crossunder 감지
    crossover = (df['close'] > df['ema_highest']) & (df['close'].shift(1) <= df['ema_highest'].shift(1))
    crossunder = (df['close'] < df['ema_lowest']) & (df['close'].shift(1) >= df['ema_lowest'].shift(1))

    # d값 설정
    df.loc[crossover, 'squeeze_d'] = 1
    df.loc[crossunder, 'squeeze_d'] = -1

    # 이전 값 유지를 위한 forward fill
    df['squeeze_d'] = df['squeeze_d'].replace(0, np.nan).ffill().fillna(0)

    df['squeeze_val'] = np.where(df['squeeze_d'] == 1, df['ema_lowest'], df['ema_highest'])
    df['squeeze_val1'] = df['close'] - df['squeeze_val']

    df['squeeze_val2'] = hull_moving_average(df['squeeze_val1'], momentum_length)  # 기존에 정의된 hull_moving_average 함수 사용
    df['squeeze_vf'] = (df['squeeze_val2'] / df['high_low_diff'].ewm(span=momentum_length*2, adjust=False).mean() * 100) / 8

   
   
   
    # SMA로 basis 계산
    df['squeeze_basis'] = df['squeeze_vf'].rolling(window=swing_length).mean()

    # SMA 기반 표준편차 
    df['squeeze_stdev'] = df['squeeze_vf'].rolling(window=swing_length).std(ddof=1)

    # Z-score 계산
    df['squeeze_zscore'] = (df['squeeze_vf'] - df['squeeze_basis']) / df['squeeze_stdev']




    # EMA 스무딩 적용
    df['squeeze_zscore'] = precise_pine_ema(df['squeeze_zscore'], swing_length)

    # 66 곱하기
    df['squeeze_zscore'] = df['squeeze_zscore'] * 66
    


    # 불필요한 중간 계산 컬럼 제거
    squeeze_cols_to_drop = ['lowest', 'highest', 'ema_lowest', 'ema_highest', 
                           'squeeze_d', 'squeeze_val', 'squeeze_val1', 
                           'squeeze_basis', 'squeeze_stdev']
    df.drop(columns=squeeze_cols_to_drop, inplace=True)


    
    current = df.iloc[-1]

    # 2. 스퀴즈 상태 체크를 위한 값들 출력
    squeeze_diff = current['squeeze_ma'] - current['squeeze_value']  
    df.loc[current.name, 'squeeze_diff'] = squeeze_diff

    current_hypersqueeze = (current['squeeze_value'] > 0) and all(
        current['squeeze_value'] > current['squeeze_value'].shift(i) 
        for i in range(1, hyper_squeeze_length + 1)
    )

    print("\n=== Squeeze 상태 디버그 ===")
    print(f"squeeze_value: {current['squeeze_value']}")
    print(f"squeeze_ma: {current['squeeze_ma']}")
    print(f"squeeze_diff: {squeeze_diff}")
    print(f"hypersqueeze: {current_hypersqueeze}")

    if current_hypersqueeze:
        df.loc[current.name, 'squeeze_state'] = 'YELLOW'
    elif squeeze_diff < 0:
        df.loc[current.name, 'squeeze_state'] = 'ORANGE'
    else:
        df.loc[current.name, 'squeeze_state'] = 'GRAY'

    print(f"최종 설정된 상태: {df.loc[current.name, 'squeeze_state']}")

    # 색상 상태 분포 확인
    print("상태별 분포:")
    print(df['squeeze_state'].value_counts(normalize=True))

    # 조건별 상세 분석
    print("\n상세 조건 분석:")
    print("Hypersqueeze 횟수:", df['hypersqueeze'].sum())
    print("Squeeze Diff < 0 횟수:", (df['squeeze_value'] - df['squeeze_ma'] < 0).sum())

    # 상태 변화 지점 확인
    def analyze_state_transitions(df):
        transitions = df[df['squeeze_state'] != df['squeeze_state'].shift(1)]
        print("\n상태 변화 지점:")
        print(transitions[['squeeze_value', 'squeeze_ma', 'squeeze_diff', 'hypersqueeze', 'squeeze_state']])
        return transitions

    df = analyze_state_transitions(df)
    '''

    """차트 데이터 처리 및 지표 계산"""
    # 변수 설정
    vol_length = 9
    trend_length = 10
    norm_period = 100
    
    
    # 볼륨 이동평균
    df['vol_ma'] = df['volume'].rolling(vol_length).mean()
    
    # 상승/하락 볼륨 구분
    up_vol = np.where(df['close'] >= df['open'], df['volume'], 0)
    down_vol = np.where(df['close'] < df['open'], df['volume'], 0)
    
    # 상승/하락 볼륨 이동평균
    df['up_vol_ma'] = pd.Series(up_vol).rolling(vol_length).mean()
    df['down_vol_ma'] = pd.Series(down_vol).rolling(vol_length).mean()
    
    # 볼륨 강도 계산
    df['vol_strength'] = ((df['up_vol_ma'] - df['down_vol_ma']) / df['vol_ma']) * 100
    
    # 볼륨 강도의 추세
    df['vol_trend'] = df['vol_strength'].ewm(span=trend_length, adjust=False).mean()
    
    # 정규화를 위한 최대/최소
    df['vt_highest'] = df['vol_trend'].rolling(norm_period).max()
    df['vt_lowest'] = df['vol_trend'].rolling(norm_period).min()
    
    # 트렌드 정규화
    df['norm_trend'] = ((df['vol_trend'] - df['vt_lowest']) / 
                       (df['vt_highest'] - df['vt_lowest'])) * 2 - 1
    
    # 시그널 라인
    df['signal_line'] = df['norm_trend'].ewm(span=trend_length, adjust=False).mean()
    
    # 차이값 계산
    df['trend_diff'] = abs(df['norm_trend'] - df['signal_line'])


    return df


if __name__ == "__main__":


    set_timevalue = '5m'
    period = 700  # 전체 데이터 수
    start_from = 85  # 과거 n번째 데이터 (뒤에서부터)
    slice_size = 300  # 슬라이싱할 데이터 개수 m
    total_ticks = 85

    from pymongo import MongoClient
    # MongoDB에 접속
    mongoClient = MongoClient("mongodb://mongodb:27017")
    database = mongoClient["bitcoin"]

    # set_timevalue 값에 따라 적절한 차트 컬렉션 선택
    chart_collections = {
        '1m': 'chart_1m',
        '3m': 'chart_3m',
        '5m': 'chart_5m',
        '15m': 'chart_15m',
        '1h': 'chart_1h',
        '30d': 'chart_30d'
    }
    
    if set_timevalue not in chart_collections:
        raise ValueError(f"Invalid time value: {set_timevalue}")
    
    chart_collection = database[chart_collections[set_timevalue]]    


    for start_from in range(start_from, 0, -1):
        

        # 최신 데이터부터 과거 데이터까지 모두 가져오기
        data_cursor = chart_collection.find().sort("timestamp", -1)
        data_list = list(data_cursor)

        # MongoDB 데이터를 DataFrame으로 변환
        df = pd.DataFrame(data_list)

        # 타임스탬프를 datetime 형식으로 변환
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # 불필요한 ObjectId 필드 제거
        if '_id' in df.columns:
            df.drop('_id', axis=1, inplace=True)

        # 인덱스를 타임스탬프로 설정
        df.set_index('timestamp', inplace=True)

        # 시간순으로 정렬 (오름차순으로 변환)
        df.sort_index(inplace=True)

        # 과거 n번째 데이터부터 m개의 데이터 슬라이싱
        if start_from > len(df):
            raise ValueError(f"start_from ({start_from}) is larger than available data length ({len(df)})")
        
        df = df.iloc[-(start_from + slice_size):-start_from]

        df = process_chart_data(df)
        
        from strategy.supertrend import supertrend

        df = supertrend(df)

        pass
