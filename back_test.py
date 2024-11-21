from tqdm import tqdm
from docs.get_chart import chart_update, chart_update_one
from docs.cal_position import cal_position
from docs.get_current import fetch_investment_status
from docs.making_order import set_leverage, create_order_with_tp_sl, close_position,get_position_amount
from docs.utility.get_sl import set_sl
from docs.utility.cal_close import isclowstime
from docs.current_price import get_current_price
from datetime import datetime, timezone, timedelta
import time
import json
import sys
import os

# 프로젝트의 루트 디렉토리를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


# 초기 설정
symbol = "BTCUSDT"
leverage = 1
usdt_amount = 10  # 초기 투자금
set_timevalue = '5m'
tp_rate = 10000
stop_loss = 500


# 초기 차트 업데이트
last_time, server_time = chart_update(set_timevalue,symbol)

# last_time과 server_time이 튜플의 요소로 반환되었다고 가정
# UTC로 변환된 시간 사용
last_time = last_time['timestamp']
server_time = datetime.fromtimestamp(server_time, timezone.utc)  # server_time을 UTC로 변환

# 분 단위를 설정 (예: '1m' => 1분, '5m' => 5분)
time_values = {
    '1m': 1,
    '3m': 3,
    '5m': 5,
    '15m': 15
}
time_interval = time_values[set_timevalue]

