from pymongo import MongoClient
# docs.get_chart 모듈을 임포트
from docs.get_chart import chart_update
from docs.cal_chart import process_chart_data
from docs.strategy.rsi_macd_stocastic import r_m_s

import time
import json
import schedule

# 초기 설정
symbol = "BTCUSDT"
leverage = 100
initial_usdt_amount = 10  # 초기 투자금
set_timevalue = '5m'

# 초기 차트 업데이트
chart_update()

# 데이터베이스 연결
mongoClient = MongoClient("mongodb://localhost:27017")
# 'bitcoin' 데이터베이스 연결
database = mongoClient["bitcoin"]

# set_timevalue 값에 따라 적절한 차트 컬렉션 선택
if set_timevalue == '1m':
    chart_collection = database['chart_1m']
elif set_timevalue == '3m':
    chart_collection = database['chart_3m']
elif set_timevalue == '5m':
    chart_collection = database['chart_5m']
elif set_timevalue == '15m':
    chart_collection = database['chart_15m']
elif set_timevalue == '1h':
    chart_collection = database['chart_1h']
elif set_timevalue == '30d':  # 30일을 분 단위로 계산 (30일 * 24시간 * 60분)
    chart_collection = database['chart_30d']
else:
    raise ValueError(f"Invalid time value: {set_timevalue}")

df = process_chart_data(chart_collection)
position = r_m_s(df)
print(position)