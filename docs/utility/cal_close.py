def isclowstime(df, side):
    """
    RSI 기반 청산 조건 확인
    :param df: DataFrame
    :param side: 현재 포지션 방향 ('Long' or 'Short')
    :return: bool (청산 여부)
    """
    # 초기 매도 신호 설정
    close_signal = False

    # RSI 값 확인
    current_rsi = df['rsi'].iloc[-1]

    # Long 포지션: RSI가 75 이상일 때 청산
    if side == 'Long' and current_rsi >= 75:
        close_signal = True
    
    # Short 포지션: RSI가 25 이하일 때 청산
    elif side == 'Short' and current_rsi <= 25:
        close_signal = True

    # 현재와 이전 값을 가져와서 기울기 계산
    if side == 'Long':
        current_di = df['DI+_MA7'].iloc[-1]
        prev_di = df['DI+_MA7'].iloc[-2]
        # 기울기가 하락할 때 (현재 값이 이전 값보다 작을 때)
        if current_di < prev_di:
            close_signal = True
    
    elif side == 'Short':
        current_di = df['DI-_MA7'].iloc[-1]
        prev_di = df['DI-_MA7'].iloc[-2]
        # 기울기가 하락할 때 (현재 값이 이전 값보다 작을 때)
        if current_di < prev_di:
            close_signal = True

    return close_signal