def macd_stg(df):
    """
    가장 최근의 'Long', 'Short', 또는 'None' 신호를 반환합니다.
    macd_diff가 0을 상향 돌파할 때 'Long', 하향 돌파할 때 'Short', 그렇지 않으면 'None'을 반환합니다.
    """
    if len(df) < 2:
        return None  # 데이터가 부족할 경우 신호를 None으로 반환
    
    # 마지막 두 행에서 macd_diff 비교
    if (df['macd_diff_stg'].iloc[-1] > 0) and (df['macd_diff_stg'].iloc[-2] <= 0):
        signal = "Long"
    elif (df['macd_diff_stg'].iloc[-1] < 0) and (df['macd_diff_stg'].iloc[-2] >= 0):
        signal = "Short"
    else:
        signal = None

    return signal