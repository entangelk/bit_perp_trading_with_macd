from pymongo import MongoClient
from docs.get_chart import chart_update
from docs.cal_position import cal_position
from collections import deque
import time

import sys
import os

# 프로젝트의 루트 디렉토리를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


# 초기 설정
symbol = "BTCUSDT"
leverage = 100
initial_usdt_amount = 10  # 초기 투자금
set_timevalue = '5m'

# 초기 차트 업데이트
chart_update(set_timevalue)

# position_dict 저장소, 최대 3개까지 저장하는 deque 설정
position_queue = deque(maxlen=3)

first_time_run_flag = True
start_counter = 3
repeat_counter = start_counter



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
for i in range(2):
    if first_time_run_flag:
        for i in range(repeat_counter):
            # position_dict 값 계산
            position_dict = cal_position(set_timevalue,start_counter)
            # position_dict를 position_queue에 추가 (3개 초과 시 자동으로 오래된 항목 삭제)
            position_queue.append(position_dict)
            start_counter -= 1
        first_time_run_flag = False
    else:
        # position_dict 값 계산
        position_dict = cal_position(set_timevalue,start_counter)

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

    # print("최종 업데이트된 position_list:", position_list)

    # 최종 신호 계산 및 결과 출력
    position = calculate_position(position_list)
    # print("최종 position:", position)



    # 포지션이 정해졌으니 이제 거래 요청 함수 짜면 됌
    # SL/TP는 만들어져있음
    # 테스트는... 어떻게 하지...?




    # 5분 대기
    # time.sleep(300)  # 300초 == 5분
