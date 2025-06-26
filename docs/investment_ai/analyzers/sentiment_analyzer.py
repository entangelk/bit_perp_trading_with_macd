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
            return self._get_dummy_fear_greed()
        except Exception as e:
            logger.error(f"공포/탐욕 지수 처리 중 오류: {e}")
            return self._get_dummy_fear_greed()
    
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
    
    def _get_dummy_fear_greed(self) -> Dict:
        """공포/탐욕 지수 더미 데이터 (API 실패시)"""
        return {
            'current_value': 50,
            'current_classification': 'Neutral',
            'week_average': 50.0,
            'trend_change': 0,
            'trend_direction': 'stable',
            'historical_data': [],
            'market_sentiment': 'neutral',
            'error': 'API 호출 실패로 더미 데이터 사용'
        }
    
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
                                all_news.append({
                                    'title': entry.get('title', ''),
                                    'summary': entry.get('summary', '')[:300],  # 요약 길이 제한
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
            return self._get_dummy_news()
    
    def _get_dummy_news(self) -> List[Dict]:
        """더미 뉴스 데이터 (뉴스 수집 실패시)"""
        return [
            {
                'title': 'Bitcoin Market Update',
                'summary': 'Bitcoin continues to show mixed signals in the current market environment.',
                'source': 'dummy',
                'published_time': datetime.now().isoformat(),
                'link': ''
            }
        ]
    
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
        # 필요할 때만 모델 초기화
        if self.client is None:
            self.client, self.model_name = self.get_model()
        
        if self.client is None:
            logger.warning("AI 모델이 없어 규칙 기반 분석으로 대체합니다.")
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
    
    async def analyze_market_sentiment(self) -> Dict:
        """시장 심리 분석 메인 함수 (스케줄러 사용)"""
        try:
            logger.info("시장 심리 분석 시작 (스케줄러 사용)")
            
            # 스케줄러에서 캐시된 데이터 사용
            try:
                from docs.investment_ai.data_scheduler import get_fear_greed_data, get_news_data
                
                # 1. 공포/탐욕 지수 (캐시된 데이터 또는 새로 수집)
                fg_cached = await get_fear_greed_data()
                if fg_cached and fg_cached.get('data'):
                    fear_greed_data = self._process_cached_fear_greed(fg_cached['data'])
                else:
                    fear_greed_data = self.get_fear_greed_index()
                
                # 2. 뉴스 (캐시된 데이터 또는 새로 수집)
                news_cached = await get_news_data()
                if news_cached and news_cached.get('news'):
                    recent_news = news_cached['news']
                else:
                    recent_news = self.get_crypto_news()
                
            except Exception as e:
                logger.warning(f"스케줄러 데이터 사용 실패, 직접 수집: {e}")
                # 백업: 직접 수집
                fear_greed_data = self.get_fear_greed_index()
                recent_news = self.get_crypto_news()
            
            # 3. 뉴스 감정 분석
            news_sentiment = self.analyze_news_sentiment(recent_news)
            
            # 4. 데이터 통합
            sentiment_data = {
                'fear_greed_index': fear_greed_data,
                'news_sentiment': news_sentiment,
                'recent_news': recent_news,
                'data_collection_time': datetime.now(timezone.utc).isoformat()
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