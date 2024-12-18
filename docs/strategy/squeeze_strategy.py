def check_squeeze_signals(df):
    """
    Squeeze Momentum Oscillator의 각 컴포넌트에 대한 신호를 확인하고 DataFrame에 저장
    
    Parameters:
    df: DataFrame with squeeze indicators
    
    Returns:
    DataFrame: 상태값이 저장된 DataFrame
    """
    
    # 현재 값 가져오기
    current = df.iloc[-1]
    
    # 1. vf (빨강/에메랄드) 신호 확인 및 저장
    if current['squeeze_vf'] > 0:
        df.loc[current.name, 'squeeze_color'] = 'EMERALD'
        df.loc[current.name, 'squeeze_strength'] = min(100, current['squeeze_vf'])
    else:
        df.loc[current.name, 'squeeze_color'] = 'RED'
        df.loc[current.name, 'squeeze_strength'] = min(100, abs(current['squeeze_vf']))
    
    # 2. 스퀴즈 상태 (회색/주황/노랑) 확인 및 저장
    squeeze_diff = current['squeeze_value'] - current['squeeze_ma']
    df.loc[current.name, 'squeeze_diff'] = squeeze_diff
    
    if current['hypersqueeze']:
        df.loc[current.name, 'squeeze_state'] = 'YELLOW'
    elif squeeze_diff < 0:
        df.loc[current.name, 'squeeze_state'] = 'ORANGE'
    else:
        df.loc[current.name, 'squeeze_state'] = 'GRAY'
    
    # 3. zscore 방향 확인 및 저장
    if len(df) > 1:
        prev_zscore = df['squeeze_zscore'].iloc[-2]
        current_zscore = current['squeeze_zscore']
        
        if current_zscore > prev_zscore:
            df.loc[current.name, 'zscore_direction'] = 'UP'
        elif current_zscore < prev_zscore:
            df.loc[current.name, 'zscore_direction'] = 'DOWN'
        else:
            df.loc[current.name, 'zscore_direction'] = 'NEUTRAL'
            
        df.loc[current.name, 'zscore_value'] = current_zscore
    else:
        df.loc[current.name, 'zscore_direction'] = 'NEUTRAL'
        df.loc[current.name, 'zscore_value'] = current['squeeze_zscore']

    return df