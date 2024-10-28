import pandas as pd

def trendline_breakout_strategy(df, threshold=0.02):
    signals = []
    resistance_level = None

    for i in range(1, len(df)):
        current_close = df['close'].iloc[i]
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]

        # 트렌드라인 형성 확인 (횡보 구간)
        if resistance_level is None:
            # 과거 데이터로 저항선 설정
            recent_highs = df['high'].iloc[:i]
            resistance_level = recent_highs.max()

        # 돌파 조건
        if current_close > resistance_level * (1 + threshold):  # 예: 2% 이상 돌파 시
            signals.append((df['date'].iloc[i], 'Buy', current_close))
            # 돌파 후 저항선 업데이트
            resistance_level = current_high

    return signals
