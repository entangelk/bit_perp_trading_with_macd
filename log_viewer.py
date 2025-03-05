from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os
import re
import shutil
from datetime import datetime
import uvicorn
from pathlib import Path

app = FastAPI(title="트레이딩 봇 로그 뷰어")

# 템플릿 디렉토리 설정
templates = Jinja2Templates(directory="/app/trading_bot/templates")

# 로그 파일 경로 설정
LOG_DIR = "/app/trading_bot"  # 올바른 경로
LOG_FILES = {
    "trading": "trading_bot.log",
    "backtest": "strategy_backtest.log"
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

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """메인 페이지"""
    # 디스크 용량 정보 가져오기
    disk_info = get_disk_usage()
    # EC2 인스턴스의 경우 루트 파일 시스템과 로그 디렉토리 파일 시스템이 다를 수 있음
    log_disk_info = get_disk_usage(LOG_DIR)
    
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request, 
            "log_files": LOG_FILES,
            "disk_info": disk_info,
            "log_disk_info": log_disk_info
        }
    )

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