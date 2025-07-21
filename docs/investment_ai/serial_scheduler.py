# 직렬 카운팅 기반 스케줄러 (분석기 호출만)

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass

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

class SerialDataScheduler:
    """직렬 카운팅 기반 스케줄러 - 분석기 호출 전용"""
    
    def __init__(self, main_cycle_minutes: int = 15):
        self.main_cycle_minutes = main_cycle_minutes
        self.tasks: Dict[str, SerialTask] = {}
        self.global_cycle_count = 0
        
        # 실행 단계 순서 정의 (데이터 의존성에 따라)
        self.execution_stages = [
            'position',      # 1단계: 포지션 데이터 (실시간)
            'analysis',      # 2단계: 차트 외 분석들 (각자 데이터 수집 포함)
            'chart',         # 3단계: 15분 캔들 차트 업데이트
            'technical',     # 4단계: 기술적 분석 (차트 데이터 의존)
            'final'          # 5단계: 최종 결정
        ]
        
        # 작업들 등록
        self._register_tasks()
        
        logger.info(f"직렬 스케줄러 초기화 완료 (메인 사이클: {main_cycle_minutes}분)")
    
    def _register_tasks(self):
        """작업들 등록 - 분석기 함수 호출만"""
        
        # 1단계: 포지션 데이터 (매번 실행)
        self.register_task("position_data", self._get_position_data, 1, "position")
        
        # 2단계: 차트 외 AI 분석들 (각 분석기가 데이터 수집 포함)
        self.register_task("ai_sentiment_analysis", self._ai_sentiment_analysis, 2, "analysis")  # 30분마다
        self.register_task("ai_macro_analysis", self._ai_macro_analysis, 24, "analysis")  # 6시간마다
        self.register_task("ai_onchain_analysis", self._ai_onchain_analysis, 4, "analysis")  # 1시간마다
        self.register_task("ai_institutional_analysis", self._ai_institutional_analysis, 8, "analysis")  # 2시간마다
        
        # 3단계: 차트 데이터 업데이트 (매번 실행)
        self.register_task("chart_update", self._update_chart_data, 1, "chart")
        
        # 4단계: 기술적 분석 (차트 데이터 의존)
        self.register_task("ai_technical_analysis", self._ai_technical_analysis, 1, "technical",
                          dependencies=["chart_update"])
        
        # 5단계: 최종 결정 (모든 분석 의존)
        self.register_task("final_decision", self._final_decision, 1, "final",
                          dependencies=["ai_technical_analysis", "ai_sentiment_analysis", 
                                      "ai_macro_analysis", "ai_onchain_analysis", 
                                      "ai_institutional_analysis", "position_data"])
        
        logger.info(f"작업 등록 완료: {len(self.tasks)}개")
        
        # 단계별 작업 수 로깅
        for stage in self.execution_stages:
            stage_tasks = [name for name, task in self.tasks.items() if task.stage == stage]
            logger.info(f"  {stage}: {len(stage_tasks)}개 작업")
    
    def register_task(self, name: str, func: callable, interval_cycles: int, stage: str, dependencies: List[str] = None):
        """작업 등록"""
        self.tasks[name] = SerialTask(
            name=name,
            func=func,
            interval_cycles=interval_cycles,
            stage=stage,
            dependencies=dependencies or []
        )
        interval_minutes = interval_cycles * self.main_cycle_minutes
        logger.debug(f"작업 등록: {name} [{stage}] (주기: {interval_minutes}분)")
    
    def should_run_task(self, task: SerialTask) -> Tuple[bool, str]:
        """작업 실행 여부 판단 - 카운팅 + 의존성 체크"""
        if task.is_running:
            return False, "already_running"
        
        if task.error_count >= task.max_errors:
            return False, f"disabled({task.error_count} errors)"
        
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
    
    async def run_task(self, task: SerialTask, stage_name: str, task_index: int, total_tasks: int) -> bool:
        """개별 작업 실행"""
        try:
            task.is_running = True
            logger.info(f"  {stage_name}-{task_index}: {task.name} 실행 중...")
            
            start_time = datetime.now()
            result = await asyncio.wait_for(task.func(), timeout=180)
            duration = (datetime.now() - start_time).total_seconds()
            
            if result is not None:
                task.last_result = result
                task.error_count = 0  # 성공 시 에러 카운트 리셋
                
                # 결과 요약 로깅
                result_summary = self._get_result_summary(task.name, result)
                logger.info(f"    ✅ {task.name} 성공 ({duration:.1f}초) - {result_summary}")
                return True
            else:
                task.error_count += 1
                logger.warning(f"    ❌ {task.name} 실패 (결과 없음)")
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
        """한 사이클 직렬 실행 - 강제 모든 분석 옵션 추가"""
        self.global_cycle_count += 1
        cycle_start = datetime.now()
        
        logger.info(f"=== 직렬 사이클 #{self.global_cycle_count} 시작 ===")
        if force_all_analysis:
            logger.info("🔥 강제 모든 분석 모드 활성화")
        
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
                    # 🔧 수정: force_all_analysis가 True면 모든 분석 실행
                    if force_all_analysis and task_name.startswith('ai_'):
                        should_run = True
                        reason = "forced_execution"
                    else:
                        should_run, reason = self.should_run_task(task)
                    
                    if should_run:
                        stage_tasks.append((task_name, task))
                    else:
                        skipped_tasks.append((task_name, reason))
            
            if not stage_tasks and not skipped_tasks:
                continue  # 해당 단계에 작업이 없음
            
            logger.info(f"{stage_idx}단계: {stage} ({len(stage_tasks)}개 실행, {len(skipped_tasks)}개 스킵)")
            
            # 스킵된 작업들 로깅 (force_all_analysis 모드에서는 더 자세히)
            if force_all_analysis and skipped_tasks:
                for task_name, reason in skipped_tasks:
                    if task_name.startswith('ai_'):
                        logger.warning(f"  AI 분석 스킵됨: {task_name} ({reason}) - 강제 모드에서도 스킵")
                    else:
                        logger.debug(f"  스킵: {task_name} ({reason})")
            else:
                for task_name, reason in skipped_tasks:
                    logger.debug(f"  스킵: {task_name} ({reason})")
            
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
        logger.info(f"전체 성공률: {total_tasks_success}/{total_tasks_run}")
        
        return {
            'success': True,
            'cycle_count': self.global_cycle_count,
            'tasks_run': total_tasks_run,
            'tasks_success': total_tasks_success,
            'duration_seconds': cycle_duration,
            'stage_results': stage_results,
            'forced_all_analysis': force_all_analysis
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
    
    async def run_cycle(self) -> Dict:
        """한 사이클 직렬 실행"""
        self.global_cycle_count += 1
        cycle_start = datetime.now()
        
        logger.info(f"=== 직렬 사이클 #{self.global_cycle_count} 시작 ===")
        
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
                    should_run, reason = self.should_run_task(task)
                    if should_run:
                        stage_tasks.append((task_name, task))
                    else:
                        skipped_tasks.append((task_name, reason))
            
            if not stage_tasks and not skipped_tasks:
                continue  # 해당 단계에 작업이 없음
            
            logger.info(f"{stage_idx}단계: {stage} ({len(stage_tasks)}개 실행, {len(skipped_tasks)}개 스킵)")
            
            # 스킵된 작업들 로깅
            for task_name, reason in skipped_tasks:
                logger.debug(f"  스킵: {task_name} ({reason})")
            
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
        logger.info(f"전체 성공률: {total_tasks_success}/{total_tasks_run}")
        
        return {
            'success': True,
            'cycle_count': self.global_cycle_count,
            'tasks_run': total_tasks_run,
            'tasks_success': total_tasks_success,
            'duration_seconds': cycle_duration,
            'stage_results': stage_results
        }
    
    def get_data(self, task_name: str) -> any:
        """데이터 요청 - 단순히 마지막 결과 반환"""
        if task_name not in self.tasks:
            logger.error(f"등록되지 않은 작업: {task_name}")
            return None
        
        task = self.tasks[task_name]
        
        if task.error_count >= task.max_errors:
            logger.warning(f"비활성화된 작업: {task_name}")
            return None
        
        return task.last_result
    
    def get_all_analysis_for_decision(self) -> Dict:
        """최종 결정용 모든 분석 결과 반환"""
        results = {}
        
        # AI 분석 결과 매핑
        ai_mapping = {
            'ai_technical_analysis': 'technical_analysis',
            'ai_sentiment_analysis': 'sentiment_analysis',
            'ai_macro_analysis': 'macro_analysis',
            'ai_onchain_analysis': 'onchain_analysis',
            'ai_institutional_analysis': 'institutional_analysis'
        }
        
        for ai_task, result_key in ai_mapping.items():
            data = self.get_data(ai_task)
            if data:
                results[result_key] = data
            else:
                results[result_key] = {
                    'success': False,
                    'error': f'{ai_task} 결과 없음',
                    'skip_reason': 'no_result'
                }
        
        # 포지션 분석 (실시간)
        try:
            from docs.investment_ai.analyzers.position_analyzer import analyze_position_status
            position_analysis = analyze_position_status()
            results['position_analysis'] = position_analysis if position_analysis else {
                'success': False, 'error': '포지션 분석 실패'
            }
        except Exception as e:
            results['position_analysis'] = {
                'success': False, 'error': str(e)
            }
        
        # 현재 포지션 정보
        position_data = self.get_data('position_data')
        if position_data:
            results['current_position'] = self._extract_position_info(position_data)
        else:
            results['current_position'] = {
                'has_position': False,
                'side': 'none',
                'size': 0,
                'entry_price': 0
            }
        
        return results
    
    def _extract_position_info(self, position_data) -> Dict:
        """포지션 데이터에서 현재 포지션 정보 추출"""
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
            
            # 잔고 정보
            balance = position_data.get('balance', {})
            if isinstance(balance, dict) and 'USDT' in balance:
                usdt_balance = balance['USDT']
                position_info.update({
                    'total_equity': float(usdt_balance.get('total', 0)),
                    'available_balance': float(usdt_balance.get('free', 0))
                })
            
            # positions에서 BTC 포지션 찾기
            positions = position_data.get('positions', [])
            if isinstance(positions, str):
                import json
                positions = json.loads(positions)
            
            for pos in positions:
                if 'BTC' in pos.get('symbol', ''):
                    size = float(pos.get('size', pos.get('contracts', 0)))
                    if abs(size) > 0:
                        position_info.update({
                            'has_position': True,
                            'side': 'long' if size > 0 else 'short',
                            'size': abs(size),
                            'entry_price': float(pos.get('avgPrice', pos.get('entryPrice', 0))),
                            'unrealized_pnl': float(pos.get('unrealizedPnl', 0))
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
        """스케줄러 상태 반환"""
        status = {
            'global_cycle_count': self.global_cycle_count,
            'next_cycle_in_minutes': self.main_cycle_minutes,
            'execution_stages': self.execution_stages,
            'tasks_by_stage': {},
            'tasks': {}
        }
        
        # 단계별 작업 정리
        for stage in self.execution_stages:
            stage_tasks = []
            for task_name, task in self.tasks.items():
                if task.stage == stage:
                    stage_tasks.append(task_name)
            status['tasks_by_stage'][stage] = stage_tasks
        
        # 개별 작업 상태
        for task_name, task in self.tasks.items():
            next_run_cycle = (
                (task.interval_cycles - (self.global_cycle_count % task.interval_cycles)) 
                % task.interval_cycles
            )
            
            should_run, reason = self.should_run_task(task)
            
            status['tasks'][task_name] = {
                'stage': task.stage,
                'interval_cycles': task.interval_cycles,
                'interval_minutes': task.interval_cycles * self.main_cycle_minutes,
                'has_result': task.last_result is not None,
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
        """최종 결정 결과 반환"""
        final_task = self.tasks.get('final_decision')
        if final_task and final_task.last_result:
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
        """차트 데이터 업데이트 (15분 캔들)"""
        try:
            from docs.get_chart import chart_update_one
            result, server_time, execution_time = chart_update_one('15m', 'BTCUSDT')
            return result is not None
        except Exception as e:
            logger.error(f"차트 데이터 업데이트 오류: {e}")
            return None
    
    # AI 분석 함수들 (분석기 직접 호출)
    async def _ai_technical_analysis(self):
        """기술적 분석"""
        try:
            from docs.investment_ai.analyzers.technical_analyzer import analyze_technical_indicators
            return await analyze_technical_indicators('BTCUSDT', '15m', 300)
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
        """최종 결정"""
        try:
            # 모든 분석 결과 수집
            all_analysis_results = self.get_all_analysis_for_decision()
            
            # 최종 결정 실행
            from docs.investment_ai.final_decisionmaker import make_final_investment_decision
            return await make_final_investment_decision(all_analysis_results)
        except Exception as e:
            logger.error(f"최종 결정 오류: {e}")
            return None

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