def flow_line(df, UseATRfilter=True):
    position = None  # 초기 포지션 설정
    previous_follow_line = None  # 이전 Follow Line 값

    for i in range(1, len(df)):
        BBSignal = 0
        
        # Bollinger Bands 상한선 및 하한선 비교
        if df['close'].iloc[i] > df['BBUpper'].iloc[i]:
            BBSignal = 1  # 상한선 돌파 시 상승 신호
        elif df['close'].iloc[i] < df['BBLower'].iloc[i]:
            BBSignal = -1  # 하한선 하락 시 하락 신호

        # Follow Line 계산
        follow_line_value = None
        if BBSignal == 1:  # 매수 신호 처리
            follow_line_value = df['low'].iloc[i] - df['atr_200'].iloc[i] if UseATRfilter else df['low'].iloc[i]
        elif BBSignal == -1:  # 매도 신호 처리
            follow_line_value = df['high'].iloc[i] + df['atr_200'].iloc[i] if UseATRfilter else df['high'].iloc[i]


        # 추세 방향 결정 및 신호 반환
        if previous_follow_line is not None and follow_line_value is not None:
            if follow_line_value > previous_follow_line:
                if BBSignal == 1:
                    position = 'Long'
            elif follow_line_value < previous_follow_line:
                if BBSignal == -1:
                    position = 'Short'

        # 이전 Follow Line 값을 업데이트
        if follow_line_value is not None:
            previous_follow_line = follow_line_value

    return position
