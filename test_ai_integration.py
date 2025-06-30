"""
AI 거래 시스템 통합 테스트 스크립트
실제 거래 없이 AI 분석 시스템의 모든 구성요소를 테스트
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

# 프로젝트 루트 디렉토리 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 테스트할 모듈들
from docs.investment_ai.ai_trading_integration import AITradingIntegration
from docs.investment_ai.analyzers.position_analyzer import analyze_position_status
from docs.investment_ai.analyzers.sentiment_analyzer import analyze_market_sentiment
from docs.investment_ai.analyzers.technical_analyzer import analyze_technical_indicators
from docs.investment_ai.analyzers.macro_analyzer import analyze_macro_economics
from docs.investment_ai.analyzers.onchain_analyzer import analyze_onchain_data
from docs.investment_ai.analyzers.institution_analyzer import analyze_institutional_flow
from docs.investment_ai.final_decisionmaker import make_final_investment_decision

class AIIntegrationTester:
    """AI 통합 시스템 테스터"""
    
    def __init__(self):
        self.test_config = {
            'symbol': 'BTCUSDT',
            'leverage': 5,
            'usdt_amount': 0.3,
            'set_timevalue': '15m',
            'take_profit': 400,
            'stop_loss': 400
        }
        self.test_results = {}
        
    async def test_individual_analyzers(self):
        """개별 분석기들 테스트"""
        print("=== 개별 분석기 테스트 시작 ===")
        
        analyzers = [
            ("Position Analyzer", analyze_position_status),
            ("Sentiment Analyzer", analyze_market_sentiment),
            ("Technical Analyzer", lambda: analyze_technical_indicators('BTCUSDT', '15m', 300)),
            ("Macro Analyzer", analyze_macro_economics),
            ("Onchain Analyzer", analyze_onchain_data),
            ("Institution Analyzer", analyze_institutional_flow)
        ]
        
        results = {}
        
        for name, analyzer_func in analyzers:
            try:
                print(f"\n{name} 테스트 중...")
                start_time = datetime.now()
                
                if name == "Technical Analyzer":
                    result = await analyzer_func()
                else:
                    result = await analyzer_func()
                
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                
                success = result.get('success', False)
                
                results[name] = {
                    'success': success,
                    'duration': duration,
                    'error': result.get('error') if not success else None,
                    'result_keys': list(result.get('result', {}).keys()) if success else []
                }
                
                status = "✅ 성공" if success else "❌ 실패"
                print(f"{name}: {status} ({duration:.2f}초)")
                
                if not success:
                    print(f"  오류: {result.get('error', 'Unknown error')}")
                else:
                    print(f"  결과 키: {results[name]['result_keys']}")
                
            except Exception as e:
                results[name] = {
                    'success': False,
                    'duration': 0,
                    'error': str(e),
                    'result_keys': []
                }
                print(f"{name}: ❌ 예외 발생 - {str(e)}")
        
        self.test_results['individual_analyzers'] = results
        return results
    
    async def test_final_decision_maker(self):
        """최종 결정 AI 테스트"""
        print("\n=== 최종 결정 AI 테스트 시작 ===")
        
        try:
            # 더미 분석 결과 생성
            dummy_results = {
                'position_analysis': {
                    'success': True,
                    'result': {
                        'position_status': 'None',
                        'recommended_actions': [{'action': 'Hold', 'reason': 'Test'}],
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
            
            start_time = datetime.now()
            result = await make_final_investment_decision(dummy_results)
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            success = result.get('success', False)
            
            self.test_results['final_decision'] = {
                'success': success,
                'duration': duration,
                'error': result.get('error') if not success else None,
                'decision': result.get('result', {}).get('final_decision') if success else None,
                'confidence': result.get('result', {}).get('decision_confidence') if success else 0
            }
            
            status = "✅ 성공" if success else "❌ 실패"
            print(f"최종 결정 AI: {status} ({duration:.2f}초)")
            
            if success:
                final_result = result.get('result', {})
                decision = final_result.get('final_decision', 'Unknown')
                confidence = final_result.get('decision_confidence', 0)
                print(f"  결정: {decision} (신뢰도: {confidence}%)")
            else:
                print(f"  오류: {result.get('error', 'Unknown error')}")
            
            return result
            
        except Exception as e:
            self.test_results['final_decision'] = {
                'success': False,
                'duration': 0,
                'error': str(e),
                'decision': None,
                'confidence': 0
            }
            print(f"최종 결정 AI: ❌ 예외 발생 - {str(e)}")
            return {'success': False, 'error': str(e)}
    
    async def test_ai_integration(self):
        """AI 통합 시스템 테스트"""
        print("\n=== AI 통합 시스템 테스트 시작 ===")
        
        try:
            integration = AITradingIntegration(self.test_config)
            
            # 현재 포지션 데이터 테스트
            print("포지션 데이터 수집 테스트...")
            position_data = await integration.get_current_position_data()
            print(f"  포지션 상태: {position_data.get('has_position', 'Unknown')}")
            
            # 전체 분석 테스트
            print("전체 AI 분석 테스트...")
            start_time = datetime.now()
            all_results = await integration.run_all_analyses()
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            # AI 결정 도출 테스트
            print("AI 결정 도출 테스트...")
            ai_decision = await integration.get_ai_decision()
            
            success = ai_decision.get('success', False)
            
            self.test_results['ai_integration'] = {
                'success': success,
                'duration': duration,
                'error': ai_decision.get('error') if not success else None,
                'analyses_completed': len([k for k, v in all_results.items() if isinstance(v, dict) and v.get('success', False)]),
                'total_analyses': len([k for k in all_results.keys() if k != 'current_position'])
            }
            
            status = "✅ 성공" if success else "❌ 실패"
            print(f"AI 통합 시스템: {status} ({duration:.2f}초)")
            
            if success:
                analyses_ok = self.test_results['ai_integration']['analyses_completed']
                total_analyses = self.test_results['ai_integration']['total_analyses']
                print(f"  완료된 분석: {analyses_ok}/{total_analyses}")
            
            # 결정 해석 테스트
            print("AI 결정 해석 테스트...")
            interpreted = integration.interpret_ai_decision(ai_decision)
            print(f"  해석된 액션: {interpreted.get('action', 'Unknown')}")
            print(f"  신뢰도: {interpreted.get('confidence', 0)}%")
            
            self.test_results['ai_integration']['interpreted_action'] = interpreted.get('action')
            self.test_results['ai_integration']['interpreted_confidence'] = interpreted.get('confidence', 0)
            
            return ai_decision
            
        except Exception as e:
            self.test_results['ai_integration'] = {
                'success': False,
                'duration': 0,
                'error': str(e),
                'analyses_completed': 0,
                'total_analyses': 6
            }
            print(f"AI 통합 시스템: ❌ 예외 발생 - {str(e)}")
            return {'success': False, 'error': str(e)}
    
    async def test_full_cycle(self):
        """완전한 AI 트레이딩 사이클 테스트 (실제 거래 제외)"""
        print("\n=== 완전한 AI 트레이딩 사이클 테스트 ===")
        
        try:
            integration = AITradingIntegration(self.test_config)
            
            start_time = datetime.now()
            
            # 1. AI 결정 도출
            ai_decision = await integration.get_ai_decision()
            
            # 2. 결정 해석
            interpreted_decision = integration.interpret_ai_decision(ai_decision)
            
            # 3. 실행 시뮬레이션 (실제 거래 X)
            print("거래 실행 시뮬레이션...")
            action = interpreted_decision.get('action', 'wait')
            confidence = interpreted_decision.get('confidence', 0)
            
            if action in ['open_long', 'open_short', 'reverse_to_long', 'reverse_to_short']:
                print(f"  시뮬레이션: {action} 포지션 진입")
                print(f"  신뢰도: {confidence}%")
                print(f"  포지션 크기: {interpreted_decision.get('position_size', 0)}%")
                print(f"  레버리지: {interpreted_decision.get('leverage', 1)}x")
            elif action == 'close_position':
                print(f"  시뮬레이션: 포지션 종료")
            else:
                print(f"  시뮬레이션: {action} (거래 없음)")
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            self.test_results['full_cycle'] = {
                'success': True,
                'duration': duration,
                'action': action,
                'confidence': confidence,
                'ai_decision_success': ai_decision.get('success', False)
            }
            
            print(f"완전한 사이클: ✅ 성공 ({duration:.2f}초)")
            print(f"  최종 액션: {action}")
            print(f"  신뢰도: {confidence}%")
            
            return True
            
        except Exception as e:
            self.test_results['full_cycle'] = {
                'success': False,
                'duration': 0,
                'error': str(e),
                'action': None,
                'confidence': 0
            }
            print(f"완전한 사이클: ❌ 예외 발생 - {str(e)}")
            return False
    
    def print_summary(self):
        """테스트 결과 요약 출력"""
        print("\n" + "="*50)
        print("AI 통합 시스템 테스트 결과 요약")
        print("="*50)
        
        # 개별 분석기 요약
        if 'individual_analyzers' in self.test_results:
            analyzers = self.test_results['individual_analyzers']
            successful = sum(1 for result in analyzers.values() if result['success'])
            total = len(analyzers)
            print(f"\n📊 개별 분석기: {successful}/{total} 성공")
            
            for name, result in analyzers.items():
                status = "✅" if result['success'] else "❌"
                print(f"  {status} {name}: {result['duration']:.2f}초")
        
        # 최종 결정 AI 요약
        if 'final_decision' in self.test_results:
            final = self.test_results['final_decision']
            status = "✅" if final['success'] else "❌"
            print(f"\n🧠 최종 결정 AI: {status}")
            if final['success']:
                print(f"  결정: {final['decision']} (신뢰도: {final['confidence']}%)")
            print(f"  소요시간: {final['duration']:.2f}초")
        
        # AI 통합 시스템 요약
        if 'ai_integration' in self.test_results:
            integration = self.test_results['ai_integration']
            status = "✅" if integration['success'] else "❌"
            print(f"\n🔗 AI 통합 시스템: {status}")
            print(f"  분석 완료: {integration['analyses_completed']}/{integration['total_analyses']}")
            print(f"  소요시간: {integration['duration']:.2f}초")
            if integration['success']:
                print(f"  해석된 액션: {integration.get('interpreted_action', 'N/A')}")
        
        # 완전한 사이클 요약
        if 'full_cycle' in self.test_results:
            cycle = self.test_results['full_cycle']
            status = "✅" if cycle['success'] else "❌"
            print(f"\n🔄 완전한 사이클: {status}")
            print(f"  소요시간: {cycle['duration']:.2f}초")
            if cycle['success']:
                print(f"  최종 액션: {cycle['action']}")
                print(f"  신뢰도: {cycle['confidence']}%")
        
        # 전체 평가
        all_tests = [
            self.test_results.get('individual_analyzers', {}),
            self.test_results.get('final_decision', {}),
            self.test_results.get('ai_integration', {}),
            self.test_results.get('full_cycle', {})
        ]
        
        total_success = sum(1 for test in all_tests if test.get('success', False))
        total_tests = len([test for test in all_tests if test])
        
        print(f"\n🎯 전체 평가: {total_success}/{total_tests} 테스트 통과")
        
        if total_success == total_tests:
            print("🎉 모든 테스트 통과! AI 시스템이 정상 작동합니다.")
        else:
            print("⚠️  일부 테스트 실패. 로그를 확인하여 문제를 해결하세요.")
    
    def save_results(self):
        """테스트 결과를 파일로 저장"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ai_test_results_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.test_results, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 테스트 결과가 {filename}에 저장되었습니다.")

