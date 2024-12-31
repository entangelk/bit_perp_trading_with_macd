def generate_macd_dive_signal(df, hist_upper=60, hist_lower=-200, 
                      price_threshold=0.16, lookback=1):
    """
    MACD 다이버전스 기반 매매 신호 생성
    
    Parameters:
    - df: DataFrame with columns ['close', 'macd', 'macd_signal', 'hist']
    - hist_upper: 히스토그램 상단 제한 (default: 60)
    - hist_lower: 히스토그램 하단 제한 (default: -200)
    - price_threshold: 가격 변동 임계값 % (default: 0.16)
    - lookback: 다이버전스 확인 기간 (default: 1)
    
    Returns:
    - str: 'long', 'short', or None
    """
    
    # 충분한 데이터가 없으면 None 반환
    if len(df) < lookback + 1:
        return None
        
    # 현재 종가와 이전 종가
    current_price = df['close'].iloc[-1]
    prev_price = df['close'].iloc[-2]
    
    # 가격 변동률 계산 (%)
    price_change_pct = (current_price - prev_price) / prev_price * 100
    
    # 현재 히스토그램 값
    current_hist = df['hist'].iloc[-1]
    
    # 히스토그램이 안전 구간 내에 있으면 거래 없음
    if hist_lower <= current_hist <= hist_upper:
        return None
        
    # 히스토그램 방향
    hist_direction = current_hist - df['hist'].iloc[-2]
    
    # Bearish Divergence (히스토그램 상승 + 가격 하락)
    if hist_direction > 0 and price_change_pct < -price_threshold:
        bearish_count = 0
        for i in range(lookback):
            idx = -(i + 1)
            if abs(idx) < len(df):
                hist_diff = df['hist'].iloc[idx] - df['hist'].iloc[idx - 1]
                price_diff_pct = ((df['close'].iloc[idx] - df['close'].iloc[idx - 1]) 
                                / df['close'].iloc[idx - 1] * 100)
                if hist_diff > 0 and price_diff_pct < -price_threshold:
                    bearish_count += 1
        if bearish_count >= lookback:
            return 'Short'
    
    # Bullish Divergence (히스토그램 하락 + 가격 상승)
    if hist_direction < 0 and price_change_pct > price_threshold:
        bullish_count = 0
        for i in range(lookback):
            idx = -(i + 1)
            if abs(idx) < len(df):
                hist_diff = df['hist'].iloc[idx] - df['hist'].iloc[idx - 1]
                price_diff_pct = ((df['close'].iloc[idx] - df['close'].iloc[idx - 1]) 
                                / df['close'].iloc[idx - 1] * 100)
                if hist_diff < 0 and price_diff_pct > price_threshold:
                    bullish_count += 1
        if bullish_count >= lookback:
            return 'Long'
    
    return None