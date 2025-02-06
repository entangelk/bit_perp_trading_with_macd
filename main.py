from tqdm import tqdm
from docs.making_order import set_tp_sl
from docs.get_chart import chart_update, chart_update_one
from docs.cal_chart import process_chart_data
from docs.cal_position import cal_position
from docs.get_current import fetch_investment_status
from docs.making_order import set_leverage, create_order_with_tp_sl, close_position, get_position_amount
from docs.strategy.adx_di import adx_di_signal
from docs.utility.get_sl import set_sl
from docs.utility.cal_close import isclowstime
from docs.current_price import get_current_price
from docs.utility.load_data import load_data
from datetime import datetime, timezone, timedelta
import time
import json
import sys
import os
from logger import logger

# 프로젝트 루트 디렉토리 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 설정값
TRADING_CONFIG = {
    'symbol': 'BTCUSDT',
    'leverage': 5,
    'usdt_amount': 0.3,
    'set_timevalue': '5m',
    'take_profit': 400,
    'stop_loss': 400
}

TIME_VALUES = {
    '1m': 1,
    '3m': 3,
    '5m': 5,
    '15m': 15
}

# 전역 변수 수정
trigger_first_active = False  # 트리거 시그널 선행
trigger_first_count = 4

position_first_active = False  # 포지션 신호 선행
position_first_count = 2  # 2틱으로 수정
position_save = None

