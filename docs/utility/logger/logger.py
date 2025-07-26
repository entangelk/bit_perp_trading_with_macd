# logger.py
import logging
from logging.handlers import RotatingFileHandler

# 로거 생성 및 레벨 설정
logger = logging.getLogger('trading_bot')
logger.setLevel(logging.INFO)

# 핸들러 설정
handler = RotatingFileHandler(
    filename='trading_bot.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=1,
    encoding='utf-8'
)
handler.setLevel(logging.INFO)

# 포맷터 설정
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# 핸들러를 로거에 추가
logger.addHandler(handler)