import sys
import os
import pandas as pd
import time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from docs.cal_position import cal_position
from docs.cal_chart import process_chart_data

set_timevalue = '5m'

from pymongo import MongoClient

mongoClient = MongoClient("mongodb://mongodb:27017")
# mongoClient = MongoClient("mongodb://localhost:27017")

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

time.sleep(1)

chart_collections = {
    '1m': 'chart_1m',
    '3m': 'chart_3m',
    '5m': 'chart_5m',
    '15m': 'chart_15m',
    '1h': 'chart_1h',
    '30d': 'chart_30d'
}

if set_timevalue not in chart_collections:
    raise ValueError(f"Invalid time value: {set_timevalue}")

   

# 설정값 저장 및 업데이트

from datetime import datetime

def init_reverse_config(database):
    """초기 설정값 생성"""
    config_collection = database['config']
    
    initial_config = {
        'name': 'reverse_settings',
        'is_reverse': {
            'lr': False,  # line_position
            'vn': False,  # volume_position
            'sl': False,  # slop_position
            'sz': False,  # size_position
            'dv': False,  # dive_position
            'st': False   # st_position
        },
        'updated_at': datetime.now()
    }
    
    config_collection.update_one(
        {'name': 'reverse_settings'}, 
        {'$set': initial_config}, 
        upsert=True
    )
    return initial_config['is_reverse']

def load_reverse_config(database):
    """설정값 불러오기"""
    try:
        config_collection = database['config']
        config = config_collection.find_one({'name': 'reverse_settings'})
        if config and 'is_reverse' in config:
            return config['is_reverse']
        else:
            return init_reverse_config(database)
    except Exception as e:
        print(f"설정 로드 중 오류 발생: {e}")
        return init_reverse_config(database)


try:
    is_reverse = load_reverse_config(database)
except Exception as e:
    print(f"초기 설정 로드 실패: {e}")
    is_reverse = init_reverse_config(database)


import logging
from logging.handlers import RotatingFileHandler


# 로거 생성 및 레벨 설정 
logger = logging.getLogger('strategy_backtest')
logger.setLevel(logging.INFO)

# 핸들러 설정
handler = RotatingFileHandler(
   filename='strategy_backtest.log',
   maxBytes=10*1024*1024,  # 10MB
   backupCount=1,
   encoding='utf-8'
)
handler.setLevel(logging.INFO)

# 포맷터 설정
formatter = logging.Formatter('%(asctime)s - %(message)s')
# formatter = logging.Formatter('%(message)s')

handler.setFormatter(formatter)

# 핸들러를 로거에 추가
logger.addHandler(handler)


def evaluate_strategy(df, signal_column):
    """각 전략의 백테스팅 수행"""
    initial_capital = 10000000  # 1천만 달러 시작
    commission_rate = 0.00044   # 0.044%
    trigger_amount = 800        # 트리거 가격차이 800달러

    positions = df[signal_column].tolist()
    timestamps = df.index.tolist()
    current_position = None
    entry_price = 0
    entry_time = None
    position_size = 1
    capital = initial_capital
    wins = 0
    losses = 0
   
    for i in range(len(df) - 1):
        if current_position is None and positions[i] in ['Long', 'Short']:
            # 새로운 포지션 진입
            current_position = positions[i]
            entry_price = df['open'].iloc[i + 1]
            entry_time = timestamps[i + 1]
            
            # TP/SL 가격 설정
            if current_position == 'Long':
                tp_price = entry_price + trigger_amount
                sl_price = entry_price - trigger_amount
            else:  # Short
                tp_price = entry_price - trigger_amount
                sl_price = entry_price + trigger_amount
            
            # 진입 로그 기록
            logger.info(f"\n진입 시간: {entry_time}")
            logger.info(f"포지션: {current_position}")
            logger.info(f"진입가: {entry_price}")
            logger.info(f"TP 가격: {tp_price}")
            logger.info(f"SL 가격: {sl_price}")
            
            # 진입 수수료 계산
            commission = position_size * entry_price * commission_rate
            capital -= commission
            
        elif current_position:
            high = df['high'].iloc[i]
            low = df['low'].iloc[i]
            close = df['close'].iloc[i]
            open_price = df['open'].iloc[i]
            current_time = timestamps[i]
           
           # 청산 봉의 OHLC 로깅
            # logger.info(f"\n체크 봉 OHLC: 시간 {current_time} Open {open_price}, High {high}, Low {low}, Close {close}")
           
            # 동일 봉에서 TP와 SL을 모두 만족하는 경우 
            if current_position == 'Long' and (high >= tp_price and low <= sl_price):
                # 봉의 방향으로 판단
                candle_direction = 'up' if close > open_price else 'down'
                if candle_direction == 'up':  # 양봉이면 TP
                    profit = tp_price - entry_price
                    capital += profit
                    commission = position_size * tp_price * commission_rate
                    capital -= commission
                    wins += 1
                    logger.info(f"청산 시간: {current_time} - TP Hit (동일 봉 TPSL, 양봉)")
                    logger.info(f"청산가: {tp_price}")
                    logger.info(f"수익: {profit}")
                else:  # 음봉이면 SL
                    loss = sl_price - entry_price
                    capital += loss
                    commission = position_size * sl_price * commission_rate
                    capital -= commission
                    losses += 1
                    logger.info(f"청산 시간: {current_time} - SL Hit (동일 봉 TPSL, 음봉)")
                    logger.info(f"청산가: {sl_price}")
                    logger.info(f"손실: {loss}")
                logger.info(f"수수료: {commission}")
                current_position = None
                
            elif current_position == 'Short' and (low <= tp_price and high >= sl_price):
                # 봉의 방향으로 판단
                candle_direction = 'up' if close > open_price else 'down'
                if candle_direction == 'down':  # 음봉이면 TP
                    profit = entry_price - tp_price
                    capital += profit
                    commission = position_size * tp_price * commission_rate
                    capital -= commission
                    wins += 1
                    logger.info(f"청산 시간: {current_time} - TP Hit (동일 봉 TPSL, 음봉)")
                    logger.info(f"청산가: {tp_price}")
                    logger.info(f"수익: {profit}")
                else:  # 양봉이면 SL
                    loss = entry_price - sl_price
                    capital += loss
                    commission = position_size * sl_price * commission_rate
                    capital -= commission
                    losses += 1
                    logger.info(f"청산 시간: {current_time} - SL Hit (동일 봉 TPSL, 양봉)")
                    logger.info(f"청산가: {sl_price}")
                    logger.info(f"손실: {loss}")
                logger.info(f"수수료: {commission}")
                current_position = None
               
              # TP만 만족하는 경우
            elif (current_position == 'Long' and high >= tp_price) or \
                (current_position == 'Short' and low <= tp_price):
                if current_position == 'Long':
                    profit = tp_price - entry_price
                else:
                    profit = entry_price - tp_price
                capital += profit
                commission = position_size * tp_price * commission_rate
                capital -= commission
                wins += 1
                logger.info(f"청산 시간: {current_time} - TP Hit")
                logger.info(f"청산가: {tp_price}")
                logger.info(f"수익: {profit}")
                logger.info(f"수수료: {commission}")
                current_position = None
               
            # SL만 만족하는 경우  
            elif (current_position == 'Long' and low <= sl_price) or \
                (current_position == 'Short' and high >= sl_price):
                if current_position == 'Long':
                    loss = sl_price - entry_price
                else:
                    loss = entry_price - sl_price
                capital += loss
                commission = position_size * sl_price * commission_rate
                capital -= commission
                losses += 1
                logger.info(f"청산 시간: {current_time} - SL Hit")
                logger.info(f"청산가: {sl_price}")
                logger.info(f"손실: {loss}")
                logger.info(f"수수료: {commission}")
                current_position = None
   
    total_trades = wins + losses
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    total_pnl = capital - initial_capital

    logger.info(f"\n{'='*50}")
    logger.info(f"Strategy: {signal_column}")
    logger.info(f"Initial Capital: ${initial_capital:,.2f}")
    logger.info(f"Final Capital: ${capital:,.2f}")
    logger.info(f"Total PnL: ${total_pnl:,.2f}")
    logger.info(f"Total Trades: {total_trades}")
    logger.info(f"Wins: {wins}")
    logger.info(f"Losses: {losses}")
    logger.info(f"Win Rate: {win_rate:.2f}%")

    return win_rate, total_trades

