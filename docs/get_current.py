import ccxt
import os
from dotenv import load_dotenv
from datetime import datetime
import json
import time
# 환경 변수 로드
load_dotenv()

# Bybit API 키와 시크릿 가져오기
BYBIT_ACCESS_KEY = os.getenv("BYBIT_ACCESS_KEY")
BYBIT_SECRET_KEY = os.getenv("BYBIT_SECRET_KEY")

# Bybit 거래소 객체 생성
bybit = ccxt.bybit({
    'apiKey': BYBIT_ACCESS_KEY,
    'secret': BYBIT_SECRET_KEY,
    'options': {
        'defaultType': 'swap',  # 무기한 선물 (perpetual swap) 용
        'recvWindow': 10000  # recv_window를 10초로 증가
    },
    'enableRateLimit': True  # API 호출 속도 제한 관리 활성화
})

# 서버 시간을 클라이언트 시간과 동기화하는 방법
def sync_time():
    try:
        # Bybit 서버 시간 가져오기 (재시도 처리 추가)
        max_retries = 3
        retry_delay = 10
        server_time = None

        for attempt in range(max_retries):
            try:
                server_time = bybit.fetch_time() / 1000  # 밀리초를 초 단위로 변환
                server_datetime = datetime.utcfromtimestamp(server_time)
                print(f"바이비트 서버 시간 (UTC): {server_datetime}")
                break  # 성공하면 루프 탈출
            except Exception as e:
                print(f"바이비트 서버 시간 가져오기 실패 (시도 {attempt+1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:  # 마지막 시도가 아니면 대기 후 재시도
                    time.sleep(retry_delay)
                else:
                    print(f"바이비트 서버 시간 가져오기 최종 실패: {str(e)}")
                    # 모든 재시도 실패 시 현재 시간으로 대체
                    server_time = time.time()  # 이미 초 단위로 반환됨
                    server_datetime = datetime.utcfromtimestamp(server_time)
                    print(f"로컬 시간으로 대체 (UTC): {server_datetime}")
                    print("주의: 로컬 시간은 바이비트 서버 시간과 약간의 차이가 있을 수 있습니다")
        print(f"Bybit 서버 시간 (UTC): {server_datetime}")
        return server_time
    except Exception as e:
        print(f"서버 시간 동기화 중 오류 발생: {e}")
        return None



def fetch_investment_status():

    try:
        # 서버 시간 동기화 시도
        sync_time()
        # 이전 거래 기록 가져오기
        ledger = bybit.fetch_ledger()

        # 현재 잔고 정보 가져오기
        balance = bybit.fetch_balance()
        # print("잔고 정보:")
        # print(balance)

        # 현재 포지션 정보 가져오기
        positions = bybit.fetch_positions()
        print("\n포지션 정보:")
        active_positions = []  # 포지션이 있는 항목만 추가할 리스트

        for position in positions:
            if float(position['contracts']) > 0:  # 포지션이 있는 경우에만 처리
                print(f"심볼: {position['symbol']}")
                print(f"진입 가격: {position['entryPrice']}")
                print(f"현재 수량: {position['contracts']}")
                print(f"미실현 손익: {position['unrealizedPnl']}")
                print(f"레버리지: {position['leverage']}")
                print(f"현재 가격: {position['markPrice']}")
                print(f"포지션 방향: {position['side']}")
                print("------")

                # 포지션이 있는 항목을 리스트에 추가
                active_positions.append(position)

        if not active_positions:
            print('현재 포지션 없음')

        # 포지션을 JSON으로 변환하여 반환
        positions_json = json.dumps(active_positions)

    except Exception as e:
        print(f"API 호출 중 오류 발생: {e}")
        return 'error', None, None
    pass
    return balance, positions_json, ledger

if __name__ == "__main__":
    balance, positions_json, ledger = fetch_investment_status()
    sync_time()
    positions = bybit.fetch_positions()
    print(positions)
    pass