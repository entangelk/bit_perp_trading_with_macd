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
from docs.utility.logger.logger import logger
from typing import Dict, List, Optional

# 프로젝트 루트 디렉토리 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 기존 시스템 함수들
from docs.get_chart import chart_update, chart_update_one
from docs.get_current import fetch_investment_status
from docs.making_order import set_leverage, create_order_with_tp_sl, close_position, get_position_amount, set_tp_sl
from docs.current_price import get_current_price
from docs.utility.load_data import load_data
from docs.utility.trade_logger import TradeLogger

# 🔧 수정: 포워딩된 data_scheduler 사용 (순환 import 방지)
from docs.investment_ai.data_scheduler import (
    run_scheduled_data_collection, get_data_status
)

# 🔧 추가: 최종 결정 직접 import (순환 import 방지)
from docs.investment_ai.final_decisionmaker import make_final_investment_decision

# 설정값 (60분 간격)
TRADING_CONFIG = {
    'symbol': 'BTCUSDT',
    'leverage': 5,
    'usdt_amount': 0.3,
    'set_timevalue': '60m',
    'take_profit': 1000,
    'stop_loss': 1000
}

TIME_VALUES = {
    '1m': 1,
    '3m': 3,
    '5m': 5,
    '15m': 15,
    '60m': 60
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

        if side == 'Buy':
            sl_price = current_price - config['stop_loss']  
            tp_price = current_price + config['take_profit']
        else:  # Sell
            sl_price = current_price + config['stop_loss']  
            tp_price = current_price - config['take_profit']


        # 🔧 수정: 문자열을 float로 변환 후 처리
        ai_stop_loss = recommended_action.get('mandatory_stop_loss')
        ai_take_profit = recommended_action.get('mandatory_take_profit')

        # None이 아니고 'N/A'도 아닌 경우에만 사용
        if ai_stop_loss and ai_stop_loss != 'N/A':
            try:
                stop_loss = float(ai_stop_loss)
            except (ValueError, TypeError):
                stop_loss = sl_price
        else:
            stop_loss = sl_price

        if ai_take_profit and ai_take_profit != 'N/A':
            try:
                take_profit = float(ai_take_profit)
            except (ValueError, TypeError):
                take_profit = tp_price
        else:
            take_profit = tp_price

      
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
            stop_loss=sl_price,
            take_profit=tp_price
        )
        
        if order_response:
            logger.info(f"AI 주문 재시도 성공: {order_response}")
            return True
        
        logger.error(f"AI 주문 재생성 실패: {order_response}")
        return False
        
    except Exception as e:
        logger.error(f"AI 주문 실행 중 오류: {e}", exc_info=True)
        return False

def create_order_without_tp_sl(symbol, side, usdt_amount, leverage, current_price):
    """TP/SL 없이 순수 포지션 주문만 생성"""
    try:
        # 기존 create_order_with_tp_sl에서 TP/SL 부분만 제거한 버전
        # 또는 기존 함수에서 stop_loss=None, take_profit=None으로 호출
        
        # 예시: 기존 함수 수정 호출
        return create_order_with_tp_sl(
            symbol=symbol,
            side=side,
            usdt_amount=usdt_amount,
            leverage=leverage,
            current_price=current_price,
            stop_loss=None,  # TP/SL 없이
            take_profit=None
        )
        
    except Exception as e:
        logger.error(f"순수 주문 생성 중 오류: {e}")
        return None


