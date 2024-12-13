# import sys
# import os
# # 현재 파일이 위치한 경로의 상위 디렉토리를 모듈 경로에 추가
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


from docs.cal_chart import process_chart_data
from docs.strategy.ut_bot import calculate_ut_bot_signal
from docs.strategy.follow_line import flow_line
from docs.strategy.adx_di import adx_di_signal
from docs.strategy.macd_stg import macd_stg



def cal_position(set_timevalue):
    # 기본 사용 지표 계산
    df = process_chart_data(set_timevalue)
    
    # 포지션 오픈 시그널 확인
    start_signal = adx_di_signal(df)

    # 포지션 결과를 저장할 딕셔너리 생성
    position_dict = {}

    # 각 전략의 포지션 확인
    position_dict['Flow Line'] = flow_line(df)
    position_dict['ut bot'] = calculate_ut_bot_signal(df)
    position_dict['macd stg'] = macd_stg(df)

    print(f'Flow Line : {position_dict["Flow Line"]}')
    print(f'ut bot : {position_dict["ut bot"]}')
    print(f'macd stg : {position_dict["macd stg"]}')


    # None을 제외한 'Long', 'Short' 포지션의 개수를 계산
    long_count = sum(1 for pos in position_dict.values() if pos == 'Long')
    short_count = sum(1 for pos in position_dict.values() if pos == 'Short')

    # 가장 많은 포지션을 반환
    if long_count > short_count:
        final_position = 'Long'
    elif short_count > long_count:
        final_position = 'Short'
    else:
        final_position = None  # 동률이거나 모든 값이 None일 경우

    # 최종 포지션 딕셔너리와 결과 반환
    return start_signal,final_position,df






if __name__ == "__main__":
    from pymongo import MongoClient

    # 초기 설정
    symbol = "BTCUSDT"
    leverage = 100
    initial_usdt_amount = 10  # 초기 투자금
    set_timevalue = '5m'

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
    
    cal_position(chart_collection)
    pass