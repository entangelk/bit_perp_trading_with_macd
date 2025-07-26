import logging
import json
from datetime import datetime
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import time

# access.log 로거 설정
access_logger = logging.getLogger("access_log")
access_logger.setLevel(logging.INFO)

# 파일 핸들러 설정 (access.log 파일에 저장)
access_handler = logging.FileHandler("/app/trading_bot/access.log", encoding='utf-8')
access_formatter = logging.Formatter('%(message)s')
access_handler.setFormatter(access_formatter)
access_logger.addHandler(access_handler)
access_logger.propagate = False  # 다른 로거로 전파 방지

class SecurityLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
    
    def get_real_ip(self, request: Request) -> str:
        """실제 클라이언트 IP 주소를 가져옵니다."""
        # nginx에서 전달하는 헤더들을 순서대로 확인
        forwarded_for = request.headers.get("X-Forwarded-For")
        real_ip = request.headers.get("X-Real-IP")
        
        if forwarded_for:
            # X-Forwarded-For에 여러 IP가 있을 수 있으므로 첫 번째 사용
            return forwarded_for.split(',')[0].strip()
        elif real_ip:
            return real_ip
        else:
            # 헤더가 없으면 기본 IP 사용 (내부 네트워크 IP)
            return request.client.host
    
    def is_suspicious_request(self, request: Request) -> bool:
        """의심스러운 요청인지 확인합니다."""
        suspicious_paths = [
            "/.env", "/admin", "/wp-admin", "/phpmyadmin", 
            "/.git", "/config", "/backup", "/uploads",
            "/shell", "/cmd", "/etc/passwd", "/api/v1/users",
            "/.well-known/security.txt", "/robots.txt"
        ]
        
        suspicious_user_agents = [
            "bot", "crawler", "spider", "scanner", "nuclei",
            "sqlmap", "nikto", "dirb", "gobuster", "masscan"
        ]
        
        path = str(request.url.path).lower()
        user_agent = request.headers.get("user-agent", "").lower()
        
        # 의심스러운 경로 체크
        if any(sus_path in path for sus_path in suspicious_paths):
            return True
            
        # 의심스러운 User-Agent 체크
        if any(sus_agent in user_agent for sus_agent in suspicious_user_agents):
            return True
            
        return False
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # 요청 정보 수집
        real_ip = self.get_real_ip(request)
        user_agent = request.headers.get("user-agent", "Unknown")
        referer = request.headers.get("referer", "")
        host = request.headers.get("host", "")
        method = request.method
        path = str(request.url.path)
        query = str(request.url.query) if request.url.query else ""
        
        # 의심스러운 요청 체크
        is_suspicious = self.is_suspicious_request(request)
        
        # 응답 처리
        response = await call_next(request)
        
        # 처리 시간 계산
        process_time = time.time() - start_time
        
        # 로그 데이터 구성
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "ip": real_ip,
            "method": method,
            "path": path,
            "query": query,
            "status_code": response.status_code,
            "user_agent": user_agent,
            "referer": referer,
            "host": host,
            "process_time": round(process_time, 3),
            "suspicious": is_suspicious,
            "response_size": response.headers.get("content-length", "0")
        }
        
        # JSON 형태로 로그 기록
        access_logger.info(json.dumps(log_data, ensure_ascii=False))
        
        # 의심스러운 요청은 추가로 경고 레벨로 기록
        if is_suspicious:
            access_logger.warning(f"SUSPICIOUS: {real_ip} {method} {path} - {user_agent}")
        
        return response

