import json
import re
import logging
import requests
import feedparser
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
logger = logging.getLogger("sentiment_analyzer")

class SentimentAnalyzer:
    """시장 심리 분석 AI - 1단계 (뉴스 + 공포/탐욕 지수)"""
    
    def __init__(self):
        # AI 모델 초기화 제거 - 실제 호출 시에만 초기화
        self.client = None
        self.model_name = None
        
        # 실패 카운트 추가
        self.error_counts = {
            'fear_greed': 0,
            'news': 0
        }
        self.max_errors = 3  # 최대 허용 오류 수
        
        # 뉴스 소스 설정
        self.news_sources = {
            'cointelegraph': 'https://cointelegraph.com/rss',
            'coindesk': 'https://www.coindesk.com/arc/outboundfeeds/rss/',
            'decrypt': 'https://decrypt.co/feed',
            'bitcoinist': 'https://bitcoinist.com/feed/'
        }
        
        # Fear & Greed Index API
        self.fear_greed_api = "https://api.alternative.me/fng/"
    
    def get_fear_greed_index(self, days: int = 7) -> Dict:
        """공포/탐욕 지수 수집"""
        try:
            # Alternative.me API 호출
            response = requests.get(f"{self.fear_greed_api}?limit={days}", timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if 'data' not in data:
                raise ValueError("공포/탐욕 지수 데이터 형식 오류")
            
            fear_greed_data = []
            for item in data['data']:
                fear_greed_data.append({
                    'value': int(item['value']),
                    'classification': item['value_classification'],
                    'timestamp': item['timestamp'],
                    'date': datetime.fromtimestamp(int(item['timestamp'])).strftime('%Y-%m-%d')
                })
            
            # 최신 데이터와 평균 계산
            latest = fear_greed_data[0]
            avg_value = sum(item['value'] for item in fear_greed_data) / len(fear_greed_data)
            
            # 추세 계산 (7일간 변화)
            if len(fear_greed_data) >= 7:
                trend = fear_greed_data[0]['value'] - fear_greed_data[6]['value']
                trend_direction = 'increasing' if trend > 5 else 'decreasing' if trend < -5 else 'stable'
            else:
                trend = 0
                trend_direction = 'stable'
            
            result = {
                'current_value': latest['value'],
                'current_classification': latest['classification'],
                'week_average': round(avg_value, 1),
                'trend_change': trend,
                'trend_direction': trend_direction,
                'historical_data': fear_greed_data,
                'market_sentiment': self._classify_market_sentiment(latest['value'])
            }
            
            logger.info(f"공포/탐욕 지수 수집 완료: {latest['value']} ({latest['classification']})")
            return result
            
        except requests.RequestException as e:
            logger.error(f"공포/탐욕 지수 API 호출 실패: {e}")
            self.error_counts['fear_greed'] += 1
            return self._get_cached_fear_greed()
        except Exception as e:
            logger.error(f"공포/탐욕 지수 처리 중 오류: {e}")
            self.error_counts['fear_greed'] += 1
            return self._get_cached_fear_greed()
    
    def _classify_market_sentiment(self, value: int) -> str:
        """공포/탐욕 지수 값을 시장 심리로 분류"""
        if value >= 75:
            return "extreme_greed"
        elif value >= 55:
            return "greed"
        elif value >= 45:
            return "neutral"
        elif value >= 25:
            return "fear"
        else:
            return "extreme_fear"
    
    def _get_cached_fear_greed(self) -> Optional[Dict]:
        """MongoDB에서 과거 공포/탐욕 지수 데이터 가져오기"""
        try:
            from pymongo import MongoClient
            from datetime import datetime, timezone, timedelta
            
            client = MongoClient("mongodb://mongodb:27017")
            db = client["bitcoin"]
            cache_collection = db["data_cache"]
            
            # 최근 7일 이내 데이터 찾기
            seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
            
            cached_data = cache_collection.find_one({
                "task_name": "fear_greed_index",
                "created_at": {"$gte": seven_days_ago}
            }, sort=[("created_at", -1)])
            
            if cached_data and cached_data.get('data'):
                fg_data = cached_data['data']['data'][0]  # 최신 데이터
                return {
                    'current_value': int(fg_data['value']),
                    'current_classification': fg_data['value_classification'],
                    'week_average': int(fg_data['value']),  # 단일 데이터이므로 동일
                    'trend_change': 0,
                    'trend_direction': 'stable',
                    'historical_data': [{
                        'value': int(fg_data['value']),
                        'classification': fg_data['value_classification'],
                        'timestamp': fg_data['timestamp'],
                        'date': datetime.fromtimestamp(int(fg_data['timestamp'])).strftime('%Y-%m-%d')
                    }],
                    'market_sentiment': self._classify_market_sentiment(int(fg_data['value'])),
                    'cached_data_age': str(datetime.now(timezone.utc) - cached_data['created_at'])
                }
            
            logger.warning("공포/탐욕 지수: 캐시된 데이터 없음")
            return None
            
        except Exception as e:
            logger.error(f"캐시된 공포/탐욕 데이터 조회 실패: {e}")
            return None
    
    def _clean_summary(self, summary: str) -> str:
        """HTML 태그와 불필요한 내용을 제거하고 유의미한 텍스트 추출"""
        if not summary:
            return ""
        
        # HTML 태그 제거
        import re
        clean_text = re.sub(r'<[^>]+>', '', summary)
        
        # HTML 엔티티 디코딩
        import html
        clean_text = html.unescape(clean_text)
        
        # 불필요한 공백 정리
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # 텍스트가 너무 짧으면 원본 반환 (최소 50자)
        if len(clean_text) < 50:
            return clean_text[:300] if clean_text else ""
        
        # 문장 단위로 분할하여 중간 부분 추출
        sentences = re.split(r'[.!?]+', clean_text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
        
        if len(sentences) <= 1:
            # 문장이 1개 이하면 전체 텍스트 사용
            return clean_text[:300]
        elif len(sentences) == 2:
            # 문장이 2개면 둘 다 사용
            return '. '.join(sentences)[:300]
        else:
            # 문장이 3개 이상이면 중간 부분 우선 사용
            if len(sentences) >= 3:
                # 첫 번째 문장 제외하고 중간부터 사용
                middle_text = '. '.join(sentences[1:])
                if len(middle_text) >= 100:  # 중간 부분이 충분히 길면 사용
                    return middle_text[:300]
            
            # 중간 부분이 짧으면 전체 사용
            return '. '.join(sentences)[:300]

    def get_crypto_news(self, limit: int = 20) -> List[Dict]:
        """암호화폐 뉴스 수집"""
        try:
            all_news = []
            
            for source_name, rss_url in self.news_sources.items():
                try:
                    # RSS 피드 파싱
                    feed = feedparser.parse(rss_url)
                    
                    for entry in feed.entries[:limit//len(self.news_sources)]:
                        # 비트코인 관련 뉴스만 필터링
                        title = entry.get('title', '').lower()
                        summary = entry.get('summary', '').lower()
                        
                        bitcoin_keywords = ['bitcoin', 'btc', 'cryptocurrency', 'crypto']
                        if any(keyword in title or keyword in summary for keyword in bitcoin_keywords):
                            
                            # 발행 시간 처리
                            published_time = None
                            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                                published_time = datetime(*entry.published_parsed[:6])
                            elif hasattr(entry, 'published'):
                                try:
                                    published_time = datetime.strptime(entry.published, '%a, %d %b %Y %H:%M:%S %Z')
                                except:
                                    published_time = datetime.now()
                            else:
                                published_time = datetime.now()
                            
                            # 24시간 이내 뉴스만
                            if published_time > datetime.now() - timedelta(hours=24):
                                # summary 정리 처리
                                clean_summary = self._clean_summary(entry.get('summary', ''))
                                
                                all_news.append({
                                    'title': entry.get('title', ''),
                                    'summary': clean_summary,
                                    'source': source_name,
                                    'published_time': published_time.isoformat(),
                                    'link': entry.get('link', '')
                                })
                                
                except Exception as e:
                    logger.warning(f"{source_name} RSS 파싱 실패: {e}")
                    continue
            
            # 시간순 정렬 (최신순)
            all_news.sort(key=lambda x: x['published_time'], reverse=True)
            
            logger.info(f"암호화폐 뉴스 수집 완료: {len(all_news)}개")
            return all_news[:limit]
            
        except Exception as e:
            logger.error(f"뉴스 수집 중 오류: {e}")
            self.error_counts['news'] += 1
            return self._get_cached_news()
    
    def _get_cached_news(self) -> Optional[List[Dict]]:
        """MongoDB에서 과거 뉴스 데이터 가져오기"""
        try:
            from pymongo import MongoClient
            from datetime import datetime, timezone, timedelta
            
            client = MongoClient("mongodb://mongodb:27017")
            db = client["bitcoin"]
            cache_collection = db["data_cache"]
            
            # 최근 24시간 이내 뉴스 데이터 찾기
            one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
            
            cached_data = cache_collection.find_one({
                "task_name": "crypto_news",
                "created_at": {"$gte": one_day_ago}
            }, sort=[("created_at", -1)])
            
            if cached_data and cached_data.get('data', {}).get('news'):
                return cached_data['data']['news']
            
            logger.warning("뉴스 데이터: 캐시된 데이터 없음")
            return None
            
        except Exception as e:
            logger.error(f"캐시된 뉴스 데이터 조회 실패: {e}")
            return None
    
    def analyze_news_sentiment(self, news_list: List[Dict]) -> Dict:
        """뉴스 감정 분석 (간단한 키워드 기반)"""
        try:
            if not news_list:
                return {
                    'overall_sentiment': 'neutral',
                    'sentiment_score': 0,
                    'positive_count': 0,
                    'negative_count': 0,
                    'neutral_count': 0
                }
            
            # 긍정/부정 키워드
            positive_keywords = [
                'rise', 'surge', 'gain', 'bull', 'bullish', 'pump', 'moon', 'rally',
                'breakthrough', 'adoption', 'institutional', 'etf', 'approval',
                'positive', 'optimistic', 'growth', 'increase', 'up', 'high'
            ]
            
            negative_keywords = [
                'fall', 'drop', 'crash', 'bear', 'bearish', 'dump', 'decline',
                'correction', 'sell-off', 'fear', 'panic', 'regulation', 'ban',
                'negative', 'pessimistic', 'loss', 'decrease', 'down', 'low'
            ]
            
            sentiment_scores = []
            positive_count = 0
            negative_count = 0
            neutral_count = 0
            
            for news in news_list:
                text = f"{news['title']} {news['summary']}".lower()
                
                pos_score = sum(1 for keyword in positive_keywords if keyword in text)
                neg_score = sum(1 for keyword in negative_keywords if keyword in text)
                
                if pos_score > neg_score:
                    sentiment_scores.append(1)
                    positive_count += 1
                elif neg_score > pos_score:
                    sentiment_scores.append(-1)
                    negative_count += 1
                else:
                    sentiment_scores.append(0)
                    neutral_count += 1
            
            # 전체 감정 점수
            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
            
            # 전체 감정 분류
            if avg_sentiment > 0.3:
                overall_sentiment = 'positive'
            elif avg_sentiment < -0.3:
                overall_sentiment = 'negative'
            else:
                overall_sentiment = 'neutral'
            
            return {
                'overall_sentiment': overall_sentiment,
                'sentiment_score': round(avg_sentiment, 2),
                'positive_count': positive_count,
                'negative_count': negative_count,
                'neutral_count': neutral_count,
                'total_news': len(news_list)
            }
            
        except Exception as e:
            logger.error(f"뉴스 감정 분석 중 오류: {e}")
            return {
                'overall_sentiment': 'neutral',
                'sentiment_score': 0,
                'positive_count': 0,
                'negative_count': 0,
                'neutral_count': 0,
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
                    logger.warning(f"시장 심리 분석 모델 {model_name} 초기화 실패: {e}")
                    continue
            
            return None, None
            
        except Exception as e:
            logger.error(f"시장 심리 분석 모델 초기화 중 오류: {e}")
            return None, None

    async def analyze_with_ai(self, sentiment_data: Dict) -> Dict:
        """AI 모델을 사용하여 시장 심리 종합 분석"""
        from ..data_scheduler import mark_ai_api_success, mark_ai_api_failure
        
        # 필요할 때만 모델 초기화
        if self.client is None:
            self.client, self.model_name = self.get_model()
        
        if self.client is None:
            logger.warning("AI 모델이 없어 규칙 기반 분석으로 대체합니다.")
            mark_ai_api_failure()
            return self.rule_based_analysis(sentiment_data)
        
        try:
            # 프롬프트 구성
            prompt = CONFIG["prompts"]["sentiment_analysis"].format(
                fear_greed_data=json.dumps(sentiment_data['fear_greed_index'], ensure_ascii=False, indent=2),
                news_data=json.dumps(sentiment_data['news_sentiment'], ensure_ascii=False, indent=2),
                recent_news=json.dumps(sentiment_data['recent_news'][:5], ensure_ascii=False, indent=2)  # 최근 5개 뉴스만
            )
            
            # AI 모델에 질의
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=-1)
                )
            )
            
            # AI API 성공 기록
            mark_ai_api_success()
            
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
                    'raw_data': sentiment_data
                }
                
                return result_json
            else:
                logger.error("AI 응답에서 JSON을 찾을 수 없습니다.")
                return self.rule_based_analysis(sentiment_data)
                
        except Exception as e:
            logger.error(f"AI 시장 심리 분석 중 오류: {e}")
            mark_ai_api_failure()
            return self.rule_based_analysis(sentiment_data)
    
    def rule_based_analysis(self, sentiment_data: Dict) -> Dict:
        """규칙 기반 시장 심리 분석 (AI 모델 없을 때 백업)"""
        try:
            fear_greed = sentiment_data.get('fear_greed_index', {})
            news_sentiment = sentiment_data.get('news_sentiment', {})
            
            # 공포/탐욕 지수 점수
            fg_value = fear_greed.get('current_value', 50)
            fg_score = (fg_value - 50) / 50  # -1 ~ 1 범위로 정규화
            
            # 뉴스 감정 점수
            news_score = news_sentiment.get('sentiment_score', 0)
            
            # 가중평균 (공포/탐욕 지수 70%, 뉴스 30%)
            combined_score = (fg_score * 0.7) + (news_score * 0.3)
            
            # 시장 심리 점수 (0-100)
            market_sentiment_score = max(0, min(100, (combined_score + 1) * 50))
            
            # 심리 상태 분류
            if market_sentiment_score >= 80:
                sentiment_state = "극도의 탐욕"
                market_impact = "과열 위험"
            elif market_sentiment_score >= 65:
                sentiment_state = "탐욕"
                market_impact = "상승 모멘텀"
            elif market_sentiment_score >= 35:
                sentiment_state = "중립"
                market_impact = "혼조세"
            elif market_sentiment_score >= 20:
                sentiment_state = "공포"
                market_impact = "하락 압력"
            else:
                sentiment_state = "극도의 공포"
                market_impact = "바닥 신호 가능성"
            
            # 투자 심리 영향
            if market_sentiment_score > 60:
                investment_recommendation = "주의 깊은 관찰"
            elif market_sentiment_score < 40:
                investment_recommendation = "기회 모색"
            else:
                investment_recommendation = "중립적 접근"
            
            result = {
                "market_sentiment_score": round(market_sentiment_score, 1),
                "sentiment_state": sentiment_state,
                "market_impact": market_impact,
                "investment_recommendation": investment_recommendation,
                "fear_greed_analysis": {
                    "current_value": fg_value,
                    "classification": fear_greed.get('current_classification', 'Neutral'),
                    "trend": fear_greed.get('trend_direction', 'stable'),
                    "interpretation": self._interpret_fear_greed(fg_value)
                },
                "news_analysis": {
                    "overall_sentiment": news_sentiment.get('overall_sentiment', 'neutral'),
                    "positive_ratio": round(news_sentiment.get('positive_count', 0) / max(1, news_sentiment.get('total_news', 1)) * 100, 1),
                    "negative_ratio": round(news_sentiment.get('negative_count', 0) / max(1, news_sentiment.get('total_news', 1)) * 100, 1),
                    "total_news_analyzed": news_sentiment.get('total_news', 0)
                },
                "combined_analysis": {
                    "fear_greed_weight": 70,
                    "news_weight": 30,
                    "combined_score": round(combined_score, 3),
                    "confidence": min(90, max(40, abs(combined_score) * 80 + 40))
                },
                "confidence": min(90, max(40, abs(combined_score) * 80 + 40)),
                "analysis_summary": f"공포/탐욕 지수 {fg_value}와 뉴스 감정을 종합한 시장 심리는 '{sentiment_state}' 상태입니다."
            }
            
            # 메타데이터 추가
            result['analysis_metadata'] = {
                'analysis_type': 'rule_based',
                'data_timestamp': datetime.now(timezone.utc).isoformat(),
                'model_used': 'rule_based_fallback',
                'raw_data': sentiment_data
            }
            
            return result
            
        except Exception as e:
            logger.error(f"규칙 기반 시장 심리 분석 중 오류: {e}")
            return {
                "market_sentiment_score": 50,
                "sentiment_state": "중립",
                "error": str(e),
                "confidence": 0,
                "analysis_summary": f"시장 심리 분석 중 오류 발생: {str(e)}"
            }
    
    def _interpret_fear_greed(self, value: int) -> str:
        """공포/탐욕 지수 해석"""
        if value >= 75:
            return "시장이 과열 상태로 조정 가능성"
        elif value >= 55:
            return "낙관적 분위기로 상승 모멘텀"
        elif value >= 45:
            return "균형 잡힌 시장 상태"
        elif value >= 25:
            return "불안감 확산으로 하락 압력"
        else:
            return "극도의 공포로 반등 기회 모색"
    
    def _process_cached_fear_greed(self, cached_data: Dict) -> Dict:
        """스케줄러에서 가져온 캐시된 공포/탐욕 데이터 처리"""
        try:
            if 'data' not in cached_data:
                return self._get_dummy_fear_greed()
            
            fear_greed_data = []
            for item in cached_data['data']:
                fear_greed_data.append({
                    'value': int(item['value']),
                    'classification': item['value_classification'],
                    'timestamp': item['timestamp'],
                    'date': datetime.fromtimestamp(int(item['timestamp'])).strftime('%Y-%m-%d')
                })
            
            # 최신 데이터와 평균 계산
            latest = fear_greed_data[0]
            avg_value = sum(item['value'] for item in fear_greed_data) / len(fear_greed_data)
            
            # 추세 계산
            if len(fear_greed_data) >= 7:
                trend = fear_greed_data[0]['value'] - fear_greed_data[6]['value']
                trend_direction = 'increasing' if trend > 5 else 'decreasing' if trend < -5 else 'stable'
            else:
                trend = 0
                trend_direction = 'stable'
            
            return {
                'current_value': latest['value'],
                'current_classification': latest['classification'],
                'week_average': round(avg_value, 1),
                'trend_change': trend,
                'trend_direction': trend_direction,
                'historical_data': fear_greed_data,
                'market_sentiment': self._classify_market_sentiment(latest['value']),
                'cached': True
            }
            
        except Exception as e:
            logger.error(f"캐시된 공포/탐욕 데이터 처리 오류: {e}")
            return self._get_dummy_fear_greed()
    
    def check_data_availability(self) -> bool:
        """데이터 사용 가능 여부 확인"""
        if (self.error_counts['fear_greed'] >= self.max_errors and 
            self.error_counts['news'] >= self.max_errors):
            return False
        return True
    
    async def analyze_market_sentiment(self) -> Dict:
        """시장 심리 분석 메인 함수 - 수정된 버전 (순환 import 해결)"""
        try:
            logger.info("시장 심리 분석 시작")
            
            # 데이터 사용 가능 여부 확인
            if not self.check_data_availability():
                logger.warning("심리 분석: 모든 데이터 소스 실패 - 분석 건너뛰기")
                return {
                    "success": False,
                    "error": "모든 데이터 소스에서 연속 실패 - 분석 불가",
                    "analysis_type": "market_sentiment",
                    "skip_reason": "insufficient_data"
                }
            
            # 🔧 수정: 스케줄러 사용 대신 직접 MongoDB에서 캐시 조회 + 직접 수집
            
            # 1. 공포/탐욕 지수 - 캐시된 데이터 우선 사용
            fear_greed_data = self._get_cached_fear_greed()
            if fear_greed_data is None:
                # 캐시에 없으면 직접 수집
                fear_greed_data = self.get_fear_greed_index()
            
            # 2. 뉴스 데이터 - 캐시된 데이터 우선 사용  
            recent_news = self._get_cached_news()
            if recent_news is None:
                # 캐시에 없으면 직접 수집
                recent_news = self.get_crypto_news()
            
            # 데이터 유효성 검사
            if fear_greed_data is None and (recent_news is None or len(recent_news) == 0):
                logger.warning("심리 분석: 사용 가능한 데이터 없음")
                return {
                    "success": False,
                    "error": "유효한 데이터 없음 - 분석 불가",
                    "analysis_type": "market_sentiment",
                    "skip_reason": "no_valid_data"
                }
            
            # 3. 뉴스 감정 분석
            news_sentiment = self.analyze_news_sentiment(recent_news or [])
            
            # 4. 데이터 통합
            sentiment_data = {
                'fear_greed_index': fear_greed_data,
                'news_sentiment': news_sentiment,
                'recent_news': recent_news or [],
                'data_collection_time': datetime.now(timezone.utc).isoformat(),
                'data_quality': {
                    'fear_greed_available': fear_greed_data is not None,
                    'news_available': recent_news is not None and len(recent_news) > 0,
                    'error_counts': self.error_counts.copy()
                }
            }
            
            # 5. AI 종합 분석
            analysis_result = await self.analyze_with_ai(sentiment_data)
            
            logger.info("시장 심리 분석 완료")
            
            return {
                "success": True,
                "result": analysis_result,
                "analysis_type": "market_sentiment"
            }
            
        except Exception as e:
            logger.error(f"시장 심리 분석 중 오류: {e}")
            return {
                "success": False,
                "error": f"분석 중 오류 발생: {str(e)}",
                "analysis_type": "market_sentiment"
            }

# 외부에서 사용할 함수
async def analyze_market_sentiment() -> Dict:
    """시장 심리를 분석하는 함수"""
    analyzer = SentimentAnalyzer()
    return await analyzer.analyze_market_sentiment()

# 테스트용 코드
if __name__ == "__main__":
    import asyncio
    
    async def test():
        result = await analyze_market_sentiment()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())