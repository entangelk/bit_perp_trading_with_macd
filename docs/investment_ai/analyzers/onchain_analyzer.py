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
        logger.debug("CoinGecko API 키 적용됨")
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
        """Blockchain.info에서 기본 통계 수집 (캐싱 권장: 1시간)"""
        try:
            url = f"{self.data_sources['blockchain_info']['base_url']}/stats"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            return {
                'total_btc_supply': data.get('totalbc', 0) / 100000000,  # Satoshi -> BTC
                'market_cap_usd': data.get('market_price_usd', 0) * (data.get('totalbc', 0) / 100000000),
                'hash_rate': data.get('hash_rate', 0),
                'difficulty': data.get('difficulty', 0),
                'mempool_size': data.get('n_btc_mined', 0),
                'total_transactions': data.get('n_tx', 0),
                'blocks_count': data.get('n_blocks_total', 0),
                'avg_block_size': data.get('avg_block_size', 0),
                'minutes_between_blocks': data.get('minutes_between_blocks', 0),
                'trade_volume_btc': data.get('trade_volume_btc', 0),
                'trade_volume_usd': data.get('trade_volume_usd', 0),
                'timestamp': datetime.now().isoformat(),
                'source': 'blockchain_info',
                'cache_ttl': self.cache_ttl['network_metrics']
            }
            
        except Exception as e:
            logger.error(f"Blockchain.info 통계 수집 실패: {e}")
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
        """채굴 관련 지표 수집 (캐싱 권장: 2시간)"""
        try:
            # Blockchain.info에서 채굴 관련 데이터
            stats_data = self.get_blockchain_info_stats()
            
            hash_rate = stats_data.get('hash_rate', 0)
            difficulty = stats_data.get('difficulty', 0)
            
            # 해시레이트 단위 변환 수정 (정확한 변환)
            # Blockchain.info는 hash/s 단위로 제공, EH/s로 변환
            hash_rate_eh = hash_rate / 1e18 if hash_rate > 0 else 300  # 1 EH/s = 10^18 H/s
            
            # 채굴 지표 계산
            mining_difficulty_trend = 'Increasing' if difficulty > 50000000000000 else 'Stable'
            network_security = min(100, max(0, hash_rate_eh / 5 * 100))  # 500 EH/s = 100점 기준
            
            return {
                'hash_rate_eh': round(hash_rate_eh, 2),
                'hash_rate_raw': hash_rate,  # 원본 데이터도 포함
                'difficulty': difficulty,
                'mining_difficulty_trend': mining_difficulty_trend,
                'network_security_score': round(network_security, 1),
                'hash_rate_trend': 'Strong' if hash_rate_eh > 400 else 'Weak' if hash_rate_eh < 200 else 'Moderate',
                'miner_capitulation_risk': 'Low' if hash_rate_eh > 300 else 'High',
                'timestamp': datetime.now().isoformat(),
                'source': 'blockchain_info',
                'cache_ttl': self.cache_ttl['mining_metrics']
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
            
            # 최근 4시간 이내 데이터 찾기
            four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=4)
            
            cached_data = cache_collection.find_one({
                "task_name": "onchain_data",
                "created_at": {"$gte": four_hours_ago}
            }, sort=[("created_at", -1)])
            
            if cached_data and cached_data.get('data'):
                onchain_data = cached_data['data']
                if 'metrics' in onchain_data:
                    metrics = onchain_data['metrics']
                    return {
                        'total_btc_supply': metrics.get('total_btc_supply'),
                        'market_cap_usd': metrics.get('market_cap_usd'),
                        'hash_rate': metrics.get('hash_rate'),
                        'difficulty': metrics.get('difficulty'),
                        'mempool_size': metrics.get('mempool_size'),
                        'total_transactions': metrics.get('transaction_count'),
                        'blocks_count': metrics.get('blocks_count'),
                        'avg_block_size': metrics.get('avg_block_size'),
                        'minutes_between_blocks': metrics.get('minutes_between_blocks'),
                        'trade_volume_btc': metrics.get('trade_volume_btc'),
                        'trade_volume_usd': metrics.get('trade_volume_usd'),
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
        """MongoDB에서 과거 채굴 지표 데이터 가져오기"""
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
                return {
                    'hash_rate_eh': mining_data.get('hash_rate_eh'),
                    'hash_rate_raw': mining_data.get('hash_rate_raw'),
                    'difficulty': mining_data.get('difficulty'),
                    'mining_difficulty_trend': mining_data.get('mining_difficulty_trend'),
                    'network_security_score': mining_data.get('network_security_score'),
                    'hash_rate_trend': mining_data.get('hash_rate_trend'),
                    'miner_capitulation_risk': mining_data.get('miner_capitulation_risk'),
                    'timestamp': cached_data['created_at'].isoformat(),
                    'source': 'cached_data',
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
                onchain_data['network_stats'] = network_stats
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
        """온체인 데이터 신호 분석 (규칙 기반)"""
        try:
            # 네트워크 건강도 분석 - 올바른 데이터 접근
            network_stats = onchain_data.get('network_stats', {})
            mining_data = onchain_data.get('mining', {})
            
            # 수정된 데이터 접근
            hash_rate_eh = mining_data.get('hash_rate_eh', 350)  # mining에서 가져오기
            network_security_score = mining_data.get('network_security_score', 85)
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
            
            # 채굴 지표 - 올바른 접근
            miner_risk = mining_data.get('miner_capitulation_risk', 'Low')
            
            # 종합 점수 계산 (0-100) - 수정된 로직
            onchain_score = 0
            
            # 네트워크 보안 (30점 만점) - 수정된 기준
            if network_security_score > 80:
                onchain_score += 30
            elif network_security_score > 60:
                onchain_score += 20
            elif network_security_score > 40:
                onchain_score += 15
            elif network_security_score > 20:
                onchain_score += 10
            else:
                onchain_score += 5  # 최소 점수
            
            # HODL 강도 (25점 만점)
            if hodl_strength > 80:
                onchain_score += 25
            elif hodl_strength > 60:
                onchain_score += 18
            elif hodl_strength > 40:
                onchain_score += 12
            elif hodl_strength > 20:
                onchain_score += 6
            else:
                onchain_score += 2
            
            # 네트워크 활성도 (20점 만점)
            if activity_score > 80:
                onchain_score += 20
            elif activity_score > 60:
                onchain_score += 15
            elif activity_score > 40:
                onchain_score += 10
            elif activity_score > 20:
                onchain_score += 5
            else:
                onchain_score += 2
            
            # 메모리풀 상태 (15점 만점)
            if congestion_level == 'Low':
                onchain_score += 15
            elif congestion_level == 'Medium':
                onchain_score += 10
            else:  # High
                onchain_score += 5
            
            # 채굴자 리스크 (10점 만점)
            if miner_risk == 'Low':
                onchain_score += 10
            elif miner_risk == 'Medium':
                onchain_score += 7
            else:  # High
                onchain_score += 3
            
            # 신호 강도 분류
            if onchain_score >= 85:
                signal_strength = "매우 강함"
                btc_signal = "Strong Buy"
            elif onchain_score >= 70:
                signal_strength = "강함"
                btc_signal = "Buy"
            elif onchain_score >= 50:
                signal_strength = "중립"
                btc_signal = "Hold"
            elif onchain_score >= 30:
                signal_strength = "약함"
                btc_signal = "Weak Sell"
            else:
                signal_strength = "매우 약함"
                btc_signal = "Sell"
            
            return {
                'onchain_score': round(onchain_score, 1),
                'signal_strength': signal_strength,
                'btc_signal': btc_signal,
                'network_health': {
                    'security_level': 'High' if network_security_score > 70 else 'Medium' if network_security_score > 40 else 'Low',
                    'hash_rate_trend': 'Strong' if hash_rate_eh > 400 else 'Weak' if hash_rate_eh < 200 else 'Moderate',
                    'hash_rate_eh': hash_rate_eh,  # 실제 값 포함
                    'miner_sentiment': 'Bullish' if miner_risk == 'Low' else 'Bearish' if miner_risk == 'High' else 'Neutral'
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
                'key_signals': self._identify_key_signals(onchain_data, onchain_score),
                'risk_factors': self._identify_onchain_risks(onchain_data),
                'bullish_factors': self._identify_bullish_factors(onchain_data),
                'data_reliability': {
                    'success_rate': onchain_data.get('collection_stats', {}).get('success_rate', 0),
                    'confidence': 'High' if onchain_data.get('collection_stats', {}).get('success_rate', 0) > 80 else 'Medium' if onchain_data.get('collection_stats', {}).get('success_rate', 0) > 50 else 'Low'
                },
                'debug_info': {  # 디버깅 정보 추가
                    'hash_rate_eh': hash_rate_eh,
                    'network_security_score': network_security_score,
                    'score_breakdown': {
                        'security_points': 30 if network_security_score > 80 else 20 if network_security_score > 60 else 15 if network_security_score > 40 else 10 if network_security_score > 20 else 5,
                        'hodl_points': 25 if hodl_strength > 80 else 18 if hodl_strength > 60 else 12 if hodl_strength > 40 else 6 if hodl_strength > 20 else 2,
                        'activity_points': 20 if activity_score > 80 else 15 if activity_score > 60 else 10 if activity_score > 40 else 5 if activity_score > 20 else 2,
                        'mempool_points': 15 if congestion_level == 'Low' else 10 if congestion_level == 'Medium' else 5,
                        'miner_points': 10 if miner_risk == 'Low' else 7 if miner_risk == 'Medium' else 3
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"온체인 신호 분석 중 오류: {e}")
            return {
                'onchain_score': 50.0,
                'signal_strength': '중립',
                'btc_signal': 'Hold',
                'error': str(e),
                'data_reliability': {'success_rate': 0, 'confidence': 'None'}
            }

    def _identify_key_signals(self, onchain_data: Dict, score: float) -> List[str]:
        """주요 온체인 신호들 식별"""
        signals = []
        
        holder_behavior = onchain_data.get('holder_behavior', {})
        hodl_strength = holder_behavior.get('hodl_strength_score', 65)
        
        if hodl_strength > 75:
            signals.append(f"강한 HODL 패턴 ({hodl_strength:.1f}) - 장기 보유 증가")
        
        mining = onchain_data.get('mining', {})
        hash_rate_eh = mining.get('hash_rate_eh', 350)
        if hash_rate_eh > 400:
            signals.append(f"높은 해시레이트 ({hash_rate_eh:.1f} EH/s) - 네트워크 보안 강화")
        
        addresses = onchain_data.get('addresses', {})
        activity_score = addresses.get('address_activity_score', 65)
        if activity_score > 80:
            signals.append(f"높은 네트워크 활성도 ({activity_score}) - 사용자 참여 증가")
        
        mempool = onchain_data.get('mempool', {})
        congestion = mempool.get('congestion_level', 'Medium')
        if congestion == 'Low':
            signals.append("낮은 네트워크 혼잡도 - 거래 효율성 양호")
        
        if score > 70:
            signals.append("온체인 지표 종합: 강세 신호 우세")
        
        return signals if signals else ["현재 뚜렷한 온체인 신호 없음"]
    
    def _identify_onchain_risks(self, onchain_data: Dict) -> List[str]:
        """온체인 리스크 요인들"""
        risks = []
        
        mining = onchain_data.get('mining', {})
        miner_risk = mining.get('miner_capitulation_risk', 'Low')
        if miner_risk == 'High':
            risks.append("채굴자 항복 위험 - 해시레이트 급락 가능성")
        
        holder_behavior = onchain_data.get('holder_behavior', {})
        selling_pressure = holder_behavior.get('selling_pressure', 'Medium')
        if selling_pressure == 'High':
            risks.append("높은 매도 압력 - 대량 물량 출회 위험")
        
        mempool = onchain_data.get('mempool', {})
        unconfirmed = mempool.get('unconfirmed_transactions', 25000)
        if unconfirmed > 50000:
            risks.append(f"심각한 네트워크 혼잡 ({unconfirmed:,}건) - 거래 지연")
        
        network_stats = onchain_data.get('network_stats', {})
        hash_rate_eh = mining.get('hash_rate_eh', 350)
        if hash_rate_eh < 200:
            risks.append(f"낮은 해시레이트 ({hash_rate_eh:.1f} EH/s) - 네트워크 보안 약화")
        
        addresses = onchain_data.get('addresses', {})
        activity_score = addresses.get('address_activity_score', 65)
        if activity_score < 40:
            risks.append(f"낮은 네트워크 활성도 ({activity_score}) - 사용자 이탈")
        
        return risks if risks else ["현재 특별한 온체인 리스크 없음"]
    
    def _identify_bullish_factors(self, onchain_data: Dict) -> List[str]:
        """강세 요인들"""
        bullish = []
        
        holder_behavior = onchain_data.get('holder_behavior', {})
        accumulation = holder_behavior.get('accumulation_phase', False)
        if accumulation:
            bullish.append("축적 단계 진입 - 장기 투자자 매수 증가")
        
        mining = onchain_data.get('mining', {})
        security_score = mining.get('network_security_score', 85)
        if security_score > 90:
            bullish.append(f"매우 높은 네트워크 보안 ({security_score:.1f}) - 신뢰도 증가")
        
        addresses = onchain_data.get('addresses', {})
        new_addresses_trend = addresses.get('new_addresses_trend', 'Stable')
        if new_addresses_trend == 'Increasing':
            bullish.append("신규 주소 증가 - 새로운 사용자 유입")
        
        holder_behavior = onchain_data.get('holder_behavior', {})
        hodl_strength = holder_behavior.get('hodl_strength_score', 65)
        if hodl_strength > 80:
            bullish.append(f"극강 HODL 심리 ({hodl_strength:.1f}) - 공급 부족 심화")
        
        network_stats = onchain_data.get('network_stats', {})
        hash_rate_eh = mining.get('hash_rate_eh', 350)
        if hash_rate_eh > 450:
            bullish.append(f"사상 최고 해시레이트 ({hash_rate_eh:.1f} EH/s) - 채굴자 신뢰")
        
        return bullish if bullish else ["현재 특별한 강세 요인 없음"]
    
    async def analyze_with_ai(self, onchain_data: Dict) -> Dict:
        """AI 모델을 사용하여 온체인 데이터 종합 분석"""
        if self.client is None:
            self.client, self.model_name = self.get_model()
        
        if self.client is None:
            logger.warning("AI 모델이 없어 규칙 기반 분석으로 대체합니다.")
            return self.rule_based_analysis(onchain_data)
        
        try:
            prompt = CONFIG["prompts"]["onchain_analysis"].format(
                onchain_data=json.dumps(onchain_data, ensure_ascii=False, indent=2)
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