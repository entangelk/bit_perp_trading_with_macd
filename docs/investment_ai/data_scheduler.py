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
from pymongo import MongoClient

logger = logging.getLogger("data_scheduler")

# AI API 상태 전역 변수
_ai_api_status = {
    'is_working': True,
    'last_success_time': None,
    'last_failure_time': None,
    'consecutive_failures': 0,
    'last_check_time': None
}

@dataclass
class DataTask:
    """데이터 수집 작업 정의"""
    name: str
    func: Callable
    interval_minutes: int
    last_run: Optional[datetime] = None
    cache_duration_minutes: int = 0  # 0이면 캐시 사용 안함
    is_running: bool = False
    error_count: int = 0
    max_errors: int = 3
    last_error_time: Optional[datetime] = None  # 마지막 에러 발생 시간
    auto_recovery_enabled: bool = True  # 자동 복구 활성화
    recovery_interval_hours: int = 2  # 복구 시도 간격 (시간)

class DataScheduler:
    """데이터 수집 스케줄러"""
    
    def __init__(self, main_interval_minutes: int = 15):
        self.main_interval = main_interval_minutes
        self.tasks: Dict[str, DataTask] = {}
        self.running = False
        
        # MongoDB 연결 설정
        self._setup_mongodb()
        
        # 기본 데이터 수집 작업들 등록
        self._register_default_tasks()
    
    def _setup_mongodb(self):
        """MongoDB 연결 및 캐시 컬렉션 설정"""
        try:
            self.mongo_client = MongoClient("mongodb://mongodb:27017")
            self.database = self.mongo_client["bitcoin"]
            self.cache_collection = self.database["data_cache"]
            
            # 만료 시간을 위한 TTL 인덱스 생성 (expire_at 필드에 대해)
            try:
                self.cache_collection.create_index("expire_at", expireAfterSeconds=0)
                logger.info("데이터 캐시 컬렉션 TTL 인덱스 생성 완료")
            except Exception as e:
                logger.debug(f"TTL 인덱스 생성 오류 (이미 존재할 수 있음): {e}")
                
            logger.info("MongoDB 데이터 캐시 연결 완료")
        except Exception as e:
            logger.error(f"MongoDB 연결 실패: {e}")
            self.mongo_client = None
            self.database = None
            self.cache_collection = None
    
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
        
        # ========= AI 분석 결과 작업들 =========
        
        # 8. 시장 감정 AI 분석 - 30분마다
        self.register_task(
            name="ai_sentiment_analysis",
            func=self._collect_ai_sentiment_analysis,
            interval_minutes=30,
            cache_duration_minutes=25  # 25분 캐시
        )
        
        # 9. 기술적 분석 AI 분석 - 15분마다 (메인 주기와 동일)
        self.register_task(
            name="ai_technical_analysis",
            func=self._collect_ai_technical_analysis,
            interval_minutes=15,
            cache_duration_minutes=10  # 10분 캐시
        )
        
        # 10. 거시경제 AI 분석 - 6시간마다
        self.register_task(
            name="ai_macro_analysis",
            func=self._collect_ai_macro_analysis,
            interval_minutes=360,  # 6시간
            cache_duration_minutes=300  # 5시간 캐시
        )
        
        # 11. 온체인 AI 분석 - 1시간마다
        self.register_task(
            name="ai_onchain_analysis",
            func=self._collect_ai_onchain_analysis,
            interval_minutes=60,
            cache_duration_minutes=50  # 50분 캐시
        )
        
        # 12. 기관투자 AI 분석 - 2시간마다
        self.register_task(
            name="ai_institutional_analysis",
            func=self._collect_ai_institutional_analysis,
            interval_minutes=120,
            cache_duration_minutes=100  # 100분 캐시
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
        """MongoDB에서 캐시된 데이터 반환"""
        if task_name not in self.tasks:
            return None
        
        task = self.tasks[task_name]
        
        # 캐시 사용 안하는 경우
        if task.cache_duration_minutes == 0 or self.cache_collection is None:
            return None
        
        try:
            # MongoDB에서 캐시 데이터 조회
            cache_doc = self.cache_collection.find_one({
                "task_name": task_name,
                "expire_at": {"$gt": datetime.now(timezone.utc)}
            })
            
            if cache_doc:
                logger.debug(f"MongoDB 캐시된 데이터 사용: {task_name}")
                return cache_doc.get("data")
            
            return None
        except Exception as e:
            logger.error(f"캐시 데이터 조회 오류: {e}")
            return None
    
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
                self._update_cache(task, result)
                task.last_run = datetime.now(timezone.utc)
                task.error_count = 0  # 에러 카운트 리셋
                logger.debug(f"데이터 수집 완료: {task.name} ({duration:.2f}초)")
            else:
                task.error_count += 1
                task.last_error_time = datetime.now(timezone.utc)
                logger.warning(f"데이터 수집 실패: {task.name} (오류 {task.error_count}/{task.max_errors})")
            
            return result
            
        except Exception as e:
            task.error_count += 1
            task.last_error_time = datetime.now(timezone.utc)
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
        
        # 에러가 너무 많으면 스킵 (AI 분석 작업에 대해서는 더 엄격하게 처리)
        if task.error_count >= task.max_errors:
            # 자동 복구 시도
            if self._should_attempt_auto_recovery(task):
                logger.info(f"자동 복구 시도: {task_name} (에러 후 {self._get_hours_since_last_error(task):.1f}시간 경과)")
                task.error_count = max(0, task.error_count - 1)  # 에러 카운트 1 감소
                task.last_error_time = datetime.now(timezone.utc)  # 복구 시도 시간 기록
                
                # 복구 시도 후 다시 실행 가능하므로 계속 진행
            else:
                if task_name.startswith('ai_'):
                    hours_since_error = self._get_hours_since_last_error(task)
                    logger.warning(f"AI 분석 작업 비활성화 (연속 {task.error_count}회 실패): {task_name} - 다음 자동 복구까지 {task.recovery_interval_hours - hours_since_error:.1f}시간")
                    # AI 분석 실패 시 실패 정보를 포함한 결과 반환
                    return {
                        'analysis_result': {
                            'success': False,
                            'skip_reason': 'analyzer_disabled',
                            'error': f'연속 {task.error_count}회 실패로 분석기 비활성화',
                            'error_count': task.error_count,
                            'max_errors': task.max_errors,
                            'next_recovery_in_hours': task.recovery_interval_hours - hours_since_error
                        },
                        'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                        'disabled': True
                    }
                else:
                    logger.warning(f"데이터 작업 스킵 (최대 오류 횟수 초과): {task_name}")
                    return self.get_cached_data(task_name)  # 마지막 성공 데이터라도 반환
        
        # 캐시된 데이터 확인
        cached_data = self.get_cached_data(task_name)
        if cached_data is not None:
            return cached_data
        
        # 수집 필요 여부 확인
        if self.should_run_task(task):
            return await self.run_task(task)
        else:
            # 수집 주기가 아니면 마지막 데이터 반환
            return self.get_cached_data(task_name)
    
    async def run_scheduled_collections(self):
        """예정된 수집 작업들 실행"""
        logger.info("예정된 데이터 수집 작업 실행")
        
        tasks_to_run = []
        disabled_tasks = []
        
        for task_name, task in self.tasks.items():
            if task.interval_minutes > 0:  # 스케줄링된 작업만
                if task.error_count >= task.max_errors:
                    disabled_tasks.append(task_name)
                elif self.should_run_task(task):
                    tasks_to_run.append((task_name, task))
        
        if disabled_tasks:
            logger.warning(f"비활성화된 작업들 (최대 오류 초과): {disabled_tasks}")
        
        if not tasks_to_run:
            logger.debug("실행할 예정 작업 없음")
            return
        
        logger.info(f"실행할 작업: {[name for name, _ in tasks_to_run]}")
        
        # 병렬 실행
        await asyncio.gather(*[self.run_task(task) for _, task in tasks_to_run])
    
    def _update_cache(self, task: DataTask, data: Any):
        """MongoDB에 캐시 데이터 저장"""
        if task.cache_duration_minutes == 0 or self.cache_collection is None:
            return
        
        try:
            expire_at = datetime.now(timezone.utc) + timedelta(minutes=task.cache_duration_minutes)
            
            # upsert를 사용하여 기존 데이터 업데이트 또는 새로 삽입
            self.cache_collection.replace_one(
                {"task_name": task.name},
                {
                    "task_name": task.name,
                    "data": data,
                    "created_at": datetime.now(timezone.utc),
                    "expire_at": expire_at
                },
                upsert=True
            )
            logger.debug(f"MongoDB 캐시 업데이트: {task.name}")
        except Exception as e:
            logger.error(f"캐시 업데이트 오류: {e}")
    
    def get_task_status(self) -> Dict:
        """모든 작업의 상태 반환"""
        status = {}
        for task_name, task in self.tasks.items():
            has_cache = False
            cache_age_minutes = 0
            
            # MongoDB에서 캐시 상태 확인
            if self.cache_collection is not None:
                try:
                    cache_doc = self.cache_collection.find_one({"task_name": task_name})
                    if cache_doc:
                        has_cache = True
                        if cache_doc.get("created_at"):
                            cache_age = datetime.now(timezone.utc) - cache_doc["created_at"]
                            cache_age_minutes = cache_age.total_seconds() / 60
                except Exception as e:
                    logger.error(f"캐시 상태 확인 오류: {e}")
            
            # 복구 정보 계산
            hours_since_error = self._get_hours_since_last_error(task)
            is_disabled = task.error_count >= task.max_errors
            can_auto_recover = self._should_attempt_auto_recovery(task)
            
            status[task_name] = {
                'interval_minutes': task.interval_minutes,
                'last_run': task.last_run.isoformat() if task.last_run else None,
                'has_cache': has_cache,
                'is_running': task.is_running,
                'error_count': task.error_count,
                'max_errors': task.max_errors,
                'is_disabled': is_disabled,
                'cache_age_minutes': cache_age_minutes,
                'auto_recovery': {
                    'enabled': task.auto_recovery_enabled,
                    'last_error_time': task.last_error_time.isoformat() if task.last_error_time else None,
                    'hours_since_error': round(hours_since_error, 1),
                    'recovery_interval_hours': task.recovery_interval_hours,
                    'can_recover_now': can_auto_recover,
                    'next_recovery_in_hours': max(0, task.recovery_interval_hours - hours_since_error) if is_disabled else 0
                }
            }
        
        return status
    
    def reset_task_errors(self, task_name: str) -> bool:
        """특정 작업의 에러 카운트 리셋 (수동 복구용)"""
        if task_name in self.tasks:
            old_count = self.tasks[task_name].error_count
            self.tasks[task_name].error_count = 0
            logger.info(f"작업 에러 카운트 리셋: {task_name} ({old_count} → 0)")
            return True
        return False
    
    def reset_all_errors(self) -> int:
        """모든 작업의 에러 카운트 리셋"""
        reset_count = 0
        for task_name, task in self.tasks.items():
            if task.error_count > 0:
                task.error_count = 0
                reset_count += 1
        logger.info(f"모든 작업 에러 카운트 리셋: {reset_count}개 작업")
        return reset_count
    
    def _should_attempt_auto_recovery(self, task: DataTask) -> bool:
        """자동 복구 시도 여부 판단"""
        if not task.auto_recovery_enabled:
            return False
        
        if task.last_error_time is None:
            return False
        
        hours_since_error = self._get_hours_since_last_error(task)
        return hours_since_error >= task.recovery_interval_hours
    
    def _get_hours_since_last_error(self, task: DataTask) -> float:
        """마지막 에러 이후 경과 시간 (시간 단위)"""
        if task.last_error_time is None:
            return 0
        
        time_diff = datetime.now(timezone.utc) - task.last_error_time
        return time_diff.total_seconds() / 3600
    
    def get_recovery_status(self) -> Dict:
        """자동 복구 상태 확인"""
        recovery_info = {
            'disabled_tasks': [],
            'recovering_tasks': [],
            'healthy_tasks': [],
            'next_recovery_times': {}
        }
        
        for task_name, task in self.tasks.items():
            if task.error_count >= task.max_errors:
                hours_since_error = self._get_hours_since_last_error(task)
                time_to_recovery = max(0, task.recovery_interval_hours - hours_since_error)
                
                if time_to_recovery <= 0:
                    recovery_info['recovering_tasks'].append(task_name)
                else:
                    recovery_info['disabled_tasks'].append(task_name)
                    recovery_info['next_recovery_times'][task_name] = time_to_recovery
            else:
                recovery_info['healthy_tasks'].append(task_name)
        
        return recovery_info
    
    def force_recovery_attempt(self, task_name: str) -> bool:
        """특정 작업의 강제 복구 시도"""
        if task_name not in self.tasks:
            return False
        
        task = self.tasks[task_name]
        if task.error_count >= task.max_errors:
            old_count = task.error_count
            task.error_count = max(0, task.error_count - 2)  # 강제 복구는 2 감소
            task.last_error_time = datetime.now(timezone.utc)
            logger.info(f"강제 복구 시도: {task_name} (에러 카운트: {old_count} → {task.error_count})")
            return True
        
        return False
    
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
    
    # ============= AI 분석 결과 수집 함수들 =============
    
    async def _collect_ai_sentiment_analysis(self):
        """시장 감정 AI 분석 수집 및 저장"""
        try:
            from docs.investment_ai.analyzers.sentiment_analyzer import analyze_market_sentiment
            
            # 원시 데이터 확인 (뉴스, 공포/탐욕 지수)
            news_data = self.get_cached_data("crypto_news")
            fear_greed_data = self.get_cached_data("fear_greed_index")
            
            # 최소 데이터 요구사항 확인
            available_data_sources = 0
            if news_data:
                available_data_sources += 1
            if fear_greed_data:
                available_data_sources += 1
            
            if available_data_sources == 0:
                logger.warning("감정 분석: 모든 원시 데이터 소스 실패 - AI 분석 스킵")
                return {
                    'analysis_result': {
                        'success': False,
                        'skip_reason': 'insufficient_raw_data',
                        'error': '모든 원시 데이터 소스 실패 (뉴스, 공포/탐욕 지수)'
                    },
                    'raw_data_used': {
                        'has_news': False,
                        'has_fear_greed': False
                    },
                    'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                    'skipped': True
                }
            
            # 데이터 품질 확인
            data_quality_issues = []
            if not news_data:
                data_quality_issues.append("뉴스 데이터 없음")
            if not fear_greed_data:
                data_quality_issues.append("공포/탐욕 지수 없음")
            
            # AI 분석 실행 (최소 1개 데이터 소스 있을 때만)
            logger.info(f"감정 분석 실행: {available_data_sources}개 데이터 소스 사용")
            analysis_result = await analyze_market_sentiment()
            
            if analysis_result and analysis_result.get('success', False):
                return {
                    'analysis_result': analysis_result,
                    'raw_data_used': {
                        'has_news': news_data is not None,
                        'has_fear_greed': fear_greed_data is not None,
                        'available_sources': available_data_sources,
                        'quality_issues': data_quality_issues
                    },
                    'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                    'data_freshness': {
                        'news_age_minutes': self._get_data_age_minutes("crypto_news"),
                        'fear_greed_age_minutes': self._get_data_age_minutes("fear_greed_index")
                    }
                }
            else:
                logger.error("감정 분석 AI 호출 실패")
                return {
                    'analysis_result': {
                        'success': False,
                        'skip_reason': 'ai_analysis_failed',
                        'error': 'AI 분석 실행 실패'
                    },
                    'raw_data_used': {
                        'has_news': news_data is not None,
                        'has_fear_greed': fear_greed_data is not None
                    },
                    'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                    'failed': True
                }
                
        except Exception as e:
            logger.error(f"AI 감정 분석 수집 오류: {e}")
            return {
                'analysis_result': {
                    'success': False,
                    'skip_reason': 'exception',
                    'error': f'분석 중 예외 발생: {str(e)}'
                },
                'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                'failed': True
            }
    
    async def _collect_ai_technical_analysis(self):
        """기술적 분석 AI 분석 수집 및 저장"""
        try:
            from docs.investment_ai.analyzers.technical_analyzer import analyze_technical_indicators
            
            # 차트 데이터 확인 (필수)
            chart_data = self.get_cached_data("chart_data")
            if not chart_data:
                logger.warning("기술적 분석: 차트 데이터 없음 - AI 분석 스킵")
                return {
                    'analysis_result': {
                        'success': False,
                        'skip_reason': 'insufficient_raw_data',
                        'error': '차트 데이터 없음 - 기술적 분석 불가'
                    },
                    'raw_data_used': {
                        'has_chart': False
                    },
                    'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                    'skipped': True
                }
            
            # 차트 데이터 품질 확인
            chart_age = self._get_data_age_minutes("chart_data")
            if chart_age > 30:  # 30분 이상 오래된 데이터
                logger.warning(f"기술적 분석: 차트 데이터가 {chart_age:.1f}분 전 데이터임")
            
            # AI 분석 실행
            logger.info("기술적 분석 실행: 차트 데이터 사용")
            analysis_result = await analyze_technical_indicators('BTCUSDT', '15m', 300)
            
            if analysis_result and analysis_result.get('success', False):
                return {
                    'analysis_result': analysis_result,
                    'raw_data_used': {
                        'has_chart': True,
                        'chart_quality': 'fresh' if chart_age <= 30 else 'stale'
                    },
                    'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                    'data_freshness': {
                        'chart_age_minutes': chart_age
                    }
                }
            else:
                logger.error("기술적 분석 AI 호출 실패")
                return {
                    'analysis_result': {
                        'success': False,
                        'skip_reason': 'ai_analysis_failed',
                        'error': 'AI 분석 실행 실패'
                    },
                    'raw_data_used': {
                        'has_chart': True
                    },
                    'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                    'failed': True
                }
                
        except Exception as e:
            logger.error(f"AI 기술적 분석 수집 오류: {e}")
            return {
                'analysis_result': {
                    'success': False,
                    'skip_reason': 'exception',
                    'error': f'분석 중 예외 발생: {str(e)}'
                },
                'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                'failed': True
            }
    
    async def _collect_ai_macro_analysis(self):
        """거시경제 AI 분석 수집 및 저장"""
        try:
            from docs.investment_ai.analyzers.macro_analyzer import analyze_macro_economics
            
            # 거시경제 데이터 확인 (필수)
            macro_data = self.get_cached_data("macro_economic")
            if not macro_data:
                logger.warning("거시경제 분석: 데이터 없음 - AI 분석 스킵")
                return {
                    'analysis_result': {
                        'success': False,
                        'skip_reason': 'insufficient_raw_data',
                        'error': '거시경제 데이터 없음'
                    },
                    'raw_data_used': {'has_macro': False},
                    'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                    'skipped': True
                }
            
            # AI 분석 실행
            logger.info("거시경제 분석 실행")
            analysis_result = await analyze_macro_economics()
            
            if analysis_result and analysis_result.get('success', False):
                return {
                    'analysis_result': analysis_result,
                    'raw_data_used': {'has_macro': True},
                    'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                    'data_freshness': {
                        'macro_age_minutes': self._get_data_age_minutes("macro_economic")
                    }
                }
            else:
                logger.error("거시경제 분석 AI 호출 실패")
                return {
                    'analysis_result': {
                        'success': False,
                        'skip_reason': 'ai_analysis_failed',
                        'error': 'AI 분석 실행 실패'
                    },
                    'raw_data_used': {'has_macro': True},
                    'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                    'failed': True
                }
                
        except Exception as e:
            logger.error(f"AI 거시경제 분석 수집 오류: {e}")
            return {
                'analysis_result': {
                    'success': False,
                    'skip_reason': 'exception',
                    'error': f'분석 중 예외 발생: {str(e)}'
                },
                'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                'failed': True
            }
    
    async def _collect_ai_onchain_analysis(self):
        """온체인 AI 분석 수집 및 저장"""
        try:
            from docs.investment_ai.analyzers.onchain_analyzer import analyze_onchain_data
            
            # 온체인 데이터 확인 (필수)
            onchain_data = self.get_cached_data("onchain_data")
            if not onchain_data:
                logger.warning("온체인 분석: 데이터 없음 - AI 분석 스킵")
                return {
                    'analysis_result': {
                        'success': False,
                        'skip_reason': 'insufficient_raw_data',
                        'error': '온체인 데이터 없음'
                    },
                    'raw_data_used': {'has_onchain': False},
                    'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                    'skipped': True
                }
            
            # AI 분석 실행
            logger.info("온체인 분석 실행")
            analysis_result = await analyze_onchain_data()
            
            if analysis_result and analysis_result.get('success', False):
                return {
                    'analysis_result': analysis_result,
                    'raw_data_used': {'has_onchain': True},
                    'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                    'data_freshness': {
                        'onchain_age_minutes': self._get_data_age_minutes("onchain_data")
                    }
                }
            else:
                logger.error("온체인 분석 AI 호출 실패")
                return {
                    'analysis_result': {
                        'success': False,
                        'skip_reason': 'ai_analysis_failed',
                        'error': 'AI 분석 실행 실패'
                    },
                    'raw_data_used': {'has_onchain': True},
                    'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                    'failed': True
                }
                
        except Exception as e:
            logger.error(f"AI 온체인 분석 수집 오류: {e}")
            return {
                'analysis_result': {
                    'success': False,
                    'skip_reason': 'exception',
                    'error': f'분석 중 예외 발생: {str(e)}'
                },
                'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                'failed': True
            }
    
    async def _collect_ai_institutional_analysis(self):
        """기관투자 AI 분석 수집 및 저장"""
        try:
            from docs.investment_ai.analyzers.institution_analyzer import analyze_institutional_flow
            
            # 기관투자 데이터 확인 (필수)
            institutional_data = self.get_cached_data("institutional_data")
            if not institutional_data:
                logger.warning("기관투자 분석: 데이터 없음 - AI 분석 스킵")
                return {
                    'analysis_result': {
                        'success': False,
                        'skip_reason': 'insufficient_raw_data',
                        'error': '기관투자 데이터 없음'
                    },
                    'raw_data_used': {'has_institutional': False},
                    'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                    'skipped': True
                }
            
            # AI 분석 실행
            logger.info("기관투자 분석 실행")
            analysis_result = await analyze_institutional_flow()
            
            if analysis_result and analysis_result.get('success', False):
                return {
                    'analysis_result': analysis_result,
                    'raw_data_used': {'has_institutional': True},
                    'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                    'data_freshness': {
                        'institutional_age_minutes': self._get_data_age_minutes("institutional_data")
                    }
                }
            else:
                logger.error("기관투자 분석 AI 호출 실패")
                return {
                    'analysis_result': {
                        'success': False,
                        'skip_reason': 'ai_analysis_failed',
                        'error': 'AI 분석 실행 실패'
                    },
                    'raw_data_used': {'has_institutional': True},
                    'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                    'failed': True
                }
                
        except Exception as e:
            logger.error(f"AI 기관투자 분석 수집 오류: {e}")
            return {
                'analysis_result': {
                    'success': False,
                    'skip_reason': 'exception',
                    'error': f'분석 중 예외 발생: {str(e)}'
                },
                'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                'failed': True
            }
    
    def _get_data_age_minutes(self, task_name: str) -> float:
        """특정 데이터의 생성 시간으로부터 경과 시간 계산 (분 단위)"""
        try:
            if self.cache_collection is None:
                return 0
            
            cache_doc = self.cache_collection.find_one({"task_name": task_name})
            if cache_doc and cache_doc.get("created_at"):
                age = datetime.now(timezone.utc) - cache_doc["created_at"]
                return age.total_seconds() / 60
            return 0
        except Exception:
            return 0

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

