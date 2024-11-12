def isclowstime(df):
    # 초기 매도 신호 설정
    close_signal = False
    reason = ""

    # ADX가 하락 중이고 MACD가 활성화된 경우 - 복수 매도 조건
    if df['adx'].iloc[-1] < df['adx'].iloc[-2] and df['macd'].iloc[-1] > 0:
        # ADX가 상승 신호로 변환될 때까지 MACD와 RSI 신호를 wait 상태로 전환
        wait = df['adx'].iloc[-1] < df['adx'].max()
        
        # 매도 조건: ADX, MACD, RSI 이평선의 최대값 도달
        if df['adx'].iloc[-1] >= df['adx'].max() and \
           df['macd'].iloc[-1] >= df['macd'].max() and \
           df['rsi_ma'].iloc[-1] >= df['rsi_ma'].max():
            close_signal = True
            reason = "복수 매도 조건 - ADX, MACD, RSI 이평선 최대값 도달"

    # 단독 매도 조건
    elif (df['rsi'].iloc[-1] < 20 or df['rsi'].iloc[-1] > 80) or \
         (df['macd'].iloc[-1] > df['macd_limit'].iloc[-1]) or \
         (df['adx'].iloc[-1] >= 60):
        close_signal = True
        reason = "단독 매도 조건 - RSI 임계값 초과, MACD 라인 오버, 또는 ADX 60 이상"

    return close_signal, reason
