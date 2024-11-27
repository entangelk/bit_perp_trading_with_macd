from pymongo import MongoClient
import pandas as pd

def load_data(set_timevalue, period=300, last_day=0):
    # MongoDB에 접속
    mongoClient = MongoClient("mongodb://localhost:27017")
    database = mongoClient["bitcoin"]

    # set_timevalue 값에 따라 적절한 차트 컬렉션 선택
    if set_timevalue == '1m':
        chart_collection = database['chart_1m']
    elif set_timevalue == '3m':
        chart_collection = database['chart_3m']
    elif set_timevalue == '5m':
        chart_collection = database["chart_5m"]
    elif set_timevalue == '15m':
        chart_collection = database['chart_15m']
    elif set_timevalue == '1h':
        chart_collection = database['chart_1h']
    elif set_timevalue == '30d':  # 30일을 분 단위로 계산 (30일 * 24시간 * 60분)
        chart_collection = database['chart_30d']
    else:
        raise ValueError(f"Invalid time value: {set_timevalue}")
    
    # 최신 데이터부터 과거 데이터까지 모두 가져오기
    data_cursor = chart_collection.find().sort("timestamp", -1)
    data_list = list(data_cursor)

    # MongoDB 데이터를 DataFrame으로 변환
    df = pd.DataFrame(data_list)

    # 타임스탬프를 datetime 형식으로 변환
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # 불필요한 ObjectId 필드 제거
    if '_id' in df.columns:
        df.drop('_id', axis=1, inplace=True)

    # 인덱스를 타임스탬프로 설정
    df.set_index('timestamp', inplace=True)

    # 시간순으로 정렬 (오름차순으로 변환)
    df.sort_index(inplace=True)

    # `last_day`와 `period`에 따라 데이터 슬라이싱
    if last_day > 0:
        # 끝 데이터를 기준으로 과거로 `period`만큼 가져옴
        df = df.iloc[-(last_day + period):-last_day]
    else:
        # 최신 데이터에서 과거로 `period`만큼 가져옴
        df = df.iloc[-period:]

    return df
