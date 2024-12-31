import ccxt
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
import time

# 환경 변수 로드
load_dotenv()

# Bybit API 키와 시크릿 가져오기
BYBIT_ACCESS_KEY = os.getenv("BYBIT_ACCESS_KEY")
BYBIT_SECRET_KEY = os.getenv("BYBIT_SECRET_KEY")

# MongoDB에 접속
mongoClient = MongoClient("mongodb://mongodb:27017")
database = mongoClient["bitcoin"]
chart_collection_1m = database['chart_1m']
chart_collection_3m = database['chart_3m']
chart_collection_5m = database['chart_5m']
chart_collection_15m = database['chart_15m']

# Bybit 거래소 객체 생성 (recvWindow 값 조정)
bybit = ccxt.bybit({
    'apiKey': BYBIT_ACCESS_KEY,
    'secret': BYBIT_SECRET_KEY,
    'options': {
        'recvWindow': 5000,  # recvWindow 값을 5000으로 설정
    },
    'enableRateLimit': True
})


# Bybit 서버 시간 가져오기
server_time = bybit.fetch_time() / 1000
server_datetime = datetime.utcfromtimestamp(server_time)
print(f"서버 시간 (UTC): {server_datetime}")


def chart_update(update,symbol):
    """차트를 업데이트하고 MongoDB에 저장"""
    def fetch_and_store_ohlcv(collection, timeframe, symbol, limit, minutes_per_unit, time_description):
        # MongoDB에서 마지막으로 저장된 데이터의 타임스탬프 찾기
        last_saved_data = collection.find_one(sort=[("timestamp", -1)])
        if last_saved_data:
            last_timestamp = last_saved_data["timestamp"]
            print(f"{time_description} 마지막으로 저장된 데이터 시점: {last_timestamp}")
        else:
            # 저장된 데이터가 없으면 기본값을 과거로 설정 (ex: 7일 전)
            last_timestamp = server_datetime - timedelta(minutes=minutes_per_unit * limit)
            print(f"{time_description} 저장된 데이터가 없습니다. {limit}틱 전 시점부터 데이터를 가져옵니다.")

        since_timestamp = int(last_timestamp.timestamp() * 1000)  # 밀리초 단위 타임스탬프 변환

        # 데이터 가져오기 (Bybit 서버 시간 기반으로)
        try:
            ohlcv = bybit.fetch_ohlcv(symbol, timeframe, since=since_timestamp, limit=limit)
        except ccxt.InvalidNonce as e:
            print(f"InvalidNonce 오류 발생: {e}")
            return

        # MongoDB에 데이터 저장
        for data in ohlcv:
            timestamp = data[0]  # 타임스탬프 (밀리초)
            dt_object = datetime.utcfromtimestamp(timestamp / 1000)  # UTC 시간으로 변환
            open_price = data[1]
            high_price = data[2]
            low_price = data[3]
            close_price = data[4]
            volume = data[5]
            
            # 데이터 포맷
            data_dict = {
                "timestamp": dt_object,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume
            }

            collection.update_one({"timestamp": dt_object}, {"$set": data_dict}, upsert=True)
            print(f"{time_description} 저장된 데이터: {dt_object} - O: {open_price}, H: {high_price}, L: {low_price}, C: {close_price}, V: {volume}")

    # 심볼 설정
    symbol = symbol

    if update == '1m':
        # 1분봉 데이터 업데이트
        fetch_and_store_ohlcv(chart_collection_1m, '1m', symbol, limit=1440, minutes_per_unit=1, time_description="1분봉")
        return chart_collection_1m.find_one(sort=[("timestamp", -1)]), server_time

    elif update == '3m':
        # 3분봉 데이터 업데이트 (7일치)
        minutes_per_3m = 3
        limit_7d = (7 * 24 * 60) // minutes_per_3m
        fetch_and_store_ohlcv(chart_collection_3m, '3m', symbol, limit=limit_7d, minutes_per_unit=minutes_per_3m, time_description="3분봉")
        return chart_collection_3m.find_one(sort=[("timestamp", -1)]), server_time

    elif update == '5m':
        # 5분봉 (최근 1000틱 데이터 저장 및 업데이트)
        fetch_and_store_ohlcv(chart_collection_5m, '5m', symbol, limit=1000, minutes_per_unit=5, time_description="5분봉")
        return chart_collection_5m.find_one(sort=[("timestamp", -1)]), server_time

    elif update == '15m':
        # 15분봉 (최근 3500틱 데이터 저장 및 업데이트)
        fetch_and_store_ohlcv(chart_collection_15m, '15m', symbol, limit=3500, minutes_per_unit=15, time_description="15분봉")
        return chart_collection_15m.find_one(sort=[("timestamp", -1)]), server_time

    else:
        raise ValueError(f"Invalid update value: {update}")


def fetch_latest_ohlcv_and_update_db(symbol, timeframe, collection, max_check_time=240, check_interval=60):
    start_time = time.time()
    last_try_timestamp = None
    
    while (time.time() - start_time) < max_check_time:
        # Bybit에서 최신 2개 틱 데이터를 가져옴 (최신 것과 그 직전 것)
        ohlcv = bybit.fetch_ohlcv(symbol, timeframe, limit=2)
        complete_data = ohlcv[-2]  # 완성된 직전 캔들 선택
        timestamp = complete_data[0]
        dt_object = datetime.utcfromtimestamp(timestamp / 1000)  # UTC 시간으로 변환
        
        # 새로운 데이터 저장/업데이트
        data_dict = {
            "timestamp": dt_object,
            "open": complete_data[1],
            "high": complete_data[2],
            "low": complete_data[3],
            "close": complete_data[4],
            "volume": complete_data[5]
        }
        
        # MongoDB에 데이터 저장 (동일 타임스탬프여도 업데이트)
        collection.update_one(
            {"timestamp": dt_object}, 
            {"$set": data_dict}, 
            upsert=True
        )
        
        print(f"데이터가 성공적으로 저장/업데이트되었습니다: {data_dict}")
        break

def chart_update_one(update, symbol, max_check_time=240, check_interval=60):
    start_time = time.time()
    server_time = datetime.utcnow()
    
    try:
        # collection 매핑을 None 비교로 수정
        collection = None
        if update == '1m':
            collection = chart_collection_1m
        elif update == '3m':
            collection = chart_collection_3m
        elif update == '5m':
            collection = chart_collection_5m
        elif update == '15m':
            collection = chart_collection_15m
            
        if collection is None:
            raise ValueError(f"Invalid update value: {update}")
        
        fetch_latest_ohlcv_and_update_db(
            symbol=symbol,
            timeframe=update,
            collection=collection,
            max_check_time=max_check_time,
            check_interval=check_interval
        )
        
        result = collection.find_one(sort=[("timestamp", -1)])
        total_time = time.time() - start_time
        
        return result, server_time, total_time
        
    except Exception as e:
        total_time = time.time() - start_time
        print(f"오류 발생: {e}")
        return None, server_time, total_time
# 사용 예시
if __name__ == "__main__":
    update_type = '5m'  # '1m', '3m', '5m', '15m' 중 선택
    collection_map = {
        '1m': chart_collection_1m,
        '3m': chart_collection_3m,
        '5m': chart_collection_5m,
        '15m': chart_collection_15m
    }
    
    collection = collection_map.get(update_type)
    if collection:
        chart_update_one(update_type)
    else:
        print(f"유효하지 않은 업데이트 타입: {update_type}")
