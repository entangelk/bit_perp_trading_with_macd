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
# take_profit,stop_loss 전부 달러 기준임.
# usdt_amount는 0~1 계정 내 사용할 수 있는 USDT양의 퍼센테이지로 설정 1이면 전체체
TRADING_CONFIG = {
    'symbol': 'BTCUSDT',
    'leverage': 5,
    'usdt_amount': 0.1,
    'set_timevalue': '5m',
    'take_profit': 500,
    'stop_loss': 500
}

TIME_VALUES = {
    '1m': 1,
    '3m': 3,
    '5m': 5,
    '15m': 15
}

def get_time_block(dt, interval):
    """datetime 객체를 interval 분 단위로 표현"""
    return (dt.year, dt.month, dt.day, dt.hour, (dt.minute // interval) * interval)

def get_next_run_time(current_time, interval_minutes):
    """다음 실행 시간 계산"""
    minute_block = (current_time.minute // interval_minutes + 1) * interval_minutes
    next_time = current_time.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minute_block)
    return next_time

def check_adx_di_trigger(df, threshold=2.5):  # threshold는 DI 간의 근접 정도를 정의
    """ADX/DI 교차 또는 근접 트리거 체크"""
    current_di_plus = df['DI+'].iloc[-1]
    current_di_minus = df['DI-'].iloc[-1]
    prev_di_plus = df['DI+'].iloc[-2]
    prev_di_minus = df['DI-'].iloc[-2]
    
    current_adx = df['ADX'].iloc[-1]
    prev_adx = df['ADX'].iloc[-2]
    adx_avg = (current_adx + prev_adx) / 2
    
    # 교차 체크
    di_cross = ((prev_di_plus < prev_di_minus and current_di_plus > current_di_minus) or 
                (prev_di_plus > prev_di_minus and current_di_plus < current_di_minus))
    
    # 근접도 체크
    di_close = abs(current_di_plus - current_di_minus) <= threshold
    
    if di_cross or di_close:
        cross_di_avg = (current_di_plus + current_di_minus) / 2
        return adx_avg < cross_di_avg
    return False

def validate_di_difference(df, position):
    """DI 차이 검증"""
    if not position:
        return None
    di_diff = abs(df['DI+'].iloc[-1] - df['DI-'].iloc[-1])
    return position if di_diff >= 10 else None

def should_close_position(current_side, new_position):
    """포지션 청산 여부 확인"""
    return ((current_side == 'Long' and new_position == 'Short') or 
            (current_side == 'Short' and new_position == 'Long'))

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

# 전역 변수
trigger_active = False
trigger_count = 4

def check_adx_di_trigger(df, threshold=2.5):
    """ADX/DI 교차 또는 근접 트리거 체크 (롱/숏 구분)"""
    current_di_plus = df['DI+'].iloc[-1]
    current_di_minus = df['DI-'].iloc[-1]
    prev_di_plus = df['DI+'].iloc[-2]
    prev_di_minus = df['DI-'].iloc[-2]
    
    current_adx = df['ADX'].iloc[-1]
    prev_adx = df['ADX'].iloc[-2]
    adx_avg = (current_adx + prev_adx) / 2
    
    # DI 차이 계산
    di_diff = current_di_plus - current_di_minus
    prev_di_diff = prev_di_plus - prev_di_minus
    
    # 교차 또는 근접 여부 체크 및 방향 판단
    long_signal = (
        (prev_di_diff < 0 and di_diff > 0) or  # 상향 교차
        (prev_di_diff < 0 and abs(di_diff) <= threshold)  # DI- 우세인 상태에서 근접
    )
    
    short_signal = (
        (prev_di_diff > 0 and di_diff < 0) or  # 하향 교차
        (prev_di_diff > 0 and abs(di_diff) <= threshold)  # DI+ 우세인 상태에서 근접
    )
    
    cross_di_avg = (current_di_plus + current_di_minus) / 2
    adx_condition = adx_avg < cross_di_avg
    
    if long_signal and adx_condition:
        return 'long'
    elif short_signal and adx_condition:
        return 'short'
    return None

def main():
    # 초기 설정
    config = TRADING_CONFIG
    save_signal = None
    
    # 초기 차트 동기화
    try:
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
        last_day = 0    # 0일때 최신데이터
        back_testing_count = 0 # 0일때 실제 거래 루프 시작
        
        # 메인 루프
        while True:
        # for i in range(back_testing_count):
            # 다음 실행 시간 계산 및 대기
            server_time = datetime.now(timezone.utc)
            next_run_time = get_next_run_time(server_time, TIME_VALUES[config['set_timevalue']])
            wait_seconds = (next_run_time - server_time).total_seconds()
            
            if wait_seconds > 0:
                with tqdm(total=int(wait_seconds), desc="싱크 조절 중", ncols=100) as pbar:
                    for _ in range(int(wait_seconds)):
                        time.sleep(1)
                        pbar.update(1)
                        
            # 차트 업데이트 및 데이터 처리
            chart_update_one(config['set_timevalue'], config['symbol'])
            df_rare_chart = load_data(set_timevalue=config['set_timevalue'], 
                                    period=period, 
                                    last_day=(back_testing_count-last_day))
            df_calculated = process_chart_data(df_rare_chart)
            
            # 포지션 시그널 계산
            position, df = cal_position(df=df_calculated)
            trigger_signal = check_adx_di_trigger(df)  # 'long', 'short', None 중 하나 반환

            # 시그널 검증
            if position and trigger_signal:
                # position과 trigger_signal의 방향이 일치하는지 확인
                if ((position == 'Long' and trigger_signal == 'long') or 
                    (position == 'Short' and trigger_signal == 'short')):
                    position = validate_di_difference(df, position)
                else:
                    position = None  # 방향이 불일치하면 시그널 무시

            # 포지션 관리
            balance, positions_json, ledger = fetch_investment_status()
            positions_flag = positions_json != '[]' and positions_json is not None

            if positions_flag:
                positions_data = json.loads(positions_json)
                check_fee = float(positions_data[0]['info']['curRealisedPnl'])
                check_nowPnL = float(positions_data[0]['info']['unrealisedPnl'])
                total_pnl = check_nowPnL + (check_fee * 2)
                print(f"현재 포지셔닝 중입니다. Pnl : {total_pnl}")
                
                current_amount, current_side, current_avgPrice = get_position_amount(config['symbol'])
                current_side = 'Long' if current_side == 'Buy' else 'Short'
                
                # 포지션 청산 조건 체크
                if should_close_position(current_side, position) or isclowstime(df, current_side):
                    close_position(symbol=config['symbol'])
                    print("포지션 종료")
                else:
                    print("최적 포지션 미도달, Stay")
            else:
                if save_signal != position:
                    position = None
                
                print(f'결정 포지션 : {position}')
                
                if position in ['Long', 'Short']:
                    execute_order(
                        symbol=config['symbol'],
                        position=position,
                        usdt_amount=config['usdt_amount'],
                        leverage=config['leverage'],
                        stop_loss=config['stop_loss'],
                        take_profit=config['take_profit']
                    )
            
            # 대기
            with tqdm(total=270, desc="대기 중", ncols=100) as pbar:
                for _ in range(270):
                    time.sleep(1)
                    pbar.update(1)
                    
            back_testing_count -= 1
            
    except Exception as e:
        print(f"오류 발생: {e}")
        return False
        
if __name__ == "__main__":
    main()