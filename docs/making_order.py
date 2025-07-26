import os
import requests
import time
import hashlib
import hmac
from dotenv import load_dotenv
import math
import ccxt
from datetime import datetime
import json
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

def sync_time():
    try:

        # Bybit 서버 시간 가져오기 (재시도 처리 추가)
        max_retries = 3
        retry_delay = 10
        server_time = None

        for attempt in range(max_retries):
            try:
                server_time = int(bybit.fetch_time())

                break  # 성공하면 루프 탈출
            except Exception as e:
                print(f"바이비트 서버 시간 가져오기 실패 (시도 {attempt+1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:  # 마지막 시도가 아니면 대기 후 재시도
                    time.sleep(retry_delay)
                else:
                    print(f"바이비트 서버 시간 가져오기 최종 실패: {str(e)}")
                    # 모든 재시도 실패 시 현재 시간으로 대체
                    server_time = int(time.time() * 1000) # 이미 초 단위로 반환됨
                    print("주의: 로컬 시간은 바이비트 서버 시간과 약간의 차이가 있을 수 있습니다")





        local_time = int(datetime.now().timestamp() * 1000)
        time_offset = server_time - local_time
        bybit.options['timeDifference'] = time_offset
        return time_offset
    except Exception as e:
        print(f"서버 시간 동기화 중 오류 발생: {e}")
        return None
    

# Bybit V5 API 서버 시간 조회 함수
def get_server_time():
    try:
        url = "https://api.bybit.com/v5/market/time"
        response = requests.get(url)
        
        if response.status_code == 200:
            server_time = response.json()['time']  # 밀리초 단위 시간 사용
            print(f"서버 시간: {server_time}")
            return server_time
        else:
            print(f"서버 시간 조회 중 오류 발생: {response.status_code}, {response.text}")
            return None
    except Exception as e:
        print(f"서버 시간 조회 중 오류 발생: {e}")
        return None




# 현재 레버리지 조회 함수
def get_leverage(symbol, category='linear'):
    sync_time()
    try:
        timestamp = str(int(time.time() * 1000))
        
        # 요청 파라미터
        params = {
            'category': category,
            'symbol': symbol
        }

        # GET 요청용 서명 생성
        signature = create_signature_for_get(
            timestamp=timestamp,
            api_key=BYBIT_ACCESS_KEY,
            api_secret=BYBIT_SECRET_KEY,
            params=params
        )

        headers = {
            'X-BAPI-API-KEY': BYBIT_ACCESS_KEY,
            'X-BAPI-SIGN': signature,
            'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-RECV-WINDOW': '5000'
        }

        url = "https://api.bybit.com/v5/position/list"
        
        print("요청 헤더:", headers)
        print("요청 데이터:", params)
        
        response = requests.get(url, headers=headers, params=params)
        print("응답:", response.text)

        if response.status_code == 200:
            result = response.json()
            if result['retCode'] == 0:
                return result['result']
            else:
                print(f"API 오류: {result}")
                return None
        else:
            print(f"HTTP 오류: {response.text}")
            return None

    except Exception as e:
        print(f"레버리지 조회 중 오류 발생: {e}")
        return None

# 레버리지 설정 함수 (V5 API)
def set_leverage(symbol, leverage, category='linear'):
   sync_time()
   # 현재 레버리지 확인
   current_leverage_data = get_leverage(symbol, category)

   if current_leverage_data:
       current_leverage = int(current_leverage_data.get('list', [])[0]['leverage'])
       print(f"현재 레버리지: {current_leverage}")
       print(f"설정할 레버리지: {leverage}")

       if current_leverage == leverage:
           print("레버리지가 이미 설정되어 있습니다. 변경할 필요가 없습니다.")
           return current_leverage

   try:
       timestamp = str(int(time.time() * 1000))
       
       # 요청 파라미터
       params = {
           'category': category,
           'symbol': symbol,
           'buyLeverage': str(leverage),
           'sellLeverage': str(leverage)
       }

       # 새로운 서명 생성 방식 적용
       signature = create_signature(
           timestamp=timestamp,
           api_key=BYBIT_ACCESS_KEY,
           api_secret=BYBIT_SECRET_KEY,
           params=params
       )

       # 새로운 헤더 설정
       headers = {
           'X-BAPI-API-KEY': BYBIT_ACCESS_KEY,
           'X-BAPI-SIGN': signature,
           'X-BAPI-TIMESTAMP': timestamp,
           'X-BAPI-RECV-WINDOW': '5000',
           'Content-Type': 'application/json'
       }

       url = "https://api.bybit.com/v5/position/set-leverage"
       
       print("요청 헤더:", headers)
       print("요청 데이터:", params)
       
       response = requests.post(url, headers=headers, json=params)
       print("응답:", response.text)

       if response.status_code == 200:
           result = response.json()
           if result['retCode'] == 0:
               print("레버리지 설정 성공:", result)
               return result
           else:
               print(f"API 오류: {result}")
               return None
       else:
           print(f"HTTP 오류: {response.text}")
           return None

   except Exception as e:
       print(f"레버리지 설정 중 오류 발생: {e}")
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
    
def create_signature(timestamp, api_key, api_secret, params):
    """
    Bybit V5 API 서명 생성 POST
    """
    # 파라미터를 JSON 문자열로 변환
    params_json = json.dumps(params)
    
    # 서명 문자열 생성 (timestamp + api_key + recv_window + params_json)
    signature_string = f"{timestamp}{api_key}5000{params_json}"
    
    # HMAC SHA256 서명 생성
    signature = hmac.new(
        api_secret.encode('utf-8'),
        signature_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return signature

def create_signature_for_get(timestamp, api_key, api_secret, params):
    """
    GET 요청을 위한 서명 생성
    """
    # 파라미터를 알파벳 순으로 정렬
    sorted_params = dict(sorted(params.items()))
    
    # 쿼리 문자열 생성
    query_string = '&'.join([f"{key}={value}" for key, value in sorted_params.items()])
    
    # 서명 문자열 생성
    signature_string = f"{timestamp}{api_key}5000{query_string}"
    
    # HMAC SHA256 서명 생성
    signature = hmac.new(
        api_secret.encode('utf-8'),
        signature_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return signature

def create_order_with_tp_sl(symbol, side, usdt_amount, leverage, current_price, stop_loss, take_profit):
    sync_time()
    try:
        balance = bybit.fetch_balance()
        current_have = balance['USDT']['total']
        
        if usdt_amount <= 0 or usdt_amount > 1:
            print(f"잘못된 투자 비율: {usdt_amount}. 0과 1 사이의 값이어야 합니다.")
            return None
        

        pass
        order_amount = current_have * usdt_amount
        pass
        amount = calculate_amount(order_amount, leverage, current_price)
        
        if amount is None:
            print("BTC 수량이 유효하지 않습니다. 주문을 생성하지 않습니다.")
            return None

        timestamp = str(int(time.time() * 1000))
        
        # 주문 파라미터
        params = {
            'category': 'linear',
            'symbol': symbol,
            'side': side.capitalize(),
            'orderType': 'Market',
            'qty': str(amount),
            'timeInForce': 'IOC',
            'positionIdx': 0
        }

        # 새로운 서명 생성 방식
        signature = create_signature(
            timestamp=timestamp,
            api_key=BYBIT_ACCESS_KEY,
            api_secret=BYBIT_SECRET_KEY,
            params=params
        )

        # 새로운 헤더 설정
        headers = {
            'X-BAPI-API-KEY': BYBIT_ACCESS_KEY,
            'X-BAPI-SIGN': signature,
            'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-RECV-WINDOW': '5000',
            'Content-Type': 'application/json'
        }

        url = "https://api.bybit.com/v5/order/create"
        
        # 디버깅을 위한 출력
        print("요청 헤더:", headers)
        print("요청 데이터:", params)
        
        # 요청 보내기
        response = requests.post(url, headers=headers, json=params)
        print("응답:", response.text)

        if response.status_code == 200:
            result = response.json()
            if result['retCode'] == 0:
                print("주문 성공:", result)
                
                # 이 부분은 기존 코드 유지
                amount, side, avgPrice,pnl = get_position_amount(symbol)
                if avgPrice:
                    set_tp_sl(symbol, stop_loss, take_profit, avgPrice, side)
                return result
            else:
                print("API 오류:", result)
                return None
        else:
            print("HTTP 오류:", response.text)
            return None

    except Exception as e:
        print(f"오류 발생: {str(e)}")
        return None

def set_tp_sl(symbol, stop_loss, take_profit, current_price, side):
    sync_time()
    try:
        # TP 및 SL 가격 계산
        tp_price = take_profit
        sl_price = stop_loss

           
        print(f"현재 가격: {current_price}")
        print(f"계산된 sl_price: {sl_price}")
        print(f"계산된 tp_price: {tp_price}")

        timestamp = str(int(time.time() * 1000))

        params = {
            'category': 'linear',
            'symbol': symbol,
            'tpslMode': 'Full',
            'positionIdx': 0
        }

        if tp_price is not None:
            params['takeProfit'] = str(tp_price)  # round() 제거
        if sl_price is not None:
            params['stopLoss'] = str(sl_price)    # round() 제거

        signature = create_signature(
            timestamp=timestamp,
            api_key=BYBIT_ACCESS_KEY,
            api_secret=BYBIT_SECRET_KEY,
            params=params
        )

        headers = {
            'X-BAPI-API-KEY': BYBIT_ACCESS_KEY,
            'X-BAPI-SIGN': signature,
            'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-RECV-WINDOW': '5000',
            'Content-Type': 'application/json'
        }

        url = "https://api.bybit.com/v5/position/trading-stop"
        
        print("요청 헤더:", headers)
        print("요청 데이터:", params)
        
        response = requests.post(url, headers=headers, json=params)
        print("응답:", response.text)

        if response.status_code == 200:
            result = response.json()
            if result['retCode'] == 0:
                print("TP/SL 설정 성공!")
                return result
            else:
                print(f"API 오류: {result}")
                return None
        else:
            print(f"HTTP 오류: {response.text}")
            return None

    except Exception as e:
        import traceback
        print(f"TP/SL 설정 중 오류 발생: {e}, 오류 발생 위치:", traceback.format_exc())
        return None




# 현재 포지션 정보 조회 함수 (Bybit V5 API)
def get_position_amount(symbol):
    sync_time()
    try:
        timestamp = str(int(time.time() * 1000))
        
        # 요청 파라미터
        params = {
            'category': 'linear',
            'symbol': symbol
        }

        # GET 요청용 서명 생성
        signature = create_signature_for_get(
            timestamp=timestamp,
            api_key=BYBIT_ACCESS_KEY,
            api_secret=BYBIT_SECRET_KEY,
            params=params
        )

        headers = {
            'X-BAPI-API-KEY': BYBIT_ACCESS_KEY,
            'X-BAPI-SIGN': signature,
            'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-RECV-WINDOW': '5000'
        }

        url = "https://api.bybit.com/v5/position/list"
        
        print("요청 헤더:", headers)
        print("요청 데이터:", params)
        
        # GET 요청은 params로 전달
        response = requests.get(url, headers=headers, params=params)
        print("응답:", response.text)

        if response.status_code == 200:
            position_data = response.json()
            if position_data['retCode'] == 0 and position_data['result']['list']:
                position = position_data['result']['list'][0]
                amount = float(position['size'])
                side = position['side']
                avgPrice = float(position['avgPrice'])
                print(f"현재 포지션 수량: {amount}")
                PnL = float(position_data['result']['list'][0]['curRealisedPnl'])
                return amount, side, avgPrice, PnL
            else:
                print("열린 포지션이 없습니다.")
                return None, None, None, None
        else:
            print(f"포지션 조회 중 오류 발생: {response.text}")
            return None, None, None, None

    except Exception as e:
        print(f"포지션 조회 중 오류 발생: {e}")
        return None, None, None, None


def close_position(symbol):
    sync_time()
    try:
        # 현재 포지션의 방향, 수량 조회
        amount, side, avgPrice, PnL = get_position_amount(symbol)
        if amount is None or amount == 0:
            print("청산할 포지션이 없습니다.")
            return None

        # 타임스탬프 생성
        timestamp = str(int(time.time() * 1000))

        # 반대 포지션으로 설정하여 청산 주문 생성
        opposite_side = 'Sell' if side == 'Buy' else 'Buy'
        
        # 요청 파라미터
        params = {
            'category': 'linear',
            'symbol': symbol,
            'side': opposite_side,
            'orderType': 'Market',
            'qty': str(amount),
            'reduceOnly': True,
            'positionIdx': 0
        }

        # 새로운 서명 생성 방식 적용
        signature = create_signature(
            timestamp=timestamp,
            api_key=BYBIT_ACCESS_KEY,
            api_secret=BYBIT_SECRET_KEY,
            params=params
        )

        # 새로운 헤더 설정
        headers = {
            'X-BAPI-API-KEY': BYBIT_ACCESS_KEY,
            'X-BAPI-SIGN': signature,
            'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-RECV-WINDOW': '5000',
            'Content-Type': 'application/json'
        }

        url = "https://api.bybit.com/v5/order/create"
        
        print("요청 헤더:", headers)
        print("요청 데이터:", params)
        
        response = requests.post(url, headers=headers, json=params)
        print("응답:", response.text)

        if response.status_code == 200:
            result = response.json()
            if result['retCode'] == 0:
                print("포지션 청산 성공:", result)
                return result
            else:
                print(f"API 오류: {result}")
                return None
        else:
            print(f"HTTP 오류: {response.text}")
            return None

    except Exception as e:
        print(f"포지션 청산 중 오류 발생: {e}")
        return None





if __name__ == "__main__":
    # 초기 설정
    TRADING_CONFIG = {
    'symbol': 'BTCUSDT',
    'leverage': 5,
    'usdt_amount': 0.1,
    'set_timevalue': '5m',
    'take_profit': 500,
    'stop_loss': 600
}
    symbol = "BTCUSDT"
    leverage = 5
    usdt_amount = 0.1  # 초기 투자금 비율율
    side = 'Buy'
    avgPrice=62404.70
    take_profit = 400
    stop_loss = 400
    current_price = 104644.90
    sl_price = 118128.9
    tp_price = 116438.4
    # set_leverage(symbol, leverage)
    # get_server_time()
    # close_position(symbol)
    # amount,side,avgPrice,pnl = get_position_amount(symbol)
    set_tp_sl(symbol, sl_price, tp_price, current_price, side)
    # from current_price import get_current_price
    # current_price = get_current_price(symbol=symbol)
    # create_order_with_tp_sl(symbol, side, usdt_amount, leverage,current_price,stop_loss,take_profit)
    pass