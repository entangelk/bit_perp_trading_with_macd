def supertrend(df, prev_position=None):
    # 최신 데이터 기준으로 추세 판단
    if df['close'].iloc[-1] > df['dn'].iloc[-1]:
        position = 'Long'  # 상승 추세
    elif df['close'].iloc[-1] < df['up'].iloc[-1]:
        position = 'Short'  # 하락 추세
    else:
        position = prev_position if prev_position else None  # 이전 추세 유지 또는 초기화

    # # 디버깅 출력
    # print(f"Close[-1]: {df['close'].iloc[-1]}, DN[-1]: {df['dn'].iloc[-1]}, UP[-1]: {df['up'].iloc[-1]}")
    # print(f"Position: {position}")

    return position
