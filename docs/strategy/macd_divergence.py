def generate_macd_dive_signal(df,STG_CONFIG):
    df = df.copy()
    df['macd_dive_signal'] = None
    
    hist_upper = STG_CONFIG['MACD_DIVE']['HISTOGRAM_UPPER_LIMIT']
    hist_lower = STG_CONFIG['MACD_DIVE']['HISTOGRAM_LOWER_LIMIT']
    price_threshold = STG_CONFIG['MACD_DIVE']['PRICE_MOVEMENT_THRESHOLD']
    lookback = STG_CONFIG['MACD_DIVE']['LOOKBACK_PERIOD']

    # 중간값 확인을 위한 출력
    print(f"파라미터: hist_upper={hist_upper}, hist_lower={hist_lower}, price_threshold={price_threshold}, lookback={lookback}")
    
    for i in range(lookback + 1, len(df)):
        current_price = df['close'].iloc[i]
        prev_price = df['close'].iloc[i-1]
        price_change_pct = (current_price - prev_price) / prev_price * 100
        
        # hist_stg2 사용
        current_hist = df['hist_stg2'].iloc[i]
        if hist_lower <= current_hist <= hist_upper:
            continue
            
        hist_direction = current_hist - df['hist_stg2'].iloc[i-1]
        
        # Bearish Divergence
        if hist_direction > 0 and price_change_pct < -price_threshold:
            bearish_count = 0
            for j in range(lookback):
                check_idx = i - j
                prev_check_idx = check_idx - 1
                
                if prev_check_idx >= 0:
                    hist_diff = df['hist_stg2'].iloc[check_idx] - df['hist_stg2'].iloc[prev_check_idx]
                    price_diff_pct = ((df['close'].iloc[check_idx] - df['close'].iloc[prev_check_idx])
                                    / df['close'].iloc[prev_check_idx] * 100)
                    if hist_diff > 0 and price_diff_pct < -price_threshold:
                        bearish_count += 1
            
            if bearish_count >= lookback:
                df.iloc[i, df.columns.get_loc('macd_dive_signal')] = 'Short'
        
        # Bullish Divergence
        elif hist_direction < 0 and price_change_pct > price_threshold:
            bullish_count = 0
            for j in range(lookback):
                check_idx = i - j
                prev_check_idx = check_idx - 1
                
                if prev_check_idx >= 0:
                    hist_diff = df['hist_stg2'].iloc[check_idx] - df['hist_stg2'].iloc[prev_check_idx]
                    price_diff_pct = ((df['close'].iloc[check_idx] - df['close'].iloc[prev_check_idx])
                                    / df['close'].iloc[prev_check_idx] * 100)
                    if hist_diff < 0 and price_diff_pct > price_threshold:
                        bullish_count += 1
            
            if bullish_count >= lookback:
                df.iloc[i, df.columns.get_loc('macd_dive_signal')] = 'Long'
    
    return df