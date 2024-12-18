def check_squeeze_signals(df):
    current = df.iloc[-1]
    
    # 1. vf 신호 확인 및 저장
    if current['squeeze_vf'] > 0:
        df.loc[current.name, 'squeeze_color'] = 'EMERALD'
        df.loc[current.name, 'squeeze_strength'] = min(100, current['squeeze_vf'])
    else:
        df.loc[current.name, 'squeeze_color'] = 'RED'
        df.loc[current.name, 'squeeze_strength'] = min(100, abs(current['squeeze_vf']))
    
    print("\n=== Squeeze VF 디버그 ===")
    print(f"squeeze_vf: {current['squeeze_vf']}")
    print(f"설정된 색상: {df.loc[current.name, 'squeeze_color']}")
    print(f"설정된 강도: {df.loc[current.name, 'squeeze_strength']}")
    
    # 2. 스퀴즈 상태 체크를 위한 값들 출력
    squeeze_diff = current['squeeze_ma'] - current['squeeze_value'] 
    df.loc[current.name, 'squeeze_diff'] = squeeze_diff
    
    print("\n=== Squeeze 상태 디버그 ===")
    print(f"squeeze_value: {current['squeeze_value']}")
    print(f"squeeze_ma: {current['squeeze_ma']}")
    print(f"squeeze_diff: {squeeze_diff}")
    print(f"hypersqueeze: {current['hypersqueeze']}")
    
    if current['hypersqueeze']:
        df.loc[current.name, 'squeeze_state'] = 'YELLOW'
    elif squeeze_diff < 0:
        df.loc[current.name, 'squeeze_state'] = 'ORANGE'
    else:
        df.loc[current.name, 'squeeze_state'] = 'GRAY'
    
    print(f"최종 설정된 상태: {df.loc[current.name, 'squeeze_state']}")
    
    # 3. zscore 디버그
    if len(df) > 1:
        prev_zscore = df['squeeze_zscore'].iloc[-2]
        current_zscore = current['squeeze_zscore']
        
        print("\n=== ZScore 디버그 ===")
        print(f"이전 zscore: {prev_zscore}")
        print(f"현재 zscore: {current_zscore}")
        
        if current_zscore > prev_zscore:
            df.loc[current.name, 'zscore_direction'] = 'UP'
        elif current_zscore < prev_zscore:
            df.loc[current.name, 'zscore_direction'] = 'DOWN'
        else:
            df.loc[current.name, 'zscore_direction'] = 'NEUTRAL'
            
        df.loc[current.name, 'zscore_value'] = current_zscore
        print(f"설정된 방향: {df.loc[current.name, 'zscore_direction']}")
    else:
        df.loc[current.name, 'zscore_direction'] = 'NEUTRAL'
        df.loc[current.name, 'zscore_value'] = current['squeeze_zscore']

    return df