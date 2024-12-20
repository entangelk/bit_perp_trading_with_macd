def check_trade_signal(df):
    """
    MACD 변화량 기반 매매 신호 체크 함수
    
    Parameters:
    df : DataFrame - 'macd_diff' 컬럼이 포함된 데이터프레임
    
    Returns:
    str - 'long', 'short', or None
    """
    # 마지막 두 개의 MACD 값 가져오기
    current = df['macd_diff'].iloc[-1]
    prev = df['macd_diff'].iloc[-2]
    
    check_diff = 35

    # MACD 변화량 계산
    macd_change = current - prev
    print(f'macd 변화량 : {macd_change}')
    # 변화량이 35 이상일 때 신호 발생
    if abs(macd_change) >= check_diff:
        if macd_change > 0:  # MACD가 크게 상승
            print('포지션 결정 : Long')
            return 'Long'
        else:  # MACD가 크게 하락
            print('포지션 결정 : Short')
            return 'Short'
    
    print(f'변화량이 {check_diff}보다 낮으므로 포지션 생성 없음음')
    return None