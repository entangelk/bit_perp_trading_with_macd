def check_VSTG_signal(df,STG_CONFIG):
    """시그널 체크 함수
    Returns:
        str: 'long', 'short', 또는 None
    """
    # 마지막 두 봉 데이터만 필요
    last_two = df.tail(2)
    if len(last_two) < 2:
        return None
        
    prev_norm_trend = last_two['norm_trend'].iloc[0]
    curr_norm_trend = last_two['norm_trend'].iloc[1]
    prev_signal_line = last_two['signal_line'].iloc[0]
    curr_signal_line = last_two['signal_line'].iloc[1]
    trend_diff = last_two['trend_diff'].iloc[1]

    threshold = STG_CONFIG['VOLUME_TREND']['SIGNAL_THRESHOLD']
    
    # 크로스오버 체크
    if (prev_norm_trend < prev_signal_line and 
        curr_norm_trend > curr_signal_line and 
        trend_diff >= threshold):
        return 'Long'
        
    elif (prev_norm_trend > prev_signal_line and 
          curr_norm_trend < curr_signal_line and 
          trend_diff >= threshold):
        return 'Short'
        
    return None