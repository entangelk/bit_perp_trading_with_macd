from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
import json
import logging
from docs.investment_ai.data_scheduler import get_data_status, get_recovery_status, get_ai_api_status_summary

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="/app/trading_bot/templates")

class AIAnalysisViewer:
    """AI 분석 결과 조회 클래스"""
    
    def __init__(self):
        self.client = MongoClient("mongodb://mongodb:27017")
        self.database = self.client["bitcoin"]
        self.cache_collection = self.database["data_cache"]
    
    def get_analysis_tasks(self) -> List[str]:
        """사용 가능한 AI 분석 작업 목록 반환"""
        return [
            "ai_sentiment_analysis",
            "ai_technical_analysis", 
            "ai_macro_analysis",
            "ai_onchain_analysis",
            "ai_institutional_analysis",
            "final_decision"
        ]

    def sort_by_latest_first(self, analyses: List[Dict]) -> List[Dict]:
        """분석기별 최신 데이터를 맨 위로 이동"""
        if not analyses:
            return analyses
        
        # 각 분석기별 최신 데이터 찾기
        latest_by_task = {}
        other_analyses = []
        
        for analysis in analyses:
            task_name = analysis.get('task_name')
            if task_name not in latest_by_task:
                # 첫 번째로 발견된 것이 최신 (이미 시간순 역순 정렬되어 있음)
                latest_by_task[task_name] = analysis
            else:
                # 최신이 아닌 나머지들
                other_analyses.append(analysis)
        
        # 최신 데이터들을 맨 위로, 나머지는 시간순으로 유지
        latest_analyses = list(latest_by_task.values())
        # 최신 데이터들도 시간순 정렬
        latest_analyses.sort(key=lambda x: x.get('created_at', datetime.min), reverse=True)
        
        return latest_analyses + other_analyses

    def get_task_display_name(self, task_name: str) -> str:
        """작업명을 표시용 이름으로 변환"""
        name_mapping = {
            "ai_sentiment_analysis": "시장 감정 분석",
            "ai_technical_analysis": "기술적 분석",
            "ai_macro_analysis": "거시경제 분석", 
            "ai_onchain_analysis": "온체인 분석",
            "ai_institutional_analysis": "기관투자 분석",
            "final_decision": "최종 AI 투자 결정"
        }
        return name_mapping.get(task_name, task_name)
    
    def get_recent_analyses(self, task_name: Optional[str] = None, hours: int = 24, limit: int = 50, for_blog: bool = False) -> List[Dict]:
        """최근 AI 분석 결과 조회"""
        try:
            # 시간 범위 설정
            since_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            # 쿼리 조건 구성
            query = {
                "created_at": {"$gte": since_time}
            }
            
            if task_name:
                query["task_name"] = task_name
            else:
                # AI 분석 작업만 조회
                query["task_name"] = {"$in": self.get_analysis_tasks()}
            
            # 데이터 조회
            cursor = self.cache_collection.find(query).sort("created_at", -1).limit(limit)
            
            results = []
            for doc in cursor:
                try:
                    # 분석 결과 추출
                    analysis_data = doc.get("data", {})

                    has_success = analysis_data.get("success", False)
                    has_result = "result" in analysis_data and analysis_data["result"] is not None

                    # 기본 정보
                    result = {
                        "task_name": doc.get("task_name"),
                        "display_name": self.get_task_display_name(doc.get("task_name", "")),
                        "created_at": doc.get("created_at"),
                        "expire_at": doc.get("expire_at"),
                        "success": has_success and has_result,  # 둘 다 있어야 성공
                        "analysis_result": analysis_data,                # ✅ 전체 데이터 저장
                        "raw_data": analysis_data
                    }

                    # 성공한 분석의 경우 요약 정보 추출  
                    if result["success"] and "result" in analysis_data:
                        # 블로그용인지 일반용인지에 따라 다른 요약 함수 사용
                        if for_blog:
                            result["summary"] = self._extract_blog_summary(doc.get("task_name"), analysis_data.get("result", {}))
                        else:
                            result["summary"] = self._extract_summary(doc.get("task_name"), analysis_data.get("result", {}))
                    else:
                        # 실패한 분석의 경우 실패 정보 추출
                        result["failure_info"] = self._extract_failure_info(analysis_data)

                    results.append(result)
                    
                except Exception as e:
                    logger.error(f"분석 결과 파싱 오류: {e}")
                    continue
            
            return self.sort_by_latest_first(results)
            
        except Exception as e:
            logger.error(f"AI 분석 결과 조회 오류: {e}")
            return []
    
    def _extract_summary(self, task_name: str, analysis_result: Dict) -> Dict:
        """분석 결과에서 요약 정보 추출"""
        summary = {
            "confidence": analysis_result.get("confidence", 0),
            "key_points": [],
            "recommendation": "분석 불가"
        }
        
        try:
            if task_name == "ai_sentiment_analysis":
                summary.update({
                    "confidence": analysis_result.get("confidence", 0),
                    "sentiment_score": analysis_result.get("market_sentiment_score", 50),
                    "sentiment_state": analysis_result.get("sentiment_state", "중립"),
                    "recommendation": analysis_result.get("investment_recommendation", "중립적 접근")
                })
                
            elif task_name == "ai_technical_analysis":
                summary.update({
                    "confidence": analysis_result.get("confidence", 0),
                    "signal": analysis_result.get("overall_signal", "Hold"),
                    "trend": analysis_result.get("trend_analysis", {}).get("trend_direction", "중립"),
                    "momentum": analysis_result.get("momentum_analysis", {}).get("momentum_direction", "중립"),
                    "recommendation": f"{analysis_result.get('overall_signal', 'Hold')} - {analysis_result.get('trend_analysis', {}).get('trend_direction', '중립')} 추세"
                })
                
            elif task_name == "ai_macro_analysis":
                summary.update({
                    "confidence": analysis_result.get("confidence", 0),
                    "macro_score": analysis_result.get("macro_environment_score", 50),
                    "investment_environment": analysis_result.get("investment_environment", "중립"),
                    "recommendation": analysis_result.get("btc_recommendation", "신중한 접근")
                })
                
            elif task_name == "ai_onchain_analysis":
                summary.update({
                    "confidence": analysis_result.get("confidence", 0),
                    "health_score": analysis_result.get("onchain_health_score", 50),
                    "signal": analysis_result.get("investment_signal", "Hold"),
                    "network_security": analysis_result.get("network_security_analysis", "정상"),
                    "recommendation": analysis_result.get("investment_signal", "중립적")
                })
                
            elif task_name == "ai_institutional_analysis":
                summary.update({
                    "confidence": analysis_result.get("confidence", 0),
                    "flow_score": analysis_result.get("institutional_flow_score", 50),
                    "signal": analysis_result.get("investment_signal", "Hold"),
                    "flow_direction": "분산" if "Sell" in analysis_result.get("investment_signal", "") else "중립",
                    "recommendation": analysis_result.get("investment_signal", "관망")
                })
                
            elif task_name == "final_decision":
                def safe_slice(text, length=100):
                    if text and isinstance(text, str):
                        return text[:length] + "..." if len(text) > length else text
                    return "분석 중"
                summary.update({
                    "confidence": analysis_result.get("decision_confidence", 0),
                    "decision": analysis_result.get("final_decision", "Hold"),
                    "action": analysis_result.get("recommended_action", {}).get("action_type", "Hold"),
                    "recommendation": safe_slice(analysis_result.get("decision_reasoning")),
                    "needs_human_review": analysis_result.get("needs_human_review", False),
                    "human_review_reason": safe_slice(analysis_result.get("human_review_reason"))
                })
            
            # 공통 키 포인트 추출
            if "analysis_summary" in analysis_result:
                summary["key_points"] = [analysis_result["analysis_summary"][:200] + "..."]
                
        except Exception as e:
            logger.error(f"요약 정보 추출 오류: {e}")
        
        return summary
    
    def _extract_blog_summary(self, task_name: str, analysis_result: Dict) -> Dict:
        """블로그용 분석 결과 요약 정보 추출 (길이 제한 없음)"""
        summary = {
            "confidence": analysis_result.get("confidence", 0),
            "key_points": [],
            "recommendation": "분석 불가"
        }
        
        try:
            if task_name == "ai_sentiment_analysis":
                summary.update({
                    "confidence": analysis_result.get("confidence", 0),
                    "sentiment_score": analysis_result.get("market_sentiment_score", 50),
                    "sentiment_state": analysis_result.get("sentiment_state", "중립"),
                    "recommendation": analysis_result.get("investment_recommendation", "중립적 접근")
                })
                
            elif task_name == "ai_technical_analysis":
                summary.update({
                    "confidence": analysis_result.get("confidence", 0),
                    "signal": analysis_result.get("overall_signal", "Hold"),
                    "trend": analysis_result.get("trend_analysis", {}).get("trend_direction", "중립"),
                    "momentum": analysis_result.get("momentum_analysis", {}).get("momentum_direction", "중립"),
                    "recommendation": f"{analysis_result.get('overall_signal', 'Hold')} - {analysis_result.get('trend_analysis', {}).get('trend_direction', '중립')} 추세"
                })
                
            elif task_name == "ai_macro_analysis":
                summary.update({
                    "confidence": analysis_result.get("confidence", 0),
                    "macro_score": analysis_result.get("macro_environment_score", 50),
                    "investment_environment": analysis_result.get("investment_environment", "중립"),
                    "recommendation": analysis_result.get("btc_recommendation", "신중한 접근")
                })
                
            elif task_name == "ai_onchain_analysis":
                summary.update({
                    "confidence": analysis_result.get("confidence", 0),
                    "health_score": analysis_result.get("onchain_health_score", 50),
                    "signal": analysis_result.get("investment_signal", "Hold"),
                    "network_security": analysis_result.get("network_security_analysis", "정상"),
                    "recommendation": analysis_result.get("investment_signal", "중립적")
                })
                
            elif task_name == "ai_institutional_analysis":
                summary.update({
                    "confidence": analysis_result.get("confidence", 0),
                    "flow_score": analysis_result.get("institutional_flow_score", 50),
                    "signal": analysis_result.get("investment_signal", "Hold"),
                    "flow_direction": "분산" if "Sell" in analysis_result.get("investment_signal", "") else "중립",
                    "recommendation": analysis_result.get("investment_signal", "관망")
                })
                
            elif task_name == "final_decision":
                summary.update({
                    "confidence": analysis_result.get("decision_confidence", 0),
                    "decision": analysis_result.get("final_decision", "Hold"),
                    "action": analysis_result.get("recommended_action", {}).get("action_type", "Hold"),
                    "recommendation": analysis_result.get("decision_reasoning", "분석 중"),  # 길이 제한 제거
                    "needs_human_review": analysis_result.get("needs_human_review", False),
                    "human_review_reason": analysis_result.get("human_review_reason", "")  # 길이 제한 제거
                })
            
            # 공통 키 포인트 추출 (길이 제한 없음)
            if "analysis_summary" in analysis_result:
                summary["key_points"] = [analysis_result["analysis_summary"]]  # 전체 내용 사용
                
        except Exception as e:
            logger.error(f"블로그용 요약 정보 추출 오류: {e}")
        
        return summary


    def _extract_failure_info(self, analysis_result: Dict) -> Dict:
        """실패한 분석 결과에서 실패 정보 추출"""
        failure_info = {
            "error_type": "unknown",
            "error_message": "분석 실패",
            "skip_reason": None,
            "error_count": 0,
            "max_errors": 3,
            "retry_available": True
        }
        
        try:
            if isinstance(analysis_result, dict):
                failure_info.update({
                    "error_type": analysis_result.get("skip_reason", "unknown"),
                    "error_message": analysis_result.get("error", "분석 실패"),
                    "skip_reason": analysis_result.get("skip_reason"),
                    "error_count": analysis_result.get("error_count", 0),
                    "max_errors": analysis_result.get("max_errors", 3),
                    "retry_available": analysis_result.get("error_count", 0) < analysis_result.get("max_errors", 3)
                })
                
                # 실패 유형별 사용자 친화적 메시지
                skip_reason = analysis_result.get("skip_reason", "")
                if skip_reason == "insufficient_raw_data":
                    failure_info["user_message"] = "원시 데이터 부족으로 분석 불가"
                elif skip_reason == "ai_analysis_failed":
                    failure_info["user_message"] = "AI 모델 호출 실패"
                elif skip_reason == "exception":
                    failure_info["user_message"] = "분석 중 예외 발생"
                elif skip_reason == "execution_failed":
                    failure_info["user_message"] = "분석 실행 실패"
                elif skip_reason == "analyzer_disabled":
                    failure_info["user_message"] = "분석기 비활성화 (연속 실패)"
                else:
                    failure_info["user_message"] = failure_info["error_message"]
                    
        except Exception as e:
            logger.error(f"실패 정보 추출 오류: {e}")
        
        return failure_info
    
    def get_analysis_detail(self, task_name: str, created_at: datetime) -> Optional[Dict]:
        """특정 분석 결과의 상세 정보 조회"""
        try:
            # 정확한 시간 매칭을 위해 범위 검색
            time_range = timedelta(seconds=30)
            start_time = created_at - time_range
            end_time = created_at + time_range
            
            doc = self.cache_collection.find_one({
                "task_name": task_name,
                "created_at": {
                    "$gte": start_time,
                    "$lte": end_time
                }
            })
            
            if not doc:
                return None
            
            return {
                "task_name": task_name,
                "display_name": self.get_task_display_name(task_name),
                "created_at": doc.get("created_at"),
                "data": doc.get("data", {}),
                "formatted_data": json.dumps(doc.get("data", {}), indent=2, ensure_ascii=False, default=str)
            }
            
        except Exception as e:
            logger.error(f"분석 상세 정보 조회 오류: {e}")
            return None
    
    def get_analysis_statistics(self, hours: int = 24) -> Dict:
        """AI 분석 통계 정보"""
        try:
            since_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            stats = {
                "total_analyses": 0,
                "success_count": 0,
                "failure_count": 0,
                "by_analyzer": {},
                "success_rate": 0
            }
            
            # 각 분석기별 통계
            for task_name in self.get_analysis_tasks():
                cursor = self.cache_collection.find({
                    "task_name": task_name,
                    "created_at": {"$gte": since_time}
                })
                
                task_total = 0
                task_success = 0
                
                for doc in cursor:
                    task_total += 1
                    analysis_data = doc.get("data", {})
                    
                    # 🔧 수정: 올바른 success 체크
                    if analysis_data.get("success", False):  # analysis_result 제거!
                        task_success += 1
                
                stats["by_analyzer"][task_name] = {
                    "display_name": self.get_task_display_name(task_name),
                    "total": task_total,
                    "success": task_success,
                    "failure": task_total - task_success,
                    "success_rate": (task_success / task_total * 100) if task_total > 0 else 0
                }
                
                stats["total_analyses"] += task_total
                stats["success_count"] += task_success
            
            stats["failure_count"] = stats["total_analyses"] - stats["success_count"]
            stats["success_rate"] = (stats["success_count"] / stats["total_analyses"] * 100) if stats["total_analyses"] > 0 else 0
            
            return stats
            
        except Exception as e:
            logger.error(f"분석 통계 조회 오류: {e}")
            return {"total_analyses": 0, "success_count": 0, "failure_count": 0, "by_analyzer": {}, "success_rate": 0}

    # 외부 전송용 차트 데이터 (72시간봉)
    def get_chart_data(self, hours: int = 300) -> List[Dict]:
        """시계열 차트 데이터 조회 (1시간봉 기준, 불완전한 마지막 데이터 제외)"""
        try:
            # 시간 범위 설정 (73시간 가져와서 마지막 1개 제외)
            since_time = datetime.now(timezone.utc) - timedelta(hours=hours + 1)
            
            # chart_60m 컬렉션에서 데이터 조회
            chart_collection = self.database["chart_60m"]
            
            cursor = chart_collection.find({
                "timestamp": {"$gte": since_time}
            }).sort("timestamp", 1).limit(hours + 1)  # 73개 가져오기
            
            chart_data = []
            for doc in cursor:
                chart_data.append({
                    "timestamp": doc.get("timestamp"),
                    "open": float(doc.get("open", 0)),
                    "high": float(doc.get("high", 0)), 
                    "low": float(doc.get("low", 0)),
                    "close": float(doc.get("close", 0)),
                    "volume": float(doc.get("volume", 0))
                })
            
            # 마지막 불완전한 데이터 제거
            if len(chart_data) > hours:
                chart_data = chart_data[:-1]  # 마지막 1개 제거
            
            return chart_data
            
        except Exception as e:
            logger.error(f"차트 데이터 조회 오류: {e}")
            return []


    def _filter_analysis_for_blog(self, analysis_data):
        """블로그용으로 분석 데이터를 필터링하는 함수"""
        filtered_data = {}
        
        # 기본 정보 유지
        basic_fields = ['task_name', 'display_name', 'created_at', 'success']
        for field in basic_fields:
            if field in analysis_data:
                filtered_data[field] = analysis_data[field]
        
        # analysis_result가 있는 경우에만 처리
        if 'analysis_result' in analysis_data and analysis_data['analysis_result'].get('success'):
            result = analysis_data['analysis_result']['result']
            filtered_result = {}
            
            # 분석 타입별로 필터링
            task_name = analysis_data.get('task_name', '')
            
            if task_name == 'final_decision':
                # 최종 결정 - 핵심 정보만
                filtered_result = {
                    'final_decision': result.get('final_decision'),
                    'decision_confidence': result.get('decision_confidence'),
                    'market_outlook': result.get('market_outlook', {}),
                    'decision_reasoning': result.get('decision_reasoning'),
                    'signal_consensus': {
                        'consensus_level': result.get('signal_consensus', {}).get('consensus_level'),
                        'conflicting_signals': result.get('signal_consensus', {}).get('conflicting_signals', []),
                        'dominant_signal_source': result.get('signal_consensus', {}).get('dominant_signal_source')
                    },
                    'confidence_factors': {
                        'supporting_factors': result.get('confidence_factors', {}).get('supporting_factors', []),
                        'risk_factors': result.get('confidence_factors', {}).get('risk_factors', [])
                    }
                }
                
            elif task_name == 'ai_technical_analysis':
                # 기술적 분석 - 상세 수치 제외
                filtered_result = {
                    'overall_signal': result.get('overall_signal'),
                    'confidence': result.get('confidence'),
                    'trend_analysis': result.get('trend_analysis', {}),
                    'momentum_analysis': result.get('momentum_analysis', {}),
                    'timeframe_analysis': result.get('timeframe_analysis', {}),
                    'analysis_summary': result.get('analysis_summary')
                }
                
            elif task_name == 'ai_sentiment_analysis':
                # 시장 감정 분석
                filtered_result = {
                    'market_sentiment_score': result.get('market_sentiment_score'),
                    'sentiment_state': result.get('sentiment_state'),
                    'confidence': result.get('confidence'),
                    'investment_recommendation': result.get('investment_recommendation'),
                    'market_impact': result.get('market_impact'),
                    'analysis_summary': result.get('analysis_summary')
                }
                
            elif task_name == 'ai_macro_analysis':
                # 거시경제 분석
                filtered_result = {
                    'macro_environment_score': result.get('macro_environment_score'),
                    'investment_environment': result.get('investment_environment'),
                    'confidence': result.get('confidence'),
                    'btc_recommendation': result.get('btc_recommendation'),
                    'analysis_summary': result.get('analysis_summary'),
                    'key_insights': result.get('key_insights', [])
                }
                
            elif task_name == 'ai_onchain_analysis':
                # 온체인 분석
                filtered_result = {
                    'onchain_health_score': result.get('onchain_health_score'),
                    'investment_signal': result.get('investment_signal'),
                    'confidence': result.get('confidence'),
                    'network_security_analysis': result.get('network_security_analysis'),
                    'holder_sentiment': result.get('holder_sentiment'),
                    'mining_outlook': result.get('mining_outlook'),
                    'analysis_summary': result.get('analysis_summary'),
                    'key_insights': result.get('key_insights', [])
                }
                
            elif task_name == 'ai_institutional_analysis':
                # 기관투자 분석
                filtered_result = {
                    'institutional_flow_score': result.get('institutional_flow_score'),
                    'investment_signal': result.get('investment_signal'),
                    'confidence': result.get('confidence'),
                    'analysis_summary': result.get('analysis_summary'),
                    'key_insights': result.get('key_insights', [])
                }
            
            # 필터링된 결과 저장
            filtered_data['analysis_result'] = {
                'success': True,
                'result': filtered_result
            }
        
        return filtered_data

    def _filter_blog_analysis_data(self, latest_detailed, historical_summaries):
        """블로그 분석 데이터 전체를 필터링하는 함수"""
        
        # 최신 상세 데이터 필터링
        filtered_latest = []
        for analysis in latest_detailed:
            filtered_analysis = self._filter_analysis_for_blog(analysis)
            filtered_latest.append(filtered_analysis)
        
        # 과거 요약 데이터는 이미 요약된 형태이므로 그대로 유지
        # 단, 너무 긴 summary 내용이 있다면 일부 제한
        filtered_historical = []
        for summary in historical_summaries:
            filtered_summary = summary.copy()
            
            # summary 내 key_points가 너무 길면 첫 번째만 유지
            if 'summary' in filtered_summary and 'key_points' in filtered_summary['summary']:
                key_points = filtered_summary['summary']['key_points']
                if isinstance(key_points, list) and len(key_points) > 0:
                    # 첫 번째 key_point가 너무 길면 1000자로 제한
                    first_point = key_points[0]
                    if len(first_point) > 1000:
                        filtered_summary['summary']['key_points'] = [first_point[:1000] + "..."]
                    else:
                        filtered_summary['summary']['key_points'] = [first_point]
            
            filtered_historical.append(filtered_summary)
        
        return filtered_latest, filtered_historical



