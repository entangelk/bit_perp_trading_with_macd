import pandas as pd

def calculate_atr_trailing_stop(src, nLoss, prev_src, prev_stop):
    """
    ATR 기반 트레일링 스탑 계산
    """
    # 상승 → 하락 전환
    if (src - nLoss) < prev_stop and prev_src > prev_stop:
        return (src + nLoss + prev_stop) / 2  # 완화된 전환
    
    # 하락 → 상승 전환
    elif (src + nLoss) > prev_stop and prev_src < prev_stop:
        return (src - nLoss + prev_stop) / 2  # 완화된 전환
    
    # 상승 추세 유지
    elif src > prev_stop:
        return max(prev_stop, src - nLoss)
    
    # 하락 추세 유지
    elif src < prev_stop:
        return min(prev_stop, src + nLoss)
    
    # 변동 없음
    else:
        return prev_stop


def calculate_initial_stop(df, nLoss):
    if len(df) < 10:
        raise ValueError("DataFrame must contain at least 10 rows for initial stop calculation.")

    # 마지막 10개 close 값 가져오기
    recent_closes = df['close'].iloc[-10:]  # Ensure slicing works correctly

    # 상승 추세라면 max를 기준으로, 하락 추세라면 min을 기준으로 초기값 설정
    if recent_closes.iloc[-1] > recent_closes.iloc[0]:  # 상승 추세
        baseline_close = recent_closes.max()
        return baseline_close - nLoss
    else:  # 하락 추세
        baseline_close = recent_closes.min()
        return baseline_close + nLoss

def calculate_trailing_stops(df, a=4, debug=False):
    nLoss = a * df['atr_100'].iloc[0]  # ATR multiplier
    trailing_stops = [0.0] * len(df)  # Initialize the list for trailing stops

    # 초기값 설정
    trailing_stops[9] = calculate_initial_stop(df.iloc[:10], nLoss)

    # 순차적으로 계산
    for i in range(10, len(df)):
        curr_close = df['close'].iloc[i]
        prev_close = df['close'].iloc[i - 1]
        prev_stop = trailing_stops[i - 1]
        trailing_stops[i] = calculate_atr_trailing_stop(curr_close, nLoss, prev_close, prev_stop)

        if debug:
            print(f"Row {i}: src: {curr_close}, prev_src: {prev_close}, prev_stop: {prev_stop}, new_stop: {trailing_stops[i]}")

    return trailing_stops

def calculate_ut_bot_signals(df, a=4, debug=False):
    if len(df) < 10:
        raise ValueError("DataFrame must contain at least 10 rows for calculations.")

    # ATR multiplier
    nLoss = a * df['atr_100'].iloc[-1]

    # Calculate trailing stops for the entire DataFrame
    trailing_stops = calculate_trailing_stops(df, a, debug=debug)

    # 현재와 이전 값을 추출
    prev_close = df['close'].iloc[-2]
    curr_close = df['close'].iloc[-1]
    prev_ema = df['ema'].iloc[-2]
    curr_ema = df['ema'].iloc[-1]
    prev_stop = trailing_stops[-2]
    curr_stop = trailing_stops[-1]

    # 조건 계산
    condition1 = prev_ema <= prev_stop
    condition2 = curr_ema > curr_stop
    condition3 = curr_close > curr_stop

    # Debugging output
    if debug:
        print("=== DEBUG INFO ===")
        print(f"Prev Stop: {prev_stop}, Curr Stop: {curr_stop}")
        print(f"Prev EMA: {prev_ema}, Curr EMA: {curr_ema}")
        print(f"Condition 1 (Prev EMA <= Prev Stop): {condition1}")
        print(f"Condition 2 (Curr EMA > Curr Stop): {condition2}")
        print(f"Condition 3 (Curr Close > Curr Stop): {condition3}")
        print("==================")

    # 신호 생성
    if condition1 and condition2 and condition3:
        return 'Long'
    elif not condition1 and not condition2 and not condition3:
        return 'Short'
    return None