async def handle_reverse_decision(final_decision_result: dict, current_position: dict, config: dict) -> bool:
    """Reverse 결정 처리 - 완전한 구현"""
    try:
        logger.info("🔄 Reverse 결정 처리 시작")
        
        result = final_decision_result.get('result', {})
        confidence = result.get('decision_confidence', 0)
        
        # 신뢰도 체크
        if confidence < 65:
            logger.warning(f"Reverse 신뢰도 부족 ({confidence}%) - 실행 보류")
            return False
        
        has_position = current_position.get('has_position', False)
        position_side = current_position.get('side', 'none')
        
        if has_position:
            logger.info(f"🔄 기존 {position_side} 포지션 → 반대 방향 반전 실행")
            
            # 1단계: 기존 포지션 즉시 종료 (TP/SL 무시)
            logger.info("1단계: 기존 포지션 종료")
            close_result = close_position(symbol=config['symbol'])
            if not close_result:
                logger.error("❌ 기존 포지션 종료 실패")
                return False
            
            logger.info("✅ 기존 포지션 종료 완료")
            
            # 2단계: 포지션 종료 확인 대기
            logger.info("2단계: 포지션 종료 확인 대기")
            await asyncio.sleep(3)  # 3초 대기
            
            # 종료 확인
            verification_balance, verification_positions, _ = fetch_investment_status()
            if verification_positions != '[]' and verification_positions is not None:
                logger.warning("⚠️ 포지션이 완전히 종료되지 않음 - 추가 대기")
                await asyncio.sleep(2)
            
            # 3단계: 반대 방향 포지션 생성
            logger.info("3단계: 반대 방향 포지션 생성")
            new_side = 'Buy' if position_side == 'short' else 'Sell'
            
            # TP/SL은 새로운 포지션 생성 후 설정
            order_success = await execute_reverse_order(
                symbol=config['symbol'], 
                new_side=new_side,
                final_decision_result=final_decision_result,
                config=config
            )
            
            if order_success:
                logger.info("✅ Reverse 포지션 생성 완료")
                
                # 4단계: 새 포지션에 TP/SL 설정 (별도 처리)
                await asyncio.sleep(2)  # 포지션 안정화 대기
                await set_tp_sl_for_new_position(config['symbol'], new_side, final_decision_result, config)
                
                return True
            else:
                logger.error("❌ Reverse 포지션 생성 실패")
                return False
            
        else:
            logger.warning("⚠️ 현재 포지션이 없는데 Reverse 결정 - 일반 진입으로 처리")
            # 포지션이 없으면 일반적인 신규 진입
            return await execute_ai_order(config['symbol'], final_decision_result, config)
        
    except Exception as e:
        logger.error(f"❌ Reverse 결정 처리 중 오류: {e}")
        return False


async def set_tp_sl_for_new_position(symbol: str, side: str, final_decision_result: Dict, config: Dict):
    """새로운 포지션에 TP/SL 설정"""
    try:
        logger.info("새 포지션에 TP/SL 설정 시작")
        
        # 현재 포지션 정보 확인
        amount, pos_side, avgPrice, pnl = get_position_amount(symbol)
        
        if not pos_side or not avgPrice:
            logger.warning("새 포지션 정보를 찾을 수 없음 - TP/SL 설정 스킵")
            return
        
        # Reverse 후에는 기본 TP/SL 사용 (AI 값이 이전 포지션 기준일 수 있음)
        current_price = get_current_price(symbol)
        if not current_price:
            logger.error("현재가 조회 실패 - TP/SL 설정 실패")
            return
        
        if side == 'Buy':
            stop_loss = current_price - config['stop_loss']
            take_profit = current_price + config['take_profit']
        else:  # Sell
            stop_loss = current_price + config['stop_loss']
            take_profit = current_price - config['take_profit']
        
        logger.info(f"새 포지션 TP/SL 설정: SL={stop_loss}, TP={take_profit}")
        
        # TP/SL 설정
        tp_sl_result = set_tp_sl(symbol, stop_loss, take_profit, avgPrice, pos_side)
        
        if tp_sl_result:
            logger.info("✅ 새 포지션 TP/SL 설정 완료")
        else:
            logger.warning("⚠️ 새 포지션 TP/SL 설정 실패")
        
    except Exception as e:
        logger.error(f"새 포지션 TP/SL 설정 중 오류: {e}")


async def execute_reverse_order(symbol: str, new_side: str, final_decision_result: dict, config: dict) -> bool:
    """Reverse 전용 주문 실행 - TP/SL 없이"""
    try:
        # 현재가 조회
        current_price = get_current_price(symbol=symbol)
        if current_price is None:
            logger.error("현재가 조회 실패")
            return False
        
        logger.info(f"Reverse 주문 실행: {new_side} at {current_price}")
        
        # TP/SL 없이 순수 포지션 진입만
        order_response = create_order_with_tp_sl(
            symbol=symbol,
            side=new_side,
            usdt_amount=config['usdt_amount'],
            leverage=config['leverage'],
            current_price=current_price,
            stop_loss=None,  # TP/SL 없이
            take_profit=None
        )
        
        if order_response:
            logger.info(f"✅ Reverse 주문 성공: {order_response}")
            return True
        else:
            logger.error(f"❌ Reverse 주문 실패")
            return False
        
    except Exception as e:
        logger.error(f"Reverse 주문 실행 중 오류: {e}")
        return False

