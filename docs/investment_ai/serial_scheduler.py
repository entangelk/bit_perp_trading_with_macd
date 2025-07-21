# data_scheduler.py - 기존 인터페이스 유지하면서 내부만 교체

# 🔧 기존 복잡한 스케줄러 코드 전체 삭제하고 아래로 교체

from docs.investment_ai.serial_scheduler import (
    get_serial_scheduler, 
    run_serial_cycle,
    get_serial_data,
    get_serial_status,
    get_final_decision
)
import logging

logger = logging.getLogger("data_scheduler")

# 🔧 기존 인터페이스와 호환되도록 포워딩 함수들

def get_data_scheduler():
    """기존 호환성을 위한 포워딩"""
    return get_serial_scheduler()

async def run_scheduled_data_collection(initial_run=False):
    """기존 호환성을 위한 포워딩 - 직렬 사이클 실행"""
    logger.info("스케줄링된 데이터 수집 실행 (직렬 스케줄러)")
    return await run_serial_cycle()

def get_data_status():
    """기존 호환성을 위한 포워딩"""
    return get_serial_status()

# 개별 데이터 요청 함수들 (기존 호환성)
async def get_chart_data():
    return get_serial_data("chart_update")

async def get_fear_greed_data():
    return get_serial_data("ai_sentiment_analysis")  # 감정분석 결과에 포함

async def get_news_data():
    return get_serial_data("ai_sentiment_analysis")  # 감정분석 결과에 포함

async def get_macro_data():
    return get_serial_data("ai_macro_analysis")

async def get_onchain_data():
    return get_serial_data("ai_onchain_analysis")

async def get_institutional_data():
    return get_serial_data("ai_institutional_analysis")

async def get_position_data():
    return get_serial_data("position_data")

# AI 분석 결과 요청 함수들 (기존 호환성)
async def get_ai_sentiment_analysis():
    return get_serial_data("ai_sentiment_analysis")

async def get_ai_technical_analysis():
    return get_serial_data("ai_technical_analysis")

async def get_ai_macro_analysis():
    return get_serial_data("ai_macro_analysis")

async def get_ai_onchain_analysis():
    return get_serial_data("ai_onchain_analysis")

async def get_ai_institutional_analysis():
    return get_serial_data("ai_institutional_analysis")

# 기타 호환성 함수들
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

# AI API 상태 관리 (기존 호환성 - 단순화)
_ai_api_status = {
    'is_working': True,
    'last_success_time': None,
    'last_failure_time': None,
    'consecutive_failures': 0,
    'last_check_time': None
}

def check_ai_api_status():
    return _ai_api_status.copy()

def mark_ai_api_success():
    global _ai_api_status
    _ai_api_status.update({
        'is_working': True,
        'consecutive_failures': 0
    })

def mark_ai_api_failure():
    global _ai_api_status
    _ai_api_status.update({
        'consecutive_failures': _ai_api_status['consecutive_failures'] + 1
    })
    if _ai_api_status['consecutive_failures'] >= 3:
        _ai_api_status['is_working'] = False

def get_ai_api_status_summary():
    status = check_ai_api_status()
    return {
        'is_working': status['is_working'],
        'consecutive_failures': status['consecutive_failures'],
        'status_text': 'AI API 정상 작동' if status['is_working'] else f'AI API 비작동 ({status["consecutive_failures"]}회 실패)'
    }