def generate_macd_size_signal(df, debug=False):
    if len(df) < 2:
        return None

    # 파라미터 설정
    required_candles = 2
    size_ratio = 1.4
    min_slope_threshold = 12

    if debug:
        print("\n=== MACD 크기 & DI 기울기 전략 디버깅 ===")
        print(f"필요 연속 봉 수: {required_candles}")
        print(f"크기 비율: {size_ratio}")
        print(f"기울기 임계값: {min_slope_threshold}")

    # MACD Size 조건 확인
    macd_size_conditions = []
    if debug:
        print("\nMACD 크기 조건 확인:")
    for i in range(required_candles):
        if i < len(df):
            hist = df['hist_di'].iloc[-(i+1)]
            norm_hist_size = df['normalized_hist_size'].iloc[-(i+1)]
            norm_candle_size = df['normalized_candle_size'].iloc[-(i+1)]
            
            bull_size = (hist > 0 and norm_hist_size > norm_candle_size * size_ratio)
            bear_size = (hist < 0 and norm_hist_size > norm_candle_size * size_ratio)
            
            if debug:
                print(f"{i+1}번째 이전 봉:")
                print(f"  히스토그램: {hist:.2f}")
                print(f"  정규화된 히스토그램 크기: {norm_hist_size:.2f}")
                print(f"  정규화된 봉 크기: {norm_candle_size:.2f}")
                print(f"  상승 크기 조건: {'충족' if bull_size else '미충족'}")
                print(f"  하락 크기 조건: {'충족' if bear_size else '미충족'}")
            
            macd_size_conditions.append((bull_size, bear_size))

    # DI Slope 조건 확인
    di_conditions = []
    if debug:
        print("\nDI 기울기 조건 확인:")
    for i in range(required_candles):
        if i < len(df):
            di_plus_slope = df['DIPlus_slope1'].iloc[-(i+1)]
            di_minus_slope = df['DIMinus_slope1'].iloc[-(i+1)]
            
            bull_slope = di_plus_slope > min_slope_threshold
            bear_slope = di_minus_slope > min_slope_threshold
            
            if debug:
                print(f"{i+1}번째 이전 봉:")
                print(f"  DI+ 기울기: {di_plus_slope:.2f}")
                print(f"  DI- 기울기: {di_minus_slope:.2f}")
                print(f"  상승 기울기 조건: {'충족' if bull_slope else '미충족'}")
                print(f"  하락 기울기 조건: {'충족' if bear_slope else '미충족'}")
            
            di_conditions.append((bull_slope, bear_slope))

    # 카운트 확인
    bull_count = 0
    bear_count = 0

    for macd_cond, di_cond in zip(macd_size_conditions, di_conditions):
        if macd_cond[0] and di_cond[0]:
            bull_count += 1
        elif macd_cond[1] and di_cond[1]:
            bear_count += 1

    if debug:
        print(f"\n최종 카운트:")
        print(f"상승 카운트: {bull_count}")
        print(f"하락 카운트: {bear_count}")
        print(f"필요 카운트: {required_candles}")

    # 시그널 생성
    if bull_count == required_candles:
        if debug:
            print("\n최종 신호: 매수")
        return "Long"
    elif bear_count == required_candles:
        if debug:
            print("\n최종 신호: 매도")
        return "Short"

    if debug:
        print("\n최종 신호: 없음")
    return None