def get_action_from_decision(final_decision, current_position):
    """AI 최종 결정을 거래 액션으로 변환"""
    try:
        has_position = current_position.get('has_position', False)
        position_side = current_position.get('side', 'none')
        
        # ✅ 추가: Reverse 처리
        if final_decision == 'Reverse':
            if has_position:
                if position_side in ['short', 'Short', 'Sell']:
                    return 'reverse_to_long'
                elif position_side in ['long', 'Long', 'Buy']:
                    return 'reverse_to_short'
            else:
                return 'wait'  # 포지션 없으면 대기


        if final_decision in ['Strong Buy', 'Buy']:
            if not has_position:
                return 'open_long'
            else:
                return 'add_long'
                
        elif final_decision in ['Strong Sell', 'Sell']:
            if not has_position:
                return 'open_short'
            else:
                return 'add_short'
                
        else:  # Hold
            if has_position:
                return 'hold_position'
            else:
                return 'wait'
    except Exception:
        return 'wait'

def normalize_position_side(side_value):
    """
    포지션 방향을 안전하게 정규화하는 함수
    API 응답의 다양한 형태를 모두 처리
    """
    if not side_value:
        return 'none'
    
    side_str = str(side_value).lower().strip()
    
    # Long 포지션 케이스들
    if side_str in ['buy', 'long', 'bid', '1']:
        return 'long'
    # Short 포지션 케이스들  
    elif side_str in ['sell', 'short', 'ask', '-1']:
        return 'short'
    else:
        return 'none'

