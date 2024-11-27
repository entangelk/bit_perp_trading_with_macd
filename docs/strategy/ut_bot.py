import pandas as pd

def calculate_ut_bot_signals(df, a=4, debug=False):
    """
    UT Bot Alerts 시그널 계산 (Python 구현). 마지막 시그널만 계산.

    Parameters:
        df (DataFrame): OHLC 데이터와 ATR 및 EMA 컬럼을 포함한 DataFrame. 최소 3개의 데이터 필요.
        a (float): 민감도 값 (기본값: 4).
        debug (bool): 디버깅 정보 출력 여부.

    Returns:
        str: 'Long', 'Short', 또는 None.
    """


    # ATR 및 민감도 계산
    nLoss = a * df['atr_100'].iloc[-1]

    # 이전 및 현재 값 설정
    prev_close = df['close'].iloc[-2]
    curr_close = df['close'].iloc[-1]
    prev_ema = df['ema'].iloc[-2]
    curr_ema = df['ema'].iloc[-1]

    # 이전 트레일링 스탑 계산
    prev_stop = (
        df['close'].iloc[-3] - nLoss
        if df['close'].iloc[-3] > df['close'].iloc[-4]
        else df['close'].iloc[-3] + nLoss
    )

    # 현재 트레일링 스탑 계산
    curr_stop = (
        max(prev_stop, curr_close - nLoss)
        if curr_close > prev_stop
        else min(prev_stop, curr_close + nLoss)
    )

    # 디버깅 정보 출력
    if debug:
        print(f"Previous Stop: {prev_stop}")
        print(f"Current Stop: {curr_stop}")
        print(f"Prev EMA vs Stop: {prev_ema} {'>' if prev_ema > prev_stop else '<='} {prev_stop}")
        print(f"Curr EMA vs Stop: {curr_ema} {'>' if curr_ema > curr_stop else '<='} {curr_stop}")
        print(f"Price vs Stop: {curr_close} {'>' if curr_close > curr_stop else '<='} {curr_stop}")

    # Long 신호 조건
    if prev_ema <= prev_stop and curr_ema > curr_stop and curr_close > curr_stop:
        return 'Long'

    # Short 신호 조건
    elif prev_ema >= prev_stop and curr_ema < curr_stop and curr_close < curr_stop:
        return 'Short'

    # 신호 없음
    return None


if __name__ == "__main__":
    import pandas as pd
    data = {
        'close': [91841.2, 91762.9, 92070.0, 92260.9],
        'high': [91968.1, 91863.3, 92070.1, 92291.6],
        'low': [91770.6, 91717.8, 91601.0, 91972.9],
        'open': [91770.6, 91841.2, 91762.9, 92070.0],
        'ema': [91841.2, 91762.9, 92070.0, 92260.9],
        'atr_100': [324.005822, 322.220764, 323.689556, 323.639661]
    }
    df = pd.DataFrame(data)

    # 신호 계산
    df_with_signals = calculate_ut_bot_signals(df, a=4,debug=True)
    print(df_with_signals[['close', 'xATRTrailingStop', 'signal']])





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