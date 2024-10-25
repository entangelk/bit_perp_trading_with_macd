# Three Bar Reversal Pattern
# https://kr.tradingview.com/v/ct5E4FSn/

# Moving Average Cloud 기반의 Three Bar Reversal 포지션 계산 함수
def three_bar_ma(df):
    position = None

    # 최소 데이터가 3개 이상일 때만 실행 (shift(2)를 안전하게 사용하기 위함)
    if len(df) < 3:
        return position

    # 1. Moving Average Cloud
    C_UpTrend_ma = df['maFast'] > df['maSlow']  # 상승 추세
    C_DownTrend_ma = df['maFast'] < df['maSlow']  # 하락 추세

    # 3-Bar Reversal Pattern (마지막 틱)
    bullish_reversal = (
        (df['close'].shift(2).iloc[-1] < df['open'].shift(2).iloc[-1]) &
        (df['low'].shift(1).iloc[-1] < df['low'].shift(2).iloc[-1]) &
        (df['high'].shift(1).iloc[-1] < df['high'].shift(2).iloc[-1]) &
        (df['close'].shift(1).iloc[-1] < df['open'].shift(1).iloc[-1]) &
        (df['close'].iloc[-1] > df['open'].iloc[-1]) &
        (df['high'].iloc[-1] > df['high'].shift(2).iloc[-1])
    )

    bearish_reversal = (
        (df['close'].shift(2).iloc[-1] > df['open'].shift(2).iloc[-1]) &
        (df['high'].shift(1).iloc[-1] > df['high'].shift(2).iloc[-1]) &
        (df['low'].shift(1).iloc[-1] > df['low'].shift(2).iloc[-1]) &
        (df['close'].shift(1).iloc[-1] > df['open'].shift(1).iloc[-1]) &
        (df['close'].iloc[-1] < df['open'].iloc[-1]) &
        (df['low'].iloc[-1] < df['low'].shift(2).iloc[-1])
    )

    # 트렌드를 개별적으로 처리
    if C_UpTrend_ma.iloc[-1]:
        if bullish_reversal:
            position = 'Long'  # 상승 추세에서 반전 감지
        else:
            position = 'No Position'  # 상승 추세이나 반전 패턴 없음
    elif C_DownTrend_ma.iloc[-1]:
        if bearish_reversal:
            position = 'Short'  # 하락 추세에서 반전 감지
        else:
            position = 'No Position'  # 하락 추세이나 반전 패턴 없음

    return position


# Donchian Channels 기반의 Three Bar Reversal 포지션 계산 함수
def three_bar_donchian(df):
    position = None

    # 최소 데이터가 3개 이상일 때만 실행 (shift(2)를 안전하게 사용하기 위함)
    if len(df) < 3:
        return position

    # 2. Donchian Channels Trend
    C_UpTrend_donchian = df['close'] > df['lower']  # Donchian Channels 상승 추세
    C_DownTrend_donchian = df['close'] < df['upper']  # Donchian Channels 하락 추세

    # 3-Bar Reversal Pattern (마지막 틱)
    bullish_reversal = (
        (df['close'].shift(2).iloc[-1] < df['open'].shift(2).iloc[-1]) &
        (df['low'].shift(1).iloc[-1] < df['low'].shift(2).iloc[-1]) &
        (df['high'].shift(1).iloc[-1] < df['high'].shift(2).iloc[-1]) &
        (df['close'].shift(1).iloc[-1] < df['open'].shift(1).iloc[-1]) &
        (df['close'].iloc[-1] > df['open'].iloc[-1]) &
        (df['high'].iloc[-1] > df['high'].shift(2).iloc[-1])
    )

    bearish_reversal = (
        (df['close'].shift(2).iloc[-1] > df['open'].shift(2).iloc[-1]) &
        (df['high'].shift(1).iloc[-1] > df['high'].shift(2).iloc[-1]) &
        (df['low'].shift(1).iloc[-1] > df['low'].shift(2).iloc[-1]) &
        (df['close'].shift(1).iloc[-1] > df['open'].shift(1).iloc[-1]) &
        (df['close'].iloc[-1] < df['open'].iloc[-1]) &
        (df['low'].iloc[-1] < df['low'].shift(2).iloc[-1])
    )

    # 트렌드를 개별적으로 처리
    if C_UpTrend_donchian.iloc[-1]:
        if bullish_reversal:
            position = 'Long'  # 상승 추세에서 반전 감지
        else:
            position = 'No Position'  # 상승 추세이나 반전 패턴 없음
    elif C_DownTrend_donchian.iloc[-1]:
        if bearish_reversal:
            position = 'Short'  # 하락 추세에서 반전 감지
        else:
            position = 'No Position'  # 하락 추세이나 반전 패턴 없음

    return position
















