# Three Bar Reversal Pattern
# https://kr.tradingview.com/v/ct5E4FSn/

def three_bar(df):
    position = None
    C_UpTrend = C_DownTrend = None
    
    trendFilt = "Aligned"
    if trendFilt == 'Aligned':
        C_DownTrend = (df['close'] < df['maFast']) & (df['maFast'] < df['maSlow'])
        C_UpTrend = (df['close'] > df['maFast']) & (df['maFast'] > df['maSlow'])
    elif trendFilt == 'Opposite':
        C_DownTrend = (df['close'] > df['maFast']) & (df['maFast'] > df['maSlow'])
        C_UpTrend = (df['close'] < df['maFast']) & (df['maFast'] < df['maSlow'])

    # Bullish Reversal Pattern
    bullish_reversal = (
        (df['close'].shift(2) < df['open'].shift(2)) &
        (df['low'].shift(1) < df['low'].shift(2)) &
        (df['high'].shift(1) < df['high'].shift(2)) &
        (df['close'].shift(1) < df['open'].shift(1)) &
        (df['close'] > df['open']) &
        (df['high'] > df['high'].shift(2))
    ) & C_UpTrend

    # Bearish Reversal Pattern
    bearish_reversal = (
        (df['close'].shift(2) > df['open'].shift(2)) &
        (df['high'].shift(1) > df['high'].shift(2)) &
        (df['low'].shift(1) > df['low'].shift(2)) &
        (df['close'].shift(1) > df['open'].shift(1)) &
        (df['close'] < df['open']) &
        (df['low'] < df['low'].shift(2))
    ) & C_DownTrend

    # 디버깅: 패턴 감지 여부 확인
    if bullish_reversal.any():
        print("Bullish Reversal Detected")
        position = 'Long'
    elif bearish_reversal.any():
        print("Bearish Reversal Detected")
        position = 'Short'
    
    return position
