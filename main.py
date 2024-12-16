from tqdm import tqdm
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

# 프로젝트 루트 디렉토리 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 설정값
TRADING_CONFIG = {
    'symbol': 'BTCUSDT',
    'leverage': 5,
    'usdt_amount': 0.1,
    'set_timevalue': '5m',
    'take_profit': 1000,
    'stop_loss': 500
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

def should_close_position(current_side, new_position):
    """포지션 청산 여부 확인"""
    return ((current_side == 'Long' and new_position == 'Short') or 
            (current_side == 'Short' and new_position == 'Long'))

def validate_di_difference(df, position):
    """DI 차이 검증"""
    if not position:
        return None
    di_diff = abs(df['DI+'].iloc[-1] - df['DI-'].iloc[-1])
    return position if di_diff >= 10 else None

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
            return True
        print("주문 생성 실패")
        return False
    except Exception as e:
        print(f"주문 실행 중 오류 발생: {e}")
        return False

def check_adx_di_trigger(df, di_threshold=2.5, adx_threshold=2.5, lookback=2):
    """
    ADX/DI 크로스오버 또는 근접 상태를 확인하여 매매 신호를 생성
    """
    if len(df) < lookback:
        return None
        
    # 현재 및 이전 값 가져오기
    current_di_plus = df['DI+'].iloc[-1]
    current_di_minus = df['DI-'].iloc[-1]
    prev_di_plus = df['DI+'].iloc[-2]
    prev_di_minus = df['DI-'].iloc[-2]
    
    current_adx = df['ADX'].iloc[-1]
    prev_adx = df['ADX'].iloc[-2]
    
    # 평균값 계산
    adx_avg = (current_adx + prev_adx) / 2
    current_di_avg = (current_di_plus + current_di_minus) / 2
    
    # DI 차이 계산
    di_diff = current_di_plus - current_di_minus
    prev_di_diff = prev_di_plus - prev_di_minus
    
    # 교차 상태 확인
    crossover_long = prev_di_diff < 0 and di_diff > 0
    crossover_short = prev_di_diff > 0 and di_diff < 0
    
    # DI 근접 상태 확인
    proximity_long = prev_di_diff < 0 and abs(di_diff) <= di_threshold
    proximity_short = prev_di_diff > 0 and abs(di_diff) <= di_threshold
    
    # 교차와 근접 상황에 따른 ADX 조건 확인
    if crossover_long or crossover_short:
        cross_point = min(current_di_plus, current_di_minus)
        adx_condition = abs(adx_avg - cross_point) <= adx_threshold
    else:
        adx_condition = abs(adx_avg - current_di_avg) <= adx_threshold
    
    # 트렌드 확인
    if lookback > 2:
        di_diffs = [df['DI+'].iloc[i] - df['DI-'].iloc[i] for i in range(-lookback, -1)]
        trend_consistent = all(d < 0 for d in di_diffs) if (crossover_long or proximity_long) else all(d > 0 for d in di_diffs)
    else:
        trend_consistent = True
    
    # 신호 생성
    if (crossover_long or proximity_long) and adx_condition and trend_consistent:
        return 'long'
    elif (crossover_short or proximity_short) and adx_condition and trend_consistent:
        return 'short'
    
    return None

def main():
    # 초기 설정
    config = TRADING_CONFIG
    save_signal = None
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
        
        # 레버리지 설정
        if not set_leverage(config['symbol'], config['leverage']):
            raise Exception("레버리지 설정 실패")
            
        # 백테스팅 설정
        period = 300
        last_day = 0
        back_testing_count = 0
        
        # 메인 루프
        while True:
            # 시간 동기화
            server_time = datetime.now(timezone.utc)
            next_run_time = get_next_run_time(server_time, TIME_VALUES[config['set_timevalue']])
            wait_seconds = (next_run_time - server_time).total_seconds()
            
            if wait_seconds > 0:
                with tqdm(total=int(wait_seconds), desc="싱크 조절 중", ncols=100) as pbar:
                    for _ in range(int(wait_seconds)):
                        time.sleep(1)
                        pbar.update(1)
            
            # 차트 데이터 업데이트
            chart_update_one(config['set_timevalue'], config['symbol'])
            df_rare_chart = load_data(set_timevalue=config['set_timevalue'], 
                                    period=period, 
                                    last_day=(back_testing_count-last_day))
            df_calculated = process_chart_data(df_rare_chart)
            
            # 시그널 체크 먼저 수행
            position, df = cal_position(df=df_calculated)
            trigger_signal = check_adx_di_trigger(df)

            # 포지션 상태 확인
            balance, positions_json, ledger = fetch_investment_status()
            positions_flag = positions_json != '[]' and positions_json is not None

            if positions_flag:  # 포지션이 있는 경우
                positions_data = json.loads(positions_json)
                current_amount, current_side, current_avgPrice = get_position_amount(config['symbol'])
                current_side = 'Long' if current_side == 'Buy' else 'Short'
                
                # 포지션 종료 조건 체크
                if should_close_position(current_side, position) or isclowstime(df, current_side):
                    close_position(symbol=config['symbol'])
                    print("포지션 종료")
                    # 트리거 상태 초기화
                    trigger_first_active = False
                    trigger_first_count = 4
                    position_first_active = False
                    position_first_count = 2
                    position_save = None

            else:  # 포지션이 없는 경우
                # 케이스 1: 트리거 시그널 선행 (4틱)
                if trigger_signal:
                    print("트리거 조건 충족, 카운트다운 시작")
                    trigger_first_active = True
                    trigger_first_count = 4

                if trigger_first_active:
                    trigger_first_count -= 1
                    print(f"트리거 선행 카운트다운: {trigger_first_count}틱 남음")
                    
                    if position:
                        validated_position = validate_di_difference(df, position)
                        if validated_position:
                            print(f"트리거 창 내 포지션 발생: {validated_position} 포지션 실행")
                            execute_order(
                                symbol=config['symbol'],
                                position=validated_position,  # validated_position 사용
                                usdt_amount=config['usdt_amount'],
                                leverage=config['leverage'],
                                stop_loss=config['stop_loss'],
                                take_profit=config['take_profit']
                            )
                            trigger_first_active = False
                            trigger_first_count = 4
                    
                    if trigger_first_count <= 0:
                        print("트리거 선행 윈도우 종료")
                        trigger_first_active = False
                        trigger_first_count = 4

                # 케이스 2: 포지션 신호 선행 (2틱)
                if position and not position_first_active and not trigger_first_active:  # 트리거 선행이 없을 때만
                    validated_position = validate_di_difference(df, position)
                    if validated_position:
                        print("포지션 신호 발생, 카운트다운 시작 (2틱)")
                        position_first_active = True
                        position_first_count = 2
                        position_save = validated_position

                if position_first_active:
                    position_first_count -= 1
                    print(f"포지션 선행 카운트다운: {position_first_count}틱 남음")
                    
                    if trigger_signal:
                        if ((position_save == 'Long' and trigger_signal == 'long') or 
                            (position_save == 'Short' and trigger_signal == 'short')):
                            print(f"포지션 창 내 트리거 발생: {position_save} 포지션 실행")
                            execute_order(
                                symbol=config['symbol'],
                                position=position_save,  # position_save 사용
                                usdt_amount=config['usdt_amount'],
                                leverage=config['leverage'],
                                stop_loss=config['stop_loss'],
                                take_profit=config['take_profit']
                            )
                            position_first_active = False
                            position_first_count = 2
                            position_save = None
                    
                    if position_first_count <= 0:
                        print("포지션 선행 윈도우 종료")
                        position_first_active = False
                        position_first_count = 2
                        position_save = None
            
            # 대기
            with tqdm(total=270, desc="대기 중", ncols=100) as pbar:
                for _ in range(270):
                    time.sleep(1)
                    pbar.update(1)
                    
            back_testing_count -= 1
            save_signal = position
            
    except Exception as e:
        print(f"오류 발생: {e}")
        return False
if __name__ == "__main__":
    main()