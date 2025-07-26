from fastapi import FastAPI, Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os
import re
import shutil
import psutil
from datetime import datetime
import uvicorn
from pathlib import Path
from docs.utility.logger.access_logger import SecurityLoggingMiddleware
from routers.trading_stats import router as trading_stats_router
from routers.ai_analysis import router as ai_analysis_router
import time
import json
import logging

class HostValidationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_hosts):
        super().__init__(app)
        self.allowed_hosts = allowed_hosts
    
    async def dispatch(self, request: Request, call_next):
        # Host 헤더 가져오기
        host = request.headers.get("host", "")
        
        # 허용된 호스트인지 확인
        if host not in self.allowed_hosts:
            return JSONResponse(
                status_code=403,
                content={"detail": "Access denied"}
            )
        
        # 허용된 호스트면 정상 처리
        response = await call_next(request)
        return response


app = FastAPI(title="트레이딩 봇 로그 뷰어")


# 허용할 도메인 리스트
ALLOWED_HOSTS = [
    "entangelk.o-r.kr",
    "www.entangelk.o-r.kr"  # www 버전도 허용하고 싶다면
]

# 기존 FastAPI 앱에 미들웨어 추가
app.add_middleware(HostValidationMiddleware, allowed_hosts=ALLOWED_HOSTS)

# 보안 로깅 미들웨어 추가
app.add_middleware(SecurityLoggingMiddleware)

app.include_router(trading_stats_router)
app.include_router(ai_analysis_router)

# 템플릿 디렉토리 설정
templates = Jinja2Templates(directory="/app/trading_bot/templates")

# 로그 파일 경로 설정
LOG_DIR = "/app/trading_bot"  # 올바른 경로
LOG_FILES = {
    "trading": "trading_bot.log"
}

# 모니터링할 파일 설정
MONITOR_FILES = {
    "main": "main_ai_new.py",    # AI 트레이딩 봇
    "backtest": "back_test.py"  # 백테스트 
}

# 로그 레벨에 따른 색상 정의
LOG_LEVELS = {
    "DEBUG": "text-gray-600",
    "INFO": "text-blue-600",
    "WARNING": "text-yellow-600",
    "ERROR": "text-red-600",
    "CRITICAL": "text-red-700 font-bold"
}

# 디스크 용량 정보를 가져오는 함수
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

# 프로세스 실행 상태 확인 함수 추가
def check_process_status(script_name):
    """주어진 스크립트 이름이 실행 중인지 확인합니다."""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        try:
            # python 프로세스를 찾고 커맨드라인에 스크립트 이름이 있는지 확인
            if 'python' in proc.info['name'].lower() and any(script_name in cmd for cmd in proc.info['cmdline'] if cmd):
                return {
                    'running': True,
                    'pid': proc.info['pid'],
                    'start_time': time.strftime('%Y-%m-%d %H:%M:%S', 
                                              time.localtime(proc.info['create_time'])),
                    'memory_usage': f"{proc.memory_info().rss / (1024 * 1024):.2f} MB",
                    'cpu_percent': f"{proc.cpu_percent(interval=0.1):.1f}%"
                }
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return {'running': False}

from docs.utility.trade_analyzer import TradeAnalyzer
from docs.investment_ai.data_scheduler import get_data_status, get_recovery_status, get_ai_api_status_summary, test_ai_api_connection

