def adx_di_signal(df):
    """
    교차 여부, DI 기울기 방향, 기울기 크기 비교, ADX 조건을 기반으로 신호를 생성합니다.
    """
    if len(df) < 2:
        return None

    # 현재 및 이전 DI와 ADX 값
    current_di_plus = df['DI+'].iloc[-1]
    current_di_minus = df['DI-'].iloc[-1]
    previous_di_plus = df['DI+'].iloc[-2]
    previous_di_minus = df['DI-'].iloc[-2]
    current_adx = df['ADX'].iloc[-1]

    # DI 교차점 계산 (평균값)
    di_mean = (current_di_plus + current_di_minus) / 2

    # ADX와 DI 교차점 차이
    difference = abs(di_mean - current_adx)

    # DI 기울기 계산
    di_plus_slope = current_di_plus - previous_di_plus
    di_minus_slope = current_di_minus - previous_di_minus

    # 교차 조건 + 근소치 기준
    di_difference = abs(current_di_plus - current_di_minus)
    near_crossover = di_difference <= 2

    # 교차 조건 + ADX 조건 + 기울기 크기 비교
    if (previous_di_plus <= previous_di_minus and current_di_plus > current_di_minus) or near_crossover:
        # 상향 교차 또는 근소치 기준
        if di_plus_slope > 0 and di_minus_slope > 0:  # 기울기 같은 방향
            if abs(di_plus_slope) > abs(di_minus_slope):  # DI+ 기울기가 더 큼
                if difference <= 3:
                    return "Long"
            elif abs(di_minus_slope) > abs(di_plus_slope):  # DI- 기울기가 더 큼
                if difference <= 3:
                    return "Short"
        else:
            return "Reset"  # 기울기 반대 방향이면 Reset
    elif (previous_di_plus >= previous_di_minus and current_di_plus < current_di_minus) or near_crossover:
        # 하향 교차 또는 근소치 기준
        if di_plus_slope < 0 and di_minus_slope < 0:  # 기울기 같은 방향
            if abs(di_plus_slope) > abs(di_minus_slope):  # DI+ 기울기가 더 큼
                if difference <= 3:
                    return "Long"
            elif abs(di_minus_slope) > abs(di_plus_slope):  # DI- 기울기가 더 큼
                if difference <= 3:
                    return "Short"
        else:
            return "Reset"  # 기울기 반대 방향이면 Reset

    # 기본적으로 신호 없음 반환
    return None









if __name__ == "__main__":
    import pandas as pd

    print("=== ADX DI Signal Test ===")

    # 테스트 케이스 목록
    test_cases = [
        {
            "name": "Normal Case - Clear upward crossover",
            "data": {
                "DI+": [20, 22, 25],
                "DI-": [25, 20, 18],
                "ADX": [15, 20, 22],
            },
        },
        {
            "name": "Boundary Case - DI values close but no crossover",
            "data": {
                "DI+": [20, 21, 21],
                "DI-": [20, 21, 22],
                "ADX": [18, 19, 20],
            },
        },
        {
            "name": "Extreme Case - Large DI gap without crossover",
            "data": {
                "DI+": [10, 50, 60],
                "DI-": [60, 10, 20],
                "ADX": [25, 30, 35],
            },
        },
        {
            "name": "Boundary Case - Minimal ADX difference",
            "data": {
                "DI+": [22, 23, 24],
                "DI-": [23, 22, 21],
                "ADX": [20, 20.5, 21],
            },
        },
        {
            "name": "Normal Case - Clear downward crossover",
            "data": {
                "DI+": [25, 22, 20],
                "DI-": [20, 22, 25],
                "ADX": [22, 20, 18],
            },
        },
        {
            "name": "Extreme Case - ADX consistently high",
            "data": {
                "DI+": [20, 25, 30],
                "DI-": [30, 25, 20],
                "ADX": [60, 65, 70],
            },
        },
        {
            "name": "Edge Case - Same DI+ and DI- values",
            "data": {
                "DI+": [20, 20, 20],
                "DI-": [20, 20, 20],
                "ADX": [15, 20, 25],
            },
        },
    ]

    # 테스트 실행
    for case in test_cases:
        print(f"\n--- {case['name']} ---")
        df = pd.DataFrame(case["data"])
        for i in range(1, len(df)):
            sub_df = df.iloc[: i + 1]
            signal = adx_di_signal(sub_df)
            print(f"Row {i}: Signal: {signal}")



    # 테스트 데이터
    test_data = {
                "DI+": [22, 25],
                "DI-": [20, 18],
                "ADX": [20, 22],
    }
    df = pd.DataFrame(test_data)

    # Row 2 데이터
    current_di_plus = df['DI+'].iloc[-1]
    current_di_minus = df['DI-'].iloc[-1]
    current_adx = df['ADX'].iloc[-1]

    # DI 교차점 (평균값)
    di_mean = (current_di_plus + current_di_minus) / 2

    # 차이 계산
    difference = abs(di_mean - current_adx)
    signal = adx_di_signal(df)
    print(signal)
    print(f"DI Mean (교차점): {di_mean}")
    print(f"Current ADX: {current_adx}")
    print(f"Difference: {difference}")


