import pandas as pd
import ta  # 기술적 지표 라이브러리
from pymongo import MongoClient
import numpy as np

def process_chart_data(set_timevalue):

    # MongoDB에 접속
    mongoClient = MongoClient("mongodb://mongodb:27017")
    database = mongoClient["bitcoin"]

    # set_timevalue 값에 따라 적절한 차트 컬렉션 선택
    if set_timevalue == '1m':
        chart_collection = database['chart_1m']
    elif set_timevalue == '3m':
        chart_collection = database['chart_3m']
    elif set_timevalue == '5m':
        chart_collection = database["chart_5m"]
    elif set_timevalue == '15m':
        chart_collection = database['chart_15m']
    elif set_timevalue == '1h':
        chart_collection = database['chart_1h']
    elif set_timevalue == '30d':  # 30일을 분 단위로 계산 (30일 * 24시간 * 60분)
        chart_collection = database['chart_30d']
    else:
        raise ValueError(f"Invalid time value: {set_timevalue}")




    # 최신 데이터 200개만 가져오기 (timestamp 내림차순 정렬)
    data_cursor = chart_collection.find().sort("timestamp", -1).limit(300)

    # MongoDB 데이터 DataFrame으로 변환
    data_list = list(data_cursor)
    df = pd.DataFrame(data_list)

    # 타임스탬프를 datetime 형식으로 변환
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # 불필요한 ObjectId 필드 제거
    if '_id' in df.columns:
        df.drop('_id', axis=1, inplace=True)

    # 인덱스를 타임스탬프로 설정
    df.set_index('timestamp', inplace=True)

    # 시간순으로 정렬 (오름차순)
    df.sort_index(inplace=True)

    # 1. MACD (Moving Average Convergence Divergence)
    df['macd'] = ta.trend.macd(df['close'])
    df['macd_signal'] = ta.trend.macd_signal(df['close'])
    df['macd_diff'] = ta.trend.macd_diff(df['close'])


    # 1++ MACD stragy 용 계산 (사용자 정의 파라미터 적용)

    fast_length=4
    slow_length=100
    macd_length=21

    df['macd_stg'] = ta.trend.ema_indicator(df['close'], window=fast_length) - ta.trend.ema_indicator(df['close'], window=slow_length)
    df['macd_signal_stg'] = ta.trend.ema_indicator(df['macd'], window=macd_length)
    df['macd_diff_stg'] = df['macd'] - df['macd_signal']

    # 2. RSI (Relative Strength Index)
    df['rsi'] = ta.momentum.rsi(df['close'])

    # RSI의 21기간 SMA
    rsi_period = 21
    df['rsi_sma'] = df['rsi'].rolling(window=rsi_period).mean()

    # ATR(10-period) 및 ATR(200-period) 계산
    df['atr_10'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=10)
    df['atr_100'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=100)
    df['atr_200'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=200)

    # Follow Line 계산을 위한 Bollinger Bands 추가 계산
    BBperiod = 21  # 기본 설정 값, 필요 시 변경 가능
    BBdeviation = 1.00  # 기본 편차 값
    df['BBUpper'] = ta.trend.sma_indicator(df['close'], window=BBperiod) + df['close'].rolling(window=BBperiod).std() * BBdeviation
    df['BBLower'] = ta.trend.sma_indicator(df['close'], window=BBperiod) - df['close'].rolling(window=BBperiod).std() * BBdeviation

    # 6. 이동 평균 (Moving Average Cloud)
    maFLength = 50  # Fast MA
    maSLength = 200  # Slow MA
    df['maFast'] = ta.trend.sma_indicator(df['close'], maFLength)
    df['maSlow'] = ta.trend.sma_indicator(df['close'], maSLength)

    # 7. ADX, DI+ 및 DI- 계산
    adx_period = 14
    df['TR'] = np.maximum(df['high'] - df['low'], 
                          np.maximum(abs(df['high'] - df['close'].shift(1)), 
                                     abs(df['low'] - df['close'].shift(1))))
    df['DM+'] = np.where((df['high'] - df['high'].shift(1)) > (df['low'].shift(1) - df['low']),
                         np.maximum(df['high'] - df['high'].shift(1), 0), 0)
    df['DM-'] = np.where((df['low'].shift(1) - df['low']) > (df['high'] - df['high'].shift(1)),
                         np.maximum(df['low'].shift(1) - df['low'], 0), 0)

    df['ATR'] = df['TR'].rolling(window=adx_period, min_periods=1).mean()
    df['DI+'] = 100 * (df['DM+'].rolling(window=adx_period, min_periods=1).mean() / df['ATR'])
    df['DI-'] = 100 * (df['DM-'].rolling(window=adx_period, min_periods=1).mean() / df['ATR'])

    df['DX'] = 100 * abs(df['DI+'] - df['DI-']) / (df['DI+'] + df['DI-'])
    df['ADX'] = df['DX'].rolling(window=adx_period, min_periods=1).mean()

    # 필요없는 중간 계산 열 삭제
    df.drop(columns=['TR', 'DM+', 'DM-', 'DX'], inplace=True)

    length = 1
    df['ema'] = ta.trend.ema_indicator(df['close'], window=length)

    return df
