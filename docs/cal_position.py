from docs.strategy.follow_line import follow_line
from docs.strategy.supertrend import supertrend
from docs.strategy.hma_strategy import check_hma_signals
from docs.strategy.squeeze_strategy import check_squeeze_signals
from docs.strategy.macd_stg import check_trade_signal
from docs.strategy.macd_di_slop import generate_macd_di_rsi_signal
from docs.strategy.macd_size_di import generate_macd_size_signal
from docs.strategy.macd_divergence import generate_macd_dive_signal
from docs.strategy.volume_norm import check_VSTG_signal
from docs.strategy.line_reg import check_line_reg_signal
import json
def cal_position(df, STG_CONFIG):
    # 전략 활성화 설정
    STRATEGY_ENABLE = {
        'SUPERTREND': True,      # 슈퍼트렌드 전략
        'LINE_REGRESSION': True,  # 선형회귀 전략
        'VOLUME_NORM': False,      # 볼륨 정규화 전략
        'MACD_DI_RSI': False,     # MACD-DI-RSI Slop 전략
        'MACD_SIZE': True,       # MACD 크기 전략
        'MACD_DIVERGENCE': True,  # MACD 다이버전스 전략
    }
    with open('/app/trading_bot/STRATEGY_ENABLE.json', 'w') as f:
        json.dump(STRATEGY_ENABLE, f)

    tag = None
    
    # 슈퍼트렌드 전략 실행
    if STRATEGY_ENABLE['SUPERTREND']:
        df = supertrend(df, STG_CONFIG)
        print("\n===== 포지션 계산 디버깅 =====")
        print(f"슈퍼트렌드 포지션: {df['st_position'].iloc[-1]}")

        # 슈퍼트랜드 필터링 적용
        di_diff_filter = STG_CONFIG['SUPERTREND']['DI_DIFFERENCE_FILTER']
        di_diff_lookback = STG_CONFIG['SUPERTREND']['DI_DIFFERENCE_LOOKBACK_PERIOD']

        # DI 차이와 4기간 평균
        df['di_diff'] = df['DI+_stg3'] - df['DI-_stg3']
        df['avg_di_diff'] = df['di_diff'].rolling(window=di_diff_lookback).mean()

        print(f"\n===== DI 지표 =====")
        print(f"DI+ 값: {df['DI+_stg3'].iloc[-1]:.2f}")
        print(f"DI- 값: {df['DI-_stg3'].iloc[-1]:.2f}")
        print(f"DI 차이: {df['di_diff'].iloc[-1]:.2f}")
        print(f"4기간 평균 DI 차이: {df['avg_di_diff'].iloc[-1]:.2f}")

        # 시그널 필터링
        df['filtered_position'] = None
        
        long_condition = (df['st_position'] == 'Long') & (df['avg_di_diff'] > di_diff_filter)
        short_condition = (df['st_position'] == 'Short') & (df['avg_di_diff'] < -di_diff_filter)
        
        df.loc[long_condition, 'filtered_position'] = 'Long'
        df.loc[short_condition, 'filtered_position'] = 'Short'

        st_position = df['filtered_position'].iloc[-1]
        print(f"\n===== 필터링 결과 =====")
        print(f"DI 필터 적용 포지션: {df['filtered_position'].iloc[-1]}")
    else:
        st_position = None

    if not st_position:
        print("\n===== 대체 시그널 확인 =====")
        
        line_position = None
        dive_position = None
        slop_position = None
        size_position = None
        volume_position = None

        # 각 전략 실행 (활성화된 경우에만)
        if STRATEGY_ENABLE['LINE_REGRESSION']:
            df = check_line_reg_signal(df, STG_CONFIG)
            line_position = df['line_reg_signal'].iloc[-1]
            print(f"선형회귀 시그널: {line_position}")

        if STRATEGY_ENABLE['MACD_DIVERGENCE']:
            df = generate_macd_dive_signal(df, STG_CONFIG)
            dive_position = df['macd_dive_signal'].iloc[-1]
            print(f"MACD 다이버전스 시그널: {dive_position}")

        if STRATEGY_ENABLE['MACD_DI_RSI']:
            slop_position = generate_macd_di_rsi_signal(df, STG_CONFIG, debug=True)
            print(f"MACD-DI-RSI 시그널: {slop_position}")

        if STRATEGY_ENABLE['MACD_SIZE']:
            df = generate_macd_size_signal(df, STG_CONFIG, debug=True)
            size_position = df['macd_size_signal'].iloc[-1]
            print(f"MACD 크기 시그널: {size_position}")

        if STRATEGY_ENABLE['VOLUME_NORM']:
            volume_position = check_VSTG_signal(df, STG_CONFIG)
            print(f"볼륨 정규화 시그널 : {volume_position}")

        # 우선순위에 따라 포지션 결정
        if line_position:
            position = line_position
            tag = 'lr'
        elif volume_position:
            position = volume_position
            tag = 'vn'
        elif slop_position:
            position = slop_position
            tag = 'sl'
        elif size_position:
            position = size_position
            tag = 'sz'
        elif dive_position:
            position = dive_position
            tag = 'dv'
        else:
            position = None
    else:
        position = st_position
        tag = 'st'

    print(f"\n===== 최종 포지션 =====")
    print(f"결정된 포지션: {tag}, {position}")

    return position, df, tag



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