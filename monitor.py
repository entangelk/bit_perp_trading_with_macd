from dotenv import load_dotenv
import os

load_dotenv()

import psutil
import time
import smtplib
from email.message import EmailMessage
from datetime import datetime

# 모니터링할 프로세스 설정
MONITOR_FILES = {
    "main": "main.py",    # 트레이딩 봇
    "backtest": "back_test.py"  # 백테스트 
}

# 이메일 설정
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")  # Gmail 앱 비밀번호
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")


ALERT_INTERVAL = 28800  # 8시간마다 알림 반복 (초 단위: 8시간 = 8 * 60 * 60 = 28800초)

# 마지막으로 알림을 보낸 시간 기록
last_alert_time = {process: 0 for process in MONITOR_FILES.keys()}

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

def send_email_alert(process_name, is_first_alert=False):
    """Gmail을 통해 알림 이메일을 보냅니다."""
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 첫 번째 알림인지 반복 알림인지에 따라 메시지 내용 변경
    if is_first_alert:
        content = f"""
        경고: {process_name} 프로세스가 실행을 멈췄습니다!
        
        시간: {current_time}
        
        서버에서 프로세스 상태를 확인해주세요.
        """
        subject = f"[서버 알림] {process_name} 프로세스 중지됨"
    else:
        content = f"""
        경고: {process_name} 프로세스가 여전히 중지 상태입니다.
        
        최초 감지 후 계속 중지된 상태입니다.
        현재 시간: {current_time}
        
        서버에서 프로세스 상태를 확인해주세요.
        """
        subject = f"[서버 알림] {process_name} 프로세스 계속 중지 상태"
    
    msg = EmailMessage()
    msg.set_content(content)
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = RECIPIENT_EMAIL
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print(f"'{process_name}' 알림 이메일 전송 완료 ({current_time})")
        return True
    except Exception as e:
        print(f"이메일 전송 실패: {e} ({current_time})")
        return False

def main():
    print(f"프로세스 모니터링 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    
    # 각 프로세스의 이전 상태 기록
    previous_status = {}
    # 프로세스가 중지된 시간을 기록
    stopped_since = {}
    
    for process_name, script_name in MONITOR_FILES.items():
        status = check_process_status(script_name)
        previous_status[process_name] = status['running']
        
        status_text = "실행 중" if status['running'] else "실행되지 않음"
        print(f"{process_name} ({script_name}): {status_text}")
    
    while True:
        current_time = time.time()
        
        for process_name, script_name in MONITOR_FILES.items():
            # 현재 상태 확인
            status = check_process_status(script_name)
            
            # 이전에 실행 중이었는데 지금 실행 중이 아니면 알림 전송
            if previous_status[process_name] and not status['running']:
                # 프로세스가 처음 중지되었을 때
                print(f"{process_name} ({script_name})이(가) 중지되었습니다. ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
                stopped_since[process_name] = current_time  # 중지된 시간 기록
                send_email_alert(process_name, is_first_alert=True)
                last_alert_time[process_name] = current_time
            
            # 프로세스가 계속 중지 상태이면 8시간마다 알림 반복
            elif not status['running'] and process_name in stopped_since:
                time_since_last_alert = current_time - last_alert_time.get(process_name, 0)
                
                # 마지막 알림 이후 지정된 시간이 지났으면 알림 재전송
                if time_since_last_alert > ALERT_INTERVAL:
                    send_email_alert(process_name, is_first_alert=False)
                    last_alert_time[process_name] = current_time
            
            # 이전에 실행 중이 아니었는데 지금 실행 중이면 기록
            elif not previous_status[process_name] and status['running']:
                print(f"{process_name} ({script_name})이(가) 다시 실행 중입니다. ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
                # 중지 시간 기록 제거
                if process_name in stopped_since:
                    del stopped_since[process_name]
            
            # 상태 업데이트
            previous_status[process_name] = status['running']
        
        # 60초마다 확인
        time.sleep(300)

if __name__ == "__main__":
    main()