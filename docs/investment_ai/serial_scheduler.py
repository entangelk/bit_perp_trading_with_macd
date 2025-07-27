# 직렬 카운팅 기반 스케줄러 (분석기 호출 + MongoDB 저장)

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
from pymongo import MongoClient

logger = logging.getLogger("serial_scheduler")

@dataclass
class SerialTask:
    """직렬 작업 정의"""
    name: str
    func: callable
    interval_cycles: int  # N번의 메인 사이클마다 실행
    stage: str  # 'position', 'analysis', 'chart', 'technical', 'final'
    last_result: any = None
    cycle_counter: int = 0
    error_count: int = 0
    max_errors: int = 5
    is_running: bool = False
    dependencies: List[str] = None  # 의존성 작업들
    cache_duration_minutes: int = 10080  # 기본 7일 캐시 (10080분)

class SerialDataScheduler:
    """직렬 카운팅 기반 스케줄러 - 분석기 호출 + MongoDB 저장"""
    
    def __init__(self, main_cycle_minutes: int = 60):  # 15분 → 60분으로 변경
        self.main_cycle_minutes = main_cycle_minutes
        self.tasks: Dict[str, SerialTask] = {}
        self.global_cycle_count = 0
        
        # MongoDB 연결 설정
        self._setup_mongodb()
        
        # 실행 단계 순서 정의 (데이터 의존성에 따라)
        self.execution_stages = [
            'position',      # 1단계: 포지션 데이터 (실시간)
            'analysis',      # 2단계: 차트 외 분석들 (각자 데이터 수집 포함)
            'chart',         # 3단계: 60분 캔들 차트 업데이트  # 주석 수정
            'technical',     # 4단계: 기술적 분석 (차트 데이터 의존)
            'final'          # 5단계: 최종 결정
        ]
        
        # 작업들 등록
        self._register_tasks()
        
        logger.info(f"직렬 스케줄러 초기화 완료 (메인 사이클: {main_cycle_minutes}분) - MongoDB 저장 기능 포함")

    def _setup_mongodb(self):
        """MongoDB 연결 및 캐시 컬렉션 설정"""
        try:
            self.mongo_client = MongoClient("mongodb://mongodb:27017")
            self.database = self.mongo_client["bitcoin"]
            self.cache_collection = self.database["data_cache"]
            
            # 만료 시간을 위한 TTL 인덱스 생성
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
    
    def _register_tasks(self):
        """작업들 등록 - 분석기 함수 호출만"""
        
        # 🔧 수정: 모든 캐시를 7일(10080분)로 설정
        cache_duration_7days = 10080  # 7일 = 7 * 24 * 60 = 10080분
        
        # 1단계: 포지션 데이터 (매번 실행, 캐시 없음)
        self.register_task("position_data", self._get_position_data, 1, "position", cache_duration_minutes=0)
        
        # 2단계: 차트 외 AI 분석들 (각 분석기가 데이터 수집 포함) - 실행 주기 수정
        self.register_task("ai_sentiment_analysis", self._ai_sentiment_analysis, 1, "analysis", cache_duration_minutes=cache_duration_7days)  # 2→1로 변경: 1시간마다
        self.register_task("ai_macro_analysis", self._ai_macro_analysis, 6, "analysis", cache_duration_minutes=cache_duration_7days)  # 24→6으로 변경: 6시간마다
        self.register_task("ai_onchain_analysis", self._ai_onchain_analysis, 1, "analysis", cache_duration_minutes=cache_duration_7days)  # 4→1로 변경: 1시간마다
        self.register_task("ai_institutional_analysis", self._ai_institutional_analysis, 2, "analysis", cache_duration_minutes=cache_duration_7days)  # 8→2로 변경: 2시간마다
        
        # 3단계: 차트 데이터 업데이트 (매번 실행)
        self.register_task("chart_update", self._update_chart_data, 1, "chart", cache_duration_minutes=cache_duration_7days)
        
        # 4단계: 기술적 분석 (차트 데이터 의존)
        self.register_task("ai_technical_analysis", self._ai_technical_analysis, 1, "technical",
                        dependencies=["chart_update"], cache_duration_minutes=cache_duration_7days)
        
        # 5단계: 최종 결정 (모든 분석 의존)
        self.register_task("final_decision", self._final_decision, 1, "final",
                        dependencies=["ai_technical_analysis", "ai_sentiment_analysis", 
                                    "ai_macro_analysis", "ai_onchain_analysis", 
                                    "ai_institutional_analysis", "position_data"],
                        cache_duration_minutes=cache_duration_7days)
        
        logger.info(f"작업 등록 완료: {len(self.tasks)}개 (모든 캐시 7일 유지)")
        
        # 단계별 작업 수 로깅
        for stage in self.execution_stages:
            stage_tasks = [name for name, task in self.tasks.items() if task.stage == stage]
            logger.info(f"  {stage}: {len(stage_tasks)}개 작업")
    
    def register_task(self, name: str, func: callable, interval_cycles: int, stage: str, 
                     dependencies: List[str] = None, cache_duration_minutes: int = 60):
        """작업 등록"""
        self.tasks[name] = SerialTask(
            name=name,
            func=func,
            interval_cycles=interval_cycles,
            stage=stage,
            dependencies=dependencies or [],
            cache_duration_minutes=cache_duration_minutes
        )
        interval_minutes = interval_cycles * self.main_cycle_minutes
        logger.debug(f"작업 등록: {name} [{stage}] (주기: {interval_minutes}분, 캐시: {cache_duration_minutes}분)")
    
    def should_run_task(self, task: SerialTask, force_all_analysis: bool = False) -> Tuple[bool, str]:
        """작업 실행 여부 판단 - 카운팅 + 의존성 체크 + 초기 강제 실행"""
        if task.is_running:
            return False, "already_running"
        
        if task.error_count >= task.max_errors:
            return False, f"disabled({task.error_count} errors)"
        
        # 🔧 초기 실행시 모든 분석 및 final_decision 강제 실행
        if force_all_analysis and (task.name.startswith('ai_') or task.name == 'final_decision'):
            logger.info(f"🔥 초기 실행: {task.name} 강제 실행")
            return True, "forced_initial_execution"
        
        # 카운팅 기반 실행 주기 체크
        if (self.global_cycle_count % task.interval_cycles) != 0:
            cycles_left = task.interval_cycles - (self.global_cycle_count % task.interval_cycles)
            return False, f"wait_{cycles_left}_cycles"
        
        # 의존성 체크
        missing_deps = []
        for dep_name in task.dependencies:
            if dep_name not in self.tasks:
                missing_deps.append(f"{dep_name}(not_registered)")
                continue
                
            dep_task = self.tasks[dep_name]
            if dep_task.last_result is None:
                missing_deps.append(f"{dep_name}(no_result)")
            elif dep_task.error_count >= dep_task.max_errors:
                missing_deps.append(f"{dep_name}(disabled)")
        
        if missing_deps:
            return False, f"missing_deps:{','.join(missing_deps)}"
        
        return True, "ready"

    def get_cached_data(self, task_name: str) -> Optional[any]:
        """MongoDB에서 캐시된 데이터 반환 - 버그 수정"""
        if task_name not in self.tasks:
            return None
        
        task = self.tasks[task_name]
        
        # 캐시 사용 안하는 경우
        if task.cache_duration_minutes == 0 or self.cache_collection is None:
            return None
        
        try:
            # ✅ 수정: aggregate를 사용해서 가장 확실하게 최신 문서 하나만 가져오기
            pipeline = [
                {
                    "$match": {
                        "task_name": task_name,
                        "expire_at": {"$gt": datetime.now(timezone.utc)}
                    }
                },
                {"$sort": {"created_at": -1}},  # 최신순 정렬
                {"$limit": 1}                   # 하나만 가져오기
            ]
            
            result = list(self.cache_collection.aggregate(pipeline))
            
            if result:
                cache_doc = result[0]
                logger.debug(f"MongoDB 캐시된 데이터 사용: {task_name} (created: {cache_doc.get('created_at')})")
                return cache_doc.get("data")
            else:
                logger.debug(f"MongoDB 캐시 데이터 없음: {task_name}")
                return None
            
        except Exception as e:
            logger.error(f"캐시 데이터 조회 오류 ({task_name}): {e}")
            return None

    def _update_cache(self, task: SerialTask, data: any):
        """MongoDB에 캐시 데이터 저장 - 디버깅 로그 강화"""
        if task.cache_duration_minutes == 0:
            logger.debug(f"캐시 비활성화: {task.name} (cache_duration=0)")
            return
            
        if self.cache_collection is None:
            logger.error(f"MongoDB 연결 없음: {task.name} 저장 실패")
            return
        
        try:
            expire_at = datetime.now(timezone.utc) + timedelta(minutes=task.cache_duration_minutes)
            
            # 저장할 데이터 크기 확인
            data_size = len(str(data)) if data else 0
            logger.info(f"MongoDB 저장 시도: {task.name} (데이터 크기: {data_size}bytes, 만료: {task.cache_duration_minutes}분)")
            
            # 새 문서로 삽입 (덮어쓰지 않음)
            result = self.cache_collection.insert_one({
                "task_name": task.name,
                "data": data,
                "created_at": datetime.now(timezone.utc),
                "expire_at": expire_at
            })
            
            # 저장 결과 확인
            if result.inserted_id:
                logger.info(f"✅ MongoDB 새 문서 생성: {task.name} (ID: {result.inserted_id})")
            else:
                logger.warning(f"⚠️ MongoDB 저장 실패: {task.name}")
                
        except Exception as e:
            logger.error(f"❌ MongoDB 저장 실패: {task.name} - {type(e).__name__}: {e}")
            # 추가 디버깅 정보
            logger.error(f"   데이터 타입: {type(data)}, MongoDB 연결: {self.cache_collection is not None}")
            if hasattr(e, 'details'):
                logger.error(f"   오류 상세: {e.details}")

    
    async def run_task(self, task: SerialTask, stage_name: str, task_index: int, total_tasks: int) -> bool:
        """개별 작업 실행 - MongoDB 저장 기능 추가"""
        try:
            task.is_running = True
            logger.info(f"  {stage_name}-{task_index}: {task.name} 실행 중...")
            
            start_time = datetime.now()
            result = await asyncio.wait_for(task.func(), timeout=180)
            duration = (datetime.now() - start_time).total_seconds()
            
            if result is not None:
                # 🔧 핵심 추가: 메모리 저장
                task.last_result = result
                task.error_count = 0  # 성공 시 에러 카운트 리셋
                
                # 🔧 핵심 추가: MongoDB 저장 (result가 None이 아닐 때만)
                logger.info(f"작업 결과 저장 시도: {task.name} (결과 타입: {type(result)})")
                self._update_cache(task, result)
                
                # 결과 요약 로깅
                result_summary = self._get_result_summary(task.name, result)
                logger.info(f"    ✅ {task.name} 성공 ({duration:.1f}초) - {result_summary}")
                return True
            else:
                task.error_count += 1
                logger.warning(f"    ❌ {task.name} 실패 (결과가 None) - MongoDB 저장하지 않음")
                return False
                
        except asyncio.TimeoutError:
            task.error_count += 1
            logger.error(f"    ⏰ {task.name} 타임아웃 (180초)")
            return False
        except Exception as e:
            task.error_count += 1
            logger.error(f"    💥 {task.name} 오류: {e}")
            return False
        finally:
            task.is_running = False

    async def run_cycle(self, force_all_analysis=False) -> Dict:
        """한 사이클 직렬 실행 - 초기 실행 강제 분석 로직 수정"""
        self.global_cycle_count += 1
        cycle_start = datetime.now()
        
        logger.info(f"=== 직렬 사이클 #{self.global_cycle_count} 시작 (MongoDB 저장 포함) ===")
        if force_all_analysis:
            logger.info("🔥 초기 실행 모드: 모든 AI 분석 강제 실행")
        
        total_tasks_run = 0
        total_tasks_success = 0
        stage_results = {}
        
        # 각 단계별로 순차 실행
        for stage_idx, stage in enumerate(self.execution_stages, 1):
            stage_start = datetime.now()
            
            # 해당 단계의 실행할 작업들 선별
            stage_tasks = []
            skipped_tasks = []
            
            for task_name, task in self.tasks.items():
                if task.stage == stage:
                    # 🔧 수정: force_all_analysis를 should_run_task에 전달
                    should_run, reason = self.should_run_task(task, force_all_analysis)
                    
                    if should_run:
                        stage_tasks.append((task_name, task))
                    else:
                        skipped_tasks.append((task_name, reason))
            
            if not stage_tasks and not skipped_tasks:
                continue  # 해당 단계에 작업이 없음
            
            logger.info(f"{stage_idx}단계: {stage} ({len(stage_tasks)}개 실행, {len(skipped_tasks)}개 스킵)")
            
            # 단계 내 작업들 순차 실행
            stage_success = 0
            for i, (task_name, task) in enumerate(stage_tasks, 1):
                success = await self.run_task(task, stage, i, len(stage_tasks))
                total_tasks_run += 1
                if success:
                    stage_success += 1
                    total_tasks_success += 1
                
                # 작업 간 짧은 대기 (AI 분석의 경우)
                if task_name.startswith('ai_') and i < len(stage_tasks):
                    await asyncio.sleep(0.5)
            
            stage_duration = (datetime.now() - stage_start).total_seconds()
            stage_results[stage] = {
                'tasks_run': len(stage_tasks),
                'tasks_success': stage_success,
                'duration_seconds': stage_duration
            }
            
            if stage_tasks:
                logger.info(f"  {stage} 완료: {stage_success}/{len(stage_tasks)} 성공 ({stage_duration:.1f}초)")
            
            # 단계 간 대기 (데이터 안정화)
            if stage_idx < len(self.execution_stages):
                await asyncio.sleep(0.5)
        
        cycle_duration = (datetime.now() - cycle_start).total_seconds()
        
        logger.info(f"=== 직렬 사이클 #{self.global_cycle_count} 완료 ({cycle_duration:.1f}초) ===")
        logger.info(f"전체 성공률: {total_tasks_success}/{total_tasks_run} (MongoDB 저장 포함)")
        
        # 초기 실행 결과 요약
        if force_all_analysis:
            ai_tasks_run = sum(1 for stage_result in stage_results.values() 
                            for task_name in [t[0] for t in stage_tasks] 
                            if task_name.startswith('ai_'))
            logger.info(f"🔥 초기 실행 완료: AI 분석 {ai_tasks_run}개 실행 및 MongoDB 저장")
        
        return {
            'success': True,
            'cycle_count': self.global_cycle_count,
            'tasks_run': total_tasks_run,
            'tasks_success': total_tasks_success,
            'duration_seconds': cycle_duration,
            'stage_results': stage_results,
            'forced_all_analysis': force_all_analysis,
            'mongodb_enabled': True
        }

    def _get_result_summary(self, task_name: str, result) -> str:
        """결과 요약 생성"""
        try:
            if task_name == "chart_update":
                return f"차트 업데이트 {'성공' if result else '실패'}"
            elif task_name == "position_data":
                if isinstance(result, dict):
                    positions = result.get('positions', '[]')
                    pos_count = len(eval(positions)) if positions != '[]' else 0
                    balance = result.get('balance', {}).get('USDT', {}).get('total', 0) if result.get('balance') else 0
                    return f"포지션 {pos_count}개, 잔고 {balance:.2f} USDT"
                return "포지션 데이터 수집됨"
            elif task_name.startswith('ai_'):
                if isinstance(result, dict) and result.get('success'):
                    confidence = result.get('confidence', result.get('analysis_confidence', 0))
                    signal = result.get('investment_signal', result.get('btc_signal', result.get('final_decision', 'N/A')))
                    return f"{signal} (신뢰도: {confidence}%)"
                else:
                    error = result.get('error', 'unknown') if isinstance(result, dict) else 'unknown'
                    return f"분석 실패: {error}"
            elif task_name == "final_decision":
                if isinstance(result, dict) and result.get('success'):
                    decision_result = result.get('result', {})
                    action = decision_result.get('final_decision', 'N/A')
                    confidence = decision_result.get('decision_confidence', 0)
                    return f"{action} (신뢰도: {confidence}%)"
                else:
                    error = result.get('error', 'unknown') if isinstance(result, dict) else 'unknown'
                    return f"결정 실패: {error}"
            else:
                return "완료"
        except Exception:
            return "요약 실패"
    
    def get_data(self, task_name: str) -> any:
        """데이터 요청 - 캐시 우선, 메모리 백업"""
        if task_name not in self.tasks:
            logger.error(f"등록되지 않은 작업: {task_name}")
            return None
        
        task = self.tasks[task_name]
        
        if task.error_count >= task.max_errors:
            logger.warning(f"비활성화된 작업: {task_name}")
            return None
        
        # 🔧 핵심 수정: 캐시 우선, 메모리 백업
        # 1. MongoDB 캐시에서 먼저 조회
        cached_data = self.get_cached_data(task_name)
        if cached_data is not None:
            logger.debug(f"MongoDB 캐시 데이터 사용: {task_name}")
            return cached_data
        
        # 2. 캐시에 없으면 메모리에서 조회
        if task.last_result is not None:
            logger.debug(f"메모리 데이터 사용: {task_name}")
            return task.last_result
        
        # 3. 둘 다 없으면 None
        logger.warning(f"사용 가능한 데이터 없음: {task_name}")
        return None
    
    async def get_all_analysis_for_decision(self) -> Dict:
        """최종 결정용 모든 분석 결과 반환 - 포지션 조건부 처리 추가"""
        try:
            logger.info("🔍 DEBUG: get_all_analysis_for_decision 시작")
            results = {}
            
            # AI 분석 결과 매핑
            ai_mapping = {
                'ai_technical_analysis': 'technical_analysis',
                'ai_sentiment_analysis': 'sentiment_analysis',
                'ai_macro_analysis': 'macro_analysis',
                'ai_onchain_analysis': 'onchain_analysis',
                'ai_institutional_analysis': 'institutional_analysis'
            }
            
            # 🔍 디버깅: AI 분석 결과 수집
            for ai_task, result_key in ai_mapping.items():
                try:
                    logger.info(f"🔍 DEBUG: {ai_task} 데이터 조회 중...")
                    data = self.get_data(ai_task)
                    
                    logger.info(f"🔍 DEBUG: {ai_task} 결과 타입: {type(data)}")
                    logger.info(f"🔍 DEBUG: {ai_task} 결과가 None: {data is None}")
                    
                    if data:
                        if isinstance(data, dict):
                            logger.info(f"🔍 DEBUG: {ai_task} 결과 키들: {list(data.keys())}")
                            if 'success' in data:
                                logger.info(f"🔍 DEBUG: {ai_task} success: {data.get('success')}")
                        results[result_key] = data
                        logger.info(f"🔍 DEBUG: {result_key} 설정 완료")
                    else:
                        logger.warning(f"🔍 DEBUG: {ai_task} 결과 없음")
                        results[result_key] = {
                            'success': False,
                            'error': f'{ai_task} 결과 없음',
                            'skip_reason': 'no_result'
                        }
                except Exception as e:
                    logger.error(f"🔍 DEBUG: {ai_task} 조회 실패: {e}")
                    results[result_key] = {'success': False, 'error': str(e)}
            
            # 🔧 현재 포지션 정보 먼저 수집 및 확인
            logger.info("🔍 DEBUG: 현재 포지션 정보 수집 시작")
            position_data = self.get_data('position_data')
            
            logger.info(f"🔍 DEBUG: position_data 타입: {type(position_data)}")
            logger.info(f"🔍 DEBUG: position_data가 None: {position_data is None}")
            
            if position_data:
                if isinstance(position_data, dict):
                    logger.info(f"🔍 DEBUG: position_data 키들: {list(position_data.keys())}")
                current_position = self._extract_position_info(position_data)
                results['current_position'] = current_position
                has_position = current_position.get('has_position', False)
                logger.info(f"🔍 DEBUG: 포지션 데이터 추출 완료 - has_position: {has_position}")
            else:
                logger.warning("🔍 DEBUG: position_data가 None - 기본값 사용")
                current_position = {
                    'has_position': False,
                    'side': 'none',
                    'size': 0,
                    'entry_price': 0
                }
                results['current_position'] = current_position
                has_position = False
            
            # 🔧 포지션 분석 (포지션 유무에 따라 조건부 실행)
            logger.info("🔍 DEBUG: 포지션 분석 시작")
            try:
                logger.info(f"🔍 DEBUG: 포지션 상태 - has_position: {has_position}")
                
                if has_position:
                    # 포지션이 있을 때만 실제 분석 실행
                    logger.info("🔍 DEBUG: 포지션 있음 - 실제 position_analysis 실행")
                    from docs.investment_ai.analyzers.position_analyzer import analyze_position_status
                    
                    # analyze_position_status 함수 호출 - 비동기 함수 처리
                    import inspect
                    if inspect.iscoroutinefunction(analyze_position_status):
                        logger.info("🔍 DEBUG: position_analyzer가 비동기 함수임 - await로 호출")
                        # 비동기 함수를 await로 호출 (동기 함수에서 안전하게 처리)
                        try:
                            # asyncio.run을 사용해서 비동기 함수 실행
                            import asyncio
                            if asyncio.get_running_loop():
                                # 이미 실행 중인 루프가 있으면 새 태스크로 실행
                                position_analysis = await analyze_position_status()
                            else:
                                # 실행 중인 루프가 없으면 새로 만들어서 실행
                                position_analysis = asyncio.run(analyze_position_status())
                        except RuntimeError:
                            # 실행 중인 루프에서 새 루프를 만들 수 없는 경우 기본값
                            logger.warning("🔍 DEBUG: 실행 중인 루프에서 position_analyzer 호출 불가 - 기본값 사용")
                            position_analysis = {
                                'success': True,
                                'result': {
                                    'recommended_action': 'Wait',
                                    'position_status': 'Running Loop Conflict',
                                    'risk_level': 'None',
                                    'confidence': 50
                                },
                                'note': 'Event loop conflict - using default'
                            }
                    else:
                        position_analysis = analyze_position_status()
                        
                        logger.info(f"🔍 DEBUG: 실제 포지션 분석 결과 타입: {type(position_analysis)}")
                        logger.info(f"🔍 DEBUG: 실제 포지션 분석 결과가 None: {position_analysis is None}")
                        
                        if position_analysis and isinstance(position_analysis, dict):
                            logger.info(f"🔍 DEBUG: 실제 포지션 분석 키들: {list(position_analysis.keys())}")
                            if 'success' in position_analysis:
                                logger.info(f"🔍 DEBUG: 실제 포지션 분석 success: {position_analysis.get('success')}")
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
                            'analysis_summary': '현재 포지션이 없어 대기 상태 권장',
                            'position_health': 'N/A - No Position'
                        },
                        'analysis_type': 'position_analysis',
                        'note': 'No position - default analysis'
                    }
                
                if position_analysis and position_analysis.get('success', False):
                    results['position_analysis'] = position_analysis
                    logger.info("🔍 DEBUG: 포지션 분석 성공")
                else:
                    logger.warning("🔍 DEBUG: 포지션 분석 실패")
                    error_msg = position_analysis.get('error', '포지션 분석 실패') if isinstance(position_analysis, dict) else '포지션 분석 실패'
                    results['position_analysis'] = {
                        'success': False, 
                        'error': error_msg,
                        'skip_reason': position_analysis.get('skip_reason', 'analysis_failed') if isinstance(position_analysis, dict) else 'analysis_failed'
                    }
                    
            except Exception as e:
                logger.error(f"🔍 DEBUG: 포지션 분석 중 오류: {e}")
                results['position_analysis'] = {
                    'success': False,
                    'error': f'포지션 분석 오류: {str(e)}',
                    'skip_reason': 'position_analysis_error'
                }
            
            # 🔍 디버깅: 최종 결과 요약
            logger.info(f"🔍 DEBUG: 최종 결과 키들: {list(results.keys())}")
            for key, value in results.items():
                if isinstance(value, dict) and 'success' in value:
                    logger.info(f"🔍 DEBUG: {key} success: {value.get('success')}")
                
            return results
            
        except Exception as e:
            logger.error(f"🔍 DEBUG: get_all_analysis_for_decision 전체 오류: {e}")
            return {}

    def _extract_position_info(self, position_data) -> Dict:
        """포지션 데이터에서 현재 포지션 정보 추출 - 안전성 강화"""
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
            
            # 🔧 수정: position_data가 None이거나 잘못된 형태 체크
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
                    
                    if abs(size) > 0:
                        # side 필드를 직접 사용해야 함
                        api_side = pos.get('side', '')
                        position_info.update({
                            'has_position': True,
                            'side': 'long' if api_side == 'Buy' else 'short',
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
    
    def get_status(self) -> Dict:
        """스케줄러 상태 반환 - MongoDB 캐시 정보 포함"""
        status = {
            'global_cycle_count': self.global_cycle_count,
            'next_cycle_in_minutes': self.main_cycle_minutes,
            'execution_stages': self.execution_stages,
            'tasks_by_stage': {},
            'tasks': {},
            'mongodb_connected': self.cache_collection is not None
        }
        
        # 단계별 작업 정리
        for stage in self.execution_stages:
            stage_tasks = []
            for task_name, task in self.tasks.items():
                if task.stage == stage:
                    stage_tasks.append(task_name)
            status['tasks_by_stage'][stage] = stage_tasks
        
        # 개별 작업 상태 - MongoDB 캐시 상태 포함
        for task_name, task in self.tasks.items():
            next_run_cycle = (
                (task.interval_cycles - (self.global_cycle_count % task.interval_cycles)) 
                % task.interval_cycles
            )
            
            should_run, reason = self.should_run_task(task)
            
            # MongoDB 캐시 상태 확인
            has_cache = False
            cache_age_minutes = 0
            
            if self.cache_collection is not None:
                try:
                    cache_doc = self.cache_collection.find_one({"task_name": task_name})
                    if cache_doc:
                        has_cache = True
                        if cache_doc.get("created_at"):
                            created_at = cache_doc["created_at"]
                            
                            # timezone 정보 확인 및 변환
                            if created_at.tzinfo is None:
                                # timezone-naive인 경우 UTC로 가정
                                created_at = created_at.replace(tzinfo=timezone.utc)
                            
                            cache_age = datetime.now(timezone.utc) - created_at
                            cache_age_minutes = cache_age.total_seconds() / 60
                except Exception as e:
                    logger.error(f"캐시 상태 확인 오류: {e}")
            
            status['tasks'][task_name] = {
                'stage': task.stage,
                'interval_cycles': task.interval_cycles,
                'interval_minutes': task.interval_cycles * self.main_cycle_minutes,
                'cache_duration_minutes': task.cache_duration_minutes,
                'has_result': task.last_result is not None,
                'has_cache': has_cache,
                'cache_age_minutes': round(cache_age_minutes, 1),
                'error_count': task.error_count,
                'is_disabled': task.error_count >= task.max_errors,
                'is_running': task.is_running,
                'next_run_in_cycles': next_run_cycle,
                'next_run_in_minutes': next_run_cycle * self.main_cycle_minutes,
                'dependencies': task.dependencies,
                'current_status': reason,
                'ready_to_run': should_run
            }
        
        return status
    
    def get_final_decision_result(self) -> Dict:
        """최종 결정 결과 반환 - 캐시 우선"""
        final_task = self.tasks.get('final_decision')
        if final_task:
            # 캐시에서 먼저 조회
            cached_result = self.get_cached_data('final_decision')
            if cached_result:
                return cached_result
            
            # 캐시에 없으면 메모리에서 조회
            if final_task.last_result:
                return final_task.last_result
        
        return {
            'success': False,
            'error': '최종 결정 결과 없음',
            'result': {
                'final_decision': 'Hold',
                'decision_confidence': 0,
                'needs_human_review': True,
                'human_review_reason': '최종 결정 미완료'
            }
        }
    
    def reset_errors(self, task_name: str = None):
        """에러 카운트 리셋"""
        if task_name:
            if task_name in self.tasks:
                old_count = self.tasks[task_name].error_count
                self.tasks[task_name].error_count = 0
                logger.info(f"에러 리셋: {task_name} ({old_count} → 0)")
        else:
            reset_count = 0
            for task in self.tasks.values():
                if task.error_count > 0:
                    task.error_count = 0
                    reset_count += 1
            logger.info(f"모든 작업 에러 리셋: {reset_count}개")
    
    def clear_cache(self, task_name: str = None):
        """MongoDB 캐시 삭제"""
        if self.cache_collection is None:
            logger.warning("MongoDB 연결되지 않음 - 캐시 삭제 불가")
            return False
        
        try:
            if task_name:
                # 특정 작업 캐시 삭제
                result = self.cache_collection.delete_many({"task_name": task_name})
                logger.info(f"캐시 삭제: {task_name} ({result.deleted_count}개 문서)")
                return result.deleted_count > 0
            else:
                # 모든 캐시 삭제
                result = self.cache_collection.delete_many({})
                logger.info(f"모든 캐시 삭제: {result.deleted_count}개 문서")
                return result.deleted_count > 0
        except Exception as e:
            logger.error(f"캐시 삭제 오류: {e}")
            return False
    
    def get_cache_info(self) -> Dict:
        """MongoDB 캐시 상태 정보"""
        if self.cache_collection is None:
            return {'error': 'MongoDB 연결되지 않음'}
        
        try:
            # 전체 캐시 문서 수
            total_count = self.cache_collection.count_documents({})
            
            # 만료된 캐시 수 (수동 계산)
            expired_count = self.cache_collection.count_documents({
                "expire_at": {"$lt": datetime.now(timezone.utc)}
            })
            
            # 작업별 캐시 상태
            task_cache_info = {}
            for task_name in self.tasks.keys():
                task_docs = self.cache_collection.count_documents({"task_name": task_name})
                active_docs = self.cache_collection.count_documents({
                    "task_name": task_name,
                    "expire_at": {"$gt": datetime.now(timezone.utc)}
                })
                
                task_cache_info[task_name] = {
                    'total_docs': task_docs,
                    'active_docs': active_docs,
                    'expired_docs': task_docs - active_docs
                }
            
            return {
                'total_documents': total_count,
                'expired_documents': expired_count,
                'active_documents': total_count - expired_count,
                'task_cache_info': task_cache_info,
                'mongodb_connected': True
            }
        except Exception as e:
            logger.error(f"캐시 정보 조회 오류: {e}")
            return {'error': str(e)}
    
    # ========== 작업 함수들 (분석기 호출만) ==========
    
    async def _get_position_data(self):
        """포지션 데이터 수집"""
        try:
            from docs.get_current import fetch_investment_status
            balance, positions_json, ledger = fetch_investment_status()
            
            if balance == 'error':
                return None
            
            return {
                'balance': balance,
                'positions': positions_json,
                'ledger': ledger[:10] if ledger else [],
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error(f"포지션 데이터 수집 오류: {e}")
            return None
    
    async def _update_chart_data(self):
        """차트 데이터 업데이트 - 초기/평상시 구분"""
        try:
            # 🔧 초기 실행 여부 확인 (사이클 1이거나 캐시된 데이터가 없으면 초기)
            is_initial_run = (self.global_cycle_count <= 1) or (self.get_cached_data("chart_update") is None)
            
            if is_initial_run:
                # 초기 실행: 전체 차트 데이터 수집
                logger.info("🔄 초기 차트 데이터 전체 수집 시작")
                from docs.get_chart import chart_update
                result = chart_update('60m', 'BTCUSDT')  # 15m → 60m으로 변경
                
                return {
                    'success': result is not None,
                    'mode': 'full_update',
                    'message': '전체 차트 데이터 수집 완료',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            else:
                # 평상시: 최신 60분봉만 업데이트
                logger.info("🔄 차트 데이터 최신봉 업데이트")
                from docs.get_chart import chart_update_one
                result, server_time, execution_time = chart_update_one('60m', 'BTCUSDT')  # 15m → 60m으로 변경
                
                return {
                    'success': result is not None,
                    'mode': 'incremental_update',
                    'server_time': server_time,
                    'execution_time': execution_time,
                    'message': '최신 차트 데이터 업데이트 완료',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
                
        except Exception as e:
            logger.error(f"차트 데이터 업데이트 오류: {e}")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
    
    # AI 분석 함수들 (분석기 직접 호출)
    async def _ai_technical_analysis(self):
        """기술적 분석"""
        try:
            from docs.investment_ai.analyzers.technical_analyzer import analyze_technical_indicators
            return await analyze_technical_indicators('BTCUSDT', '60m', 300)  # 15m → 60m으로 변경
        except Exception as e:
            logger.error(f"기술적 분석 오류: {e}")
            return None
    
    async def _ai_sentiment_analysis(self):
        """감정 분석"""
        try:
            from docs.investment_ai.analyzers.sentiment_analyzer import analyze_market_sentiment
            return await analyze_market_sentiment()
        except Exception as e:
            logger.error(f"감정 분석 오류: {e}")
            return None
    
    async def _ai_macro_analysis(self):
        """거시경제 분석"""
        try:
            from docs.investment_ai.analyzers.macro_analyzer import analyze_macro_economics
            return await analyze_macro_economics()
        except Exception as e:
            logger.error(f"거시경제 분석 오류: {e}")
            return None
    
    async def _ai_onchain_analysis(self):
        """온체인 분석"""
        try:
            from docs.investment_ai.analyzers.onchain_analyzer import analyze_onchain_data
            return await analyze_onchain_data()
        except Exception as e:
            logger.error(f"온체인 분석 오류: {e}")
            return None
    
    async def _ai_institutional_analysis(self):
        """기관투자 분석"""
        try:
            from docs.investment_ai.analyzers.institution_analyzer import analyze_institutional_flow
            return await analyze_institutional_flow()
        except Exception as e:
            logger.error(f"기관투자 분석 오류: {e}")
            return None
    
    async def _final_decision(self):
        """최종 결정 - 코루틴 에러 수정"""
        try:
            # 🔧 수정: 동기적으로 분석 결과 수집
            all_analysis_results = await self.get_all_analysis_for_decision()
            
            if not all_analysis_results:
                logger.warning("분석 결과가 없어 최종 결정 불가")
                return {
                    'success': False,
                    'error': '분석 결과 없음',
                    'result': {
                        'final_decision': 'Hold',
                        'decision_confidence': 0,
                        'needs_human_review': True,
                        'human_review_reason': '분석 결과 없음'
                    }
                }
            
            # 성공한 분석 개수 확인
            success_count = sum(1 for result in all_analysis_results.values() 
                              if isinstance(result, dict) and result.get('success', False))
            total_count = len([k for k in all_analysis_results.keys() if k != 'current_position'])
            
            logger.info(f"분석 결과 수집 완료: {success_count}/{total_count} 성공")
            
            # 최종 결정 실행
            from docs.investment_ai.final_decisionmaker import make_final_investment_decision
            return await make_final_investment_decision(all_analysis_results)
        except Exception as e:
            logger.error(f"최종 결정 오류: {e}")
            return {
                'success': False,
                'error': str(e),
                'result': {
                    'final_decision': 'Hold',
                    'decision_confidence': 0,
                    'needs_human_review': True,
                    'human_review_reason': f'최종 결정 오류: {str(e)}'
                }
            }

# 전역 인스턴스
_serial_scheduler: Optional[SerialDataScheduler] = None

def get_serial_scheduler() -> SerialDataScheduler:
    """직렬 스케줄러 인스턴스 반환"""
    global _serial_scheduler
    if _serial_scheduler is None:
        _serial_scheduler = SerialDataScheduler()
    return _serial_scheduler

# 편의 함수들
async def run_serial_cycle(force_all_analysis=False):
    """직렬 사이클 실행 - 강제 모든 분석 옵션 추가"""
    scheduler = get_serial_scheduler()
    return await scheduler.run_cycle(force_all_analysis=force_all_analysis)

def get_serial_data(task_name: str):
    """직렬 스케줄러에서 데이터 요청"""
    scheduler = get_serial_scheduler()
    return scheduler.get_data(task_name)

def get_serial_status():
    """직렬 스케줄러 상태"""
    scheduler = get_serial_scheduler()
    return scheduler.get_status()

def get_final_decision():
    """최종 결정 결과"""
    scheduler = get_serial_scheduler()
    return scheduler.get_final_decision_result()

def clear_serial_cache(task_name: str = None):
    """직렬 스케줄러 캐시 삭제"""
    scheduler = get_serial_scheduler()
    return scheduler.clear_cache(task_name)

def get_cache_status():
    """캐시 상태 정보"""
    scheduler = get_serial_scheduler()
    return scheduler.get_cache_info()

def reset_serial_errors(task_name: str = None):
    """직렬 스케줄러 에러 리셋"""
    scheduler = get_serial_scheduler()
    scheduler.reset_errors(task_name)