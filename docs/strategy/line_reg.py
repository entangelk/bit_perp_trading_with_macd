def check_line_reg_signal(df,STG_CONFIG):
    """
    진입 시그널 체크 함수
    Parameters:
        df: 데이터프레임
    Returns:
        'long', 'short', 또는 None
    """
    if len(df) < 2:  # 최소 2개의 데이터 필요
        return None
        
    # 파라미터 설정
    rsi_lower = STG_CONFIG['LINEAR_REG']['RSI_LOWER_BOUND'] 
    rsi_upper = STG_CONFIG['LINEAR_REG']['RSI_UPPER_BOUND']
    min_slope_filter = STG_CONFIG['LINEAR_REG']['MIN_SLOPE_VALUE']
    min_trend_bars = STG_CONFIG['LINEAR_REG']['MIN_TREND_DURATION']
    bounce_strength = STG_CONFIG['LINEAR_REG']['MIN_BOUNCE_BARS']
    
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
    

    # 바운스 확인 함수
    def check_bounce():
        count = 0
        current_idx = len(df) - 1
        
        for i in range(1, bounce_strength + 1):
            if current_idx - i < 0 or current_idx - (i-1) < 0:  # 인덱스 범위 체크
                return False
            
            curr_price = df['close'].iloc[current_idx - (i-1)]
            prev_price = df['close'].iloc[current_idx - i]
            
            if is_uptrend:
                if (df['low'].iloc[current_idx - (i-1)] <= df['lower_band'].iloc[current_idx - (i-1)] and 
                    curr_price < prev_price):
                    count += 1
            else:
                if (df['high'].iloc[current_idx - (i-1)] >= df['upper_band'].iloc[current_idx - (i-1)] and 
                    curr_price > prev_price):  # 다운트렌드에서도 상승을 체크
                    count += 1
            pass
        return count >= bounce_strength
    
    # 모든 진입 조건 확인
    if not (is_valid_rsi and is_valid_slope and is_valid_trend_duration):
        return None
    
    # 롱 포지션 조건
    if (is_uptrend and 
        current['low'] <= current['lower_band'] and 
        check_bounce()):
        return 'Long'
        
    # 숏 포지션 조건
    if (is_downtrend and 
        current['high'] >= current['upper_band'] and 
        check_bounce()):
        return 'Short'
        
    return None