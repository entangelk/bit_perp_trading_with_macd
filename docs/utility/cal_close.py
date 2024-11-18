def isclowstime(df,side):
    # 초기 매도 신호 설정
    close_signal = False


    if side == 'Long':
    # 복수 매도 조건: ADX, MACD 상승, RSI SMA 상승 추세
        if (df['ADX'].iloc[-1] > df['ADX'].iloc[-2]) or \
            (df['macd'].iloc[-1] > df['macd'].iloc[-2]) or \
            (df['rsi_sma'].iloc[-1] > df['rsi_sma'].iloc[-2]):  # RSI SMA 상승 추세
            close_signal = True
    
    # Short 포지션인 경우
    elif side == 'Short':
        # 복수 매도 조건: ADX, MACD 상승, RSI SMA 하락 추세
        if (df['ADX'].iloc[-1] > df['ADX'].iloc[-2]) or \
            (df['macd'].iloc[-1] < df['macd'].iloc[-2]) or \
            (df['rsi_sma'].iloc[-1] < df['rsi_sma'].iloc[-2]):  # RSI SMA 하락 추세
            close_signal = True



    # 단독 매도 조건
    if (df['rsi'].iloc[-1] < 20 or df['rsi'].iloc[-1] > 80) or \
         (df['macd'].iloc[-1] > df['macd_signal'].iloc[-1]) or \
         (df['ADX'].iloc[-1] >= 60):
        close_signal = True

    return close_signal