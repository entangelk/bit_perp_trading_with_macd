def adx_di_signal(df):
    """
    DI+와 DI-의 가장 최신 교차를 기반으로 신호를 생성합니다.
    DI+가 DI-를 상향 돌파하고 ADX 값이 DI+와 DI- 값보다 낮으면 'Long',
    DI+가 DI-를 하향 돌파하고 ADX 값이 DI+와 DI- 값보다 낮으면 'Short',
    DI+와 DI-의 교차 시 ADX 값이 DI+와 DI- 값보다 높으면 'Reset' 신호를 반환합니다.
    신호가 없을 경우 None을 반환합니다.
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

    # 신호 생성 조건
    if (current_di_plus > current_di_minus) and (previous_di_plus <= previous_di_minus):
        if current_adx < current_di_plus and current_adx < current_di_minus:
            signal = "Long"  # ADX가 교차된 DI 값들보다 낮을 때
        elif current_adx > current_di_plus and current_adx > current_di_minus:
            signal = "Reset"  # ADX가 교차된 DI 값들보다 높을 때
        else:
            signal = None
    elif (current_di_plus < current_di_minus) and (previous_di_plus >= previous_di_minus):
        if current_adx < current_di_plus and current_adx < current_di_minus:
            signal = "Short"  # ADX가 교차된 DI 값들보다 낮을 때
        elif current_adx > current_di_plus and current_adx > current_di_minus:
            signal = "Reset"  # ADX가 교차된 DI 값들보다 높을 때
        else:
            signal = None
    else:
        signal = None  # 신호 없음

    return signal
