import asyncio
import json
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone

# AI 분석 모듈들 import
from docs.investment_ai.analyzers.position_analyzer import analyze_position_status
from docs.investment_ai.analyzers.sentiment_analyzer import analyze_market_sentiment
from docs.investment_ai.analyzers.technical_analyzer import analyze_technical_indicators
from docs.investment_ai.analyzers.macro_analyzer import analyze_macro_economics
from docs.investment_ai.analyzers.onchain_analyzer import analyze_onchain_data
from docs.investment_ai.analyzers.institution_analyzer import analyze_institutional_flow
from docs.investment_ai.final_decisionmaker import make_final_investment_decision
# 🔧 누락: 이 import가 없음
from docs.investment_ai.data_scheduler import run_scheduled_data_collection
# 기존 시스템 모듈들 import
from docs.get_current import fetch_investment_status
from docs.current_price import get_current_price
from docs.making_order import close_position, get_position_amount

logger = logging.getLogger("ai_trading_integration")

class AITradingIntegration:
    """AI 투자 분석과 실제 거래 시스템을 통합하는 클래스"""
    
    def __init__(self, trading_config: Dict):
        self.config = trading_config
        self.symbol = trading_config.get('symbol', 'BTCUSDT')
        self.timeframe = trading_config.get('set_timevalue', '15m')
        
        # 결정 히스토리 추적
        self.decision_history = []
        self.max_history = 100


    # 🔧 완전히 새로운 메서드: 스케줄러 기반 분석 결과 조회
    async def get_analysis_results_from_scheduler(self) -> Dict:
        """스케줄러에서 분석 결과들을 가져와서 최종결정용 형식으로 변환"""
        try:
            logger.info("스케줄러에서 분석 결과 조회 시작")
            
            # 1. 데이터 수집과 AI 분석 실행 (await로 완료 대기)
            logger.info("데이터 수집 및 AI 분석 실행 중...")
            await run_scheduled_data_collection()
            logger.info("데이터 수집 및 AI 분석 완료")
            
            # 2. 스케줄러 인스턴스 가져오기
            from docs.investment_ai.data_scheduler import get_data_scheduler
            scheduler = get_data_scheduler()
            
            # 3. 최종 결정 메이커 인스턴스 가져오기
            from docs.investment_ai.final_decisionmaker import get_final_decision_maker
            decision_maker = get_final_decision_maker()
            
            # 4. 🔧 핵심: 스케줄러에서 데이터를 가져와서 매핑하는 새로운 메서드 사용
            mapped_results = decision_maker.get_analysis_data_from_scheduler(scheduler)
            
            if not mapped_results:
                logger.error("스케줄러에서 분석 결과 매핑 실패")
                return {
                    'error': '스케줄러 연동 실패 - 매핑된 결과 없음',
                    'current_position': await self.get_current_position_data()
                }
            
            # 5. 매핑 결과 검증 및 로깅
            success_count = sum(1 for result in mapped_results.values() 
                              if isinstance(result, dict) and result.get('success', False))
            total_count = len(mapped_results)
            
            logger.info(f"스케줄러 연동 분석 결과 매핑 완료: {success_count}/{total_count} 성공")
            
            # 실패한 분석들 상세 로깅
            failed_analyses = []
            for key, value in mapped_results.items():
                if isinstance(value, dict) and not value.get('success', False):
                    reason = value.get('skip_reason', value.get('error', 'unknown'))
                    failed_analyses.append(f"{key}({reason})")
            
            if failed_analyses:
                logger.warning(f"실패한 분석들: {', '.join(failed_analyses)}")
            
            return mapped_results
            
        except Exception as e:
            logger.error(f"스케줄러 기반 분석 결과 조회 중 오류: {e}")
            return {
                'error': str(e),
                'current_position': await self.get_current_position_data()
            }

    # 🔧 기존 run_all_analyses 메서드를 대체하는 새로운 메서드
    async def run_all_analyses_v2(self) -> Dict:
        """모든 AI 분석 결과 조회 - 스케줄러 연동 버전"""
        try:
            logger.info("AI 분석 결과 조회 시작 (스케줄러 연동 v2)")
            
            # 스케줄러에서 매핑된 분석 결과 가져오기
            analysis_results = await self.get_analysis_results_from_scheduler()
            
            if 'error' in analysis_results:
                logger.error(f"분석 결과 조회 실패: {analysis_results['error']}")
                return analysis_results
            
            # 현재 포지션 정보 별도 추가 (실시간 업데이트)
            current_position = await self.get_current_position_data()
            analysis_results['current_position'] = current_position
            
            # 성공 통계 계산
            total_analyses = len([k for k in analysis_results.keys() if k != 'current_position'])
            successful_analyses = sum(1 for k, v in analysis_results.items() 
                                    if k != 'current_position' and isinstance(v, dict) and v.get('success', False))
            
            logger.info(f"최종 분석 결과 준비 완료: {successful_analyses}/{total_analyses} 성공")
            
            return analysis_results
            
        except Exception as e:
            logger.error(f"AI 분석 결과 조회 중 오류 (v2): {e}")
            return {
                'error': str(e),
                'current_position': await self.get_current_position_data()
            }


    async def get_current_position_data(self) -> Dict:
        """현재 포지션 정보를 AI 분석용 형태로 변환"""
        try:
            balance, positions_json, ledger = fetch_investment_status()
            
            if balance == 'error':
                return {
                    'has_position': False,
                    'error': 'API 호출 오류'
                }
            
            current_position = {
                'has_position': False,
                'side': 'none',
                'size': 0,
                'entry_price': 0,
                'unrealized_pnl': 0,
                'total_equity': balance.get('USDT', {}).get('total', 0) if balance else 0,
                'available_balance': balance.get('USDT', {}).get('free', 0) if balance else 0,
                'recent_trades': [],
                'funding_info': {}
            }
            
            # 포지션이 있는 경우
            if positions_json and positions_json != '[]':
                positions = json.loads(positions_json)
                if positions:
                    position = positions[0]  # 첫 번째 포지션 (BTCUSDT)

                    # API 값 정규화
                    api_side = position['side']
                    if api_side in ['Buy', 'buy', 'Long', 'long']:
                        normalized_side = 'long'
                    elif api_side in ['Sell', 'sell', 'Short', 'short']:
                        normalized_side = 'short'
                    else:
                        normalized_side = 'none'

                    current_position.update({
                        'has_position': True,
                        'side': normalized_side,
                        'size': float(position.get('contracts', 0)),
                        'entry_price': float(position.get('entryPrice', 0)),
                        'unrealized_pnl': float(position.get('unrealizedPnl', 0)),
                        'leverage': float(position.get('leverage', 1)),
                        'mark_price': float(position.get('markPrice', 0))
                    })
            
            # 최근 거래 내역 (ledger 활용)
            if ledger:
                recent_trades = []
                for trade in ledger[-10:]:  # 최근 10개 거래
                    recent_trades.append({
                        'timestamp': trade.get('timestamp', ''),
                        'type': trade.get('type', ''),
                        'amount': trade.get('amount', 0),
                        'info': trade.get('info', '')
                    })
                current_position['recent_trades'] = recent_trades
            
            return current_position
            
        except Exception as e:
            logger.error(f"포지션 정보 수집 중 오류: {e}")
            return {
                'has_position': False,
                'error': str(e)
            }
    
    async def run_all_analyses(self) -> Dict:
        """모든 AI 분석 결과 조회 - 수정된 버전 (직렬 처리 대응)"""
        try:
            logger.info("AI 분석 결과 조회 시작 (직렬 처리 대응)")
            
            # 🔧 수정: 데이터 수집과 AI 분석 실행 (await로 완료 대기)
            logger.info("데이터 수집 및 AI 분석 실행 중...")
            await run_scheduled_data_collection()
            logger.info("데이터 수집 및 AI 분석 완료")
            
            # 현재 포지션 정보 수집 (실시간, 항상 최신)
            current_position = await self.get_current_position_data()
            
            # 포지션 분석은 실시간 데이터를 사용하므로 즉시 실행
            position_analysis = await analyze_position_status(current_position)
            
            # 🔧 수정: data_scheduler의 get_data 함수 직접 사용 (캐시 우선)
            from docs.investment_ai.data_scheduler import get_data_scheduler
            scheduler = get_data_scheduler()
            
            # 캐시된 AI 분석 결과들을 개별적으로 조회
            cached_analysis_results = {}
            cached_analysis_names = [
                'ai_sentiment_analysis',
                'ai_technical_analysis', 
                'ai_macro_analysis',
                'ai_onchain_analysis',
                'ai_institutional_analysis'
            ]
            
            # 🔧 수정: 각 분석 결과를 순차적으로 조회 (직렬 처리 완료 후)
            for analysis_name in cached_analysis_names:
                try:
                    # logger.debug(f"캐시 조회 중: {analysis_name}")
                    cached_result = await scheduler.get_data(analysis_name)
                    
                    if cached_result is not None:
                        # logger.debug(f"{analysis_name} 캐시된 결과 사용")
                        cached_analysis_results[analysis_name] = cached_result
                    else:
                        logger.warning(f"{analysis_name} 캐시된 결과 없음")
                        cached_analysis_results[analysis_name] = None
                        
                    # 캐시 조회 간 잠시 대기
                    await asyncio.sleep(0.5)
                        
                except Exception as e:
                    logger.error(f"{analysis_name} 캐시 조회 중 오류: {e}")
                    cached_analysis_results[analysis_name] = None
            
            # 결과 정리
            all_analysis_results = {
                'current_position': current_position,
                'position_analysis': position_analysis
            }
            
            # 🔧 수정: 캐시된 분석 결과 처리 로직
            analysis_name_mapping = {
                'ai_sentiment_analysis': 'sentiment_analysis',
                'ai_technical_analysis': 'technical_analysis', 
                'ai_macro_analysis': 'macro_analysis',
                'ai_onchain_analysis': 'onchain_analysis',
                'ai_institutional_analysis': 'institutional_analysis'
            }
            
            fresh_analysis_needed = []
            successful_analyses = 0
            
            for cache_name, result_name in analysis_name_mapping.items():
                cached_result = cached_analysis_results.get(cache_name)
                
                if cached_result is None:
                    logger.warning(f"{result_name} 캐시된 결과 없음")
                    fresh_analysis_needed.append(result_name)
                    all_analysis_results[result_name] = {
                        'success': False,
                        'error': '캐시된 분석 결과 없음',
                        'fallback_needed': True
                    }
                else:
                    # 캐시 결과 구조 확인 및 처리
                    if isinstance(cached_result, dict):
                        if 'analysis_result' in cached_result:
                            actual_result = cached_result['analysis_result']
                            
                            # 분석 성공 여부 확인
                            if actual_result.get('success', False):
                                all_analysis_results[result_name] = actual_result
                                successful_analyses += 1
                                logger.info(f"✅ {result_name} 캐시된 성공 결과 사용")
                            else:
                                # 실패한 캐시 결과 처리
                                skip_reason = actual_result.get('skip_reason', 'unknown')
                                all_analysis_results[result_name] = actual_result
                                logger.warning(f"❌ {result_name} 캐시된 실패 결과 (이유: {skip_reason})")
                        else:
                            # analysis_result 키가 없는 경우
                            all_analysis_results[result_name] = cached_result
                            successful_analyses += 1
                            # logger.debug(f"✅ {result_name} 캐시된 결과 직접 사용")
                    else:
                        # 캐시 결과가 딕셔너리가 아닌 경우
                        fresh_analysis_needed.append(result_name)
                        all_analysis_results[result_name] = {
                            'success': False,
                            'error': '잘못된 캐시 결과 형식',
                            'fallback_needed': True
                        }
            
            # 🔧 수정: fallback 실행하지 않음 (직렬 처리에서 이미 완료됨)
            if fresh_analysis_needed:
                logger.warning(f"캐시 미스된 분석들 (fallback 생략): {fresh_analysis_needed}")
                logger.info("직렬 처리에서 이미 실행되었으므로 fallback 생략")
            
            # 최종 통계
            total_analyses = len(analysis_name_mapping)
            cached_count = total_analyses - len(fresh_analysis_needed)
            
            logger.info(f"AI 분석 결과 조회 완료 - 성공: {successful_analyses}/{total_analyses}, 캐시 사용: {cached_count}개")
            
            return all_analysis_results
            
        except Exception as e:
            logger.error(f"AI 분석 결과 조회 중 오류: {e}")
            return {
                'error': str(e),
                'current_position': await self.get_current_position_data()
            }
    

    
    # 🔧 수정된 get_ai_decision 메서드
    async def get_ai_decision(self) -> Dict:
        """AI 기반 투자 결정 도출 - 스케줄러 연동 버전"""
        try:
            # 🔧 핵심 변경: 새로운 분석 결과 조회 방법 사용
            all_analysis_results = await self.run_all_analyses_v2()
            
            # 에러가 있으면 조기 반환
            if 'error' in all_analysis_results:
                return {
                    'success': False,
                    'error': all_analysis_results['error'],
                    'result': {
                        'final_decision': 'Hold',
                        'decision_confidence': 0,
                        'needs_human_review': True,
                        'human_review_reason': f'분석 결과 조회 실패: {all_analysis_results["error"]}'
                    }
                }
            
            # 🔧 핵심 변경: 스케줄러 연동 최종 결정 메서드 사용
            from docs.investment_ai.final_decisionmaker import get_final_decision_maker
            from docs.investment_ai.data_scheduler import get_data_scheduler
            
            decision_maker = get_final_decision_maker()
            scheduler = get_data_scheduler()
            
            # 새로운 스케줄러 연동 메서드 사용
            final_decision = await decision_maker.make_final_decision_with_scheduler(scheduler)
            
            # 결정 히스토리에 추가
            decision_record = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'analysis_results': all_analysis_results,
                'final_decision': final_decision,
                'symbol': self.symbol,
                'timeframe': self.timeframe,
                'method': 'scheduler_integration_v2'
            }
            
            self.decision_history.append(decision_record)
            
            # 히스토리 크기 제한
            if len(self.decision_history) > self.max_history:
                self.decision_history = self.decision_history[-self.max_history:]
            
            return final_decision
            
        except Exception as e:
            logger.error(f"AI 결정 도출 중 오류 (스케줄러 연동): {e}")
            return {
                'success': False,
                'error': str(e),
                'result': {
                    'final_decision': 'Hold',
                    'decision_confidence': 0,
                    'needs_human_review': True,
                    'human_review_reason': f'AI 시스템 오류: {str(e)}'
                }
            }


    # 🔧 추가: 디버깅용 스케줄러 상태 확인 메서드
    async def debug_scheduler_status(self) -> Dict:
        """스케줄러 상태 및 캐시된 데이터 확인 (디버깅용)"""
        try:
            from docs.investment_ai.data_scheduler import get_data_scheduler, get_data_status
            
            scheduler = get_data_scheduler()
            status = get_data_status()
            
            # 각 AI 분석의 캐시 상태 확인
            ai_cache_status = {}
            ai_analysis_tasks = [
                'ai_technical_analysis',
                'ai_sentiment_analysis', 
                'ai_macro_analysis',
                'ai_onchain_analysis',
                'ai_institutional_analysis'
            ]
            
            for task_name in ai_analysis_tasks:
                try:
                    cached_data = scheduler.get_cached_data(task_name)
                    if cached_data:
                        if 'analysis_result' in cached_data:
                            analysis_result = cached_data['analysis_result']
                            ai_cache_status[task_name] = {
                                'has_cache': True,
                                'success': analysis_result.get('success', False),
                                'skip_reason': analysis_result.get('skip_reason'),
                                'error': analysis_result.get('error'),
                                'cache_timestamp': cached_data.get('analysis_timestamp', 'unknown')
                            }
                        else:
                            ai_cache_status[task_name] = {
                                'has_cache': True,
                                'malformed': True,
                                'cache_keys': list(cached_data.keys()) if isinstance(cached_data, dict) else str(type(cached_data))
                            }
                    else:
                        ai_cache_status[task_name] = {
                            'has_cache': False
                        }
                except Exception as e:
                    ai_cache_status[task_name] = {
                        'has_cache': False,
                        'error': str(e)
                    }
            
            return {
                'scheduler_status': status,
                'ai_cache_status': ai_cache_status,
                'debug_timestamp': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"스케줄러 상태 확인 중 오류: {e}")
            return {
                'error': str(e),
                'debug_timestamp': datetime.now(timezone.utc).isoformat()
            }

    def interpret_ai_decision(self, ai_decision: Dict) -> Dict:
        """AI 결정을 거래 실행 가능한 형태로 해석"""
        try:
            if not ai_decision.get('success', False):
                return {
                    'action': 'wait',
                    'reason': 'AI 분석 실패',
                    'error': ai_decision.get('error', 'Unknown error')
                }
            
            result = ai_decision.get('result', {})
            final_decision = result.get('final_decision', 'Hold')
            confidence = result.get('decision_confidence', 0)
            recommended_action = result.get('recommended_action', {})
            
            # 신뢰도가 너무 낮으면 대기
            if confidence < 60:
                return {
                    'action': 'wait',
                    'reason': f'낮은 신뢰도 ({confidence}%)',
                    'ai_decision': final_decision,
                    'confidence': confidence
                }
            
            # 인간 검토가 필요한 경우
            if result.get('needs_human_review', False):
                return {
                    'action': 'wait',
                    'reason': f"인간 검토 필요: {result.get('human_review_reason', 'Unknown')}",
                    'ai_decision': final_decision,
                    'confidence': confidence
                }
            
            # 실행 가능한 액션으로 변환
            action_type = recommended_action.get('action_type', 'Wait')
            
            action_mapping = {
                'Open Long Position': 'open_long',
                'Open Short Position': 'open_short', 
                'Close Position': 'close_position',
                'Reverse to Long': 'reverse_to_long',
                'Reverse to Short': 'reverse_to_short',
                'Add to Long Position': 'add_long',
                'Add to Short Position': 'add_short',
                'Hold Current Position': 'hold',
                'Hold Long Position': 'hold',
                'Hold Short Position': 'hold',
                'Wait for Signal': 'wait',
                'Wait': 'wait'
            }
            
            action = action_mapping.get(action_type, 'wait')
            
            return {
                'action': action,
                'ai_decision': final_decision,
                'confidence': confidence,
                'position_size': recommended_action.get('position_size', 0),
                'leverage': recommended_action.get('leverage', 1),
                'entry_price': recommended_action.get('entry_price'),
                'stop_loss': recommended_action.get('mandatory_stop_loss'),
                'take_profit': recommended_action.get('mandatory_take_profit'),
                'reason': f'AI 결정: {final_decision} (신뢰도: {confidence}%)',
                'full_analysis': result
            }
            
        except Exception as e:
            logger.error(f"AI 결정 해석 중 오류: {e}")
            return {
                'action': 'wait',
                'reason': f'결정 해석 오류: {str(e)}',
                'error': str(e)
            }
    
    async def execute_ai_decision(self, interpreted_decision: Dict) -> Dict:
        """해석된 AI 결정을 실제 거래로 실행"""
        try:
            action = interpreted_decision['action']
            
            if action == 'wait' or action == 'hold':
                return {
                    'executed': False,
                    'action': action,
                    'reason': interpreted_decision.get('reason', 'No action needed')
                }
            
            # 현재 포지션 상태 확인
            current_amount, current_side, current_avgPrice, pnl = get_position_amount(self.symbol)
            has_position = current_amount is not None and current_amount > 0
            
            execution_result = {'executed': False, 'action': action}
            
            if action == 'close_position':
                if has_position:
                    close_result = close_position(self.symbol)
                    execution_result.update({
                        'executed': close_result is not None,
                        'close_result': close_result,
                        'reason': 'AI 결정에 따른 포지션 종료'
                    })
                else:
                    execution_result['reason'] = '종료할 포지션이 없음'
            
            elif action in ['open_long', 'open_short', 'reverse_to_long', 'reverse_to_short']:
                # 리버스 액션인 경우 먼저 기존 포지션 종료
                if action.startswith('reverse_') and has_position:
                    close_position(self.symbol)
                    await asyncio.sleep(1)  # 종료 처리 대기
                
                # 새 포지션 열기
                position_type = 'Long' if 'long' in action else 'Short'
                side = 'Buy' if position_type == 'Long' else 'Sell'
                
                # AI가 권장한 설정 사용 또는 기본값 사용
                usdt_amount = interpreted_decision.get('position_size', self.config.get('usdt_amount', 0.3)) / 100
                leverage = interpreted_decision.get('leverage', self.config.get('leverage', 5))
                stop_loss = interpreted_decision.get('stop_loss') or self.config.get('stop_loss', 400)
                take_profit = interpreted_decision.get('take_profit') or self.config.get('take_profit', 400)
                
                # 현재가 조회
                current_price = get_current_price(self.symbol)
                
                # 주문 실행
                from docs.making_order import create_order_with_tp_sl
                order_result = create_order_with_tp_sl(
                    symbol=self.symbol,
                    side=side,
                    usdt_amount=usdt_amount,
                    leverage=leverage,
                    current_price=current_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
                
                execution_result.update({
                    'executed': order_result is not None,
                    'order_result': order_result,
                    'position_type': position_type,
                    'side': side,
                    'usdt_amount': usdt_amount,
                    'leverage': leverage,
                    'current_price': current_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'reason': f'AI 결정에 따른 {position_type} 포지션 진입'
                })
            
            return execution_result
            
        except Exception as e:
            logger.error(f"AI 결정 실행 중 오류: {e}")
            return {
                'executed': False,
                'error': str(e),
                'reason': f'실행 중 오류 발생: {str(e)}'
            }
    
    # run_ai_trading_cycle은 기본적으로 동일하게 유지 (get_ai_decision만 수정됨)
    async def run_ai_trading_cycle(self) -> Dict:
        """완전한 AI 트레이딩 사이클 실행 - 스케줄러 연동 버전"""
        try:
            logger.info("AI 트레이딩 사이클 시작 (스케줄러 연동)")
            
            # 🔧 디버깅: 스케줄러 상태 먼저 확인
            debug_info = await self.debug_scheduler_status()
            # logger.debug(f"스케줄러 디버그 정보: AI 캐시 상태 = {len([k for k, v in debug_info.get('ai_cache_status', {}).items() if v.get('has_cache', False)])}개 캐시됨")
            
            # 1. AI 결정 도출 (이제 스케줄러 연동 버전 사용)
            ai_decision = await self.get_ai_decision()
            
            # 2. 결정 해석
            interpreted_decision = self.interpret_ai_decision(ai_decision)
            
            # 3. 거래 실행
            execution_result = await self.execute_ai_decision(interpreted_decision)
            
            # 4. 결과 통합
            cycle_result = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'ai_decision': ai_decision,
                'interpreted_decision': interpreted_decision,
                'execution_result': execution_result,
                'success': True,
                'method': 'scheduler_integration_v2',
                'debug_info': debug_info  # 디버깅 정보 포함
            }
            
            # 최종 AI 투자 결정 결과를 데이터베이스에 저장
            await self._save_final_decision_result(cycle_result)
            
            logger.info(f"AI 트레이딩 사이클 완료 (스케줄러 연동): {interpreted_decision['action']}")
            return cycle_result
            
        except Exception as e:
            logger.error(f"AI 트레이딩 사이클 중 오류 (스케줄러 연동): {e}")
            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'success': False,
                'error': str(e),
                'ai_decision': None,
                'interpreted_decision': None,
                'execution_result': None,
                'method': 'scheduler_integration_v2'
            }
    
    def get_decision_history(self, limit: int = 10) -> list:
        """최근 결정 히스토리 반환"""
        return self.decision_history[-limit:] if self.decision_history else []
    
    async def _save_final_decision_result(self, cycle_result: Dict):
        """최종 AI 투자 결정 결과를 MongoDB에 저장"""
        try:
            from pymongo import MongoClient
            from datetime import datetime, timezone, timedelta
            
            client = MongoClient("mongodb://mongodb:27017")
            database = client["bitcoin"]
            cache_collection = database["data_cache"]
            
            # 최종 결정 데이터 구성
            final_decision_data = {
                'analysis_result': {
                    'success': cycle_result.get('success', False),
                    'final_decision': cycle_result.get('interpreted_decision', {}).get('action', 'unknown'),
                    'ai_confidence': cycle_result.get('ai_decision', {}).get('result', {}).get('decision_confidence', 0),
                    'ai_decision_raw': cycle_result.get('ai_decision', {}).get('result', {}).get('final_decision', 'Hold'),
                    'reasoning': cycle_result.get('interpreted_decision', {}).get('reason', ''),
                    'should_trade': cycle_result.get('interpreted_decision', {}).get('action') not in ['wait', 'hold'],
                    'execution_attempted': cycle_result.get('execution_result', {}).get('attempted', False),
                    'execution_success': cycle_result.get('execution_result', {}).get('success', False),
                    'position_action': cycle_result.get('interpreted_decision', {}).get('action', 'wait'),
                    'analysis_quality': cycle_result.get('ai_decision', {}).get('result', {}).get('timing_summary', {}).get('overall_quality', 'unknown'),
                    'cache_efficiency': cycle_result.get('ai_decision', {}).get('result', {}).get('timing_summary', {}).get('cache_efficiency_percent', 0),
                    'analyzers_used': list(cycle_result.get('analysis_results', {}).keys()) if cycle_result.get('analysis_results') else [],
                    'analyzers_success_count': sum(1 for result in cycle_result.get('analysis_results', {}).values() if result.get('success', False)),
                    'analyzers_total_count': len(cycle_result.get('analysis_results', {}))
                },
                'analysis_timestamp': cycle_result.get('timestamp', datetime.now(timezone.utc).isoformat()),
                'cycle_details': {
                    'trading_config': self.config,
                    'analysis_results': cycle_result.get('analysis_results', {}),
                    'ai_decision_full': cycle_result.get('ai_decision', {}),
                    'interpreted_decision_full': cycle_result.get('interpreted_decision', {}),
                    'execution_result_full': cycle_result.get('execution_result', {})
                },
                'summary': {
                    'action_taken': cycle_result.get('interpreted_decision', {}).get('action', 'wait'),
                    'confidence_level': 'high' if cycle_result.get('ai_decision', {}).get('result', {}).get('decision_confidence', 0) >= 80 
                                      else 'medium' if cycle_result.get('ai_decision', {}).get('result', {}).get('decision_confidence', 0) >= 60 
                                      else 'low',
                    'trade_executed': cycle_result.get('execution_result', {}).get('success', False),
                    'analysis_completeness': f"{sum(1 for result in cycle_result.get('analysis_results', {}).values() if result.get('success', False))}/{len(cycle_result.get('analysis_results', {}))}" if cycle_result.get('analysis_results') else "0/0"
                }
            }
            
            # 캐시 데이터 저장 (24시간 TTL)
            expire_at = datetime.now(timezone.utc) + timedelta(hours=24)
            
            cache_collection.replace_one(
                {"task_name": "ai_final_decision", "created_at": {"$gte": datetime.now(timezone.utc) - timedelta(minutes=1)}},
                {
                    "task_name": "ai_final_decision",
                    "data": final_decision_data,
                    "created_at": datetime.now(timezone.utc),
                    "expire_at": expire_at
                },
                upsert=True
            )
            
            # logger.debug("최종 AI 투자 결정 결과 저장 완료")
            
        except Exception as e:
            logger.error(f"최종 AI 투자 결정 결과 저장 중 오류: {e}")
    
    def get_system_status(self) -> Dict:
        """AI 트레이딩 시스템 상태 반환"""
        return {
            'config': self.config,
            'decision_history_count': len(self.decision_history),
            'last_decision_time': self.decision_history[-1]['timestamp'] if self.decision_history else None,
            'system_health': 'operational'
        }