def get_time_block(dt, interval):
    """datetime 객체를 interval 분 단위로 표현"""
    return (dt.year, dt.month, dt.day, dt.hour, (dt.minute // interval) * interval)

def get_next_run_time(current_time, interval_minutes):
    """다음 실행 시간 계산"""
    minute_block = (current_time.minute // interval_minutes + 1) * interval_minutes
    next_time = current_time.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minute_block)
    return next_time

def execute_order(symbol, position, usdt_amount, leverage, stop_loss, take_profit):
    """주문 실행"""
    try:
        current_price = get_current_price(symbol=symbol)
        side = "Buy" if position == "Long" else "Sell"
        
        order_response = create_order_with_tp_sl(
            symbol=symbol,
            side=side,
            usdt_amount=usdt_amount,
            leverage=leverage,
            current_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit
        )
        
        if order_response:
            print(f"주문 성공: {order_response}")
            logger.info(f"주문 성공: {order_response}")
            return True
        
        print("주문 생성 실패")
        logger.info(f"주문 생성 실패 재시도 : {symbol}, {side}, {usdt_amount}, {leverage}, {current_price}, {stop_loss}, {take_profit}")

        order_response = create_order_with_tp_sl(
            symbol=symbol,
            side=side,
            usdt_amount=usdt_amount,
            leverage=leverage,
            current_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit
        )
        
        if order_response:
            print(f"주문 성공: {order_response}")
            logger.info(f"주문 성공: {order_response}")
            return True
        
        print("주문 생성 실패")
        logger.info(f"주문 재생성 실패 : {order_response}")

        return False
    except Exception as e:
        print(f"주문 실행 중 오류 발생: {e}")
        logger.info(f"주문 실행 중 오류 발생: {e}", exc_info=True)

        return False
def try_update_with_check(config, max_retries=3):
    for attempt in range(max_retries):
        # 기존 반환값 유지 (result, server_time, execution_time)
        result, server_time, execution_time = chart_update_one(config['set_timevalue'], config['symbol'])
        if result is None:
            logger.error(f"차트 업데이트 실패 (시도 {attempt + 1}/{max_retries})")
            continue
            
        # 데이터 로드 시도 (서버 시간 전달)
        df_rare_chart = load_data(
            set_timevalue=config['set_timevalue'], 
            period=300,
            server_time=server_time
        )
        
        if df_rare_chart is not None:
            return result, server_time, execution_time  # 기존 반환값 유지
            
        logger.warning(f"데이터 시간 불일치, 재시도... (시도 {attempt + 1}/{max_retries})")
        time.sleep(5)  # 잠시 대기
        
    return None, server_time, execution_time  # 실패시에도 기존 형식 유지

def main():
    # 초기 설정
    config = TRADING_CONFIG
    stg_tag = None
    stg_side = None
    global trigger_first_active, trigger_first_count, position_first_active, position_first_count, position_save


    try:
        # 초기 차트 동기화
        last_time, server_time = chart_update(config['set_timevalue'], config['symbol'])
        last_time = last_time['timestamp']
        server_time = datetime.fromtimestamp(server_time, timezone.utc)
        
        while get_time_block(server_time, TIME_VALUES[config['set_timevalue']]) != get_time_block(last_time, TIME_VALUES[config['set_timevalue']]):
            print(f"{config['set_timevalue']} 차트 업데이트 중...")
            last_time, server_time = chart_update(config['set_timevalue'], config['symbol'])
            last_time = last_time['timestamp'].astimezone(timezone.utc)
            server_time = datetime.fromtimestamp(server_time, timezone.utc)
            time.sleep(60)
            
        print(f"{config['set_timevalue']} 차트 업데이트 완료")
        logger.info(f"{config['set_timevalue']} 차트 업데이트 완료")
        
        # # 레버리지 설정
        # if not set_leverage(config['symbol'], config['leverage']):
        #     logger.info(f"레버리지 설정 실패")

        #     raise Exception("레버리지 설정 실패")
            
        
        # 메인 루프
        while True:
            # 시간 동기화
            server_time = datetime.now(timezone.utc)
            next_run_time = get_next_run_time(server_time, TIME_VALUES[config['set_timevalue']])
            wait_seconds = (next_run_time - server_time).total_seconds() + 5 # 서버 렉 시간 고려 봉 마감 후 5초 진입입
            
            if wait_seconds > 0:
                with tqdm(total=int(wait_seconds), desc="싱크 조절 중", ncols=100) as pbar:
                    for _ in range(int(wait_seconds)):
                        time.sleep(1)
                        pbar.update(1)
            
            # 차트 데이터 업데이트 (재시도 포함)
            result, update_server_time, execution_time = try_update_with_check(config)
            if result is None:
                logger.error("최대 재시도 횟수 초과, 프로세스 종료")
                return

            df_rare_chart = load_data(set_timevalue=config['set_timevalue'], period=300)
            if df_rare_chart is None or df_rare_chart.empty:
                logger.error("데이터 로드 실패: 데이터가 비어있습니다")
                return
            
            # 데이터 정합성을 위한 대기
            time.sleep(1.0)  # 1초 대기

            df_calculated, STG_CONFIG = process_chart_data(df_rare_chart)
            


            # 시그널 체크 먼저 수행
            try:
                position, df, tag = cal_position(df=df_calculated, STG_CONFIG = STG_CONFIG)  # 포지션은 숏,롱,None, hma롱, hma숏
            except:
                logger.info(f"포지션 계산 오류")



            # 포지션 상태 확인
            balance, positions_json, ledger = fetch_investment_status()

            error_time = 0
            if balance == 'error':
                logger.info(f"오류 발생: 상태 확인 api 호출 오류", exc_info=True)
                
                for i in range(24):
                    print("API 호출 실패, 5초 후 재시도합니다...")

                    time.sleep(5)
                    error_time += 5
                    balance, positions_json, ledger = fetch_investment_status()

                    
                    if balance != 'error':
                        logger.info(f"api 호출 재시도 성공", exc_info=True)
                        break
                else:
                    logger.info(f"api 호출 오류 3분 재시도 실패", exc_info=True)
                    

            positions_flag = positions_json != '[]' and positions_json is not None

            if positions_flag:  # 포지션이 있는 경우
                positions_data = json.loads(positions_json)
                current_amount, current_side, current_avgPrice = get_position_amount(config['symbol'])
                current_side = 'Long' if current_side == 'Buy' else 'Short'

                
                # 포지션 종료 조건 체크
                # should_close_position(current_side, position) or 
                if isclowstime(df, current_side):
                    close_position(symbol=config['symbol'])
                    logger.info(f"포지션 종료")

                    print("포지션 종료")
                    # 트리거 상태 초기화

                    trigger_first_active = False
                    trigger_first_count = 4
                    position_first_active = False
                    position_first_count = 2
                    position_save = None
                    stg_tag = None
                    stg_side = None

                if position:
                    if stg_side != position: # 반대 신호가 나타났을때 종료 후 전환
                        close_position(symbol=config['symbol'])
                        logger.info(f"반대 신호 포지션 종료")

                        print("포지션 종료")
                        time.sleep(1)
                        
                        stop_loss = config['stop_loss']
                        take_profit = config['take_profit']
                        stg_tag = tag # 태그 저장
                        stg_side = position # 포지션 저장

                        if tag == 'st': # 슈퍼 트랜드일시 특별 tpsl사용용
                            stop_loss = 700
                            take_profit = 700
                        elif tag == 'vn' or tag == 'lr' or tag == 'sz' or tag == 'dv':
                            stop_loss = 800
                            take_profit = 800



                        execute_order(
                            symbol=config['symbol'],
                            position=position,  # position_save 사용
                            usdt_amount=config['usdt_amount'],
                            leverage=config['leverage'],
                            stop_loss=stop_loss,
                            take_profit=take_profit
                        )                                        
                        trigger_first_active = False
                        trigger_first_count = 4
                        position_first_active = False
                        position_first_count = 2
                        position_save = None
                        stg_tag = None
                        stg_side = None

            else:  # 포지션이 없는 경우
                stg_tag = None
                stg_side = None
                if position:
                    stop_loss = config['stop_loss']
                    take_profit = config['take_profit']
                    stg_tag = tag # 태그 저장
                    stg_side = position # 포지션 저장

                    if tag == 'st': # 슈퍼 트랜드일시 특별 tpsl사용용
                        stop_loss = 700
                        take_profit = 700
                    elif tag == 'vn' or tag == 'lr' or tag == 'sz' or tag == 'dv':
                        stop_loss = 800
                        take_profit = 800


                    execute_order(
                        symbol=config['symbol'],
                        position=position,  # position_save 사용
                        usdt_amount=config['usdt_amount'],
                        leverage=config['leverage'],
                        stop_loss=stop_loss,
                        take_profit=take_profit
                    )
                    position_first_active = False
                    position_first_count = 2
                    position_save = None


            remaining_time = 269 - (execution_time + error_time)

            # 남은 시간이 있다면 대기
            if remaining_time > 0:
                with tqdm(total=int(remaining_time), desc="대기 중", ncols=100) as pbar:
                    for _ in range(int(remaining_time)):
                        time.sleep(1)
                        pbar.update(1)
                                
                        save_signal = position
            
    except Exception as e:
        print(f"오류 발생: {e}")
        logger.info(f"오류 발생: {e}", exc_info=True)
        return False
    
if __name__ == "__main__":
    main()