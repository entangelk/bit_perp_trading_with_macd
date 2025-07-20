import ccxt
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
import time
import sys
import os
# trading_bot 디렉토리를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logger import logger

# 환경 변수 로드
load_dotenv()

# Bybit API 키와 시크릿 가져오기
BYBIT_ACCESS_KEY = os.getenv("BYBIT_ACCESS_KEY")
BYBIT_SECRET_KEY = os.getenv("BYBIT_SECRET_KEY")

# MongoDB에 접속
mongoClient = MongoClient("mongodb://mongodb:27017")
database = mongoClient["bitcoin"]
# Capped Collections 초기화
collections_config = {
    'chart_1m': {'size': 200 * 1500, 'max': 1500},  # 실시간 모니터링용
    'chart_3m': {'size': 200 * 2100, 'max': 2100},  # 7일치 보장
    'chart_5m': {'size': 200 * 2100, 'max': 2100},  # 7일치 보장
    'chart_15m': {'size': 200 * 1000, 'max': 1000}  # 7일치 충분
}
# 컬렉션 초기화
for collection_name, config in collections_config.items():
    if collection_name not in database.list_collection_names():
        database.create_collection(
            collection_name,
            capped=True,
            size=config['size'],
            max=config['max']
        )
        print(f"{collection_name} Capped Collection 생성됨")
    else:
        print(f"{collection_name} 컬렉션이 이미 존재함")

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





