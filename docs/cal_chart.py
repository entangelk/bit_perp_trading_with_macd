import pandas as pd
import ta  # 기술적 지표 라이브러리

def process_chart_data(chart_collection):
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

    # 5. Volume 30-period moving average (volume_Avg30)
    df['volume_Avg30'] = df['volume'].rolling(window=30).mean()

    # 추가 지표: Zero-Lag Moving Average (ZLMA)
    length = 15  # ZLMA에서 사용할 기간 (필요 시 변경 가능)
    df['ema'] = ta.trend.ema_indicator(df['close'], window=length)
    correction = df['close'] + (df['close'] - df['ema'])
    df['zlma'] = ta.trend.ema_indicator(correction, window=length)

    # ATR(10-period) 및 ATR(200-period) 계산
    df['atr_10'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=10)
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

    # 7. Donchian 채널 계산
    dcLength = 13
    df['upper'] = df['high'].rolling(window=dcLength).max()
    df['lower'] = df['low'].rolling(window=dcLength).min()

    # 8. Supertrend 계산 (10-period ATR 사용)
    factor = 3.0

    df['hl2'] = (df['high'] + df['low']) / 2
    df['up'] = df['hl2'] - (factor * df['atr_10'])  # 10-period ATR 사용
    df['dn'] = df['hl2'] + (factor * df['atr_10'])  # 10-period ATR 사용

    return df