async def get_all_analysis_for_decision():
    """최종 결정용 분석 데이터 수집 - 포지션 조건부 처리 추가"""
    try:
        logger.info("🔍 DEBUG: 메인봇 get_all_analysis_for_decision 시작")
        
        # 포워딩된 data_scheduler 사용
        from docs.investment_ai.data_scheduler import (
            get_ai_technical_analysis,
            get_ai_sentiment_analysis, 
            get_ai_macro_analysis,
            get_ai_onchain_analysis,
            get_ai_institutional_analysis,
            get_position_data
        )
        
        # 각 분석 결과 수집
        results = {}
        
        logger.info("🔍 DEBUG: AI 분석 결과 수집 시작")
        
        # AI 분석들 개별 수집 및 로깅
        analyses = [
            ('technical_analysis', get_ai_technical_analysis),
            ('sentiment_analysis', get_ai_sentiment_analysis),
            ('macro_analysis', get_ai_macro_analysis),
            ('onchain_analysis', get_ai_onchain_analysis),
            ('institutional_analysis', get_ai_institutional_analysis)
        ]
        
        for result_key, get_func in analyses:
            try:
                # logger.info(f"🔍 DEBUG: {result_key} 수집 시작")
                result = await get_func()
                
                # logger.info(f"🔍 DEBUG: {result_key} 결과 타입: {type(result)}")
                # logger.info(f"🔍 DEBUG: {result_key} 결과가 None: {result is None}")
                
                # if result and isinstance(result, dict):
                    # logger.info(f"🔍 DEBUG: {result_key} 키들: {list(result.keys())}")
                    # if 'success' in result:
                        # logger.info(f"🔍 DEBUG: {result_key} success: {result.get('success')}")
                
                results[result_key] = result if result else {'success': False, 'error': f'{result_key} 결과 없음'}
                # logger.info(f"🔍 DEBUG: {result_key} 수집 완료")
            except Exception as e:
                logger.error(f"🔍 DEBUG: {result_key} 수집 실패: {e}")
                results[result_key] = {'success': False, 'error': str(e)}
        
        # 🔧 현재 포지션 정보 먼저 수집
        logger.info("🔍 DEBUG: 현재 포지션 정보 수집 시작")
        try:
            position_data = await get_position_data()
            
            # logger.info(f"🔍 DEBUG: position_data 타입: {type(position_data)}")
            # logger.info(f"🔍 DEBUG: position_data가 None: {position_data is None}")
            
            if position_data:
                # if isinstance(position_data, dict):
                    # logger.info(f"🔍 DEBUG: position_data 키들: {list(position_data.keys())}")
                current_position_info = extract_position_info(position_data)
                results['current_position'] = current_position_info
                logger.info("🔍 DEBUG: 포지션 데이터 추출 완료")
            else:
                logger.warning("🔍 DEBUG: 포지션 데이터가 없음 - 기본값 사용")
                current_position_info = {
                    'has_position': False,
                    'side': 'none',
                    'size': 0,
                    'entry_price': 0
                }
                results['current_position'] = current_position_info
        except Exception as e:
            logger.error(f"🔍 DEBUG: 포지션 데이터 수집 실패: {e}")
            current_position_info = {
                'has_position': False,
                'side': 'none',
                'size': 0,
                'entry_price': 0,
                'error': str(e)
            }
            results['current_position'] = current_position_info
        
        # 🔧 포지션 분석 (포지션 유무에 따라 조건부 실행)
        logger.info("🔍 DEBUG: 포지션 분석 수집 시작")
        try:
            has_position = current_position_info.get('has_position', False)
            # logger.info(f"🔍 DEBUG: 포지션 상태 확인 - has_position: {has_position}")
            
            if has_position:
                # 포지션이 있을 때만 실제 분석 실행
                logger.info("🔍 DEBUG: 포지션 있음 - 실제 position_analysis 실행")
                from docs.investment_ai.analyzers.position_analyzer import analyze_position_status
                
                # analyze_position_status가 비동기인지 동기인지 확인 후 처리
                import inspect
                if inspect.iscoroutinefunction(analyze_position_status):
                    position_analysis = await analyze_position_status()
                else:
                    position_analysis = analyze_position_status()
                
                # logger.info(f"🔍 DEBUG: 실제 포지션 분석 결과 타입: {type(position_analysis)}")
                # logger.info(f"🔍 DEBUG: 실제 포지션 분석 결과가 None: {position_analysis is None}")
                
                # if position_analysis and isinstance(position_analysis, dict):
                    # logger.info(f"🔍 DEBUG: 실제 포지션 분석 키들: {list(position_analysis.keys())}")
                    # if 'success' in position_analysis:
                        # logger.info(f"🔍 DEBUG: 실제 포지션 분석 success: {position_analysis.get('success')}")
                
                results['position_analysis'] = position_analysis if position_analysis else {
                    'success': False, 'error': '포지션 분석 실패'
                }
            else:
                # 포지션이 없으면 기본값
                logger.info("🔍 DEBUG: 포지션 없음 - 기본값 position_analysis 설정")
                position_analysis = {
                    'success': True,
                    'result': {
                        'recommended_action': 'Wait',
                        'position_status': 'No Position',
                        'risk_level': 'None',
                        'confidence': 100,
                        'analysis_summary': '현재 포지션이 없어 대기 상태 권장'
                    },
                    'analysis_type': 'position_analysis',
                    'note': 'No position - default analysis'
                }
                results['position_analysis'] = position_analysis
            
            logger.info("🔍 DEBUG: 포지션 분석 완료")
            
        except Exception as e:
            logger.error(f"🔍 DEBUG: 포지션 분석 호출 오류: {e}")
            results['position_analysis'] = {
                'success': False, 'error': str(e)
            }
        
        # 성공 통계
        success_count = sum(1 for result in results.values() 
                          if isinstance(result, dict) and result.get('success', False))
        total_count = len(results)
        
        # logger.info(f"🔍 DEBUG: 최종 수집 결과 - 성공: {success_count}/{total_count}")
        # logger.info(f"🔍 DEBUG: 최종 결과 키들: {list(results.keys())}")
        
        # 각 결과의 success 상태 로깅
        # for key, value in results.items():
            # if isinstance(value, dict) and 'success' in value:
                # logger.info(f"🔍 DEBUG: 최종 {key} success: {value.get('success')}")
        
        return results
    except Exception as e:
        logger.error(f"🔍 DEBUG: 분석 데이터 수집 전체 오류: {e}")
        return {}

