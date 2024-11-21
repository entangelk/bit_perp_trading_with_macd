def calculate_follow_line(df, UseATRfilter=True):
    # Follow Line 계산
    if df['close'].iloc[-1] > df['BBUpper'].iloc[-1]:  # 상한선 돌파
        FollowLine = (
            df['low'].iloc[-1] - df['atr'].iloc[-1] if UseATRfilter else df['low'].iloc[-1]
        )
        trend = 1  # 상승 추세
    elif df['close'].iloc[-1] < df['BBLower'].iloc[-1]:  # 하한선 돌파
        FollowLine = (
            df['high'].iloc[-1] + df['atr'].iloc[-1] if UseATRfilter else df['high'].iloc[-1]
        )
        trend = -1  # 하락 추세
    else:
        FollowLine = None  # 범위 내 움직임 (추세 없음)
        trend = 0

    # 매수 및 매도 신호
    buy = (trend == 1)
    sell = (trend == -1)

    # 결과 출력
    if buy:
        return 'Long'
    elif sell:
        return "Short"
    else:
        return None
