# Zero-Lag MA Trend Levels
# https://kr.tradingview.com/v/pP2FhzAX/

def zero_reg(df):
    position = None  # 초기 포지션 값을 None으로 설정

    # 데이터프레임이 충분한 데이터(최소 2개 이상의 행)를 가지고 있는지 확인
    if len(df) > 1 and 'zlma' in df.columns and 'ema' in df.columns:
        # 가장 최근 값과 이전 값 가져오기 (최근 1개와 2번째 최근 값)
        current_zlma = df['zlma'].iloc[-1]
        previous_zlma = df['zlma'].iloc[-2]
        current_ema = df['ema'].iloc[-1]
        previous_ema = df['ema'].iloc[-2]

        # 상승 교차: ZLMA가 EMA를 위로 교차할 때
        if previous_zlma <= previous_ema and current_zlma > current_ema:
            position = 'Long'

        # 하락 교차: ZLMA가 EMA를 아래로 교차할 때
        elif previous_zlma >= previous_ema and current_zlma < current_ema:
            position = 'Short'
    else:
        print("Insufficient data or missing columns.")

    return position

