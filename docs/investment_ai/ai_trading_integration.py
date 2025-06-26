import asyncio
import json
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone

# AI 분석 모듈들 import
from docs.investment_ai.analyzers.position_analyzer import analyze_position_status
from docs.investment_ai.analyzers.sentiment_analyzer import analyze_market_sentiment
from docs.investment_ai.analyzers.technical_analyzer import analyze_technical_indicators
from docs.investment_ai.analyzers.macro_analyzer import analyze_macro_environment
from docs.investment_ai.analyzers.onchain_analyzer import analyze_onchain_data
from docs.investment_ai.analyzers.institution_analyzer import analyze_institutional_flow
from docs.investment_ai.final_decisionmaker import make_final_investment_decision

# 기존 시스템 모듈들 import
from docs.get_current import fetch_investment_status
from docs.current_price import get_current_price
from docs.making_order import execute_order, close_position, get_position_amount

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
                    current_position.update({
                        'has_position': True,
                        'side': 'long' if position['side'] == 'long' else 'short',
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
        """모든 AI 분석을 병렬로 실행"""
        try:
            logger.info("모든 AI 분석 시작")
            
            # 현재 포지션 정보 수집
            current_position = await self.get_current_position_data()
            
            # 모든 분석을 병렬로 실행
            analysis_tasks = [
                analyze_position_status(current_position),
                analyze_market_sentiment(),
                analyze_technical_indicators(self.symbol, self.timeframe, 300),
                analyze_macro_environment(),
                analyze_onchain_data(),
                analyze_institutional_flow()
            ]
            
            analysis_names = [
                'position_analysis',
                'sentiment_analysis', 
                'technical_analysis',
                'macro_analysis',
                'onchain_analysis',
                'institutional_analysis'
            ]
            
            # 병렬 실행
            results = await asyncio.gather(*analysis_tasks, return_exceptions=True)
            
            # 결과 정리
            all_analysis_results = {'current_position': current_position}
            
            for name, result in zip(analysis_names, results):
                if isinstance(result, Exception):
                    logger.error(f"{name} 분석 중 오류: {result}")
                    all_analysis_results[name] = {
                        'success': False,
                        'error': str(result)
                    }
                else:
                    all_analysis_results[name] = result
            
            logger.info("모든 AI 분석 완료")
            return all_analysis_results
            
        except Exception as e:
            logger.error(f"AI 분석 실행 중 오류: {e}")
            return {
                'error': str(e),
                'current_position': await self.get_current_position_data()
            }
    
    async def get_ai_decision(self) -> Dict:
        """AI 기반 투자 결정 도출"""
        try:
            # 모든 분석 실행
            all_analysis_results = await self.run_all_analyses()
            
            # 최종 투자 결정
            final_decision = await make_final_investment_decision(all_analysis_results)
            
            # 결정 히스토리에 추가
            decision_record = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'analysis_results': all_analysis_results,
                'final_decision': final_decision,
                'symbol': self.symbol,
                'timeframe': self.timeframe
            }
            
            self.decision_history.append(decision_record)
            
            # 히스토리 크기 제한
            if len(self.decision_history) > self.max_history:
                self.decision_history = self.decision_history[-self.max_history:]
            
            return final_decision
            
        except Exception as e:
            logger.error(f"AI 결정 도출 중 오류: {e}")
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
    
    async def run_ai_trading_cycle(self) -> Dict:
        """완전한 AI 트레이딩 사이클 실행"""
        try:
            logger.info("AI 트레이딩 사이클 시작")
            
            # 1. AI 결정 도출
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
                'success': True
            }
            
            logger.info(f"AI 트레이딩 사이클 완료: {interpreted_decision['action']}")
            return cycle_result
            
        except Exception as e:
            logger.error(f"AI 트레이딩 사이클 중 오류: {e}")
            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'success': False,
                'error': str(e),
                'ai_decision': None,
                'interpreted_decision': None,
                'execution_result': None
            }
    
    def get_decision_history(self, limit: int = 10) -> list:
        """최근 결정 히스토리 반환"""
        return self.decision_history[-limit:] if self.decision_history else []
    
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
    """AI 트레이딩 분석 실행"""
    integration = AITradingIntegration(trading_config)
    return await integration.get_ai_decision()

async def execute_ai_trading_cycle(trading_config: Dict) -> Dict:
    """완전한 AI 트레이딩 사이클 실행"""
    integration = AITradingIntegration(trading_config)
    return await integration.run_ai_trading_cycle()

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