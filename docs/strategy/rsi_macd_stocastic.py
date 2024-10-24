def r_m_s(data):
    position = None

    # 트리거 플래그 초기화
    first_trigger_active = False
    second_trigger_active = False

    # 마지막 행 데이터를 사용
    row = data.tail(1).iloc[0]

    # 첫 번째 트리거: Stochastic %K와 %D가 20 이하일 때 (과매도 구간)
    if row['stoch_k'] < 20 and row['stoch_d'] < 20:
        first_trigger_active = True

    # 두 번째 트리거: RSI가 50을 돌파할 때
    if first_trigger_active and row['rsi'] > 50:
        second_trigger_active = True

    # 세 번째 트리거: MACD가 상승 추세로 진입할 때 (Long 포지션)
    if second_trigger_active:
        # 과매수 상태에서 트리거 초기화
        if row['stoch_k'] > 80 and row['stoch_d'] > 80:
            first_trigger_active = False
            second_trigger_active = False

        # MACD와 거래량 조건 충족 시 Long 포지션 진입
        if row['macd'] > row['macd_signal'] and row['volume'] > row['volume_Avg30']:
            position = 'Long'
            first_trigger_active = False
            second_trigger_active = False

    # 숏 포지션 준비: Stochastic %K와 %D가 80 이상일 때 (과매수 구간)
    elif row['stoch_k'] > 80 and row['stoch_d'] > 80:
        first_trigger_active = True

    # 숏 포지션 두 번째 트리거: RSI가 50 아래로 내려갈 때
    if first_trigger_active and row['rsi'] < 50:
        second_trigger_active = True

    # 세 번째 트리거: MACD가 하락 추세일 때 (Short 포지션)
    if second_trigger_active:
        # 과매도 상태에서 트리거 초기화
        if row['stoch_k'] < 20 and row['stoch_d'] < 20:
            first_trigger_active = False
            second_trigger_active = False

        # MACD와 거래량 조건 충족 시 Short 포지션 진입
        if row['macd'] < row['macd_signal'] and row['volume'] > row['volume_Avg30']:
            position = 'Short'
            first_trigger_active = False
            second_trigger_active = False

    return position
