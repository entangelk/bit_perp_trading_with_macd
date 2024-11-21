def calculate_ut_bot_signal(df, a=4):
    """
    UT Bot Alerts 전략을 구현하여 단일 신호('Long', 'Short', None)만 생성.

    Parameters:
        df (DataFrame): 사전 계산된 지표를 포함한 DataFrame.
        a (float): 트레일링 스탑 민감도 값.

    Returns:
        str: 'Long', 'Short', 또는 None
    """
    # 마지막 데이터와 이전 데이터 가져오기
    last_close = df['close'].iloc[-1]
    last_ema = df['ema'].iloc[-1]
    last_atr = df['atr_100'].iloc[-1]
    prev_close = df['close'].iloc[-2]
    prev_ema = df['ema'].iloc[-2]

    # 트레일링 스탑 계산
    nLoss = a * last_atr
    if last_close > prev_close:
        xATRTrailingStop = last_close - nLoss
    else:
        xATRTrailingStop = last_close + nLoss

    # 이전 트레일링 스탑 계산
    prev_nLoss = a * df['atr_100'].iloc[-2]
    if prev_close > df['close'].iloc[-3]:
        prev_xATRTrailingStop = prev_close - prev_nLoss
    else:
        prev_xATRTrailingStop = prev_close + prev_nLoss

    # 이전 신호 계산
    if prev_close > prev_xATRTrailingStop and prev_ema > prev_xATRTrailingStop:
        prev_signal = 'Long'
    elif prev_close < prev_xATRTrailingStop and prev_ema < prev_xATRTrailingStop:
        prev_signal = 'Short'
    else:
        prev_signal = None

    # 현재 신호 계산
    if last_close > xATRTrailingStop and last_ema > xATRTrailingStop:
        current_signal = 'Long'
    elif last_close < xATRTrailingStop and last_ema < xATRTrailingStop:
        current_signal = 'Short'
    else:
        current_signal = None

    # 이전 신호와 비교
    if current_signal == prev_signal:
        signal = None  # 신호가 변경되지 않으면 None 반환
    else:
        signal = current_signal  # 신호가 변경되면 새로운 신호 반환

    # 디버깅 출력
    print(f"Final Results:\n"
          f"Last close: {last_close}\n"
          f"Last EMA: {last_ema}\n"
          f"Final xATRTrailingStop: {xATRTrailingStop}\n"
          f"Previous close: {prev_close}\n"
          f"Previous EMA: {prev_ema}\n"
          f"Previous xATRTrailingStop: {prev_xATRTrailingStop}\n"
          f"Previous Signal: {prev_signal}\n"
          f"Current Signal: {current_signal}\n"
          f"Returned Signal: {signal}")

    return signal
