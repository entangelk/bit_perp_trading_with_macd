def check_line_reg_signal(df,STG_CONFIG):
    """
    진입 시그널을 계산하여 데이터프레임에 새로운 컬럼으로 추가하는 함수
    Parameters:
        df: 데이터프레임
    Returns:
        시그널 컬럼이 추가된 데이터프레임
    """
    df = df.copy()  # 원본 데이터 보호
    # 결과를 저장할 새로운 컬럼 초기화
    df['line_reg_signal'] = None
    
    if len(df) < 2:  # 최소 2개의 데이터 필요
        return df
        
    # 파라미터 설정
    rsi_lower = STG_CONFIG['LINEAR_REG']['RSI_LOWER_BOUND'] 
    rsi_upper = STG_CONFIG['LINEAR_REG']['RSI_UPPER_BOUND']
    min_slope_filter = STG_CONFIG['LINEAR_REG']['MIN_SLOPE_VALUE']
    min_trend_bars = STG_CONFIG['LINEAR_REG']['MIN_TREND_DURATION']
    bounce_strength = STG_CONFIG['LINEAR_REG']['MIN_BOUNCE_BARS']

    # 시그널 컬럼 인덱스 미리 저장
    signal_column_idx = df.columns.get_loc('line_reg_signal')

    def check_bounce(idx):
        count = 0
        
        for i in range(1, bounce_strength + 1):
            if idx - i < 0 or idx - (i-1) < 0:  # 인덱스 범위 체크
                return False
            
            curr_price = df['close'].iloc[idx - (i-1)]
            prev_price = df['close'].iloc[idx - i]
            
            if df['slope'].iloc[idx] >= 0:  # 상승추세
                if (df['low'].iloc[idx - (i-1)] <= df['lower_band'].iloc[idx - (i-1)] and 
                    curr_price < prev_price):
                    count += 1
            else:  # 하락추세
                if (df['high'].iloc[idx - (i-1)] >= df['upper_band'].iloc[idx - (i-1)] and 
                    curr_price > prev_price):
                    count += 1

        return count >= bounce_strength
    
    # 각 행에 대해 시그널 계산
    for i in range(len(df)):
        if i < bounce_strength:  # 초기 데이터는 건너뛰기
            continue
            
        current = df.iloc[i]
        
        # RSI 필터
        is_valid_rsi = rsi_lower <= current['rsi_stg4'] <= rsi_upper
        
        # 기울기 강도 필터
        is_valid_slope = abs(current['slope']) >= min_slope_filter
        
        # 추세 방향
        is_uptrend = current['slope'] >= 0
        is_downtrend = current['slope'] < 0
        
        # 추세 지속성 확인
        is_valid_trend_duration = abs(current['trend_duration']) >= min_trend_bars
        
        # 모든 진입 조건 확인
        if not (is_valid_rsi and is_valid_slope and is_valid_trend_duration):
            continue
        
        # 롱 포지션 조건
        if (is_uptrend and 
            current['low'] <= current['lower_band'] and 
            check_bounce(i)):
            df.iloc[i, signal_column_idx] = 'Long'
            
        # 숏 포지션 조건
        elif (is_downtrend and 
              current['high'] >= current['upper_band'] and 
              check_bounce(i)):
            df.iloc[i, signal_column_idx] = 'Short'
    
    return df