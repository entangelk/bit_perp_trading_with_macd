def check_line_reg_signal(df):
    """
    진입 시그널 체크 함수
    Parameters:
        df: 데이터프레임
    Returns:
        'long', 'short', 또는 None
    """
    # 파라미터 설정
    rsi_lower = 25
    rsi_upper = 75
    min_slope_filter = 4.5
    min_trend_bars = 67
    bounce_strength = 4
    
    # 현재 값들 가져오기
    current = df.iloc[-1]
    
    # RSI 필터
    is_valid_rsi = rsi_lower <= current['rsi'] <= rsi_upper
    
    # 기울기 강도 필터
    is_valid_slope = abs(current['slope']) >= min_slope_filter
    
    # 추세 방향
    is_uptrend = current['slope'] >= 0
    is_downtrend = current['slope'] < 0
    
    # 추세 지속성 확인
    is_valid_trend_duration = abs(current['trend_duration']) >= min_trend_bars
    
    # 바운스 확인
    def check_bounce():
        count = 0
        for i in range(1, bounce_strength + 1):
            prev_idx = -1 - i
            prev_idx2 = -2 - i
            
            if is_uptrend:
                if (df['low'].iloc[prev_idx] <= df['lower_band'].iloc[prev_idx] and 
                    df['close'].iloc[prev_idx] > df['close'].iloc[prev_idx2]):
                    count += 1
            else:
                if (df['high'].iloc[prev_idx] >= df['upper_band'].iloc[prev_idx] and 
                    df['close'].iloc[prev_idx] < df['close'].iloc[prev_idx2]):
                    count += 1
                    
        return count >= bounce_strength
    
    # 모든 조건 확인
    if not (is_valid_rsi and is_valid_slope and is_valid_trend_duration):
        return None
    
    # 롱 포지션 조건
    if (is_uptrend and 
        current['low'] <= current['lower_band'] and 
        check_bounce()):
        return 'long'
        
    # 숏 포지션 조건
    if (is_downtrend and 
        current['high'] >= current['upper_band'] and 
        check_bounce()):
        return 'short'
        
    return None