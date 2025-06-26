"""
AI 기반 비트코인 무기한 선물 자동거래 시스템
기존 전략 기반 시스템을 AI 기반으로 완전 대체
"""

import asyncio
import time
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from tqdm import tqdm

# 프로젝트 루트 디렉토리 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 기존 시스템 모듈들
from docs.get_chart import chart_update, chart_update_one
from docs.making_order import set_leverage, close_position, get_position_amount
from docs.utility.load_data import load_data
from docs.utility.trade_logger import TradeLogger
from docs.utility.check_pnl import get_7win_rate
from logger import logger

# AI 시스템 모듈
from docs.investment_ai.ai_trading_integration import AITradingIntegration
from docs.investment_ai.data_scheduler import get_data_scheduler, get_data_status

# 설정값
TRADING_CONFIG = {
    'symbol': 'BTCUSDT',
    'leverage': 5,
    'usdt_amount': 0.3,  # 자산 대비 비율
    'set_timevalue': '15m',  # AI 분석에 최적화된 15분봉
    'take_profit': 400,
    'stop_loss': 400
}

TIME_VALUES = {
    '1m': 1,
    '3m': 3,
    '5m': 5,
    '15m': 15
}

# API 키 설정
BYBIT_ACCESS_KEY = os.getenv("BYBIT_ACCESS_KEY")
BYBIT_SECRET_KEY = os.getenv("BYBIT_SECRET_KEY")

# 글로벌 변수
trade_logger = TradeLogger()
ai_integration = None

