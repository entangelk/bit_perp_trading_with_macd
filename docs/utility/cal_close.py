def isclowstime(df, side):
    """
    RSI와 DI 이동평균선을 기반으로 포지션 청산 조건을 확인하는 함수
    :param df: DataFrame
    :param side: 현재 포지션 방향 ('Long' or 'Short')
    :return: bool (청산 여부)
    """
    # 초기 매도 신호 설정
    close_signal = False

    # RSI 값 확인
    current_rsi = df['rsi'].iloc[-1]

    # Long 포지션: RSI가 75 이상일 때 청산
    if side == 'Long' and current_rsi >= 85:
        close_signal = True
    
    # Short 포지션: RSI가 25 이하일 때 청산
    elif side == 'Short' and current_rsi <= 15:
        close_signal = True

    '''
    # DI 이동평균선 기울기 확인
    if side == 'Long':
        current_di_plus = df['DI+_MA7'].iloc[-1]
        prev_di_plus = df['DI+_MA7'].iloc[-2]
        current_di_minus = df['DI-_MA7'].iloc[-1]
        prev_di_minus = df['DI-_MA7'].iloc[-2]
        
        # DI+ 하락하고 DI-는 상승하는 경우에만 청산
        if current_di_plus < prev_di_plus and current_di_minus >= prev_di_minus:
            close_signal = True
    
    elif side == 'Short':
        current_di_minus = df['DI-_MA7'].iloc[-1]
        prev_di_minus = df['DI-_MA7'].iloc[-2]
        current_di_plus = df['DI+_MA7'].iloc[-1]
        prev_di_plus = df['DI+_MA7'].iloc[-2]
        
        # DI- 하락하고 DI+는 상승하는 경우에만 청산
        if current_di_minus < prev_di_minus and current_di_plus >= prev_di_plus:
            close_signal = True
    '''
    return close_signal