import json
import re
import logging
import requests
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types
import sys
import os

# 상위 디렉토리의 모듈 import를 위한 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../'))

from docs.investment_ai.config import CONFIG, API_KEY, MODEL_PRIORITY

# 로깅 설정
logger = logging.getLogger("institution_analyzer")

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

class InstitutionAnalyzer:
    """기관 투자 흐름 분석 AI - 5단계 (순수 기관 지표만)"""
    
    def __init__(self):
        self.client = None
        self.model_name = None
        
        # 실패 카운트 추가
        self.error_counts = {
            'corporate_holdings': 0,
            'volume_patterns': 0,
            'market_structure': 0,
            'derivatives_flow': 0
        }
        self.max_errors = 3
        
        # 캐싱 TTL 설정 (초 단위) - 15분봉 기준 최적화
        self.cache_ttl = {
            'etf_flows': 14400,           # 4시간 (1일 2-3회 확인)
            'corporate_holdings': 21600,  # 6시간 (느린 변화)
            'institutional_volume': 7200, # 2시간 (거래량 패턴)
            'market_structure': 3600,     # 1시간 (시장 구조)
            'derivatives_flow': 7200,     # 2시간 (파생상품)
        }
        
        # 무료 기관 데이터 소스들 (뉴스/감정 제외)
        self.data_sources = {
            # CoinGecko - 기관 관련 데이터만 (무료)
            'coingecko': {
                'base_url': 'https://api.coingecko.com/api/v3',
                'endpoints': {
                    'global': '/global',
                    'btc_data': '/coins/bitcoin',
                    'companies': '/companies/public_treasury/bitcoin',
                    'exchanges': '/exchanges'
                }
            },
            
            # Blockchain.info - 거래량 패턴 분석
            'blockchain': {
                'base_url': 'https://api.blockchain.info',
                'endpoints': {
                    'stats': '/stats',
                    'pools': '/pools'
                }
            },
            
            # CoinMarketCap (무료 제한) - 기관 관련 지표만
            'coinmarketcap': {
                'base_url': 'https://pro-api.coinmarketcap.com/v1',
                'endpoints': {
                    'global_metrics': '/global-metrics/quotes/latest'
                }
            }
        }
    
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
                    logger.info(f"기관 투자 분석 모델 {model_name} 초기화 성공")
                    return client, model_name
                    
                except Exception as e:
                    logger.warning(f"기관 투자 분석 모델 {model_name} 초기화 실패: {e}")
                    continue
            
            logger.error("기관 투자 분석용 모든 모델 초기화 실패")
            return None, None
            
        except Exception as e:
            logger.error(f"기관 투자 분석 모델 초기화 중 전체 오류: {e}")
            return None, None
    
    def get_corporate_holdings_data(self) -> Dict:
        """기업 BTC 보유량 데이터 (캐싱 권장: 6시간)"""
        try:
            url = f"{self.data_sources['coingecko']['base_url']}/companies/public_treasury/bitcoin"
            response = requests.get(url, headers=get_coingecko_headers(), timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if 'companies' in data:
                companies = data['companies']
                
                # 기업별 보유량 분석
                total_holdings = sum(company.get('total_holdings', 0) for company in companies)
                total_companies = len(companies)
                
                # 상위 기업들
                top_holders = sorted(companies, key=lambda x: x.get('total_holdings', 0), reverse=True)[:10]
                
                # 최근 변화 추정 (보유량 기준)
                large_holders = [c for c in companies if c.get('total_holdings', 0) > 10000]
                medium_holders = [c for c in companies if 1000 <= c.get('total_holdings', 0) <= 10000]
                small_holders = [c for c in companies if c.get('total_holdings', 0) < 1000]
                
                return {
                    'total_corporate_btc': total_holdings,
                    'total_companies': total_companies,
                    'large_holders_count': len(large_holders),
                    'medium_holders_count': len(medium_holders),
                    'small_holders_count': len(small_holders),
                    'top_10_holdings': sum(h.get('total_holdings', 0) for h in top_holders),
                    'concentration_ratio': (sum(h.get('total_holdings', 0) for h in top_holders) / total_holdings * 100) if total_holdings > 0 else 0,
                    'average_holding': total_holdings / total_companies if total_companies > 0 else 0,
                    'institutional_adoption_level': min(100, (total_companies / 100 + total_holdings / 1000000) * 50),
                    'top_holders': [{'name': h.get('name', ''), 'holdings': h.get('total_holdings', 0)} for h in top_holders[:5]],
                    'timestamp': datetime.now().isoformat(),
                    'source': 'coingecko',
                    'cache_ttl': self.cache_ttl['corporate_holdings']
                }
            else:
                raise ValueError("기업 보유량 데이터 형식 오류")
                
        except Exception as e:
            logger.error(f"기업 BTC 보유량 데이터 수집 실패: {e}")
            self.error_counts['corporate_holdings'] += 1
            return self._get_cached_corporate_holdings()
    
    def get_institutional_volume_patterns(self) -> Dict:
        """기관 거래량 패턴 분석 (캐싱 권장: 2시간)"""
        try:
            # CoinGecko에서 BTC 시장 데이터
            url = f"{self.data_sources['coingecko']['base_url']}/coins/bitcoin/market_chart"
            params = {
                'vs_currency': 'usd',
                'days': '30',
                'interval': 'daily'
            }
            
            response = requests.get(url, params=params, headers=get_coingecko_headers(), timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if 'total_volumes' in data and 'prices' in data:
                volumes = [v[1] for v in data['total_volumes']]
                prices = [p[1] for p in data['prices']]
                
                # 거래량 패턴 분석
                recent_7d_volume = sum(volumes[-7:]) / 7 if len(volumes) >= 7 else volumes[-1] if volumes else 0
                previous_7d_volume = sum(volumes[-14:-7]) / 7 if len(volumes) >= 14 else recent_7d_volume
                
                # 기관 거래량 추정 (큰 거래량 = 기관 활동)
                high_volume_days = len([v for v in volumes[-30:] if v > recent_7d_volume * 1.5])
                volume_volatility = (max(volumes[-30:]) - min(volumes[-30:])) / max(volumes[-30:]) if volumes else 0
                
                # 가격 대비 거래량 분석
                price_volume_correlation = self._calculate_correlation(prices[-30:], volumes[-30:]) if len(prices) >= 30 else 0
                
                # 기관 활동 추정
                institutional_activity_score = min(100, (
                    (recent_7d_volume / 50000000000 * 30) +  # 거래량 크기
                    (high_volume_days / 30 * 100 * 30) +      # 고거래량 빈도
                    ((1 - volume_volatility) * 40)            # 안정적 거래량 = 기관
                ))
                
                return {
                    'recent_7d_avg_volume': recent_7d_volume,
                    'volume_trend': 'Increasing' if recent_7d_volume > previous_7d_volume * 1.1 else 'Decreasing' if recent_7d_volume < previous_7d_volume * 0.9 else 'Stable',
                    'high_volume_days_30d': high_volume_days,
                    'volume_volatility': round(volume_volatility, 3),
                    'price_volume_correlation': round(price_volume_correlation, 3),
                    'institutional_activity_score': round(institutional_activity_score, 1),
                    'large_block_trading': 'High' if high_volume_days > 10 else 'Low' if high_volume_days < 3 else 'Medium',
                    'institutional_flow_direction': 'Accumulation' if price_volume_correlation < -0.3 else 'Distribution' if price_volume_correlation > 0.3 else 'Neutral',
                    'timestamp': datetime.now().isoformat(),
                    'source': 'coingecko_analysis',
                    'cache_ttl': self.cache_ttl['institutional_volume']
                }
            else:
                raise ValueError("거래량 데이터 부족")
                
        except Exception as e:
            logger.error(f"기관 거래량 패턴 분석 실패: {e}")
            self.error_counts['volume_patterns'] += 1
            return self._get_cached_volume_patterns()
    
    def get_market_structure_indicators(self) -> Dict:
        """시장 구조 지표 (캐싱 권장: 1시간)"""
        try:
            # CoinGecko 글로벌 데이터
            url = f"{self.data_sources['coingecko']['base_url']}/global"
            response = requests.get(url, headers=get_coingecko_headers(), timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if 'data' in data:
                global_data = data['data']
                
                # 시장 구조 분석
                btc_dominance = global_data.get('market_cap_percentage', {}).get('btc', 0)
                eth_dominance = global_data.get('market_cap_percentage', {}).get('eth', 0)
                total_market_cap = global_data.get('total_market_cap', {}).get('usd', 0)
                
                # DeFi 비율 (기관 vs 소매 투자 구분)
                defi_ratio = global_data.get('defi_market_cap', 0) / total_market_cap if total_market_cap > 0 else 0
                
                # 기관 선호도 지표
                institutional_preference_score = min(100, (
                    (btc_dominance / 70 * 40) +               # BTC 도미넌스 (기관 선호)
                    ((100 - defi_ratio * 100) / 100 * 30) +  # DeFi 비율 낮을수록 기관적
                    (min(total_market_cap / 3000000000000, 1) * 30)  # 시총 성숙도
                ))
                
                # 시장 성숙도
                market_maturity = 'High' if btc_dominance > 60 and total_market_cap > 2000000000000 else 'Low' if btc_dominance < 45 else 'Medium'
                
                return {
                    'btc_dominance': round(btc_dominance, 2),
                    'eth_dominance': round(eth_dominance, 2),
                    'alt_dominance': round(100 - btc_dominance - eth_dominance, 2),
                    'total_market_cap': total_market_cap,
                    'defi_ratio': round(defi_ratio * 100, 2),
                    'institutional_preference_score': round(institutional_preference_score, 1),
                    'market_maturity': market_maturity,
                    'institutional_vs_retail': 'Institutional Driven' if btc_dominance > 65 else 'Retail Driven' if btc_dominance < 50 else 'Balanced',
                    'market_concentration': 'Concentrated' if btc_dominance + eth_dominance > 75 else 'Diversified',
                    'timestamp': datetime.now().isoformat(),
                    'source': 'coingecko',
                    'cache_ttl': self.cache_ttl['market_structure']
                }
            else:
                raise ValueError("시장 구조 데이터 형식 오류")
                
        except Exception as e:
            logger.error(f"시장 구조 지표 수집 실패: {e}")
            self.error_counts['market_structure'] += 1
            return self._get_cached_market_structure()
    
    def get_derivatives_flow_estimation(self) -> Dict:
        """파생상품 플로우 추정 (캐싱 권장: 2시간)"""
        try:
            # CoinGecko에서 BTC 상세 데이터
            url = f"{self.data_sources['coingecko']['base_url']}/coins/bitcoin"
            params = {
                'localization': 'false',
                'tickers': 'true',
                'market_data': 'true',
                'community_data': 'false',
                'developer_data': 'false'
            }
            
            response = requests.get(url, params=params, headers=get_coingecko_headers(), timeout=10)
            response.raise_for_status()
            data = response.json()
            
            market_data = data.get('market_data', {})
            tickers = data.get('tickers', [])
            
            # 현물 vs 선물 거래량 분석
            spot_volume = 0
            futures_volume = 0
            
            for ticker in tickers[:50]:  # 상위 50개 거래소
                volume_usd = ticker.get('converted_volume', {}).get('usd', 0)
                market_type = ticker.get('market', {}).get('name', '').lower()
                
                if 'perp' in market_type or 'future' in market_type or 'swap' in market_type:
                    futures_volume += volume_usd
                else:
                    spot_volume += volume_usd
            
            total_volume = spot_volume + futures_volume
            futures_ratio = futures_volume / total_volume if total_volume > 0 else 0
            
            # 기관 파생상품 활동 추정
            institutional_derivatives_score = min(100, (
                (futures_ratio * 60) +                        # 선물 비율 (기관 활동)
                (min(total_volume / 30000000000, 1) * 40)      # 총 거래량 (기관 참여도)
            ))
            
            # 현재 가격 변동성으로 옵션 활동 추정
            current_price = market_data.get('current_price', {}).get('usd', 0)
            price_change_24h = market_data.get('price_change_percentage_24h', 0)
            
            implied_vol_estimate = min(100, abs(price_change_24h) * 3)  # 단순 추정
            
            return {
                'spot_volume_24h': spot_volume,
                'futures_volume_24h': futures_volume,
                'futures_to_spot_ratio': round(futures_ratio, 3),
                'total_derivatives_volume': futures_volume,
                'institutional_derivatives_score': round(institutional_derivatives_score, 1),
                'derivatives_market_type': 'Institutional Heavy' if futures_ratio > 0.6 else 'Retail Heavy' if futures_ratio < 0.3 else 'Balanced',
                'implied_volatility_estimate': round(implied_vol_estimate, 2),
                'options_activity_estimate': 'High' if implied_vol_estimate > 15 else 'Low' if implied_vol_estimate < 5 else 'Medium',
                'institutional_hedging': 'Active' if futures_ratio > 0.5 and institutional_derivatives_score > 70 else 'Passive',
                'timestamp': datetime.now().isoformat(),
                'source': 'coingecko_estimation',
                'cache_ttl': self.cache_ttl['derivatives_flow']
            }
            
        except Exception as e:
            logger.error(f"파생상품 플로우 추정 실패: {e}")
            self.error_counts['derivatives_flow'] += 1
            return self._get_cached_derivatives_flow()
    
    def get_exchange_institutional_indicators(self) -> Dict:
        """거래소 기관 지표 (캐싱 권장: 2시간)"""
        try:
            # CoinGecko 거래소 데이터
            url = f"{self.data_sources['coingecko']['base_url']}/exchanges"
            params = {'per_page': 20, 'page': 1}
            
            response = requests.get(url, params=params, headers=get_coingecko_headers(), timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if isinstance(data, list):
                # 기관용 거래소 vs 소매용 거래소 구분
                institutional_exchanges = ['coinbase-pro', 'kraken', 'bitstamp', 'gemini', 'itbit']
                retail_exchanges = ['binance', 'okex', 'huobi', 'kucoin']
                
                institutional_volume = 0
                retail_volume = 0
                total_volume = 0
                
                for exchange in data:
                    exchange_id = exchange.get('id', '')
                    volume_btc = exchange.get('trade_volume_24h_btc', 0)
                    
                    total_volume += volume_btc
                    
                    if exchange_id in institutional_exchanges:
                        institutional_volume += volume_btc
                    elif exchange_id in retail_exchanges:
                        retail_volume += volume_btc
                
                institutional_ratio = institutional_volume / total_volume if total_volume > 0 else 0
                
                # 기관 거래소 활동 점수
                institutional_exchange_score = min(100, (
                    (institutional_ratio * 70) +
                    (min(institutional_volume / 100000, 1) * 30)
                ))
                
                return {
                    'institutional_exchange_volume': institutional_volume,
                    'retail_exchange_volume': retail_volume,
                    'total_exchange_volume': total_volume,
                    'institutional_volume_ratio': round(institutional_ratio, 3),
                    'institutional_exchange_score': round(institutional_exchange_score, 1),
                    'exchange_flow_type': 'Institutional Driven' if institutional_ratio > 0.4 else 'Retail Driven' if institutional_ratio < 0.2 else 'Mixed',
                    'top_institutional_exchanges': institutional_exchanges[:3],
                    'market_access_pattern': 'Professional' if institutional_ratio > 0.3 else 'Retail',
                    'timestamp': datetime.now().isoformat(),
                    'source': 'coingecko',
                    'cache_ttl': self.cache_ttl['institutional_volume']
                }
            else:
                raise ValueError("거래소 데이터 형식 오류")
                
        except Exception as e:
            logger.error(f"거래소 기관 지표 수집 실패: {e}")
            return self._get_cached_exchange_indicators()
    
    def _calculate_correlation(self, x: List[float], y: List[float]) -> float:
        """간단한 상관관계 계산"""
        try:
            if len(x) != len(y) or len(x) < 2:
                return 0
            
            n = len(x)
            sum_x = sum(x)
            sum_y = sum(y)
            sum_xy = sum(x[i] * y[i] for i in range(n))
            sum_x2 = sum(xi ** 2 for xi in x)
            sum_y2 = sum(yi ** 2 for yi in y)
            
            numerator = n * sum_xy - sum_x * sum_y
            denominator = ((n * sum_x2 - sum_x ** 2) * (n * sum_y2 - sum_y ** 2)) ** 0.5
            
            return numerator / denominator if denominator != 0 else 0
        except:
            return 0
    
    def _get_cached_corporate_holdings(self) -> Optional[Dict]:
        """MongoDB에서 과거 기업 보유량 데이터 가져오기"""
        try:
            from pymongo import MongoClient
            from datetime import datetime, timezone, timedelta
            
            client = MongoClient("mongodb://mongodb:27017")
            db = client["bitcoin"]
            cache_collection = db["data_cache"]
            
            # 최근 12시간 이내 데이터 찾기
            twelve_hours_ago = datetime.now(timezone.utc) - timedelta(hours=12)
            
            cached_data = cache_collection.find_one({
                "task_name": "institutional_data",
                "created_at": {"$gte": twelve_hours_ago}
            }, sort=[("created_at", -1)])
            
            if cached_data and cached_data.get('data', {}).get('corporate_holdings'):
                holdings_data = cached_data['data']['corporate_holdings']
                return {
                    'total_corporate_btc': holdings_data.get('total_corporate_btc'),
                    'total_companies': holdings_data.get('total_companies'),
                    'large_holders_count': holdings_data.get('large_holders_count'),
                    'medium_holders_count': holdings_data.get('medium_holders_count'),
                    'small_holders_count': holdings_data.get('small_holders_count'),
                    'top_10_holdings': holdings_data.get('top_10_holdings'),
                    'concentration_ratio': holdings_data.get('concentration_ratio'),
                    'average_holding': holdings_data.get('average_holding'),
                    'institutional_adoption_level': holdings_data.get('institutional_adoption_level'),
                    'top_holders': holdings_data.get('top_holders', []),
                    'timestamp': cached_data['created_at'].isoformat(),
                    'source': 'cached_data',
                    'cache_ttl': self.cache_ttl['corporate_holdings']
                }
            
            logger.warning("기업 보유량: 캐시된 데이터 없음")
            return None
            
        except Exception as e:
            logger.error(f"캐시된 기업 보유량 데이터 조회 실패: {e}")
            return None
    
    def _get_cached_volume_patterns(self) -> Optional[Dict]:
        """MongoDB에서 과거 거래량 패턴 데이터 가져오기"""
        logger.warning("거래량 패턴: 캐시된 데이터 없음")
        return None
    
    def _get_cached_market_structure(self) -> Optional[Dict]:
        """MongoDB에서 과거 시장 구조 데이터 가져오기"""
        logger.warning("시장 구조: 캐시된 데이터 없음")
        return None
    
    def _get_cached_derivatives_flow(self) -> Optional[Dict]:
        """MongoDB에서 과거 파생상품 플로우 데이터 가져오기"""
        logger.warning("파생상품 플로우: 캐시된 데이터 없음")
        return None
    
    def _get_cached_exchange_indicators(self) -> Optional[Dict]:
        """MongoDB에서 과거 거래소 지표 데이터 가져오기"""
        logger.warning("거래소 지표: 캐시된 데이터 없음")
        return None
    
    def check_data_availability(self) -> bool:
        """데이터 사용 가능 여부 확인"""
        failed_sources = sum(1 for count in self.error_counts.values() if count >= self.max_errors)
        if failed_sources >= 3:  # 4개 소스 중 3개 이상 실패시 불가
            return False
        return True
    
    def collect_institutional_data(self) -> Dict:
        """기관 투자 데이터 종합 수집"""
        try:
            logger.info("기관 투자 데이터 수집 시작")
            
            institutional_data = {}
            success_count = 0
            total_categories = 5
            
            # 1. 기업 BTC 보유량
            try:
                corporate_holdings = self.get_corporate_holdings_data()
                institutional_data['corporate_holdings'] = corporate_holdings
                if 'error' not in corporate_holdings:
                    success_count += 1
                logger.info(f"✅ 기업보유량: {corporate_holdings.get('total_companies', 'N/A')}개사, {corporate_holdings.get('total_corporate_btc', 'N/A'):,.0f} BTC")
            except Exception as e:
                logger.error(f"❌ 기업보유량 수집 실패: {e}")
                institutional_data['corporate_holdings'] = self._get_cached_corporate_holdings()
            
            # 2. 기관 거래량 패턴
            try:
                volume_patterns = self.get_institutional_volume_patterns()
                institutional_data['volume_patterns'] = volume_patterns
                if 'error' not in volume_patterns:
                    success_count += 1
                logger.info(f"✅ 거래량패턴: {volume_patterns.get('institutional_activity_score', 'N/A')}점, {volume_patterns.get('volume_trend', 'N/A')}")
            except Exception as e:
                logger.error(f"❌ 거래량패턴 수집 실패: {e}")
                institutional_data['volume_patterns'] = self._get_cached_volume_patterns()
            
            # 3. 시장 구조
            try:
                market_structure = self.get_market_structure_indicators()
                institutional_data['market_structure'] = market_structure
                if 'error' not in market_structure:
                    success_count += 1
                logger.info(f"✅ 시장구조: BTC {market_structure.get('btc_dominance', 'N/A')}%, 기관선호도 {market_structure.get('institutional_preference_score', 'N/A')}")
            except Exception as e:
                logger.error(f"❌ 시장구조 수집 실패: {e}")
                institutional_data['market_structure'] = self._get_cached_market_structure()
            
            # 4. 파생상품 플로우
            try:
                derivatives_flow = self.get_derivatives_flow_estimation()
                institutional_data['derivatives_flow'] = derivatives_flow
                if 'error' not in derivatives_flow:
                    success_count += 1
                logger.info(f"✅ 파생상품: 선물비율 {derivatives_flow.get('futures_to_spot_ratio', 'N/A'):.2f}, 기관점수 {derivatives_flow.get('institutional_derivatives_score', 'N/A')}")
            except Exception as e:
                logger.error(f"❌ 파생상품 수집 실패: {e}")
                institutional_data['derivatives_flow'] = self._get_cached_derivatives_flow()
            
            # 5. 거래소 기관 지표
            try:
                exchange_indicators = self.get_exchange_institutional_indicators()
                institutional_data['exchange_indicators'] = exchange_indicators
                if 'error' not in exchange_indicators:
                    success_count += 1
                logger.info(f"✅ 거래소지표: 기관비율 {exchange_indicators.get('institutional_volume_ratio', 'N/A'):.2f}, {exchange_indicators.get('exchange_flow_type', 'N/A')}")
            except Exception as e:
                logger.error(f"❌ 거래소지표 수집 실패: {e}")
                institutional_data['exchange_indicators'] = self._get_cached_exchange_indicators()
            
            # 수집 통계
            success_rate = (success_count / total_categories) * 100
            institutional_data['collection_stats'] = {
                'timestamp': datetime.now().isoformat(),
                'total_categories': total_categories,
                'successful_categories': success_count,
                'success_rate': round(success_rate, 1),
                'data_sources': ['coingecko', 'blockchain_info', 'estimated_calculations'],
                'cache_recommendations': {
                    'corporate_holdings': f"{self.cache_ttl['corporate_holdings']}초",
                    'volume_patterns': f"{self.cache_ttl['institutional_volume']}초",
                    'market_structure': f"{self.cache_ttl['market_structure']}초",
                    'derivatives_flow': f"{self.cache_ttl['derivatives_flow']}초",
                    'exchange_indicators': f"{self.cache_ttl['institutional_volume']}초"
                }
            }
            
            logger.info(f"기관 투자 데이터 수집 완료: {success_count}/{total_categories} 성공 ({success_rate:.1f}%)")
            return institutional_data
            
        except Exception as e:
            logger.error(f"기관 투자 데이터 수집 중 전체 오류: {e}")
            return self._get_cached_complete_institutional_data()
    
    def _get_cached_complete_institutional_data(self) -> Dict:
        """전체 실패시 캐시된 데이터 사용"""
        return {
            'corporate_holdings': self._get_cached_corporate_holdings(),
            'volume_patterns': self._get_cached_volume_patterns(),
            'market_structure': self._get_cached_market_structure(),
            'derivatives_flow': self._get_cached_derivatives_flow(),
            'exchange_indicators': self._get_cached_exchange_indicators(),
            'collection_stats': {
                'timestamp': datetime.now().isoformat(),
                'total_categories': 5,
                'successful_categories': 0,
                'success_rate': 0.0,
                'note': '모든 API 실패 - 캐시된 데이터 사용'
            }
        }
    
    def analyze_institutional_signals(self, institutional_data: Dict) -> Dict:
        """기관 투자 신호 분석 (규칙 기반)"""
        try:
            # 기업 보유량 분석
            corporate = institutional_data.get('corporate_holdings', {})
            total_corporate_btc = corporate.get('total_corporate_btc', 1850000)
            total_companies = corporate.get('total_companies', 45)
            adoption_level = corporate.get('institutional_adoption_level', 78)
            
            # 거래량 패턴 분석
            volume = institutional_data.get('volume_patterns', {})
            institutional_activity_score = volume.get('institutional_activity_score', 72)
            flow_direction = volume.get('institutional_flow_direction', 'Neutral')
            
            # 시장 구조 분석
            structure = institutional_data.get('market_structure', {})
            btc_dominance = structure.get('btc_dominance', 62.5)
            institutional_preference = structure.get('institutional_preference_score', 75)
            market_maturity = structure.get('market_maturity', 'Medium')
            
            # 파생상품 분석
            derivatives = institutional_data.get('derivatives_flow', {})
            derivatives_score = derivatives.get('institutional_derivatives_score', 68)
            futures_ratio = derivatives.get('futures_to_spot_ratio', 0.58)
            
            # 거래소 분석
            exchange = institutional_data.get('exchange_indicators', {})
            exchange_score = exchange.get('institutional_exchange_score', 65)
            institutional_volume_ratio = exchange.get('institutional_volume_ratio', 0.35)
            
            # 기관 투자 종합 점수 계산 (0-100)
            institutional_score = 0
            
            # 1. 기업 채택도 (25점 만점)
            if adoption_level > 85:
                institutional_score += 25
            elif adoption_level > 70:
                institutional_score += 20
            elif adoption_level > 55:
                institutional_score += 15
            elif adoption_level > 40:
                institutional_score += 10
            else:
                institutional_score += 5
            
            # 2. 기관 거래 활동 (20점 만점)
            if institutional_activity_score > 80:
                institutional_score += 20
            elif institutional_activity_score > 65:
                institutional_score += 16
            elif institutional_activity_score > 50:
                institutional_score += 12
            elif institutional_activity_score > 35:
                institutional_score += 8
            else:
                institutional_score += 4
            
            # 3. 시장 선호도 (20점 만점)
            if institutional_preference > 80:
                institutional_score += 20
            elif institutional_preference > 65:
                institutional_score += 16
            elif institutional_preference > 50:
                institutional_score += 12
            elif institutional_preference > 35:
                institutional_score += 8
            else:
                institutional_score += 4
            
            # 4. 파생상품 활동 (20점 만점)
            if derivatives_score > 75:
                institutional_score += 20
            elif derivatives_score > 60:
                institutional_score += 16
            elif derivatives_score > 45:
                institutional_score += 12
            elif derivatives_score > 30:
                institutional_score += 8
            else:
                institutional_score += 4
            
            # 5. 거래소 기관 비중 (15점 만점)
            if institutional_volume_ratio > 0.5:
                institutional_score += 15
            elif institutional_volume_ratio > 0.4:
                institutional_score += 12
            elif institutional_volume_ratio > 0.3:
                institutional_score += 9
            elif institutional_volume_ratio > 0.2:
                institutional_score += 6
            else:
                institutional_score += 3
            
            # 신호 강도 분류
            if institutional_score >= 85:
                signal_strength = "매우 강함"
                institution_signal = "Strong Institutional Buy"
            elif institutional_score >= 70:
                signal_strength = "강함"
                institution_signal = "Institutional Buy"
            elif institutional_score >= 50:
                signal_strength = "중립"
                institution_signal = "Institutional Hold"
            elif institutional_score >= 30:
                signal_strength = "약함"
                institution_signal = "Institutional Caution"
            else:
                signal_strength = "매우 약함"
                institution_signal = "Institutional Sell"
            
            return {
                'institutional_score': round(institutional_score, 1),
                'signal_strength': signal_strength,
                'institution_signal': institution_signal,
                'corporate_adoption': {
                    'total_companies': total_companies,
                    'total_holdings': total_corporate_btc,
                    'adoption_level': adoption_level,
                    'adoption_trend': 'Growing' if total_companies > 40 else 'Stable',
                    'concentration': 'High' if corporate.get('concentration_ratio', 65) > 70 else 'Medium'
                },
                'institutional_activity': {
                    'activity_score': institutional_activity_score,
                    'flow_direction': flow_direction,
                    'trading_pattern': 'Accumulation' if flow_direction == 'Accumulation' else 'Distribution' if flow_direction == 'Distribution' else 'Neutral',
                    'volume_trend': volume.get('volume_trend', 'Stable')
                },
                'market_positioning': {
                    'btc_preference': btc_dominance,
                    'preference_score': institutional_preference,
                    'market_maturity': market_maturity,
                    'positioning': 'BTC Focused' if btc_dominance > 65 else 'Diversified' if btc_dominance < 55 else 'Balanced'
                },
                'derivatives_usage': {
                    'derivatives_score': derivatives_score,
                    'futures_dominance': futures_ratio,
                    'hedging_activity': derivatives.get('institutional_hedging', 'Active'),
                    'sophistication': 'High' if derivatives_score > 70 else 'Medium' if derivatives_score > 50 else 'Low'
                },
                'exchange_patterns': {
                    'institutional_ratio': institutional_volume_ratio,
                    'exchange_score': exchange_score,
                    'flow_type': exchange.get('exchange_flow_type', 'Mixed'),
                    'access_pattern': exchange.get('market_access_pattern', 'Professional')
                },
                'key_signals': self._identify_institutional_signals(institutional_data, institutional_score),
                'growth_drivers': self._identify_growth_drivers(institutional_data),
                'risk_factors': self._identify_institutional_risks(institutional_data),
                'data_reliability': {
                    'success_rate': institutional_data.get('collection_stats', {}).get('success_rate', 0),
                    'confidence': 'High' if institutional_data.get('collection_stats', {}).get('success_rate', 0) > 80 else 'Medium' if institutional_data.get('collection_stats', {}).get('success_rate', 0) > 50 else 'Low'
                }
            }
            
        except Exception as e:
            logger.error(f"기관 투자 신호 분석 중 오류: {e}")
            return {
                'institutional_score': 50.0,
                'signal_strength': '중립',
                'institution_signal': 'Institutional Hold',
                'error': str(e),
                'data_reliability': {'success_rate': 0, 'confidence': 'None'}
            }
    
    def _identify_institutional_signals(self, institutional_data: Dict, score: float) -> List[str]:
        """주요 기관 투자 신호들 식별"""
        signals = []
        
        corporate = institutional_data.get('corporate_holdings', {})
        total_companies = corporate.get('total_companies', 45)
        if total_companies > 50:
            signals.append(f"기업 채택 확산 ({total_companies}개사) - 기관 관심 증가")
        
        volume = institutional_data.get('volume_patterns', {})
        activity_score = volume.get('institutional_activity_score', 72)
        if activity_score > 80:
            signals.append(f"높은 기관 거래 활동 ({activity_score}점) - 적극적 포지셔닝")
        
        structure = institutional_data.get('market_structure', {})
        btc_dominance = structure.get('btc_dominance', 62.5)
        if btc_dominance > 65:
            signals.append(f"높은 BTC 도미넌스 ({btc_dominance:.1f}%) - 기관 BTC 선호")
        
        derivatives = institutional_data.get('derivatives_flow', {})
        futures_ratio = derivatives.get('futures_to_spot_ratio', 0.58)
        if futures_ratio > 0.6:
            signals.append(f"높은 선물 비율 ({futures_ratio:.2f}) - 기관 헷징 활발")
        
        if score > 75:
            signals.append("기관 투자 지표 종합: 강한 기관 자금 유입 신호")
        
        return signals if signals else ["현재 뚜렷한 기관 투자 신호 없음"]
    
    def _identify_growth_drivers(self, institutional_data: Dict) -> List[str]:
        """기관 투자 성장 동력들"""
        drivers = []
        
        corporate = institutional_data.get('corporate_holdings', {})
        adoption_level = corporate.get('institutional_adoption_level', 78)
        if adoption_level > 80:
            drivers.append(f"높은 기관 채택 수준 ({adoption_level:.1f}) - 성숙한 투자 환경")
        
        structure = institutional_data.get('market_structure', {})
        market_maturity = structure.get('market_maturity', 'Medium')
        if market_maturity == 'High':
            drivers.append("높은 시장 성숙도 - 기관 투자 적합성 증가")
        
        derivatives = institutional_data.get('derivatives_flow', {})
        hedging = derivatives.get('institutional_hedging', 'Active')
        if hedging == 'Active':
            drivers.append("활발한 기관 헷징 - 리스크 관리 도구 활용")
        
        exchange = institutional_data.get('exchange_indicators', {})
        access_pattern = exchange.get('market_access_pattern', 'Professional')
        if access_pattern == 'Professional':
            drivers.append("전문적 시장 접근 - 기관 인프라 구축")
        
        return drivers if drivers else ["현재 특별한 성장 동력 없음"]
    
    def _identify_institutional_risks(self, institutional_data: Dict) -> List[str]:
        """기관 투자 리스크 요인들"""
        risks = []
        
        corporate = institutional_data.get('corporate_holdings', {})
        concentration = corporate.get('concentration_ratio', 65)
        if concentration > 80:
            risks.append(f"높은 보유 집중도 ({concentration:.1f}%) - 대형 매도 위험")
        
        volume = institutional_data.get('volume_patterns', {})
        flow_direction = volume.get('institutional_flow_direction', 'Neutral')
        if flow_direction == 'Distribution':
            risks.append("기관 자금 유출 패턴 - 매도 압력 가능성")
        
        structure = institutional_data.get('market_structure', {})
        btc_dominance = structure.get('btc_dominance', 62.5)
        if btc_dominance < 50:
            risks.append(f"낮은 BTC 도미넌스 ({btc_dominance:.1f}%) - 기관 관심 분산")
        
        derivatives = institutional_data.get('derivatives_flow', {})
        vol_estimate = derivatives.get('implied_volatility_estimate', 12.5)
        if vol_estimate > 20:
            risks.append(f"높은 변동성 ({vol_estimate:.1f}) - 기관 투자 위축")
        
        return risks if risks else ["현재 특별한 기관 투자 리스크 없음"]
    
    async def analyze_with_ai(self, institutional_data: Dict) -> Dict:
        """AI 모델을 사용하여 기관 투자 종합 분석"""
        if self.client is None:
            self.client, self.model_name = self.get_model()
        
        if self.client is None:
            logger.warning("AI 모델이 없어 규칙 기반 분석으로 대체합니다.")
            return self.rule_based_analysis(institutional_data)
        
        try:
            # 기관 투자 분석용 프롬프트 사용
            prompt = CONFIG["prompts"]["institutional_analysis"].format(
                institutional_data=json.dumps(institutional_data, ensure_ascii=False, indent=2)
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
                    'data_success_rate': institutional_data.get('collection_stats', {}).get('success_rate', 0),
                    'cache_info': institutional_data.get('collection_stats', {}).get('cache_recommendations', {}),
                    'raw_data': institutional_data
                }
                
                return result_json
            else:
                logger.error("AI 응답에서 JSON을 찾을 수 없습니다.")
                return self.rule_based_analysis(institutional_data)
                
        except Exception as e:
            logger.error(f"AI 기관 투자 분석 중 오류: {e}")
            return self.rule_based_analysis(institutional_data)
    
    def rule_based_analysis(self, institutional_data: Dict) -> Dict:
        """규칙 기반 기관 투자 분석 (AI 모델 없을 때 백업)"""
        try:
            # 기관 투자 신호 분석
            signal_analysis = self.analyze_institutional_signals(institutional_data)
            
            institutional_score = signal_analysis.get('institutional_score', 50.0)
            institution_signal = signal_analysis.get('institution_signal', 'Institutional Hold')
            
            # 투자 신호 매핑
            signal_mapping = {
                'Strong Institutional Buy': 'Strong Institutional Buy',
                'Institutional Buy': 'Institutional Buy',
                'Institutional Hold': 'Hold',
                'Institutional Caution': 'Institutional Sell',
                'Institutional Sell': 'Strong Institutional Sell'
            }
            
            investment_signal = signal_mapping.get(institution_signal, 'Hold')
            
            # 분석 결과 구성
            result = {
                "institutional_flow_score": institutional_score,
                "investment_signal": investment_signal,
                "corporate_adoption_analysis": f"기업 채택: {signal_analysis.get('corporate_adoption', {}).get('total_companies', 45)}개사, 보유량: {signal_analysis.get('corporate_adoption', {}).get('total_holdings', 1850000):,.0f} BTC",
                "institutional_trading_patterns": f"기관 거래 활동도: {signal_analysis.get('institutional_activity', {}).get('activity_score', 72)}점, 흐름: {signal_analysis.get('institutional_activity', {}).get('flow_direction', 'Neutral')}",
                "market_structure_impact": f"BTC 도미넌스: {signal_analysis.get('market_positioning', {}).get('btc_preference', 62.5):.1f}%, 기관 선호도: {signal_analysis.get('market_positioning', {}).get('preference_score', 75)}점",
                "derivatives_sophistication": f"파생상품 점수: {signal_analysis.get('derivatives_usage', {}).get('derivatives_score', 68)}점, 선물 비율: {signal_analysis.get('derivatives_usage', {}).get('futures_dominance', 0.58):.2f}",
                "exchange_institutional_flow": f"기관 거래소 비중: {signal_analysis.get('exchange_patterns', {}).get('institutional_ratio', 0.35):.2f}, 패턴: {signal_analysis.get('exchange_patterns', {}).get('flow_type', 'Mixed')}",
                "key_insights": signal_analysis.get('key_signals', [])[:5],
                "growth_catalysts": "; ".join(signal_analysis.get('growth_drivers', ['현재 특별한 성장 동력 없음'])[:3]),
                "institutional_risks": "; ".join(signal_analysis.get('risk_factors', ['현재 특별한 리스크 없음'])[:3]),
                "adoption_outlook": f"기관 채택 전망: {signal_analysis.get('corporate_adoption', {}).get('adoption_trend', 'Stable')}",
                "confidence": max(50, min(95, int(institutional_score + signal_analysis.get('data_reliability', {}).get('success_rate', 0) * 0.3))),
                "analysis_summary": f"기관 투자 흐름 점수 {institutional_score:.1f}점으로 '{signal_analysis.get('signal_strength', '중립')}' 신호. 투자 권장: {investment_signal}"
            }
            
            # 메타데이터 추가
            result['analysis_metadata'] = {
                'analysis_type': 'rule_based',
                'data_timestamp': datetime.now(timezone.utc).isoformat(),
                'model_used': 'rule_based_fallback',
                'data_success_rate': institutional_data.get('collection_stats', {}).get('success_rate', 0),
                'cache_info': institutional_data.get('collection_stats', {}).get('cache_recommendations', {}),
                'raw_data': institutional_data
            }
            
            return result
            
        except Exception as e:
            logger.error(f"규칙 기반 기관 투자 분석 중 오류: {e}")
            return {
                "institutional_flow_score": 50.0,
                "investment_signal": "Hold",
                "error": str(e),
                "confidence": 0,
                "analysis_summary": f"기관 투자 분석 중 오류 발생: {str(e)}"
            }
    
    async def analyze_institutional_flow(self) -> Dict:
        """기관 투자 흐름 분석 메인 함수"""
        try:
            logger.info("기관 투자 흐름 분석 시작")
            
            # 데이터 사용 가능 여부 확인
            if not self.check_data_availability():
                logger.warning("기관 분석: 대부분의 데이터 소스 실패 - 분석 건너뛰기")
                return {
                    "success": False,
                    "error": "대부분의 데이터 소스에서 연속 실패 - 분석 불가",
                    "analysis_type": "institutional_flow",
                    "skip_reason": "insufficient_data"
                }
            
            # 1. 기관 투자 데이터 수집
            institutional_raw_data = self.collect_institutional_data()
            
            # 데이터 유효성 검사
            if institutional_raw_data is None:
                logger.warning("기관 분석: 사용 가능한 데이터 없음")
                return {
                    "success": False,
                    "error": "유효한 데이터 없음 - 분석 불가",
                    "analysis_type": "institutional_flow",
                    "skip_reason": "no_valid_data"
                }
            
            # 2. 기관 투자 신호 분석
            signal_analysis = self.analyze_institutional_signals(institutional_raw_data)
            
            # 3. 데이터 통합
            comprehensive_data = {
                'raw_data': institutional_raw_data,
                'signal_analysis': signal_analysis,
                'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                'data_quality': {
                    'error_counts': self.error_counts.copy()
                }
            }
            
            # 4. AI 종합 분석
            analysis_result = await self.analyze_with_ai(comprehensive_data)
            
            logger.info("기관 투자 흐름 분석 완료")
            
            return {
                "success": True,
                "result": analysis_result,
                "analysis_type": "institutional_flow",
                "data_quality": {
                    "success_rate": institutional_raw_data.get('collection_stats', {}).get('success_rate', 0),
                    "total_categories": institutional_raw_data.get('collection_stats', {}).get('total_categories', 0),
                    "successful_categories": institutional_raw_data.get('collection_stats', {}).get('successful_categories', 0),
                    "data_sources": ['coingecko', 'blockchain_info', 'estimated_calculations'],
                    "cache_recommendations": institutional_raw_data.get('collection_stats', {}).get('cache_recommendations', {})
                }
            }
            
        except Exception as e:
            logger.error(f"기관 투자 흐름 분석 중 오류: {e}")
            return {
                "success": False,
                "error": f"분석 중 오류 발생: {str(e)}",
                "analysis_type": "institutional_flow",
                "data_quality": {
                    "success_rate": 0,
                    "error": str(e)
                }
            }

# 외부에서 사용할 함수
async def analyze_institutional_flow() -> Dict:
    """기관 투자 흐름을 분석하는 함수"""
    analyzer = InstitutionAnalyzer()
    return await analyzer.analyze_institutional_flow()

# 테스트용 코드
if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("🔍 기관 투자 흐름 분석 테스트 시작...")
        result = await analyze_institutional_flow()
        
        if result['success']:
            print("✅ 기관 투자 분석 성공!")
            print(f"데이터 성공률: {result['data_quality']['success_rate']:.1f}%")
            print(f"기관 투자 점수: {result['result']['institutional_flow_score']:.1f}")
            print(f"투자 신호: {result['result']['investment_signal']}")
            print(f"캐싱 권장사항:")
            for category, ttl in result['data_quality']['cache_recommendations'].items():
                print(f"  {category}: {ttl}")
        else:
            print("❌ 기관 투자 분석 실패:")
            print(result['error'])
        
        print("\n" + "="*50)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())