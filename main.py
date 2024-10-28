from tqdm import tqdm
from docs.get_chart import chart_update, chart_update_one
from docs.cal_position import cal_position
from docs.get_current import fetch_investment_status
from docs.making_order import set_leverage, create_order_with_tp_sl, close_position
from docs.utility.get_sl import set_sl
from docs.current_price import get_current_price
from datetime import datetime, timezone, timedelta
from collections import deque
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
tp_rate = 1.5

# 첫 실행시 3개의 데이터 쌓고 시작
first_time_run_flag = True
start_counter = 3
repeat_counter = start_counter




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
    # time.sleep(60)  # 1분 대기 (API 요청 빈도 조절)
    time.sleep(1)

print(f"{set_timevalue} 차트 업데이트 완료. 서버 시간과 일치합니다.")

def get_next_run_time(current_time, interval_minutes):
    """현재 시간을 interval 분 단위로 맞추고 10초 후 실행 시간을 반환"""
    # 현재 분을 interval에 맞춰 올림한 분으로 설정
    minute_block = (current_time.minute // interval_minutes + 1) * interval_minutes
    next_time = current_time.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minute_block)
    # return next_time + timedelta(seconds=10)
    return next_time



# 초기 레버리지 설정
leverage_response = set_leverage(symbol, leverage)
if leverage_response is None:
    print("레버리지 설정 실패. 주문 생성을 중단합니다.")

# position_dict 저장소, 최대 3개까지 저장하는 deque 설정
position_queue = deque(maxlen=3)





# 최소 3개의 신호가 일치하는지 확인하는 함수
def calculate_position(queue):
    # 신호 초기화

    final_signal = None


    long_count = queue.count('Long')
    short_count = queue.count('Short')

    # 최소 3개의 신호가 동일할 때 최종 신호 설정
    if long_count >= 3:
        final_signal = 'Long'
    elif short_count >= 3:
        final_signal = 'Short'
    
    # 최종 신호 반환
    return final_signal

# while True:

test_time = 8
time_range = int(test_time*60/time_interval)
for i in range(time_range):
    # 현재 서버 시간으로 다음 실행 시간을 계산
    server_time = datetime.now(timezone.utc)
    next_run_time = get_next_run_time(server_time, time_interval)  # time_interval은 분 단위로 사용
    wait_seconds = (next_run_time - server_time).total_seconds()

    print(f"다음 실행 시간: {next_run_time} (대기 시간: {wait_seconds:.1f}초)")

    if wait_seconds > 0:
        with tqdm(total=int(wait_seconds), desc="대기 중", ncols=100, leave=True, dynamic_ncols=True) as pbar:
            for _ in range(int(wait_seconds)):
                time.sleep(1)  # 1초 대기
                pbar.update(1)  # 진행바 업데이트

    time.sleep(1)

    chart_update_one(set_timevalue,symbol)


    if first_time_run_flag:
        for i in range(repeat_counter):
            # position_dict 값 계산
            position_dict,df = cal_position(set_timevalue,start_counter)
            # position_dict를 position_queue에 추가 (3개 초과 시 자동으로 오래된 항목 삭제)
            position_queue.append(position_dict)
            start_counter -= 1
        first_time_run_flag = False
    else:
        # position_dict 값 계산
        position_dict,df = cal_position(set_timevalue,start_counter)

        # position_dict를 position_queue에 추가 (3개 초과 시 자동으로 오래된 항목 삭제)
        position_queue.append(position_dict)


    select_list = []

    # 각 딕셔너리를 리스트로 변환하여 select_list에 추가
    for data in position_queue:
        temp_list = []
        for k, v in data.items():
            temp_list.append(v)
        select_list.append(temp_list)

    # 마지막 리스트 가져오기
    position_list = select_list[-1]

    # None이 있는 곳을 이전 값으로 채우기
    for idx, i in enumerate(position_list):
        if i is None:
            # 이전 리스트들에서 None이 아닌 첫 번째 값으로 대체
            for prev_list in reversed(select_list[:-1]):  # 마지막을 제외한 리스트들 순회
                if prev_list[idx] is not None:
                    position_list[idx] = prev_list[idx]
                    break  # None이 아닌 값을 찾으면 해당 위치는 업데이트 완료

    print("최종 업데이트된 position_list:", position_list)




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
                # 이익이 발생한 경우: 포지션 종료 후 새로운 주문 생성
        if total_pnl > 10:
            # 기존 포지션 종료
            close_position(symbol=symbol)
            print("포지션 종료 성공")

            # 새로 매수 또는 매도 방향 결정 (기존 투자금 유지)
            current_price = get_current_price(symbol=symbol)

            # 최종 신호 계산 및 결과 출력
            position = calculate_position(position_list)
            
            # 'stay'가 반환되면 주문 생성을 중단하고 함수 종료
            if position == None:
                print("stay 상태입니다. 다음 턴까지 대기합니다.")

            # 포지션이 결정되어 있을 경우 주문 재생성
            else:
                stop_loss = set_sl(df,position)
                # 주문 생성 함수 호출
                current_price = get_current_price(symbol=symbol)

                order_response = create_order_with_tp_sl(
                    symbol=symbol,  # 거래할 심볼 (예: 'BTC/USDT')
                    side=position,  # 'buy' 또는 'sell'
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
            # 손실 발생 시 포지션 유지
            print("손실 발생 중, 포지션 유지.")
            side = 'Wait and see'
            decision = 'No clear direction in time'

    else:
        # 최종 신호 계산 및 결과 출력
        position = calculate_position(position_list)
        # print("최종 position:", position)

        print(f'결정 포지션 : {position}')

        if position == "Long":
            stop_loss = set_sl(df,position)
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
            stop_loss = set_sl(df,position)
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





    # 총 대기 시간과 업데이트 주기 설정
    total_time = 270  # 총 대기 시간 (초 단위) 4분 30초
    update_interval = 1  # 진행 상황 업데이트 주기 (10초마다)

    # 진행바 초기화, leave=True로 완료 후에도 표시 유지, dynamic_ncols=True로 터미널 너비 자동 조정
    with tqdm(total=total_time, desc="대기 중", ncols=100, leave=True, dynamic_ncols=True) as pbar:
        for _ in range(total_time // update_interval):
            time.sleep(update_interval)
            pbar.update(update_interval)
