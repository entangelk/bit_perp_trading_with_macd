import ccxt
import os
from dotenv import load_dotenv


# 현재 비트코인 가격을 가져오는 함수
def get_current_price(symbol):

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
            'recvWindow': 10000,  # 기본값을 10초로 증가
        },
        'enableRateLimit': True  # API 호출 속도 제한 관리 활성화
    })
    ticker = bybit.fetch_ticker(symbol)
    current_price = ticker['last']  # 마지막 거래 가격 (현재 가격)
    print(f"현재 {symbol} 가격: {current_price}")

    return current_price


if __name__ == "__main__":
    symbol = "BTCUSDT"
    get_current_price(symbol)
