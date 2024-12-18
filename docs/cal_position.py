from docs.strategy.follow_line import follow_line
from docs.strategy.supertrend import supertrend
from docs.strategy.hma_strategy import check_hma_signals
from docs.strategy.squeeze_strategy import check_squeeze_signals

def cal_position(df):
    # 각 전략 계산
    df = follow_line(df)
    df = supertrend(df)
    df = check_hma_signals(df)
    
    # 포지션 결과를 저장할 딕셔너리 생성
    position_dict = {}
    
    # 이전 포지션과 비교하여 변화가 있을 때만 시그널 생성
    fl_position_changed = df['fl_position'] != df['fl_position'].shift(1)
    st_position_changed = df['st_position'] != df['st_position'].shift(1)
    hma_position_changed = df['signal_hma'] != df['signal_hma'].shift(1)
    
    # 포지션이 변경된 경우에만 딕셔너리에 저장
    if fl_position_changed.iloc[-1]:
        position_dict['Flow Line'] = df['fl_position'].iloc[-1]
    else:
        position_dict['Flow Line'] = None
        
    if st_position_changed.iloc[-1]:
        position_dict['super trend'] = df['st_position'].iloc[-1]
    else:
        position_dict['super trend'] = None

    if hma_position_changed.iloc[-1]:
        position_dict['hma_signal'] = df['signal_hma'].iloc[-1]
    else:
        position_dict['hma_signal'] = None
    
    print(df.index[-1])
    print(f'Flow Line : {position_dict["Flow Line"]}, super trend : {position_dict["super trend"]}, HMA : {position_dict["hma_signal"]}')
    
    # 순차적으로 포지션 덮어쓰기
    final_position = None
    
    # Flow Line 신호가 있으면 적용
    if position_dict['Flow Line'] is not None:
        final_position = position_dict['Flow Line']
    
    # Super Trend 신호가 있으면 적용
    if position_dict['super trend'] is not None:
        final_position = position_dict['super trend']
        
    # Flow Line과 Super Trend가 다른 방향을 가리키면 포지션 없음
    if (position_dict['Flow Line'] is not None and 
        position_dict['super trend'] is not None and 
        position_dict['Flow Line'] != position_dict['super trend']):
        final_position = None
    
    # HMA 신호가 있으면 마지막으로 적용
    if position_dict['hma_signal'] is not None:
        squeeze_signals = check_squeeze_signals(df)
        current = df.iloc[-1]
        
        # 기본 신호 준비
        signal = position_dict['hma_signal']  # 'Long' 또는 'Short'
                
        # 1. MACD 방향 확인
        macd_aligned = (signal == 'Long' and current['macd_diff'] > 0) or \
                    (signal == 'Short' and current['macd_diff'] < 0)
        
        # 2. 스퀴즈 방향 확인
        momentum_aligned = (signal == 'Long' and squeeze_signals['momentum']['color'] == 'EMERALD') or \
                        (signal == 'Short' and squeeze_signals['momentum']['color'] == 'RED')
        
        # 3. 스퀴즈 강도 확인
        strong_squeeze = squeeze_signals['squeeze']['state'] == 'YELLOW'
        
        # 모든 조건 확인
        if macd_aligned and momentum_aligned and strong_squeeze:
            final_position = 'hma_' + signal
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