def get_time_block(dt, interval):
    """datetime 객체를 interval 분 단위로 표현하는 함수"""
    return (dt.year, dt.month, dt.day, dt.hour, (dt.minute // interval) * interval)

# 서버 시간과 마지막 업데이트 시간이 time_interval 블록으로 일치하는지 확인
while get_time_block(server_time, time_interval) != get_time_block(last_time, time_interval):
    print(f"{set_timevalue} 차트 업데이트 중...")
    last_time, server_time = chart_update(set_timevalue,symbol)  # 차트 업데이트 함수 호출
    last_time = last_time['timestamp'].astimezone(timezone.utc)  # last_time을 UTC로 변환
    server_time = datetime.fromtimestamp(server_time, timezone.utc)  # server_time을 UTC로 변환
    time.sleep(60)  # 1분 대기 (API 요청 빈도 조절)
    # time.sleep(1)

print(f"{set_timevalue} 차트 업데이트 완료. 서버 시간과 일치합니다.")

def get_next_run_time(current_time, interval_minutes):
    """현재 시간을 interval 분 단위로 맞추고 10초 후 실행 시간을 반환"""
    # 현재 분을 interval에 맞춰 올림한 분으로 설정
    minute_block = (current_time.minute // interval_minutes + 1) * interval_minutes
    next_time = current_time.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minute_block)
    # return next_time + timedelta(seconds=10)
    return next_time

def start_signal_final_check(start_signal, df):
    """
    최종 신호 검증 함수.
    start_signal이 'Long', 'Short', 또는 'None' 중 하나일 때,
    추가 조건을 확인하고 신호를 검증합니다.
    """
    # DI+와 DI- 차이 계산
    di_difference = abs(df['DI+'].iloc[-1] - df['DI-'].iloc[-1])

    # 조건에 따라 신호 검증
    if start_signal == 'Long':
        # DI 차이가 10 이상이고, RSI 이동 평균이 양의 기울기인지 확인
        rsi_slope = df['rsi_sma'].iloc[-1] - df['rsi_sma'].iloc[-2]
        if di_difference >= 10 and rsi_slope > 0:
            return "Long"  # 조건 충족 시 최종 'Long' 신호 반환
    elif start_signal == 'Short':
        # DI 차이가 10 이상이고, RSI 이동 평균이 음의 기울기인지 확인
        rsi_slope = df['rsi_sma'].iloc[-1] - df['rsi_sma'].iloc[-2]
        if di_difference >= 10 and rsi_slope < 0:
            return "Short"  # 조건 충족 시 최종 'Short' 신호 반환
    
    # 조건에 맞지 않으면 None 반환
    return None


# 초기 레버리지 설정
leverage_response = set_leverage(symbol, leverage)
if leverage_response is None:
    print("레버리지 설정 실패. api 확인 요망")

signal_save_list = [None, None, None]
first_time_run_flag = True
signal_save_flag = False
save_signal = None
adx_flag_counter = 0

# while True:
test_time = 8
time_range = int(test_time * 60 / time_interval)
for i in range(time_range):
    # 현재 서버 시간으로 다음 실행 시간을 계산
    server_time = datetime.now(timezone.utc)
    next_run_time = get_next_run_time(server_time, time_interval)
    wait_seconds = (next_run_time - server_time).total_seconds()

    print(f"다음 실행 시간: {next_run_time} (대기 시간: {wait_seconds:.1f}초)")

    if wait_seconds > 0:
        with tqdm(total=int(wait_seconds), desc="싱크 조절 중", ncols=100, leave=True, dynamic_ncols=True) as pbar:
            for _ in range(int(wait_seconds)):
                time.sleep(1)
                pbar.update(1)

    time.sleep(1)

    # 차트 업데이트
    chart_update_one(set_timevalue, symbol)
    time.sleep(1)

    # position_dict 값 계산
    start_signal, position, df = cal_position(set_timevalue)

    # save_position_signal = position

    # 현재 start_signal이 None이면서 position에 신호가 발생한 경우
    if position:
        # 포지션 시그널 저장
        signal_save_list.pop(0)
        signal_save_list.append(position)
    else:
        # 포지션 시그널 저장
        signal_save_list.pop(0)
        signal_save_list.append(None)

    # start_signal에 따라 save_signal 값을 업데이트
    if start_signal is not None and start_signal != 'Reset':
        save_signal = start_signal
    elif start_signal == 'Reset':
        save_signal = None
    # None일 경우 이전에 저장된 save_signal 값을 그대로 유지

    print(f"현재 save_signal: {save_signal}")
    print(f"현재 position: {position}")


    # 조건 확인 및 유효 신호 확인
    if start_signal is not None and start_signal != 'Reset' and position is None:
        for signal in reversed(signal_save_list):
            if signal == start_signal:
                position = save_signal
                print(f"유효 신호 감지: Position '{position}' 후 Start Signal '{save_signal}' 발생")
                break
            elif position == 'Long' and signal == 'Short':
                position = None
                break
            elif position == 'Short' and signal == 'Long':
                position = None
                break


    # 내 포지션 정보 가져오기
    balance, positions_json, ledger = fetch_investment_status()

    # 포지션 상태 저장 (포지션이 open 상태일경우 True)
    positions_flag = True
    if positions_json == '[]' or positions_json is None:
        print('포지션 없음 -> 포지션 오픈 결정 단계 진행')
        positions_flag = False


    # 포지션이 있을경우 패스
    if positions_flag:
        # 포지션이 있을 경우 이익 또는 손실을 확인
        positions_data = json.loads(positions_json)
        check_fee = float(positions_data[0]['info']['curRealisedPnl'])
        check_nowPnL = float(positions_data[0]['info']['unrealisedPnl'])
        total_pnl = check_nowPnL + (check_fee * 2)

        print(f"현재 포지셔닝 중입니다. Pnl : {total_pnl}")

        current_amount,current_side,current_avgPrice = get_position_amount(symbol)

        # 포지션 값 설정
        if current_side == 'Buy':
            current_side = 'Long'
        elif current_side == 'Sell':
            current_side = 'Short'

        # 현 포지션과 반대 포지션 시그널 진입 시 청산
        if (current_side == 'Long' and position == 'Short') or \
        (current_side == 'Short' and position == 'Long'):
            close_position(symbol=symbol)

        # 조건에 의한 adx 상승까지 waiting flag 설정
        adx_flag = False

        adx_flag = df['ADX'].iloc[-1] > df['ADX'].iloc[-2]


        if adx_flag:
            adx_flag_counter += 1
            if adx_flag_counter >= 1:
                close_signal = False
                close_signal = isclowstime(df,current_side)
        
        if close_signal:
            adx_flag_counter = 0
            adx_flag = False
            close_position(symbol=symbol)
            print("포지션 종료 성공")
        else:
            print("최적 포지션 미도달, Stay")
    else:

        # 세이브된 시그널과 포지션이 서로 다를 경우 주문 생성 중지
        if save_signal != position:
            position = None  

        print(f'결정 포지션 : {position}')

        if position == "Long":

            # 스탑 로스는 오더 주문에서 설정
            # stop_loss = set_sl(df,position)

            # 주문 생성 함수 호출
            current_price = get_current_price(symbol=symbol)

            order_response = create_order_with_tp_sl(
                symbol=symbol,  # 거래할 심볼 (예: 'BTC/USDT')
                side="Buy",  # 'buy' 또는 'sell'
                usdt_amount=usdt_amount,  # 주문 수량
                leverage=leverage,  # 레버리지 100배
                current_price=current_price,  # 현재 가격
                stop_loss = stop_loss,
                tp_rate = tp_rate
            )
            if order_response is None:
                print("주문 생성 실패.")
            else:
                print(f"주문 성공: {order_response}")

        elif position == "Short":
            # stop_loss = set_sl(df,position)
            # 주문 생성 함수 호출
            current_price = get_current_price(symbol=symbol)

            order_response = create_order_with_tp_sl(
                symbol=symbol,  # 거래할 심볼 (예: 'BTC/USDT')
                side="Sell",  # 'buy' 또는 'sell'
                usdt_amount=usdt_amount,  # 주문 수량
                leverage=leverage,  # 레버리지 100배
                current_price=current_price,  # 현재 가격
                stop_loss = stop_loss,
                tp_rate = tp_rate
            )
            if order_response is None:
                print("주문 생성 실패.")
            else:
                print(f"주문 성공: {order_response}")
        else:
            pass


