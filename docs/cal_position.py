from docs.strategy.follow_line import follow_line
from docs.strategy.supertrend import supertrend
from docs.strategy.hma_strategy import check_hma_signals
from docs.strategy.squeeze_strategy import check_squeeze_signals
from docs.strategy.macd_stg import check_trade_signal
from docs.strategy.macd_di_slop import generate_macd_di_rsi_signal
from docs.strategy.macd_size_di import generate_macd_size_signal
from docs.strategy.macd_divergence import generate_macd_dive_signal
from docs.strategy.volume_norm import check_VSTG_signal

def cal_position(df):
    # 각 전략 계산
    # df = check_hma_signals(df)
    
    # df = follow_line(df)
    df = supertrend(df)
    print("\n===== 포지션 계산 디버깅 =====")
    print(f"슈퍼트렌드 포지션: {df['st_position'].iloc[-1]}")

    # 슈퍼트랜드 필터링 적용

    # DI 차이와 4기간 평균
    df['di_diff'] = df['DI+'] - df['DI-']
    df['avg_di_diff'] = df['di_diff'].rolling(window=4).mean()

    print(f"\n===== DI 지표 =====")
    print(f"DI+ 값: {df['DI+'].iloc[-1]:.2f}")
    print(f"DI- 값: {df['DI-'].iloc[-1]:.2f}")
    print(f"DI 차이: {df['di_diff'].iloc[-1]:.2f}")
    print(f"4기간 평균 DI 차이: {df['avg_di_diff'].iloc[-1]:.2f}")

    # 시그널 필터링 (DI difference threshold: 17)
    df['filtered_position'] = None
    
    long_condition = (df['st_position'] == 'Long') & (df['avg_di_diff'] > 17)
    short_condition = (df['st_position'] == 'Short') & (df['avg_di_diff'] < -17)
    
    df.loc[long_condition, 'filtered_position'] = 'Long'
    df.loc[short_condition, 'filtered_position'] = 'Short'

    st_position = df['filtered_position'].iloc[-1]
    print(f"\n===== 필터링 결과 =====")
    print(f"DI 필터 적용 포지션: {df['filtered_position'].iloc[-1]}")

    if not st_position:
        print("\n===== 대체 시그널 확인 =====")
        # macd_position = check_trade_signal(df)
        dive_position = generate_macd_dive_signal(df)
        slop_position = generate_macd_di_rsi_signal(df,debug=True)
        size_position = generate_macd_size_signal(df,debug=True)
        volume_position = check_VSTG_signal(df)
        print(f"MACD-DI-RSI 시그널: {slop_position}")
        print(f"MACD 크기 시그널: {size_position}")
        print(f"MACD 다이버전스 시그널: {dive_position}")
        print(f"볼륨 정규화 시그널 : {volume_position}")

        if volume_position:
            position = 'vn_' + volume_position
        elif slop_position:
            position = slop_position
        elif size_position:
            position = size_position
        elif dive_position:
            position = dive_position
        else:
            position = None
    else:
        position = 'st_' + st_position

    print(f"\n===== 최종 포지션 =====")
    print(f"결정된 포지션: {position}")

    '''
    macd 전략 테스트를 위해 macd 포지션만 리턴
    



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

    # 연속 시그널널
    position_dict['hma_signal'] = df['signal_hma'].iloc[-1]
 
    
    print(df.index[-1])
    print(f'Flow Line : {position_dict["Flow Line"]}, super trend : {position_dict["super trend"]}, HMA : {position_dict["hma_signal"]}')
    
    # 순차적으로 포지션 덮어쓰기
    final_position = None
    
    df = check_squeeze_signals(df)

    # HMA 신호가 있으면 마지막으로 적용
    if position_dict['hma_signal'] is not None:
        current = df.iloc[-1]
                
        # 기본 신호 준비
        signal = position_dict['hma_signal']  # 'Long' 또는 'Short'
                        
        # 1. MACD 방향 확인
        macd_aligned = (signal == 'Long' and current['macd_diff'] > 0) or \
                        (signal == 'Short' and current['macd_diff'] < 0)
                
        # 2. 스퀴즈 방향 확인
        momentum_aligned = (signal == 'Long' and current['squeeze_color'] == 'EMERALD') or \
                            (signal == 'Short' and current['squeeze_color'] == 'RED')
                
        # 3. 스퀴즈 강도 확인
        strong_squeeze = current['squeeze_state'] == 'YELLOW'
                
        # 모든 조건 확인
        if macd_aligned and momentum_aligned and strong_squeeze:
            print("\n[디버그] 포지션 결정 조건 확인:")
            print(f"1. MACD 정렬 상태: {macd_aligned} (현재 MACD 차이: {current['macd_diff']})")
            print(f"2. 모멘텀 방향 정렬: {momentum_aligned} (현재 색상: {current['squeeze_color']})")
            print(f"3. 스퀴즈 강도: {strong_squeeze} (현재 상태: {current['squeeze_state']})")
            print(f"최종 포지션: hma_{signal}")
            
            final_position = 'hma_' + signal
        else:
            print("\n[디버그] 포지션 결정 조건 불충족:")
            print(f"1. MACD 정렬 상태: {macd_aligned} (현재 MACD 차이: {current['macd_diff']})")
            print(f"2. 모멘텀 방향 정렬: {momentum_aligned} (현재 색상: {current['squeeze_color']})")
            print(f"3. 스퀴즈 강도: {strong_squeeze} (현재 상태: {current['squeeze_state']})")
            print("최종 포지션: None")
            
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
    '''

    return position, df



if __name__ == "__main__":
   from pymongo import MongoClient

   # 초기 설정
   symbol = "BTCUSDT"
   leverage = 100
   initial_usdt_amount = 10  # 초기 투자금
   set_timevalue = '5m'

   # 데이터베이스 연결
   mongoClient = MongoClient("mongodb://mongodb:27017")
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