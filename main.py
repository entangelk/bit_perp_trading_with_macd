from pymongo import MongoClient
from docs.get_chart import chart_update
from docs.cal_position import cal_position
from collections import deque
import time

# 초기 설정
symbol = "BTCUSDT"
leverage = 100
initial_usdt_amount = 10  # 초기 투자금
set_timevalue = '5m'

# 초기 차트 업데이트
chart_update(set_timevalue)

# 데이터베이스 연결
mongoClient = MongoClient("mongodb://localhost:27017")
database = mongoClient["bitcoin"]

# set_timevalue 값에 따라 적절한 차트 컬렉션 선택
chart_collection_map = {
    '1m': 'chart_1m',
    '3m': 'chart_3m',
    '5m': 'chart_5m',
    '15m': 'chart_15m',
    '1h': 'chart_1h',
    '30d': 'chart_30d'
}

if set_timevalue not in chart_collection_map:
    raise ValueError(f"Invalid time value: {set_timevalue}")

chart_collection = database[chart_collection_map[set_timevalue]]

# position_dict 저장소, 최대 3개까지 저장하는 deque 설정
position_queue = deque(maxlen=3)

first_time_run_flag = True

while True:
    if first_time_run_flag:
        get_len = len(chart_collection)-3
        for i in range(get_len):
            # position_dict 값 계산
            position_dict = cal_position(chart_collection[:i+1])

            # position_dict를 position_queue에 추가 (3개 초과 시 자동으로 오래된 항목 삭제)
            position_queue.append(position_dict)

        first_time_run_flag = False
    else:
        # position_dict 값 계산
        position_dict = cal_position(chart_collection)

        # position_dict를 position_queue에 추가 (3개 초과 시 자동으로 오래된 항목 삭제)
        position_queue.append(position_dict)

    # 현재 position_queue 출력 (또는 다른 방식으로 사용 가능)
    print("현재 저장된 position_dict 리스트:")
    for idx, position in enumerate(position_queue):
        print(f"{idx + 1}: {position}")

    # 5분 대기
    time.sleep(300)  # 300초 == 5분
