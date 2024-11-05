def adx_di_signal(df):
    """
    DI+와 DI-의 가장 최신 교차를 기반으로 신호를 생성합니다.
    DI+가 DI-를 상향 돌파하면 'Long', 하향 돌파하면 'Short' 신호를 반환합니다.
    신호가 없을 경우 'None'을 반환합니다.
    """
    # 마지막 두 행만 확인하여 신호 결정
    if len(df) < 2:
        return "None"  # 데이터가 부족하면 신호 없음 반환

    # 현재와 이전 DI 값
    current_di_plus = df['DI+'].iloc[-1]
    current_di_minus = df['DI-'].iloc[-1]
    previous_di_plus = df['DI+'].iloc[-2]
    previous_di_minus = df['DI-'].iloc[-2]

    # 신호 생성
    if (current_di_plus > current_di_minus) and (previous_di_plus <= previous_di_minus):
        signal = "Long"  # DI+가 DI-를 상향 돌파할 때
    elif (current_di_plus < current_di_minus) and (previous_di_plus >= previous_di_minus):
        signal = "Short"  # DI+가 DI-를 하향 돌파할 때
    else:
        signal = "None"  # 신호 없음

    return signal
