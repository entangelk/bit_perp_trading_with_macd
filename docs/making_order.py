import os
import requests
import time
import hashlib
import hmac
from dotenv import load_dotenv
import math

# 환경 변수 로드
load_dotenv()

# Bybit API 키와 시크릿 가져오기
BYBIT_ACCESS_KEY = os.getenv("BYBIT_ACCESS_KEY")
BYBIT_SECRET_KEY = os.getenv("BYBIT_SECRET_KEY")

# Bybit API 서명 생성 함수
def create_signature(api_key, secret, params):
    query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
    return hmac.new(bytes(secret, 'utf-8'), bytes(query_string, 'utf-8'), hashlib.sha256).hexdigest()

# Bybit V2 API 서버 시간 조회 함수
def get_server_time():
    try:
        url = "https://api.bybit.com/v2/public/time"
        response = requests.get(url)
        
        pass
        if response.status_code == 200:
            server_time = response.json()['time_now']
            server_time_ms = int(float(server_time) * 1000)
            print(f"서버 시간: {server_time_ms}")
            return server_time_ms
        else:
            print(f"서버 시간 조회 중 오류 발생: {response.status_code}, {response.text}")
            return None
    except Exception as e:
        print(f"서버 시간 조회 중 오류 발생: {e}")
        return None




# 현재 레버리지 조회 함수
def get_leverage(symbol, category='linear'):
    url = "https://api.bybit.com/v5/position/list"
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    params = {
        'api_key': BYBIT_ACCESS_KEY,
        'symbol': symbol,
        'category': category,  # 선물 종류 (linear는 USDT 무기한 선물, inverse는 코인 기반)
        'timestamp': int(time.time() * 1000),
        'recv_window': 60000
    }

    # 서명 생성
    signature = create_signature(BYBIT_ACCESS_KEY, BYBIT_SECRET_KEY, params)
    params['sign'] = signature

    # HTTP GET 요청 보내기
    try:
        response = requests.get(url, headers=headers, params=params)

        # 응답 상태 코드 확인
        print(f"응답 상태 코드: {response.status_code}")
        print(f"응답 내용: {response.text}")  # 응답 내용 출력

        if response.status_code == 200:
            response_data = response.json()
            return response_data['result']  # 현재 레버리지 값 반환
        else:
            print("서버 응답 오류:", response.text)
            return None

    except Exception as e:
        print(f"레버리지 조회 중 오류 발생: {e}")
        return None

# 레버리지 설정 함수 (V5 API)
def set_leverage(symbol, leverage, category='linear'):
    # 현재 레버리지 확인
    current_leverage_data = get_leverage(symbol, category)

    if current_leverage_data:
        current_leverage = int(current_leverage_data.get('list', [])[0]['leverage'])  # 현재 레버리지 추출
        print(f"현재 레버리지: {current_leverage}")
        print(f"설정할 레버리지: {leverage}")

        # 현재 설정된 레버리지와 동일한 경우 설정하지 않음
        if current_leverage == leverage:
            print("레버리지가 이미 설정되어 있습니다. 변경할 필요가 없습니다.")
            return current_leverage

    # 레버리지가 다른 경우에만 설정
    url = "https://api.bybit.com/v5/position/set-leverage"
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    params = {
        'api_key': BYBIT_ACCESS_KEY,
        'symbol': symbol,
        'buyLeverage': leverage,
        'sellLeverage': leverage,
        'category': category,
        'timestamp': int(time.time() * 1000),
        'recv_window': 60000
    }

    # 서명 생성
    signature = create_signature(BYBIT_ACCESS_KEY, BYBIT_SECRET_KEY, params)
    params['sign'] = signature

    # HTTP POST 요청 보내기
    try:
        response = requests.post(url, headers=headers, data=params)

        # 응답 상태 코드 확인
        print(f"응답 상태 코드: {response.status_code}")
        print(f"응답 내용: {response.text}")

        if response.status_code == 200:
            response_data = response.json()

            if response_data['retCode'] == 0:
                print(f"레버리지 설정 성공: {response_data}")
            else:
                print(f"레버리지 설정 중 오류 발생: {response_data}")
            return response_data
        else:
            print("서버 응답 오류:", response.text)
            return None

    except Exception as e:
        print(f"HTTP 요청 중 오류 발생: {e}")
        return None


