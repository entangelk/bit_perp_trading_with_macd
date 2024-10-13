from docs.get_chart import chart_update
from docs.get_current import fetch_investment_status
from docs.making_order import set_leverage, create_order_with_tp_sl, close_position
from docs.openai_utils import ai_choice
from docs.cal_pnl import cal_pnl
from docs.current_price import get_current_price

import time
import json
import schedule

# 초기 설정
symbol = "BTCUSDT"
leverage = 100
initial_usdt_amount = 10  # 초기 투자금
usdt_amount = initial_usdt_amount  # 현재 투자 금액
max_martingale_steps = 1  # 마틴게일 최대 단계 설정
current_step = 0  # 현재 마틴게일 단계

# 마틴게일 전략 실행 함수
def execute_trading():
    global usdt_amount, current_step

    # 차트 업데이트
    chart_update()

    # 내 포지션 정보 가져오기
    balance, positions_json, ledger = fetch_investment_status()

    # 포지션 상태 저장 (포지션이 open 상태일경우 True)
    positions_flag = True
    if positions_json == '[]' or positions_json is None:
        positions_flag = False

    # 마지막 거래 성공 여부 저장 (성공했을 시 True)
    trading_result = True 

    if not positions_flag:  # 포지션이 없을 때, 즉 새로운 거래를 생성할 때
        # 마지막 거래의 결과와 관계없이 초기화 (처음 실행할 때만)
        if current_step == 0:
            usdt_amount = initial_usdt_amount
            current_step = 0

        final_result = cal_pnl(ledger)
        
        # 마지막 거래 실패 여부 확인
        if final_result < 0:
            trading_result = False
            
            # 마틴게일 단계가 최대 단계보다 작은 경우만 투자금 증가
            if current_step < max_martingale_steps:
                usdt_amount *= 2
                current_step += 1
            else:
                print(f"최대 마틴게일 단계 {max_martingale_steps}에 도달했습니다. 투자 금액을 더 이상 늘리지 않습니다.")
        else:
            # 거래 성공 시 투자 금액을 초기화하고 마틴게일 단계도 초기화
            usdt_amount = initial_usdt_amount
            current_step = 0

        # 현재 가격 불러오기
        current_price = get_current_price(symbol=symbol)

        # 매수 또는 매도 결정
        side, decision = ai_choice(current_price)

        # 'stay'가 반환되면 주문 생성을 중단하고 함수 종료
        if side == 'stay':
            print("stay 상태입니다. 다음 턴까지 대기합니다.")
            return None, None

        # 레버리지 설정
        leverage_response = set_leverage(symbol, leverage)
        if leverage_response is None:
            print("레버리지 설정 실패. 주문 생성을 중단합니다.")
        else:
            # 주문 생성 함수 호출
            current_price = get_current_price(symbol=symbol)

            order_response = create_order_with_tp_sl(
                symbol=symbol,  # 거래할 심볼 (예: 'BTC/USDT')
                side=side,  # 'buy' 또는 'sell'
                usdt_amount=usdt_amount,  # 주문 수량
                leverage=leverage,  # 레버리지 100배
                tp_rate=0.20,  # 목표 수익률 20%
                sl_rate=0.20,  # 목표 손실률 20%
                current_price=current_price  # 현재 가격
            )
            if order_response is None:
                print("주문 생성 실패.")
            else:
                print(f"주문 성공: {order_response}")
    else:
        # 포지션이 있을 경우 이익 또는 손실을 확인
        positions_data = json.loads(positions_json)
        check_fee = float(positions_data[0]['info']['curRealisedPnl'])
        check_nowPnL = float(positions_data[0]['info']['unrealisedPnl'])
        total_pnl = check_nowPnL + (check_fee * 2) - 0.1

        # 이익이 발생한 경우: 포지션 종료 후 새로운 주문 생성
        if total_pnl > 0:
            # 기존 포지션 종료
            close_position(symbol=symbol)
            print("포지션 종료 성공")

            # 새로 매수 또는 매도 방향 결정 (기존 투자금 유지)
            current_price = get_current_price(symbol=symbol)

            side, decision = ai_choice(current_price)
            
            # 'stay'가 반환되면 주문 생성을 중단하고 함수 종료
            if side == 'stay':
                print("stay 상태입니다. 다음 턴까지 대기합니다.")
                return None, None

            # 동일한 투자금으로 새로운 주문 생성
            current_price = get_current_price(symbol=symbol)

            order_response = create_order_with_tp_sl(
                symbol=symbol,  # 거래할 심볼 (예: 'BTC/USDT')
                side=side,  # 'buy' 또는 'sell'
                usdt_amount=usdt_amount,  # 기존 투자금으로 수량 계산
                leverage=leverage,  # 레버리지 100배
                tp_rate=0.20,  # 목표 수익률 20%
                sl_rate=0.20,  # 목표 손실률 20%
                current_price=current_price  # 현재 가격
            )

            if order_response is None:
                print("재진입 주문 생성 실패.")
            else:
                print(f"재진입 주문 성공: {order_response}")

        else:
            # 손실 발생 시 포지션 유지
            print("손실 발생 중, 포지션 유지.")
            side = 'Wait and see'
            decision = 'No clear direction in time'

    return side, decision

# 5분마다 실행하는 함수 (schedule 라이브러리 사용)
def schedule_trading():
    schedule.every(5).minutes.do(execute_trading)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":

    test_count = 12
    for i in range(test_count):
        print(f"\n실행 {i+1}/{test_count}")
        side, decision = execute_trading()
        print(f"Position: {side}, Decision: {decision}")
        time.sleep(300)  # 5분(300초) 대기

    # fetch_investment_status()
    

# 트레이딩 스케줄 실행
# schedule_trading()

