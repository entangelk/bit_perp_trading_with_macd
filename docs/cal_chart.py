import pandas as pd
import ta  # 기술적 지표 라이브러리
import numpy as np

def process_chart_data(df):

    STG_CONFIG = {
        'MACD_SIZE': {
            'STG_No' : 1,
            'MACD_FAST_LENGTH': 12,
            'MACD_SLOW_LENGTH': 17,
            'MACD_SIGNAL_LENGTH': 20,
            'SIZE_RATIO_THRESHOLD': 1.4,
            'DI_LENGTH': 18,
            'DI_SLOPE_LENGTH': 9,
            'MIN_SLOPE_THRESHOLD': 13,
            'REQUIRED_CONSECUTIVE_CANDLES': 2
        },
        'MACD_DIVE': {
            'STG_No' : 2,
            'FAST_LENGTH': 11,
            'SLOW_LENGTH': 27,
            'SIGNAL_LENGTH': 12,
            'HISTOGRAM_UPPER_LIMIT': 60,
            'HISTOGRAM_LOWER_LIMIT': -60,
            'LOOKBACK_PERIOD': 2,
            'PRICE_MOVEMENT_THRESHOLD': 0.01
        },
        'SUPERTREND': {
            'STG_No' : 3,
            'ATR_PERIOD': 30,
            'ATR_MULTIPLIER': 6,
            'ADX_LENGTH': 14,
            'DI_DIFFERENCE_FILTER': 8,
            'DI_DIFFERENCE_LOOKBACK_PERIOD': 6
        },
        'LINEAR_REG': {
            'STG_No' : 4,
            'LENGTH': 100,
            'RSI_LENGTH': 14,
            'RSI_LOWER_BOUND': 40,
            'RSI_UPPER_BOUND': 60,
            'MIN_BOUNCE_BARS': 4,
            'UPPER_MULTIPLIER': 3,
            'LOWER_MULTIPLIER': 3,
            'MIN_SLOPE_VALUE': 6,
            'MIN_TREND_DURATION': 50
        },
        'MACD_DI_SLOPE': {
            'STG_No' : 5,
            'FAST_LENGTH': 12,
            'SLOW_LENGTH': 26,
            'SIGNAL_LENGTH': 8,
            'DI_LENGTH': 14,
            'SLOPE_LENGTH': 3,
            'RSI_LENGTH': 14,
            'RSI_UPPER_BOUND': 60,
            'RSI_LOWER_BOUND': 40,
            'MIN_SLOPE_THRESHOLD': 6,
            'REQUIRED_CONSECUTIVE_SIGNALS': 5
        },
        'VOLUME_TREND': {
            'STG_No' : 6,
            'VOLUME_MA_LENGTH': 9,
            'TREND_PERIOD': 11,
            'SIGNAL_THRESHOLD': 0.2,
            'NORM_PERIOD' : 100
        }
    }


    # 함수 및 공통 계산 부분
        # SMA 초기값을 사용하는 EMA 함수
    def ema_with_sma_init(series, period):
        sma = series.rolling(window=period, min_periods=period).mean()
        ema = series.ewm(span=period, adjust=False).mean()
        ema[:period] = sma[:period]  # 초기값을 SMA로 설정
        return ema
    
    # RMA 함수 정의
    def rma(series, period):
        alpha = 1/period
        return series.ewm(alpha=alpha, adjust=False).mean()

    def wilder_smoothing(series, period):
        # 첫 번째 유효한 값의 위치를 찾는 부분
        first_valid_idx = series.first_valid_index()
        if first_valid_idx is None:
            return pd.Series(index=series.index)
        
        # get_loc 결과 타입 체크 및 처리
        first_valid_loc = series.index.get_loc(first_valid_idx)
        if not isinstance(first_valid_loc, (int, np.integer)):
            first_valid_loc = series.reset_index(drop=True).first_valid_index()
            if first_valid_loc is None:
                first_valid_loc = 0
        
        smoothed = []
        smoothed.extend([np.nan] * first_valid_loc)
        smoothed.append(series[first_valid_idx])
        
        # Wilder's smoothing 계산 부분 수정
        for i in range(first_valid_loc + 1, len(series)):
            prev_value = smoothed[i-1]
            current_value = series.iloc[i]
            
            if np.isnan(prev_value):  # numpy의 isnan 사용
                smoothed.append(current_value)
            elif np.isnan(current_value):
                smoothed.append(prev_value)
            else:
                smoothed.append((prev_value * (period - 1) + current_value) / period)
        
        return pd.Series(smoothed, index=series.index)
    
    # ATR 계산
    df['TR'] = np.maximum(df['high'] - df['low'], 
                        np.maximum(abs(df['high'] - df['close'].shift(1)), 
                                    abs(df['low'] - df['close'].shift(1))))

    df['TR'] = df['TR'].fillna(0)


    # Directional Movement (DM+ 및 DM-) 계산
    df['DM+'] = np.where((df['high'] - df['high'].shift(1)) > (df['low'].shift(1) - df['low']),
                        np.maximum(df['high'] - df['high'].shift(1), 0), 0)
    df['DM-'] = np.where((df['low'].shift(1) - df['low']) > (df['high'] - df['high'].shift(1)),
                        np.maximum(df['low'].shift(1) - df['low'], 0), 0)

    # 동시 활성화 방지
    df.loc[df['DM+'] > 0, 'DM-'] = 0
    df.loc[df['DM-'] > 0, 'DM+'] = 0
    df[['DM+', 'DM-']] = df[['DM+', 'DM-']].fillna(0)


    ''' 여기서부터 계산 부분 '''

    # STG_No1 - MACD_SIZE 전략
    df['EMA_fast_stg1'] = ema_with_sma_init(df['close'], STG_CONFIG['MACD_SIZE']['MACD_FAST_LENGTH'])
    df['EMA_slow_stg1'] = ema_with_sma_init(df['close'], STG_CONFIG['MACD_SIZE']['MACD_SLOW_LENGTH'])
    df['macd_stg1'] = df['EMA_fast_stg1'] - df['EMA_slow_stg1']
    df['macd_signal_stg1'] = ema_with_sma_init(df['macd_stg1'], STG_CONFIG['MACD_SIZE']['MACD_SIGNAL_LENGTH'])
    df['hist_stg1'] = df['macd_stg1'] - df['macd_signal_stg1']

        ## MACD Size 계산부분
    df['hist_size'] = abs(df['hist_stg1'])
    df['candle_size'] = abs(df['close'] - df['open'])
    df['candle_size_ma'] = df['candle_size'].rolling(window=STG_CONFIG['MACD_SIZE']['MACD_SLOW_LENGTH']).mean()
    df['normalized_candle_size'] = df['candle_size'] / df['candle_size_ma']
    df['hist_size_ma'] = df['hist_size'].rolling(window=STG_CONFIG['MACD_SIZE']['MACD_SLOW_LENGTH']).mean()
    df['normalized_hist_size'] = df['hist_size'] / df['hist_size_ma']


    df['Smoothed_TR_stg1'] = wilder_smoothing(df['TR'], STG_CONFIG['MACD_SIZE']['DI_LENGTH'])
    df['Smoothed_DM+_stg1'] = wilder_smoothing(df['DM+'], STG_CONFIG['MACD_SIZE']['DI_LENGTH'])
    df['Smoothed_DM-_stg1'] = wilder_smoothing(df['DM-'], STG_CONFIG['MACD_SIZE']['DI_LENGTH'])
    
    df['DI+_stg1'] = 100 * (df['Smoothed_DM+_stg1'] / df['Smoothed_TR_stg1'])
    df['DI-_stg1'] = 100 * (df['Smoothed_DM-_stg1'] / df['Smoothed_TR_stg1'])
    
        # DI Slopes
    df['DIPlus_stg1'] = df['DI+_stg1'] - df['DI+_stg1'].shift(STG_CONFIG['MACD_SIZE']['DI_SLOPE_LENGTH'])
    df['DIMinus_stg1'] = df['DI-_stg1'] - df['DI-_stg1'].shift(STG_CONFIG['MACD_SIZE']['DI_SLOPE_LENGTH'])


    ''' STG_No1 MACD_SIZE 계산 끝'''


    # STG_No2 - MACD_DIVE 전략
    df['EMA_fast_stg2'] = ema_with_sma_init(df['close'], STG_CONFIG['MACD_DIVE']['FAST_LENGTH'])
    df['EMA_slow_stg2'] = ema_with_sma_init(df['close'], STG_CONFIG['MACD_DIVE']['SLOW_LENGTH'])
    df['macd_stg2'] = df['EMA_fast_stg2'] - df['EMA_slow_stg2']
    df['macd_signal_stg2'] = ema_with_sma_init(df['macd_stg2'], STG_CONFIG['MACD_DIVE']['SIGNAL_LENGTH'])
    df['hist_stg2'] = df['macd_stg2'] - df['macd_signal_stg2']
    
        # === MACD dive 방향 ===
    df['hist_direction_dive'] = df['hist_stg2'] - df['hist_stg2'].shift(1)

    ''' STG_No2 MACD_DIVE 계산 끝'''



    # STG_No3 - SUPERTREND 전략
    df['atr_stg3'] = rma(df['TR'], STG_CONFIG['SUPERTREND']['ATR_PERIOD'])  # RMA로 변경

    df['Smoothed_TR_stg3'] = wilder_smoothing(df['TR'], STG_CONFIG['SUPERTREND']['ADX_LENGTH'])
    df['Smoothed_DM+_stg3'] = wilder_smoothing(df['DM+'], STG_CONFIG['SUPERTREND']['ADX_LENGTH'])
    df['Smoothed_DM-_stg3'] = wilder_smoothing(df['DM-'], STG_CONFIG['SUPERTREND']['ADX_LENGTH'])

    # DI+ 및 DI- 계산
    df['DI+_stg3'] = 100 * (df['Smoothed_DM+_stg3'] / df['Smoothed_TR_stg3'])
    df['DI-_stg3'] = 100 * (df['Smoothed_DM-_stg3'] / df['Smoothed_TR_stg3'])

    ''' STG_No3 SUPERTREND 계산 끝'''


    # STG_No4 - LINEAR_REG 전략

    length = STG_CONFIG['LINEAR_REG']['LENGTH']
    
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
    up_multiplier = STG_CONFIG['LINEAR_REG']['UPPER_MULTIPLIER']
    lw_multiplier = STG_CONFIG['LINEAR_REG']['LOWER_MULTIPLIER']
    df['upper_band'] = df['middle_line'] + up_multiplier * df['std_dev']
    df['lower_band'] = df['middle_line'] - lw_multiplier * df['std_dev']
    
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


    rsi_length = STG_CONFIG['LINEAR_REG']['RSI_LENGTH']
    df['rsi_stg4'] = ta.momentum.rsi(df['close'], window=rsi_length).fillna(50)

    ''' STG_No4 LINEAR_REG 계산 끝 '''

    # STG_No5 MACD_DI_SLOPE 전략
    df['EMA_fast_stg5'] = ema_with_sma_init(df['close'], STG_CONFIG['MACD_DI_SLOPE']['FAST_LENGTH'])
    df['EMA_slow_stg5'] = ema_with_sma_init(df['close'], STG_CONFIG['MACD_DI_SLOPE']['SLOW_LENGTH'])
    df['macd_stg5'] = df['EMA_fast_stg5'] - df['EMA_slow_stg5']
    df['macd_signal_stg5'] = ema_with_sma_init(df['macd_stg5'], STG_CONFIG['MACD_DI_SLOPE']['SIGNAL_LENGTH'])
    df['hist_stg5'] = df['macd_stg5'] - df['macd_signal_stg5']
    
    # === MACD dive 방향 ===
    df['hist_direction_stg5'] = df['hist_stg5'] - df['hist_stg5'].shift(1)


    df['Smoothed_TR_stg5'] = wilder_smoothing(df['TR'], STG_CONFIG['MACD_DI_SLOPE']['DI_LENGTH'])
    df['Smoothed_DM+_stg5'] = wilder_smoothing(df['DM+'], STG_CONFIG['MACD_DI_SLOPE']['DI_LENGTH'])
    df['Smoothed_DM-_stg5'] = wilder_smoothing(df['DM-'], STG_CONFIG['MACD_DI_SLOPE']['DI_LENGTH'])

    # DI+ 및 DI- 계산
    df['DI+_stg5'] = 100 * (df['Smoothed_DM+_stg5'] / df['Smoothed_TR_stg5'])
    df['DI-_stg5'] = 100 * (df['Smoothed_DM-_stg5'] / df['Smoothed_TR_stg5'])

    # === 두 번째 전략의 DI Slope (slope_len=3) ===
    df['DIPlus_stg5'] = df['DI+_stg5'] - df['DI+_stg5'].shift(STG_CONFIG['MACD_DI_SLOPE']['SLOPE_LENGTH'])
    df['DIMinus_stg5'] = df['DI-_stg5'] - df['DI-_stg5'].shift(STG_CONFIG['MACD_DI_SLOPE']['SLOPE_LENGTH'])
    df['slope_diff_stg5'] = df['DIPlus_stg5'] - df['DIMinus_stg5']
    
    # RSI (Relative Strength Index)
    rsi_length = STG_CONFIG['MACD_DI_SLOPE']['RSI_LENGTH']
    df['rsi_stg5'] = ta.momentum.rsi(df['close'], window=rsi_length).fillna(50)

    ''' STG_No5 MACD_DI_SLPOE 계산 끝'''



    # STG_No6 VOLUME_TREND 전략

    vol_length = STG_CONFIG['VOLUME_TREND']['VOLUME_MA_LENGTH']
    trend_length = STG_CONFIG['VOLUME_TREND']['TREND_PERIOD']
    norm_period = STG_CONFIG['VOLUME_TREND']['NORM_PERIOD']
    
    
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




    # 불필요한 중간 계산 컬럼 제거
    try:
        columns_to_drop = ['TR', 'DM+', 'DM-', 'Smoothed_TR_stg1', 'Smoothed_DM+_stg1', 'Smoothed_DM-_stg1','Smoothed_TR_stg3', 'Smoothed_DM+_stg3', 'Smoothed_DM-_stg3']
        df.drop(columns=columns_to_drop, inplace=True)
    except Exception as e:
        print(f"컬럼 지우기 오류 발생: {e}")
    
    return df, STG_CONFIG


if __name__ == "__main__":


    set_timevalue = '5m'
    period = 700  # 전체 데이터 수
    start_from = 109  # 과거 n번째 데이터 (뒤에서부터)
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

        df, STG_CONFIG = process_chart_data(df)
        
        # from strategy.supertrend import supertrend

        # df = supertrend(df)
        # from strategy.volume_norm import check_VSTG_signal
        # position = check_VSTG_signal(df)
        
        # from strategy.line_reg import check_line_reg_signal
        # position = check_line_reg_signal(df)
        # print(f'시간 : {df.tail(1).index[0]}, 포지션 :  {position}')

        from strategy.macd_divergence import generate_macd_dive_signal
        position = generate_macd_dive_signal(df,STG_CONFIG)
        
        pass