def backtest_all_strategies(df_backtest):
    strategy_columns = {
        'lr': 'line_reg_signal',
        'dv': 'macd_dive_signal',
        'sz': 'macd_size_signal',
        'st': 'filtered_position'
    }
    
    results = {}
    
    for tag, column in strategy_columns.items():
        if column in df_backtest.columns:
            # 전략 테스트
            win_rate, total_trades = evaluate_strategy(df_backtest, column)
            # 거래가 있을 때만 리버스 여부 판단
            if total_trades > 0:
                results[tag] = win_rate < 50
            else:
                results[tag] = False  # 거래가 없으면 리버스 하지 않음
    
    return results

def run_daily_backtest():
    chart_collection = database[chart_collections[set_timevalue]] 
    while True:
        try:
            current_time = datetime.now()
            logger.info(f"\n{'='*50}")
            logger.info(f"백테스트 시작 시간: {current_time}")

            data_cursor = chart_collection.find().sort("timestamp", -1).skip(1)
            data_list = list(data_cursor)
            if data_list:
            

                df = pd.DataFrame(data_list)
                df['timestamp'] = pd.to_datetime(df['timestamp'])

                if '_id' in df.columns:
                    df.drop('_id', axis=1, inplace=True)

                df.set_index('timestamp', inplace=True)
                df.sort_index(inplace=True)
            else:
                from docs.get_chart import chart_update
                last_time, server_time = chart_update('5m','BTCUSDT')

                time.sleep(1)

                chart_collection = database[chart_collections[set_timevalue]]    

                data_cursor = chart_collection.find().sort("timestamp", -1)
                data_list = list(data_cursor)
                df = pd.DataFrame(data_list)
                df['timestamp'] = pd.to_datetime(df['timestamp'])

                if '_id' in df.columns:
                    df.drop('_id', axis=1, inplace=True)

                df.set_index('timestamp', inplace=True)
                df.sort_index(inplace=True)


            # 전략 계산

            df_rare_chart = df

            df_calculated, STG_CONFIG = process_chart_data(df_rare_chart)

            position, df_backtest, tag = cal_position(df=df_calculated, STG_CONFIG = STG_CONFIG)  # 포지션은 숏,롱,None, hma롱, hma숏

            # 백테스트 실행
            backtest_results = backtest_all_strategies(df_backtest)
            
            # 설정 업데이트
            for tag, should_reverse in backtest_results.items():
                is_reverse[tag] = should_reverse

            config_collection = database['config']
            config_collection.update_one(
                {'name': 'reverse_settings'},
                {'$set': {
                    'is_reverse': is_reverse,
                    'updated_at': datetime.now()
                }}
            )
            
            logger.info("백테스트 완료")
            
            # 24시간 대기
            time.sleep(24 * 60 * 60)
            
        except Exception as e:
            logger.error(f"백테스트 중 오류 발생: {e}")
            time.sleep(30)  # 오류 발생시 5분 후 재시도

# 실행
logger.info("백테스트 프로그램 시작")
run_daily_backtest()


    