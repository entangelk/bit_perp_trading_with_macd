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
import logging
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    filename='trading_bot.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=0,
    encoding='utf-8'
)

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
            logging.info(f"주문 성공: {order_response}")
            return True
        print("주문 생성 실패")
        logging.info(f"주문 실패")

        return False
    except Exception as e:
        print(f"주문 실행 중 오류 발생: {e}")
        logging.info(f"주문 실행 중 오류 발생: {e}")

        return False

def check_adx_di_trigger(df, di_threshold=3, adx_threshold=2.5, lookback=2):
    """
    ADX/DI 크로스오버 또는 근접 상태를 확인하여 매매 신호를 생성
    정확한 교차점 계산 로직 포함
    """
    if len(df) < lookback:
        print("데이터 길이 부족")
        return None
    
    # 현재 및 이전 값 가져오기
    current_di_plus = df['DI+'].iloc[-1]
    current_di_minus = df['DI-'].iloc[-1]
    prev_di_plus = df['DI+'].iloc[-2]
    prev_di_minus = df['DI-'].iloc[-2]
    
    print(f"\n=== DI 현재값 ===")
    print(f"DI+ 현재: {current_di_plus:.2f}, DI- 현재: {current_di_minus:.2f}")
    print(f"DI+ 이전: {prev_di_plus:.2f}, DI- 이전: {prev_di_minus:.2f}")
    
    current_adx = df['ADX'].iloc[-1]
    prev_adx = df['ADX'].iloc[-2]
    
    print(f"\n=== ADX 값 ===")
    print(f"ADX 현재: {current_adx:.2f}, ADX 이전: {prev_adx:.2f}")
    
    # 평균값 계산
    adx_avg = (current_adx + prev_adx) / 2
    current_di_avg = (current_di_plus + current_di_minus) / 2
    
    print(f"\n=== 평균값 ===")
    print(f"ADX 평균: {adx_avg:.2f}")
    print(f"현재 DI 평균: {current_di_avg:.2f}")
    
    # DI 차이 계산
    di_diff = current_di_plus - current_di_minus
    prev_di_diff = prev_di_plus - prev_di_minus
    
    print(f"\n=== DI 차이 ===")
    print(f"현재 DI 차이: {di_diff:.2f}")
    print(f"이전 DI 차이: {prev_di_diff:.2f}")
    
    # 교차 상태 확인
    crossover_long = (prev_di_plus < prev_di_minus) and (current_di_plus > current_di_minus)
    crossover_short = (prev_di_plus > prev_di_minus) and (current_di_plus < current_di_minus)
    
    print(f"\n=== 교차 상태 ===")
    print(f"롱 크로스오버: {crossover_long}")
    print(f"숏 크로스오버: {crossover_short}")
    
    # DI 근접 상태 확인
    # DI 근접 상태 확인
    proximity_long = (prev_di_plus > prev_di_minus) and abs(current_di_plus - current_di_minus) <= di_threshold
    proximity_short = (prev_di_plus < prev_di_minus) and abs(current_di_plus - current_di_minus) <= di_threshold
    
    print(f"\n=== 근접 상태 ===")
    print(f"롱 근접: {proximity_long} (임계값: {di_threshold})")
    print(f"숏 근접: {proximity_short} (임계값: {di_threshold})")
    
    # ADX 조건 확인 (수정된 로직)
    if crossover_long or crossover_short:
        # 교차 상황일 때
        di_plus_slope = current_di_plus - prev_di_plus
        di_minus_slope = current_di_minus - prev_di_minus
        x_intersect = (prev_di_minus - prev_di_plus) / (di_plus_slope - di_minus_slope)
        y_intersect = (di_plus_slope * x_intersect) + prev_di_plus
        
        cross_point = y_intersect
        
        # ADX 평균값이 교차점보다 낮으면 바로 트리거
        if adx_avg <= cross_point:
            adx_condition = True
        # ADX 평균값이 교차점보다 높으면 2.5 이내일 때만 트리거
        else:
            adx_condition = abs(adx_avg - cross_point) <= adx_threshold
            
        print(f"\n=== ADX 교차 조건 ===")
        print(f"교차 지점: {cross_point:.2f}")
        print(f"교차 시점: {x_intersect:.3f}")
        print(f"ADX 평균값: {adx_avg:.2f}")
        print(f"ADX-교차점 차이: {abs(adx_avg - cross_point):.2f}")
        
    elif proximity_long or proximity_short:
        # 근접 상황일 때
        higher_di = max(current_di_plus, current_di_minus)
        
        # 현재 ADX값이 큰 DI값보다 낮으면 바로 트리거
        if current_adx <= higher_di:
            adx_condition = True
        # 현재 ADX값이 큰 DI값보다 높으면 2.5 이내일 때만 트리거
        else:
            adx_condition = abs(current_adx - higher_di) <= adx_threshold
            
        print(f"\n=== ADX 근접 조건 ===")
        print(f"큰 DI값: {higher_di:.2f}")
        print(f"현재 ADX값: {current_adx:.2f}")
        print(f"ADX-DI 차이: {abs(current_adx - higher_di):.2f}")
    
    else:
        adx_condition = False

    print(f"ADX 조건 충족: {adx_condition}")
    
    # 트렌드 확인
    if lookback > 2:
        di_diffs = [df['DI+'].iloc[i] - df['DI-'].iloc[i] for i in range(-lookback, -1)]
        trend_consistent = all(d < 0 for d in di_diffs) if (crossover_long or proximity_long) else all(d > 0 for d in di_diffs)
        print(f"\n=== 트렌드 확인 ===")
        print(f"이전 {lookback}틱 DI 차이: {[f'{d:.2f}' for d in di_diffs]}")
    else:
        trend_consistent = True
    
    print(f"트렌드 일관성: {trend_consistent}")
    
    # 신호 생성
    if (crossover_long or proximity_long) and adx_condition and trend_consistent:
        print("\n=== 최종 신호: LONG ===")
        return 'long'
    elif (crossover_short or proximity_short) and adx_condition and trend_consistent:
        print("\n=== 최종 신호: SHORT ===")
        return 'short'
    
    print("\n=== 신호 없음 ===")
    return None