def normalize_position_side(side_value):
    """
    포지션 방향을 안전하게 정규화하는 헬퍼 함수
    API 응답의 다양한 형태를 모두 처리
    """
    if not side_value:
        return 'none'
    
    side_str = str(side_value).lower().strip()
    
    # Long 포지션 케이스들
    if side_str in ['buy', 'long', 'bid', '1']:
        return 'long'
    # Short 포지션 케이스들  
    elif side_str in ['sell', 'short', 'ask', '-1']:
        return 'short'
    else:
        return 'none'

def extract_position_info(position_data):
    """포지션 데이터에서 현재 포지션 정보 추출 - 안전성 강화 (기존 함수명 유지)"""
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
        
        # 🔧 수정: position_data 유효성 검사
        if not position_data or not isinstance(position_data, dict):
            logger.warning("포지션 데이터가 없거나 잘못된 형태")
            return position_info
        
        # 잔고 정보
        balance = position_data.get('balance', {})
        if isinstance(balance, dict) and 'USDT' in balance:
            usdt_balance = balance['USDT']
            # 🔧 수정: None 값 체크 추가
            total = usdt_balance.get('total', 0)
            free = usdt_balance.get('free', 0)
            if total is not None and free is not None:
                position_info.update({
                    'total_equity': float(total),
                    'available_balance': float(free)
                })
        
        # positions에서 BTC 포지션 찾기
        positions = position_data.get('positions', [])
        if isinstance(positions, str):
            import json
            try:
                positions = json.loads(positions)
            except:
                logger.warning("포지션 JSON 파싱 실패")
                return position_info
        
        if not isinstance(positions, list):
            logger.warning("포지션 데이터가 리스트가 아님")
            return position_info
        
        for pos in positions:
            if not isinstance(pos, dict):
                continue
                
            symbol = pos.get('symbol', '')
            if 'BTC' in symbol:
                # 🔧 수정: None 값 체크 강화
                size_raw = pos.get('size', pos.get('contracts', 0))
                entry_price_raw = pos.get('avgPrice', pos.get('entryPrice', 0))
                unrealized_pnl_raw = pos.get('unrealizedPnl', 0)
                
                # None 체크 후 float 변환
                try:
                    size = float(size_raw) if size_raw is not None else 0
                    entry_price = float(entry_price_raw) if entry_price_raw is not None else 0
                    unrealized_pnl = float(unrealized_pnl_raw) if unrealized_pnl_raw is not None else 0
                except (ValueError, TypeError) as e:
                    logger.warning(f"포지션 수치 변환 실패: {e}")
                    continue
                
                # 🔧 핵심 수정: 안전한 포지션 방향 처리
                side_raw = pos.get('side', 'none')
                position_side = normalize_position_side(side_raw)
                
                if abs(size) > 0:
                    position_info.update({
                        'has_position': True,
                        'side': position_side,  # ✅ 정규화된 값 사용
                        'size': abs(size),
                        'entry_price': entry_price,
                        'unrealized_pnl': unrealized_pnl
                    })
                break
        
        return position_info
    except Exception as e:
        logger.error(f"포지션 정보 추출 오류: {e}")
        return {
            'has_position': False,
            'side': 'none',
            'size': 0,
            'entry_price': 0,
            'error': str(e)
        }

