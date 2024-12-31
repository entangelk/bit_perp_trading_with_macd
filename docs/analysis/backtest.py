import os
import pandas as pd
import numpy as np
from pymongo import MongoClient
import ta
import sys

# 현재 파일이 위치한 경로의 상위 디렉토리를 모듈 경로에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# docs.get_chart 모듈을 임포트
from docs.get_chart import chart_update

# 전저점(SL)을 찾는 함수: 현재 가격부터 이전 가격을 하나씩 확인하여 반전이 일어나는 시점까지 찾기
def find_previous_low(data, current_index):
    recent_low = data.loc[current_index, 'low']  # 현재 시점의 low
    for i in range(current_index - 1, -1, -1):  # 현재 시점 이전의 가격을 탐색
        if data.loc[i, 'low'] > recent_low:
            # 이전 가격이 현재 가격보다 높으면, 최근 하락 구간이 끝난 것으로 판단
            break
        recent_low = data.loc[i, 'low']
    return recent_low

# 전고점(SL)을 찾는 함수: 현재 가격부터 이전 가격을 하나씩 확인하여 반전이 일어나는 시점까지 찾기
def find_previous_high(data, current_index):
    recent_high = data.loc[current_index, 'high']  # 현재 시점의 high
    for i in range(current_index - 1, -1, -1):  # 현재 시점 이전의 가격을 탐색
        if data.loc[i, 'high'] < recent_high:
            # 이전 가격이 현재 가격보다 낮으면, 최근 상승 구간이 끝난 것으로 판단
            break
        recent_high = data.loc[i, 'high']
    return recent_high

