#!/usr/bin/env python3
"""
AI 기반 자동 트레이딩 메인 실행 파일 - 직렬 스케줄러 버전 (순환 import 해결)
- 15분마다 직렬 사이클 실행
- AI 분석 결과만 기반으로 거래 결정
- 단순한 카운팅 기반 스케줄링
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

# 🔧 수정: 포워딩된 data_scheduler 사용 (순환 import 방지)
from docs.investment_ai.data_scheduler import (
    run_scheduled_data_collection, get_data_status
)

# 🔧 추가: 최종 결정 직접 import (순환 import 방지)
from docs.investment_ai.final_decisionmaker import make_final_investment_decision

# 설정값 (15분 간격)
TRADING_CONFIG = {
    'symbol': 'BTCUSDT',
    'leverage': 5,
    'usdt_amount': 0.3,
    'set_timevalue': '15m',
    'take_profit': 800,
    'stop_loss': 800
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

async def execute_ai_order(symbol, final_decision_result, config):
    """AI 최종 결정에 따른 주문 실행"""
    try:
        if not final_decision_result.get('success', False):
            logger.warning(f"AI 분석 실패로 주문 실행 안함: {final_decision_result.get('error', 'Unknown')}")
            return False
        
        result = final_decision_result.get('result', {})
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
        usdt_amount = config['usdt_amount']
        leverage = config['leverage']
        stop_loss = recommended_action.get('mandatory_stop_loss') or config['stop_loss']
        take_profit = recommended_action.get('mandatory_take_profit') or config['take_profit']
        
        # 가격 기반 TP/SL을 pips로 변환 (필요시)
        if isinstance(stop_loss, float) and stop_loss > 100:
            stop_loss_pips = abs(current_price - stop_loss) / current_price * 10000
            stop_loss = min(800, max(200, int(stop_loss_pips)))
        
        if isinstance(take_profit, float) and take_profit > 100:
            take_profit_pips = abs(take_profit - current_price) / current_price * 10000
            take_profit = min(800, max(200, int(take_profit_pips)))
        
        logger.info(f"AI 주문 실행: {final_decision} -> {position} (신뢰도: {confidence}%)")
        logger.info(f"주문 상세: 가격={current_price}, SL={stop_loss}, TP={take_profit}")
        
        # 주문 실행
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

def get_action_from_decision(final_decision, current_position):
    """AI 최종 결정을 거래 액션으로 변환"""
    try:
        has_position = current_position.get('has_position', False)
        position_side = current_position.get('side', 'none')
        
        if final_decision in ['Strong Buy', 'Buy']:
            if not has_position:
                return 'open_long'
            elif position_side == 'short':
                return 'reverse_to_long'
            else:
                return 'add_long'
                
        elif final_decision in ['Strong Sell', 'Sell']:
            if not has_position:
                return 'open_short'
            elif position_side == 'long':
                return 'reverse_to_short'
            else:
                return 'add_short'
                
        else:  # Hold
            if has_position:
                return 'hold_position'
            else:
                return 'wait'
    except Exception:
        return 'wait'

async def get_all_analysis_for_decision():
    """최종 결정용 분석 데이터 수집 - 안전한 버전"""
    try:
        # 🔧 포워딩된 data_scheduler 사용
        from docs.investment_ai.data_scheduler import (
            get_ai_technical_analysis,
            get_ai_sentiment_analysis, 
            get_ai_macro_analysis,
            get_ai_onchain_analysis,
            get_ai_institutional_analysis,
            get_position_data
        )
        
        # 🔧 포지션 분석 직접 호출
        from docs.investment_ai.analyzers.position_analyzer import analyze_position_status
        
        # 각 분석 결과 수집 - 안전하게
        results = {}
        
        # AI 분석들 - None 체크 추가
        try:
            results['technical_analysis'] = await get_ai_technical_analysis()
        except Exception as e:
            logger.error(f"기술적 분석 조회 오류: {e}")
            results['technical_analysis'] = None
            
        try:
            results['sentiment_analysis'] = await get_ai_sentiment_analysis()
        except Exception as e:
            logger.error(f"감정 분석 조회 오류: {e}")
            results['sentiment_analysis'] = None
            
        try:
            results['macro_analysis'] = await get_ai_macro_analysis()
        except Exception as e:
            logger.error(f"거시경제 분석 조회 오류: {e}")
            results['macro_analysis'] = None
            
        try:
            results['onchain_analysis'] = await get_ai_onchain_analysis()
        except Exception as e:
            logger.error(f"온체인 분석 조회 오류: {e}")
            results['onchain_analysis'] = None
            
        try:
            results['institutional_analysis'] = await get_ai_institutional_analysis()
        except Exception as e:
            logger.error(f"기관투자 분석 조회 오류: {e}")
            results['institutional_analysis'] = None
        
        # 포지션 분석 (실시간) - 안전하게
        try:
            position_analysis = analyze_position_status()
            results['position_analysis'] = position_analysis if position_analysis else {
                'success': False, 'error': '포지션 분석 실패'
            }
        except Exception as e:
            logger.error(f"포지션 분석 오류: {e}")
            results['position_analysis'] = {
                'success': False, 'error': str(e)
            }
        
        # 현재 포지션 정보 - 안전하게
        try:
            position_data = await get_position_data()
            if position_data:
                results['current_position'] = extract_position_info(position_data)
            else:
                logger.warning("포지션 데이터가 None - 기본값 사용")
                results['current_position'] = {
                    'has_position': False,
                    'side': 'none',
                    'size': 0,
                    'entry_price': 0
                }
        except Exception as e:
            logger.error(f"포지션 데이터 조회 오류: {e}")
            results['current_position'] = {
                'has_position': False,
                'side': 'none',
                'size': 0,
                'entry_price': 0,
                'error': str(e)
            }
        
        # 결과 검증
        valid_results = {}
        for key, value in results.items():
            if value is not None:
                valid_results[key] = value
            else:
                logger.warning(f"{key} 결과가 None - 기본 실패 결과 생성")
                valid_results[key] = {
                    'success': False,
                    'error': f'{key} 결과 없음',
                    'skip_reason': 'null_result'
                }
        
        success_count = sum(1 for v in valid_results.values() 
                          if isinstance(v, dict) and v.get('success', False))
        total_count = len(valid_results)
        
        logger.info(f"분석 데이터 수집 완료: {success_count}/{total_count} 성공")
        
        return valid_results
        
    except Exception as e:
        logger.error(f"분석 데이터 수집 중 전체 오류: {e}")
        return {}

def extract_position_info(position_data):
    """포지션 데이터에서 현재 포지션 정보 추출 - 안전한 버전"""
    try:
        # 기본값
        position_info = {
            'has_position': False,
            'side': 'none',
            'size': 0,
            'entry_price': 0,
            'unrealized_pnl': 0,
            'total_equity': 0,
            'available_balance': 0
        }
        
        # position_data가 None이거나 비어있으면 기본값 반환
        if not position_data or not isinstance(position_data, dict):
            logger.warning("포지션 데이터가 없음 - 기본값 사용")
            return position_info
        
        # 잔고 정보 안전하게 추출
        balance = position_data.get('balance', {})
        if isinstance(balance, dict) and 'USDT' in balance:
            usdt_balance = balance['USDT']
            if isinstance(usdt_balance, dict):
                total = usdt_balance.get('total')
                free = usdt_balance.get('free')
                
                position_info.update({
                    'total_equity': float(total) if total is not None else 0,
                    'available_balance': float(free) if free is not None else 0
                })
        
        # positions에서 BTC 포지션 찾기 - 안전하게
        positions = position_data.get('positions', [])
        if isinstance(positions, str):
            try:
                import json
                positions = json.loads(positions)
            except json.JSONDecodeError:
                logger.warning("포지션 JSON 파싱 실패")
                positions = []
        
        if not isinstance(positions, list):
            positions = []
        
        for pos in positions:
            if not isinstance(pos, dict):
                continue
                
            symbol = pos.get('symbol', '')
            if symbol and 'BTC' in symbol:
                # size 안전하게 추출
                size_raw = pos.get('size') or pos.get('contracts')
                if size_raw is not None:
                    try:
                        size = float(size_raw)
                        if abs(size) > 0:
                            # entry_price 안전하게 추출
                            entry_price_raw = pos.get('avgPrice') or pos.get('entryPrice')
                            entry_price = float(entry_price_raw) if entry_price_raw is not None else 0
                            
                            # unrealized_pnl 안전하게 추출
                            unrealized_pnl_raw = pos.get('unrealizedPnl')
                            unrealized_pnl = float(unrealized_pnl_raw) if unrealized_pnl_raw is not None else 0
                            
                            position_info.update({
                                'has_position': True,
                                'side': 'long' if size > 0 else 'short',
                                'size': abs(size),
                                'entry_price': entry_price,
                                'unrealized_pnl': unrealized_pnl
                            })
                            break
                    except (ValueError, TypeError) as e:
                        logger.warning(f"포지션 수치 변환 오류: {e}")
                        continue
        
        return position_info
        
    except Exception as e:
        logger.error(f"포지션 정보 추출 중 예외: {e}")
        return {
            'has_position': False,
            'side': 'none',
            'size': 0,
            'entry_price': 0,
            'error': str(e)
        }

async def main():
    """AI 기반 메인 트레이딩 루프 - 직렬 스케줄러 버전 (순환 import 해결)"""
    config = TRADING_CONFIG
    
    try:
        logger.info("=== AI 자동 트레이딩 시스템 시작 (직렬 스케줄러) ===")
        
        # 레버리지 설정 (한 번만 설정)
        if not set_leverage(config['symbol'], config['leverage']):
            raise Exception("레버리지 설정 실패")
        logger.info(f"레버리지 {config['leverage']}배 설정 완료")
        
        # 🔧 추가: 초기 데이터 수집 및 AI 분석 (시스템 워밍업)
        logger.info("시스템 초기화: 초기 데이터 수집 및 AI 분석 시작...")
        try:
            # 초기 직렬 사이클 실행 (모든 데이터 수집 + AI 분석)
            initial_start_time = time.time()
            await run_scheduled_data_collection()
            initial_duration = time.time() - initial_start_time
            
            logger.info(f"초기 데이터 수집 및 AI 분석 완료 ({initial_duration:.1f}초)")
            
            # 초기 최종 결정도 실행해서 시스템 전체 테스트
            logger.info("초기 최종 결정 테스트 실행...")
            initial_analysis_results = await get_all_analysis_for_decision()
            
            if initial_analysis_results:
                initial_decision = await make_final_investment_decision(initial_analysis_results)
                if initial_decision.get('success', False):
                    result = initial_decision.get('result', {})
                    decision = result.get('final_decision', 'Hold')
                    confidence = result.get('decision_confidence', 0)
                    logger.info(f"초기 AI 결정: {decision} (신뢰도: {confidence}%)")
                else:
                    logger.warning(f"초기 최종 결정 실패: {initial_decision.get('error', 'Unknown')}")
            else:
                logger.warning("초기 분석 결과가 없어 최종 결정 스킵")
            
            # 초기화 상태 확인
            status = get_data_status()
            total_tasks = len(status.get('tasks', {}))
            healthy_tasks = len([t for t in status.get('tasks', {}).values() if not t.get('is_disabled', False)])
            logger.info(f"시스템 초기화 완료: {healthy_tasks}/{total_tasks} 작업 정상")
            
        except Exception as e:
            logger.error(f"초기 데이터 수집 중 오류 (계속 진행): {e}")
            # 초기 수집 실패해도 메인 루프는 계속 진행
        
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
            
            # 🔧 핵심: 직렬 사이클 실행 (포워딩된 함수 사용)
            logger.info("직렬 AI 분석 사이클 실행 중...")
            cycle_start_time = time.time()
            
            try:
                # 데이터 수집 및 AI 분석 실행
                await run_scheduled_data_collection()
                
                cycle_duration = time.time() - cycle_start_time
                logger.info(f"직렬 사이클 완료 ({cycle_duration:.1f}초)")
                
                # 🔧 최종 결정 실행
                logger.info("최종 투자 결정 실행 중...")
                all_analysis_results = await get_all_analysis_for_decision()
                
                if not all_analysis_results:
                    logger.warning("분석 결과가 없어 최종 결정 스킵")
                    continue
                
                final_decision_result = await make_final_investment_decision(all_analysis_results)
                
                if not final_decision_result.get('success', False):
                    logger.warning(f"최종 결정 실패: {final_decision_result.get('error', 'Unknown')}")
                    continue
                
                result = final_decision_result.get('result', {})
                final_decision = result.get('final_decision', 'Hold')
                confidence = result.get('decision_confidence', 0)
                
                logger.info(f"AI 최종 결정: {final_decision} (신뢰도: {confidence}%)")
                
                # 현재 포지션 상태 확인
                balance, positions_json, ledger = fetch_investment_status()
                
                if balance == 'error':
                    logger.warning("API 호출 오류, 재시도 중...")
                    for i in range(12):  # 최대 1분 재시도
                        time.sleep(5)
                        balance, positions_json, ledger = fetch_investment_status()
                        if balance != 'error':
                            logger.info("API 호출 재시도 성공")
                            break
                    else:
                        logger.error("API 호출 오류 지속, 이번 사이클 스킵")
                        continue
                
                # 현재 포지션 정보 추출
                current_position = {
                    'has_position': False,
                    'side': 'none',
                    'size': 0,
                    'entry_price': 0
                }
                
                positions_flag = positions_json != '[]' and positions_json is not None
                if positions_flag:
                    try:
                        positions_data = json.loads(positions_json)
                        if positions_data:
                            position = positions_data[0]
                            size = float(position.get('size', position.get('contracts', 0)))
                            if abs(size) > 0:
                                current_position.update({
                                    'has_position': True,
                                    'side': 'long' if size > 0 else 'short',
                                    'size': abs(size),
                                    'entry_price': float(position.get('avgPrice', position.get('entryPrice', 0)))
                                })
                    except Exception as e:
                        logger.error(f"포지션 정보 파싱 오류: {e}")
                
                logger.info(f"현재 포지션: {current_position['side']} {current_position['size']}")
                
                # AI 결정을 거래 액션으로 변환
                action = get_action_from_decision(final_decision, current_position)
                logger.info(f"거래 액션: {action}")
                
                # 거래 실행
                if action == 'wait' or action == 'hold_position':
                    logger.info("거래 대기 또는 포지션 유지")
                    
                elif action == 'close_position':
                    logger.info("포지션 종료")
                    close_position(symbol=config['symbol'])
                    
                elif action in ['reverse_to_long', 'reverse_to_short']:
                    logger.info(f"포지션 반전: {action}")
                    close_position(symbol=config['symbol'])
                    time.sleep(1)  # 종료 후 잠시 대기
                    
                    # 새 포지션 진입
                    order_success = await execute_ai_order(config['symbol'], final_decision_result, config)
                    if order_success:
                        try:
                            trade_logger.log_snapshot(
                                server_time=datetime.now(timezone.utc),
                                tag='ai_reverse',
                                position='Long' if 'long' in action else 'Short'
                            )
                        except Exception as e:
                            logger.warning(f"거래 로그 기록 실패: {e}")
                    
                elif action in ['open_long', 'open_short', 'add_long', 'add_short']:
                    logger.info(f"포지션 진입/추가: {action}")
                    order_success = await execute_ai_order(config['symbol'], final_decision_result, config)
                    
                    if order_success:
                        try:
                            trade_logger.log_snapshot(
                                server_time=datetime.now(timezone.utc),
                                tag='ai_entry',
                                position='Long' if 'long' in action else 'Short'
                            )
                        except Exception as e:
                            logger.warning(f"거래 로그 기록 실패: {e}")
                
                # 스케줄러 상태 로깅 (디버깅용)
                status = get_data_status()
                total_tasks = len(status.get('tasks', {}))
                healthy_tasks = len([t for t in status.get('tasks', {}).values() if not t.get('is_disabled', False)])
                logger.debug(f"스케줄러 상태: {healthy_tasks}/{total_tasks} 작업 정상")
                
            except Exception as e:
                logger.error(f"사이클 실행 중 오류: {e}")
                continue
            
            logger.info(f"AI 트레이딩 사이클 #{cycle_count} 완료")
                        
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