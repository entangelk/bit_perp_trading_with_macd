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
logger = logging.getLogger("onchain_analyzer")

# CoinGecko API 키 설정
COINGECKO_API_KEY = os.getenv("GEKCO_API_KEY")

def get_coingecko_headers():
    """CoinGecko API 헤더 생성 (API 키 포함)"""
    headers = {'User-Agent': 'trading-bot/1.0'}
    if COINGECKO_API_KEY:
        headers['x-cg-demo-api-key'] = COINGECKO_API_KEY
        # logger.debug("CoinGecko API 키 적용됨")
    else:
        logger.warning("CoinGecko API 키가 설정되지 않음 - 무료 한도 적용")
    return headers

class OnchainAnalyzer:
    """온체인 데이터 분석 AI - 4단계 (무료 API 기반)"""
    
    def __init__(self):
        self.client = None
        self.model_name = None
        
        # 실패 카운트 추가
        self.error_counts = {
            'blockchain_stats': 0,
            'address_metrics': 0,
            'holder_behavior': 0,
            'mining_metrics': 0,
            'mempool_data': 0
        }
        self.max_errors = 3
        
        # 캐싱 TTL 설정 (초 단위)
        self.cache_ttl = {
            'whale_movements': 1800,      # 30분 (고래 거래)
            'exchange_flows': 1800,       # 30분 (거래소 유입/유출)
            'network_metrics': 3600,      # 1시간 (네트워크 지표)
            'holder_behavior': 3600,      # 1시간 (보유자 행동)
            'mining_metrics': 7200,       # 2시간 (채굴 지표)
            'addresses_metrics': 3600,    # 1시간 (주소 활성도)
        }
        
        # 무료 온체인 데이터 소스들
        self.data_sources = {
            # Blockchain.info API - 무료 (제한 있음)
            'blockchain_info': {
                'base_url': 'https://api.blockchain.info',
                'endpoints': {
                    'stats': '/stats',
                    'charts_hash_rate': '/charts/hash-rate',
                    'pools': '/pools',
                    'unconfirmed': '/q/unconfirmedcount',
                    'difficulty': '/q/getdifficulty',
                    'hashrate': '/q/hashrate',
                    'market_cap': '/q/marketcap',
                    'total_btc': '/q/totalbc',
                    'avg_block_size': '/q/avgtxsize',
                }
            },
            
            # CoinGecko API - 무료 (온체인 데이터 일부)
            'coingecko': {
                'base_url': 'https://api.coingecko.com/api/v3',
                'endpoints': {
                    'global_data': '/global',
                    'btc_data': '/coins/bitcoin',
                    'btc_market_data': '/coins/bitcoin/market_chart',
                }
            },
            
            # BitcoinVisuals API - 무료 (제한적)
            'bitcoin_visuals': {
                'base_url': 'https://api.bitcoinvisuals.com',
                'endpoints': {
                    'addresses': '/addresses',
                    'transactions': '/transactions',
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
                    logger.info(f"온체인 분석 모델 {model_name} 초기화 성공")
                    return client, model_name
                    
                except Exception as e:
                    logger.warning(f"온체인 분석 모델 {model_name} 초기화 실패: {e}")
                    continue
            
            logger.error("온체인 분석용 모든 모델 초기화 실패")
            return None, None
            
        except Exception as e:
            logger.error(f"온체인 분석 모델 초기화 중 전체 오류: {e}")
            return None, None
    
    def get_blockchain_info_stats(self) -> Dict:
        """Blockchain.info에서 기본 통계 수집 (개별 엔드포인트 사용)"""
        try:
            base_url = self.data_sources['blockchain_info']['base_url']
            
            # 1. 난이도 - 별도 엔드포인트 (2주마다 변경)
            difficulty_url = f"{base_url}/q/getdifficulty"
            difficulty_response = requests.get(difficulty_url, timeout=10)
            difficulty = float(difficulty_response.text) if difficulty_response.status_code == 200 else 127620086886391
            
            # 2. 총 BTC 공급량
            totalbc_url = f"{base_url}/q/totalbc"
            totalbc_response = requests.get(totalbc_url, timeout=10)
            totalbc = int(totalbc_response.text) if totalbc_response.status_code == 200 else 1989793125000000
            
            # 3. 미확인 거래 수
            unconfirmed_url = f"{base_url}/q/unconfirmedcount"
            unconfirmed_response = requests.get(unconfirmed_url, timeout=10)
            unconfirmed_count = int(unconfirmed_response.text) if unconfirmed_response.status_code == 200 else 25000
            
            # 4. 시장 데이터는 CoinGecko에서 가져오기 (더 신뢰성 있음)
            try:
                cg_url = f"{self.data_sources['coingecko']['base_url']}/simple/price"
                cg_params = {'ids': 'bitcoin', 'vs_currencies': 'usd', 'include_market_cap': 'true', 'include_24hr_vol': 'true'}
                cg_response = requests.get(cg_url, params=cg_params, headers=get_coingecko_headers(), timeout=10)
                cg_data = cg_response.json() if cg_response.status_code == 200 else {}
                
                btc_data = cg_data.get('bitcoin', {})
                market_price_usd = btc_data.get('usd', 118000)
                market_cap_usd = btc_data.get('usd_market_cap', 0)
                volume_24h_usd = btc_data.get('usd_24h_vol', 0)
            except:
                # CoinGecko 실패시 기본값
                market_price_usd = 118000
                market_cap_usd = market_price_usd * (totalbc / 100000000)
                volume_24h_usd = 20000000000
            
            return {
                'total_btc_supply': totalbc / 100000000,  # Satoshi -> BTC
                'market_cap_usd': market_cap_usd,
                'market_price_usd': market_price_usd,
                'difficulty': difficulty,
                'unconfirmed_transactions': unconfirmed_count,
                'trade_volume_usd': volume_24h_usd,
                'trade_volume_btc': volume_24h_usd / market_price_usd if market_price_usd > 0 else 0,
                'timestamp': datetime.now().isoformat(),
                'source': 'blockchain_info_individual_endpoints',
                'cache_ttl': self.cache_ttl['network_metrics'],
                'data_sources': {
                    'difficulty': 'blockchain_info_q_getdifficulty',
                    'btc_supply': 'blockchain_info_q_totalbc', 
                    'unconfirmed_txs': 'blockchain_info_q_unconfirmedcount',
                    'market_data': 'coingecko_simple_price'
                }
            }
            
        except Exception as e:
            logger.error(f"Blockchain.info 개별 통계 수집 실패: {e}")
            self.error_counts['blockchain_stats'] += 1
            return self._get_cached_blockchain_stats()
    
    def get_mempool_data(self) -> Dict:
        """메모리풀 데이터 수집 (캐싱 권장: 30분)"""
        try:
            # 미확인 거래 수
            unconfirmed_url = f"{self.data_sources['blockchain_info']['base_url']}/q/unconfirmedcount"
            unconfirmed_response = requests.get(unconfirmed_url, timeout=10)
            unconfirmed_count = int(unconfirmed_response.text) if unconfirmed_response.status_code == 200 else 0
            
            return {
                'unconfirmed_transactions': unconfirmed_count,
                'congestion_level': 'High' if unconfirmed_count > 50000 else 'Medium' if unconfirmed_count > 20000 else 'Low',
                'timestamp': datetime.now().isoformat(),
                'source': 'blockchain_info',
                'cache_ttl': self.cache_ttl['network_metrics']
            }
            
        except Exception as e:
            logger.error(f"메모리풀 데이터 수집 실패: {e}")
            self.error_counts['mempool_data'] += 1
            return None
    
    def get_address_metrics(self) -> Dict:
        """주소 활성도 지표 수집 (캐싱 권장: 1시간)"""
        try:
            # 실제로는 여러 API를 조합해야 하지만, 무료 제한으로 인해 추정치 사용
            # 향후 더 나은 무료 API 발견시 교체 가능
            
            # CoinGecko에서 Bitcoin 데이터 가져오기
            url = f"{self.data_sources['coingecko']['base_url']}/coins/bitcoin"
            params = {
                'localization': 'false',
                'tickers': 'false',
                'market_data': 'true',
                'community_data': 'false',
                'developer_data': 'false'
            }
            
            response = requests.get(url, params=params, headers=get_coingecko_headers(), timeout=10)
            response.raise_for_status()
            data = response.json()
            
            market_data = data.get('market_data', {})
            
            # 추정 계산 (실제 온체인 데이터 대신)
            current_price = market_data.get('current_price', {}).get('usd', 50000)
            market_cap = market_data.get('market_cap', {}).get('usd', 0)
            volume_24h = market_data.get('total_volume', {}).get('usd', 0)
            
            # 활성 주소 추정 (거래량 기반)
            estimated_active_addresses = min(1000000, max(100000, int(volume_24h / current_price * 100)))
            
            return {
                'estimated_active_addresses': estimated_active_addresses,
                'new_addresses_trend': 'Increasing' if volume_24h > 20000000000 else 'Stable',
                'address_activity_score': min(100, int((volume_24h / 20000000000) * 100)),
                'whale_addresses_estimate': int(estimated_active_addresses * 0.001),  # 0.1% 추정
                'retail_addresses_estimate': int(estimated_active_addresses * 0.95),   # 95% 추정
                'timestamp': datetime.now().isoformat(),
                'source': 'coingecko_estimation',
                'cache_ttl': self.cache_ttl['addresses_metrics'],
                'note': '실제 온체인 데이터 대신 거래량 기반 추정치'
            }
            
        except Exception as e:
            logger.error(f"주소 지표 수집 실패: {e}")
            self.error_counts['address_metrics'] += 1
            return self._get_cached_address_metrics()
    
    def get_holder_behavior_metrics(self) -> Dict:
        """보유자 행동 분석 (캐싱 권장: 1시간)"""
        try:
            # CoinGecko에서 시장 데이터로 보유자 행동 추정
            url = f"{self.data_sources['coingecko']['base_url']}/coins/bitcoin/market_chart"
            params = {
                'vs_currency': 'usd',
                'days': '30',
                'interval': 'daily'
            }
            
            response = requests.get(url, params=params, headers=get_coingecko_headers(), timeout=10)
            response.raise_for_status()
            data = response.json()
            
            prices = data.get('prices', [])
            volumes = data.get('total_volumes', [])
            
            if len(prices) >= 7 and len(volumes) >= 7:
                # 최근 7일 평균 대비 현재 볼륨 비교
                recent_volumes = [v[1] for v in volumes[-7:]]
                avg_volume = sum(recent_volumes) / len(recent_volumes)
                current_volume = volumes[-1][1] if volumes else avg_volume
                
                # 가격 변동성 계산
                recent_prices = [p[1] for p in prices[-7:]]
                price_volatility = (max(recent_prices) - min(recent_prices)) / min(recent_prices) * 100
                
                # HODL 추정 지표
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
                hodl_strength = max(0, min(100, 100 - (volume_ratio * 50)))  # 거래량 낮을수록 HODL 강함
                
                return {
                    'hodl_strength_score': round(hodl_strength, 1),
                    'volume_trend': 'Increasing' if volume_ratio > 1.2 else 'Decreasing' if volume_ratio < 0.8 else 'Stable',
                    'price_volatility_7d': round(price_volatility, 2),
                    'holder_behavior': 'Strong HODL' if hodl_strength > 70 else 'Weak HODL' if hodl_strength < 30 else 'Mixed',
                    'selling_pressure': 'High' if volume_ratio > 1.5 else 'Low' if volume_ratio < 0.7 else 'Medium',
                    'accumulation_phase': hodl_strength > 60 and price_volatility < 10,
                    'timestamp': datetime.now().isoformat(),
                    'source': 'coingecko_analysis',
                    'cache_ttl': self.cache_ttl['holder_behavior']
                }
            else:
                raise ValueError("충분한 가격/볼륨 데이터 없음")
                
        except Exception as e:
            logger.error(f"보유자 행동 분석 실패: {e}")
            self.error_counts['holder_behavior'] += 1
            return self._get_cached_holder_behavior()
    
    def get_mining_metrics(self) -> Dict:
        """채굴 관련 지표 수집 (7일 평균 + 일일 원시값 제공)"""
        try:
            base_url = f"{self.data_sources['blockchain_info']['base_url']}/charts/hash-rate"
            
            # 1. 7일 평균 해시레이트 (기존)
            hash_params_7d = {
                'rollingAverage': '7days',
                'format': 'json',
                'timespan': '14days'  # 충분한 데이터 보장
            }
            
            hash_response_7d = requests.get(base_url, params=hash_params_7d, timeout=10)
            hash_response_7d.raise_for_status()
            hash_data_7d = hash_response_7d.json()
            
            # 2. 일일 원시값 해시레이트 (추가)
            hash_params_daily = {
                'format': 'json',
                'timespan': '3days'  # 최근 3일 원시값
            }
            
            hash_response_daily = requests.get(base_url, params=hash_params_daily, timeout=10)
            hash_response_daily.raise_for_status()
            hash_data_daily = hash_response_daily.json()
            
            # 3. 7일 평균 해시레이트 추출 (TH/s)
            if hash_data_7d.get('values') and len(hash_data_7d['values']) > 0:
                hash_rate_7d_th = hash_data_7d['values'][-1]['y']  # TH/s 단위
            else:
                hash_rate_7d_th = 900_000_000  # 기본값 900M TH/s ≈ 900 EH/s
            
            # 4. 일일 원시값 해시레이트 추출 (TH/s)
            if hash_data_daily.get('values') and len(hash_data_daily['values']) > 0:
                hash_rate_daily_th = hash_data_daily['values'][-1]['y']  # TH/s 단위
            else:
                hash_rate_daily_th = hash_rate_7d_th  # 7일 평균값으로 대체
            
            # 5. 난이도 (기존 방식)
            stats_data = self.get_blockchain_info_stats()
            difficulty = stats_data.get('difficulty', 0)
            
            # 6. 단위 변환 (TH/s -> EH/s)
            hash_rate_7d_eh = hash_rate_7d_th / 1_000_000      # 7일 평균 EH/s
            hash_rate_daily_eh = hash_rate_daily_th / 1_000_000  # 일일 원시값 EH/s
            
            # 7. 계산 로직 - 두 가지 기준 제공
            mining_difficulty_trend = 'Increasing' if difficulty > 50000000000000 else 'Stable'
            
            # 7일 평균 기준 계산
            network_security_7d = min(100, max(0, hash_rate_7d_eh / 5 * 100))  # 500 EH/s = 100점
            hash_rate_trend_7d = 'Strong' if hash_rate_7d_eh > 400 else 'Weak' if hash_rate_7d_eh < 200 else 'Moderate'
            miner_risk_7d = 'Low' if hash_rate_7d_eh > 300 else 'High'
            
            # 일일 원시값 기준 계산
            network_security_daily = min(100, max(0, hash_rate_daily_eh / 5 * 100))
            hash_rate_trend_daily = 'Strong' if hash_rate_daily_eh > 400 else 'Weak' if hash_rate_daily_eh < 200 else 'Moderate'
            miner_risk_daily = 'Low' if hash_rate_daily_eh > 300 else 'High'
            
            return {
                # 7일 평균 데이터 (중장기 트렌드용)
                'hash_rate_7d_eh': round(hash_rate_7d_eh, 2),
                'hash_rate_7d_th': round(hash_rate_7d_th, 2),
                'network_security_7d': round(network_security_7d, 1),
                'hash_rate_trend_7d': hash_rate_trend_7d,
                'miner_risk_7d': miner_risk_7d,
                
                # 일일 원시값 데이터 (스윙 거래용)
                'hash_rate_daily_eh': round(hash_rate_daily_eh, 2),
                'hash_rate_daily_th': round(hash_rate_daily_th, 2),
                'network_security_daily': round(network_security_daily, 1),
                'hash_rate_trend_daily': hash_rate_trend_daily,
                'miner_risk_daily': miner_risk_daily,
                
                # 공통 데이터
                'difficulty': difficulty,
                'mining_difficulty_trend': mining_difficulty_trend,
                
                # 기존 호환성을 위한 필드 (7일 평균 기준)
                'hash_rate_eh': round(hash_rate_7d_eh, 2),
                'hash_rate_th': round(hash_rate_7d_th, 2),
                'network_security_score': round(network_security_7d, 1),
                'hash_rate_trend': hash_rate_trend_7d,
                'miner_capitulation_risk': miner_risk_7d,
                
                'timestamp': datetime.now().isoformat(),
                'source': 'blockchain_info_charts_7d_avg_plus_daily',
                'cache_ttl': self.cache_ttl['mining_metrics'],
                'data_methodology': {
                    '7d_average': '중장기 트렌드 분석용 - 안정적, 노이즈 제거',
                    'daily_raw': '스윙 거래용 - 즉시 반응성, 단기 변동 반영',
                    'recommended_use': {
                        'swing_trading': 'daily 필드 사용',
                        'trend_analysis': '7d 필드 사용',
                        'comprehensive': '두 데이터 조합 분석'
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"채굴 지표 수집 실패: {e}")
            self.error_counts['mining_metrics'] += 1
            return self._get_cached_mining_metrics()
    
    def _get_cached_blockchain_stats(self) -> Optional[Dict]:
        """MongoDB에서 과거 블록체인 통계 데이터 가져오기"""
        try:
            from pymongo import MongoClient
            from datetime import datetime, timezone, timedelta
            
            client = MongoClient("mongodb://mongodb:27017")
            db = client["bitcoin"]
            cache_collection = db["data_cache"]
            
            # 최근 24시간 이내 데이터 찾기
            twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)
            
            cached_data = cache_collection.find_one({
                "task_name": "onchain_data",
                "created_at": {"$gte": twenty_four_hours_ago}
            }, sort=[("created_at", -1)])
            
            if cached_data and cached_data.get('data'):
                onchain_data = cached_data['data']
                
                # metrics에서 가져오기 (기존 경로 사용)
                if 'metrics' in onchain_data:
                    metrics = onchain_data['metrics']
                    return {
                        'total_btc_supply': metrics.get('total_btc_supply'),
                        'market_cap_usd': metrics.get('market_cap_usd'),
                        'market_price_usd': metrics.get('market_price_usd'),
                        'difficulty': metrics.get('difficulty'),
                        'unconfirmed_transactions': metrics.get('unconfirmed_transactions'),
                        'trade_volume_btc': metrics.get('trade_volume_btc'),
                        'trade_volume_usd': metrics.get('trade_volume_usd'),
                        'data_sources': metrics.get('data_sources'),
                        'timestamp': cached_data['created_at'].isoformat(),
                        'source': 'cached_data',
                        'cache_ttl': self.cache_ttl['network_metrics']
                    }
            
            logger.warning("블록체인 통계: 캐시된 데이터 없음")
            return None
            
        except Exception as e:
            logger.error(f"캐시된 블록체인 데이터 조회 실패: {e}")
            return None
    
    def _get_cached_address_metrics(self) -> Optional[Dict]:
        """MongoDB에서 과거 주소 지표 데이터 가져오기"""
        try:
            from pymongo import MongoClient
            from datetime import datetime, timezone, timedelta
            
            client = MongoClient("mongodb://mongodb:27017")
            db = client["bitcoin"]
            cache_collection = db["data_cache"]
            
            # 최근 2시간 이내 데이터 찾기
            two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
            
            cached_data = cache_collection.find_one({
                "task_name": "onchain_data",
                "created_at": {"$gte": two_hours_ago}
            }, sort=[("created_at", -1)])
            
            if cached_data and cached_data.get('data', {}).get('address_metrics'):
                address_data = cached_data['data']['address_metrics']
                return {
                    'estimated_active_addresses': address_data.get('estimated_active_addresses'),
                    'new_addresses_trend': address_data.get('new_addresses_trend'),
                    'address_activity_score': address_data.get('address_activity_score'),
                    'whale_addresses_estimate': address_data.get('whale_addresses_estimate'),
                    'retail_addresses_estimate': address_data.get('retail_addresses_estimate'),
                    'timestamp': cached_data['created_at'].isoformat(),
                    'source': 'cached_data',
                    'cache_ttl': self.cache_ttl['addresses_metrics']
                }
            
            logger.warning("주소 지표: 캐시된 데이터 없음")
            return None
            
        except Exception as e:
            logger.error(f"캐시된 주소 데이터 조회 실패: {e}")
            return None
    
    def _get_cached_holder_behavior(self) -> Optional[Dict]:
        """MongoDB에서 과거 보유자 행동 데이터 가져오기"""
        try:
            from pymongo import MongoClient
            from datetime import datetime, timezone, timedelta
            
            client = MongoClient("mongodb://mongodb:27017")
            db = client["bitcoin"]
            cache_collection = db["data_cache"]
            
            # 최근 2시간 이내 데이터 찾기
            two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
            
            cached_data = cache_collection.find_one({
                "task_name": "onchain_data",
                "created_at": {"$gte": two_hours_ago}
            }, sort=[("created_at", -1)])
            
            if cached_data and cached_data.get('data', {}).get('holder_behavior'):
                holder_data = cached_data['data']['holder_behavior']
                return {
                    'hodl_strength_score': holder_data.get('hodl_strength_score'),
                    'volume_trend': holder_data.get('volume_trend'),
                    'price_volatility_7d': holder_data.get('price_volatility_7d'),
                    'holder_behavior': holder_data.get('holder_behavior'),
                    'selling_pressure': holder_data.get('selling_pressure'),
                    'accumulation_phase': holder_data.get('accumulation_phase'),
                    'timestamp': cached_data['created_at'].isoformat(),
                    'source': 'cached_data',
                    'cache_ttl': self.cache_ttl['holder_behavior']
                }
            
            logger.warning("보유자 행동 데이터: 캐시된 데이터 없음")
            return None
            
        except Exception as e:
            logger.error(f"캐시된 보유자 데이터 조회 실패: {e}")
            return None
    
    def _get_cached_mining_metrics(self) -> Optional[Dict]:
        """MongoDB에서 과거 채굴 지표 데이터 가져오기 (7일평균 + 일일원시값 지원)"""
        try:
            from pymongo import MongoClient
            from datetime import datetime, timezone, timedelta
            
            client = MongoClient("mongodb://mongodb:27017")
            db = client["bitcoin"]
            cache_collection = db["data_cache"]
            
            # 최근 4시간 이내 데이터 찾기
            four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=4)
            
            cached_data = cache_collection.find_one({
                "task_name": "onchain_data",
                "created_at": {"$gte": four_hours_ago}
            }, sort=[("created_at", -1)])
            
            if cached_data and cached_data.get('data', {}).get('mining'):
                mining_data = cached_data['data']['mining']
                
                # 새로운 구조 (7일평균 + 일일원시값)가 있는지 확인
                if 'hash_rate_7d_eh' in mining_data and 'hash_rate_daily_eh' in mining_data:
                    return {
                        # 7일 평균 데이터 (중장기 트렌드용)
                        'hash_rate_7d_eh': mining_data.get('hash_rate_7d_eh'),
                        'hash_rate_7d_th': mining_data.get('hash_rate_7d_th'),
                        'network_security_7d': mining_data.get('network_security_7d'),
                        'hash_rate_trend_7d': mining_data.get('hash_rate_trend_7d'),
                        'miner_risk_7d': mining_data.get('miner_risk_7d'),
                        
                        # 일일 원시값 데이터 (스윙 거래용)
                        'hash_rate_daily_eh': mining_data.get('hash_rate_daily_eh'),
                        'hash_rate_daily_th': mining_data.get('hash_rate_daily_th'),
                        'network_security_daily': mining_data.get('network_security_daily'),
                        'hash_rate_trend_daily': mining_data.get('hash_rate_trend_daily'),
                        'miner_risk_daily': mining_data.get('miner_risk_daily'),
                        
                        # 공통 데이터
                        'difficulty': mining_data.get('difficulty'),
                        'mining_difficulty_trend': mining_data.get('mining_difficulty_trend'),
                        
                        # 기존 호환성 필드
                        'hash_rate_eh': mining_data.get('hash_rate_eh'),
                        'hash_rate_th': mining_data.get('hash_rate_th'),
                        'network_security_score': mining_data.get('network_security_score'),
                        'hash_rate_trend': mining_data.get('hash_rate_trend'),
                        'miner_capitulation_risk': mining_data.get('miner_capitulation_risk'),
                        
                        'data_methodology': mining_data.get('data_methodology'),
                        'timestamp': cached_data['created_at'].isoformat(),
                        'source': 'cached_data',
                        'cache_ttl': self.cache_ttl['mining_metrics']
                    }
                
                # 기존 구조 (7일평균만) 호환성 유지
                else:
                    return {
                        # 기존 필드들
                        'hash_rate_eh': mining_data.get('hash_rate_eh'),
                        'hash_rate_th': mining_data.get('hash_rate_th'),
                        'difficulty': mining_data.get('difficulty'),
                        'mining_difficulty_trend': mining_data.get('mining_difficulty_trend'),
                        'network_security_score': mining_data.get('network_security_score'),
                        'hash_rate_trend': mining_data.get('hash_rate_trend'),
                        'miner_capitulation_risk': mining_data.get('miner_capitulation_risk'),
                        
                        # 기존 데이터를 새 필드에도 매핑 (호환성)
                        'hash_rate_7d_eh': mining_data.get('hash_rate_eh'),
                        'hash_rate_7d_th': mining_data.get('hash_rate_th'),
                        'network_security_7d': mining_data.get('network_security_score'),
                        'hash_rate_trend_7d': mining_data.get('hash_rate_trend'),
                        'miner_risk_7d': mining_data.get('miner_capitulation_risk'),
                        
                        # 일일 데이터는 7일 평균값으로 대체 (기본값)
                        'hash_rate_daily_eh': mining_data.get('hash_rate_eh'),
                        'hash_rate_daily_th': mining_data.get('hash_rate_th'),
                        'network_security_daily': mining_data.get('network_security_score'),
                        'hash_rate_trend_daily': mining_data.get('hash_rate_trend'),
                        'miner_risk_daily': mining_data.get('miner_capitulation_risk'),
                        
                        'timestamp': cached_data['created_at'].isoformat(),
                        'source': 'cached_data_legacy',
                        'cache_ttl': self.cache_ttl['mining_metrics']
                    }
            
            logger.warning("채굴 지표: 캐시된 데이터 없음")
            return None
            
        except Exception as e:
            logger.error(f"캐시된 채굴 데이터 조회 실패: {e}")
            return None
        
    def collect_onchain_data(self) -> Dict:
        """온체인 데이터 종합 수집"""
        try:
            logger.info("온체인 데이터 수집 시작")
            
            # 각 카테고리별 데이터 수집
            onchain_data = {}
            success_count = 0
            total_categories = 5
            
            # 1. 네트워크 기본 통계
            try:
                network_stats = self.get_blockchain_info_stats()
                onchain_data['metrics'] = network_stats
                if 'error' not in network_stats:
                    success_count += 1
                logger.info("✅ 네트워크 통계 수집 완료")
            except Exception as e:
                logger.error(f"❌ 네트워크 통계 수집 실패: {e}")
                onchain_data['network_stats'] = self._get_cached_blockchain_stats()
            
            # 2. 메모리풀 데이터
            try:
                mempool_data = self.get_mempool_data()
                onchain_data['mempool'] = mempool_data
                if 'error' not in mempool_data:
                    success_count += 1
                logger.info("✅ 메모리풀 데이터 수집 완료")
            except Exception as e:
                logger.error(f"❌ 메모리풀 데이터 수집 실패: {e}")
                onchain_data['mempool'] = None
            
            # 3. 주소 활성도
            try:
                address_metrics = self.get_address_metrics()
                onchain_data['addresses'] = address_metrics
                if 'error' not in address_metrics:
                    success_count += 1
                logger.info("✅ 주소 지표 수집 완료")
            except Exception as e:
                logger.error(f"❌ 주소 지표 수집 실패: {e}")
                onchain_data['addresses'] = self._get_cached_address_metrics()
            
            # 4. 보유자 행동
            try:
                holder_behavior = self.get_holder_behavior_metrics()
                onchain_data['holder_behavior'] = holder_behavior
                if 'error' not in holder_behavior:
                    success_count += 1
                logger.info("✅ 보유자 행동 분석 완료")
            except Exception as e:
                logger.error(f"❌ 보유자 행동 분석 실패: {e}")
                onchain_data['holder_behavior'] = self._get_cached_holder_behavior()
            
            # 5. 채굴 지표
            try:
                mining_metrics = self.get_mining_metrics()
                onchain_data['mining'] = mining_metrics
                if 'error' not in mining_metrics:
                    success_count += 1
                logger.info("✅ 채굴 지표 수집 완료")
            except Exception as e:
                logger.error(f"❌ 채굴 지표 수집 실패: {e}")
                onchain_data['mining'] = self._get_cached_mining_metrics()
            
            # 수집 통계
            success_rate = (success_count / total_categories) * 100
            onchain_data['collection_stats'] = {
                'timestamp': datetime.now().isoformat(),
                'total_categories': total_categories,
                'successful_categories': success_count,
                'success_rate': round(success_rate, 1),
                'data_sources': ['blockchain_info', 'coingecko'],
                'cache_recommendations': {
                    'network_stats': f"{self.cache_ttl['network_metrics']}초",
                    'mempool': f"{self.cache_ttl['network_metrics']}초",
                    'addresses': f"{self.cache_ttl['addresses_metrics']}초",
                    'holder_behavior': f"{self.cache_ttl['holder_behavior']}초",
                    'mining': f"{self.cache_ttl['mining_metrics']}초"
                }
            }
            
            logger.info(f"온체인 데이터 수집 완료: {success_count}/{total_categories} 성공 ({success_rate:.1f}%)")
            return onchain_data
            
        except Exception as e:
            logger.error(f"온체인 데이터 수집 중 전체 오류: {e}")
            return self._get_cached_complete_data()
    
    def check_data_availability(self) -> bool:
        """데이터 사용 가능 여부 확인"""
        failed_sources = sum(1 for count in self.error_counts.values() if count >= self.max_errors)
        if failed_sources >= 3:  # 5개 소스 중 3개 이상 실패시 불가
            return False
        return True
    
    def _get_cached_complete_data(self) -> Optional[Dict]:
        """전체 실패시 캐시된 데이터 사용"""
        network_stats = self._get_cached_blockchain_stats()
        addresses = self._get_cached_address_metrics()
        holder_behavior = self._get_cached_holder_behavior()
        mining = self._get_cached_mining_metrics()
        
        # 캐시된 데이터가 있는지 확인
        if any([network_stats, addresses, holder_behavior, mining]):
            return {
                'network_stats': network_stats,
                'mempool': None,
                'addresses': addresses,
                'holder_behavior': holder_behavior,
                'mining': mining,
                'collection_stats': {
                    'timestamp': datetime.now().isoformat(),
                    'total_categories': 5,
                    'successful_categories': 0,
                    'success_rate': 0.0,
                    'note': '대부분 API 실패 - 캐시된 데이터 사용'
                }
            }
        return None
    
    def analyze_onchain_signals(self, onchain_data: Dict) -> Dict:
        """온체인 데이터 신호 분석 (스윙거래 + 트렌드 분석 지원)"""
        try:
            # 네트워크 건강도 분석 - 7일평균 + 일일원시값 접근
            network_stats = onchain_data.get('network_stats', {})
            mining_data = onchain_data.get('mining', {})
            
            # 7일 평균 데이터 (중장기 트렌드용)
            hash_rate_7d_eh = mining_data.get('hash_rate_7d_eh', mining_data.get('hash_rate_eh', 350))
            network_security_7d = mining_data.get('network_security_7d', mining_data.get('network_security_score', 85))
            hash_rate_trend_7d = mining_data.get('hash_rate_trend_7d', mining_data.get('hash_rate_trend', 'Moderate'))
            miner_risk_7d = mining_data.get('miner_risk_7d', mining_data.get('miner_capitulation_risk', 'Low'))
            
            # 일일 원시값 데이터 (스윙거래용)
            hash_rate_daily_eh = mining_data.get('hash_rate_daily_eh', hash_rate_7d_eh)
            network_security_daily = mining_data.get('network_security_daily', network_security_7d)
            hash_rate_trend_daily = mining_data.get('hash_rate_trend_daily', hash_rate_trend_7d)
            miner_risk_daily = mining_data.get('miner_risk_daily', miner_risk_7d)
            
            # 공통 데이터
            difficulty = mining_data.get('difficulty', 70000000000000)
            
            # 메모리풀 혼잡도
            mempool = onchain_data.get('mempool', {})
            unconfirmed_txs = mempool.get('unconfirmed_transactions', 25000)
            congestion_level = mempool.get('congestion_level', 'Medium')
            
            # 보유자 행동
            holder_behavior = onchain_data.get('holder_behavior', {})
            hodl_strength = holder_behavior.get('hodl_strength_score', 65)
            selling_pressure = holder_behavior.get('selling_pressure', 'Medium')
            
            # 주소 활성도
            addresses = onchain_data.get('addresses', {})
            active_addresses = addresses.get('estimated_active_addresses', 800000)
            activity_score = addresses.get('address_activity_score', 65)
            
            # 종합 점수 계산 (0-100) - 스윙거래와 트렌드 분석 분리
            
            # === 스윙거래용 점수 (일일 원시값 기준) ===
            swing_score = 0
            
            # 네트워크 보안 (30점 만점) - 일일 기준
            if network_security_daily > 80:
                swing_score += 30
            elif network_security_daily > 60:
                swing_score += 20
            elif network_security_daily > 40:
                swing_score += 15
            elif network_security_daily > 20:
                swing_score += 10
            else:
                swing_score += 5
            
            # 채굴자 리스크 (20점 만점) - 일일 기준으로 가중치 증가
            if miner_risk_daily == 'Low':
                swing_score += 20
            elif miner_risk_daily == 'Medium':
                swing_score += 12
            else:
                swing_score += 5
            
            # HODL 강도 (20점 만점)
            if hodl_strength > 80:
                swing_score += 20
            elif hodl_strength > 60:
                swing_score += 15
            elif hodl_strength > 40:
                swing_score += 10
            elif hodl_strength > 20:
                swing_score += 5
            else:
                swing_score += 2
            
            # 네트워크 활성도 (15점 만점)
            if activity_score > 80:
                swing_score += 15
            elif activity_score > 60:
                swing_score += 12
            elif activity_score > 40:
                swing_score += 8
            elif activity_score > 20:
                swing_score += 4
            else:
                swing_score += 2
            
            # 메모리풀 상태 (15점 만점) - 스윙거래에 중요
            if congestion_level == 'Low':
                swing_score += 15
            elif congestion_level == 'Medium':
                swing_score += 10
            else:
                swing_score += 5
            
            # === 트렌드 분석용 점수 (7일 평균 기준) ===
            trend_score = 0
            
            # 네트워크 보안 (35점 만점) - 트렌드 분석에서 가중치 증가
            if network_security_7d > 80:
                trend_score += 35
            elif network_security_7d > 60:
                trend_score += 25
            elif network_security_7d > 40:
                trend_score += 18
            elif network_security_7d > 20:
                trend_score += 12
            else:
                trend_score += 6
            
            # HODL 강도 (25점 만점)
            if hodl_strength > 80:
                trend_score += 25
            elif hodl_strength > 60:
                trend_score += 18
            elif hodl_strength > 40:
                trend_score += 12
            elif hodl_strength > 20:
                trend_score += 6
            else:
                trend_score += 2
            
            # 네트워크 활성도 (20점 만점)
            if activity_score > 80:
                trend_score += 20
            elif activity_score > 60:
                trend_score += 15
            elif activity_score > 40:
                trend_score += 10
            elif activity_score > 20:
                trend_score += 5
            else:
                trend_score += 2
            
            # 메모리풀 상태 (10점 만점) - 트렌드에서는 가중치 감소
            if congestion_level == 'Low':
                trend_score += 10
            elif congestion_level == 'Medium':
                trend_score += 7
            else:
                trend_score += 4
            
            # 채굴자 리스크 (10점 만점)
            if miner_risk_7d == 'Low':
                trend_score += 10
            elif miner_risk_7d == 'Medium':
                trend_score += 7
            else:
                trend_score += 3
            
            # 신호 강도 분류
            def get_signal_classification(score):
                if score >= 85:
                    return "매우 강함", "Strong Buy"
                elif score >= 70:
                    return "강함", "Buy"
                elif score >= 50:
                    return "중립", "Hold"
                elif score >= 30:
                    return "약함", "Weak Sell"
                else:
                    return "매우 약함", "Sell"
            
            swing_strength, swing_signal = get_signal_classification(swing_score)
            trend_strength, trend_signal = get_signal_classification(trend_score)
            
            # 종합 판단 (스윙 신호 우선, 트렌드로 검증)
            if swing_signal == trend_signal:
                final_signal = swing_signal
                signal_confidence = "High"
            elif abs(swing_score - trend_score) <= 10:
                final_signal = swing_signal  # 스윙 우선
                signal_confidence = "Medium"
            else:
                final_signal = "Hold"  # 상충시 중립
                signal_confidence = "Low"
            
            return {
                # 스윙거래 분석 (일일 원시값 기준)
                'swing_analysis': {
                    'score': round(swing_score, 1),
                    'signal_strength': swing_strength,
                    'signal': swing_signal,
                    'hash_rate_eh': hash_rate_daily_eh,
                    'hash_rate_trend': hash_rate_trend_daily,
                    'network_security': network_security_daily,
                    'miner_risk': miner_risk_daily,
                    'data_basis': 'daily_raw_values'
                },
                
                # 트렌드 분석 (7일 평균 기준)
                'trend_analysis': {
                    'score': round(trend_score, 1),
                    'signal_strength': trend_strength,
                    'signal': trend_signal,
                    'hash_rate_eh': hash_rate_7d_eh,
                    'hash_rate_trend': hash_rate_trend_7d,
                    'network_security': network_security_7d,
                    'miner_risk': miner_risk_7d,
                    'data_basis': '7day_moving_average'
                },
                
                # 종합 판단
                'final_recommendation': {
                    'signal': final_signal,
                    'confidence': signal_confidence,
                    'swing_score': round(swing_score, 1),
                    'trend_score': round(trend_score, 1),
                    'score_difference': round(abs(swing_score - trend_score), 1),
                    'alignment': 'aligned' if swing_signal == trend_signal else 'divergent'
                },
                
                # 기존 호환성 (스윙 기준)
                'onchain_score': round(swing_score, 1),
                'signal_strength': swing_strength,
                'btc_signal': swing_signal,
                
                # 상세 분석
                'network_health': {
                    'security_level_7d': 'High' if network_security_7d > 70 else 'Medium' if network_security_7d > 40 else 'Low',
                    'security_level_daily': 'High' if network_security_daily > 70 else 'Medium' if network_security_daily > 40 else 'Low',
                    'hash_rate_trend_7d': hash_rate_trend_7d,
                    'hash_rate_trend_daily': hash_rate_trend_daily,
                    'hash_rate_7d_eh': hash_rate_7d_eh,
                    'hash_rate_daily_eh': hash_rate_daily_eh,
                    'miner_sentiment_7d': 'Bullish' if miner_risk_7d == 'Low' else 'Bearish' if miner_risk_7d == 'High' else 'Neutral',
                    'miner_sentiment_daily': 'Bullish' if miner_risk_daily == 'Low' else 'Bearish' if miner_risk_daily == 'High' else 'Neutral'
                },
                
                'user_behavior': {
                    'hodl_sentiment': 'Strong' if hodl_strength > 70 else 'Weak' if hodl_strength < 40 else 'Mixed',
                    'selling_pressure_level': selling_pressure,
                    'accumulation_signal': hodl_strength > 60 and selling_pressure in ['Low', 'Medium']
                },
                
                'network_activity': {
                    'activity_level': 'High' if activity_score > 75 else 'Low' if activity_score < 50 else 'Medium',
                    'congestion_status': congestion_level,
                    'transaction_demand': 'High' if unconfirmed_txs > 40000 else 'Low' if unconfirmed_txs < 15000 else 'Medium'
                },
                
                'key_signals': self._identify_key_signals_enhanced(onchain_data, swing_score, trend_score),
                'risk_factors': self._identify_onchain_risks_enhanced(onchain_data),
                'bullish_factors': self._identify_bullish_factors_enhanced(onchain_data),
                
                'data_reliability': {
                    'success_rate': onchain_data.get('collection_stats', {}).get('success_rate', 0),
                    'confidence': 'High' if onchain_data.get('collection_stats', {}).get('success_rate', 0) > 80 else 'Medium' if onchain_data.get('collection_stats', {}).get('success_rate', 0) > 50 else 'Low'
                },
                
                'methodology_info': {
                    'swing_trading': 'daily_raw_values_for_immediate_responsiveness',
                    'trend_analysis': '7day_moving_average_for_stable_trends',
                    'recommended_use': 'swing_analysis_for_1-2day_trades_trend_analysis_for_position_sizing'
                }
            }
            
        except Exception as e:
            logger.error(f"온체인 신호 분석 중 오류: {e}")
            return {
                'swing_analysis': {'score': 50.0, 'signal': 'Hold'},
                'trend_analysis': {'score': 50.0, 'signal': 'Hold'},
                'final_recommendation': {'signal': 'Hold', 'confidence': 'Low'},
                'onchain_score': 50.0,
                'signal_strength': '중립',
                'btc_signal': 'Hold',
                'error': str(e),
                'data_reliability': {'success_rate': 0, 'confidence': 'None'}
            }


    def _identify_key_signals_enhanced(self, onchain_data: Dict, swing_score: float, trend_score: float) -> List[str]:
        """주요 온체인 신호들 식별 (스윙거래 + 트렌드 분석)"""
        signals = []
        
        # 데이터 추출
        mining = onchain_data.get('mining', {})
        holder_behavior = onchain_data.get('holder_behavior', {})
        addresses = onchain_data.get('addresses', {})
        mempool = onchain_data.get('mempool', {})
        
        # 스윙거래 관련 신호들 (일일 데이터 기준)
        hash_rate_daily_eh = mining.get('hash_rate_daily_eh', mining.get('hash_rate_eh', 350))
        hash_rate_7d_eh = mining.get('hash_rate_7d_eh', mining.get('hash_rate_eh', 350))
        miner_risk_daily = mining.get('miner_risk_daily', mining.get('miner_capitulation_risk', 'Low'))
        miner_risk_7d = mining.get('miner_risk_7d', mining.get('miner_capitulation_risk', 'Low'))
        
        hodl_strength = holder_behavior.get('hodl_strength_score', 65)
        activity_score = addresses.get('address_activity_score', 65)
        congestion = mempool.get('congestion_level', 'Medium')
        unconfirmed_txs = mempool.get('unconfirmed_transactions', 25000)
        
        # === 스윙거래 신호 (단기 변화 중심) ===
        if abs(hash_rate_daily_eh - hash_rate_7d_eh) > hash_rate_7d_eh * 0.05:  # 5% 이상 차이
            direction = "급상승" if hash_rate_daily_eh > hash_rate_7d_eh else "급하락"
            signals.append(f"🚨 스윙신호: 일일 해시레이트 {direction} ({hash_rate_daily_eh:.1f} vs 7일평균 {hash_rate_7d_eh:.1f} EH/s)")
        
        if miner_risk_daily != miner_risk_7d:
            if miner_risk_daily == 'Low' and miner_risk_7d != 'Low':
                signals.append("🟢 스윙신호: 채굴자 리스크 일일 개선 - 단기 매수 기회")
            elif miner_risk_daily == 'High' and miner_risk_7d != 'High':
                signals.append("🔴 스윙신호: 채굴자 리스크 일일 악화 - 단기 매도 압력")
        
        if congestion == 'High' and unconfirmed_txs > 50000:
            signals.append(f"⚠️ 스윙신호: 네트워크 심각 혼잡 ({unconfirmed_txs:,}건) - 단기 거래 지연 위험")
        elif congestion == 'Low' and unconfirmed_txs < 15000:
            signals.append("✅ 스윙신호: 네트워크 원활 - 거래 효율성 양호")
        
        # === 트렌드 신호 (안정적 변화 중심) ===
        if hash_rate_7d_eh > 500:
            signals.append(f"📈 트렌드신호: 높은 7일평균 해시레이트 ({hash_rate_7d_eh:.1f} EH/s) - 네트워크 보안 강화")
        
        if hodl_strength > 75:
            signals.append(f"💎 트렌드신호: 강한 HODL 패턴 ({hodl_strength:.1f}) - 장기 보유 증가")
        elif hodl_strength < 40:
            signals.append(f"📉 트렌드신호: 약한 HODL 패턴 ({hodl_strength:.1f}) - 매도 압력 증가")
        
        if activity_score > 80:
            signals.append(f"🚀 트렌드신호: 높은 네트워크 활성도 ({activity_score}) - 사용자 참여 증가")
        
        # === 종합 분석 신호 ===
        score_diff = abs(swing_score - trend_score)
        if score_diff <= 5:
            signals.append(f"🎯 강한 신호 일치: 스윙({swing_score:.1f}) ≈ 트렌드({trend_score:.1f}) - 높은 신뢰도")
        elif score_diff > 20:
            signals.append(f"⚡ 신호 상충: 스윙({swing_score:.1f}) vs 트렌드({trend_score:.1f}) - 주의 필요")
        
        if swing_score > 70 and trend_score > 70:
            signals.append("🔥 종합 강세: 단기/중기 모든 지표 긍정적")
        elif swing_score < 40 and trend_score < 40:
            signals.append("❄️ 종합 약세: 단기/중기 모든 지표 부정적")
        
        return signals if signals else ["현재 뚜렷한 스윙/트렌드 신호 없음"]

    def _identify_onchain_risks_enhanced(self, onchain_data: Dict) -> List[str]:
        """온체인 리스크 요인들 (스윙거래 + 트렌드 관점)"""
        risks = []
        
        mining = onchain_data.get('mining', {})
        holder_behavior = onchain_data.get('holder_behavior', {})
        mempool = onchain_data.get('mempool', {})
        addresses = onchain_data.get('addresses', {})
        
        # 스윙거래 리스크 (단기 위험)
        miner_risk_daily = mining.get('miner_risk_daily', mining.get('miner_capitulation_risk', 'Low'))
        hash_rate_daily_eh = mining.get('hash_rate_daily_eh', mining.get('hash_rate_eh', 350))
        hash_rate_7d_eh = mining.get('hash_rate_7d_eh', mining.get('hash_rate_eh', 350))
        
        if miner_risk_daily == 'High':
            risks.append("🚨 스윙리스크: 일일 채굴자 항복 위험 - 즉시 매도 압력 가능")
        
        if hash_rate_daily_eh < hash_rate_7d_eh * 0.9:  # 일일값이 7일평균보다 10% 이상 낮음
            risks.append(f"⚠️ 스윙리스크: 일일 해시레이트 급락 ({hash_rate_daily_eh:.1f} < {hash_rate_7d_eh:.1f} EH/s)")
        
        unconfirmed = mempool.get('unconfirmed_transactions', 25000)
        if unconfirmed > 50000:
            risks.append(f"🔴 스윙리스크: 네트워크 심각 혼잡 ({unconfirmed:,}건) - 거래 지연 및 수수료 급등")
        
        # 트렌드 리스크 (중장기 위험)
        miner_risk_7d = mining.get('miner_risk_7d', mining.get('miner_capitulation_risk', 'Low'))
        if miner_risk_7d == 'High':
            risks.append("📉 트렌드리스크: 7일평균 채굴자 항복 신호 - 지속적 매도 압력")
        
        selling_pressure = holder_behavior.get('selling_pressure', 'Medium')
        if selling_pressure == 'High':
            risks.append("💰 트렌드리스크: 높은 매도 압력 - 대량 물량 출회 위험")
        
        if hash_rate_7d_eh < 300:
            risks.append(f"🛡️ 트렌드리스크: 낮은 7일평균 해시레이트 ({hash_rate_7d_eh:.1f} EH/s) - 네트워크 보안 약화")
        
        activity_score = addresses.get('address_activity_score', 65)
        if activity_score < 40:
            risks.append(f"📱 트렌드리스크: 낮은 네트워크 활성도 ({activity_score}) - 사용자 이탈")
        
        # 데이터 신뢰성 리스크
        success_rate = onchain_data.get('collection_stats', {}).get('success_rate', 0)
        if success_rate < 60:
            risks.append(f"📊 데이터리스크: 낮은 수집 성공률 ({success_rate:.1f}%) - 분석 신뢰도 저하")
        
        return risks if risks else ["현재 특별한 스윙/트렌드 리스크 없음"]

    def _identify_bullish_factors_enhanced(self, onchain_data: Dict) -> List[str]:
        """강세 요인들 (스윙거래 + 트렌드 관점)"""
        bullish = []
        
        mining = onchain_data.get('mining', {})
        holder_behavior = onchain_data.get('holder_behavior', {})
        addresses = onchain_data.get('addresses', {})
        mempool = onchain_data.get('mempool', {})
        
        # 스윙거래 강세 요인 (단기 기회)
        hash_rate_daily_eh = mining.get('hash_rate_daily_eh', mining.get('hash_rate_eh', 350))
        hash_rate_7d_eh = mining.get('hash_rate_7d_eh', mining.get('hash_rate_eh', 350))
        miner_risk_daily = mining.get('miner_risk_daily', mining.get('miner_capitulation_risk', 'Low'))
        
        if hash_rate_daily_eh > hash_rate_7d_eh * 1.05:  # 일일값이 7일평균보다 5% 이상 높음
            bullish.append(f"🚀 스윙강세: 일일 해시레이트 급상승 ({hash_rate_daily_eh:.1f} > {hash_rate_7d_eh:.1f} EH/s)")
        
        if miner_risk_daily == 'Low':
            bullish.append("💪 스윙강세: 일일 채굴자 신뢰 회복 - 단기 매수 신호")
        
        congestion = mempool.get('congestion_level', 'Medium')
        if congestion == 'Low':
            bullish.append("⚡ 스윙강세: 네트워크 효율성 우수 - 거래 활성화 기대")
        
        # 트렌드 강세 요인 (중장기 기회)
        security_score_7d = mining.get('network_security_7d', mining.get('network_security_score', 85))
        if security_score_7d > 90:
            bullish.append(f"🛡️ 트렌드강세: 매우 높은 7일평균 네트워크 보안 ({security_score_7d:.1f}) - 신뢰도 증가")
        
        hodl_strength = holder_behavior.get('hodl_strength_score', 65)
        if hodl_strength > 80:
            bullish.append(f"💎 트렌드강세: 극강 HODL 심리 ({hodl_strength:.1f}) - 공급 부족 심화")
        
        accumulation = holder_behavior.get('accumulation_phase', False)
        if accumulation:
            bullish.append("📈 트렌드강세: 축적 단계 진입 - 장기 투자자 매수 증가")
        
        new_addresses_trend = addresses.get('new_addresses_trend', 'Stable')
        if new_addresses_trend == 'Increasing':
            bullish.append("👥 트렌드강세: 신규 주소 증가 - 새로운 사용자 유입")
        
        if hash_rate_7d_eh > 600:
            bullish.append(f"🏆 트렌드강세: 사상급 7일평균 해시레이트 ({hash_rate_7d_eh:.1f} EH/s) - 네트워크 성숙")
        
        # 종합 강세 신호
        activity_score = addresses.get('address_activity_score', 65)
        if activity_score > 85:
            bullish.append(f"🌟 종합강세: 탁월한 네트워크 활성도 ({activity_score}) - 생태계 번영")
        
        return bullish if bullish else ["현재 특별한 스윙/트렌드 강세 요인 없음"]

    async def analyze_with_ai(self, onchain_data: Dict) -> Dict:
        """AI 모델을 사용하여 온체인 데이터 종합 분석"""
        if self.client is None:
            self.client, self.model_name = self.get_model()
        
        #if self.client is None:
        #    logger.warning("AI 모델이 없어 규칙 기반 분석으로 대체합니다.")
        #    return self.rule_based_analysis(onchain_data)
        
        try:
            prompt = CONFIG["prompts"]["onchain_analysis"].format(
                onchain_data=json.dumps(onchain_data, ensure_ascii=False, indent=2)
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
                    'data_success_rate': onchain_data.get('collection_stats', {}).get('success_rate', 0),
                    'cache_info': onchain_data.get('collection_stats', {}).get('cache_recommendations', {}),
                    'raw_data': onchain_data
                }
                
                return result_json
            else:
                logger.error("AI 응답에서 JSON을 찾을 수 없습니다.")
                return self.rule_based_analysis(onchain_data)
                
        except Exception as e:
            logger.error(f"AI 온체인 분석 중 오류: {e}")
            return self.rule_based_analysis(onchain_data)
    
    def rule_based_analysis(self, onchain_data: Dict) -> Dict:
        """규칙 기반 온체인 분석 (AI 모델 없을 때 백업)"""
        try:
            # 온체인 신호 분석
            signal_analysis = self.analyze_onchain_signals(onchain_data)
            
            onchain_score = signal_analysis.get('onchain_score', 50.0)
            btc_signal = signal_analysis.get('btc_signal', 'Hold')
            
            # 투자 신호 매핑
            signal_mapping = {
                'Strong Buy': 'Strong Buy',
                'Buy': 'Buy', 
                'Hold': 'Hold',
                'Weak Sell': 'Sell',
                'Sell': 'Strong Sell'
            }
            
            investment_signal = signal_mapping.get(btc_signal, 'Hold')
            
            # 네트워크 건강도 분석
            network_health = signal_analysis.get('network_health', {})
            security_level = network_health.get('security_level', 'Medium')
            
            # 보유자 심리 분석
            user_behavior = signal_analysis.get('user_behavior', {})
            hodl_sentiment = user_behavior.get('hodl_sentiment', 'Mixed')
            
            # 채굴 환경 분석
            miner_sentiment = network_health.get('miner_sentiment', 'Neutral')
            
            # 주요 인사이트
            key_insights = []
            key_insights.extend(signal_analysis.get('key_signals', [])[:3])
            key_insights.extend(signal_analysis.get('bullish_factors', [])[:2])
            
            result = {
                "onchain_health_score": onchain_score,
                "investment_signal": investment_signal,
                "network_security_analysis": f"네트워크 보안 수준: {security_level}, 채굴자 심리: {miner_sentiment}",
                "holder_sentiment": f"HODL 심리: {hodl_sentiment}, 매도압력: {user_behavior.get('selling_pressure_level', 'Medium')}",
                "mining_outlook": f"채굴 환경: {network_health.get('hash_rate_trend', 'Moderate')}, 위험도: {signal_analysis.get('network_health', {}).get('miner_sentiment', 'Neutral')}",
                "liquidity_flow": f"네트워크 활성도: {signal_analysis.get('network_activity', {}).get('activity_level', 'Medium')}, 거래 수요: {signal_analysis.get('network_activity', {}).get('transaction_demand', 'Medium')}",
                "key_insights": key_insights[:5] if key_insights else ["온체인 데이터에서 특별한 신호 없음"],
                "risk_assessment": "; ".join(signal_analysis.get('risk_factors', ['현재 특별한 리스크 없음'])[:3]),
                "opportunity_analysis": "; ".join(signal_analysis.get('bullish_factors', ['현재 특별한 기회 없음'])[:3]),
                "confidence": max(50, min(95, int(onchain_score + signal_analysis.get('data_reliability', {}).get('success_rate', 0) * 0.3))),
                "analysis_summary": f"온체인 건강도 {onchain_score:.1f}점으로 '{signal_analysis.get('signal_strength', '중립')}' 신호. 투자 권장: {investment_signal}"
            }
            
            # 메타데이터 추가
            result['analysis_metadata'] = {
                'analysis_type': 'rule_based',
                'data_timestamp': datetime.now(timezone.utc).isoformat(),
                'model_used': 'rule_based_fallback',
                'data_success_rate': onchain_data.get('collection_stats', {}).get('success_rate', 0),
                'cache_info': onchain_data.get('collection_stats', {}).get('cache_recommendations', {}),
                'raw_data': onchain_data
            }
            
            return result
            
        except Exception as e:
            logger.error(f"규칙 기반 온체인 분석 중 오류: {e}")
            return {
                "onchain_health_score": 50.0,
                "investment_signal": "Hold",
                "error": str(e),
                "confidence": 0,
                "analysis_summary": f"온체인 분석 중 오류 발생: {str(e)}"
            }
    
    async def analyze_onchain_data(self) -> Dict:
        """온체인 데이터 분석 메인 함수"""
        try:
            logger.info("온체인 데이터 분석 시작")
            
            # 1. 온체인 데이터 수집
            onchain_raw_data = self.collect_onchain_data()
            
            # 2. 온체인 신호 분석
            signal_analysis = self.analyze_onchain_signals(onchain_raw_data)
            
            # 3. 데이터 통합
            comprehensive_data = {
                'raw_data': onchain_raw_data,
                'signal_analysis': signal_analysis,
                'analysis_timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            # 4. AI 종합 분석
            analysis_result = await self.analyze_with_ai(comprehensive_data)
            
            logger.info("온체인 데이터 분석 완료")
            
            return {
                "success": True,
                "result": analysis_result,
                "analysis_type": "onchain_data",
                "data_quality": {
                    "success_rate": onchain_raw_data.get('collection_stats', {}).get('success_rate', 0),
                    "total_categories": onchain_raw_data.get('collection_stats', {}).get('total_categories', 0),
                    "successful_categories": onchain_raw_data.get('collection_stats', {}).get('successful_categories', 0),
                    "data_sources": ['blockchain_info', 'coingecko', 'estimated_calculations'],
                    "cache_recommendations": onchain_raw_data.get('collection_stats', {}).get('cache_recommendations', {}),
                    "error_counts": self.error_counts.copy()
                }
            }
            
        except Exception as e:
            logger.error(f"온체인 데이터 분석 중 오류: {e}")
            return {
                "success": False,
                "error": f"분석 중 오류 발생: {str(e)}",
                "analysis_type": "onchain_data"
            }

# 외부에서 사용할 함수
async def analyze_onchain_data() -> Dict:
    """온체인 데이터를 분석하는 함수"""
    analyzer = OnchainAnalyzer()
    return await analyzer.analyze_onchain_data()

# 테스트용 코드
if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("🔍 온체인 데이터 분석 테스트 시작...")
        result = await analyze_onchain_data()
        
        if result['success']:
            print("✅ 온체인 분석 성공!")
            print(f"데이터 성공률: {result['data_quality']['success_rate']:.1f}%")
            print(f"온체인 건강도: {result['result']['onchain_health_score']:.1f}")
            print(f"투자 신호: {result['result']['investment_signal']}")
            print(f"캐싱 권장사항:")
            for category, ttl in result['data_quality']['cache_recommendations'].items():
                print(f"  {category}: {ttl}")
        else:
            print("❌ 온체인 분석 실패:")
            print(result['error'])
        
        print("\n" + "="*50)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())