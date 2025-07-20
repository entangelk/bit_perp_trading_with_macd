#!/usr/bin/env python3
"""
AI 기반 자동 트레이딩 메인 실행 파일
- 15분마다 데이터 수집 및 AI 분석 실행
- AI 분석 결과만 기반으로 거래 결정
- 규칙 기반 분석 사용하지 않음
"""

from tqdm import tqdm
from datetime import datetime, timezone, timedelta
import time
import json
import sys
import os
import asyncio
from logger import logger

# 프로젝트 루트 디렉토리 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 기존 시스템 함수들
from docs.get_chart import chart_update, chart_update_one
from docs.get_current import fetch_investment_status
from docs.making_order import set_leverage, create_order_with_tp_sl, close_position, get_position_amount
from docs.current_price import get_current_price
from docs.utility.load_data import load_data
from docs.utility.trade_logger import TradeLogger

# AI 시스템 함수들
from docs.investment_ai.ai_trading_integration import execute_ai_trading_cycle
from docs.investment_ai.data_scheduler import run_scheduled_data_collection, get_data_status, get_recovery_status

# 설정값 (15분 간격으로 변경)
TRADING_CONFIG = {
    'symbol': 'BTCUSDT',
    'leverage': 5,
    'usdt_amount': 0.3,
    'set_timevalue': '15m',  # 15분으로 변경 (AI 최적화된 주기)
    'take_profit': 400,
    'stop_loss': 400
}

TIME_VALUES = {
    '1m': 1,
    '3m': 3,
    '5m': 5,
    '15m': 15
}

# API 키
BYBIT_ACCESS_KEY = os.getenv("BYBIT_ACCESS_KEY")
BYBIT_SECRET_KEY = os.getenv("BYBIT_SECRET_KEY")

api_key = BYBIT_ACCESS_KEY
api_secret = BYBIT_SECRET_KEY

trade_logger = TradeLogger()