async def update_existing_position_tp_sl(symbol, final_decision_result, config):
    """기존 포지션의 TP/SL만 업데이트하는 함수 - 매 사이클마다 적용"""
    try:
        # final_decision_result에서 성공 여부 확인
        if not final_decision_result.get('success', False):
            logger.warning(f"AI 분석 실패로 TP/SL 업데이트 안함: {final_decision_result.get('error', 'Unknown')}")
            return False
        
        result = final_decision_result.get('result', {})
        recommended_action = result.get('recommended_action', {})
        
        # AI 권장 TP/SL 값 추출 (기존 메인 코드와 동일한 방식)
        ai_stop_loss = recommended_action.get('mandatory_stop_loss')
        ai_take_profit = recommended_action.get('mandatory_take_profit')
        
        # None이거나 'N/A'인 경우 업데이트하지 않음
        if not ai_stop_loss or ai_stop_loss == 'N/A':
            logger.info("AI에서 제공한 stop_loss 값이 없어 업데이트 스킵")
            return False
            
        if not ai_take_profit or ai_take_profit == 'N/A':
            logger.info("AI에서 제공한 take_profit 값이 없어 업데이트 스킵")
            return False
        
        # 문자열을 float로 변환 (기존 메인 코드 방식)
        try:
            stop_loss_price = float(ai_stop_loss)
            take_profit_price = float(ai_take_profit)
        except (ValueError, TypeError) as e:
            logger.warning(f"TP/SL 값 변환 실패: stop_loss={ai_stop_loss}, take_profit={ai_take_profit}, error={e}")
            return False
        
        # 현재 포지션 정보 가져오기
        amount, side, avgPrice, pnl = get_position_amount(symbol)
        
        # 포지션이 없으면 업데이트하지 않음
        if not side or not avgPrice:
            logger.info("현재 포지션이 없어 TP/SL 업데이트 스킵")
            return False
        
        logger.info(f"기존 포지션 TP/SL 업데이트 시작: {side} 포지션, 진입가={avgPrice}")
        logger.info(f"새로운 설정값: SL={stop_loss_price}, TP={take_profit_price}")
        
        # TP/SL 설정 적용
        tp_sl_result = set_tp_sl(symbol, stop_loss_price, take_profit_price, avgPrice, side)
        
        if tp_sl_result:
            logger.info(f"기존 포지션 TP/SL 업데이트 성공: {tp_sl_result}")
            return True
        else:
            logger.warning("기존 포지션 TP/SL 업데이트 실패")
            return False
        
    except Exception as e:
        logger.error(f"기존 포지션 TP/SL 업데이트 중 오류: {e}", exc_info=True)
        return False

