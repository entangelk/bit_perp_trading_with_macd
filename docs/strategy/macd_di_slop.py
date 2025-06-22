def generate_macd_di_rsi_signal(df,STG_CONFIG, debug=False):
    if len(df) < 5:
        return None

    # 파라미터 설정
    required_signals = STG_CONFIG['MACD_DI_SLOPE']['REQUIRED_CONSECUTIVE_SIGNALS']
    min_slope_threshold = STG_CONFIG['MACD_DI_SLOPE']['MIN_SLOPE_THRESHOLD']
    rsi_lower = STG_CONFIG['MACD_DI_SLOPE']['RSI_LOWER_BOUND']
    rsi_upper = STG_CONFIG['MACD_DI_SLOPE']['RSI_UPPER_BOUND']

    if debug:
        print("\n=== MACD 방향성 & DI 기울기 & RSI 전략 디버깅 ===")
        print(f"필요 연속 시그널: {required_signals}")
        print(f"기울기 임계값: {min_slope_threshold}")
        print(f"RSI 범위: {rsi_lower} - {rsi_upper}")

    # RSI 확인
    current_rsi = df['rsi_stg5'].iloc[-1]
    if debug:
        print(f"\nRSI 확인:")
        print(f"현재 RSI: {current_rsi:.2f}")
        print(f"유효 범위 내: {'예' if rsi_lower < current_rsi < rsi_upper else '아니오'}")

    if not (rsi_lower < current_rsi < rsi_upper):
        if debug:
            print("신호: 없음 (RSI 범위 초과)")
        return None

    # MACD 방향 확인
    macd_conditions = []
    if debug:
        print("\nMACD 방향성 조건 확인:")
    for i in range(required_signals):
        if i < len(df):
            direction = df['hist_direction_stg5'].iloc[-(i+1)]
            macd_up = direction > 0
            macd_down = direction < 0
            
            if debug:
                print(f"{i+1}번째 이전 봉:")
                print(f"  방향성: {direction:.2f}")
                print(f"  상승 추세: {'예' if macd_up else '아니오'}")
                print(f"  하락 추세: {'예' if macd_down else '아니오'}")
            
            macd_conditions.append((macd_up, macd_down))

    # DI 기울기 차이 확인
    slope_conditions = []
    if debug:
        print("\nDI 기울기 차이 조건 확인:")
    for i in range(required_signals):
        if i < len(df):
            slope_diff = df['slope_diff_stg5'].iloc[-(i+1)]
            slope_up = slope_diff > min_slope_threshold
            slope_down = slope_diff < -min_slope_threshold
            
            if debug:
                print(f"{i+1}번째 이전 봉:")
                print(f"  기울기 차이: {slope_diff:.2f}")
                print(f"  상승 기울기: {'충족' if slope_up else '미충족'}")
                print(f"  하락 기울기: {'충족' if slope_down else '미충족'}")
            
            slope_conditions.append((slope_up, slope_down))

    # 카운트 확인
    bull_count = 0
    bear_count = 0

    for macd_cond, slope_cond in zip(macd_conditions, slope_conditions):
        if macd_cond[0] and slope_cond[0]:
            bull_count += 1
        elif macd_cond[1] and slope_cond[1]:
            bear_count += 1

    if debug:
        print(f"\n최종 카운트:")
        print(f"상승 카운트: {bull_count}")
        print(f"하락 카운트: {bear_count}")
        print(f"필요 카운트: {required_signals}")

    # 카운트 확인 후, 시그널 생성 직전에 추가
    if bull_count == required_signals:
        if abs(df['slope_diff_stg5'].iloc[-1]) > min_slope_threshold * 2:
            if debug:
                print("\n최종 신호: 매수")
            return "Long"
    elif bear_count == required_signals:
        if abs(df['slope_diff_stg5'].iloc[-1]) > min_slope_threshold * 2:
            if debug:
                print("\n최종 신호: 매도")
            return "Short"
   
    if debug:
       print("\n최종 신호: 없음")
    return None