def get_time_block(dt, interval):
    """datetime 객체를 interval 분 단위로 표현"""
    return (dt.year, dt.month, dt.day, dt.hour, (dt.minute // interval) * interval)

def get_next_run_time(current_time, interval_minutes):
    """다음 실행 시간 계산"""
    minute_block = (current_time.minute // interval_minutes + 1) * interval_minutes
    next_time = current_time.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minute_block)
    return next_time

async def execute_ai_order(symbol, ai_decision, config):
    """AI 결정에 따른 주문 실행"""
    try:
        if not ai_decision.get('success', False):
            logger.warning(f"AI 분석 실패로 주문 실행 안함: {ai_decision.get('error', 'Unknown')}")
            return False
        
        result = ai_decision.get('result', {})
        final_decision = result.get('final_decision', 'Hold')
        confidence = result.get('decision_confidence', 0)
        recommended_action = result.get('recommended_action', {})
        
        # 신뢰도가 너무 낮거나 인간 검토가 필요한 경우
        if confidence < 60 or result.get('needs_human_review', False):
            logger.info(f"AI 결정 신뢰도 부족 또는 검토 필요: {final_decision} (신뢰도: {confidence}%)")
            return False
        
        # Hold 결정은 주문하지 않음
        if final_decision == 'Hold':
            logger.info(f"AI 결정: Hold (신뢰도: {confidence}%)")
            return False
        
        # 주문 타입 결정
        action_type = recommended_action.get('action_type', 'Wait')
        if action_type in ['Wait for Signal', 'Hold Current Position', 'Wait']:
            logger.info(f"AI 권장 액션: {action_type}")
            return False
        
        # 포지션 방향 결정
        if final_decision in ['Strong Buy', 'Buy']:
            position = 'Long'
            side = 'Buy'
        elif final_decision in ['Strong Sell', 'Sell']:
            position = 'Short'
            side = 'Sell'
        else:
            logger.info(f"알 수 없는 AI 결정: {final_decision}")
            return False
        
        # 현재가 조회
        current_price = get_current_price(symbol=symbol)
        if current_price is None:
            logger.error("현재가 조회 실패")
            return False
        
        # AI 권장 설정 또는 기본 설정 사용
        usdt_amount = config['usdt_amount']  # 기본 설정 사용
        leverage = config['leverage']  # 레버리지는 변경하지 않음
        stop_loss = recommended_action.get('mandatory_stop_loss') or config['stop_loss']
        take_profit = recommended_action.get('mandatory_take_profit') or config['take_profit']
        
        # 가격 기반 TP/SL을 pips로 변환 (필요시)
        if isinstance(stop_loss, float) and stop_loss > 100:
            # 절대 가격인 경우 pips로 변환
            stop_loss_pips = abs(current_price - stop_loss) / current_price * 10000
            stop_loss = min(800, max(200, int(stop_loss_pips)))  # 200-800 pips 범위
        
        if isinstance(take_profit, float) and take_profit > 100:
            # 절대 가격인 경우 pips로 변환
            take_profit_pips = abs(take_profit - current_price) / current_price * 10000
            take_profit = min(800, max(200, int(take_profit_pips)))  # 200-800 pips 범위
        
        logger.info(f"AI 주문 실행: {final_decision} -> {position} (신뢰도: {confidence}%)")
        logger.info(f"주문 상세: 가격={current_price}, SL={stop_loss}, TP={take_profit}")
        
        # 주문 실행 (기존 execute_order 로직과 동일)
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
            logger.info(f"AI 주문 성공: {order_response}")
            return True
        
        logger.warning("AI 주문 생성 실패, 재시도...")
        
        # 재시도
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
            logger.info(f"AI 주문 재시도 성공: {order_response}")
            return True
        
        logger.error(f"AI 주문 재생성 실패: {order_response}")
        return False
        
    except Exception as e:
        logger.error(f"AI 주문 실행 중 오류: {e}", exc_info=True)
        return False

def try_update_with_check(config, max_retries=3):
    """차트 업데이트 및 데이터 정합성 확인"""
    for attempt in range(max_retries):
        result, server_time, execution_time = chart_update_one(config['set_timevalue'], config['symbol'])
        if result is None:
            logger.error(f"차트 업데이트 실패 (시도 {attempt + 1}/{max_retries})")
            continue
            
        df_rare_chart = load_data(
            set_timevalue=config['set_timevalue'], 
            period=300,
            server_time=server_time
        )
        
        if df_rare_chart is not None:
            return result, server_time, execution_time
            
        logger.warning(f"데이터 시간 불일치, 재시도... (시도 {attempt + 1}/{max_retries})")
        time.sleep(5)
        
    return None, server_time, execution_time

async def main():
    """AI 기반 메인 트레이딩 루프"""
    config = TRADING_CONFIG
    
    try:
        logger.info("=== AI 자동 트레이딩 시스템 시작 ===")
        
        # 초기 차트 동기화
        logger.info("차트 동기화 시작...")
        last_time, server_time = chart_update(config['set_timevalue'], config['symbol'])
        last_time = last_time['timestamp']
        server_time = datetime.fromtimestamp(server_time, timezone.utc)
        
        while get_time_block(server_time, TIME_VALUES[config['set_timevalue']]) != get_time_block(last_time, TIME_VALUES[config['set_timevalue']]):
            print(f"{config['set_timevalue']} 차트 업데이트 중...")
            last_time, server_time = chart_update(config['set_timevalue'], config['symbol'])
            last_time = last_time['timestamp'].astimezone(timezone.utc)
            server_time = datetime.fromtimestamp(server_time, timezone.utc)
            time.sleep(60)
            
        logger.info(f"{config['set_timevalue']} 차트 동기화 완료")
        
        # 레버리지 설정 (한 번만 설정)
        if not set_leverage(config['symbol'], config['leverage']):
            raise Exception("레버리지 설정 실패")
        logger.info(f"레버리지 {config['leverage']}배 설정 완료")
        
        # 메인 루프
        cycle_count = 0
        while True:
            cycle_count += 1
            logger.info(f"=== AI 트레이딩 사이클 #{cycle_count} 시작 ===")
            
            # 시간 동기화 (15분 간격)
            server_time = datetime.now(timezone.utc)
            next_run_time = get_next_run_time(server_time, TIME_VALUES[config['set_timevalue']])
            wait_seconds = (next_run_time - server_time).total_seconds() + 5  # 5초 버퍼
            
            if wait_seconds > 0:
                logger.info(f"다음 실행까지 대기: {wait_seconds:.0f}초")
                with tqdm(total=int(wait_seconds), desc="다음 분석까지 대기", ncols=100) as pbar:
                    for _ in range(int(wait_seconds)):
                        time.sleep(1)
                        pbar.update(1)
            
            # 차트 데이터 업데이트
            logger.info("차트 데이터 업데이트 중...")
            result, update_server_time, execution_time = try_update_with_check(config)
            if result is None:
                logger.error("차트 업데이트 최대 재시도 초과")
                continue
            
            # 데이터 정합성을 위한 대기
            time.sleep(1.0)
            
            # AI 시스템 상태 확인
            data_status = get_data_status()
            recovery_status = get_recovery_status()
            
            disabled_ai_tasks = [task for task, status in data_status.items() 
                               if task.startswith('ai_') and status.get('is_disabled', False)]
            if disabled_ai_tasks:
                logger.warning(f"비활성화된 AI 분석기: {disabled_ai_tasks}")
            
            if recovery_status['disabled_tasks']:
                logger.info(f"복구 대기 중인 작업: {recovery_status['disabled_tasks']}")
            
            # AI 트레이딩 사이클 실행
            logger.info("AI 분석 및 거래 결정 중...")
            ai_result = await execute_ai_trading_cycle(config)
            
            if not ai_result.get('success', False):
                logger.error(f"AI 트레이딩 사이클 실패: {ai_result.get('error', 'Unknown')}")
                continue
            
            ai_decision = ai_result.get('ai_decision', {})
            interpreted_decision = ai_result.get('interpreted_decision', {})
            execution_result = ai_result.get('execution_result', {})
            
            # AI 결정 로깅
            if ai_decision.get('success', False):
                result_info = ai_decision.get('result', {})
                logger.info(f"AI 분석 완료: {result_info.get('final_decision', 'Unknown')} "
                          f"(신뢰도: {result_info.get('decision_confidence', 0)}%)")
                
                # 타이밍 정보 로깅
                timing_summary = result_info.get('timing_summary', {})
                if timing_summary:
                    logger.info(f"분석 품질: {timing_summary.get('overall_quality', 'unknown')}, "
                              f"캐시 효율성: {timing_summary.get('cache_efficiency_percent', 0)}%")
            
            # 실제 거래 실행 여부 확인
            action = interpreted_decision.get('action', 'wait')
            if action in ['wait', 'hold']:
                logger.info(f"거래 대기: {interpreted_decision.get('reason', 'No action needed')}")
                continue
            
            # 현재 포지션 상태 확인
            balance, positions_json, ledger = fetch_investment_status()
            
            error_time = 0
            if balance == 'error':
                logger.warning("API 호출 오류, 재시도 중...")
                for i in range(24):  # 최대 2분 재시도
                    time.sleep(5)
                    error_time += 5
                    balance, positions_json, ledger = fetch_investment_status()
                    if balance != 'error':
                        logger.info("API 호출 재시도 성공")
                        break
                else:
                    logger.error("API 호출 오류 지속, 이번 사이클 스킵")
                    continue
            
            positions_flag = positions_json != '[]' and positions_json is not None
            
            # 포지션 관리
            if positions_flag:  # 기존 포지션이 있는 경우
                positions_data = json.loads(positions_json)
                current_amount, current_side, current_avgPrice, pnl = get_position_amount(config['symbol'])
                current_side_str = 'Long' if current_side == 'Buy' else 'Short'
                
                logger.info(f"기존 포지션: {current_side_str}, 수량: {current_amount}, PNL: {pnl}")
                
                # AI가 포지션 종료를 권장하는 경우
                if action == 'close_position':
                    logger.info("AI 권장에 따른 포지션 종료")
                    close_position(symbol=config['symbol'])
                    
                # AI가 포지션 반전을 권장하는 경우
                elif action in ['reverse_to_long', 'reverse_to_short']:
                    logger.info(f"AI 권장에 따른 포지션 반전: {action}")
                    close_position(symbol=config['symbol'])
                    time.sleep(1)  # 종료 후 잠시 대기
                    
                    # 새 포지션 진입
                    await execute_ai_order(config['symbol'], ai_decision, config)
                    
                # AI가 포지션 추가를 권장하는 경우
                elif ((current_side_str == 'Long' and action == 'add_long') or 
                      (current_side_str == 'Short' and action == 'add_short')):
                    logger.info(f"AI 권장에 따른 포지션 추가: {action}")
                    await execute_ai_order(config['symbol'], ai_decision, config)
                
                # 기존 포지션과 반대 신호인 경우 (일반적인 반전)
                elif ((current_side_str == 'Long' and action in ['open_short']) or 
                      (current_side_str == 'Short' and action in ['open_long'])):
                    logger.info("AI 신호 반전으로 포지션 전환")
                    close_position(symbol=config['symbol'])
                    time.sleep(1)
                    
                    # 새 포지션 진입
                    await execute_ai_order(config['symbol'], ai_decision, config)
                
                else:
                    logger.info(f"기존 포지션 유지: {current_side_str}")
            
            else:  # 포지션이 없는 경우
                if action in ['open_long', 'open_short', 'add_long', 'add_short']:
                    # add_long, add_short도 포지션이 없으면 새 포지션 오픈으로 처리
                    if action in ['add_long', 'add_short']:
                        logger.info(f"포지션 없음 - {action}을 새 포지션 오픈으로 처리")
                    else:
                        logger.info("새 포지션 진입")
                    order_success = await execute_ai_order(config['symbol'], ai_decision, config)
                    
                    if order_success:
                        # 거래 로그 기록
                        try:
                            final_decision = ai_decision.get('result', {}).get('final_decision', 'Unknown')
                            trade_logger.log_snapshot(
                                server_time=server_time,
                                tag='ai',
                                position='Long' if 'long' in action else 'Short'
                            )
                        except Exception as e:
                            logger.warning(f"거래 로그 기록 실패: {e}")
            
            # 남은 시간 대기 (15분 - 실행 시간)
            remaining_time = max(0, 900 - (execution_time + error_time))  # 15분 = 900초
            if remaining_time > 0:
                logger.info(f"다음 사이클까지 대기: {remaining_time:.0f}초")
                with tqdm(total=int(remaining_time), desc="대기 중", ncols=100) as pbar:
                    for _ in range(int(remaining_time)):
                        time.sleep(1)
                        pbar.update(1)
                        
    except Exception as e:
        logger.error(f"메인 루프 오류: {e}", exc_info=True)
        return False

def run_main():
    """비동기 메인 함수 실행"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("사용자에 의한 프로그램 종료")
    except Exception as e:
        logger.error(f"프로그램 실행 오류: {e}", exc_info=True)

if __name__ == "__main__":
    run_main()