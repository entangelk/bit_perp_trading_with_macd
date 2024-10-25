# import sys
# import os
# # 현재 파일이 위치한 경로의 상위 디렉토리를 모듈 경로에 추가
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


from docs.cal_chart import process_chart_data
from docs.strategy.rsi_macd_stocastic import r_m_s
from docs.strategy.zlma import zero_reg
from docs.strategy.flow_line import flow_line
from docs.strategy.tbrp import three_bar_ma, three_bar_donchian
from docs.strategy.supertrend import supertrend



def cal_position(set_timevalue,times_check):
    # 기본 사용 지표 계산
    df = process_chart_data(set_timevalue,times_check)
    
    # 포지션 결과를 저장할 딕셔너리 생성
    position_dict = {}

    # 각 전략의 포지션 확인
    position_dict['RMS'] = r_m_s(df)
    position_dict['ZLMA'] = zero_reg(df)
    position_dict['Flow Line'] = flow_line(df)
    position_dict['Three Bar Donchian'] = three_bar_donchian(df)
    position_dict['Three Bar MA'] = three_bar_ma(df)
    position_dict['Supertrend'] = supertrend(df)

    # print(df.index[-1])
    # 최종 포지션 딕셔너리 반환
    return position_dict





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