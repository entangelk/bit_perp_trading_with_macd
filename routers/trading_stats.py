from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os
from datetime import datetime, timedelta
import sys
from pathlib import Path
import shutil

# get_disk_usage 함수를 직접 구현
def get_disk_usage(path="/"):
    """지정된 경로의 디스크 사용량 정보를 반환합니다."""
    total, used, free = shutil.disk_usage(path)
    return {
        "total": f"{total / (1024**3):.2f} GB",
        "used": f"{used / (1024**3):.2f} GB",
        "free": f"{free / (1024**3):.2f} GB",
        "percent_used": f"{(used / total) * 100:.1f}%",
        "percent_free": f"{(free / total) * 100:.1f}%"
    }

# 공통 유틸리티 모듈 경로 추가
sys.path.append(str(Path(__file__).parent.parent))
from docs.utility.check_pnl import get_win_rate

# 라우터 및 템플릿 설정
router = APIRouter()
templates = Jinja2Templates(directory="/app/trading_bot/templates")

@router.get("/trading-stats", response_class=HTMLResponse)
async def view_trading_stats(request: Request, days: int = 7):
    """바이비트 거래 승률 통계를 보여주는 페이지"""
    try:
        # 디스크 용량 정보 가져오기
        disk_info = get_disk_usage()
        
        # 시작일과 종료일 계산
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
        
        try:
            # 환경 변수에서 API 키 가져오기
            BYBIT_ACCESS_KEY = os.getenv("BYBIT_ACCESS_KEY")
            BYBIT_SECRET_KEY = os.getenv("BYBIT_SECRET_KEY")
            
            if not BYBIT_ACCESS_KEY or not BYBIT_SECRET_KEY:
                return templates.TemplateResponse(
                    "trading_stats.html", 
                    {
                        "request": request,
                        "disk_info": disk_info,
                        "error_message": "API 키가 설정되지 않았습니다. 환경 변수를 확인하세요.",
                        "daily_stats": [],
                        "overall_stats": {},
                        "days": days
                    }
                )
            
            # 바이비트 API 호출
            result = get_win_rate(BYBIT_ACCESS_KEY, BYBIT_SECRET_KEY, 
                                 start_time=start_time, end_time=end_time, limit=100)
            
            # 일별 통계 계산
            daily_stats = calculate_daily_stats(result['trades'])
            
            # 전체 PnL 합계 계산
            total_pnl = sum(stat['pnl'] for stat in daily_stats)
            
            return templates.TemplateResponse(
                "trading_stats.html", 
                {
                    "request": request,
                    "disk_info": disk_info,
                    "daily_stats": daily_stats,
                    "overall_stats": {
                        "win_rate": result['win_rate'],
                        "win_trades": result['win_trades'],
                        "total_trades": result['total_trades'],
                        "total_pnl": total_pnl  # 전체 PnL 추가
                    },
                    "days": days
                }
            )
            
        except Exception as e:
            return templates.TemplateResponse(
                "trading_stats.html", 
                {
                    "request": request,
                    "disk_info": disk_info,
                    "error_message": f"API 호출 오류: {str(e)}",
                    "daily_stats": [],
                    "overall_stats": {},
                    "days": days
                }
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"거래 통계 페이지 오류: {str(e)}")

def calculate_daily_stats(trades):
    """거래 내역을 일별로 분석하여 승률 계산"""
    daily_stats = {}
    
    for trade in trades:
        # 거래 시간을 날짜로 변환
        trade_time = int(trade['createdTime']) / 1000  # 밀리초를 초 단위로 변환
        date = datetime.fromtimestamp(trade_time).strftime('%Y-%m-%d')
        
        # 해당 날짜의 통계 초기화
        if date not in daily_stats:
            daily_stats[date] = {
                'win': 0,
                'loss': 0,
                'pnl': 0.0
            }
        
        # 승패 기록
        pnl = float(trade['closedPnl'])
        if pnl > 0:
            daily_stats[date]['win'] += 1
        else:
            daily_stats[date]['loss'] += 1
            
        # PnL 누적
        daily_stats[date]['pnl'] += pnl
    
    # 일별 승률 계산 및 리스트로 변환
    result = []
    for date, stats in sorted(daily_stats.items()):
        total = stats['win'] + stats['loss']
        win_rate = (stats['win'] / total * 100) if total > 0 else 0
        
        result.append({
            'date': date,
            'win': stats['win'],
            'loss': stats['loss'],
            'total': total,
            'win_rate': win_rate,
            'pnl': stats['pnl']
        })
    
    return result