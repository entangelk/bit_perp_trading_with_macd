import requests
import hmac
import hashlib
import time
import json
from dotenv import load_dotenv
import os

# 환경 변수 로드
load_dotenv()

def get_bybit_signature(api_secret, params_str):
    return hmac.new(
        api_secret.encode('utf-8'),
        params_str.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

def get_win_rate(api_key, api_secret, start_time=None, end_time=None, limit=100):
    # API 엔드포인트 설정
    url = "https://api.bybit.com/v5/position/closed-pnl"
    
    # 타임스탬프
    timestamp = int(time.time() * 1000)
    
    # 파라미터 설정
    params = {
        'category': 'linear',  # 선물 거래 (USDT 페어펀딩)
        'limit': limit,
        'timestamp': timestamp,
        'api_key': api_key,
    }
    
    if start_time:
        params['startTime'] = start_time
    if end_time:
        params['endTime'] = end_time
    
    # 파라미터 정렬 및 문자열 변환
    params_str = '&'.join([f"{key}={params[key]}" for key in sorted(params.keys())])
    
    # 서명 생성
    signature = get_bybit_signature(api_secret, params_str)
    params['sign'] = signature
    
    # API 요청
    response = requests.get(url, params=params)
    data = response.json()
    
    if data['retCode'] != 0:
        raise Exception(f"API 오류: {data['retMsg']}")
    
    # 승률 계산
    trades = data['result']['list']
    win_trades = sum(1 for trade in trades if float(trade['closedPnl']) > 0)
    total_trades = len(trades)
    
    win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0


    return {
        'win_rate': win_rate,
        'win_trades': win_trades,
        'total_trades': total_trades,
        'trades': trades
    }

def get_7win_rate(api_key, api_secret, start_time=None, end_time=None, limit=100):
    # API 엔드포인트 설정
    url = "https://api.bybit.com/v5/position/closed-pnl"
    
    # 타임스탬프
    timestamp = int(time.time() * 1000)
    
    # 파라미터 설정
    params = {
        'category': 'linear',  # 선물 거래 (USDT 페어펀딩)
        'limit': limit,
        'timestamp': timestamp,
        'api_key': api_key,
    }
    
    if start_time:
        params['startTime'] = start_time
    if end_time:
        params['endTime'] = end_time
    
    # 파라미터 정렬 및 문자열 변환
    params_str = '&'.join([f"{key}={params[key]}" for key in sorted(params.keys())])
    
    # 서명 생성
    signature = get_bybit_signature(api_secret, params_str)
    params['sign'] = signature
    
    # API 요청
    response = requests.get(url, params=params)
    data = response.json()
    
    if data['retCode'] != 0:
        raise Exception(f"API 오류: {data['retMsg']}")
    
    # 승률 계산
    trades = data['result']['list']
    total_trades = len(trades)
    
    # 마지막 7거래 승률 계산 (7거래 미만일 경우 5거래로 계산)
    if total_trades >= 7:
        trades = trades[-7:]
    elif total_trades >= 5:
        trades = trades[-5:]
    else:
        trades = trades[-total_trades:]

    win_trades = sum(1 for trade in trades if float(trade['closedPnl']) > 0)
    total_trades = len(trades)
    win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0

    # 승률을 50% 기준으로 True/False로 변환
    win_rate = True if win_rate >= 50 else False
    # 결과를 json 파일로 저장 (파일이 경로에 없을 시 자동생성)
    with open('win_rate.json', 'w') as f:
        json.dump({'win_rate': win_rate}, f)

    return 

if __name__ == "__main__":
    # Bybit API 키와 시크릿 가져오기
    BYBIT_ACCESS_KEY = os.getenv("BYBIT_ACCESS_KEY")
    BYBIT_SECRET_KEY = os.getenv("BYBIT_SECRET_KEY")
    # 사용 예시
    api_key = BYBIT_ACCESS_KEY
    api_secret = BYBIT_SECRET_KEY

    result = get_win_rate(api_key, api_secret)
    print(f"승률: {result['win_rate']:.2f}%")
    print(f"총 거래: {result['total_trades']}건, 수익 거래: {result['win_trades']}건")