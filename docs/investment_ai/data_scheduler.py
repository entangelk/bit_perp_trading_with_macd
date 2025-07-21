# data_scheduler.py - 직렬 스케줄러로 포워딩

"""
기존 캐시 기반 복잡한 스케줄러를 직렬 카운팅 스케줄러로 교체
기존 코드 호환성을 위해 포워딩 함수들 제공
"""

from docs.investment_ai.serial_scheduler import (
    get_serial_scheduler, 
    run_serial_cycle,
    get_serial_data,
    get_serial_status,
    get_final_decision
)
import logging

logger = logging.getLogger("data_scheduler")

# ========= 🔧 기존 인터페이스와 호환되도록 포워딩 함수들 =========

def get_data_scheduler():
    """기존 호환성을 위한 포워딩 - 직렬 스케줄러 반환"""
    return get_serial_scheduler()

async def run_scheduled_data_collection(initial_run=False):
    """기존 호환성을 위한 포워딩 - 직렬 사이클 실행"""
    logger.info("스케줄링된 데이터 수집 실행 (직렬 스케줄러로 포워딩)")
    return await run_serial_cycle()

def get_data_status():
    """기존 호환성을 위한 포워딩 - 직렬 스케줄러 상태"""
    return get_serial_status()

# ========= 개별 데이터 요청 함수들 (기존 호환성) =========

async def get_chart_data():
    """차트 데이터 요청 - 직렬 스케줄러에서 chart_update 결과"""
    return get_serial_data("chart_update")

async def get_fear_greed_data():
    """공포/탐욕 지수 요청 - 감정분석 결과에 포함"""
    sentiment_result = get_serial_data("ai_sentiment_analysis")
    if sentiment_result and isinstance(sentiment_result, dict):
        # 감정 분석 결과에서 공포탐욕 지수 추출
        return {
            'current_fng': sentiment_result.get('fear_greed_index', 50),
            'timestamp': sentiment_result.get('analysis_timestamp', 'unknown')
        }
    return None

async def get_news_data():
    """뉴스 데이터 요청 - 감정분석 결과에 포함"""
    sentiment_result = get_serial_data("ai_sentiment_analysis") 
    if sentiment_result and isinstance(sentiment_result, dict):
        # 감정 분석 결과에서 뉴스 데이터 추출
        return {
            'news': sentiment_result.get('news_summary', []),
            'count': len(sentiment_result.get('news_summary', [])),
            'timestamp': sentiment_result.get('analysis_timestamp', 'unknown')
        }
    return None

async def get_macro_data():
    """거시경제 데이터 요청"""
    return get_serial_data("ai_macro_analysis")

async def get_onchain_data():
    """온체인 데이터 요청"""
    return get_serial_data("ai_onchain_analysis")

async def get_institutional_data():
    """기관투자 데이터 요청"""
    return get_serial_data("ai_institutional_analysis")

async def get_position_data():
    """포지션 데이터 요청"""
    return get_serial_data("position_data")

# ========= AI 분석 결과 요청 함수들 (기존 호환성) =========

async def get_ai_sentiment_analysis():
    """AI 시장 감정 분석 결과 요청"""
    return get_serial_data("ai_sentiment_analysis")

async def get_ai_technical_analysis():
    """AI 기술적 분석 결과 요청"""
    return get_serial_data("ai_technical_analysis")

async def get_ai_macro_analysis():
    """AI 거시경제 분석 결과 요청"""
    return get_serial_data("ai_macro_analysis")

async def get_ai_onchain_analysis():
    """AI 온체인 분석 결과 요청"""
    return get_serial_data("ai_onchain_analysis")

async def get_ai_institutional_analysis():
    """AI 기관투자 분석 결과 요청"""
    return get_serial_data("ai_institutional_analysis")

# ========= 기타 호환성 함수들 =========

def get_recovery_status():
    """복구 상태 - 직렬 스케줄러에서는 단순화"""
    status = get_serial_status()
    
    disabled_tasks = []
    healthy_tasks = []
    
    for task_name, task_info in status.get('tasks', {}).items():
        if task_info.get('is_disabled', False):
            disabled_tasks.append(task_name)
        else:
            healthy_tasks.append(task_name)
    
    return {
        'disabled_tasks': disabled_tasks,
        'recovering_tasks': [],  # 직렬 스케줄러에서는 자동 복구 없음
        'healthy_tasks': healthy_tasks,
        'next_recovery_times': {}
    }