def back_testing():

    chart_update()

    # MongoDB에 접속하여 데이터 로드
    mongoClient = MongoClient("mongodb://mongodb:27017")
    database = mongoClient["bitcoin"]
    chart_collection_3m = database['chart_3m']
    chart_collection_1m = database['chart_1m']
    chart_collection_5m = database['chart_5m']
    chart_collection_15m = database['chart_15m']

    # 3분봉 테스트
    data_list = list(chart_collection_3m.find())


    # 1분봉 테스트
    days = 5
    minutes = 1440

    # MongoDB에서 최신 데이터를 기준으로 필요한 개수만큼 조회 (역순으로 정렬 후 제한)
    data_list = list(chart_collection_1m.find().sort([('_id', -1)]).limit(days * minutes))
    

    # 5분봉 테스트
    data_list = list(chart_collection_5m.find())

    # 15분봉 테스트
    # data_list = list(chart_collection_15m.find())




    if data_list:
        data = pd.DataFrame(data_list)
        if '_id' in data.columns:
            data.drop(columns=['_id'], inplace=True)
    
    data['timestamp'] = pd.to_datetime(data['timestamp'])


    # timestamp를 기준으로 다시 오름차순으로 정렬
    data.sort_values(by='timestamp', inplace=True)

    # 옵션
    tp_rate = 1.5
    stop_loss_rate = 0.0001
    leverage = 1  # 레버리지 적용
    fee_rate = 0.0000
    position_size_usdt = 10000  # 거래량을 10000 USDT로 가정

    # 지표 계산 (MACD, RSI, Stochastic)
    data['EMA12'] = data['close'].ewm(span=12, adjust=False).mean()
    data['EMA26'] = data['close'].ewm(span=26, adjust=False).mean()
    data['MACD'] = data['EMA12'] - data['EMA26']
    data['Signal_Line'] = data['MACD'].ewm(span=9, adjust=False).mean()
    
    delta = data['close'].diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(window=14).mean()
    avg_loss = pd.Series(loss).rolling(window=14).mean()
    rs = avg_gain / avg_loss
    data['RSI'] = 100 - (100 / (1 + rs))
    
    stoch = ta.momentum.StochasticOscillator(data['high'], data['low'], data['close'])
    data['Stoch_K'] = stoch.stoch()
    data['Stoch_D'] = stoch.stoch_signal()

    # 볼륨 평균 (30틱)
    data['Volume_Avg30'] = data['volume'].rolling(window=30).mean()

    # 포지션 추적 및 설정
    position = None
    entry_data = {}
    results = []
    
    # 준비 트리거 초기화
    first_trigger_active = False
    second_trigger_active = False

    max_profit_row = None
    min_profit_row = None
    max_profit_value = None

    for index, row in data.iterrows():
        if position is None:
            # 첫 번째 트리거: 스토캐스틱 K, D가 과매도 구간에 있을 때 롱 포지션 준비
            if row['Stoch_K'] < 20 and row['Stoch_D'] < 20:
                first_trigger_active = True

            # 두 번째 트리거: RSI가 50을 돌파할 때
            if first_trigger_active and row['RSI'] > 50:
                second_trigger_active = True

            # 세 번째 트리거: MACD가 상승 추세로 진입할 때
            if second_trigger_active:

                if row['Stoch_K'] > 80 and row['Stoch_D'] > 80:  # 과매수일 때
                    first_trigger_active = False
                    second_trigger_active = False
                    continue  # 신호 무효화 후 다음 데이터로 이동

                if row['MACD'] > row['Signal_Line'] and row['volume'] > row['Volume_Avg30']:
                    position = 'Long'
                    entry_time = row['timestamp']
                    entry_price = row['close']
                    position_size_btc = (position_size_usdt / entry_price) * leverage  # 레버리지 반영
                    entry_fee = (entry_price * position_size_btc * fee_rate) * leverage  # 레버리지 반영된 수수료

                    # 전저점을 SL로 설정 (함수 사용)
                    sl = find_previous_low(data, index)
                    tp = entry_price + (tp_rate / leverage) * (entry_price - sl)  # 레버리지 반영된 TP 설정

                    entry_data = {
                        "Position": position,
                        "Entry_RSI": row['RSI'],
                        "Entry_MACD": row['MACD'],
                        "Entry_Signal_Line": row['Signal_Line'],
                        "Entry_Time": entry_time,
                        "Entry_Price": entry_price,
                        "SL": sl,
                        "TP": tp
                    }

                    # 최대 수익 기록 초기화
                    max_profit_row = row
                    min_profit_row = row
                    max_profit_value = 0

                    first_trigger_active = False
                    second_trigger_active = False

            # 숏 포지션 준비
            elif row['Stoch_K'] > 80 and row['Stoch_D'] > 80:
                first_trigger_active = True

            # 숏 포지션 두 번째 트리거: RSI가 50 아래로 내려갈 때
            if first_trigger_active and row['RSI'] < 50:
                second_trigger_active = True

            # 세 번째 트리거: MACD가 하락 추세일 때 숏 포지션 진입
            if second_trigger_active:

                    # 트리거 무효화 조건: K, D가 다시 과매도/과매수 구간에 있으면 초기화
                if row['Stoch_K'] < 20 and row['Stoch_D'] < 20:  # 과매도일 때
                    first_trigger_active = False
                    second_trigger_active = False
                    continue  # 신호 무효화 후 다음 데이터로 이동

                if row['MACD'] < row['Signal_Line'] and row['volume'] > row['Volume_Avg30']:
                    position = 'Short'
                    entry_time = row['timestamp']
                    entry_price = row['close']
                    position_size_btc = (position_size_usdt / entry_price) * leverage  # 레버리지 반영
                    entry_fee = (entry_price * position_size_btc * fee_rate) * leverage  # 레버리지 반영된 수수료

                    # 전고점을 SL로 설정 (함수 사용)
                    sl = find_previous_high(data, index)
                    tp = entry_price - (tp_rate / leverage) * (sl - entry_price)  # 레버리지 반영된 TP 설정

                    entry_data = {
                        "Position": position,
                        "Entry_RSI": row['RSI'],
                        "Entry_MACD": row['MACD'],
                        "Entry_Signal_Line": row['Signal_Line'],
                        "Entry_Time": entry_time,
                        "Entry_Price": entry_price,
                        "SL": sl,
                        "TP": tp
                    }

                    max_profit_row = row
                    min_profit_row = row
                    max_profit_value = 0

                    first_trigger_active = False
                    second_trigger_active = False

        # 롱 포지션 청산 조건
        elif position == 'Long':
            exit_price = row['close']
            exit_fee = (exit_price * position_size_btc * fee_rate) * leverage  # 레버리지 반영된 수수료
            profit_loss = leverage * ((exit_price - entry_price) * position_size_btc - (entry_fee + exit_fee))  # 레버리지 반영된 수익

            # 최대 수익 기록 (포지션 중 실제 가격 상승이 있었을 때만 계산)
            if row['high'] > entry_price:  # 실제로 가격 상승이 있었을 때만 최대 수익 계산
                potential_profit = leverage * ((row['high'] - entry_price) * position_size_btc - (entry_fee + row['high'] * position_size_btc * fee_rate))
                max_profit_value = max(max_profit_value, potential_profit)
                max_profit_row = row

            # 청산 시점에서 수익이 최대 수익과 같다면, 최대 수익 값과 동일하게 설정
            if row['timestamp'] == max_profit_row['timestamp']:
                max_profit_value = profit_loss

            if row['low'] <= sl or row['high'] >= tp:
                results.append({
                    "Position": position,
                    "Entry_RSI": entry_data['Entry_RSI'],
                    "Exit_RSI": row['RSI'],
                    "Max_Profit_RSI": max_profit_row['RSI'],
                    "Entry_MACD": entry_data['Entry_MACD'],
                    "Exit_MACD": row['MACD'],
                    "Max_Profit_MACD": max_profit_row['MACD'],
                    "Entry_Signal_Line": entry_data['Entry_Signal_Line'],
                    "Exit_Signal_Line": row['Signal_Line'],
                    "Max_Profit_Signal_Line": max_profit_row['Signal_Line'],
                    "Entry_Time": entry_data['Entry_Time'],
                    "Entry_Price": entry_data['Entry_Price'],
                    "Exit_Time": row['timestamp'],
                    "Exit_Price": exit_price,
                    "Profit_Loss": profit_loss,
                    "Max_Profit_Value": max_profit_value,
                    "Max_Profit_Time": max_profit_row['timestamp']
                })
                position = None
                max_profit_row = None

        # 숏 포지션 청산 조건
        elif position == 'Short':
            exit_price = row['close']
            exit_fee = (exit_price * position_size_btc * fee_rate) * leverage  # 레버리지 반영된 수수료
            profit_loss = leverage * ((entry_price - exit_price) * position_size_btc - (entry_fee + exit_fee))  # 레버리지 반영된 수익

            # 최대 수익 기록 (포지션 중 실제 가격 하락이 있었을 때만 계산)
            if row['low'] < entry_price:  # 실제로 가격 하락이 있었을 때만 최대 수익 계산
                potential_profit = leverage * ((entry_price - row['low']) * position_size_btc - (entry_fee + row['low'] * position_size_btc * fee_rate))
                max_profit_value = max(max_profit_value, potential_profit)
                max_profit_row = row

            # 청산 시점에서 수익이 최대 수익과 같다면, 최대 수익 값과 동일하게 설정
            if row['timestamp'] == max_profit_row['timestamp']:
                max_profit_value = profit_loss

            if row['high'] >= sl or row['low'] <= tp:
                results.append({
                    "Position": position,
                    "Entry_RSI": entry_data['Entry_RSI'],
                    "Exit_RSI": row['RSI'],
                    "Max_Profit_RSI": min_profit_row['RSI'],
                    "Entry_MACD": entry_data['Entry_MACD'],
                    "Exit_MACD": row['MACD'],
                    "Max_Profit_MACD": min_profit_row['MACD'],
                    "Entry_Signal_Line": entry_data['Entry_Signal_Line'],
                    "Exit_Signal_Line": row['Signal_Line'],
                    "Max_Profit_Signal_Line": min_profit_row['Signal_Line'],
                    "Entry_Time": entry_data['Entry_Time'],
                    "Entry_Price": entry_data['Entry_Price'],
                    "Exit_Time": row['timestamp'],
                    "Exit_Price": exit_price,
                    "Profit_Loss": profit_loss,
                    "Max_Profit_Value": max_profit_value,
                    "Max_Profit_Time": min_profit_row['timestamp']
                })
                position = None
                min_profit_row = None


    # 결과를 DataFrame으로 변환
    results_df = pd.DataFrame(results)
    print(results_df)

    # 양수인 경우의 개수
    positive = results_df[results_df['Max_Profit_Value'] > 0]
    negative = results_df[results_df['Max_Profit_Value'] <= 0]
    num_positive_max_profit = len(positive)
    num_negative_max_profit = len(negative)
    total = sum(positive['Max_Profit_Value']) + sum(negative['Max_Profit_Value'])

    # 실제 수익
    positive_real = results_df[results_df['Profit_Loss'] > 0]
    negative_real = results_df[results_df['Profit_Loss'] <= 0]
    num_positive_max_profit_real = len(positive_real)
    num_negative_max_profit_real = len(negative_real)
    total_real = sum(positive_real['Profit_Loss']) + sum(negative_real['Profit_Loss'])

    # 전체 개수
    total_entries = len(results_df)

    # 비율 계산
    positive_ratio = (num_positive_max_profit / total_entries) * 100
    positive_ratio_real = (num_positive_max_profit_real / total_entries) * 100

    # 결과 출력
    print("-------------------------------------------")
    print(f"포지션 오픈 성공 개수: {num_positive_max_profit}")
    print(f"포지션 오픈 실패 개수: {num_negative_max_profit}")
    print(f"성공 비율: {positive_ratio:.2f}%")
    print(f"최대 이익: {total}")
    print("-------------------------------------------")
    print(f"포지션 이익 개수: {num_positive_max_profit_real}")
    print(f"포지션 손해 개수: {num_negative_max_profit_real}")
    print(f"이익 비율: {positive_ratio_real:.2f}%")
    print(f"손익합: {total_real}")

    # 첫 번째와 마지막 행의 날짜만 추출
    first_date = data['timestamp'].iloc[0].date()
    last_date = data['timestamp'].iloc[-1].date()

    # 두 날짜의 차이 계산
    date_difference = (last_date - first_date).days + 1

    # 결과 출력
    print("-------------------------------------------")
    print(f"첫 번째 날짜: {first_date}, 마지막 날짜: {last_date}")
    print(f"데이터에 포함된 총 날짜 수: {date_difference}일")
    print(f"1일 평균 포지션 갯수 : {round(total_entries/date_difference, 1)}개/일")

    return results_df, data

if __name__ == "__main__":
    results_df,data = back_testing()
    # print(results_df)

