def adx_di_signal(df):
    """
    DI+와 DI-의 교차 시 신호를 생성합니다.
    - DI+가 DI-를 상향 돌파(교차)하고 ADX 값이 DI+와 DI- 값보다 낮으면 'Long',
    - DI+가 DI-를 하향 돌파(교차)하고 ADX 값이 DI+와 DI- 값보다 낮으면 'Short',
    - DI+와 DI-의 교차 시 ADX 값이 DI+와 DI- 값보다 높으면 'Reset' 신호를 반환합니다.
    신호가 없으면 None을 반환합니다.
    """
    # 데이터가 충분한지 확인
    if len(df) < 2:
        return None  # 데이터가 부족하면 신호 없음 반환

    # 현재 및 이전 DI와 ADX 값
    current_di_plus = df['DI+'].iloc[-1]
    current_di_minus = df['DI-'].iloc[-1]
    previous_di_plus = df['DI+'].iloc[-2]
    previous_di_minus = df['DI-'].iloc[-2]
    current_adx = df['ADX'].iloc[-1]

    # 신호 생성 조건 (DI+와 DI-의 교차 이벤트)
    if (previous_di_plus <= previous_di_minus) and (current_di_plus > current_di_minus):
        # DI+가 DI-를 상향 돌파 (교차 발생)
        if current_adx < current_di_plus and current_adx < current_di_minus:
            return "Long"
        elif current_adx > current_di_plus and current_adx > current_di_minus:
            return "Reset"
    elif (previous_di_plus >= previous_di_minus) and (current_di_plus < current_di_minus):
        # DI+가 DI-를 하향 돌파 (교차 발생)
        if current_adx < current_di_plus and current_adx < current_di_minus:
            return "Short"
        elif current_adx > current_di_plus and current_adx > current_di_minus:
            return "Reset"

    # 교차가 발생하지 않으면 None 반환
    return None

# 여기도 교차가 발생했을때만 신호가 와야되는데 그냥 계속 있음