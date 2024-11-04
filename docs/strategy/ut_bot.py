import numpy as np

def calculate_ut_bot_signal(df, a=4):
    """
    UT Bot Alerts 전략을 구현하여 단일 신호('Long', 'Short', None)만 생성.

    Parameters:
        df (DataFrame): 사전 계산된 지표를 포함한 DataFrame.
        a (float): 트레일링 스탑 민감도 값.
        atr_period (int): ATR 계산에 사용되는 기간.

    Returns:
        str: 'Long', 'Short', 또는 None
    """
    # 트레일링 스탑 계산을 위한 설정
    nLoss = a * df['atr_100'].iloc[-1]
    xATRTrailingStop = None  # 초기값

    # 마지막 두 개의 종가로 트레일링 스탑 계산 및 신호 생성
    for i in range(1, len(df)):
        close_prev, close_curr = df['close'].iloc[i - 1], df['close'].iloc[i]

        if xATRTrailingStop is None:
            xATRTrailingStop = close_curr - nLoss if close_curr > close_prev else close_curr + nLoss

        elif close_curr > xATRTrailingStop and close_prev > xATRTrailingStop:
            xATRTrailingStop = max(xATRTrailingStop, close_curr - nLoss)
        elif close_curr < xATRTrailingStop and close_prev < xATRTrailingStop:
            xATRTrailingStop = min(xATRTrailingStop, close_curr + nLoss)
        elif close_curr > xATRTrailingStop:
            xATRTrailingStop = close_curr - nLoss
        else:
            xATRTrailingStop = close_curr + nLoss

    # 신호 결정
    last_close = df['close'].iloc[-1]
    last_ema = df['ema'].iloc[-1]  # 사전 계산된 ema 사용
    signal = None

    if last_close > xATRTrailingStop and last_ema > xATRTrailingStop:
        signal = 'Long'
    elif last_close < xATRTrailingStop and last_ema < xATRTrailingStop:
        signal = 'Short'

    return signal