# AI 분석 결과 요청 함수들
async def get_ai_sentiment_analysis():
    """AI 시장 감정 분석 결과 요청"""
    scheduler = get_data_scheduler()
    return await scheduler.get_data("ai_sentiment_analysis")

async def get_ai_technical_analysis():
    """AI 기술적 분석 결과 요청"""
    scheduler = get_data_scheduler()
    return await scheduler.get_data("ai_technical_analysis")

async def get_ai_macro_analysis():
    """AI 거시경제 분석 결과 요청"""
    scheduler = get_data_scheduler()
    return await scheduler.get_data("ai_macro_analysis")

async def get_ai_onchain_analysis():
    """AI 온체인 분석 결과 요청"""
    scheduler = get_data_scheduler()
    return await scheduler.get_data("ai_onchain_analysis")

async def get_ai_institutional_analysis():
    """AI 기관투자 분석 결과 요청"""
    scheduler = get_data_scheduler()
    return await scheduler.get_data("ai_institutional_analysis")

async def run_scheduled_data_collection():
    """예정된 데이터 수집 실행"""
    scheduler = get_data_scheduler()
    await scheduler.run_scheduled_collections()

def get_data_status():
    """데이터 수집 상태 확인"""
    scheduler = get_data_scheduler()
    return scheduler.get_task_status()