# 차트 아날라이저 초기화
analyzer = TradeAnalyzer()


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """메인 페이지"""
    # 디스크 용량 정보 가져오기
    disk_info = get_disk_usage()
    # EC2 인스턴스의 경우 루트 파일 시스템과 로그 디렉토리 파일 시스템이 다를 수 있음
    log_disk_info = get_disk_usage(LOG_DIR)
    
    # 프로세스 상태 확인
    main_status = check_process_status(MONITOR_FILES["main"])
    
    # AI 시스템 상태 확인
    try:
        ai_data_status = get_data_status()
        ai_recovery_status = get_recovery_status()
        
        # AI API 상태 실시간 테스트 (웹 페이지 로드 시 실제 테스트)
        print("[DEBUG] AI API 실시간 테스트 시작...")
        try:
            # FastAPI는 이미 async 환경이므로 직접 await 사용 불가
            # 대신 기본 상태만 조회하고 실제 테스트는 API 엔드포인트에서 수행
            api_test_result = None  # 메인 페이지에서는 테스트 생략
            print(f"[DEBUG] AI API 테스트 건너뜀 (비동기 환경 충돌 방지)")
        except Exception as test_error:
            print(f"[ERROR] AI API 테스트 중 오류: {test_error}")
            api_test_result = False
        
        ai_api_status = get_ai_api_status_summary()
        print(f"[DEBUG] AI API 상태 확인: {ai_api_status}")
        
    except Exception as e:
        print(f"[ERROR] AI 상태 확인 중 오류: {e}")
        ai_data_status = {}
        ai_recovery_status = {'disabled_tasks': [], 'recovery_timestamps': {}}
        ai_api_status = {'is_working': False, 'status_text': f'AI API 상태 확인 오류: {str(e)}'}
    
    # 트레이딩 분석 데이터 가져오기
    trade_analysis = analyzer.get_visualization_data(hours=24)

    # 승률 리버싱 json 데이터 가져오기
    try:
        with open('win_rate.json', 'r') as f:
            win_rate_data = json.load(f)
    except FileNotFoundError:
        win_rate_data = {"win_rate": True}  # 기본값 설정

    # 승률 리버싱 데이터
    win_rate = win_rate_data.get("win_rate", True)
    
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request, 
            "log_files": LOG_FILES,
            "disk_info": disk_info,
            "log_disk_info": log_disk_info,
            "main_status": main_status,
            "ai_data_status": ai_data_status,
            "ai_recovery_status": ai_recovery_status,
            "ai_api_status": ai_api_status,
            "now": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "trade_analysis_json": json.dumps(trade_analysis),
            "win_rate": win_rate
        }
    )

@app.get("/api/trade_analysis")
async def get_trade_analysis():
    data = analyzer.get_visualization_data(hours=24)
    return data

@app.get("/api/ai_status")
async def get_ai_status():
    """AI 시스템 상태를 실시간으로 확인하는 API (타임아웃 포함)"""
    try:
        # AI API 실시간 테스트 (타임아웃 설정)
        import asyncio
        try:
            api_test_result = await asyncio.wait_for(test_ai_api_connection(), timeout=10.0)
        except asyncio.TimeoutError:
            print("[WARNING] AI API 테스트 타임아웃 (10초)")
            api_test_result = False
        except Exception as test_error:
            print(f"[ERROR] AI API 테스트 중 오류: {test_error}")
            api_test_result = False
        
        # 상태 정보 수집
        ai_data_status = get_data_status()
        ai_recovery_status = get_recovery_status()
        ai_api_status = get_ai_api_status_summary()
        
        return {
            "success": True,
            "api_test_result": api_test_result,
            "ai_data_status": ai_data_status,
            "ai_recovery_status": ai_recovery_status,
            "ai_api_status": ai_api_status,
            "timestamp": datetime.now().isoformat(),
            "test_timeout": api_test_result is False
        }
    except Exception as e:
        print(f"[ERROR] AI 상태 확인 전체 오류: {e}")
        return {
            "success": False,
            "error": str(e),
            "ai_api_status": {"is_working": False, "status_text": f"API 상태 확인 실패: {str(e)}"},
            "timestamp": datetime.now().isoformat()
        }

@app.get("/api/ai_status_quick")
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
            "timestamp": datetime.now().isoformat(),
            "note": "빠른 조회 모드 - AI API 테스트 제외"
        }
        
    except Exception as e:
        print(f"[ERROR] AI 상태 빠른 조회 오류: {e}")
        return {
            "success": False,
            "error": str(e),
            "ai_api_status": {"is_working": False, "status_text": f"상태 확인 실패: {str(e)}"},
            "timestamp": datetime.now().isoformat()
        }