def force_recovery(task_name: str = None):
    """강제 복구 - 에러 카운트 리셋"""
    scheduler = get_serial_scheduler()
    scheduler.reset_errors(task_name)
    return True

def reset_errors(task_name: str = None):
    """에러 카운트 리셋"""
    scheduler = get_serial_scheduler()
    scheduler.reset_errors(task_name)
    return True

# ========= AI API 상태 관리 (기존 호환성 - 단순화) =========

_ai_api_status = {
    'is_working': True,
    'last_success_time': None,
    'last_failure_time': None,
    'consecutive_failures': 0,
    'last_check_time': None
}

def check_ai_api_status():
    """AI API 상태 확인"""
    return _ai_api_status.copy()

def mark_ai_api_success():
    """AI API 성공 시 호출"""
    global _ai_api_status
    import datetime
    _ai_api_status.update({
        'is_working': True,
        'last_success_time': datetime.datetime.now(),
        'consecutive_failures': 0,
        'last_check_time': datetime.datetime.now()
    })
    logger.info("AI API 작동 상태: 정상")

def mark_ai_api_failure():
    """AI API 실패 시 호출"""
    global _ai_api_status
    import datetime
    _ai_api_status.update({
        'last_failure_time': datetime.datetime.now(),
        'consecutive_failures': _ai_api_status['consecutive_failures'] + 1,
        'last_check_time': datetime.datetime.now()
    })
    
    if _ai_api_status['consecutive_failures'] >= 3:
        _ai_api_status['is_working'] = False
        logger.error(f"AI API 비작동 상태: {_ai_api_status['consecutive_failures']}회 연속 실패")
    else:
        logger.warning(f"AI API 실패: {_ai_api_status['consecutive_failures']}/3회")

async def test_ai_api_connection():
    """AI API 연결 테스트"""
    try:
        # 간단한 감정 분석 테스트
        from docs.investment_ai.analyzers.sentiment_analyzer import SentimentAnalyzer
        analyzer = SentimentAnalyzer()
        
        if analyzer.client is None:
            mark_ai_api_failure()
            return False
        
        # 간단한 테스트 프롬프트
        test_prompt = "Hello, respond with just 'OK'"
        response = analyzer.client.models.generate_content("gemini-1.5-flash", test_prompt)
        
        if response and response.text:
            mark_ai_api_success()
            return True
        else:
            mark_ai_api_failure()
            return False
            
    except Exception as e:
        logger.error(f"AI API 연결 테스트 실패: {e}")
        mark_ai_api_failure()
        return False

def get_ai_api_status_summary():
    """AI API 상태 요약 정보"""
    status = check_ai_api_status()
    return {
        'is_working': status['is_working'],
        'consecutive_failures': status['consecutive_failures'],
        'last_success': status['last_success_time'].isoformat() if status['last_success_time'] else None,
        'last_failure': status['last_failure_time'].isoformat() if status['last_failure_time'] else None,
        'status_text': 'AI API 정상 작동' if status['is_working'] else f'AI API 비작동 ({status["consecutive_failures"]}회 실패)'
    }

# ========= 스케줄러 클래스 포워딩 (ai_trading_integration.py 호환용) =========

class DataScheduler:
    """기존 스케줄러 클래스 호환을 위한 포워딩 래퍼"""
    
    def __init__(self):
        self._serial_scheduler = get_serial_scheduler()
    
    def get_cached_data(self, task_name: str):
        """캐시된 데이터 조회 - 직렬 스케줄러의 마지막 결과 반환"""
        return self._serial_scheduler.get_data(task_name)
    
    async def get_data(self, task_name: str):
        """데이터 요청 - 비동기 버전"""
        return self._serial_scheduler.get_data(task_name)
    
    def get_task_status(self):
        """작업 상태 반환"""
        return self._serial_scheduler.get_status()

# 전역 스케줄러 인스턴스 (기존 호환성)
_global_scheduler = None

def get_data_scheduler():
    """전역 데이터 스케줄러 반환 - 포워딩"""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = DataScheduler()
    return _global_scheduler

logger.info("데이터 스케줄러: 직렬 스케줄러로 포워딩 설정 완료")