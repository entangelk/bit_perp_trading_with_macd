from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os
import re
import shutil
import psutil
from datetime import datetime
import uvicorn
from pathlib import Path
from routers.trading_stats import router as trading_stats_router
import time

app = FastAPI(title="트레이딩 봇 로그 뷰어")
app.include_router(trading_stats_router)

# 템플릿 디렉토리 설정
templates = Jinja2Templates(directory="/app/trading_bot/templates")

# 로그 파일 경로 설정
LOG_DIR = "/app/trading_bot"  # 올바른 경로
LOG_FILES = {
    "trading": "trading_bot.log",
    "backtest": "strategy_backtest.log"
}

# 모니터링할 파일 설정
MONITOR_FILES = {
    "main": "main.py",    # 트레이딩 봇
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
    backtest_status = check_process_status(MONITOR_FILES["backtest"])
    
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
            "backtest_status": backtest_status,
            "now": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "trade_analysis_json": json.dumps(trade_analysis),  # 추가된 부분
            "win_rate": win_rate  # 추가된 부분
        }
    )

@app.get("/api/trade_analysis")
async def get_trade_analysis():
    data = analyzer.get_visualization_data(hours=24)
    return data

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
    

    # FastAPI 라우터에 추가할 코드
import json


@app.get("/strategy-config", response_class=HTMLResponse)
async def view_strategy_config(request: Request):
    """트레이딩 전략 설정을 표시합니다."""
    try:
        # 설정 파일 경로
        config_path = '/app/trading_bot/stg_config.json'
        enable_config_path = '/app/trading_bot/STRATEGY_ENABLE.json'
        
        # 디스크 용량 정보 가져오기
        disk_info = get_disk_usage()
        log_disk_info = get_disk_usage(LOG_DIR)
        
        # 프로세스 상태 확인
        main_status = check_process_status(MONITOR_FILES["main"])
        backtest_status = check_process_status(MONITOR_FILES["backtest"])
        
        # 설정 파일 존재 여부 확인
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    stg_config = json.load(f)
                
                # 파일 정보 (마지막 수정 시간)
                file_stat = os.stat(config_path)
                config_updated_at = datetime.fromtimestamp(file_stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                
                # 전략 활성화 설정 파일 불러오기
                strategy_enable = {}
                if os.path.exists(enable_config_path):
                    try:
                        with open(enable_config_path, 'r') as f:
                            strategy_enable = json.load(f)
                    except json.JSONDecodeError:
                        # 파일 형식 오류가 있더라도 계속 진행
                        strategy_enable = {"error": "활성화 설정 파일 형식이 올바르지 않습니다."}
                
                return templates.TemplateResponse(
                    "strategy_config.html", 
                    {
                        "request": request,
                        "stg_config": stg_config,
                        "strategy_enable": strategy_enable,
                        "config_updated_at": config_updated_at,
                        "disk_info": disk_info,
                        "log_disk_info": log_disk_info,
                        "main_status": main_status,
                        "backtest_status": backtest_status,
                        "now": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                )
            except json.JSONDecodeError:
                return templates.TemplateResponse(
                    "strategy_config.html", 
                    {
                        "request": request,
                        "error": "설정 파일 형식이 올바르지 않습니다.",
                        "disk_info": disk_info,
                        "log_disk_info": log_disk_info,
                        "main_status": main_status,
                        "backtest_status": backtest_status,
                        "now": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                )
        else:
            return templates.TemplateResponse(
                "strategy_config.html", 
                {
                    "request": request,
                    "error": "전략 설정 파일이 아직 생성되지 않았습니다. back_test.py가 실행 중인지 확인하세요.",
                    "disk_info": disk_info,
                    "log_disk_info": log_disk_info,
                    "main_status": main_status,
                    "backtest_status": backtest_status,
                    "now": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"전략 설정 페이지 오류: {str(e)}")