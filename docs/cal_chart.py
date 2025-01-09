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
    slow_period_for_di = 17
    signal_period_for_di = 20
    signal_period = 9
    size_ratio = 1.2

    df['EMA_fast'] = ema_with_sma_init(df['close'], fast_period)
    df['EMA_slow'] = ema_with_sma_init(df['close'], slow_period)
    df['EMA_slow_di'] = ema_with_sma_init(df['close'], slow_period_for_di)

    df['macd'] = df['EMA_fast'] - df['EMA_slow']
    df['macd_di'] = df['EMA_fast'] - df['EMA_slow_di']

    df['macd_signal'] = ema_with_sma_init(df['macd'], signal_period)
    df['macd_signal_di'] = ema_with_sma_init(df['macd'], signal_period_for_di)

    df['hist'] = df['macd'] - df['macd_signal']
    df['hist_di'] = df['macd'] - df['macd_signal_di']

    # MACD for divergence
    fast_period_dive = 17
    slow_period_dive = 27
    signal_period_dive = 7

    df['EMA_fast_dive'] = ema_with_sma_init(df['close'], fast_period_dive)
    df['EMA_slow_dive'] = ema_with_sma_init(df['close'], slow_period_dive)

    df['macd_dive'] = df['EMA_fast_dive'] - df['EMA_slow_dive']
    df['macd_signal_dive'] = ema_with_sma_init(df['macd_dive'], signal_period_dive)

    df['hist_dive'] = df['macd_dive'] - df['macd_signal_dive']




    # MACD Size 분석
    df['hist_size'] = abs(df['hist'])
    df['candle_size'] = abs(df['close'] - df['open'])
    df['candle_size_ma'] = df['candle_size'].rolling(window=slow_period).mean()
    df['normalized_candle_size'] = df['candle_size'] / df['candle_size_ma']
    df['hist_size_ma'] = df['hist_size'].rolling(window=slow_period).mean()
    df['normalized_hist_size'] = df['hist_size'] / df['hist_size_ma']

    # MACD di Size 분석
    df['hist_size_di'] = abs(df['hist_di'])
    df['candle_size_di'] = abs(df['close'] - df['open'])
    df['candle_size_ma_di'] = df['candle_size_di'].rolling(window=slow_period_for_di).mean()
    df['normalized_candle_size_di'] = df['candle_size_di'] / df['candle_size_ma_di']
    df['hist_size_ma_di'] = df['hist_size_di'].rolling(window=slow_period_for_di).mean()
    df['normalized_hist_size_di'] = df['hist_size_di'] / df['hist_size_ma_di']    

    # === 두 번째 전략 추가 계산 (MACD Direction) ===
    df['hist_direction'] = df['hist'] - df['hist'].shift(1)
    df['hist_direction_di'] = df['hist_di'] - df['hist_di'].shift(1)


 
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
    df['atr_34'] = rma(df['TR'], 34)  # RMA로 변경
    df['atr_100'] = rma(df['TR'], 100)  # RMA로 변경
    df['atr_200'] = rma(df['TR'], 200)  # RMA로 변경



    # adx di
    len_di = 14
    len_di_slope = 17


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

    df['Smoothed_TR_di'] = wilder_smoothing(df['TR'], len_di_slope)
    df['Smoothed_DM+_di'] = wilder_smoothing(df['DM+'], len_di_slope)
    df['Smoothed_DM-_di'] = wilder_smoothing(df['DM-'], len_di_slope)

    # DI+ 및 DI- 계산
    df['DI+'] = 100 * (df['Smoothed_DM+'] / df['Smoothed_TR'])
    df['DI-'] = 100 * (df['Smoothed_DM-'] / df['Smoothed_TR'])


    df['DI+_di'] = 100 * (df['Smoothed_DM+_di'] / df['Smoothed_TR_di'])
    df['DI-_di'] = 100 * (df['Smoothed_DM-_di'] / df['Smoothed_TR_di'])

    # # DI Slopes
    # df['DIPlus_slope1'] = df['DI+'] - df['DI+'].shift(slope_len)
    # df['DIMinus_slope1'] = df['DI-'] - df['DI-'].shift(slope_len)
    
    # DI Slopes
    df['DIPlus_slope1'] = df['DI+_di'] - df['DI+_di'].shift(slope_len)
    df['DIMinus_slope1'] = df['DI-_di'] - df['DI-_di'].shift(slope_len)

    # === 두 번째 전략의 DI Slope (slope_len=3) ===
    df['DIPlus_slope2'] = df['DI+'] - df['DI+'].shift(3)
    df['DIMinus_slope2'] = df['DI-'] - df['DI-'].shift(3)
    df['slope_diff'] = df['DIPlus_slope2'] - df['DIMinus_slope2']

    # 5. DX 계산
    df['DX'] = np.where((df['DI+'] + df['DI-']) > 0,
                        100 * abs(df['DI+'] - df['DI-']) / (df['DI+'] + df['DI-']),
                        0)
    # 5. DX 계산
    df['DX_di'] = np.where((df['DI+_di'] + df['DI-_di']) > 0,
                        100 * abs(df['DI+_di'] - df['DI-_di']) / (df['DI+_di'] + df['DI-_di']),
                        0)
    
    # 6. ADX 계산
    df['ADX'] = df['DX'].rolling(window=len_di).mean()

    df['ADX_di'] = df['DX_di'].rolling(window=len_di).mean()



    # 불필요한 중간 계산 컬럼 제거
    columns_to_drop = ['TR', 'DM+', 'DM-', 'Smoothed_TR', 'Smoothed_DM+', 'Smoothed_DM-']
    df.drop(columns=columns_to_drop, inplace=True)
    
    columns_to_drop = ['Smoothed_TR_di', 'Smoothed_DM+_di', 'Smoothed_DM-_di']
    df.drop(columns=columns_to_drop, inplace=True)
    
   

    """차트 데이터 처리 및 지표 계산"""
    # 변수 설정
    vol_length = 9
    trend_length = 11
    norm_period = 100
    
    
    # 볼륨 이동평균
    df['vol_ma'] = df['volume'].rolling(vol_length).mean()
    
    # 상승/하락 볼륨 구분 및 이동평균 계산
    df['up_vol'] = np.where(df['close'] >= df['open'], df['volume'], 0)
    df['down_vol'] = np.where(df['close'] < df['open'], df['volume'], 0)

    # 상승/하락 볼륨 이동평균
    df['up_vol_ma'] = df['up_vol'].rolling(vol_length).mean()
    df['down_vol_ma'] = df['down_vol'].rolling(vol_length).mean()
    
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


    # 3. Linear Regression Channel 계산
    length = 150
    
    # 초기값 설정
    df['slope'] = np.nan
    df['intercept'] = np.nan
    df['average'] = np.nan
    
    # 선형 회귀 계산
    for i in range(length-1, len(df)):
        sum_x = 0.0
        sum_y = 0.0
        sum_xy = 0.0
        sum_x2 = 0.0
        
        # 파인스크립트와 동일한 방식으로 계산
        for j in range(length):
            price = df['close'].iloc[i-j]  # 최신 데이터부터 역순으로
            x = length - 1 - j  # x값도 역순으로
            sum_x += x
            sum_y += price
            sum_xy += x * price
            sum_x2 += x * x
        
        n = float(length)
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
        intercept = (sum_y - slope * sum_x) / n
        average = sum_y / n
        
        df.loc[df.index[i], 'slope'] = slope
        df.loc[df.index[i], 'intercept'] = intercept
        df.loc[df.index[i], 'average'] = average

    # 중심선 계산
    df['middle_line'] = np.nan
    for i in range(len(df)):
        if not np.isnan(df['intercept'].iloc[i]):
            # 현재 캔들의 중간값 계산
            candle_middle = (df['close'].iloc[i] + df['open'].iloc[i]) / 2
            # 파인스크립트와 동일한 방식으로 계산
            df.loc[df.index[i], 'middle_line'] = df['intercept'].iloc[i] + df['slope'].iloc[i] * candle_middle
    
    # 표준편차 계산
    df['std_dev'] = np.nan

    for i in range(length-1, len(df)):
        sum_diff_sq = 0.0
        current_slope = df['slope'].iloc[i]
        current_intercept = df['intercept'].iloc[i]
        
        for j in range(length):
            expected_price = current_intercept + current_slope * float(j)
            idx = i - j  # 명시적으로 인덱스 계산
            # 최신 데이터부터 과거 순서로 계산
            diff = df['close'].iat[idx] - expected_price  # iloc 대신 iat 사용
            sum_diff_sq += diff * diff
            
        std_dev = np.sqrt(sum_diff_sq / length)
        df.loc[df.index[i], 'std_dev'] = std_dev
    
    # 채널 밴드 계산
    multiplier = 3
    df['upper_band'] = df['middle_line'] + multiplier * df['std_dev']
    df['lower_band'] = df['middle_line'] - multiplier * df['std_dev']
    
    # 추세 지속성 계산
    df['trend_duration'] = 0
    current_duration = 0
    
    for i in range(len(df)):
        is_uptrend = df['slope'].iloc[i] >= 0
        is_downtrend = df['slope'].iloc[i] < 0
        
        if i == 0:
            current_duration = 1 if is_uptrend else -1
        else:
            prev_duration = df['trend_duration'].iloc[i-1]
            if is_uptrend:
                current_duration = (prev_duration + 1) if prev_duration >= 0 else 1
            elif is_downtrend:
                current_duration = (prev_duration - 1) if prev_duration <= 0 else -1
            else:
                current_duration = 0
                
        df.loc[df.index[i], 'trend_duration'] = current_duration



    return df


if __name__ == "__main__":


    set_timevalue = '5m'
    period = 700  # 전체 데이터 수
    start_from = 207  # 과거 n번째 데이터 (뒤에서부터)
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
        
        # from strategy.supertrend import supertrend

        # df = supertrend(df)
        # from strategy.volume_norm import check_VSTG_signal
        # position = check_VSTG_signal(df)
        
        from strategy.line_reg import check_line_reg_signal
        position = check_line_reg_signal(df)
        print(f'시간 : {df.tail(1).index[0]}, 포지션 :  {position}')
        pass
