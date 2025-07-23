import json
import re
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types
import sys
import os

# 상위 디렉토리의 모듈 import를 위한 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../'))

from docs.investment_ai.config import CONFIG, API_KEY, MODEL_PRIORITY
from docs.investment_ai.indicators.technical_indicators import calculate_technical_indicators, get_latest_indicators

# 로깅 설정
logger = logging.getLogger("technical_analyzer")

class TechnicalAnalyzer:
    """기술적 지표 분석 AI - 2단계"""
    
    def __init__(self):
        # AI 모델 초기화 제거 - 실제 호출 시에만 초기화
        self.client = None
        self.model_name = None
    
    # 수정 후 코드

    def get_chart_data(self, symbol='BTCUSDT', timeframe='15m', limit=300):
        """차트 데이터 수집 (15분봉 300개, 미완성 캔들 제외)"""
        try:
            from pymongo import MongoClient
            
            mongoClient = MongoClient("mongodb://mongodb:27017")
            database = mongoClient["bitcoin"]
            
            chart_collections = {
                '1m': 'chart_1m',
                '3m': 'chart_3m', 
                '5m': 'chart_5m',
                '15m': 'chart_15m',
                '1h': 'chart_1h',
                '30d': 'chart_30d'
            }
            
            if timeframe not in chart_collections:
                raise ValueError(f"지원하지 않는 시간봉: {timeframe}")
            
            chart_collection = database[chart_collections[timeframe]]
            
            # 분석에 필요한 완성된 캔들 수만큼 가져오기 위해 1개를 더 요청
            data_cursor = chart_collection.find().sort("timestamp", -1).limit(limit + 1)
            data_list = list(data_cursor)
            
            if not data_list:
                raise ValueError("차트 데이터가 없습니다")
            
            df = pd.DataFrame(data_list)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            if '_id' in df.columns:
                df.drop('_id', axis=1, inplace=True)
            
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)  # 시간순 정렬
            
            # --- 핵심 수정 사항 ---
            # 가장 최신 데이터는 미완성 캔들일 가능성이 높으므로 제거합니다.
            # iloc[:-1]은 마지막 행을 제외한 모든 행을 선택합니다.
            df = df.iloc[:-1]
            
            logger.info(f"완성된 차트 데이터 수집 완료: {len(df)}개 캔들 ({timeframe})")
            return df
            
        except Exception as e:
            logger.error(f"차트 데이터 수집 중 오류: {e}")
            return None
    
    def calculate_technical_indicators(self, df):
        """기술적 지표 계산 - 새로운 정리된 코드 사용"""
        try:
            # 새로 정리된 지표 계산 함수 사용
            processed_df, config_info = calculate_technical_indicators(df)
            
            logger.info("정리된 기술적 지표 계산 완료")
            return processed_df, config_info
            
        except Exception as e:
            logger.error(f"정리된 지표 계산 중 오류: {e}")
            # 백업: 기본 지표만 계산
            return self.calculate_basic_indicators(df)
    
    def calculate_basic_indicators(self, df):
        """기본 기술적 지표 계산 (백업용)"""
        try:
            import ta
            
            # 기본 지표들
            df['rsi'] = ta.momentum.rsi(df['close'], window=14)
            df['ema_20'] = df['close'].ewm(span=20).mean()
            df['ema_50'] = df['close'].ewm(span=50).mean()
            
            # MACD
            ema_12 = df['close'].ewm(span=12).mean()
            ema_26 = df['close'].ewm(span=26).mean()
            df['macd'] = ema_12 - ema_26
            df['macd_signal'] = df['macd'].ewm(span=9).mean()
            df['macd_histogram'] = df['macd'] - df['macd_signal']
            
            # Bollinger Bands
            df['bb_middle'] = df['close'].rolling(window=20).mean()
            bb_std = df['close'].rolling(window=20).std()
            df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
            df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
            df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower']) * 100
            
            # ATR
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            df['true_range'] = np.maximum(high_low, np.maximum(high_close, low_close))
            df['atr'] = df['true_range'].rolling(window=14).mean()
            
            logger.info("기본 기술적 지표 계산 완료")
            return df, {}
            
        except Exception as e:
            logger.error(f"기본 지표 계산 중 오류: {e}")
            return df, {}
    
    def extract_key_indicators(self, df, config_info):
        """AI 분석용 핵심 지표 추출 - 새로운 구조 사용"""
        try:
            # 새로운 get_latest_indicators 함수 사용
            latest_indicators = get_latest_indicators(df)
            
            if not latest_indicators:
                raise ValueError("지표 추출 실패")
            
            # 24시간 변동률 계산 (15분봉 기준 96개 = 24시간)
            current_price = latest_indicators['basic']['current_price']
            price_change_24h = 0
            if len(df) >= 96:
                price_24h_ago = float(df.iloc[-96]['close'])
                price_change_24h = ((current_price - price_24h_ago) / price_24h_ago * 100)
            
            # AI가 이해하기 쉬운 형태로 재구성
            analysis_data = {
                'current_price': current_price,
                'price_change_24h': round(price_change_24h, 2),
                'volume': latest_indicators['basic']['volume'],
                'timestamp': latest_indicators['basic']['timestamp'],
                
                # 추세 분석
                'trend_indicators': {
                    'ema_fast': latest_indicators['trend']['ema_fast'],
                    'ema_slow': latest_indicators['trend']['ema_slow'],
                    'ema_signal': 'bullish' if latest_indicators['trend']['ema_fast'] > latest_indicators['trend']['ema_slow'] else 'bearish',
                    'macd': latest_indicators['trend']['macd'],
                    'macd_signal': latest_indicators['trend']['macd_signal'],
                    'macd_histogram': latest_indicators['trend']['macd_histogram'],
                    'macd_status': 'bullish' if latest_indicators['trend']['macd'] > latest_indicators['trend']['macd_signal'] else 'bearish',
                    'adx': latest_indicators['trend']['adx'],
                    'adx_strength': 'strong' if latest_indicators['trend']['adx'] > 25 else 'weak',
                    'di_plus': latest_indicators['trend']['di_plus'],
                    'di_minus': latest_indicators['trend']['di_minus'],
                    'di_signal': 'bullish' if latest_indicators['trend']['di_plus'] > latest_indicators['trend']['di_minus'] else 'bearish'
                },
                
                # 모멘텀 분석
                'momentum_indicators': {
                    'rsi': latest_indicators['momentum']['rsi'],
                    'rsi_state': latest_indicators['momentum']['momentum_state'],
                    'stoch_k': latest_indicators['momentum']['stoch_k'],
                    'stoch_d': latest_indicators['momentum']['stoch_d'],
                    'stoch_signal': 'bullish' if latest_indicators['momentum']['stoch_k'] > latest_indicators['momentum']['stoch_d'] else 'bearish',
                    'williams_r': latest_indicators['momentum']['williams_r'],
                    'williams_state': 'oversold' if latest_indicators['momentum']['williams_r'] > -20 else 'overbought' if latest_indicators['momentum']['williams_r'] < -80 else 'neutral'
                },
                
                # 변동성 분석
                'volatility_indicators': {
                    'bb_position': latest_indicators['volatility']['bb_position'],
                    'bb_upper': latest_indicators['volatility']['bb_upper'],
                    'bb_lower': latest_indicators['volatility']['bb_lower'],
                    'bb_middle': latest_indicators['volatility']['bb_middle'],
                    'bb_signal': 'overbought' if latest_indicators['volatility']['bb_position'] > 80 else 'oversold' if latest_indicators['volatility']['bb_position'] < 20 else 'neutral',
                    'atr': latest_indicators['volatility']['atr'],
                    'atr_percent': latest_indicators['volatility']['atr_percent'],
                    'volatility_level': latest_indicators['volatility']['volatility_level']
                },
                
                # 볼륨 분석
                'volume_indicators': {
                    'volume_ratio': latest_indicators['volume']['volume_ratio'],
                    'volume_state': latest_indicators['volume']['volume_state'],
                    'obv_trend': 'bullish' if latest_indicators['volume']['obv_trend'] > 0 else 'bearish',
                    'mfi': latest_indicators['volume']['mfi'],
                    'mfi_state': 'overbought' if latest_indicators['volume']['mfi'] > 80 else 'oversold' if latest_indicators['volume']['mfi'] < 20 else 'neutral'
                },
                
                # 지지/저항 분석
                'support_resistance': {
                    'support_level': latest_indicators['support_resistance']['support'],
                    'resistance_level': latest_indicators['support_resistance']['resistance'],
                    'price_position': latest_indicators['support_resistance']['price_position'],
                    'breakout_potential': latest_indicators['support_resistance']['breakout_potential'],
                    'support_distance': round(((current_price - latest_indicators['support_resistance']['support']) / current_price) * 100, 2),
                    'resistance_distance': round(((latest_indicators['support_resistance']['resistance'] - current_price) / current_price) * 100, 2)
                }
            }
            
            logger.info("AI용 핵심 지표 추출 완료")
            return analysis_data
            
        except Exception as e:
            logger.error(f"핵심 지표 추출 중 오류: {e}")
            return {
                'current_price': 0,
                'price_change_24h': 0,
                'volume': 0,
                'error': str(e)
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
                    logger.warning(f"기술적 분석 모델 {model_name} 초기화 실패: {e}")
                    continue
            
            return None, None
            
        except Exception as e:
            logger.error(f"기술적 분석 모델 초기화 중 오류: {e}")
            return None, None

    async def analyze_with_ai(self, indicators_data: Dict) -> Dict:
        """AI 모델을 사용하여 기술적 지표 분석"""
        # 필요할 때만 모델 초기화
        if self.client is None:
            self.client, self.model_name = self.get_model()
        
        #if self.client is None:
        #    logger.warning("AI 모델이 없어 규칙 기반 분석으로 대체합니다.")
        #    return self.rule_based_analysis(indicators_data)
        
        try:
            # 프롬프트 구성
            prompt = CONFIG["prompts"]["technical_analysis"].format(
                technical_indicators=json.dumps(indicators_data, ensure_ascii=False, indent=2),
                current_price=indicators_data['current_price'],
                price_change_24h=indicators_data['price_change_24h'],
                volume=indicators_data['volume']
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
                    'raw_data': indicators_data
                }
                
                return result_json
            else:
                logger.error("AI 응답에서 JSON을 찾을 수 없습니다.")
                return self.rule_based_analysis(indicators_data)
                
        except Exception as e:
            logger.error(f"AI 기술적 분석 중 오류: {e}")
            return self.rule_based_analysis(indicators_data)
    
    def rule_based_analysis(self, indicators_data: Dict) -> Dict:
        """규칙 기반 기술적 분석 (AI 모델 없을 때 백업)"""
        try:
            trend_indicators = indicators_data.get('trend_indicators', {})
            momentum_indicators = indicators_data.get('momentum_indicators', {})
            volatility_indicators = indicators_data.get('volatility_indicators', {})
            volume_indicators = indicators_data.get('volume_indicators', {})
            support_resistance = indicators_data.get('support_resistance', {})
            
            # 신호 점수 계산 (각 지표별 점수)
            signal_score = 0
            total_signals = 0
            
            # 추세 신호들
            if trend_indicators.get('ema_signal') == 'bullish':
                signal_score += 1
            elif trend_indicators.get('ema_signal') == 'bearish':
                signal_score -= 1
            total_signals += 1
            
            if trend_indicators.get('macd_status') == 'bullish':
                signal_score += 1
            elif trend_indicators.get('macd_status') == 'bearish':
                signal_score -= 1
            total_signals += 1
            
            if trend_indicators.get('di_signal') == 'bullish':
                signal_score += 1
            elif trend_indicators.get('di_signal') == 'bearish':
                signal_score -= 1
            total_signals += 1
            
            # 모멘텀 신호들
            rsi = momentum_indicators.get('rsi', 50)
            if rsi < 30:
                signal_score += 1  # 과매도에서 매수
            elif rsi > 70:
                signal_score -= 1  # 과매수에서 매도
            total_signals += 1
            
            if momentum_indicators.get('stoch_signal') == 'bullish':
                signal_score += 1
            elif momentum_indicators.get('stoch_signal') == 'bearish':
                signal_score -= 1
            total_signals += 1
            
            # 변동성 신호들
            bb_signal = volatility_indicators.get('bb_signal', 'neutral')
            if bb_signal == 'oversold':
                signal_score += 1
            elif bb_signal == 'overbought':
                signal_score -= 1
            total_signals += 1
            
            # 볼륨 확인
            volume_confirmation = volume_indicators.get('volume_ratio', 1) > 1.2
            
            # 전체 신호 강도
            signal_strength = abs(signal_score) / total_signals * 100 if total_signals > 0 else 0
            
            # 최종 신호 결정
            if signal_score >= 3:
                overall_signal = "Strong Buy"
            elif signal_score >= 1:
                overall_signal = "Buy"
            elif signal_score <= -3:
                overall_signal = "Strong Sell"
            elif signal_score <= -1:
                overall_signal = "Sell"
            else:
                overall_signal = "Hold"
            
            # 결과 구성
            result = {
                "overall_signal": overall_signal,
                "trend_analysis": {
                    "trend_direction": trend_indicators.get('ema_signal', 'neutral').title(),
                    "trend_strength": int(signal_strength),
                    "key_support_level": support_resistance.get('support_level', 0),
                    "key_resistance_level": support_resistance.get('resistance_level', 0)
                },
                "momentum_analysis": {
                    "momentum_direction": momentum_indicators.get('rsi_state', 'neutral').title(),
                    "momentum_strength": int(signal_strength),
                    "oversold_overbought": momentum_indicators.get('rsi_state', 'neutral').title()
                },
                "volatility_analysis": {
                    "volatility_level": volatility_indicators.get('volatility_level', 'medium').title(),
                    "breakout_probability": int(signal_strength),
                    "expected_direction": "Up" if signal_score > 0 else "Down" if signal_score < 0 else "Uncertain"
                },
                "volume_analysis": {
                    "volume_trend": volume_indicators.get('volume_state', 'normal').title(),
                    "volume_confirmation": volume_confirmation,
                    "institutional_flow": volume_indicators.get('obv_trend', 'neutral').title()
                },
                "entry_exit_points": {
                    "best_entry_long": support_resistance.get('support_level', 0),
                    "best_entry_short": support_resistance.get('resistance_level', 0),
                    "stop_loss_long": support_resistance.get('support_level', 0) * 0.97,
                    "stop_loss_short": support_resistance.get('resistance_level', 0) * 1.03,
                    "take_profit_long": support_resistance.get('resistance_level', 0),
                    "take_profit_short": support_resistance.get('support_level', 0)
                },
                "timeframe_analysis": {
                    "short_term": f"{'상승' if signal_score > 0 else '하락' if signal_score < 0 else '중립적'} 움직임 예상",
                    "medium_term": f"추세 {'지속' if abs(signal_score) >= 2 else '전환'} 가능성",
                    "long_term": f"{'강세' if signal_score >= 3 else '약세' if signal_score <= -3 else '중립'} 기조"
                },
                "confidence": max(40, int(signal_strength)),
                "analysis_summary": f"규칙 기반 분석: {total_signals}개 지표 중 {abs(signal_score)}개가 {'상승' if signal_score > 0 else '하락' if signal_score < 0 else '중립'} 신호"
            }
            
            # 메타데이터 추가
            result['analysis_metadata'] = {
                'analysis_type': 'rule_based',
                'data_timestamp': datetime.now(timezone.utc).isoformat(),
                'model_used': 'rule_based_fallback',
                'signal_score': signal_score,
                'total_signals': total_signals,
                'raw_data': indicators_data
            }
            
            return result
            
        except Exception as e:
            logger.error(f"규칙 기반 기술적 분석 중 오류: {e}")
            return {
                "overall_signal": "Hold",
                "error": str(e),
                "confidence": 0,
                "analysis_summary": f"기술적 분석 중 오류 발생: {str(e)}"
            }
    
    async def analyze_technical_indicators(self, symbol='BTCUSDT', timeframe='15m', limit=300) -> Dict:
        """기술적 지표 분석 메인 함수"""
        try:
            logger.info("기술적 지표 분석 시작")
            
            # 1. 차트 데이터 수집
            df = self.get_chart_data(symbol, timeframe, limit)
            if df is None or df.empty:
                return {
                    "success": False,
                    "error": "차트 데이터 수집 실패",
                    "analysis_type": "technical_analysis"
                }
            
            # 2. 기술적 지표 계산 (새로운 정리된 코드 사용)
            processed_df, config_info = self.calculate_technical_indicators(df)
            
            # 3. 핵심 지표 추출
            indicators_data = self.extract_key_indicators(processed_df, config_info)
            
            if 'error' in indicators_data:
                return {
                    "success": False,
                    "error": indicators_data['error'],
                    "analysis_type": "technical_analysis"
                }
            
            # 4. AI 분석 수행
            analysis_result = await self.analyze_with_ai(indicators_data)
            
            logger.info("기술적 지표 분석 완료")
            
            return {
                "success": True,
                "result": analysis_result,
                "analysis_type": "technical_analysis"
            }
            
        except Exception as e:
            logger.error(f"기술적 지표 분석 중 오류: {e}")
            return {
                "success": False,
                "error": f"분석 중 오류 발생: {str(e)}",
                "analysis_type": "technical_analysis"
            }

# 외부에서 사용할 함수
async def analyze_technical_indicators(symbol='BTCUSDT', timeframe='15m', limit=300) -> Dict:
    """기술적 지표를 분석하는 함수"""
    analyzer = TechnicalAnalyzer()
    return await analyzer.analyze_technical_indicators(symbol, timeframe, limit)

# 테스트용 코드
if __name__ == "__main__":
    import asyncio
    
    async def test():
        result = await analyze_technical_indicators()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())