# 전역 뷰어 인스턴스
ai_viewer = AIAnalysisViewer()

@router.get("/ai-analysis", response_class=HTMLResponse)
async def ai_analysis_page(
    request: Request,
    analyzer: Optional[str] = Query(None, description="분석기 필터"),
    hours: int = Query(24, description="조회 시간 범위 (시간)"),
    limit: int = Query(50, description="최대 결과 수")
):
    """AI 분석 결과 페이지"""
    try:
        # 분석 결과 조회
        analyses = ai_viewer.get_recent_analyses(task_name=analyzer, hours=hours, limit=limit)
        
        # 통계 정보 조회
        statistics = ai_viewer.get_analysis_statistics(hours=hours)
        
        # 사용 가능한 분석기 목록
        analyzers = [
            {"value": task, "name": ai_viewer.get_task_display_name(task)}
            for task in ai_viewer.get_analysis_tasks()
        ]
        
        return templates.TemplateResponse(
            "ai_analysis.html",
            {
                "request": request,
                "analyses": analyses,
                "statistics": statistics,
                "analyzers": analyzers,
                "current_analyzer": analyzer,
                "hours": hours,
                "limit": limit,
                "total_results": len(analyses)
            }
        )
        
    except Exception as e:
        logger.error(f"AI 분석 페이지 오류: {e}")
        raise HTTPException(status_code=500, detail=f"페이지 로드 오류: {str(e)}")

