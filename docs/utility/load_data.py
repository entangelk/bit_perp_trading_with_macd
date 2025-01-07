from pymongo import MongoClient
import pandas as pd

def load_data(set_timevalue, period=300):
    # MongoDB에 접속
    mongoClient = MongoClient("mongodb://mongodb:27017")
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
    elif set_timevalue == '30d':
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

    # 최신 period 개수만큼의 데이터만 반환
    df = df.iloc[-min(period, len(df)):]

    return df
