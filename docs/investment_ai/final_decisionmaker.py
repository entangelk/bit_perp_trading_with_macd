import json
import re
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from google import genai
from google.genai import types
import sys
import os

# 상위 디렉토리의 모듈 import를 위한 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../'))

from docs.investment_ai.config import CONFIG, API_KEY, MODEL_PRIORITY

# 로깅 설정
logger = logging.getLogger("final_decision_maker")

class FinalDecisionMaker:
    """최종 투자 결정 AI - 모든 분석 통합"""
    
    def __init__(self):
        # AI 모델 초기화 제거 - 실제 호출 시에만 초기화
        self.client = None
        self.model_name = None
        
        # 분석별 기본 가중치 (상황에 따라 동적 조정)
        self.default_weights = {
            'position_analysis': 25,      # 현재 포지션 상태 (최우선)
            'technical_analysis': 20,     # 기술적 분석 (단기 신호)
            'sentiment_analysis': 15,     # 시장 심리 (시장 분위기)
            'macro_analysis': 15,         # 거시경제 (중장기 환경)
            'onchain_analysis': 15,       # 온체인 데이터 (펀더멘털)
            'institutional_analysis': 10  # 기관 투자 흐름 (장기 트렌드)
        }
        
        # 결정 임계값 설정
        self.decision_thresholds = {
            'strong_buy': 75,
            'buy': 60,
            'hold': 40,
            'sell': 25,
            'strong_sell': 0
        }
        
        # 리스크 관리 설정
        self.risk_params = {
            'max_position_size': 50,      # 최대 포지션 크기 (%)
            'max_leverage': 10,           # 최대 레버리지
            'min_confidence': 60,         # 최소 신뢰도
            'stop_loss_range': (2, 8),    # 스톱로스 범위 (%)
            'take_profit_range': (4, 15)  # 테이크프로핏 범위 (%)
        }

        self.scheduler_to_analysis_mapping = {
            # 스케줄러 키 → 최종결정에서 사용하는 키
            'ai_technical_analysis': 'technical_analysis',
            'ai_sentiment_analysis': 'sentiment_analysis', 
            'ai_macro_analysis': 'macro_analysis',
            'ai_onchain_analysis': 'onchain_analysis',
            'ai_institutional_analysis': 'institutional_analysis',
            'position_data': 'position_analysis',  # 포지션은 원시 데이터
            # 현재 포지션은 별도 처리
        }
        logger.info("최종 결정 메이커 초기화 완료 - 스케줄러 연동 지원")

    def get_analysis_data_from_scheduler(self, scheduler) -> Dict:
        """스케줄러에서 AI 분석 결과들을 가져와서 최종결정 형식으로 변환"""
        try:
            logger.info("스케줄러에서 분석 데이터 매핑 시작")
            mapped_results = {}
            
            # 1. AI 분석 결과들 매핑
            for scheduler_key, analysis_key in self.scheduler_to_analysis_mapping.items():
                try:
                    logger.debug(f"매핑 시도: {scheduler_key} → {analysis_key}")
                    
                    # 스케줄러에서 캐시된 데이터 조회
                    cached_data = scheduler.get_cached_data(scheduler_key)
                    
                    if cached_data:
                        if scheduler_key.startswith('ai_'):
                            # AI 분석 결과는 analysis_result 안에 있음
                            if 'analysis_result' in cached_data:
                                analysis_result = cached_data['analysis_result']
                                mapped_results[analysis_key] = analysis_result
                                
                                # 성공/실패 로깅
                                if analysis_result.get('success', False):
                                    logger.debug(f"✅ {scheduler_key} → {analysis_key} 매핑 성공 (AI 분석)")
                                else:
                                    skip_reason = analysis_result.get('skip_reason', 'unknown')
                                    logger.warning(f"⚠️ {scheduler_key} → {analysis_key} 실패한 분석 매핑 (이유: {skip_reason})")
                            else:
                                logger.error(f"❌ {scheduler_key}: analysis_result 키가 없음")
                                mapped_results[analysis_key] = {
                                    'success': False,
                                    'error': f'{scheduler_key}: analysis_result 키 누락',
                                    'skip_reason': 'malformed_cache_data'
                                }
                        else:
                            # 원시 데이터 (position_data 등)는 직접 사용
                            mapped_results[analysis_key] = cached_data
                            logger.debug(f"✅ {scheduler_key} → {analysis_key} 원시데이터 매핑")
                    else:
                        logger.warning(f"❌ {scheduler_key} 캐시 데이터 없음")
                        mapped_results[analysis_key] = {
                            'success': False,
                            'error': f'{scheduler_key} 캐시 데이터 없음',
                            'skip_reason': 'no_cached_data'
                        }
                        
                except Exception as e:
                    logger.error(f"❌ {scheduler_key} 매핑 중 오류: {e}")
                    mapped_results[analysis_key] = {
                        'success': False,
                        'error': f'{scheduler_key} 매핑 실패: {str(e)}',
                        'skip_reason': 'mapping_error'
                    }
            
            # 2. 포지션 분석 별도 처리 (포지션 데이터로부터 실시간 분석 수행)
            try:
                logger.debug("포지션 분석 실시간 수행 시작")
                position_data = scheduler.get_cached_data('position_data')
                
                if position_data:
                    # 포지션 데이터를 바탕으로 포지션 분석 수행
                    from docs.investment_ai.analyzers.position_analyzer import analyze_position_status
                    
                    # 포지션 데이터에서 현재 포지션 정보 추출
                    current_position_info = self._extract_current_position_from_data(position_data)
                    
                    # 실시간 포지션 분석 수행
                    position_analysis = analyze_position_status()
                    
                    if position_analysis and position_analysis.get('success', False):
                        mapped_results['position_analysis'] = position_analysis
                        logger.info("✅ 포지션 분석 실시간 수행 성공")
                    else:
                        logger.warning("❌ 포지션 분석 실시간 수행 실패")
                        mapped_results['position_analysis'] = {
                            'success': False,
                            'error': '포지션 분석 실패',
                            'skip_reason': 'position_analysis_failed'
                        }
                else:
                    logger.warning("❌ 포지션 데이터 없음")
                    mapped_results['position_analysis'] = {
                        'success': False,
                        'error': '포지션 데이터 없음',
                        'skip_reason': 'no_position_data'
                    }
                    
            except Exception as e:
                logger.error(f"❌ 포지션 분석 중 오류: {e}")
                mapped_results['position_analysis'] = {
                    'success': False,
                    'error': f'포지션 분석 오류: {str(e)}',
                    'skip_reason': 'position_analysis_error'
                }
            
            # 3. 현재 포지션 정보 추가 (최종 결정에서 필요)
            try:
                logger.debug("현재 포지션 정보 추출 시작")
                position_data = scheduler.get_cached_data('position_data')
                
                if position_data and 'balance' in position_data:
                    current_position = self._extract_current_position_from_data(position_data)
                    mapped_results['current_position'] = current_position
                    logger.debug("✅ 현재 포지션 정보 추출 성공")
                else:
                    # 기본 포지션 정보
                    mapped_results['current_position'] = {
                        'has_position': False,
                        'side': 'none',
                        'size': 0,
                        'entry_price': 0
                    }
                    logger.warning("❌ 포지션 데이터 없음 - 기본값 사용")
                    
            except Exception as e:
                logger.error(f"❌ 현재 포지션 추출 중 오류: {e}")
                mapped_results['current_position'] = {
                    'has_position': False,
                    'side': 'none',
                    'size': 0,
                    'entry_price': 0,
                    'error': str(e)
                }
            
            # 4. 매핑 결과 요약 및 검증
            success_count = 0
            failed_count = 0
            skipped_count = 0
            
            for key, value in mapped_results.items():
                if key == 'current_position':
                    continue  # 현재 포지션은 별도 처리
                    
                if isinstance(value, dict):
                    if value.get('success', False):
                        success_count += 1
                    elif value.get('skip_reason'):
                        skipped_count += 1
                    else:
                        failed_count += 1
                else:
                    success_count += 1  # 원시 데이터
            
            total_analyses = success_count + failed_count + skipped_count
            
            logger.info(f"데이터 매핑 완료: 성공 {success_count}, 실패 {failed_count}, 스킵 {skipped_count} / 총 {total_analyses}개")
            
            # 실패한 분석들 상세 로깅
            failed_analyses = []
            for key, value in mapped_results.items():
                if isinstance(value, dict) and not value.get('success', False) and key != 'current_position':
                    reason = value.get('skip_reason', value.get('error', 'unknown'))
                    failed_analyses.append(f"{key}({reason})")
            
            if failed_analyses:
                logger.warning(f"실패한 분석들: {', '.join(failed_analyses)}")
            
            # 매핑 메타데이터 추가
            mapped_results['_mapping_metadata'] = {
                'mapping_timestamp': datetime.now(timezone.utc).isoformat(),
                'total_analyses': total_analyses,
                'success_count': success_count,
                'failed_count': failed_count,
                'skipped_count': skipped_count,
                'success_rate': (success_count / total_analyses * 100) if total_analyses > 0 else 0,
                'failed_analyses': failed_analyses,
                'scheduler_keys_processed': list(self.scheduler_to_analysis_mapping.keys())
            }
            
            return mapped_results
            
        except Exception as e:
            logger.error(f"데이터 매핑 중 전체 오류: {e}")
            return {
                'error': f'매핑 전체 실패: {str(e)}',
                '_mapping_metadata': {
                    'mapping_timestamp': datetime.now(timezone.utc).isoformat(),
                    'total_error': True,
                    'error_details': str(e)
                }
            }

    def _extract_current_position_from_data(self, position_data: Dict) -> Dict:
        """포지션 데이터에서 현재 포지션 상태 추출"""
        try:
            current_position = {
                'has_position': False,
                'side': 'none',
                'size': 0,
                'entry_price': 0,
                'unrealized_pnl': 0,
                'margin_ratio': 0,
                'total_equity': 0,
                'available_balance': 0
            }
            
            # 잔고 정보 추출
            balance = position_data.get('balance', {})
            if isinstance(balance, dict) and 'USDT' in balance:
                usdt_balance = balance['USDT']
                current_position.update({
                    'total_equity': float(usdt_balance.get('total', 0)),
                    'available_balance': float(usdt_balance.get('free', 0))
                })
            
            # positions 필드에서 BTC 포지션 찾기
            positions = position_data.get('positions', [])
            if isinstance(positions, str):
                import json
                try:
                    positions = json.loads(positions)
                except:
                    positions = []
            
            btc_position = None
            if isinstance(positions, list):
                for pos in positions:
                    if isinstance(pos, dict):
                        symbol = pos.get('symbol', '').upper()
                        if 'BTC' in symbol:
                            btc_position = pos
                            break
            
            if btc_position:
                size = float(btc_position.get('size', btc_position.get('contracts', 0)))
                if abs(size) > 0:
                    current_position.update({
                        'has_position': True,
                        'side': 'long' if size > 0 else 'short',
                        'size': abs(size),
                        'entry_price': float(btc_position.get('avgPrice', btc_position.get('entryPrice', 0))),
                        'unrealized_pnl': float(btc_position.get('unrealizedPnl', 0)),
                        'margin_ratio': float(btc_position.get('marginRatio', 0))
                    })
            
            logger.debug(f"포지션 상태 추출 완료: {current_position['side']} {current_position['size']}")
            return current_position
            
        except Exception as e:
            logger.error(f"포지션 상태 추출 오류: {e}")
            return {
                'has_position': False,
                'side': 'none',
                'size': 0,
                'entry_price': 0,
                'error': str(e)
            }



    async def make_final_decision_with_scheduler(self, scheduler) -> Dict:
        """스케줄러를 사용한 최종 투자 결정 (새로운 메인 함수)"""
        try:
            logger.info("최종 투자 결정 분석 시작 (스케줄러 연동)")
            
            # 1. 스케줄러에서 분석 결과들 가져오기 및 매핑
            all_analysis_results = self.get_analysis_data_from_scheduler(scheduler)
            
            # 매핑 실패 확인
            if 'error' in all_analysis_results:
                logger.error(f"스케줄러에서 분석 결과 매핑 실패: {all_analysis_results['error']}")
                return {
                    "success": False,
                    "error": f"스케줄러 연동 실패: {all_analysis_results['error']}",
                    "analysis_type": "final_decision",
                    "skip_reason": "scheduler_mapping_failed"
                }
            
            if not all_analysis_results:
                logger.error("스케줄러에서 분석 결과를 가져오지 못함")
                return {
                    "success": False,
                    "error": "스케줄러 연동 실패 - 분석 결과 없음",
                    "analysis_type": "final_decision",
                    "skip_reason": "scheduler_integration_failed"
                }
            
            # 2. 매핑 품질 검증
            mapping_metadata = all_analysis_results.get('_mapping_metadata', {})
            success_rate = mapping_metadata.get('success_rate', 0)
            
            if success_rate < 40:  # 40% 미만 성공률이면 위험
                logger.warning(f"매핑 성공률이 낮음 ({success_rate:.1f}%) - 신중한 결정 필요")
                
            # 3. 기존 최종 결정 로직 실행 (매핑된 데이터 사용)
            logger.info(f"최종 결정 로직 실행 (매핑 성공률: {success_rate:.1f}%)")
            final_decision_result = await self.make_final_decision(all_analysis_results)
            
            # 4. 결과에 스케줄러 연동 정보 추가
            if final_decision_result.get('success', False):
                result_data = final_decision_result.get('result', {})
                if 'analysis_metadata' not in result_data:
                    result_data['analysis_metadata'] = {}
                
                result_data['analysis_metadata'].update({
                    'scheduler_integration': True,
                    'mapping_success_rate': success_rate,
                    'mapping_timestamp': mapping_metadata.get('mapping_timestamp'),
                    'scheduler_keys_used': mapping_metadata.get('scheduler_keys_processed', []),
                    'failed_mappings': mapping_metadata.get('failed_analyses', [])
                })
            
            logger.info("최종 투자 결정 완료 (스케줄러 연동)")
            return final_decision_result
            
        except Exception as e:
            logger.error(f"스케줄러 연동 최종 결정 중 오류: {e}")
            return {
                "success": False,
                "error": f"스케줄러 연동 중 오류: {str(e)}",
                "analysis_type": "final_decision",
                "skip_reason": "scheduler_integration_error"
            }

    def debug_scheduler_data_mapping(self, scheduler) -> Dict:
        """스케줄러 데이터 매핑 디버깅 정보 (개발/테스트용)"""
        try:
            debug_info = {
                'scheduler_cache_status': {},
                'mapping_test_results': {},
                'raw_cache_data_preview': {},
                'debug_timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            # 각 스케줄러 키의 캐시 상태 확인
            for scheduler_key, analysis_key in self.scheduler_to_analysis_mapping.items():
                try:
                    cached_data = scheduler.get_cached_data(scheduler_key)
                    
                    if cached_data:
                        debug_info['scheduler_cache_status'][scheduler_key] = {
                            'has_cache': True,
                            'data_type': str(type(cached_data)),
                            'keys': list(cached_data.keys()) if isinstance(cached_data, dict) else 'not_dict',
                            'size_estimate': len(str(cached_data))
                        }
                        
                        # 첫 100자만 미리보기
                        preview = str(cached_data)[:100] + "..." if len(str(cached_data)) > 100 else str(cached_data)
                        debug_info['raw_cache_data_preview'][scheduler_key] = preview
                        
                        # 매핑 테스트
                        if scheduler_key.startswith('ai_') and isinstance(cached_data, dict):
                            if 'analysis_result' in cached_data:
                                analysis_result = cached_data['analysis_result']
                                debug_info['mapping_test_results'][analysis_key] = {
                                    'mapping_possible': True,
                                    'analysis_success': analysis_result.get('success', False),
                                    'analysis_keys': list(analysis_result.keys()) if isinstance(analysis_result, dict) else 'not_dict'
                                }
                            else:
                                debug_info['mapping_test_results'][analysis_key] = {
                                    'mapping_possible': False,
                                    'issue': 'no_analysis_result_key'
                                }
                        else:
                            debug_info['mapping_test_results'][analysis_key] = {
                                'mapping_possible': True,
                                'note': 'raw_data_direct_mapping'
                            }
                    else:
                        debug_info['scheduler_cache_status'][scheduler_key] = {
                            'has_cache': False
                        }
                        debug_info['mapping_test_results'][analysis_key] = {
                            'mapping_possible': False,
                            'issue': 'no_cache_data'
                        }
                        
                except Exception as e:
                    debug_info['scheduler_cache_status'][scheduler_key] = {
                        'has_cache': False,
                        'error': str(e)
                    }
                    debug_info['mapping_test_results'][analysis_key] = {
                        'mapping_possible': False,
                        'issue': f'debug_error: {str(e)}'
                    }
            
            return debug_info
            
        except Exception as e:
            return {
                'debug_error': str(e),
                'debug_timestamp': datetime.now(timezone.utc).isoformat()
            }

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
                    logger.warning(f"최종 결정 모델 {model_name} 초기화 실패: {e}")
                    continue
            
            return None, None
            
        except Exception as e:
            logger.error(f"최종 결정 모델 초기화 중 오류: {e}")
            return None, None
    
    def validate_analysis_results(self, analysis_results: Dict) -> Dict:
        """분석 결과 검증 및 정제 - NoneType 에러 수정"""
        try:
            validated = {}
            
            # 🔧 수정: analysis_results None 체크 추가
            if not analysis_results or not isinstance(analysis_results, dict):
                logger.error("분석 결과가 None이거나 딕셔너리가 아님")
                return {}
            
            # 각 분석 결과 검증
            required_analyses = [
                'position_analysis', 'technical_analysis', 'sentiment_analysis',
                'macro_analysis', 'onchain_analysis', 'institutional_analysis'
            ]
            
            for analysis_type in required_analyses:
                try:
                    if analysis_type in analysis_results:
                        result = analysis_results[analysis_type]
                        
                        # 🔧 수정: result가 None인 경우 체크
                        if result is None:
                            logger.warning(f"{analysis_type} 결과가 None")
                            validated[analysis_type] = {
                                'result': {},
                                'confidence': 0,
                                'signal': 'Hold',
                                'timestamp': datetime.now().isoformat(),
                                'data_quality': 0,
                                'error': f'{analysis_type} 결과가 None',
                                'timing_metadata': {'status': 'none_result', 'analysis_type': analysis_type}
                            }
                            continue
                        
                        # 성공 여부 확인
                        if isinstance(result, dict) and result.get('success', False):
                            validated[analysis_type] = {
                                'result': result.get('result', {}),
                                'confidence': self._extract_confidence(result.get('result', {})),
                                'signal': self._extract_signal(result.get('result', {})),
                                'timestamp': result.get('result', {}).get('analysis_metadata', {}).get('data_timestamp', datetime.now().isoformat()),
                                'data_quality': result.get('data_quality', {}).get('success_rate', 0) if result.get('data_quality') else 0,
                                'timing_metadata': self._extract_timing_metadata(result, analysis_type)
                            }
                        else:
                            # 실패한 분석은 중립으로 처리
                            error_msg = result.get('error', '분석 실패') if isinstance(result, dict) else '잘못된 결과 형식'
                            validated[analysis_type] = {
                                'result': {},
                                'confidence': 0,
                                'signal': 'Hold',
                                'timestamp': datetime.now().isoformat(),
                                'data_quality': 0,
                                'error': error_msg,
                                'timing_metadata': self._extract_timing_metadata(result if isinstance(result, dict) else {}, analysis_type)
                            }
                    else:
                        # 누락된 분석도 중립으로 처리
                        validated[analysis_type] = {
                            'result': {},
                            'confidence': 0,
                            'signal': 'Hold',
                            'timestamp': datetime.now().isoformat(),
                            'data_quality': 0,
                            'error': '분석 누락',
                            'timing_metadata': {'status': 'missing', 'analysis_type': analysis_type}
                        }
                except Exception as e:
                    logger.error(f"{analysis_type} 검증 중 오류: {e}")
                    validated[analysis_type] = {
                        'result': {},
                        'confidence': 0,
                        'signal': 'Hold',
                        'timestamp': datetime.now().isoformat(),
                        'data_quality': 0,
                        'error': f'검증 오류: {str(e)}',
                        'timing_metadata': {'status': 'validation_error', 'analysis_type': analysis_type}
                    }
            
            return validated
            
        except Exception as e:
            logger.error(f"분석 결과 검증 중 전체 오류: {e}")
            return {}

    
    def _extract_confidence(self, result: Dict) -> float:
        """분석 결과에서 신뢰도 추출 - None 체크 강화"""
        try:
            # 🔧 수정: result가 None이거나 딕셔너리가 아닌 경우 체크
            if not result or not isinstance(result, dict):
                return 50.0
            
            # 다양한 신뢰도 키 시도
            confidence_keys = ['confidence', 'analysis_confidence', 'reliability_score']
            
            for key in confidence_keys:
                if key in result:
                    confidence = result[key]
                    if isinstance(confidence, (int, float)) and confidence is not None:
                        return min(100, max(0, float(confidence)))
            
            # 신뢰도가 없으면 기본값
            return 50.0
            
        except Exception as e:
            logger.warning(f"신뢰도 추출 오류: {e}")
            return 50.0

    def _extract_signal(self, result: Dict) -> str:
        """분석 결과에서 투자 신호 추출 - None 체크 강화"""
        try:
            # 🔧 수정: result가 None이거나 딕셔너리가 아닌 경우 체크
            if not result or not isinstance(result, dict):
                return 'Hold'
            
            # 다양한 신호 키 시도
            signal_keys = [
                'investment_signal', 'final_decision', 'btc_signal', 
                'institution_signal', 'recommended_action', 'signal'
            ]
            
            for key in signal_keys:
                if key in result and result[key] is not None:
                    signal = str(result[key]).strip()
                    # 신호 정규화
                    return self._normalize_signal(signal)
            
            # 신호가 없으면 Hold
            return 'Hold'
            
        except Exception as e:
            logger.warning(f"신호 추출 오류: {e}")
            return 'Hold'


    def _normalize_signal(self, signal: str) -> str:
        """투자 신호 정규화"""
        signal_lower = signal.lower()
        
        # Strong Buy 패턴
        if any(keyword in signal_lower for keyword in ['strong buy', 'very bullish', 'aggressive buy']):
            return 'Strong Buy'
        
        # Buy 패턴
        elif any(keyword in signal_lower for keyword in ['buy', 'bullish', 'long']):
            return 'Buy'
        
        # Strong Sell 패턴
        elif any(keyword in signal_lower for keyword in ['strong sell', 'very bearish', 'aggressive sell']):
            return 'Strong Sell'
        
        # Sell 패턴
        elif any(keyword in signal_lower for keyword in ['sell', 'bearish', 'short']):
            return 'Sell'
        
        # Hold 패턴 (기본값)
        else:
            return 'Hold'
    
    def _extract_timing_metadata(self, result: Dict, analysis_type: str) -> Dict:
        """분석 결과에서 타이밍 메타데이터 추출 - None 체크 강화"""
        try:
            timing_metadata = {
                'analysis_type': analysis_type,
                'extraction_time': datetime.now(timezone.utc).isoformat()
            }
            
            # 🔧 수정: result가 None이거나 딕셔너리가 아닌 경우 체크
            if not result or not isinstance(result, dict):
                timing_metadata.update({
                    'status': 'no_result_data',
                    'error_reason': 'Result is None or not dict'
                })
                return timing_metadata
            
            # 기본 분석 정보
            if result.get('success', False):
                analysis_result = result.get('result', {})
                if isinstance(analysis_result, dict):
                    analysis_metadata = analysis_result.get('analysis_metadata', {})
                    
                    timing_metadata.update({
                        'status': 'success',
                        'analysis_timestamp': analysis_metadata.get('data_timestamp', analysis_metadata.get('analysis_timestamp')),
                        'model_used': analysis_metadata.get('model_used'),
                        'analysis_duration': analysis_metadata.get('analysis_duration'),
                        'data_collection_time': analysis_metadata.get('data_collection_time')
                    })
                else:
                    timing_metadata.update({
                        'status': 'success_but_no_metadata',
                        'note': 'Result exists but no metadata'
                    })
            else:
                timing_metadata.update({
                    'status': 'failed',
                    'error_reason': result.get('error', 'Unknown'),
                    'skip_reason': result.get('skip_reason')
                })
            
            # 캐시 관련 정보 (스케줄러에서 온 경우)
            if 'analysis_timestamp' in result:
                timing_metadata['cached_analysis_time'] = result['analysis_timestamp']
            
            if 'data_freshness' in result:
                timing_metadata['data_freshness'] = result['data_freshness']
            
            if 'raw_data_used' in result:
                timing_metadata['raw_data_status'] = result['raw_data_used']
            
            # 비활성화 정보
            if result.get('disabled', False):
                timing_metadata['disabled'] = True
                timing_metadata['status'] = 'disabled'
            
            if result.get('skipped', False):
                timing_metadata['skipped'] = True
                timing_metadata['status'] = 'skipped'
            
            return timing_metadata
            
        except Exception as e:
            return {
                'analysis_type': analysis_type,
                'status': 'extraction_error',
                'error': str(e),
                'extraction_time': datetime.now(timezone.utc).isoformat()
            }

    def calculate_dynamic_weights(self, validated_results: Dict) -> Dict:
        """분석별 동적 가중치 계산"""
        try:
            weights = self.default_weights.copy()
            
            # 데이터 품질에 따른 가중치 조정
            for analysis_type, data in validated_results.items():
                confidence = data.get('confidence', 50)
                data_quality = data.get('data_quality', 50)
                
                # 신뢰도가 낮으면 가중치 감소
                if confidence < 30:
                    weights[analysis_type] *= 0.5
                elif confidence < 50:
                    weights[analysis_type] *= 0.7
                elif confidence > 80:
                    weights[analysis_type] *= 1.2
                
                # 데이터 품질이 낮으면 가중치 추가 감소
                if data_quality < 50:
                    weights[analysis_type] *= 0.8
            
            # 포지션 분석은 항상 높은 가중치 유지
            if 'position_analysis' in weights:
                weights['position_analysis'] = max(weights['position_analysis'], 20)
            
            # 가중치 정규화 (총합 100)
            total_weight = sum(weights.values())
            if total_weight > 0:
                weights = {k: (v / total_weight) * 100 for k, v in weights.items()}
            
            return weights
            
        except Exception as e:
            logger.error(f"동적 가중치 계산 중 오류: {e}")
            return self.default_weights
    
    def calculate_composite_score(self, validated_results: Dict, weights: Dict) -> Dict:
        """종합 점수 계산"""
        try:
            # 신호별 점수 매핑
            signal_scores = {
                'Strong Buy': 90,
                'Buy': 70,
                'Hold': 50,
                'Sell': 30,
                'Strong Sell': 10
            }
            
            weighted_score = 0
            total_weight = 0
            signal_distribution = {'Strong Buy': 0, 'Buy': 0, 'Hold': 0, 'Sell': 0, 'Strong Sell': 0}
            confidence_weighted_avg = 0
            
            # 각 분석의 가중 점수 계산
            for analysis_type, data in validated_results.items():
                if analysis_type in weights:
                    weight = weights[analysis_type]
                    signal = data.get('signal', 'Hold')
                    confidence = data.get('confidence', 50)
                    
                    score = signal_scores.get(signal, 50)
                    weighted_score += score * weight / 100
                    total_weight += weight
                    
                    # 신호 분포 기록
                    signal_distribution[signal] += weight
                    confidence_weighted_avg += confidence * weight / 100
            
            # 최종 점수 정규화
            composite_score = weighted_score if total_weight > 0 else 50
            
            # 최종 결정 도출
            final_decision = self._determine_final_decision(composite_score, signal_distribution)
            
            return {
                'composite_score': round(composite_score, 2),
                'final_decision': final_decision,
                'signal_distribution': {k: round(v, 1) for k, v in signal_distribution.items()},
                'weighted_confidence': round(confidence_weighted_avg, 1),
                'decision_strength': self._calculate_decision_strength(composite_score, signal_distribution)
            }
            
        except Exception as e:
            logger.error(f"종합 점수 계산 중 오류: {e}")
            return {
                'composite_score': 50.0,
                'final_decision': 'Hold',
                'signal_distribution': {'Hold': 100.0},
                'weighted_confidence': 50.0,
                'decision_strength': 'Weak'
            }
    
    def _determine_final_decision(self, score: float, signal_distribution: Dict) -> str:
        """종합 점수와 신호 분포를 기반으로 최종 결정"""
        try:
            # 점수 기반 1차 결정
            if score >= self.decision_thresholds['strong_buy']:
                primary_decision = 'Strong Buy'
            elif score >= self.decision_thresholds['buy']:
                primary_decision = 'Buy'
            elif score >= self.decision_thresholds['hold']:
                primary_decision = 'Hold'
            elif score >= self.decision_thresholds['sell']:
                primary_decision = 'Sell'
            else:
                primary_decision = 'Strong Sell'
            
            # 신호 분포 기반 검증
            max_signal = max(signal_distribution, key=signal_distribution.get)
            max_weight = signal_distribution[max_signal]
            
            # 과반수 신호가 있으면 그것을 우선
            if max_weight > 50:
                return max_signal
            
            # 그렇지 않으면 점수 기반 결정 사용
            return primary_decision
            
        except Exception as e:
            logger.error(f"최종 결정 도출 중 오류: {e}")
            return 'Hold'
    
    def _calculate_decision_strength(self, score: float, signal_distribution: Dict) -> str:
        """결정 강도 계산"""
        try:
            # 점수 극단성
            score_extremity = max(abs(score - 50), 0) / 50  # 0~1
            
            # 신호 일치도
            max_signal_weight = max(signal_distribution.values())
            signal_consensus = max_signal_weight / 100  # 0~1
            
            # 종합 강도
            strength = (score_extremity + signal_consensus) / 2
            
            if strength > 0.7:
                return 'Very Strong'
            elif strength > 0.5:
                return 'Strong'
            elif strength > 0.3:
                return 'Moderate'
            else:
                return 'Weak'
                
        except Exception:
            return 'Weak'
    
    def generate_risk_management(self, final_decision: str, composite_score: float, 
                                current_position: Dict, market_data: Dict) -> Dict:
        """리스크 관리 권장사항 생성"""
        try:
            current_price = market_data.get('current_price', 100000)
            
            # 포지션 크기 계산
            if final_decision in ['Strong Buy', 'Buy']:
                position_size = self._calculate_position_size(composite_score, 'long')
                leverage = self._calculate_leverage(composite_score, 'long')
                
                # 스톱로스/테이크프로핏
                stop_loss_pct = self._calculate_stop_loss_percentage(composite_score)
                take_profit_pct = self._calculate_take_profit_percentage(composite_score)
                
                stop_loss_price = current_price * (1 - stop_loss_pct / 100)
                take_profit_price = current_price * (1 + take_profit_pct / 100)
                
            elif final_decision in ['Strong Sell', 'Sell']:
                position_size = self._calculate_position_size(composite_score, 'short')
                leverage = self._calculate_leverage(composite_score, 'short')
                
                stop_loss_pct = self._calculate_stop_loss_percentage(100 - composite_score)
                take_profit_pct = self._calculate_take_profit_percentage(100 - composite_score)
                
                stop_loss_price = current_price * (1 + stop_loss_pct / 100)
                take_profit_price = current_price * (1 - take_profit_pct / 100)
                
            else:  # Hold
                position_size = 0
                leverage = 1
                stop_loss_price = None
                take_profit_price = None
                stop_loss_pct = 0
                take_profit_pct = 0
            
            return {
                'position_size_percent': position_size,
                'recommended_leverage': leverage,
                'stop_loss_price': round(stop_loss_price, 2) if stop_loss_price else None,
                'take_profit_price': round(take_profit_price, 2) if take_profit_price else None,
                'stop_loss_percentage': round(stop_loss_pct, 2),
                'take_profit_percentage': round(take_profit_pct, 2),
                'max_loss_amount': round(position_size * stop_loss_pct / 100, 2) if position_size > 0 else 0,
                'risk_reward_ratio': round(take_profit_pct / stop_loss_pct, 2) if stop_loss_pct > 0 else 0,
                'liquidation_buffer': 15,  # 청산가 버퍼 15%
                'position_monitoring': self._generate_monitoring_rules(final_decision, composite_score)
            }
            
        except Exception as e:
            logger.error(f"리스크 관리 생성 중 오류: {e}")
            return self._get_default_risk_management()
    
    def _calculate_position_size(self, score: float, direction: str) -> float:
        """점수 기반 포지션 크기 계산"""
        try:
            # 점수를 포지션 크기로 변환 (50점 기준)
            if direction == 'long':
                strength = max(0, score - 50) / 50  # 0~1
            else:  # short
                strength = max(0, 50 - score) / 50  # 0~1
            
            # 최소 5%, 최대 50%
            min_size, max_size = 5, self.risk_params['max_position_size']
            position_size = min_size + (max_size - min_size) * strength
            
            return round(position_size, 1)
            
        except Exception:
            return 10.0  # 기본값
    
    def _calculate_leverage(self, score: float, direction: str) -> int:
        """점수 기반 레버리지 계산"""
        try:
            # 점수가 높을수록 높은 레버리지
            if direction == 'long':
                strength = max(0, score - 50) / 50
            else:
                strength = max(0, 50 - score) / 50
            
            # 최소 1배, 최대 설정값
            min_lev, max_lev = 1, self.risk_params['max_leverage']
            leverage = min_lev + (max_lev - min_lev) * strength
            
            return max(1, min(max_lev, int(leverage)))
            
        except Exception:
            return 3  # 기본값
    
    def _calculate_stop_loss_percentage(self, strength_score: float) -> float:
        """강도 점수 기반 스톱로스 비율 계산"""
        try:
            # 강도가 높을수록 타이트한 스톱로스
            strength = strength_score / 100  # 0~1
            min_sl, max_sl = self.risk_params['stop_loss_range']
            
            # 역비례: 강도 높으면 스톱로스 작게
            stop_loss = max_sl - (max_sl - min_sl) * strength
            return round(stop_loss, 1)
            
        except Exception:
            return 5.0  # 기본값
    
    def _calculate_take_profit_percentage(self, strength_score: float) -> float:
        """강도 점수 기반 테이크프로핏 비율 계산"""
        try:
            strength = strength_score / 100
            min_tp, max_tp = self.risk_params['take_profit_range']
            
            # 정비례: 강도 높으면 테이크프로핏 크게
            take_profit = min_tp + (max_tp - min_tp) * strength
            return round(take_profit, 1)
            
        except Exception:
            return 8.0  # 기본값
    
    def _generate_monitoring_rules(self, decision: str, score: float) -> List[str]:
        """포지션 모니터링 규칙 생성"""
        rules = []
        
        if decision in ['Strong Buy', 'Buy']:
            rules.append("롱 포지션 진입 후 스톱로스 준수 필수")
            rules.append("기술적 지표 변화 모니터링")
            if score > 80:
                rules.append("강한 신호이므로 목표가 도달 시 일부 익절 고려")
        
        elif decision in ['Strong Sell', 'Sell']:
            rules.append("숏 포지션 진입 후 스톱로스 준수 필수")
            rules.append("시장 심리 변화 주시")
            if score < 20:
                rules.append("강한 약세 신호이므로 반등 시 추가 진입 고려")
        
        else:  # Hold
            rules.append("현재 포지션 유지 또는 관망")
            rules.append("명확한 신호 등장까지 대기")
        
        rules.append("15분마다 신호 업데이트 확인")
        rules.append("리스크 관리 규칙 엄수")
        
        return rules
    
    def _get_default_risk_management(self) -> Dict:
        """기본 리스크 관리 설정"""
        return {
            'position_size_percent': 10.0,
            'recommended_leverage': 3,
            'stop_loss_price': None,
            'take_profit_price': None,
            'stop_loss_percentage': 5.0,
            'take_profit_percentage': 8.0,
            'max_loss_amount': 0.5,
            'risk_reward_ratio': 1.6,
            'liquidation_buffer': 15,
            'position_monitoring': ["기본 리스크 관리 규칙 적용"]
        }
    
    def detect_signal_conflicts(self, validated_results: Dict) -> Dict:
        """신호 충돌 감지 및 해결"""
        try:
            signals = [data.get('signal', 'Hold') for data in validated_results.values()]
            
            # 신호 카운트
            signal_count = {}
            for signal in signals:
                signal_count[signal] = signal_count.get(signal, 0) + 1
            
            # 충돌 감지
            buy_signals = signal_count.get('Strong Buy', 0) + signal_count.get('Buy', 0)
            sell_signals = signal_count.get('Strong Sell', 0) + signal_count.get('Sell', 0)
            hold_signals = signal_count.get('Hold', 0)
            
            conflicts = []
            resolution_strategy = 'consensus'
            
            if buy_signals > 0 and sell_signals > 0:
                conflicts.append("매수/매도 신호 충돌")
                resolution_strategy = 'weighted_average'
            
            if abs(buy_signals - sell_signals) <= 1 and hold_signals == 0:
                conflicts.append("강한 신호 간 팽팽한 대립")
                resolution_strategy = 'conservative_hold'
            
            return {
                'conflicts_detected': len(conflicts) > 0,
                'conflict_types': conflicts,
                'signal_distribution': signal_count,
                'resolution_strategy': resolution_strategy,
                'confidence_adjustment': -10 if len(conflicts) > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"신호 충돌 감지 중 오류: {e}")
            return {
                'conflicts_detected': False,
                'conflict_types': [],
                'signal_distribution': {},
                'resolution_strategy': 'hold',
                'confidence_adjustment': 0
            }
    
    async def analyze_with_ai(self, integrated_data: Dict) -> Dict:
        """AI 모델을 사용하여 최종 투자 결정"""
        # 필요할 때만 모델 초기화
        if self.client is None:
            self.client, self.model_name = self.get_model()
        
        if self.client is None:
            logger.warning("AI 모델이 없어 규칙 기반 분석으로 대체합니다.")
            return self.rule_based_final_decision(integrated_data)
        
        try:
            # 최종 결정 프롬프트 사용
            prompt = CONFIG["prompts"]["final_decision"].format(
                position_analysis=json.dumps(integrated_data.get('position_analysis', {}), ensure_ascii=False, indent=2),
                sentiment_analysis=json.dumps(integrated_data.get('sentiment_analysis', {}), ensure_ascii=False, indent=2),
                technical_analysis=json.dumps(integrated_data.get('technical_analysis', {}), ensure_ascii=False, indent=2),
                macro_analysis=json.dumps(integrated_data.get('macro_analysis', {}), ensure_ascii=False, indent=2),
                onchain_analysis=json.dumps(integrated_data.get('onchain_analysis', {}), ensure_ascii=False, indent=2),
                institution_analysis=json.dumps(integrated_data.get('institutional_analysis', {}), ensure_ascii=False, indent=2),
                current_position=json.dumps(integrated_data.get('current_position', {}), ensure_ascii=False, indent=2)
            )
            
            # AI 모델에 질의
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            
            # 🔧 수정: AI 응답 처리 강화
            if not response or not hasattr(response, 'text') or not response.text:
                logger.error("AI 응답이 비어있음")
                return self.rule_based_final_decision(integrated_data)
            
            result_text = response.text.strip()
            logger.info(f"🔍 DEBUG: AI 응답 길이: {len(result_text)}")
            logger.info(f"🔍 DEBUG: AI 응답 첫 100자: {result_text[:100]}")
            
            # JSON 파싱 시도
            try:
                # 1차: 전체 응답이 JSON인지 확인
                result_json = json.loads(result_text)
                logger.info("🔍 DEBUG: 전체 응답이 JSON으로 파싱됨")
            except json.JSONDecodeError:
                # 2차: JSON 블록 찾기
                json_match = re.search(r'\{[\s\S]*\}', result_text)
                if json_match:
                    try:
                        result_json = json.loads(json_match.group(0))
                        logger.info("🔍 DEBUG: JSON 블록 추출 후 파싱 성공")
                    except json.JSONDecodeError as e:
                        logger.error(f"🔍 DEBUG: JSON 블록 파싱 실패: {e}")
                        logger.error(f"🔍 DEBUG: 추출된 JSON: {json_match.group(0)[:200]}")
                        return self.rule_based_final_decision(integrated_data)
                else:
                    logger.error("🔍 DEBUG: AI 응답에서 JSON을 찾을 수 없음")
                    logger.error(f"🔍 DEBUG: 전체 응답: {result_text[:500]}")
                    return self.rule_based_final_decision(integrated_data)
            
            # 🔧 수정: 파싱된 결과 타입 확인
            if not isinstance(result_json, dict):
                logger.error(f"🔍 DEBUG: 파싱된 결과가 딕셔너리가 아님: {type(result_json)}")
                logger.error(f"🔍 DEBUG: 파싱된 결과: {result_json}")
                return self.rule_based_final_decision(integrated_data)
            
            logger.info(f"🔍 DEBUG: AI 결과 키들: {list(result_json.keys())}")
            
            # 🔧 수정: 필수 키 확인 및 기본값 설정
            required_keys = ['final_decision', 'decision_confidence', 'recommended_action']
            for key in required_keys:
                if key not in result_json:
                    logger.warning(f"🔍 DEBUG: 필수 키 누락: {key}")
                    if key == 'final_decision':
                        result_json[key] = 'Hold'
                    elif key == 'decision_confidence':
                        result_json[key] = 50
                    elif key == 'recommended_action':
                        result_json[key] = {'action_type': 'Wait'}
            
            # 분석 메타데이터 추가
            result_json['analysis_metadata'] = {
                'analysis_type': 'ai_based',
                'decision_timestamp': datetime.now(timezone.utc).isoformat(),
                'model_used': self.model_name,
                'integrated_analyses': list(integrated_data.keys()),
                'raw_data': integrated_data
            }
            
            logger.info(f"🔍 DEBUG: 최종 AI 결과 처리 완료 - {result_json.get('final_decision', 'Unknown')}")
            return result_json
            
        except Exception as e:
            logger.error(f"AI 최종 결정 분석 중 오류: {e}")
            logger.error(f"🔍 DEBUG: 오류 발생 지점에서 integrated_data 키들: {list(integrated_data.keys()) if isinstance(integrated_data, dict) else 'Not dict'}")
            return self.rule_based_final_decision(integrated_data)
    
    def rule_based_final_decision(self, integrated_data: Dict) -> Dict:
        """규칙 기반 최종 투자 결정 (AI 모델 없을 때 백업)"""
        try:
            # 1. 분석 결과 검증
            validated_results = self.validate_analysis_results(integrated_data)
            
            # 2. 동적 가중치 계산
            weights = self.calculate_dynamic_weights(validated_results)
            
            # 3. 종합 점수 계산
            composite_analysis = self.calculate_composite_score(validated_results, weights)
            
            # 4. 신호 충돌 감지
            conflict_analysis = self.detect_signal_conflicts(validated_results)
            
            # 5. 현재 포지션 고려
            current_position = integrated_data.get('current_position', {})
            
            # 6. 시장 데이터
            market_data = {
                'current_price': 100000,  # 기본값, 실제로는 현재가 전달받아야 함
                'volatility': 'medium'
            }
            
            # 7. 리스크 관리
            risk_management = self.generate_risk_management(
                composite_analysis['final_decision'],
                composite_analysis['composite_score'],
                current_position,
                market_data
            )
            
            # 8. 신뢰도 조정 (충돌 시 감소)
            final_confidence = max(0, min(100, 
                composite_analysis['weighted_confidence'] + conflict_analysis['confidence_adjustment']
            ))
            
            # 9. 최종 결과 구성
            result = {
                "final_decision": composite_analysis['final_decision'],
                "decision_confidence": round(final_confidence, 1),
                "recommended_action": {
                    "action_type": self._map_decision_to_action(composite_analysis['final_decision'], current_position),
                    "entry_price": market_data['current_price'],
                    "position_size": risk_management['position_size_percent'],
                    "leverage": risk_management['recommended_leverage'],
                    "mandatory_stop_loss": risk_management['stop_loss_price'],
                    "mandatory_take_profit": risk_management['take_profit_price']
                },
                "analysis_weight": {k: round(v, 1) for k, v in weights.items()},
                "composite_score": composite_analysis['composite_score'],
                "signal_distribution": composite_analysis['signal_distribution'],
                "decision_strength": composite_analysis['decision_strength'],
                "risk_assessment": {
                    "overall_risk": self._assess_overall_risk(composite_analysis['composite_score'], final_confidence),
                    "max_loss_potential": risk_management['max_loss_amount'],
                    "profit_potential": risk_management['take_profit_percentage'],
                    "risk_reward_ratio": risk_management['risk_reward_ratio']
                },
                "conflict_analysis": conflict_analysis,
                "execution_plan": {
                    "immediate_action": self._generate_immediate_action(composite_analysis['final_decision']),
                    "sl_tp_mandatory": True if composite_analysis['final_decision'] != 'Hold' else False,
                    "monitoring_points": risk_management['position_monitoring'],
                    "exit_conditions": self._generate_exit_conditions(composite_analysis['final_decision'])
                },
                "market_outlook": {
                    "short_term": "15분-1시간 전망",
                    "medium_term": "1-4시간 전망",
                    "trend_change_probability": self._calculate_trend_change_probability(composite_analysis)
                },
                "individual_analysis_summary": self._summarize_individual_analyses(validated_results),
                "confidence": round(final_confidence, 1),
                "decision_reasoning": self._generate_decision_reasoning(composite_analysis, weights, conflict_analysis),
                "needs_human_review": final_confidence < self.risk_params['min_confidence'] or conflict_analysis['conflicts_detected'],
                "human_review_reason": self._generate_review_reason(final_confidence, conflict_analysis)
            }
            
            # 메타데이터 추가
            result['analysis_metadata'] = {
                'analysis_type': 'rule_based',
                'decision_timestamp': datetime.now(timezone.utc).isoformat(),
                'model_used': 'rule_based_final_decision',
                'integrated_analyses': list(validated_results.keys()),
                'weights_used': weights,
                'raw_data': integrated_data
            }
            
            # 종합 타이밍 메타데이터 추가
            result['timing_summary'] = self._generate_timing_summary(validated_results)
            
            return result
            
        except Exception as e:
            logger.error(f"규칙 기반 최종 결정 중 오류: {e}")
            return self._get_emergency_decision()
    
    def _map_decision_to_action(self, decision: str, current_position: Dict) -> str:
        """결정을 실행 가능한 액션으로 매핑"""
        try:
            has_position = current_position.get('has_position', False)
            position_side = current_position.get('side', 'none')
            
            if decision == 'Strong Buy':
                if not has_position:
                    return "Open Long Position"
                elif position_side == 'short':
                    return "Reverse to Long"
                else:
                    return "Add to Long Position"
                    
            elif decision == 'Buy':
                if not has_position:
                    return "Open Long Position"
                elif position_side == 'short':
                    return "Close Short Position"
                else:
                    return "Hold Long Position"
                    
            elif decision == 'Strong Sell':
                if not has_position:
                    return "Open Short Position"
                elif position_side == 'long':
                    return "Reverse to Short"
                else:
                    return "Add to Short Position"
                    
            elif decision == 'Sell':
                if not has_position:
                    return "Open Short Position"
                elif position_side == 'long':
                    return "Close Long Position"
                else:
                    return "Hold Short Position"
                    
            else:  # Hold
                if has_position:
                    return "Hold Current Position"
                else:
                    return "Wait for Signal"
                    
        except Exception:
            return "Hold Current Position"
    
    def _assess_overall_risk(self, score: float, confidence: float) -> str:
        """전체 리스크 평가"""
        try:
            # 점수 극단성과 신뢰도 고려
            score_risk = abs(score - 50) / 50  # 0~1 (극단적일수록 위험)
            confidence_safety = confidence / 100  # 0~1 (높을수록 안전)
            
            overall_risk_score = (score_risk * 0.6) + ((1 - confidence_safety) * 0.4)
            
            if overall_risk_score > 0.7:
                return "Very High"
            elif overall_risk_score > 0.5:
                return "High"
            elif overall_risk_score > 0.3:
                return "Medium"
            else:
                return "Low"
                
        except Exception:
            return "Medium"
    
    def _generate_immediate_action(self, decision: str) -> str:
        """즉시 실행할 행동 생성"""
        action_map = {
            'Strong Buy': "즉시 롱 포지션 진입 또는 확대",
            'Buy': "적정 시점에 롱 포지션 진입",
            'Hold': "현재 상태 유지 및 관찰",
            'Sell': "적정 시점에 숏 포지션 진입 또는 롱 청산",
            'Strong Sell': "즉시 숏 포지션 진입 또는 롱 전량 청산"
        }
        return action_map.get(decision, "관찰 지속")
    
    def _generate_exit_conditions(self, decision: str) -> List[str]:
        """청산 조건 생성"""
        if decision in ['Strong Buy', 'Buy']:
            return [
                "스톱로스 가격 터치 시 즉시 청산",
                "테이크프로핏 목표가 도달 시 일부 또는 전량 청산",
                "기술적 신호 반전 시 청산 고려",
                "시장 심리 급변 시 재평가"
            ]
        elif decision in ['Strong Sell', 'Sell']:
            return [
                "스톱로스 가격 터치 시 즉시 청산",
                "테이크프로핏 목표가 도달 시 일부 또는 전량 청산",
                "지지선 강력 지지 시 청산 고려",
                "거시경제 호재 발생 시 재평가"
            ]
        else:
            return [
                "명확한 방향성 신호 등장 시 포지션 검토",
                "15분마다 신호 재평가"
            ]
    
    def _calculate_trend_change_probability(self, composite_analysis: Dict) -> str:
        """추세 전환 가능성 계산"""
        try:
            score = composite_analysis['composite_score']
            strength = composite_analysis['decision_strength']
            
            # 중립 구간에서는 전환 가능성 높음
            if 40 <= score <= 60:
                return "High (중립 구간)"
            
            # 극단 구간에서 강한 신호면 전환 가능성 낮음
            if strength in ['Very Strong', 'Strong'] and (score > 75 or score < 25):
                return "Low (강한 추세)"
            
            # 그 외는 중간
            return "Medium"
            
        except Exception:
            return "Medium"
    
    def _summarize_individual_analyses(self, validated_results: Dict) -> Dict:
        """개별 분석 요약"""
        summary = {}
        
        for analysis_type, data in validated_results.items():
            summary[analysis_type] = {
                'signal': data.get('signal', 'Hold'),
                'confidence': data.get('confidence', 50),
                'status': 'Success' if 'error' not in data else 'Failed',
                'key_point': self._extract_key_point(analysis_type, data)
            }
        
        return summary
    
    def _extract_key_point(self, analysis_type: str, data: Dict) -> str:
        """각 분석의 핵심 포인트 추출"""
        try:
            result = data.get('result', {})
            
            if analysis_type == 'position_analysis':
                return f"포지션 상태: {data.get('signal', 'N/A')}"
            elif analysis_type == 'technical_analysis':
                return f"기술적 신호: {data.get('signal', 'N/A')}"
            elif analysis_type == 'sentiment_analysis':
                sentiment_score = result.get('market_sentiment_score', 50)
                return f"시장 심리: {sentiment_score}점"
            elif analysis_type == 'macro_analysis':
                macro_score = result.get('macro_environment_score', 50)
                return f"거시경제: {macro_score}점"
            elif analysis_type == 'onchain_analysis':
                onchain_score = result.get('onchain_health_score', 50)
                return f"온체인: {onchain_score}점"
            elif analysis_type == 'institutional_analysis':
                institutional_score = result.get('institutional_flow_score', 50)
                return f"기관투자: {institutional_score}점"
            else:
                return f"신호: {data.get('signal', 'N/A')}"
                
        except Exception:
            return "분석 데이터 없음"
    
    def _generate_decision_reasoning(self, composite_analysis: Dict, weights: Dict, conflict_analysis: Dict) -> str:
        """결정 이유 생성"""
        try:
            decision = composite_analysis['final_decision']
            score = composite_analysis['composite_score']
            strength = composite_analysis['decision_strength']
            
            reasoning = f"종합 점수 {score:.1f}점을 기반으로 '{decision}' 결정. "
            reasoning += f"신호 강도: {strength}. "
            
            # 주요 가중치 언급
            max_weight_analysis = max(weights, key=weights.get)
            max_weight = weights[max_weight_analysis]
            reasoning += f"주요 근거: {max_weight_analysis} ({max_weight:.1f}% 가중치). "
            
            # 충돌 상황 언급
            if conflict_analysis['conflicts_detected']:
                reasoning += f"신호 충돌 감지: {', '.join(conflict_analysis['conflict_types'])}. "
                reasoning += f"해결 전략: {conflict_analysis['resolution_strategy']}."
            
            return reasoning
            
        except Exception:
            return "종합 분석을 통한 결정"
    
    def _generate_review_reason(self, confidence: float, conflict_analysis: Dict) -> str:
        """인간 검토 필요 이유"""
        reasons = []
        
        if confidence < self.risk_params['min_confidence']:
            reasons.append(f"낮은 신뢰도 ({confidence:.1f}%)")
        
        if conflict_analysis['conflicts_detected']:
            reasons.append("분석 간 신호 충돌")
        
        if len(reasons) == 0:
            return None
        
        return "; ".join(reasons)
    
    def _generate_timing_summary(self, validated_results: Dict) -> Dict:
        """모든 분석의 타이밍 정보 종합"""
        try:
            summary = {
                'total_analyses': len(validated_results),
                'successful_analyses': 0,
                'failed_analyses': 0,
                'skipped_analyses': 0,
                'disabled_analyses': 0,
                'cached_analyses': 0,
                'real_time_analyses': 0,
                'oldest_data_age_minutes': 0,
                'newest_data_age_minutes': float('inf'),
                'analysis_freshness': {},
                'data_quality_summary': {},
                'timing_details': {}
            }
            
            for analysis_type, data in validated_results.items():
                timing_meta = data.get('timing_metadata', {})
                status = timing_meta.get('status', 'unknown')
                
                # 상태별 카운트
                if status == 'success':
                    summary['successful_analyses'] += 1
                elif status == 'failed':
                    summary['failed_analyses'] += 1
                elif status == 'skipped':
                    summary['skipped_analyses'] += 1
                elif status == 'disabled':
                    summary['disabled_analyses'] += 1
                
                # 캐시 vs 실시간 분석
                if 'cached_analysis_time' in timing_meta:
                    summary['cached_analyses'] += 1
                else:
                    summary['real_time_analyses'] += 1
                
                # 데이터 신선도 분석
                data_freshness = timing_meta.get('data_freshness', {})
                if data_freshness:
                    ages = [age for age in data_freshness.values() if isinstance(age, (int, float))]
                    if ages:
                        max_age = max(ages)
                        min_age = min(ages)
                        summary['oldest_data_age_minutes'] = max(summary['oldest_data_age_minutes'], max_age)
                        summary['newest_data_age_minutes'] = min(summary['newest_data_age_minutes'], min_age)
                
                # 분석별 신선도 등급
                if data_freshness:
                    avg_age = sum(age for age in data_freshness.values() if isinstance(age, (int, float))) / len([age for age in data_freshness.values() if isinstance(age, (int, float))])
                    if avg_age <= 30:
                        freshness_grade = 'fresh'
                    elif avg_age <= 120:
                        freshness_grade = 'moderate'
                    else:
                        freshness_grade = 'stale'
                    summary['analysis_freshness'][analysis_type] = freshness_grade
                
                # 데이터 품질 요약
                raw_data_status = timing_meta.get('raw_data_status', {})
                if raw_data_status:
                    available_sources = raw_data_status.get('available_sources', 0)
                    total_sources = len([k for k, v in raw_data_status.items() if k.startswith('has_')])
                    if total_sources > 0:
                        quality_score = (available_sources / total_sources) * 100
                        summary['data_quality_summary'][analysis_type] = {
                            'quality_score': round(quality_score, 1),
                            'available_sources': available_sources,
                            'total_sources': total_sources
                        }
                
                # 상세 타이밍 정보
                summary['timing_details'][analysis_type] = {
                    'status': status,
                    'timestamp': timing_meta.get('analysis_timestamp', timing_meta.get('cached_analysis_time')),
                    'is_cached': 'cached_analysis_time' in timing_meta,
                    'model_used': timing_meta.get('model_used'),
                    'error_reason': timing_meta.get('error_reason')
                }
            
            # 신선도 처리 (무한대 처리)
            if summary['newest_data_age_minutes'] == float('inf'):
                summary['newest_data_age_minutes'] = 0
            
            # 전체 데이터 품질 등급
            successful_rate = (summary['successful_analyses'] / summary['total_analyses']) * 100 if summary['total_analyses'] > 0 else 0
            if successful_rate >= 80:
                summary['overall_quality'] = 'excellent'
            elif successful_rate >= 60:
                summary['overall_quality'] = 'good'
            elif successful_rate >= 40:
                summary['overall_quality'] = 'moderate'
            else:
                summary['overall_quality'] = 'poor'
            
            # 캐시 효율성
            cache_efficiency = (summary['cached_analyses'] / summary['total_analyses']) * 100 if summary['total_analyses'] > 0 else 0
            summary['cache_efficiency_percent'] = round(cache_efficiency, 1)
            
            return summary
            
        except Exception as e:
            logger.error(f"타이밍 요약 생성 중 오류: {e}")
            return {
                'total_analyses': len(validated_results) if validated_results else 0,
                'error': f'타이밍 요약 생성 실패: {str(e)}',
                'generation_time': datetime.now(timezone.utc).isoformat()
            }
    
    def _get_emergency_decision(self) -> Dict:
        """긴급 상황 기본 결정"""
        return {
            "final_decision": "Hold",
            "decision_confidence": 0,
            "recommended_action": {
                "action_type": "Wait for Signal",
                "entry_price": None,
                "position_size": 0,
                "leverage": 1,
                "mandatory_stop_loss": None,
                "mandatory_take_profit": None
            },
            "error": "최종 결정 생성 중 오류 발생",
            "needs_human_review": True,
            "human_review_reason": "시스템 오류로 인한 긴급 상황"
        }
    
    def check_analysis_data_availability(self, all_analysis_results: Dict) -> Tuple[bool, Dict]:
        """분석 데이터 사용 가능성 확인 - 포지션 유무에 따른 조건부 로직 추가"""
        try:
            logger.info(f"🔍 DEBUG: check_analysis_data_availability 시작")
            logger.info(f"🔍 DEBUG: all_analysis_results type: {type(all_analysis_results)}")
            logger.info(f"🔍 DEBUG: all_analysis_results is None: {all_analysis_results is None}")
            logger.info(f"🔍 DEBUG: all_analysis_results length: {len(all_analysis_results) if all_analysis_results else 'N/A'}")
            
            # all_analysis_results가 None이거나 비어있는 경우 체크
            if not all_analysis_results or not isinstance(all_analysis_results, dict):
                logger.error("분석 결과가 None이거나 딕셔너리가 아님")
                return False, {
                    'analysis_status': {},
                    'failed_due_to_data': 0,
                    'failed_due_to_disabled': 0,
                    'total_core_analyses': 0,
                    'core_success_count': 0,
                    'essential_success_count': 0,
                    'critical_failures': ['all_analysis_results_is_none'],
                    'data_availability_rate': 0,
                    'decision_viability': 'not_viable',
                    'failure_reasons': ['분석 결과가 None 또는 빈 딕셔너리']
                }
            
            # 🔧 포지션 유무 확인
            current_position = all_analysis_results.get('current_position', {})
            has_position = current_position.get('has_position', False)
            
            logger.info(f"🔍 DEBUG: 현재 포지션 상태: {has_position}")
            
            # 🔧 포지션 없으면 position_analysis 기본값 설정
            if not has_position and ('position_analysis' not in all_analysis_results or 
                                not isinstance(all_analysis_results.get('position_analysis'), dict)):
                logger.info("🔍 DEBUG: 포지션 없음 - position_analysis 기본값 설정")
                all_analysis_results['position_analysis'] = {
                    'success': True,
                    'result': {
                        'recommended_action': 'Wait',
                        'position_status': 'No Position',
                        'risk_level': 'None',
                        'confidence': 100
                    },
                    'analysis_type': 'position_analysis',
                    'note': 'No position - default analysis'
                }
            
            # 🔧 변수들 초기화
            analysis_status = {}
            failed_due_to_data = 0
            failed_due_to_disabled = 0
            total_analyses = 0
            critical_failures = []
            
            # 핵심 분석들 (최소 2개는 성공해야 함)
            core_analyses = ['sentiment_analysis', 'technical_analysis', 'macro_analysis', 'onchain_analysis', 'institutional_analysis']
            
            # 🔧 포지션 유무에 따른 필수 분석 결정
            if has_position:
                essential_analyses = ['technical_analysis', 'position_analysis']
                logger.info("🔍 DEBUG: 포지션 있음 - position_analysis 필수")
            else:
                essential_analyses = ['technical_analysis']
                logger.info("🔍 DEBUG: 포지션 없음 - position_analysis 필수 아님")
            
            # 🔍 디버깅: 분석 대상 목록
            logger.info(f"🔍 DEBUG: 핵심 분석 목록: {core_analyses}")
            logger.info(f"🔍 DEBUG: 필수 분석 목록: {essential_analyses}")
            
            # 각 분석 검사
            for analysis_type in core_analyses + essential_analyses:
                logger.info(f"🔍 DEBUG: {analysis_type} 검사 시작")
                
                if analysis_type in all_analysis_results:
                    total_analyses += 1
                    result = all_analysis_results[analysis_type]
                    
                    # 🔍 디버깅: 개별 분석 결과 상세 확인
                    logger.info(f"🔍 DEBUG: {analysis_type} 결과 타입: {type(result)}")
                    logger.info(f"🔍 DEBUG: {analysis_type} 결과가 None: {result is None}")
                    
                    if result is None:
                        logger.warning(f"🔍 DEBUG: {analysis_type} 결과가 None")
                        analysis_status[analysis_type] = 'failed_none_result'
                        failed_due_to_data += 1
                        if analysis_type in essential_analyses:
                            critical_failures.append(f"{analysis_type}: 결과가 None")
                        continue
                    
                    # 캐시된 분석 결과인 경우 analysis_result 내부 확인
                    if isinstance(result, dict) and 'analysis_result' in result:
                        actual_result = result['analysis_result']
                        logger.info(f"🔍 DEBUG: {analysis_type} 캐시된 결과 사용, analysis_result 타입: {type(actual_result)}")
                    else:
                        actual_result = result
                        logger.info(f"🔍 DEBUG: {analysis_type} 직접 결과 사용")
                    
                    # actual_result가 딕셔너리가 아닌 경우 체크
                    if not isinstance(actual_result, dict):
                        logger.warning(f"🔍 DEBUG: {analysis_type} actual_result가 딕셔너리가 아님: {type(actual_result)}")
                        analysis_status[analysis_type] = 'failed_invalid_format'
                        failed_due_to_data += 1
                        if analysis_type in essential_analyses:
                            critical_failures.append(f"{analysis_type}: 잘못된 결과 형식")
                        continue
                    
                    # 성공 여부 확인
                    success = actual_result.get('success', False)
                    logger.info(f"🔍 DEBUG: {analysis_type} success: {success}")
                    
                    if not success:
                        # 실패 원인 분석
                        skip_reason = actual_result.get('skip_reason', '')
                        error_msg = actual_result.get('error', '')
                        
                        logger.warning(f"🔍 DEBUG: {analysis_type} 실패 - skip_reason: {skip_reason}, error: {error_msg}")
                        
                        if skip_reason in ['insufficient_raw_data', 'no_valid_data', 'insufficient_data']:
                            failed_due_to_data += 1
                            analysis_status[analysis_type] = 'failed_data_insufficient'
                            if analysis_type in essential_analyses:
                                critical_failures.append(f"{analysis_type}: 데이터 부족")
                        elif skip_reason == 'analyzer_disabled':
                            failed_due_to_disabled += 1
                            analysis_status[analysis_type] = 'failed_disabled'
                            if analysis_type in essential_analyses:
                                critical_failures.append(f"{analysis_type}: 분석기 비활성화")
                        else:
                            analysis_status[analysis_type] = 'failed_other'
                            if analysis_type in essential_analyses:
                                critical_failures.append(f"{analysis_type}: {error_msg}")
                    else:
                        analysis_status[analysis_type] = 'success'
                        logger.info(f"🔍 DEBUG: {analysis_type} 성공으로 분류")
                else:
                    # 분석 결과 자체가 없음
                    logger.warning(f"🔍 DEBUG: {analysis_type} 키가 all_analysis_results에 없음")
                    if analysis_type in essential_analyses:
                        critical_failures.append(f"{analysis_type}: 결과 없음")
                    analysis_status[analysis_type] = 'missing'
            
            # 데이터 충분성 판단 로직
            core_success_count = sum(1 for analysis_type in core_analyses 
                                if analysis_status.get(analysis_type) == 'success')
            essential_success_count = sum(1 for analysis_type in essential_analyses 
                                        if analysis_status.get(analysis_type) == 'success')
            
            # 🔍 디버깅: 성공 카운트
            logger.info(f"🔍 DEBUG: 핵심 분석 성공 카운트: {core_success_count}/{len(core_analyses)}")
            logger.info(f"🔍 DEBUG: 필수 분석 성공 카운트: {essential_success_count}/{len(essential_analyses)}")
            logger.info(f"🔍 DEBUG: 데이터 부족 실패: {failed_due_to_data}")
            logger.info(f"🔍 DEBUG: 치명적 실패: {critical_failures}")
            
            # 판단 기준
            data_sufficient = (
                len(critical_failures) == 0 and  # 필수 분석 모두 성공
                core_success_count >= 2 and      # 핵심 분석 최소 2개 성공
                failed_due_to_data < 4           # 데이터 부족 실패 4개 미만
            )
            
            logger.info(f"🔍 DEBUG: 최종 데이터 충분성 판단: {data_sufficient}")
            
            # 상세 정보
            availability_info = {
                'analysis_status': analysis_status,
                'failed_due_to_data': failed_due_to_data,
                'failed_due_to_disabled': failed_due_to_disabled,
                'total_core_analyses': len(core_analyses),
                'core_success_count': core_success_count,
                'essential_success_count': essential_success_count,
                'critical_failures': critical_failures,
                'data_availability_rate': (core_success_count / len(core_analyses) * 100) if core_analyses else 0,
                'decision_viability': 'viable' if data_sufficient else 'not_viable',
                'failure_reasons': []
            }
            
            # 실패 이유 상세 분석
            if not data_sufficient:
                if critical_failures:
                    availability_info['failure_reasons'].append(f"필수 분석 실패: {', '.join(critical_failures)}")
                if core_success_count < 2:
                    availability_info['failure_reasons'].append(f"핵심 분석 부족 (성공: {core_success_count}/5)")
                if failed_due_to_data >= 4:
                    availability_info['failure_reasons'].append(f"광범위한 데이터 부족 ({failed_due_to_data}개 분석)")
            
            return data_sufficient, availability_info
            
        except Exception as e:
            logger.error(f"분석 데이터 가용성 확인 중 오류: {e}")
            logger.error(f"🔍 DEBUG: 에러 발생, all_analysis_results: {all_analysis_results}")
            return False, {
                'error': str(e),
                'decision_viability': 'not_viable',
                'failure_reasons': [f'가용성 확인 오류: {str(e)}']
            }







    async def make_final_decision(self, all_analysis_results: Dict) -> Dict:
        """최종 투자 결정 메인 함수 - 디버깅 로그 추가"""
        try:
            logger.info("최종 투자 결정 분석 시작")
            
            # 🔍 디버깅: 입력 데이터 상세 확인
            logger.info(f"🔍 DEBUG: 전달받은 분석 결과 키들: {list(all_analysis_results.keys()) if all_analysis_results else 'None'}")
            
            if all_analysis_results:
                for key, value in all_analysis_results.items():
                    if value is None:
                        logger.warning(f"🔍 DEBUG: {key} = None")
                    elif isinstance(value, dict):
                        logger.info(f"🔍 DEBUG: {key} = dict with keys: {list(value.keys())}")
                        if 'success' in value:
                            logger.info(f"🔍 DEBUG: {key}.success = {value.get('success')}")
                        if 'error' in value:
                            logger.warning(f"🔍 DEBUG: {key}.error = {value.get('error')}")
                    else:
                        logger.info(f"🔍 DEBUG: {key} = {type(value)} (not dict)")
            
            # 데이터 사용 가능성 확인
            data_sufficient, availability_info = self.check_analysis_data_availability(all_analysis_results)
            
            # 🔍 디버깅: 가용성 확인 결과 상세 로그
            logger.info(f"🔍 DEBUG: 데이터 충분성: {data_sufficient}")
            logger.info(f"🔍 DEBUG: 가용성 정보: {availability_info}")
            
            if not data_sufficient:
                failure_summary = "; ".join(availability_info['failure_reasons'])
                logger.warning(f"최종 결정: 중단 - {failure_summary}")
                
                return {
                    "success": False,
                    "error": f"투자 결정 중단: {failure_summary}",
                    "analysis_type": "final_decision",
                    "skip_reason": "insufficient_analysis_data",
                    "data_availability": availability_info,
                    "debug_info": {
                        "input_keys": list(all_analysis_results.keys()) if all_analysis_results else [],
                        "input_types": {k: str(type(v)) for k, v in all_analysis_results.items()} if all_analysis_results else {}
                    },
                    "safety_protocol": {
                        "triggered": True,
                        "reason": "minimum_data_requirements_not_met",
                        "recommended_action": "wait_for_data_recovery",
                        "retry_conditions": [
                            "필수 분석 (기술적 분석, 포지션 분석) 복구",
                            f"핵심 분석 최소 2개 이상 성공 (현재: {availability_info['core_success_count']}/5)",
                            "데이터 소스 복구 또는 에러 카운트 리셋"
                        ]
                    }
                }
            
            # 1. 모든 분석 결과 통합 (데이터가 충분한 경우에만)
            integrated_data = {
                'position_analysis': all_analysis_results.get('position_analysis', {}),
                'technical_analysis': all_analysis_results.get('technical_analysis', {}),
                'sentiment_analysis': all_analysis_results.get('sentiment_analysis', {}),
                'macro_analysis': all_analysis_results.get('macro_analysis', {}),
                'onchain_analysis': all_analysis_results.get('onchain_analysis', {}),
                'institutional_analysis': all_analysis_results.get('institutional_analysis', {}),
                'current_position': all_analysis_results.get('current_position', {}),
                'integration_timestamp': datetime.now(timezone.utc).isoformat(),
                'data_availability': availability_info
            }
            
            # 🔍 디버깅: 통합 데이터 확인
            logger.info(f"🔍 DEBUG: 통합된 데이터 키들: {list(integrated_data.keys())}")
            
            # 2. AI 또는 규칙 기반 최종 분석
            final_result = await self.analyze_with_ai(integrated_data)
            
            logger.info(f"최종 투자 결정 완료: {final_result.get('final_decision', 'Unknown')}")
            
            return {
                "success": True,
                "result": final_result,
                "analysis_type": "final_decision",
                "integration_summary": {
                    "total_analyses": len([k for k in integrated_data.keys() if k not in ['integration_timestamp', 'data_availability']]),
                    "successful_analyses": len([k for k, v in integrated_data.items() if v.get('success', False)]),
                    "integration_method": "weighted_composite_scoring",
                    "decision_framework": "multi_factor_analysis",
                    "data_availability_rate": availability_info['data_availability_rate']
                }
            }
            
        except Exception as e:
            logger.error(f"최종 투자 결정 중 오류: {e}")
            logger.error(f"🔍 DEBUG: 에러 발생 시점의 all_analysis_results: {all_analysis_results}")
            return {
                "success": False,
                "error": f"최종 결정 중 오류 발생: {str(e)}",
                "result": self._get_emergency_decision(),
                "analysis_type": "final_decision"
            }

# 전역 최종 결정 인스턴스
_global_decision_maker: Optional[FinalDecisionMaker] = None

def get_final_decision_maker() -> FinalDecisionMaker:
    """전역 최종 결정 인스턴스 반환"""
    global _global_decision_maker
    if _global_decision_maker is None:
        _global_decision_maker = FinalDecisionMaker()
    return _global_decision_maker

# 외부에서 사용할 함수
async def make_final_investment_decision(all_analysis_results: Dict) -> Dict:
    """최종 투자 결정을 내리는 함수"""
    decision_maker = get_final_decision_maker()
    return await decision_maker.make_final_decision(all_analysis_results)

# 🔧 기존 외부 함수에 스케줄러 연동 버전 추가
async def make_final_investment_decision_with_scheduler(scheduler) -> Dict:
    """스케줄러 연동 최종 투자 결정 함수"""
    decision_maker = get_final_decision_maker()
    return await decision_maker.make_final_decision_with_scheduler(scheduler)

def debug_final_decision_mapping(scheduler) -> Dict:
    """최종 결정 매핑 디버깅 함수"""
    decision_maker = get_final_decision_maker()
    return decision_maker.debug_scheduler_data_mapping(scheduler)


# 테스트용 코드
if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("🔍 최종 투자 결정 시스템 테스트 시작...")
        
        # 테스트용 분석 결과 (더미 데이터)
        test_analysis_results = {
            'position_analysis': {
                'success': True,
                'result': {
                    'recommended_action': 'Buy',
                    'confidence': 75
                }
            },
            'technical_analysis': {
                'success': True,
                'result': {
                    'overall_signal': 'Buy',
                    'confidence': 80
                }
            },
            'sentiment_analysis': {
                'success': True,
                'result': {
                    'market_sentiment_score': 65,
                    'investment_recommendation': 'Hold',
                    'confidence': 70
                }
            },
            'macro_analysis': {
                'success': True,
                'result': {
                    'macro_environment_score': 55,
                    'btc_recommendation': 'Hold',
                    'confidence': 65
                }
            },
            'onchain_analysis': {
                'success': True,
                'result': {
                    'onchain_health_score': 72,
                    'investment_signal': 'Buy',
                    'confidence': 78
                }
            },
            'institutional_analysis': {
                'success': True,
                'result': {
                    'institutional_flow_score': 68,
                    'investment_signal': 'Institutional Buy',
                    'confidence': 72
                }
            },
            'current_position': {
                'has_position': False,
                'side': 'none'
            }
        }
        
        result = await make_final_investment_decision(test_analysis_results)
        
        if result['success']:
            print("✅ 최종 투자 결정 성공!")
            decision = result['result']
            print(f"최종 결정: {decision.get('final_decision', 'Unknown')}")
            print(f"신뢰도: {decision.get('decision_confidence', 0):.1f}%")
            print(f"권장 액션: {decision.get('recommended_action', {}).get('action_type', 'N/A')}")
            print(f"포지션 크기: {decision.get('recommended_action', {}).get('position_size', 0):.1f}%")
            print(f"인간 검토 필요: {decision.get('needs_human_review', False)}")
        else:
            print("❌ 최종 투자 결정 실패:")
            print(result['error'])
        
        print("\n" + "="*50)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())