@router.get("/api/ai-analysis")
async def get_ai_analysis_api(
    analyzer: Optional[str] = Query(None),
    hours: int = Query(24),
    limit: int = Query(50)
):
    """AI 분석 결과 API"""
    try:
        analyses = ai_viewer.get_recent_analyses(task_name=analyzer, hours=hours, limit=limit)
        statistics = ai_viewer.get_analysis_statistics(hours=hours)
        
        return {
            "success": True,
            "data": {
                "analyses": analyses,
                "statistics": statistics,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"AI 분석 API 오류: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

@router.get("/api/ai-status-quick")
async def get_ai_status_quick():
    """AI 시스템 상태를 빠르게 확인하는 API (AI API 테스트 제외)"""
    try:
        # AI API 테스트 없이 기본 상태만 조회
        ai_data_status = get_data_status()
        ai_recovery_status = get_recovery_status()
        ai_api_status = get_ai_api_status_summary()
        
        return {
            "success": True,
            "api_test_result": None,  # 빠른 조회에서는 테스트 안함
            "ai_data_status": ai_data_status,
            "ai_recovery_status": ai_recovery_status,
            "ai_api_status": ai_api_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "빠른 조회 모드 - AI API 테스트 제외"
        }
        
    except Exception as e:
        logger.error(f"AI 상태 빠른 조회 오류: {e}")
        return {
            "success": False,
            "error": str(e),
            "ai_api_status": {"is_working": False, "status_text": f"상태 확인 실패: {str(e)}"},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

@router.get("/ai-analysis/detail", response_class=HTMLResponse)
async def ai_analysis_detail(
    request: Request,
    task_name: str = Query(..., description="분석 작업명"),
    timestamp: str = Query(..., description="분석 시각 (ISO 형식)")
):
    """AI 분석 상세 결과 페이지"""
    try:
        # 타임스탬프 파싱
        created_at = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        
        # 상세 정보 조회
        detail = ai_viewer.get_analysis_detail(task_name, created_at)
        
        if not detail:
            raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다.")
        
        return templates.TemplateResponse(
            "ai_analysis_detail.html",
            {
                "request": request,
                "detail": detail
            }
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"잘못된 타임스탬프 형식: {str(e)}")
    except Exception as e:
        logger.error(f"AI 분석 상세 페이지 오류: {e}")
        raise HTTPException(status_code=500, detail=f"페이지 로드 오류: {str(e)}")


@router.get("/api/chart-data")
async def get_chart_data_api(
    hours: int = Query(300, description="조회할 시간 범위 (시간)", ge=1, le=720)
):
    """차트 데이터 조회 API (1시간봉 기준)"""
    try:
        chart_data = ai_viewer.get_chart_data(hours=hours)
        
        if not chart_data:
            return {
                "success": False,
                "error": "차트 데이터를 찾을 수 없습니다.",
                "data": [],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        return {
            "success": True,
            "data": {
                "chart_data": chart_data,
                "data_count": len(chart_data),
                "hours_requested": hours,
                "first_timestamp": chart_data[0]["timestamp"].isoformat() if chart_data else None,
                "last_timestamp": chart_data[-1]["timestamp"].isoformat() if chart_data else None
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"차트 데이터 API 오류: {e}")
        return {
            "success": False,
            "error": str(e),
            "data": [],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

@router.get("/api/blog-analysis")
async def get_blog_analysis_api(
    analysis_hours: int = Query(6, description="AI 분석 데이터 시간 범위", ge=1, le=168)
):
    """블로그 생성용 AI 분석 데이터 API (필터링 적용)"""
    try:
        # AI 분석 데이터 조회 - 최신 상세 데이터 (각 분석기별 최신 1개씩)
        latest_detailed = ai_viewer.get_recent_analyses(hours=analysis_hours, for_blog=True, limit=6)
        
        # AI 분석 데이터 조회 - 과거 요약 데이터 (6시간 전체)
        all_analyses = ai_viewer.get_recent_analyses(hours=analysis_hours, for_blog=True, limit=50)
        historical_summaries = []
        
        for analysis in all_analyses:
            if 'summary' in analysis:
                historical_summaries.append({
                    "task_name": analysis["task_name"],
                    "display_name": analysis["display_name"],
                    "created_at": analysis["created_at"].isoformat(),  # UTC ISO 형태
                    "summary": analysis["summary"],
                    "success": analysis.get("success", False)
                })
        
        # 블로그용 데이터 필터링 적용
        filtered_latest, filtered_historical = ai_viewer._filter_blog_analysis_data(latest_detailed, historical_summaries)
        
        return {
            "success": True,
            "data": {
                "latest_detailed_analyses": filtered_latest,
                "historical_summaries": filtered_historical,
                "metadata": {
                    "latest_detailed_count": len(filtered_latest),
                    "historical_summaries_count": len(filtered_historical),
                    "analysis_hours": analysis_hours,
                    "latest_analysis_timestamp": filtered_latest[0]["created_at"].isoformat() if filtered_latest else None,
                    "filtered": True  # 필터링 적용됨을 표시
                }
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"블로그 분석 데이터 API 오류: {e}")
        return {
            "success": False,
            "error": str(e),
            "data": {
                "latest_detailed_analyses": [],
                "historical_summaries": [],
                "metadata": {}
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
