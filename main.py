from pymongo import MongoClient
# docs.get_chart 모듈을 임포트
from docs.get_chart import chart_update

import time
import json
import schedule

# 초기 설정
symbol = "BTCUSDT"
leverage = 100
initial_usdt_amount = 10  # 초기 투자금

chart_update()

mongoClient = MongoClient("mongodb://localhost:27017")
# 'bitcoin' 데이터베이스 연결
database = mongoClient["bitcoin"]

# 'chart_1m', 'chart_5m', 'chart_15m', 'chart_1h', 'chart_30d' 컬렉션 작업
chart_collection_1m = database['chart_1m']
chart_collection_5m = database['chart_5m']
chart_collection_15m = database['chart_15m']
# chart_collection_1h = database['chart_1h']
# chart_collection_30d = database['chart_30d']