# 외부에서 사용할 함수들
async def run_ai_trading_analysis(trading_config: Dict) -> Dict:
    """AI 트레이딩 분석 실행 - 스케줄러 연동 버전"""
    integration = AITradingIntegration(trading_config)
    return await integration.get_ai_decision()

async def execute_ai_trading_cycle(trading_config: Dict) -> Dict:
    """완전한 AI 트레이딩 사이클 실행 - 스케줄러 연동 버전"""
    integration = AITradingIntegration(trading_config)
    return await integration.run_ai_trading_cycle()

# 🔧 추가: 디버깅용 함수
async def debug_ai_trading_system(trading_config: Dict) -> Dict:
    """AI 트레이딩 시스템 디버깅 정보 반환"""
    integration = AITradingIntegration(trading_config)
    return await integration.debug_scheduler_status()

# 🔧 추가: 개별 분석 조회 함수들도 data_scheduler 사용하도록 수정
async def get_ai_sentiment_analysis():
    """AI 시장 감정 분석 결과 요청 - 수정된 버전"""
    from docs.investment_ai.data_scheduler import get_data_scheduler
    scheduler = get_data_scheduler()
    return await scheduler.get_data("ai_sentiment_analysis")

async def get_ai_technical_analysis():
    """AI 기술적 분석 결과 요청 - 수정된 버전"""
    from docs.investment_ai.data_scheduler import get_data_scheduler
    scheduler = get_data_scheduler()
    return await scheduler.get_data("ai_technical_analysis")

async def get_ai_macro_analysis():
    """AI 거시경제 분석 결과 요청 - 수정된 버전"""
    from docs.investment_ai.data_scheduler import get_data_scheduler
    scheduler = get_data_scheduler()
    return await scheduler.get_data("ai_macro_analysis")

async def get_ai_onchain_analysis():
    """AI 온체인 분석 결과 요청 - 수정된 버전"""
    from docs.investment_ai.data_scheduler import get_data_scheduler
    scheduler = get_data_scheduler()
    return await scheduler.get_data("ai_onchain_analysis")

async def get_ai_institutional_analysis():
    """AI 기관투자 분석 결과 요청 - 수정된 버전"""
    from docs.investment_ai.data_scheduler import get_data_scheduler
    scheduler = get_data_scheduler()
    return await scheduler.get_data("ai_institutional_analysis")




# 테스트용 코드
if __name__ == "__main__":
    import asyncio
    
    async def test():
        test_config = {
            'symbol': 'BTCUSDT',
            'leverage': 5,
            'usdt_amount': 0.3,
            'set_timevalue': '15m',
            'take_profit': 400,
            'stop_loss': 400
        }
        
        result = await execute_ai_trading_cycle(test_config)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())