from pymongo import MongoClient
# docs.get_chart 모듈을 임포트
from docs.get_chart import chart_update
from docs.cal_chart import process_chart_data
from docs.strategy.rsi_macd_stocastic import r_m_s
from docs.strategy.zlma import zero_reg
from docs.strategy.flow_line import flow_line
from docs.strategy.tbrp import three_bar
from docs.strategy.supertrend import supertrend


import time
import json
import schedule

# 초기 설정
symbol = "BTCUSDT"
leverage = 100
initial_usdt_amount = 10  # 초기 투자금
set_timevalue = '5m'

# 초기 차트 업데이트
chart_update(set_timevalue)

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

# 기본 사용 지표 계산
df = process_chart_data(chart_collection)

# RMS전략 확인
position_rms = r_m_s(df)
# zlma전략 확인
position_zlma = zero_reg(df)
# Flow line전략 확인
position_fl = flow_line(df)
# three_bar전략 확인
position_tbrp = three_bar(df)
# supertrend전략 확인
position_super = supertrend(df)


# print(position_rms,position_zlma,position_fl,position_tbrp)

# 마지막 250틱을 제외한 데이터만 사용
start_idx = len(df) - 250  # 250틱 이전 데이터를 기준으로 테스트 시작

# 각 전략을 테스트
for i in range(start_idx, len(df)):
    position_rms = r_m_s(df.iloc[:i+1])
    position_zlma = zero_reg(df.iloc[:i+1])
    position_fl = flow_line(df.iloc[:i+1])
    position_tbrp = three_bar(df.iloc[:i+1])
    position_super = supertrend(df.iloc[:i+1])


    # 결과 출력
    print(f"Timestamp: {df.index[i]}, RMS: {position_rms}, ZLMA: {position_zlma}, Flow Line: {position_fl}, Three Bar: {position_tbrp}, Super trend: {position_super}")