async def main():
    """AI 기반 메인 트레이딩 루프 - Reverse 우선 처리 버전"""
    config = TRADING_CONFIG
    
    try:
        logger.info("=== AI 자동 트레이딩 시스템 시작 (Reverse 처리 개선) ===")
        
        # 레버리지 설정 (한 번만 설정)
        if not set_leverage(config['symbol'], config['leverage']):
            raise Exception("레버리지 설정 실패")
        logger.info(f"레버리지 {config['leverage']}배 설정 완료")
        
        # 초기 데이터 수집 및 AI 분석 (시스템 워밍업)
        logger.info("시스템 초기화: 초기 데이터 수집 및 AI 분석 시작...")
        try:
            # 초기 직렬 사이클 실행 (모든 데이터 수집 + AI 분석)
            initial_start_time = time.time()
            await run_scheduled_data_collection(initial_run=True)
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
            
            # 시간 동기화 (60분 간격)
            server_time = datetime.now(timezone.utc)
            next_run_time = get_next_run_time(server_time, TIME_VALUES[config['set_timevalue']])
            wait_seconds = (next_run_time - server_time).total_seconds() + 5  # 5초 버퍼
            
            if wait_seconds > 0:
                logger.info(f"다음 실행까지 대기: {wait_seconds:.0f}초")
                with tqdm(total=int(wait_seconds), desc="다음 분석까지 대기", ncols=100) as pbar:
                    for _ in range(int(wait_seconds)):
                        time.sleep(1)
                        pbar.update(1)
            
            # 직렬 사이클 실행 (포워딩된 함수 사용)
            logger.info("직렬 AI 분석 사이클 실행 중...")
            cycle_start_time = time.time()
            
            try:
                # 데이터 수집 및 AI 분석 실행
                await run_scheduled_data_collection()
                
                cycle_duration = time.time() - cycle_start_time
                logger.info(f"직렬 사이클 완료 ({cycle_duration:.1f}초)")
                
                # 최종 결정 실행
                logger.info("최종 투자 결정 실행 중...")
                from docs.investment_ai.serial_scheduler import get_serial_scheduler

                scheduler = get_serial_scheduler()
                final_decision_result = scheduler.get_final_decision_result()
                
                if not final_decision_result.get('success', False):
                    logger.warning(f"최종 결정 실패: {final_decision_result.get('error', 'Unknown')}")
                    continue
                
                result = final_decision_result.get('result', {})
                final_decision = result.get('final_decision', 'Hold')
                confidence = result.get('decision_confidence', 0)
                
                logger.info(f"AI 최종 결정: {final_decision} (신뢰도: {confidence}%)")
                
                # 🔧 핵심: Reverse 결정 즉시 처리 (포지션 조회 전)
                if final_decision == 'Reverse':
                    logger.info("🔄 Reverse 결정 감지 - 즉시 처리 시작")
                    
                    # Reverse 처리 전 현재 포지션 상태 확인
                    balance, positions_json, ledger = fetch_investment_status()
                    
                    if balance == 'error':
                        logger.error("포지션 상태 조회 실패 - Reverse 처리 중단")
                        continue
                    
                    # 현재 포지션 정보 추출
                    current_position = extract_current_position_safely(balance, positions_json)
                    
                    logger.info(f"Reverse 처리 전 포지션: {current_position['side']} {current_position['size']}")
                    
                    # Reverse 실행
                    reverse_success = await handle_reverse_decision(final_decision_result, current_position, config)
                    
                    if reverse_success:
                        logger.info("✅ Reverse 실행 완료")
                        try:
                            trade_logger.log_snapshot(
                                server_time=datetime.now(timezone.utc),
                                tag='ai_reverse_completed',
                                position='Reversed'
                            )
                        except Exception as e:
                            logger.warning(f"거래 로그 기록 실패: {e}")
                    else:
                        logger.error("❌ Reverse 실행 실패")
                    
                    # Reverse 처리 후 다음 사이클로 이동
                    logger.info(f"AI 트레이딩 사이클 #{cycle_count} 완료 (Reverse 처리)")
                    continue
                
                # 일반적인 거래 처리 (Reverse가 아닌 경우)
                logger.info("일반 거래 결정 처리 시작")
                
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
                current_position = extract_current_position_safely(balance, positions_json)
                logger.info(f"현재 포지션: {current_position['side']} {current_position['size']}")

                # 기존 포지션이 있으면 TP/SL 업데이트 (Reverse가 아닌 경우에만)
                if current_position['has_position']:
                    logger.info("기존 포지션 발견 - TP/SL 업데이트 시도")
                    tp_sl_updated = await update_existing_position_tp_sl(config['symbol'], final_decision_result, config)
                else:
                    logger.info("현재 포지션 없음 - TP/SL 업데이트 스킵")

                # AI 결정을 거래 액션으로 변환
                action = get_action_from_decision(final_decision, current_position)
                logger.info(f"거래 액션: {action}")
                
                # 거래 실행
                if action in ['wait','Wait','hold_position','Hold Current']:
                    logger.info("거래 대기 또는 포지션 유지")
                    
                elif action in ['close_position','Close Position']:
                    logger.info("포지션 종료")
                    close_position(symbol=config['symbol'])
                    
                elif action in ['open_long', 'open_short', 'add_long', 'add_short','Open Long','Open Short']:
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
                
            except Exception as e:
                logger.error(f"사이클 실행 중 오류: {e}")
                continue
            
            logger.info(f"AI 트레이딩 사이클 #{cycle_count} 완료")
                        
    except Exception as e:
        logger.error(f"메인 루프 오류: {e}", exc_info=True)
        return False


# 새로운 헬퍼 함수들

def extract_current_position_safely(balance, positions_json) -> dict:
    """안전한 포지션 정보 추출 - normalize_position_side 사용"""
    try:
        current_position = {
            'has_position': False,
            'side': 'none',
            'size': 0,
            'entry_price': 0,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if positions_json == '[]' or positions_json is None:
            return current_position
        
        positions_data = json.loads(positions_json)
        if not positions_data:
            return current_position
        
        position = positions_data[0]
        size = float(position.get('size', position.get('contracts', 0)))
        
        if abs(size) > 0:
            side_raw = position.get('side', 'none')
            position_side = normalize_position_side(side_raw)  # ✅ 정규화 함수 사용
            
            current_position.update({
                'has_position': True,
                'side': position_side,
                'size': abs(size),
                'entry_price': float(position.get('avgPrice', position.get('entryPrice', 0)))
            })
        
        return current_position
        
    except Exception as e:
        logger.error(f"포지션 추출 오류: {e}")
        return {
            'has_position': False,
            'side': 'none',
            'size': 0,
            'entry_price': 0,
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

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