# USDT 기준으로 BTC 수량 계산 함수
def calculate_amount(usdt_amount, leverage, current_price):
    try:
        # 레버리지 적용 후 거래할 수 있는 USDT 금액
        target_investment = usdt_amount * leverage
        
        # USDT 기준으로 BTC 수량 계산 (소수점 3자리까지 버림)
        raw_amount = target_investment / current_price
        amount = math.floor(raw_amount * 1000) / 1000  # 소수점 3자리까지 버림
        if amount < 0.001:  # 최소 수량 제한을 예로 들어 0.001로 설정
            print("오류: 최소 주문 수량을 충족하지 않습니다. 최소 수량인 0.001로 시작합니다")
            amount = 0.001
            
        return amount
    except Exception as e:
        print(f"amount 계산 중 오류 발생: {e}")
        return None

def create_order_with_tp_sl(symbol, side, usdt_amount, leverage,current_price,stop_loss,tp_rate):
    try:
        # 외부에서 전달된 현재 가격을 기준으로 수량 계산
        amount = calculate_amount(usdt_amount, leverage, current_price)
        if amount is None:
            print("BTC 수량이 유효하지 않습니다. 주문을 생성하지 않습니다.")
            return None

        # Bybit V5 API 시장가 주문 엔드포인트
        url = "https://api.bybit.com/v5/order/create"
        server_time = get_server_time()
        timestamp = server_time if server_time else int(time.time() * 1000)

        # 시장가 주문 기본 파라미터
        params = {
            'api_key': BYBIT_ACCESS_KEY,
            'symbol': symbol,
            'side': side.capitalize(),
            'orderType': 'Market',
            'qty': amount,
            'category': 'linear',
            'leverage': leverage,
            'timestamp': timestamp,
            'recv_window': 5000
        }

        # 서명 생성
        signature = create_signature(BYBIT_ACCESS_KEY, BYBIT_SECRET_KEY, params)
        params['sign'] = signature

        # 시장가 주문 생성 요청
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        response = requests.post(url, headers=headers, data=params)

        if response.status_code == 200:
            order_data = response.json()
            print(f"시장가 주문 생성 성공: {order_data}")

            # 포지션 정보 조회
            amount,side,avgPrice = get_position_amount(symbol)

            if avgPrice:
                # TP/SL 설정
                set_tp_sl(symbol,stop_loss,tp_rate,current_price,side)
            return order_data
        else:
            print(f"시장가 주문 생성 중 오류 발생: {response.text}")
            return None

    except Exception as e:
        print(f"주문 생성 중 오류 발생: {e}")
        return None

def set_tp_sl(symbol, stop_loss,tp_rate,current_price,side):
    try:
        # TP 및 SL 가격 계산
        tp_price = None
        sl_price = stop_loss

        if side == 'Long':
            tp_price = current_price + (current_price - stop_loss)*tp_rate 
        else:
            tp_price = current_price - (current_price + stop_loss)*tp_rate
            

        server_time = get_server_time()
        timestamp = server_time if server_time else int(time.time() * 1000)
        # TP/SL 설정 파라미터
        tp_sl_params = {
            'api_key': BYBIT_ACCESS_KEY,
            'symbol': symbol,
            'category': 'linear',  # USDT perpetual 기준
            'tpslMode': 'Full',  # 전체 포지션에 대해 TP/SL 설정
            'positionIdx': 0,  # 기본 포지션 모드 설정
            'timestamp': timestamp,
            'recv_window': 5000
        }

        # 옵션별 TP 및 SL 추가
        if tp_price is not None:
            tp_sl_params['takeProfit'] = str(round(tp_price, 2))
        if sl_price is not None:
            tp_sl_params['stopLoss'] = str(round(sl_price, 2))

        # 서명 생성
        signature = create_signature(BYBIT_ACCESS_KEY, BYBIT_SECRET_KEY, tp_sl_params)
        tp_sl_params['sign'] = signature

        # 엔드포인트 URL
        tp_sl_url = "https://api.bybit.com/v5/position/trading-stop"
        
        # API 요청
        tp_sl_response = requests.post(tp_sl_url, headers={'Content-Type': 'application/x-www-form-urlencoded'}, data=tp_sl_params)
        pass
        # 응답 처리
        if tp_sl_response.status_code == 200:
            print("TP/SL 설정 성공!")
        else:
            print(f"TP/SL 설정 중 오류 발생: {tp_sl_response.text}")

    except Exception as e:
        print(f"TP/SL 설정 중 오류 발생: {e}")