def chart_update(update,symbol):
    """차트를 업데이트하고 MongoDB에 저장"""

    # Bybit 서버 시간 가져오기 (재시도 처리 추가)
    max_retries = 3
    retry_delay = 10
    server_time = None

    for attempt in range(max_retries):
        try:
            server_time = bybit.fetch_time() / 1000  # 밀리초를 초 단위로 변환
            server_datetime = datetime.utcfromtimestamp(server_time)
            print(f"바이비트 서버 시간 (UTC): {server_datetime}")
            break  # 성공하면 루프 탈출
        except Exception as e:
            print(f"바이비트 서버 시간 가져오기 실패 (시도 {attempt+1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:  # 마지막 시도가 아니면 대기 후 재시도
                time.sleep(retry_delay)
            else:
                print(f"바이비트 서버 시간 가져오기 최종 실패: {str(e)}")
                # 모든 재시도 실패 시 현재 시간으로 대체
                server_time = time.time()  # 이미 초 단위로 반환됨
                server_datetime = datetime.utcfromtimestamp(server_time)
                print(f"로컬 시간으로 대체 (UTC): {server_datetime}")
                print("주의: 로컬 시간은 바이비트 서버 시간과 약간의 차이가 있을 수 있습니다")

    def fetch_and_store_ohlcv(collection, timeframe, symbol, limit, minutes_per_unit, time_description):
        # 기존 코드와 동일하지만 update_one 대신 insert_one 사용
        last_saved_data = collection.find_one(sort=[("timestamp", -1)])
        if last_saved_data:
            last_timestamp = last_saved_data["timestamp"]
            print(f"{time_description} 마지막으로 저장된 데이터 시점: {last_timestamp}")
        else:
            last_timestamp = server_datetime - timedelta(minutes=minutes_per_unit * limit)
            print(f"{time_description} 저장된 데이터가 없습니다. {limit}틱 전 시점부터 데이터를 가져옵니다.")

        since_timestamp = int(last_timestamp.timestamp() * 1000)

        try:
            ohlcv = bybit.fetch_ohlcv(symbol, timeframe, since=since_timestamp, limit=limit)
        except ccxt.InvalidNonce as e:
            print(f"InvalidNonce 오류 발생: {e}")
            return

        for data in ohlcv:
            timestamp = data[0]
            dt_object = datetime.utcfromtimestamp(timestamp / 1000)
            data_dict = {
                "timestamp": dt_object,
                "open": data[1],
                "high": data[2],
                "low": data[3],
                "close": data[4],
                "volume": data[5]
            }

            collection.delete_many({"timestamp": dt_object})
            # 올바른 방법
            collection.update_one(
                {"timestamp": dt_object},     # 이 타임스탬프를 가진 문서를 찾아서
                {"$set": data_dict},         # 이 데이터로 업데이트하거나
                upsert=True                  # 없으면 새로 만들어라
            )
            print(f"{time_description} 저장된 데이터: {dt_object} - O: {data[1]}, H: {data[2]}, L: {data[3]}, C: {data[4]}, V: {data[5]}")

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
        fetch_and_store_ohlcv(chart_collection_5m, '5m', symbol, limit=2000, minutes_per_unit=5, time_description="5분봉")
        return chart_collection_5m.find_one(sort=[("timestamp", -1)]), server_time

    elif update == '15m':
        # 15분봉 (최근 3500틱 데이터 저장 및 업데이트)
        fetch_and_store_ohlcv(chart_collection_15m, '15m', symbol, limit=1000, minutes_per_unit=15, time_description="15분봉")
        return chart_collection_15m.find_one(sort=[("timestamp", -1)]), server_time

    else:
        raise ValueError(f"Invalid update value: {update}")


def fetch_latest_ohlcv_and_update_db(symbol, timeframe, collection, max_check_time=240, check_interval=60):
    start_time = time.time()
    
    while (time.time() - start_time) < max_check_time:
        ohlcv = bybit.fetch_ohlcv(symbol, timeframe, limit=2)
        
        saved_times = []  # 저장된 시간을 기록할 리스트
        # 두 캔들 모두 저장
        for candle in ohlcv:
            timestamp = candle[0]
            dt_object = datetime.utcfromtimestamp(timestamp / 1000)
            saved_times.append(dt_object)  # 변환된 시간 저장
            
            data_dict = {
                "timestamp": dt_object,
                "open": candle[1],
                "high": candle[2],
                "low": candle[3],
                "close": candle[4],
                "volume": candle[5]
            }
            
            collection.update_one(
                {"timestamp": dt_object}, 
                {"$set": data_dict}, 
                upsert=True
            )
            
        logger.info(f"최근 2개 캔들 업데이트 완료: {saved_times}")
        break

def chart_update_one(update, symbol, max_check_time=240, check_interval=60):
    start_time = time.time()  # 이건 실행 시간 체크용으로만 사용
    server_time = None  # 기본값 설정

    try:
        # Bybit 서버 시간 가져오기 (재시도 처리 추가)
        max_retries = 3
        retry_delay = 10
        server_time = None

        for attempt in range(max_retries):
            try:
                server_time = bybit.fetch_time() / 1000  # 밀리초를 초 단위로 변환
                server_datetime = datetime.utcfromtimestamp(server_time)
                print(f"바이비트 서버 시간 (UTC): {server_datetime}")
                break  # 성공하면 루프 탈출
            except Exception as e:
                print(f"바이비트 서버 시간 가져오기 실패 (시도 {attempt+1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:  # 마지막 시도가 아니면 대기 후 재시도
                    time.sleep(retry_delay)
                else:
                    print(f"바이비트 서버 시간 가져오기 최종 실패: {str(e)}")
                    # 모든 재시도 실패 시 현재 시간으로 대체
                    server_time = time.time()  # 이미 초 단위로 반환됨
                    server_datetime = datetime.utcfromtimestamp(server_time)
                    print(f"로컬 시간으로 대체 (UTC): {server_datetime}")
                    print("주의: 로컬 시간은 바이비트 서버 시간과 약간의 차이가 있을 수 있습니다")

        # collection 매핑
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
        
        # 업데이트 수행
        fetch_latest_ohlcv_and_update_db(
            symbol=symbol,
            timeframe=update,
            collection=collection,
            max_check_time=max_check_time,
            check_interval=check_interval
        )
        
        # 업데이트 결과 확인
        result = collection.find_one(sort=[("timestamp", -1)])
        if result is None:
            raise Exception("No data found after update")
            
        total_time = time.time() - start_time
        return True, server_time, total_time
        
    except Exception as e:
        total_time = time.time() - start_time
        logger.error(f"차트 업데이트 오류: {str(e)}")  # print 대신 logger.error 사용
        return False, server_time, total_time  # server_time은 None일 수 있음
    
    
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
    pass