if __name__ == "__main__":
    # 샘플 데이터
    data = {
        'close': [91841.2, 91762.9, 92070.0, 92260.9, 92150.8, 92310.4, 92420.7, 92250.5, 92050.3, 92150.0, 92260.0],
        'ema': [91841.2, 91762.9, 92070.0, 92270.0, 92160.0, 92320.0, 92430.0, 92260.0, 92080.0, 92170.0, 92280.0],
        'atr_100': [324.0] * 11
    }
    df = pd.DataFrame(data)

    # Calculate signals
    signal = calculate_ut_bot_signals(df, a=4, debug=True)
    print(f"Signal: {signal}")








'''
트레일링 스탑 및 신호 계산 과정:
이전 트레일링 스탑 초기화 및 갱신

xATRTrailingStop은 이전 값(prev_stop)을 이용해 갱신됩니다.
초기 xATRTrailingStop은 NaN 값에서 시작하고, 특정 규칙에 따라 갱신되죠.
트레일링 스탑의 갱신 규칙:

상승세: 현재 종가 > 이전 트레일링 스탑인 경우
curr_stop = max(prev_stop, curr_close - nLoss)
하락세: 현재 종가 <= 이전 트레일링 스탑인 경우
curr_stop = min(prev_stop, curr_close + nLoss)
신호 발생 조건:

Long 신호 조건:
이전 EMA <= 이전 트레일링 스탑 이고
현재 EMA > 현재 트레일링 스탑 이며
현재 종가 > 현재 트레일링 스탑일 때
Long 신호가 발생
Short 신호 조건:
반대로, Short 신호는 EMA와 트레일링 스탑이 반대 조건을 만족할 때 발생
'''






'''
//@version=4
study(title="UT Bot Alerts", overlay = true)

// Inputs
a = input(1,     title = "Key Vaule. 'This changes the sensitivity'")
c = input(10,    title = "ATR Period")
h = input(false, title = "Signals from Heikin Ashi Candles")

xATR  = atr(c)
nLoss = a * xATR

src = h ? security(heikinashi(syminfo.tickerid), timeframe.period, close, lookahead = false) : close

xATRTrailingStop = 0.0
xATRTrailingStop := iff(src > nz(xATRTrailingStop[1], 0) and src[1] > nz(xATRTrailingStop[1], 0), max(nz(xATRTrailingStop[1]), src - nLoss),
   iff(src < nz(xATRTrailingStop[1], 0) and src[1] < nz(xATRTrailingStop[1], 0), min(nz(xATRTrailingStop[1]), src + nLoss), 
   iff(src > nz(xATRTrailingStop[1], 0), src - nLoss, src + nLoss)))
 
pos = 0   
pos :=	iff(src[1] < nz(xATRTrailingStop[1], 0) and src > nz(xATRTrailingStop[1], 0), 1,
   iff(src[1] > nz(xATRTrailingStop[1], 0) and src < nz(xATRTrailingStop[1], 0), -1, nz(pos[1], 0))) 
   
xcolor = pos == -1 ? color.red: pos == 1 ? color.green : color.blue 

ema   = ema(src,1)
above = crossover(ema, xATRTrailingStop)
below = crossover(xATRTrailingStop, ema)

buy  = src > xATRTrailingStop and above 
sell = src < xATRTrailingStop and below

barbuy  = src > xATRTrailingStop 
barsell = src < xATRTrailingStop 

plotshape(buy,  title = "Buy",  text = 'Buy',  style = shape.labelup,   location = location.belowbar, color= color.green, textcolor = color.white, transp = 0, size = size.tiny)
plotshape(sell, title = "Sell", text = 'Sell', style = shape.labeldown, location = location.abovebar, color= color.red,   textcolor = color.white, transp = 0, size = size.tiny)

barcolor(barbuy  ? color.green : na)
barcolor(barsell ? color.red   : na)

alertcondition(buy,  "UT Long",  "UT Long")
alertcondition(sell, "UT Short", "UT Short")
'''