# 현재 포지션 정보 조회 함수 (Bybit V5 API)
def get_position_amount(symbol):
    try:
        url = "https://api.bybit.com/v5/position/list"
        timestamp = int(time.time() * 1000)

        params = {
            'api_key': BYBIT_ACCESS_KEY,
            'symbol': symbol,  # 예: 'BTCUSDT'
            'category': 'linear',  # USDT 기반 선물
            'timestamp': timestamp,
            'recv_window': 60000
        }

        # 서명 생성
        signature = create_signature(BYBIT_ACCESS_KEY, BYBIT_SECRET_KEY, params)
        params['sign'] = signature

        # Bybit V5 API 요청
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        response = requests.get(url, headers=headers, params=params)

        # 응답 처리
        if response.status_code == 200:
            position_data = response.json()

            # 포지션 정보에서 현재 포지션 수량(amount)을 추출
            if position_data['result']['list']:
                position = position_data['result']['list'][0]
                amount = float(position['size'])  # 포지션 수량 추출
                side = position['side']
                avgPrice = float(position['avgPrice'])
                print(f"현재 포지션 수량: {amount}")
                pass

                return amount,side,avgPrice
            else:
                print("열린 포지션이 없습니다.")
                return None
        else:
            print(f"포지션 조회 중 오류 발생: {response.text}")
            return None

    except Exception as e:
        print(f"포지션 조회 중 오류 발생: {e}")
        return None

def close_position(symbol):
    try:
        # 현재 포지션의 방향, 수량 조회
        amount,side,avgPrice = get_position_amount(symbol)
        if amount is None or amount == 0:
            print("청산할 포지션이 없습니다.")
            return None

        # Bybit V5 API 포지션 청산 엔드포인트
        url = "https://api.bybit.com/v5/order/create"
        
        # 서버 시간 가져오기
        server_time = get_server_time()
        timestamp = server_time if server_time else int(time.time() * 1000)

        # 반대 포지션으로 설정하여 청산 주문 생성
        opposite_side = 'Sell' if side == 'Buy' else 'Buy'
        params = {
            'api_key': BYBIT_ACCESS_KEY,
            'symbol': symbol,
            'side': opposite_side,  # 'Buy' 또는 'Sell'만 사용
            'orderType': 'Market',
            'qty': str(amount),
            'category': 'linear',
            'reduceOnly': 'true',
            'timestamp': str(timestamp),
            'recv_window': '60000'
        }

        # 서명 생성
        signature = create_signature(BYBIT_ACCESS_KEY, BYBIT_SECRET_KEY, params)
        params['sign'] = signature

        # Bybit V5 API 요청
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, headers=headers, json=params)

        # 응답 처리
        if response.status_code == 200:
            close_data = response.json()
            print(f"포지션 청산 성공: {close_data}")
            return close_data
        else:
            print(f"포지션 청산 중 오류 발생: {response.text}")
            return None

    except Exception as e:
        print(f"포지션 청산 중 오류 발생: {e}")
        return None





if __name__ == "__main__":
    # 초기 설정
    symbol = "BTCUSDT"
    leverage = 100
    initial_usdt_amount = 1  # 초기 투자금
    side = 'Buy'
    avgPrice=62404.70
    tp_rate = 0.2
    sl_rate = 0.2
    # set_leverage(symbol, leverage)
    # get_server_time()
    # close_position(symbol)
    # get_position_amount(symbol)
    set_tp_sl(symbol, side, avgPrice, leverage, tp_rate, sl_rate)
