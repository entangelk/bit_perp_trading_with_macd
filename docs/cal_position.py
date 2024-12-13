from docs.strategy.follow_line import follow_line
from docs.strategy.supertrend import supertrend

def cal_position(df):
   # 팔로우라인 계산
   df = follow_line(df)
   
   # 슈퍼트랜드 계산
   df = supertrend(df)
   
   # 포지션 결과를 저장할 딕셔너리 생성
   position_dict = {}
   
   # 이전 포지션과 비교하여 변화가 있을 때만 시그널 생성
   fl_position_changed = df['fl_position'] != df['fl_position'].shift(1)
   st_position_changed = df['st_position'] != df['st_position'].shift(1)
   
   # 포지션이 변경된 경우에만 딕셔너리에 저장
   if fl_position_changed.iloc[-1]:
       position_dict['Flow Line'] = df['fl_position'].iloc[-1]
   else:
       position_dict['Flow Line'] = None
       
   if st_position_changed.iloc[-1]:
       position_dict['super trend'] = df['st_position'].iloc[-1]
   else:
       position_dict['super trend'] = None
   
   print(df.index[-1])
   print(f'Flow Line : {position_dict["Flow Line"]}, super trend : {position_dict["super trend"]}')
   
   # position_dict의 값들을 리스트로 가져오기
   positions = list(position_dict.values())
   
   # 두 값이 같은 경우
   if positions[0] == positions[1]:
       final_position = positions[0]
   # Flow Line이 None인 경우 super trend 따름
   elif positions[0] is None:
       final_position = positions[1]
   # super trend가 None인 경우 Flow Line 따름
   elif positions[1] is None:
       final_position = positions[0]
   # 서로 다른 포지션인 경우(Long vs Short)
   else:
       final_position = None

   return final_position, df

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