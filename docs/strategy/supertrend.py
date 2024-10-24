def supertrend(df):
    position = None  # 초기 포지션 값을 None으로 설정
    trend = 1  # 기본적으로 상승 추세로 시작

    # Supertrend 신호 구별
    for i in range(1, len(df)):
        # 트렌드 계산: 이전 값과 현재 값 비교하여 추세 판단
        if df['close'].iloc[i-1] > df['dn'].iloc[i-1]:
            current_trend = 1  # 상승 추세
        elif df['close'].iloc[i-1] < df['up'].iloc[i-1]:
            current_trend = -1  # 하락 추세
        else:
            current_trend = trend  # 이전 추세 유지

        # 롱 포지션 신호: 하락에서 상승으로 전환
        if trend == -1 and current_trend == 1:
            position = 'Long'
        # 숏 포지션 신호: 상승에서 하락으로 전환
        elif trend == 1 and current_trend == -1:
            position = 'Short'

        # 현재 트렌드를 다음 루프에서 사용할 수 있도록 업데이트
        trend = current_trend

    return position