def get_time_block(dt, interval):
    """datetime 객체를 interval 분 단위로 표현"""
    return (dt.year, dt.month, dt.day, dt.hour, (dt.minute // interval) * interval)

def get_next_run_time(current_time, interval_minutes):
    """다음 실행 시간 계산"""
    minute_block = (current_time.minute // interval_minutes + 1) * interval_minutes
    next_time = current_time.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minute_block)
    return next_time

def try_update_with_check(config, max_retries=3):
    """차트 업데이트 및 데이터 검증 (기존 로직 유지)"""
    for attempt in range(max_retries):
        result, server_time, execution_time = chart_update_one(config['set_timevalue'], config['symbol'])
        if result is None:
            logger.error(f"차트 업데이트 실패 (시도 {attempt + 1}/{max_retries})")
            continue
            
        # 데이터 로드 시도
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

async def handle_ai_decision(ai_result):
    """AI 결정 결과 처리 및 로깅"""
    try:
        if not ai_result.get('success', False):
            logger.warning(f"AI 분석 실패: {ai_result.get('error', 'Unknown error')}")
            return False
        
        interpreted_decision = ai_result.get('interpreted_decision', {})
        execution_result = ai_result.get('execution_result', {})
        
        action = interpreted_decision.get('action', 'wait')
        reason = interpreted_decision.get('reason', 'No reason provided')
        confidence = interpreted_decision.get('confidence', 0)
        
        logger.info(f"AI 결정: {action} (신뢰도: {confidence}%) - {reason}")
        
        if execution_result.get('executed', False):
            logger.info(f"거래 실행됨: {execution_result.get('reason', 'No details')}")
            
            # 거래 스냅샷 로깅
            try:
                trade_logger.log_snapshot(
                    server_time=datetime.now(timezone.utc),
                    tag='ai',
                    position=action
                )
            except Exception as e:
                logger.warning(f"거래 스냅샷 로깅 실패: {e}")
        else:
            logger.info(f"거래 미실행: {execution_result.get('reason', 'No action taken')}")
        
        return True
        
    except Exception as e:
        logger.error(f"AI 결정 처리 중 오류: {e}")
        return False

async def run_ai_trading_cycle(config):
    """AI 기반 트레이딩 사이클 실행"""
    try:
        logger.info("AI 트레이딩 사이클 시작")
        
        # AI 트레이딩 통합 클래스 사용
        global ai_integration
        if ai_integration is None:
            ai_integration = AITradingIntegration(config)
        
        # AI 기반 완전한 트레이딩 사이클 실행
        ai_result = await ai_integration.run_ai_trading_cycle()
        
        # 결과 처리
        await handle_ai_decision(ai_result)
        
        return ai_result
        
    except Exception as e:
        logger.error(f"AI 트레이딩 사이클 중 오류: {e}")
        return {
            'success': False,
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

def check_win_rate_reversal():
    """승률 기반 리버싱 체크 (기존 로직 유지)"""
    try:
        get_7win_rate(BYBIT_ACCESS_KEY, BYBIT_SECRET_KEY)
    except Exception as e:
        if not os.path.exists('win_rate.json'):
            with open('win_rate.json', 'w') as f:
                json.dump({'win_rate': True}, f)

def should_emergency_stop():
    """긴급 정지 조건 체크"""
    try:
        # 포지션 정보 확인
        current_amount, current_side, current_avgPrice, pnl = get_position_amount(TRADING_CONFIG['symbol'])
        
        if current_amount and current_amount > 0:
            # 손실이 너무 클 때 긴급 정지
            if pnl and pnl < -1000:  # 1000 USDT 이상 손실
                logger.critical(f"긴급 정지: 과도한 손실 감지 (PnL: {pnl})")
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"긴급 정지 체크 중 오류: {e}")
        return False

async def main():
    """AI 기반 메인 트레이딩 루프"""
    config = TRADING_CONFIG
    global ai_integration
    
    try:
        logger.info("=== AI 기반 비트코인 자동거래 시스템 시작 ===")
        logger.info(f"설정: {json.dumps(config, indent=2)}")
        
        # 초기 차트 동기화
        logger.info("차트 데이터 동기화 시작...")
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
        
        # 레버리지 설정
        if not set_leverage(config['symbol'], config['leverage']):
            logger.error("레버리지 설정 실패")
            raise Exception("레버리지 설정 실패")
        
        logger.info(f"레버리지 {config['leverage']}x 설정 완료")
        
        # AI 통합 시스템 초기화
        ai_integration = AITradingIntegration(config)
        logger.info("AI 통합 시스템 초기화 완료")
        
        # 데이터 스케줄러 초기화
        data_scheduler = get_data_scheduler()
        logger.info("데이터 스케줄러 초기화 완료")
        
        # 데이터 스케줄러 상태 로깅
        data_status = get_data_status()
        logger.info(f"데이터 수집 작업: {len(data_status)}개 등록됨")
        for task_name, info in data_status.items():
            logger.info(f"  {task_name}: 수집주기 {info['interval_minutes']}분")
        
        # 메인 트레이딩 루프
        cycle_count = 0
        while True:
            try:
                cycle_count += 1
                logger.info(f"=== 트레이딩 사이클 #{cycle_count} ===")
                
                # 시간 동기화
                server_time = datetime.now(timezone.utc)
                next_run_time = get_next_run_time(server_time, TIME_VALUES[config['set_timevalue']])
                wait_seconds = (next_run_time - server_time).total_seconds() + 5  # 5초 버퍼
                
                if wait_seconds > 0:
                    logger.info(f"다음 사이클까지 {wait_seconds:.1f}초 대기")
                    with tqdm(total=int(wait_seconds), desc="대기 중", ncols=100) as pbar:
                        for _ in range(int(wait_seconds)):
                            time.sleep(1)
                            pbar.update(1)
                
                # 차트 데이터 업데이트
                logger.info("차트 데이터 업데이트 중...")
                result, update_server_time, execution_time = try_update_with_check(config)
                if result is None:
                    logger.error("차트 업데이트 실패, 다음 사이클로 건너뛰기")
                    continue
                
                # 데이터 정합성 확인
                df_rare_chart = load_data(set_timevalue=config['set_timevalue'], period=300)
                if df_rare_chart is None or df_rare_chart.empty:
                    logger.error("데이터 로드 실패, 다음 사이클로 건너뛰기")
                    continue
                
                logger.info(f"차트 데이터 업데이트 완료 (소요시간: {execution_time:.1f}초)")
                
                # 승률 기반 리버싱 체크 (기존 로직)
                check_win_rate_reversal()
                
                # 긴급 정지 조건 체크
                if should_emergency_stop():
                    logger.critical("긴급 정지 조건 감지, 시스템 종료")
                    break
                
                # ====== AI 기반 트레이딩 사이클 실행 ======
                ai_result = await run_ai_trading_cycle(config)
                
                # AI 결과 요약 로깅
                if ai_result.get('success', False):
                    interpreted = ai_result.get('interpreted_decision', {})
                    execution = ai_result.get('execution_result', {})
                    
                    logger.info(f"AI 결정: {interpreted.get('action', 'unknown')} "
                              f"(신뢰도: {interpreted.get('confidence', 0)}%)")
                    
                    if execution.get('executed', False):
                        logger.info(f"거래 실행: {execution.get('action', 'unknown')}")
                    else:
                        logger.info("거래 미실행")
                else:
                    logger.warning(f"AI 사이클 실패: {ai_result.get('error', 'Unknown error')}")
                
                # 주기적으로 데이터 스케줄러 상태 로깅 (10사이클마다)
                if cycle_count % 10 == 0:
                    data_status = get_data_status()
                    fresh_data_count = sum(1 for info in data_status.values() if info['cache_age_minutes'] < 30)
                    logger.info(f"데이터 상태: {fresh_data_count}/{len(data_status)} 신선한 데이터")
                
                # 사이클 완료 후 대기
                remaining_time = max(0, 270 - execution_time)  # 4.5분 - 실행시간
                if remaining_time > 0:
                    logger.info(f"사이클 완료, {remaining_time:.1f}초 추가 대기")
                    with tqdm(total=int(remaining_time), desc="사이클 대기", ncols=100) as pbar:
                        for _ in range(int(remaining_time)):
                            time.sleep(1)
                            pbar.update(1)
                
            except KeyboardInterrupt:
                logger.info("사용자에 의한 중단 요청")
                break
            except Exception as e:
                logger.error(f"트레이딩 사이클 중 오류: {e}", exc_info=True)
                
                # 오류 발생 시 잠시 대기 후 재시도
                logger.info("60초 후 재시도...")
                time.sleep(60)
                continue
    
    except Exception as e:
        logger.critical(f"시스템 치명적 오류: {e}", exc_info=True)
        return False
    
    finally:
        # 시스템 종료 전 정리 작업
        logger.info("=== AI 트레이딩 시스템 종료 ===")
        
        # AI 시스템 상태 로깅
        if ai_integration:
            try:
                status = ai_integration.get_system_status()
                logger.info(f"최종 시스템 상태: {json.dumps(status, indent=2)}")
                
                # 최근 결정 히스토리 저장
                history = ai_integration.get_decision_history(5)
                if history:
                    with open('ai_decision_history.json', 'w') as f:
                        json.dump(history, f, indent=2, ensure_ascii=False)
                    logger.info("AI 결정 히스토리 저장 완료")
                
                # 데이터 스케줄러 상태 저장
                final_data_status = get_data_status()
                with open('data_scheduler_status.json', 'w') as f:
                    json.dump(final_data_status, f, indent=2, ensure_ascii=False)
                logger.info("데이터 스케줄러 상태 저장 완료")
                
            except Exception as e:
                logger.error(f"종료 정리 작업 중 오류: {e}")
        
        logger.info("시스템 정상 종료")

if __name__ == "__main__":
    # 시스템 시작
    try:
        # 환경 변수 확인
        if not BYBIT_ACCESS_KEY or not BYBIT_SECRET_KEY:
            logger.error("Bybit API 키가 설정되지 않았습니다.")
            sys.exit(1)
        
        # AI API 키 확인
        ai_api_key = os.getenv('AI_API_KEY')
        if not ai_api_key:
            logger.warning("AI API 키가 설정되지 않았습니다. 규칙 기반 분석으로 동작합니다.")
        
        # 메인 루프 실행
        asyncio.run(main())
        
    except KeyboardInterrupt:
        logger.info("프로그램이 사용자에 의해 중단되었습니다.")
    except Exception as e:
        logger.critical(f"프로그램 시작 중 오류: {e}", exc_info=True)
        sys.exit(1)