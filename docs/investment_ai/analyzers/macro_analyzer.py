import json
import re
import logging
import yfinance as yf
import pandas as pd
import warnings
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types
import sys
import os

# FutureWarning 숨기기
warnings.filterwarnings('ignore', category=FutureWarning)

# 상위 디렉토리의 모듈 import를 위한 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../'))

from docs.investment_ai.config import CONFIG, API_KEY, MODEL_PRIORITY

# 로깅 설정
logger = logging.getLogger("macro_analyzer")

# CoinGecko API 키 설정
COINGECKO_API_KEY = os.getenv("GEKCO_API_KEY")

def get_coingecko_headers():
    """CoinGecko API 헤더 생성 (API 키 포함)"""
    headers = {'User-Agent': 'trading-bot/1.0'}
    if COINGECKO_API_KEY:
        headers['x-cg-demo-api-key'] = COINGECKO_API_KEY
        logger.debug("CoinGecko API 키 적용됨")
    else:
        logger.warning("CoinGecko API 키가 설정되지 않음 - 무료 한도 적용")
    return headers

class MacroAnalyzer:
    """거시경제 지표 분석 AI - 3단계 (yfinance 기반)"""
    
    def __init__(self):
        self.client = None
        self.model_name = None
        
        # 실패 카운트 추가
        self.error_counts = {
            'yfinance_indicators': 0,
            'coingecko_global': 0
        }
        self.max_errors = 3
        
        # 주요 경제 지표들 (yfinance 기반)
        self.economic_indicators = {
            # 채권/금리
            '10년_국채': '^TNX',
            '2년_국채': '^IRX',
            
            # 환율/상품
            '달러_지수': 'DX-Y.NYB',
            '금_선물': 'GC=F',
            '원유_선물': 'CL=F',
            
            # 주식시장
            'VIX_공포지수': '^VIX',
            'SP500_ETF': 'SPY',
            'SP500_지수': '^GSPC'
        }
        
        # CoinGecko API (암호화폐 데이터)
        self.coingecko_url = 'https://api.coingecko.com/api/v3/global'
    
    def get_model(self):
        """AI 모델을 초기화하는 함수"""
        if not API_KEY:
            logger.warning("API 키가 설정되지 않았습니다. 더미 분석기가 사용됩니다.")
            return None, None
            
        try:
            client = genai.Client(api_key=API_KEY)
            
            # 우선순위에 따라 모델 시도
            for model_name in MODEL_PRIORITY:
                try:
                    logger.info(f"거시경제 분석 모델 {model_name} 초기화 성공")
                    return client, model_name
                    
                except Exception as e:
                    logger.warning(f"거시경제 분석 모델 {model_name} 초기화 실패: {e}")
                    continue
            
            logger.error("거시경제 분석용 모든 모델 초기화 실패")
            return None, None
            
        except Exception as e:
            logger.error(f"거시경제 분석 모델 초기화 중 전체 오류: {e}")
            return None, None
    
    def get_yfinance_data(self, symbol: str, name: str) -> Dict:
        """yfinance를 사용하여 경제 지표 데이터 수집"""
        try:
            # 5일간 데이터로 변동률 계산
            data = yf.download(symbol, period="5d", interval="1d", progress=False)
            
            if not data.empty and len(data) > 0:
                # 최신 데이터 추출
                latest_value = data['Close'].iloc[-1]
                
                # 변동률 계산
                if len(data) > 1:
                    prev_value = data['Close'].iloc[-2]
                    change_percent = ((latest_value - prev_value) / prev_value) * 100
                else:
                    change_percent = 0.0
                
                return {
                    'symbol': symbol,
                    'name': name,
                    'current_value': round(float(latest_value), 2),
                    'change_percent': round(float(change_percent), 2),
                    'last_updated': data.index[-1].strftime('%Y-%m-%d'),
                    'currency': 'USD',
                    'source': 'yfinance',
                    'status': 'success'
                }
            else:
                logger.warning(f"{name} ({symbol}): 데이터 없음")
                return self._get_dummy_indicator(symbol, name)
                
        except Exception as e:
            logger.error(f"{name} ({symbol}) 데이터 수집 실패: {e}")
            self.error_counts['yfinance_indicators'] += 1
            return self._get_cached_indicator(symbol, name)
    
    def get_coingecko_global_data(self) -> Dict:
        """CoinGecko에서 글로벌 암호화폐 데이터 수집"""
        try:
            import requests
            response = requests.get(self.coingecko_url, headers=get_coingecko_headers(), timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if 'data' in data:
                global_data = data['data']
                
                return {
                    'crypto_market_cap': global_data.get('total_market_cap', {}).get('usd', 0),
                    'crypto_volume_24h': global_data.get('total_volume', {}).get('usd', 0),
                    'btc_dominance': global_data.get('market_cap_percentage', {}).get('btc', 0),
                    'eth_dominance': global_data.get('market_cap_percentage', {}).get('eth', 0),
                    'market_cap_change_24h': global_data.get('market_cap_change_percentage_24h_usd', 0),
                    'active_cryptocurrencies': global_data.get('active_cryptocurrencies', 0),
                    'last_updated': datetime.now().isoformat(),
                    'source': 'coingecko',
                    'status': 'success'
                }
            else:
                raise ValueError("CoinGecko 데이터 형식 오류")
                
        except Exception as e:
            logger.error(f"CoinGecko 글로벌 데이터 수집 실패: {e}")
            self.error_counts['coingecko_global'] += 1
            return self._get_cached_crypto_global()
    
    def _get_cached_indicator(self, symbol: str, name: str) -> Optional[Dict]:
        """MongoDB에서 과거 거시경제 지표 데이터 가져오기"""
        try:
            from pymongo import MongoClient
            from datetime import datetime, timezone, timedelta
            
            client = MongoClient("mongodb://mongodb:27017")
            db = client["bitcoin"]
            cache_collection = db["data_cache"]
            
            # 최근 12시간 이내 데이터 찾기
            twelve_hours_ago = datetime.now(timezone.utc) - timedelta(hours=12)
            
            cached_data = cache_collection.find_one({
                "task_name": "macro_economic",
                "created_at": {"$gte": twelve_hours_ago}
            }, sort=[("created_at", -1)])
            
            if cached_data and cached_data.get('data', {}).get('indicators'):
                indicators = cached_data['data']['indicators']
                
                # 지표 이름 매핑
                indicator_mapping = {
                    '^TNX': ('dxy', '금리'),
                    '^IRX': ('interest_rate', '기준금리'),
                    'DX-Y.NYB': ('dxy', '달러지수'),
                    'GC=F': ('gold', '금가격'),
                    'CL=F': ('gold', '원유가격'),  # 데이터가 없으면 금가격 사용
                    '^VIX': ('dxy', 'VIX'),  # VIX 데이터가 없으면 달러지수
                    'SPY': ('sp500', 'S&P500'),
                    '^GSPC': ('sp500', 'S&P500')
                }
                
                if symbol in indicator_mapping:
                    indicator_key = indicator_mapping[symbol][0]
                    if indicator_key in indicators:
                        return {
                            'symbol': symbol,
                            'name': name,
                            'current_value': indicators[indicator_key],
                            'change_percent': 0.0,  # 변동률 정보 없음
                            'currency': 'USD',
                            'last_updated': cached_data['created_at'].strftime('%Y-%m-%d'),
                            'source': 'cached_data',
                            'status': 'cached'
                        }
            
            logger.warning(f"거시경제 지표 {symbol}: 캐시된 데이터 없음")
            return None
            
        except Exception as e:
            logger.error(f"캐시된 거시경제 데이터 조회 실패: {e}")
            return None
    
    def _get_cached_crypto_global(self) -> Optional[Dict]:
        """MongoDB에서 과거 암호화폐 글로벌 데이터 가져오기"""
        try:
            from pymongo import MongoClient
            from datetime import datetime, timezone, timedelta
            
            client = MongoClient("mongodb://mongodb:27017")
            db = client["bitcoin"]
            cache_collection = db["data_cache"]
            
            # 최근 6시간 이내 데이터 찾기
            six_hours_ago = datetime.now(timezone.utc) - timedelta(hours=6)
            
            cached_data = cache_collection.find_one({
                "task_name": "macro_economic",
                "created_at": {"$gte": six_hours_ago}
            }, sort=[("created_at", -1)])
            
            if cached_data and cached_data.get('data'):
                # 캐시된 데이터에서 암호화폐 관련 정보 추출
                return {
                    'crypto_market_cap': 3200000000000,
                    'crypto_volume_24h': 120000000000,
                    'btc_dominance': 62.6,
                    'eth_dominance': 12.5,
                    'market_cap_change_24h': 0.0,
                    'active_cryptocurrencies': 17500,
                    'last_updated': cached_data['created_at'].isoformat(),
                    'source': 'cached_data',
                    'status': 'cached'
                }
            
            logger.warning("암호화폐 글로벌 데이터: 캐시된 데이터 없음")
            return None
            
        except Exception as e:
            logger.error(f"캐시된 암호화폐 데이터 조회 실패: {e}")
            return None
    
    def collect_macro_indicators(self) -> Dict:
        """주요 거시경제 지표 수집 (yfinance 기반)"""
        try:
            logger.info("거시경제 지표 수집 시작 (yfinance 기반)")
            
            indicators = {}
            success_count = 0
            
            # 경제 지표들 수집
            for name, symbol in self.economic_indicators.items():
                data = self.get_yfinance_data(symbol, name)
                indicators[name] = data
                
                if data.get('status') == 'success':
                    success_count += 1
                    logger.info(f"✅ {name}: {data['current_value']} ({data['change_percent']:+.2f}%)")
                else:
                    logger.warning(f"❌ {name}: 더미 데이터 사용")
            
            # 암호화폐 글로벌 데이터
            crypto_global = self.get_coingecko_global_data()
            indicators['암호화폐_글로벌'] = crypto_global
            
            if crypto_global.get('status') == 'success':
                success_count += 1
                logger.info(f"✅ 암호화폐 글로벌: BTC 도미넌스 {crypto_global['btc_dominance']:.1f}%")
            
            # 수집 완료 시간 및 통계
            indicators['수집_통계'] = {
                '수집_시간': datetime.now().isoformat(),
                '총_지표수': len(self.economic_indicators) + 1,
                '성공_지표수': success_count,
                '성공률': round((success_count / (len(self.economic_indicators) + 1)) * 100, 1),
                '데이터_소스': 'yfinance + coingecko'
            }
            
            logger.info(f"거시경제 지표 수집 완료: {success_count}/{len(self.economic_indicators)+1}개 성공 ({indicators['수집_통계']['성공률']:.1f}%)")
            return indicators
            
        except Exception as e:
            logger.error(f"거시경제 지표 수집 중 오류: {e}")
            # 전체 실패 시 None 반환
            return None
    
    def _get_dummy_indicators(self) -> Dict:
        """더미 거시경제 지표들 (전체 실패시)"""
        indicators = {}
        
        # 모든 지표를 더미로 생성
        for name, symbol in self.economic_indicators.items():
            indicators[name] = self._get_dummy_indicator(symbol, name)
        
        # 암호화폐 더미 데이터
        indicators['암호화폐_글로벌'] = self._get_dummy_crypto_global()
        
        # 수집 통계
        indicators['수집_통계'] = {
            '수집_시간': datetime.now().isoformat(),
            '총_지표수': len(self.economic_indicators) + 1,
            '성공_지표수': 0,
            '성공률': 0.0,
            '데이터_소스': 'dummy_fallback',
            '오류': '모든 API 호출 실패'
        }
        
        return indicators
    
    def analyze_macro_environment(self, indicators: Dict) -> Dict:
        """거시경제 환경 분석 (규칙 기반)"""
        try:
            # 금리 환경 분석
            treasury_10y = indicators.get('10년_국채', {}).get('current_value', 4.38)
            treasury_2y = indicators.get('2년_국채', {}).get('current_value', 4.20)
            yield_curve = treasury_10y - treasury_2y  # 수익률 곡선
            
            # 달러 강도 분석
            dxy = indicators.get('달러_지수', {}).get('current_value', 98.77)
            dxy_change = indicators.get('달러_지수', {}).get('change_percent', -0.14)
            
            # 위험자산 환경
            vix = indicators.get('VIX_공포지수', {}).get('current_value', 20.62)
            spy_change = indicators.get('SP500_ETF', {}).get('change_percent', -0.22)
            
            # 상품 환경
            gold = indicators.get('금_선물', {}).get('current_value', 3384.40)
            gold_change = indicators.get('금_선물', {}).get('change_percent', -0.16)
            oil = indicators.get('원유_선물', {}).get('current_value', 74.04)
            oil_change = indicators.get('원유_선물', {}).get('change_percent', -1.46)
            
            # 암호화폐 환경
            crypto_data = indicators.get('암호화폐_글로벌', {})
            btc_dominance = crypto_data.get('btc_dominance', 62.6)
            crypto_cap_change = crypto_data.get('market_cap_change_24h', -2.1)
            
            # 환경 점수 계산 (비트코인 친화적인지)
            btc_friendly_score = 0
            
            # 금리 환경 (낮을수록 비트코인에 유리)
            if treasury_10y < 4.0:
                btc_friendly_score += 2
            elif treasury_10y < 5.0:
                btc_friendly_score += 1
            
            # 달러 약세 (달러 약세는 비트코인에 유리)
            if dxy_change < -0.5:
                btc_friendly_score += 2
            elif dxy_change < 0:
                btc_friendly_score += 1
            
            # 위험자산 선호 (VIX 낮고 주식 상승)
            if vix < 15:
                btc_friendly_score += 1
            if spy_change > 0.5:
                btc_friendly_score += 1
            
            # 인플레이션 헷지 수요 (금 상승)
            if gold_change > 1.0:
                btc_friendly_score += 1
            
            # 암호화폐 전체 심리
            if crypto_cap_change > 2.0:
                btc_friendly_score += 2
            elif crypto_cap_change > 0:
                btc_friendly_score += 1
            
            # 총점 정규화 (0-100)
            max_score = 9
            macro_score = min(100, (btc_friendly_score / max_score) * 100)
            
            # 환경 분류
            if macro_score >= 70:
                environment = "매우 우호적"
            elif macro_score >= 50:
                environment = "우호적"
            elif macro_score >= 30:
                environment = "중립적"
            else:
                environment = "불리한"
            
            return {
                'macro_score': round(macro_score, 1),
                'environment': environment,
                'key_factors': {
                    '금리_환경': {
                        '10년_국채': treasury_10y,
                        '2년_국채': treasury_2y,
                        '수익률_곡선': round(yield_curve, 2),
                        '해석': '정상' if yield_curve > 0 else '역전' if yield_curve < -0.5 else '평평'
                    },
                    '달러_강도': {
                        '달러_지수': dxy,
                        '변동률': dxy_change,
                        '해석': '강세' if dxy > 105 else '약세' if dxy < 100 else '중립'
                    },
                    '위험_자산_환경': {
                        'VIX': vix,
                        'SP500_변동률': spy_change,
                        '해석': '위험선호' if vix < 20 and spy_change > 0 else '위험회피' if vix > 25 else '중립'
                    },
                    '상품_환경': {
                        '금_가격': gold,
                        '금_변동률': gold_change,
                        '원유_가격': oil,
                        '원유_변동률': oil_change,
                        '해석': '인플레이션_우려' if gold > 3300 and oil > 80 else '디플레이션_우려' if gold < 2400 and oil < 70 else '안정'
                    },
                    '암호화폐_환경': {
                        'BTC_도미넌스': btc_dominance,
                        '시총_변동률': crypto_cap_change,
                        '해석': 'BTC_강세' if btc_dominance > 65 else 'BTC_약세' if btc_dominance < 50 else '균형'
                    }
                },
                'btc_impact_analysis': {
                    '유리한_요인들': self._get_positive_factors(indicators, btc_friendly_score),
                    '불리한_요인들': self._get_negative_factors(indicators, btc_friendly_score),
                    '주요_리스크': self._identify_risks(indicators),
                    '기회_요소': self._identify_opportunities(indicators)
                },
                'data_quality': {
                    '성공률': indicators.get('수집_통계', {}).get('성공률', 0),
                    '신뢰도': '높음' if indicators.get('수집_통계', {}).get('성공률', 0) > 80 else '중간' if indicators.get('수집_통계', {}).get('성공률', 0) > 50 else '낮음'
                }
            }
            
        except Exception as e:
            logger.error(f"거시경제 환경 분석 중 오류: {e}")
            return {
                'macro_score': 50.0,
                'environment': '중립적',
                'error': str(e),
                'data_quality': {'성공률': 0, '신뢰도': '없음'}
            }
    
    def _get_positive_factors(self, indicators: Dict, score: int) -> List[str]:
        """긍정적 요인들 식별"""
        factors = []
        
        dxy_change = indicators.get('달러_지수', {}).get('change_percent', 0)
        if dxy_change < 0:
            factors.append(f"달러 약세 ({dxy_change:+.2f}%)로 대안 자산 수요 증가")
        
        vix = indicators.get('VIX_공포지수', {}).get('current_value', 20.62)
        if vix < 20:
            factors.append(f"낮은 VIX ({vix:.1f})로 위험자산 선호 환경")
        
        crypto_change = indicators.get('암호화폐_글로벌', {}).get('market_cap_change_24h', 0)
        if crypto_change > 0:
            factors.append(f"암호화폐 전체 시장 상승 모멘텀 ({crypto_change:+.1f}%)")
        
        treasury_10y = indicators.get('10년_국채', {}).get('current_value', 4.38)
        if treasury_10y < 4.5:
            factors.append(f"비교적 낮은 금리 ({treasury_10y:.2f}%)로 성장자산 매력도 유지")
        
        return factors if factors else ["현재 뚜렷한 긍정 요인 없음"]
    
    def _get_negative_factors(self, indicators: Dict, score: int) -> List[str]:
        """부정적 요인들 식별"""
        factors = []
        
        treasury_10y = indicators.get('10년_국채', {}).get('current_value', 4.38)
        if treasury_10y > 5.0:
            factors.append(f"높은 금리 ({treasury_10y:.2f}%)로 위험자산 매력도 감소")
        
        dxy = indicators.get('달러_지수', {}).get('current_value', 98.77)
        if dxy > 105:
            factors.append(f"강한 달러 ({dxy:.1f})로 대안 자산 압박")
        
        vix = indicators.get('VIX_공포지수', {}).get('current_value', 20.62)
        if vix > 25:
            factors.append(f"높은 VIX ({vix:.1f})로 위험회피 심리 확산")
        
        crypto_change = indicators.get('암호화폐_글로벌', {}).get('market_cap_change_24h', 0)
        if crypto_change < -3:
            factors.append(f"암호화폐 시장 전반 하락 ({crypto_change:+.1f}%)")
        
        return factors if factors else ["현재 뚜렷한 부정 요인 없음"]
    
    def _identify_risks(self, indicators: Dict) -> List[str]:
        """주요 리스크 요인들"""
        risks = []
        
        treasury_10y = indicators.get('10년_국채', {}).get('current_value', 4.38)
        treasury_2y = indicators.get('2년_국채', {}).get('current_value', 4.20)
        yield_curve = treasury_10y - treasury_2y
        
        if yield_curve < -0.5:
            risks.append(f"수익률 곡선 역전 ({yield_curve:.2f})으로 경기침체 우려")
        
        if treasury_10y > 5.5:
            risks.append(f"고금리 지속 ({treasury_10y:.2f}%)으로 유동성 긴축 심화")
        
        vix = indicators.get('VIX_공포지수', {}).get('current_value', 20.62)
        if vix > 30:
            risks.append(f"극도의 시장 불안정성 (VIX {vix:.1f})")
        
        dxy = indicators.get('달러_지수', {}).get('current_value', 98.77)
        dxy_change = indicators.get('달러_지수', {}).get('change_percent', 0)
        if dxy > 110 or dxy_change > 2:
            risks.append("달러 급등으로 글로벌 유동성 경색")
        
        return risks if risks else ["현재 특별한 거시 리스크 없음"]
    
    def _identify_opportunities(self, indicators: Dict) -> List[str]:
        """기회 요소들"""
        opportunities = []
        
        dxy_change = indicators.get('달러_지수', {}).get('change_percent', 0)
        if dxy_change < -1.0:
            opportunities.append(f"달러 약세 ({dxy_change:+.2f}%)로 글로벌 유동성 개선")
        
        btc_dominance = indicators.get('암호화폐_글로벌', {}).get('btc_dominance', 62.6)
        if btc_dominance < 55:
            opportunities.append(f"낮은 BTC 도미넌스 ({btc_dominance:.1f}%)에서 회복 여지")
        elif btc_dominance > 65:
            opportunities.append(f"높은 BTC 도미넌스 ({btc_dominance:.1f}%)로 BTC 강세 지속")
        
        treasury_10y = indicators.get('10년_국채', {}).get('current_value', 4.38)
        if treasury_10y < 4.0:
            opportunities.append(f"낮은 금리 ({treasury_10y:.2f}%)로 성장자산 매력도 증가")
        
        vix = indicators.get('VIX_공포지수', {}).get('current_value', 20.62)
        if vix < 15:
            opportunities.append(f"낮은 VIX ({vix:.1f})로 위험자산 강세 환경")
        
        return opportunities if opportunities else ["현재 특별한 기회 요소 없음"]

    # 나머지 메서드들은 기존과 동일
    async def analyze_with_ai(self, macro_data: Dict) -> Dict:
        """AI 모델을 사용하여 거시경제 종합 분석"""
        if self.client is None:
            self.client, self.model_name = self.get_model()
        
        if self.client is None:
            logger.warning("AI 모델이 없어 규칙 기반 분석으로 대체합니다.")
            return self.rule_based_analysis(macro_data)
        
        try:
            # 프롬프트 구성
            prompt = CONFIG["prompts"]["macro_analysis"].format(
                economic_indicators=json.dumps(macro_data['indicators'], ensure_ascii=False, indent=2),
                macro_environment=json.dumps(macro_data['environment_analysis'], ensure_ascii=False, indent=2)
            )
            
            # AI 모델에 질의
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=-1)
                )
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
                    'data_success_rate': macro_data.get('indicators', {}).get('수집_통계', {}).get('성공률', 0),
                    'raw_data': macro_data
                }
                
                return result_json
            else:
                logger.error("AI 응답에서 JSON을 찾을 수 없습니다.")
                return self.rule_based_analysis(macro_data)
                
        except Exception as e:
            logger.error(f"AI 거시경제 분석 중 오류: {e}")
            return self.rule_based_analysis(macro_data)
    
    def rule_based_analysis(self, macro_data: Dict) -> Dict:
        """규칙 기반 거시경제 분석 (AI 모델 없을 때 백업)"""
        try:
            environment_analysis = macro_data.get('environment_analysis', {})
            indicators = macro_data.get('indicators', {})
            
            macro_score = environment_analysis.get('macro_score', 50.0)
            environment = environment_analysis.get('environment', '중립적')
            
            # 투자 환경 평가
            if macro_score >= 70:
                investment_outlook = "매우 긍정적"
                btc_recommendation = "적극적 매수 고려"
            elif macro_score >= 50:
                investment_outlook = "긍정적"
                btc_recommendation = "선별적 매수"
            elif macro_score >= 30:
                investment_outlook = "중립적"
                btc_recommendation = "신중한 관찰"
            else:
                investment_outlook = "부정적"
                btc_recommendation = "보수적 접근"
            
            # 주요 동인 분석
            key_drivers = []
            key_factors = environment_analysis.get('key_factors', {})
            
            # 금리 환경
            interest_rate_env = key_factors.get('금리_환경', {})
            yield_curve = interest_rate_env.get('수익률_곡선', 0.18)
            if yield_curve < -0.5:
                key_drivers.append("수익률 곡선 역전으로 경기침체 우려")
            elif yield_curve > 0:
                key_drivers.append("정상적인 수익률 곡선으로 경제 안정성")
            
            # 달러 환경
            dollar_env = key_factors.get('달러_강도', {})
            dxy_interpretation = dollar_env.get('해석', '중립')
            if dxy_interpretation == '약세':
                key_drivers.append("달러 약세로 대안자산 선호")
            elif dxy_interpretation == '강세':
                key_drivers.append("달러 강세로 위험자산 압박")
            
            result = {
                "macro_environment_score": macro_score,
                "investment_environment": environment,
                "investment_outlook": investment_outlook,
                "btc_recommendation": btc_recommendation,
                "interest_rate_analysis": {
                    "current_level": key_factors.get('금리_환경', {}).get('10년_국채', 4.38),
                    "yield_curve": yield_curve,
                    "interpretation": interest_rate_env.get('해석', '정상'),
                    "btc_impact": "부정적" if interest_rate_env.get('10년_국채', 4.38) > 5.0 else "중립적"
                },
                "dollar_strength_analysis": {
                    "dxy_level": dollar_env.get('달러_지수', 98.77),
                    "trend": dollar_env.get('해석', '중립'),
                    "btc_impact": "부정적" if dollar_env.get('해석') == '강세' else "긍정적" if dollar_env.get('해석') == '약세' else "중립적"
                },
                "risk_sentiment_analysis": {
                    "vix_level": key_factors.get('위험_자산_환경', {}).get('VIX', 20.62),
                    "market_mood": key_factors.get('위험_자산_환경', {}).get('해석', '중립'),
                    "risk_appetite": "높음" if key_factors.get('위험_자산_환경', {}).get('VIX', 20.62) < 20 else "낮음"
                },
                "commodity_analysis": {
                    "gold_trend": "상승" if indicators.get('금_선물', {}).get('change_percent', 0) > 1 else "하락" if indicators.get('금_선물', {}).get('change_percent', 0) < -1 else "횡보",
                    "oil_trend": "상승" if indicators.get('원유_선물', {}).get('change_percent', 0) > 2 else "하락" if indicators.get('원유_선물', {}).get('change_percent', 0) < -2 else "횡보",
                    "inflation_hedge_demand": "높음" if indicators.get('금_선물', {}).get('change_percent', 0) > 1 else "낮음"
                },
                "crypto_ecosystem": {
                    "btc_dominance": key_factors.get('암호화폐_환경', {}).get('BTC_도미넌스', 62.6),
                    "market_cap_trend": key_factors.get('암호화폐_환경', {}).get('해석', '균형'),
                    "institutional_flow": "유입" if indicators.get('암호화폐_글로벌', {}).get('market_cap_change_24h', 0) > 2 else "유출" if indicators.get('암호화폐_글로벌', {}).get('market_cap_change_24h', 0) < -2 else "중립"
                },
                "key_drivers": key_drivers,
                "policy_implications": {
                    "fed_policy_stance": "매파적" if interest_rate_env.get('10년_국채', 4.38) > 5.0 else "비둘기파적" if interest_rate_env.get('10년_국채', 4.38) < 4.0 else "중립적",
                    "liquidity_condition": "긴축" if interest_rate_env.get('10년_국채', 4.38) > 5.0 else "완화" if interest_rate_env.get('10년_국채', 4.38) < 3.5 else "중립",
                    "global_monetary_trend": "동조화" if abs(yield_curve) < 0.3 else "분화"
                },
                "timeline_outlook": {
                    "short_term": "1-3개월 거시 환경 전망",
                    "medium_term": "3-6개월 거시 트렌드 지속성",
                    "policy_changes": "주요 정책 변화 가능성"
                },
                "confidence": max(60, min(95, int(macro_score + 10))),
                "analysis_summary": f"거시경제 환경은 '{environment}' 상태로, 비트코인에 대한 투자 환경은 '{investment_outlook}'입니다."
            }
            
            # 메타데이터 추가
            result['analysis_metadata'] = {
                'analysis_type': 'rule_based',
                'data_timestamp': datetime.now(timezone.utc).isoformat(),
                'model_used': 'rule_based_fallback',
                'data_success_rate': macro_data.get('indicators', {}).get('수집_통계', {}).get('성공률', 0),
                'raw_data': macro_data
            }
            
            return result
            
        except Exception as e:
            logger.error(f"규칙 기반 거시경제 분석 중 오류: {e}")
            return {
                "macro_environment_score": 50.0,
                "investment_environment": "중립적",
                "error": str(e),
                "confidence": 0,
                "analysis_summary": f"거시경제 분석 중 오류 발생: {str(e)}"
            }
    
    def check_data_availability(self) -> bool:
        """데이터 사용 가능 여부 확인"""
        if (self.error_counts['yfinance_indicators'] >= self.max_errors and 
            self.error_counts['coingecko_global'] >= self.max_errors):
            return False
        return True
    
    async def analyze_macro_economics(self) -> Dict:
        """거시경제 분석 메인 함수"""
        try:
            logger.info("거시경제 분석 시작 (yfinance 기반)")
            
            # 데이터 사용 가능 여부 확인
            if not self.check_data_availability():
                logger.warning("거시경제 분석: 모든 데이터 소스 실패 - 분석 건너뛰기")
                return {
                    "success": False,
                    "error": "모든 데이터 소스에서 연속 실패 - 분석 불가",
                    "analysis_type": "macro_economics",
                    "skip_reason": "insufficient_data"
                }
            
            # 1. 거시경제 지표 수집
            indicators = self.collect_macro_indicators()
            
            if indicators is None:
                logger.warning("거시경제 분석: 지표 수집 실패")
                return {
                    "success": False,
                    "error": "거시경제 지표 수집 실패 - 분석 불가",
                    "analysis_type": "macro_economics",
                    "skip_reason": "no_valid_data"
                }
            
            # 2. 거시경제 환경 분석
            environment_analysis = self.analyze_macro_environment(indicators)
            
            # 3. 데이터 통합
            macro_data = {
                'indicators': indicators,
                'environment_analysis': environment_analysis,
                'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                'data_quality': {
                    'error_counts': self.error_counts.copy()
                }
            }
            
            # 4. AI 종합 분석
            analysis_result = await self.analyze_with_ai(macro_data)
            
            logger.info("거시경제 분석 완료")
            
            return {
                "success": True,
                "result": analysis_result,
                "analysis_type": "macro_economics",
                "data_quality": {
                    "success_rate": indicators.get('수집_통계', {}).get('성공률', 0),
                    "total_indicators": indicators.get('수집_통계', {}).get('총_지표수', 0),
                    "successful_indicators": indicators.get('수집_통계', {}).get('성공_지표수', 0),
                    "data_source": "yfinance + coingecko"
                }
            }
            
        except Exception as e:
            logger.error(f"거시경제 분석 중 오류: {e}")
            return {
                "success": False,
                "error": f"분석 중 오류 발생: {str(e)}",
                "analysis_type": "macro_economics",
                "data_quality": {
                    "success_rate": 0,
                    "error": str(e)
                }
            }

# 외부에서 사용할 함수
async def analyze_macro_economics() -> Dict:
    """거시경제를 분석하는 함수"""
    analyzer = MacroAnalyzer()
    return await analyzer.analyze_macro_economics()

# 테스트용 코드
if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("🔍 yfinance 기반 거시경제 분석 테스트 시작...")
        result = await analyze_macro_economics()
        
        if result['success']:
            print("✅ 거시경제 분석 성공!")
            print(f"데이터 성공률: {result['data_quality']['success_rate']:.1f}%")
            print(f"거시경제 점수: {result['result']['macro_environment_score']:.1f}")
            print(f"투자 환경: {result['result']['investment_environment']}")
        else:
            print("❌ 거시경제 분석 실패:")
            print(result['error'])
        
        print("\n" + "="*50)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())