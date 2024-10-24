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


    return df