async def main():
    """메인 테스트 실행"""
    print("🚀 AI 거래 시스템 통합 테스트 시작")
    print(f"시작 시간: {datetime.now()}")
    
    # 환경 확인
    if not os.getenv('BYBIT_ACCESS_KEY') or not os.getenv('BYBIT_SECRET_KEY'):
        print("⚠️  Bybit API 키가 설정되지 않았습니다. 일부 테스트가 제한될 수 있습니다.")
    
    if not os.getenv('AI_API_KEY'):
        print("⚠️  AI API 키가 설정되지 않았습니다. 규칙 기반 분석으로 동작합니다.")
    
    tester = AIIntegrationTester()
    
    try:
        # 개별 분석기 테스트
        await tester.test_individual_analyzers()
        
        # 최종 결정 AI 테스트
        await tester.test_final_decision_maker()
        
        # AI 통합 시스템 테스트
        await tester.test_ai_integration()
        
        # 완전한 사이클 테스트
        await tester.test_full_cycle()
        
    except KeyboardInterrupt:
        print("\n⏹️  사용자에 의해 테스트가 중단되었습니다.")
    except Exception as e:
        print(f"\n❌ 테스트 중 예상치 못한 오류: {e}")
    
    finally:
        # 결과 요약 출력
        tester.print_summary()
        
        # 결과 저장
        tester.save_results()
        
        print(f"\n🏁 테스트 완료: {datetime.now()}")

if __name__ == "__main__":
    asyncio.run(main())