import requests
import json
from collections import defaultdict

def fetch_order_book_bybit(symbol="BTCUSDT", category="linear", limit=500):
    url = "https://api.bybit.com/v5/market/orderbook"

    # 요청할 심볼, 카테고리, 깊이 설정
    params = {
        "symbol": symbol,
        "category": category,
        "limit": limit  # 최대 500개의 Bid/Ask 데이터를 요청
    }

    try:
        # API 호출
        response = requests.get(url, params=params)

        # 상태 코드 확인
        if response.status_code != 200:
            print(f"API 호출 실패: {response.text}")
            return

        # JSON 데이터로 변환
        data = response.json()

        # 오더북 데이터 확인 (b: Bid, a: Ask)
        order_book_data = data['result']
        bids = order_book_data['b']
        asks = order_book_data['a']

        # 그룹화된 데이터를 저장할 딕셔너리 초기화
        bids_grouped = defaultdict(float)
        asks_grouped = defaultdict(float)

        # 가격을 1 단위로 변환하여 그룹화 (bids)
        for bid in bids:
            price = float(bid[0])  # 가격
            volume = float(bid[1])  # 수량
            grouped_price = round(price)  # 1 단위로 그룹화 (반올림)
            bids_grouped[grouped_price] += volume  # 같은 가격대의 거래량 합산

        # 가격을 1 단위로 변환하여 그룹화 (asks)
        for ask in asks:
            price = float(ask[0])  # 가격
            volume = float(ask[1])  # 수량
            grouped_price = round(price)  # 1 단위로 그룹화 (반올림)
            asks_grouped[grouped_price] += volume  # 같은 가격대의 거래량 합산

        # 상위 50개 비드와 애스크 가져오기 (정렬 후 상위 50개 선택)
        bids_grouped_list = sorted(bids_grouped.items(), key=lambda x: -x[0])[:50]  # 가격 내림차순
        asks_grouped_list = sorted(asks_grouped.items(), key=lambda x: x[0])[:50]   # 가격 오름차순

        # JSON으로 Bid와 Ask 데이터를 하나로 묶기
        orderbook_json = {
            "bids": bids_grouped_list,
            "asks": asks_grouped_list
        }

        # 결과 출력
        print(json.dumps(orderbook_json, indent=4))

        return orderbook_json

    except Exception as e:
        print(f"오류 발생: {e}")
        return None