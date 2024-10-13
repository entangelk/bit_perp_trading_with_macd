from pymongo import MongoClient
import pandas as pd
import ta  # 기술적 지표 라이브러리

def process_chart_data(chart_collection, timeframe_name):
    # 최신 데이터 200개만 가져오기 (timestamp 내림차순 정렬)
    data_cursor = chart_collection.find().sort("timestamp", -1).limit(200)

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

    # 열 이름 확인 (예: ['close', 'high', 'low', 'open', 'volume'])
    print(f"{timeframe_name} 데이터 컬럼명:", df.columns)

    # 1. MACD (Moving Average Convergence Divergence)
    df['macd'] = ta.trend.macd(df['close'])
    df['macd_signal'] = ta.trend.macd_signal(df['close'])
    df['macd_diff'] = ta.trend.macd_diff(df['close'])

    # 2. RSI (Relative Strength Index)
    df['rsi'] = ta.momentum.rsi(df['close'])

    # 3. Bollinger Bands (볼린저 밴드)
    df['bb_high'] = ta.volatility.bollinger_hband(df['close'])
    df['bb_low'] = ta.volatility.bollinger_lband(df['close'])
    df['bb_mavg'] = ta.volatility.bollinger_mavg(df['close'])

    # 4. Stochastic Oscillator (스토캐스틱 오실레이터)
    df['stoch_k'] = ta.momentum.stoch(df['high'], df['low'], df['close'])
    df['stoch_d'] = ta.momentum.stoch_signal(df['high'], df['low'], df['close'])

    # 지표 계산 후 NaN 값 여부 확인
    print(f"\n{timeframe_name} 지표 계산 후 NaN 값 여부 확인:")
    print(df[['macd', 'macd_signal', 'macd_diff', 'rsi', 'bb_high', 'bb_low', 'bb_mavg', 'stoch_k', 'stoch_d']].isna().sum())

    # 지표 출력 (마지막 5개)
    print(f"\n{timeframe_name} MACD, RSI, Bollinger Bands, Stochastic (마지막 5개):")
    print(df[['macd', 'macd_signal', 'macd_diff', 'rsi', 'bb_high', 'bb_low', 'bb_mavg', 'stoch_k', 'stoch_d']].tail())

    return df

def cal_chart():
    # MongoDB에 접속
    mongoClient = MongoClient("mongodb://localhost:27017")
    # 'bitcoin' 데이터베이스 연결
    database = mongoClient["bitcoin"]

    # 'chart_1m', 'chart_5m', 'chart_15m', 'chart_1h', 'chart_30d' 컬렉션 작업
    chart_collection_1m = database['chart_1m']
    chart_collection_5m = database['chart_5m']
    chart_collection_15m = database['chart_15m']
    chart_collection_1h = database['chart_1h']
    chart_collection_30d = database['chart_30d']


    # 각각의 봉 데이터에 대해 처리
    df_1m = process_chart_data(chart_collection_1m, '1분봉')
    df_5m = process_chart_data(chart_collection_5m, '5분봉')
    df_15m = process_chart_data(chart_collection_15m, '15분봉')
    df_1h = process_chart_data(chart_collection_1h, '1시간봉')
    df_30d = process_chart_data(chart_collection_30d, '1일봉')

    pass
    # 각각의 데이터프레임 반환
    return df_1m, df_5m, df_15m, df_1h, df_30d