@app.get("/log/{log_type}", response_class=HTMLResponse)
async def view_log(request: Request, log_type: str, lines: int = 100, error_only: bool = False):
    """특정 로그 파일을 표시합니다."""
    if log_type not in LOG_FILES:
        raise HTTPException(status_code=404, detail="존재하지 않는 로그 타입입니다")
    
    log_file = os.path.join(LOG_DIR, LOG_FILES[log_type])
    
    if not os.path.exists(log_file):
        raise HTTPException(status_code=404, detail="로그 파일을 찾을 수 없습니다")
    
    # 디스크 용량 정보 가져오기
    disk_info = get_disk_usage()
    log_disk_info = get_disk_usage(LOG_DIR)
    
    # 정규식 패턴 (로그 형식에 맞게 설정)
    # 정규식 패턴을 로그 타입별로 설정
    patterns = {
        "trading": r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (\w+) - (\w+) - (.+)',
        "backtest": r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (.+)'
    }
    
    try:
        log_entries = []
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            content = f.readlines()

        # 로그 파싱
        current_entry = None
        pattern = patterns.get(log_type)

        for line in content:
            if log_type == "trading":
                match = re.match(pattern, line)
                if match:
                    if current_entry:
                        log_entries.append(current_entry)
                    
                    timestamp, module, level, message = match.groups()
                    
                    # error_only 옵션이 활성화된 경우 ERROR/CRITICAL 레벨만 저장
                    if error_only and level not in ["ERROR", "CRITICAL"]:
                        current_entry = None
                        continue
                    
                    current_entry = {
                        "timestamp": timestamp,
                        "module": module,
                        "level": level,
                        "message": message,
                        "class": LOG_LEVELS.get(level, "")
                    }
                elif current_entry:
                    # 멀티라인 메시지 처리
                    current_entry["message"] += "\n" + line
            
            elif log_type == "backtest":
                match = re.match(pattern, line)
                if match:
                    if current_entry:
                        log_entries.append(current_entry)
                    
                    timestamp, message = match.groups()
                    
                    # backtest 로그에는 레벨 정보가 없으므로 INFO로 간주
                    level = "INFO"
                    
                    # error_only 옵션을 위한 예외 처리
                    if error_only:
                        # 메시지에 "error", "exception" 등이 포함된 경우에만 표시
                        if not re.search(r'error|exception|fail', message.lower()):
                            current_entry = None
                            continue
                        level = "ERROR"  # 오류 메시지로 간주
                    
                    current_entry = {
                        "timestamp": timestamp,
                        "module": "Backtest",
                        "level": level,
                        "message": message,
                        "class": LOG_LEVELS.get(level, "")
                    }
                elif current_entry:
                    # 멀티라인 메시지 처리
                    current_entry["message"] += "\n" + line
        
        # 마지막 로그 항목 추가
        if current_entry:
            log_entries.append(current_entry)
        
        # 최신 로그를 먼저 보여주기 위해 역순 정렬
        log_entries.reverse()
        
        # 요청한 라인 수만큼 자르기
        log_entries = log_entries[:lines]
        
        file_info = {
            "name": LOG_FILES[log_type],
            "size": f"{os.path.getsize(log_file) / 1024:.2f} KB",
            "modified": datetime.fromtimestamp(os.path.getmtime(log_file)).strftime("%Y-%m-%d %H:%M:%S"),
            "log_type": log_type
        }
        
        return templates.TemplateResponse(
            "log_view.html", 
            {
                "request": request, 
                "log_entries": log_entries, 
                "file_info": file_info,
                "lines": lines,
                "error_only": error_only,
                "disk_info": disk_info,
                "log_disk_info": log_disk_info
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"로그 파일 읽기 오류: {str(e)}")
    


