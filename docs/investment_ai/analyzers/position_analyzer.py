import json
import re
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types
import sys
import os

# 상위 디렉토리의 utility 모듈 import를 위한 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../'))

from docs.get_current import fetch_investment_status
from docs.investment_ai.config import CONFIG, API_KEY, MODEL_PRIORITY

# 로깅 설정
logger = logging.getLogger("position_analyzer")

class PositionAnalyzer:
    """포지션 상태 분석 AI - 0단계"""
    
    def __init__(self):
        # AI 모델 초기화 제거 - 실제 호출 시에만 초기화
        self.client = None
        self.model_name = None
        
        # 실패 카운트 추가
        self.error_counts = {
            'position_data_fetch': 0
        }
        self.max_errors = 3
    
    def get_model(self):
        """AI 모델을 필요할 때만 초기화"""
        if not API_KEY:
            return None, None
            
        try:
            client = genai.Client(api_key=API_KEY)
            
            for model_name in MODEL_PRIORITY:
                try:
                    return client, model_name
                except Exception as e:
                    logger.warning(f"포지션 분석 모델 {model_name} 초기화 실패: {e}")
                    continue
            
            return None, None
            
        except Exception as e:
            logger.error(f"포지션 분석 모델 초기화 중 오류: {e}")
            return None, None
    
    def parse_position_data(self, balance, positions_json, ledger) -> Dict:
        """포지션 데이터를 분석용으로 파싱"""
        try:
            # 기본 정보 추출
            total_equity = float(balance['info']['result']['list'][0]['totalEquity'])
            available_balance = float(balance['info']['result']['list'][0]['totalAvailableBalance'])
            total_unrealized_pnl = float(balance['info']['result']['list'][0]['totalPerpUPL'])
            
            # 포지션 정보 파싱
            positions = json.loads(positions_json) if positions_json else []
            current_positions = []
            
            for pos in positions:
                if float(pos['contracts']) > 0:
                    position_info = {
                        'symbol': pos['symbol'],
                        'side': pos['side'],  # 'Buy' or 'Sell'
                        'size': float(pos['contracts']),
                        'entry_price': float(pos['entryPrice']),
                        'mark_price': float(pos['markPrice']),
                        'unrealized_pnl': float(pos['unrealizedPnl']),
                        'leverage': float(pos['leverage']),
                        'liquidation_price': pos.get('liquidationPrice', 0)
                    }
                    
                    # 수익률 계산
                    if position_info['side'] == 'Buy':
                        pnl_ratio = ((position_info['mark_price'] - position_info['entry_price']) / position_info['entry_price']) * 100
                    else:  # Sell
                        pnl_ratio = ((position_info['entry_price'] - position_info['mark_price']) / position_info['entry_price']) * 100
                    
                    position_info['pnl_ratio'] = pnl_ratio
                    
                    # 청산가까지 거리 계산
                    if position_info['liquidation_price'] and position_info['liquidation_price'] > 0:
                        if position_info['side'] == 'Buy':
                            liquidation_distance = ((position_info['mark_price'] - float(position_info['liquidation_price'])) / position_info['mark_price']) * 100
                        else:  # Sell
                            liquidation_distance = ((float(position_info['liquidation_price']) - position_info['mark_price']) / position_info['mark_price']) * 100
                        position_info['liquidation_distance'] = liquidation_distance
                    else:
                        position_info['liquidation_distance'] = 100  # 청산가 정보 없으면 안전하다고 가정
                    
                    current_positions.append(position_info)
            
            # 최근 거래 내역 파싱 (최근 5개)
            recent_trades = []
            for trade in ledger[:5]:
                if trade.get('type') == 'trade':
                    trade_info = {
                        'symbol': trade['info'].get('symbol', ''),
                        'side': trade['info'].get('side', ''),
                        'price': float(trade['info'].get('tradePrice', 0)),
                        'quantity': float(trade['info'].get('qty', 0)),
                        'fee': float(trade['info'].get('fee', 0)),
                        'timestamp': trade.get('datetime', '')
                    }
                    recent_trades.append(trade_info)
            
            # 포지션 상태 요약
            if not current_positions:
                position_status = "None"
            elif len(current_positions) == 1:
                position_status = current_positions[0]['side']  # 'Buy' or 'Sell'
            else:
                position_status = "Multiple"
            
            return {
                'position_status': position_status,
                'total_equity': total_equity,
                'available_balance': available_balance,
                'unrealized_pnl': total_unrealized_pnl,
                'current_positions': current_positions,
                'recent_trades': recent_trades,
                'position_count': len(current_positions)
            }
            
        except Exception as e:
            logger.error(f"포지션 데이터 파싱 중 오류: {e}")
            return {
                'position_status': 'Error',
                'total_equity': 0,
                'available_balance': 0,
                'unrealized_pnl': 0,
                'current_positions': [],
                'recent_trades': [],
                'position_count': 0,
                'error': str(e)
            }
    
    def get_funding_info(self) -> Dict:
        """펀딩피 관련 정보 수집"""
        try:
            from datetime import datetime, timezone
            
            # 현재 시간 (UTC)
            now = datetime.now(timezone.utc)
            
            # 다음 펀딩 시간 계산 (8시간마다: 00:00, 08:00, 16:00 UTC)
            current_hour = now.hour
            if current_hour < 8:
                next_funding_hour = 8
            elif current_hour < 16:
                next_funding_hour = 16
            else:
                next_funding_hour = 24  # 다음날 00:00
            
            next_funding = now.replace(hour=next_funding_hour % 24, minute=0, second=0, microsecond=0)
            if next_funding_hour == 24:
                next_funding = next_funding.replace(day=now.day + 1, hour=0)
            
            time_to_funding = next_funding - now
            hours_to_funding = time_to_funding.total_seconds() / 3600
            
            # 펀딩 레이트는 실제 API에서 가져와야 하지만, 여기서는 더미 데이터
            # 실제 구현시에는 bybit.fetch_funding_rate() 등을 사용
            funding_rate = 0.01  # 0.01% (더미 데이터)
            
            return {
                "next_funding_hours": round(hours_to_funding, 1),
                "current_funding_rate": funding_rate,
                "funding_direction": "Long pays Short" if funding_rate > 0 else "Short pays Long"
            }
            
        except Exception as e:
            logger.error(f"펀딩 정보 수집 중 오류: {e}")
            return {
                "next_funding_hours": 0,
                "current_funding_rate": 0,
                "funding_direction": "Unknown"
            }
        
    async def analyze_with_ai(self, position_data: Dict) -> Dict:
        """AI 모델을 사용하여 포지션 분석"""
        # 필요할 때만 모델 초기화
        if self.client is None:
            self.client, self.model_name = self.get_model()
        
        #if self.client is None:
        #    logger.warning("AI 모델이 없어 규칙 기반 분석으로 대체합니다.")
        #    return self.rule_based_analysis(position_data)
        
        try:
            # 펀딩 정보 추가
            funding_info = self.get_funding_info()
            
            # 프롬프트 구성
            prompt = CONFIG["prompts"]["position_analysis"].format(
                position_status=position_data['position_status'],
                total_equity=position_data['total_equity'],
                available_balance=position_data['available_balance'],
                current_positions=json.dumps(position_data['current_positions'], ensure_ascii=False, indent=2),
                recent_trades=json.dumps(position_data['recent_trades'], ensure_ascii=False, indent=2),
                unrealized_pnl=position_data['unrealized_pnl'],
                funding_info=json.dumps(funding_info, ensure_ascii=False, indent=2)
            )
            
            # AI 모델에 질의
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            
            # JSON 파싱
            result_text = response.text
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                result_json = json.loads(json_match.group(0))
                
                # 분석 메타데이터 추가
                result_json['analysis_metadata'] = {
                    'analysis_type': 'ai_based',
                    'data_timestamp': datetime.now(timezone.utc).isoformat(),
                    'model_used': self.model_name,
                    'raw_data': position_data
                }
                
                return result_json
            else:
                logger.error("AI 응답에서 JSON을 찾을 수 없습니다.")
                return self.rule_based_analysis(position_data)
                
        except Exception as e:
            logger.error(f"AI 포지션 분석 중 오류: {e}")
            return self.rule_based_analysis(position_data)
    
    def rule_based_analysis(self, position_data: Dict) -> Dict:
        """규칙 기반 포지션 분석 (AI 모델 없을 때 백업)"""
        try:
            position_status = position_data['position_status']
            total_equity = position_data['total_equity']
            current_positions = position_data['current_positions']
            unrealized_pnl = position_data['unrealized_pnl']
            
            # 기본 분석 결과 구조
            result = {
                "position_status": position_status,
                "position_health": {
                    "risk_level": "Medium",
                    "liquidation_distance": "N/A",
                    "leverage_assessment": "적정 (변경 불가)",
                    "position_size_ratio": "0%"
                },
                "performance_analysis": {
                    "unrealized_pnl_ratio": f"{(unrealized_pnl/total_equity)*100:.2f}%" if total_equity > 0 else "0%",
                    "entry_vs_current": "정보 없음",
                    "holding_period": "정보 없음"
                },
                "recommended_actions": [],
                "next_entry_plan": {
                    "if_no_position": {
                        "recommended_leverage": "3",
                        "position_size_percent": "30%",
                        "mandatory_stop_loss": "진입가 대비 3% 손절",
                        "mandatory_take_profit": "진입가 대비 6% 익절"
                    }
                },
                "risk_management": {
                    "current_stop_loss": "설정 없음",
                    "current_take_profit": "설정 없음",
                    "adjustment_needed": False,
                    "adjustment_reason": ""
                },
                "funding_impact": {
                    "current_funding_rate": "0.01%",
                    "next_funding_time": "정보 없음",
                    "funding_strategy": "신호 강도 우선"
                },
                "confidence": 40,
                "analysis_summary": "규칙 기반 분석으로 기본적인 포지션 평가를 수행했습니다."
            }
            
            # 포지션별 상세 분석
            if position_status == "None":
                result["recommended_actions"] = [{
                    "action": "Hold",
                    "reason": "현재 포지션이 없어 진입 신호 대기",
                    "priority": "Low",
                    "suggested_price": "",
                    "risk_reward": "대기 상태"
                }]
                result["position_health"]["risk_level"] = "Low"
                
            elif current_positions:
                total_position_value = 0
                avg_leverage = 0
                min_liquidation_distance = 100
                
                for pos in current_positions:
                    position_value = pos['size'] * pos['mark_price']
                    total_position_value += position_value
                    avg_leverage += pos['leverage']
                    
                    if pos['liquidation_distance'] < min_liquidation_distance:
                        min_liquidation_distance = pos['liquidation_distance']
                
                avg_leverage = avg_leverage / len(current_positions)
                position_ratio = (total_position_value / total_equity) * 100 if total_equity > 0 else 0
                
                result["position_health"]["position_size_ratio"] = f"{position_ratio:.1f}%"
                result["position_health"]["liquidation_distance"] = f"{min_liquidation_distance:.1f}%"
                result["position_health"]["leverage_assessment"] = f"레버리지 {avg_leverage:.1f}x (변경 불가)"
                
                # 리스크 레벨 판정
                if min_liquidation_distance < 5:
                    result["position_health"]["risk_level"] = "Critical"
                elif min_liquidation_distance < 15:
                    result["position_health"]["risk_level"] = "High"
                elif avg_leverage > 5:
                    result["position_health"]["risk_level"] = "Medium"
                else:
                    result["position_health"]["risk_level"] = "Low"
                
                # 수익률 기반 권장사항
                avg_pnl_ratio = sum(pos['pnl_ratio'] for pos in current_positions) / len(current_positions)
                
                if avg_pnl_ratio > 5:
                    result["recommended_actions"].append({
                        "action": "SetTakeProfit",
                        "reason": f"평균 수익률 {avg_pnl_ratio:.1f}%로 부분 익절 고려",
                        "priority": "Medium",
                        "suggested_price": "",
                        "risk_reward": "수익 보호"
                    })
                elif avg_pnl_ratio < -3:
                    result["recommended_actions"].append({
                        "action": "SetStopLoss",
                        "reason": f"평균 손실률 {avg_pnl_ratio:.1f}%로 손절 고려",
                        "priority": "High",
                        "suggested_price": "",
                        "risk_reward": "손실 제한"
                    })
                else:
                    result["recommended_actions"].append({
                        "action": "Hold",
                        "reason": "현재 수익률 범위 내에서 추가 신호 대기",
                        "priority": "Medium",
                        "suggested_price": "",
                        "risk_reward": "관찰 유지"
                    })
                
                # SL/TP 설정 상태 확인 (실제로는 API에서 가져와야 함)
                result["risk_management"]["adjustment_needed"] = True
                result["risk_management"]["adjustment_reason"] = "SL/TP 설정 상태 확인 필요"
            
            # 메타데이터 추가
            result['analysis_metadata'] = {
                'analysis_type': 'rule_based',
                'data_timestamp': datetime.now(timezone.utc).isoformat(),
                'model_used': 'rule_based_fallback',
                'raw_data': position_data
            }
            
            return result
            
        except Exception as e:
            logger.error(f"규칙 기반 포지션 분석 중 오류: {e}")
            return {
                "position_status": "Error",
                "error": str(e),
                "confidence": 0,
                "analysis_summary": f"분석 중 오류 발생: {str(e)}"
            }
    
    def check_data_availability(self) -> bool:
        """데이터 사용 가능 여부 확인"""
        if self.error_counts['position_data_fetch'] >= self.max_errors:
            return False
        return True
    
    async def analyze_position_status(self) -> Dict:
        """포지션 상태 분석 메인 함수"""
        try:
            logger.info("포지션 상태 분석 시작")
            
            # 데이터 사용 가능 여부 확인
            if not self.check_data_availability():
                logger.warning("포지션 분석: 데이터 수집 연속 실패 - 분석 건너뛰기")
                return {
                    "success": False,
                    "error": "데이터 수집에서 연속 실패 - 분석 불가",
                    "analysis_type": "position_analysis",
                    "skip_reason": "insufficient_data"
                }
            
            # 1. 포지션 데이터 수집
            balance, positions_json, ledger = fetch_investment_status()
            
            if balance == 'error':
                self.error_counts['position_data_fetch'] += 1
                return {
                    "success": False,
                    "error": "포지션 데이터 수집 실패",
                    "analysis_type": "position_analysis"
                }
            
            # 2. 데이터 파싱
            position_data = self.parse_position_data(balance, positions_json, ledger)
            
            if 'error' in position_data:
                return {
                    "success": False,
                    "error": position_data['error'],
                    "analysis_type": "position_analysis"
                }
            
            # 3. AI 분석 수행
            analysis_result = await self.analyze_with_ai(position_data)
            
            logger.info("포지션 상태 분석 완료")
            
            return {
                "success": True,
                "result": analysis_result,
                "analysis_type": "position_analysis"
            }
            
        except Exception as e:
            logger.error(f"포지션 상태 분석 중 오류: {e}")
            return {
                "success": False,
                "error": f"분석 중 오류 발생: {str(e)}",
                "analysis_type": "position_analysis"
            }

# 외부에서 사용할 함수
async def analyze_position_status(position_data: Optional[Dict] = None) -> Dict:
    """포지션 상태를 분석하는 함수"""
    analyzer = PositionAnalyzer()
    return await analyzer.analyze_position_status()

# 테스트용 코드
if __name__ == "__main__":
    import asyncio
    
    async def test():
        result = await analyze_position_status()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())