def get_recovery_status():
    """자동 복구 상태 확인"""
    scheduler = get_data_scheduler()
    return scheduler.get_recovery_status()

def force_recovery(task_name: str = None):
    """강제 복구 실행 (특정 작업 또는 전체)"""
    scheduler = get_data_scheduler()
    if task_name:
        return scheduler.force_recovery_attempt(task_name)
    else:
        return scheduler.reset_all_errors()

def reset_errors(task_name: str = None):
    """에러 카운트 리셋 (특정 작업 또는 전체)"""
    scheduler = get_data_scheduler()
    if task_name:
        return scheduler.reset_task_errors(task_name)
    else:
        return scheduler.reset_all_errors()

# AI API 상태 관리 함수들
def check_ai_api_status() -> Dict:
    """AI API 상태 확인"""
    global _ai_api_status
    return _ai_api_status.copy()

def mark_ai_api_success():
    """AI API 성공 시 호출"""
    global _ai_api_status
    _ai_api_status.update({
        'is_working': True,
        'last_success_time': datetime.now(timezone.utc),
        'consecutive_failures': 0,
        'last_check_time': datetime.now(timezone.utc)
    })
    logger.info("AI API 작동 상태: 정상")

def mark_ai_api_failure():
    """AI API 실패 시 호출"""
    global _ai_api_status
    _ai_api_status.update({
        'last_failure_time': datetime.now(timezone.utc),
        'consecutive_failures': _ai_api_status['consecutive_failures'] + 1,
        'last_check_time': datetime.now(timezone.utc)
    })
    
    # 3회 연속 실패 시 비작동 상태로 변경
    if _ai_api_status['consecutive_failures'] >= 3:
        _ai_api_status['is_working'] = False
        logger.error(f"AI API 비작동 상태: {_ai_api_status['consecutive_failures']}회 연속 실패")
    else:
        logger.warning(f"AI API 실패: {_ai_api_status['consecutive_failures']}/3회")

async def test_ai_api_connection() -> bool:
    """AI API 연결 테스트"""
    try:
        # 간단한 AI API 테스트 호출
        from docs.investment_ai.analyzers.sentiment_analyzer import SentimentAnalyzer
        analyzer = SentimentAnalyzer()
        
        # 테스트용 간단한 데이터로 AI 호출 시도
        if analyzer.client is None:
            return False
            
        # 매우 간단한 테스트 프롬프트로 AI 연결 확인
        test_prompt = "Hello, respond with just 'OK'"
        response = analyzer.client.generate_content(test_prompt)
        
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

def get_ai_api_status_summary() -> Dict:
    """AI API 상태 요약 정보"""
    status = check_ai_api_status()
    
    return {
        'is_working': status['is_working'],
        'consecutive_failures': status['consecutive_failures'],
        'last_success': status['last_success_time'].isoformat() if status['last_success_time'] else None,
        'last_failure': status['last_failure_time'].isoformat() if status['last_failure_time'] else None,
        'status_text': 'AI API 정상 작동' if status['is_working'] else f'AI API 비작동 ({status["consecutive_failures"]}회 실패)'
    }

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