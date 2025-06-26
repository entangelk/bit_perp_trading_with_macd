"""
AI 투자 시스템용 데이터 수집 스케줄러
각 데이터 소스별로 최적화된 수집 주기 관리
"""

import asyncio
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass
import json

logger = logging.getLogger("data_scheduler")

@dataclass
class DataTask:
    """데이터 수집 작업 정의"""
    name: str
    func: Callable
    interval_minutes: int
    last_run: Optional[datetime] = None
    data_cache: Any = None
    cache_duration_minutes: int = 0  # 0이면 캐시 사용 안함
    is_running: bool = False
    error_count: int = 0
    max_errors: int = 3

class DataScheduler:
    """데이터 수집 스케줄러"""
    
    def __init__(self, main_interval_minutes: int = 15):
        self.main_interval = main_interval_minutes
        self.tasks: Dict[str, DataTask] = {}
        self.running = False
        
        # 기본 데이터 수집 작업들 등록
        self._register_default_tasks()
    
    def _register_default_tasks(self):
        """기본 데이터 수집 작업들 등록"""
        
        # 1. 차트 데이터 - 15분마다 (메인 주기와 동일)
        self.register_task(
            name="chart_data",
            func=self._collect_chart_data,
            interval_minutes=15,
            cache_duration_minutes=5  # 5분간 캐시
        )
        
        # 2. 공포/탐욕 지수 - 4시간마다 (하루 6번)
        self.register_task(
            name="fear_greed_index",
            func=self._collect_fear_greed_data,
            interval_minutes=240,  # 4시간
            cache_duration_minutes=120  # 2시간 캐시
        )
        
        # 3. 뉴스 데이터 - 30분마다
        self.register_task(
            name="crypto_news",
            func=self._collect_news_data,
            interval_minutes=30,
            cache_duration_minutes=15  # 15분 캐시
        )
        
        # 4. 거시경제 데이터 - 6시간마다 (하루 4번)
        self.register_task(
            name="macro_economic",
            func=self._collect_macro_data,
            interval_minutes=360,  # 6시간
            cache_duration_minutes=180  # 3시간 캐시
        )
        
        # 5. 온체인 데이터 - 1시간마다
        self.register_task(
            name="onchain_data",
            func=self._collect_onchain_data,
            interval_minutes=60,
            cache_duration_minutes=30  # 30분 캐시
        )
        
        # 6. 기관 투자 데이터 - 2시간마다
        self.register_task(
            name="institutional_data",
            func=self._collect_institutional_data,
            interval_minutes=120,
            cache_duration_minutes=60  # 1시간 캐시
        )
        
        # 7. 포지션/잔고 데이터 - 실시간 (캐시 없음)
        self.register_task(
            name="position_data",
            func=self._collect_position_data,
            interval_minutes=0,  # 항상 실시간
            cache_duration_minutes=0  # 캐시 없음
        )
    
    def register_task(self, name: str, func: Callable, interval_minutes: int, 
                     cache_duration_minutes: int = 0):
        """새로운 데이터 수집 작업 등록"""
        self.tasks[name] = DataTask(
            name=name,
            func=func,
            interval_minutes=interval_minutes,
            cache_duration_minutes=cache_duration_minutes
        )
        logger.info(f"데이터 작업 등록: {name} (수집주기: {interval_minutes}분, 캐시: {cache_duration_minutes}분)")
    
    def should_run_task(self, task: DataTask) -> bool:
        """작업 실행 여부 판단"""
        if task.is_running:
            return False
        
        # 실시간 데이터는 항상 실행
        if task.interval_minutes == 0:
            return True
        
        # 첫 실행
        if task.last_run is None:
            return True
        
        # 주기 확인
        time_since_last = datetime.now(timezone.utc) - task.last_run
        return time_since_last.total_seconds() >= task.interval_minutes * 60
    
    def get_cached_data(self, task_name: str) -> Optional[Any]:
        """캐시된 데이터 반환"""
        if task_name not in self.tasks:
            return None
        
        task = self.tasks[task_name]
        
        # 캐시가 없거나 만료된 경우
        if (task.cache_duration_minutes == 0 or 
            task.data_cache is None or 
            task.last_run is None):
            return None
        
        # 캐시 만료 확인
        cache_age = datetime.now(timezone.utc) - task.last_run
        if cache_age.total_seconds() > task.cache_duration_minutes * 60:
            return None
        
        logger.debug(f"캐시된 데이터 사용: {task_name}")
        return task.data_cache
    
    async def run_task(self, task: DataTask) -> Optional[Any]:
        """개별 작업 실행"""
        try:
            task.is_running = True
            logger.debug(f"데이터 수집 시작: {task.name}")
            
            start_time = datetime.now()
            result = await task.func()
            end_time = datetime.now()
            
            duration = (end_time - start_time).total_seconds()
            
            # 성공 시 캐시 업데이트
            if result is not None:
                task.data_cache = result
                task.last_run = datetime.now(timezone.utc)
                task.error_count = 0  # 에러 카운트 리셋
                logger.debug(f"데이터 수집 완료: {task.name} ({duration:.2f}초)")
            else:
                task.error_count += 1
                logger.warning(f"데이터 수집 실패: {task.name} (오류 {task.error_count}/{task.max_errors})")
            
            return result
            
        except Exception as e:
            task.error_count += 1
            logger.error(f"데이터 수집 중 오류: {task.name} - {str(e)}")
            return None
        finally:
            task.is_running = False
    
    async def get_data(self, task_name: str) -> Optional[Any]:
        """데이터 요청 (캐시 우선, 필요시 수집)"""
        if task_name not in self.tasks:
            logger.error(f"등록되지 않은 데이터 작업: {task_name}")
            return None
        
        task = self.tasks[task_name]
        
        # 에러가 너무 많으면 스킵
        if task.error_count >= task.max_errors:
            logger.warning(f"데이터 작업 스킵 (최대 오류 횟수 초과): {task_name}")
            return task.data_cache  # 마지막 성공 데이터라도 반환
        
        # 캐시된 데이터 확인
        cached_data = self.get_cached_data(task_name)
        if cached_data is not None:
            return cached_data
        
        # 수집 필요 여부 확인
        if self.should_run_task(task):
            return await self.run_task(task)
        else:
            # 수집 주기가 아니면 마지막 데이터 반환
            return task.data_cache
    
    async def run_scheduled_collections(self):
        """예정된 수집 작업들 실행"""
        logger.info("예정된 데이터 수집 작업 실행")
        
        tasks_to_run = []
        for task_name, task in self.tasks.items():
            if self.should_run_task(task) and task.interval_minutes > 0:
                tasks_to_run.append((task_name, task))
        
        if not tasks_to_run:
            logger.debug("실행할 예정 작업 없음")
            return
        
        logger.info(f"실행할 작업: {[name for name, _ in tasks_to_run]}")
        
        # 병렬 실행
        await asyncio.gather(*[self.run_task(task) for _, task in tasks_to_run])
    
    def get_task_status(self) -> Dict:
        """모든 작업의 상태 반환"""
        status = {}
        for task_name, task in self.tasks.items():
            status[task_name] = {
                'interval_minutes': task.interval_minutes,
                'last_run': task.last_run.isoformat() if task.last_run else None,
                'has_cache': task.data_cache is not None,
                'is_running': task.is_running,
                'error_count': task.error_count,
                'cache_age_minutes': 0
            }
            
            # 캐시 나이 계산
            if task.last_run:
                cache_age = datetime.now(timezone.utc) - task.last_run
                status[task_name]['cache_age_minutes'] = cache_age.total_seconds() / 60
        
        return status
    
    # ============= 데이터 수집 함수들 =============
    
    async def _collect_chart_data(self):
        """차트 데이터 수집"""
        try:
            # 기존 차트 업데이트 함수 사용
            from docs.get_chart import chart_update_one
            result, server_time, execution_time = chart_update_one('15m', 'BTCUSDT')
            return {
                'success': result is not None,
                'server_time': server_time,
                'execution_time': execution_time,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error(f"차트 데이터 수집 오류: {e}")
            return None
    
    async def _collect_fear_greed_data(self):
        """공포/탐욕 지수 수집"""
        try:
            import requests
            response = requests.get("https://api.alternative.me/fng/?limit=7", timeout=10)
            if response.status_code == 200:
                data = response.json()
                return {
                    'data': data,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
        except Exception as e:
            logger.error(f"공포/탐욕 지수 수집 오류: {e}")
        return None
    
    async def _collect_news_data(self):
        """뉴스 데이터 수집"""
        try:
            import feedparser
            
            news_sources = {
                'cointelegraph': 'https://cointelegraph.com/rss',
                'coindesk': 'https://www.coindesk.com/arc/outboundfeeds/rss/',
            }
            
            all_news = []
            for source_name, rss_url in news_sources.items():
                try:
                    feed = feedparser.parse(rss_url)
                    for entry in feed.entries[:5]:  # 최신 5개만
                        title = entry.get('title', '').lower()
                        if any(keyword in title for keyword in ['bitcoin', 'btc', 'crypto']):
                            all_news.append({
                                'title': entry.get('title', ''),
                                'summary': entry.get('summary', '')[:200],
                                'source': source_name,
                                'published_time': getattr(entry, 'published', ''),
                                'link': entry.get('link', '')
                            })
                except Exception as e:
                    logger.warning(f"{source_name} 뉴스 수집 실패: {e}")
            
            return {
                'news': all_news,
                'count': len(all_news),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error(f"뉴스 데이터 수집 오류: {e}")
        return None
    
    async def _collect_macro_data(self):
        """거시경제 데이터 수집 (더미 데이터)"""
        # 실제로는 경제 지표 API를 호출해야 함
        return {
            'indicators': {
                'dxy': 103.5,  # 달러지수
                'gold': 2650,  # 금 가격
                'sp500': 4500,  # S&P 500
                'interest_rate': 5.25  # 기준금리
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    async def _collect_onchain_data(self):
        """온체인 데이터 수집 (더미 데이터)"""
        # 실제로는 온체인 분석 API를 호출해야 함
        return {
            'metrics': {
                'hash_rate': 450000000,  # TH/s
                'difficulty': 72000000000000,
                'active_addresses': 980000,
                'transaction_count': 350000
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    async def _collect_institutional_data(self):
        """기관 투자 데이터 수집 (더미 데이터)"""
        # 실제로는 기관 투자 관련 API를 호출해야 함
        return {
            'flows': {
                'etf_inflow': 150000000,  # 달러
                'institutional_holdings': 800000,  # BTC
                'corporate_treasury': 250000  # BTC
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    async def _collect_position_data(self):
        """포지션/잔고 데이터 수집"""
        try:
            from docs.get_current import fetch_investment_status
            balance, positions_json, ledger = fetch_investment_status()
            
            if balance == 'error':
                return None
            
            return {
                'balance': balance,
                'positions': positions_json,
                'ledger': ledger[:10] if ledger else [],  # 최근 10개만
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error(f"포지션 데이터 수집 오류: {e}")
        return None

# 전역 스케줄러 인스턴스
_global_scheduler: Optional[DataScheduler] = None

def get_data_scheduler() -> DataScheduler:
    """전역 데이터 스케줄러 반환"""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = DataScheduler()
    return _global_scheduler

# 편의 함수들
async def get_chart_data():
    """차트 데이터 요청"""
    scheduler = get_data_scheduler()
    return await scheduler.get_data("chart_data")

async def get_fear_greed_data():
    """공포/탐욕 지수 요청"""
    scheduler = get_data_scheduler()
    return await scheduler.get_data("fear_greed_index")

async def get_news_data():
    """뉴스 데이터 요청"""
    scheduler = get_data_scheduler()
    return await scheduler.get_data("crypto_news")

async def get_macro_data():
    """거시경제 데이터 요청"""
    scheduler = get_data_scheduler()
    return await scheduler.get_data("macro_economic")

async def get_onchain_data():
    """온체인 데이터 요청"""
    scheduler = get_data_scheduler()
    return await scheduler.get_data("onchain_data")

async def get_institutional_data():
    """기관 투자 데이터 요청"""
    scheduler = get_data_scheduler()
    return await scheduler.get_data("institutional_data")

async def get_position_data():
    """포지션 데이터 요청"""
    scheduler = get_data_scheduler()
    return await scheduler.get_data("position_data")

async def run_scheduled_data_collection():
    """예정된 데이터 수집 실행"""
    scheduler = get_data_scheduler()
    await scheduler.run_scheduled_collections()

def get_data_status():
    """데이터 수집 상태 확인"""
    scheduler = get_data_scheduler()
    return scheduler.get_task_status()

# 테스트용 코드
if __name__ == "__main__":
    async def test():
        print("📊 데이터 스케줄러 테스트 시작")
        
        scheduler = get_data_scheduler()
        
        # 상태 확인
        print("\n=== 초기 상태 ===")
        status = scheduler.get_task_status()
        for task_name, info in status.items():
            print(f"{task_name}: 주기 {info['interval_minutes']}분, 캐시 {info['cache_age_minutes']:.1f}분")
        
        # 차트 데이터 테스트
        print("\n=== 차트 데이터 수집 테스트 ===")
        chart_data = await get_chart_data()
        print(f"차트 데이터: {chart_data is not None}")
        
        # 공포/탐욕 지수 테스트
        print("\n=== 공포/탐욕 지수 수집 테스트 ===")
        fg_data = await get_fear_greed_data()
        print(f"공포/탐욕 데이터: {fg_data is not None}")
        
        # 예정된 수집 실행
        print("\n=== 예정된 수집 실행 ===")
        await run_scheduled_data_collection()
        
        # 최종 상태
        print("\n=== 최종 상태 ===")
        final_status = get_data_status()
        for task_name, info in final_status.items():
            cache_status = "캐시됨" if info['has_cache'] else "없음"
            print(f"{task_name}: {cache_status}, 오류 {info['error_count']}회")
    
    asyncio.run(test())