def main():
    # 초기 설정
    config = TRADING_CONFIG
    save_signal = None
    global trigger_first_active, trigger_first_count, position_first_active, position_first_count, position_save
    is_hma_trade = False  # HMA 단타 플래그
    squeeze_active = False  # 새로운 플래그

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
        logging.info(f"{config['set_timevalue']} 차트 업데이트 완료")
        
        # 레버리지 설정
        if not set_leverage(config['symbol'], config['leverage']):
            logging.info(f"레버리지 설정 실패")

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
            wait_seconds = (next_run_time - server_time).total_seconds() + 5 # 서버 렉 시간 고려 봉 마감 후 5초 진입입
            
            if wait_seconds > 0:
                with tqdm(total=int(wait_seconds), desc="싱크 조절 중", ncols=100) as pbar:
                    for _ in range(int(wait_seconds)):
                        time.sleep(1)
                        pbar.update(1)
            
            # 차트 데이터 업데이트
            result, update_server_time, execution_time = chart_update_one(config['set_timevalue'], config['symbol'])
            logging.info(f"{server_time} 차트 업데이트 완료")

            df_rare_chart = load_data(set_timevalue=config['set_timevalue'], 
                                    period=period, 
                                    last_day=(back_testing_count-last_day))
            df_calculated = process_chart_data(df_rare_chart)
            
            # 시그널 체크 먼저 수행
            position, df = cal_position(df=df_calculated)  # 포지션은 숏,롱,None, hma롱, hma숏




            # trigger_signal = check_adx_di_trigger(df)



            # 포지션 상태 확인
            balance, positions_json, ledger = fetch_investment_status()
            positions_flag = positions_json != '[]' and positions_json is not None

            if positions_flag:  # 포지션이 있는 경우
                positions_data = json.loads(positions_json)
                current_amount, current_side, current_avgPrice = get_position_amount(config['symbol'])
                current_side = 'Long' if current_side == 'Buy' else 'Short'
                
                '''
                    # HMA 거래 중 일반 시그널 체크
                if is_hma_trade:
                    if trigger_signal and not trigger_first_active:  
                        print("트리거 조건 충족, 카운트다운 시작")
                        trigger_first_active = True
                        trigger_first_count = 4
                        trigger_signal_type = trigger_signal  # 'long' 또는 'short'

                    if trigger_first_active:
                        print(f"트리거 선행 카운트다운: {trigger_first_count}틱 남음")
                        
                        if position:  # position은 'Long' 또는 'Short'
                            validated_position = validate_di_difference(df, position)
                            if validated_position:  # validated_position은 'Long' 또는 'Short' 또는 None
                                # 대소문자를 맞춰서 비교
                                if ((trigger_signal_type == 'long' and validated_position == 'Long') or 
                                    (trigger_signal_type == 'short' and validated_position == 'Short')):
                                    print(f"HMA 포지션 중 스탠다드 시그널 감지: SL/TP 조정")
                                                # 포지션 정보 조회
                                    amount, side, avgPrice = get_position_amount(symbol=config['symbol'])
                                    set_tp_sl(
                                        symbol=config['symbol'], 
                                        stop_loss=config['stop_loss'],
                                        take_profit=config['take_profit'], 
                                        avgPrice=avgPrice,  # Correctly named parameter
                                        side=side  # Include side parameter if required by the function
                                        )
                                    trigger_first_active = False
                                    trigger_first_count = 4
                    
                    trigger_first_count -= 1  
                    
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
                                print(f"HMA 포지션 중 스탠다드 시그널 감지: SL/TP 조정")
                                
                                amount, side, avgPrice = get_position_amount(symbol=config['symbol'])
                                set_tp_sl(
                                    symbol=config['symbol'], 
                                    stop_loss=config['stop_loss'],
                                    take_profit=config['take_profit'], 
                                    avgPrice=avgPrice,  # Correctly named parameter
                                    side=side  # Include side parameter if required by the function
                                    )
                                position_first_active = False
                                position_first_count = 2
                                position_save = None
                        
                        if position_first_count <= 0:
                            print("포지션 선행 윈도우 종료")
                            position_first_active = False
                            position_first_count = 2
                            position_save = None
                    
                    is_hma_trade = False # 세팅 후 플래그 초기화
                '''
                
                # 포지션 종료 조건 체크
                # should_close_position(current_side, position) or 
                if isclowstime(df, current_side):
                    close_position(symbol=config['symbol'])
                    logging.info(f"포지션 종료")

                    print("포지션 종료")
                    # 트리거 상태 초기화
                    is_hma_trade = False
                    trigger_first_active = False
                    trigger_first_count = 4
                    position_first_active = False
                    position_first_count = 2
                    position_save = None

            else:  # 포지션이 없는 경우
                if position:
                    stop_loss = config['stop_loss']
                    take_profit = config['take_profit']

                    if position[:3] == 'st_': # 슈퍼 트랜드일시 특별 tpsl사용용
                        position = position[3:]
                        stop_loss = 700
                        take_profit = 700
                    elif position[:3] == 'vn_':
                        position = position[:3]
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
                                
                '''
                # 케이스 1: 트리거 시그널 선행 (4틱)
                if trigger_signal and not trigger_first_active:  
                    print("트리거 조건 충족, 카운트다운 시작")
                    trigger_first_active = True
                    trigger_first_count = 4
                    trigger_signal_type = trigger_signal  # 'long' 또는 'short'

                if trigger_first_active:
                    print(f"트리거 선행 카운트다운: {trigger_first_count}틱 남음")
                    
                    if position:  # position은 'Long' 또는 'Short'
                        validated_position = validate_di_difference(df, position)
                        if validated_position:  # validated_position은 'Long' 또는 'Short' 또는 None
                            # 대소문자를 맞춰서 비교
                            if ((trigger_signal_type == 'long' and validated_position == 'Long') or 
                                (trigger_signal_type == 'short' and validated_position == 'Short')):
                                print(f"트리거 창 내 포지션 발생: {validated_position} 포지션 실행")
                                execute_order(
                                    symbol=config['symbol'],
                                    position=validated_position,  # 'Long' 또는 'Short' 전달
                                    usdt_amount=config['usdt_amount'],
                                    leverage=config['leverage'],
                                    stop_loss=config['stop_loss'],
                                    take_profit=config['take_profit']
                                )
                                trigger_first_active = False
                                trigger_first_count = 4
                    
                    trigger_first_count -= 1  
                    
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
                
                # 케이스 3: hma 단타
                if position in ['hma_Long','hma_Short']:
                    is_hma_trade = True  # HMA 단타 플래그

                    if squeeze_active:  # 이미 스퀴즈 거래가 활성화되어 있으면 스킵
                        print("스퀴즈 거래가 한번 진행되었습니다.")
                        continue

                    hma_position = position[4:]
                    squeeze_active = True  # 스퀴즈 거래 활성화
                    execute_order(
                                symbol=config['symbol'],
                                position=hma_position,  # position_save 사용
                                usdt_amount=config['usdt_amount'],
                                leverage=config['leverage'],
                                stop_loss=400,
                                take_profit=300
                            )
                    pass
                else:
                    # HMA 신호가 없는 경우 스퀴즈 플래그 리셋
                    squeeze_active = False
            '''
            remaining_time = 270 - execution_time

            # 남은 시간이 있다면 대기
            if remaining_time > 0:
                with tqdm(total=int(remaining_time), desc="대기 중", ncols=100) as pbar:
                    for _ in range(int(remaining_time)):
                        time.sleep(1)
                        pbar.update(1)
                                
                        back_testing_count -= 1
                        save_signal = position
            
    except Exception as e:
        print(f"오류 발생: {e}")
        logging.info(f"오류 발생: {e}")
        return False
if __name__ == "__main__":
    main()