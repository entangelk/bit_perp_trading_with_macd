import os
import pandas as pd
import numpy as np
import sys

# 현재 파일이 위치한 경로의 상위 디렉토리를 모듈 경로에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# docs.get_chart 모듈을 임포트
from docs.get_chart import chart_update
from pymongo import MongoClient


def back_testing():

    chart_update()

    # 현재 스크립트 디렉토리를 기준으로 데이터 파일 경로 설정
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # data_path = os.path.join(script_dir, "data", "bitcoin_chart_1m.csv")
    data_path = os.path.join(script_dir, "data", "bitcoin_chart_3m.csv")


    # 데이터 로드
    data = pd.read_csv(data_path)
    data['timestamp'] = pd.to_datetime(data['timestamp'])


    # 몽고 db에서 데이터 로드
        # MongoDB에 접속
    mongoClient = MongoClient("mongodb://mongodb:27017")
    database = mongoClient["bitcoin"]
    chart_collection_1m = database['chart_1m']
    chart_collection_3m = database['chart_3m']

    # 1분봉 데이터를 MongoDB에서 로드
    # data_list = list(chart_collection_1m.find())  # MongoDB의 모든 데이터를 리스트로 변환
    data_list = list(chart_collection_3m.find())  # MongoDB의 모든 데이터를 리스트로 변환

        # 리스트가 비어있지 않을 경우, 데이터를 DataFrame으로 변환
    if data_list:
        # 데이터를 pandas DataFrame으로 변환
        data = pd.DataFrame(data_list)
        
        # MongoDB 데이터에는 `_id` 필드가 자동으로 포함되므로, 이를 제외하고 CSV로 저장
        if '_id' in data.columns:
            data.drop(columns=['_id'], inplace=True)

    # 옵션
    stop_loss_rate = 0.0001
    leverage = 1
    # 수수료 설정 및 거래량 (USDT)
    fee_rate = 0.0006  # 0.06%

    position_size_usdt = 10000  # 거래량을 10000 USDT로 가정



    # 지표 계산 - MACD, SMA, RSI, 볼린저 밴드, 볼륨
    # MACD
    data['EMA12'] = data['close'].ewm(span=12, adjust=False).mean()
    data['EMA26'] = data['close'].ewm(span=26, adjust=False).mean()
    data['MACD'] = data['EMA12'] - data['EMA26']
    data['Signal_Line'] = data['MACD'].ewm(span=9, adjust=False).mean()

    # 이동평균선 (계산만 유지)
    data['SMA50'] = data['close'].rolling(window=50).mean()
    data['SMA200'] = data['close'].rolling(window=200).mean()

    # RSI 계산은 유지
    delta = data['close'].diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(window=14).mean()
    avg_loss = pd.Series(loss).rolling(window=14).mean()
    rs = avg_gain / avg_loss
    data['RSI'] = 100 - (100 / (1 + rs))

    # 볼린저 밴드 (계산만 유지)
    data['SMA20'] = data['close'].rolling(window=20).mean()
    data['BB_stddev'] = data['close'].rolling(window=20).std()
    data['Upper_BB'] = data['SMA20'] + 2 * data['BB_stddev']
    data['Lower_BB'] = data['SMA20'] - 2 * data['BB_stddev']
    data['Bollinger_Percentage'] = (data['close'] - data['Lower_BB']) / (data['Upper_BB'] - data['Lower_BB']) * 100

    # 볼륨 평균
    data['Volume_Avg50'] = data['volume'].rolling(window=50).mean()



    # 포지션 추적을 위한 설정
    position = None
    entry_data = {}
    results = []
    previous_macd = None
    max_price = -np.inf
    min_price = np.inf
    max_profit_row = None
    min_profit_row = None

    # 이전 틱의 MACD 값을 구해서 새로운 열로 추가
    data['previous_MACD'] = data['MACD'].shift(1)

    for index, row in data.iterrows():
        if position is None:
            # 롱 포지션 진입 조건
            if (row['MACD'] > 400 
                and row['Signal_Line'] > 50 
                and row['volume'] > row['Volume_Avg50'] 
                # and row['Bollinger_Percentage'] > 40
                ):
                
                position = 'Long'
                entry_time = row['timestamp']
                entry_data = row
                entry_price = row['close']
                position_size_btc = position_size_usdt / entry_price
                entry_fee = entry_price * position_size_btc * fee_rate
                max_price = row['high']
                max_profit_row = row  # 초기값 설정


                # 롱 포지션 스탑로스 조건 (2% 손실)
                stop_loss_threshold_long = entry_price * (1 - (stop_loss_rate/ leverage)) # 롱 포지션의 스탑로스 가격



            # 숏 포지션 진입 조건
            elif (row['MACD'] < -150 
                  and row['Signal_Line'] < -50 
                  and row['volume'] > row['Volume_Avg50'] 
                #   and row['Bollinger_Percentage'] < 45
                  ):
                
                position = 'Short'
                entry_time = row['timestamp']
                entry_data = row
                entry_price = row['close']
                position_size_btc = position_size_usdt / entry_price
                entry_fee = entry_price * position_size_btc * fee_rate
                min_price = row['low']
                min_profit_row = row  # 초기값 설정
                # 숏 포지션 스탑로스 조건 (2% 손실)
                stop_loss_threshold_short = entry_price * (1 + (stop_loss_rate/ leverage)) # 숏 포지션의 스탑로스 가격
        elif position == 'Long':
            # 롱 포지션에서 최대 가격 및 지표 업데이트
            if row['high'] > max_price:
                max_price = row['high']  # 최대 가격 업데이트
                max_profit_row = row  # 이 시점의 지표 값으로 업데이트
            
            exit_price = row['close']
            exit_fee = exit_price * position_size_btc * fee_rate
            profit_loss = (exit_price - entry_price) * position_size_btc - (entry_fee + exit_fee)
            
            # 수수료 반영된 최대 이익 계산 (포지션이 열려 있는 동안 최대 가격과 비교)
            max_profit_value = (max_price - entry_price) * position_size_btc - (entry_fee + max_price * position_size_btc * fee_rate)

            # 롱 포지션 청산 조건
            if (
                row['RSI'] >= 85 
                or row['MACD'] >= 300 
                or row['Signal_Line'] >= 200 
                or row['close'] <= stop_loss_threshold_long
                or (row['previous_MACD'] is not None and row['MACD'] < row['previous_MACD'])  # 이전 틱의 MACD 값보다 현재 값이 낮아졌을 때
                ):
                # 청산 로직 수행
                results.append({
                    "Position": position,
                    "Entry_RSI": entry_data['RSI'],  # RSI 값 유지
                    "Exit_RSI": row['RSI'],
                    "Max_Profit_RSI": max_profit_row['RSI'],
                    "Entry_MACD": entry_data['MACD'],
                    "Exit_MACD": row['MACD'],
                    "Max_Profit_MACD": max_profit_row['MACD'],
                    "Entry_Signal_Line": entry_data['Signal_Line'],
                    "Exit_Signal_Line": row['Signal_Line'],
                    "Max_Profit_Signal_Line": max_profit_row['Signal_Line'],
                    "Entry_Bollinger_Percentage": entry_data['Bollinger_Percentage'],
                    "Exit_Bollinger_Percentage": row['Bollinger_Percentage'],
                    "Max_Profit_Bollinger_Percentage": max_profit_row['Bollinger_Percentage'],
                    "Entry_Time": entry_time,
                    "Entry_Price": entry_price,
                    "Exit_Time": row['timestamp'],
                    "Exit_Price": exit_price,
                    "Profit_Loss": profit_loss,
                    "Max_Profit_Value": max_profit_value,  # 여기서 최대 이익을 기록
                    "Max_Profit_Time": max_profit_row['timestamp']
                })
                position = None
                max_price = -np.inf  # 다음 포지션을 위해 초기화
                max_profit_row = None


        elif position == 'Short':
            # 숏 포지션에서 최소 가격 및 지표 업데이트
            if row['low'] < min_price:
                min_price = row['low']  # 최소 가격 업데이트
                min_profit_row = row  # 이 시점의 지표 값으로 업데이트
            
            exit_price = row['close']
            exit_fee = exit_price * position_size_btc * fee_rate
            profit_loss = (entry_price - exit_price) * position_size_btc - (entry_fee + exit_fee)
            
            # 수수료 반영된 최대 이익 계산 (포지션이 열려 있는 동안 최소 가격과 비교)
            max_profit_value = (entry_price - min_price) * position_size_btc - (entry_fee + min_price * position_size_btc * fee_rate)

            # 숏 포지션 청산 조건
            if (
                row['RSI'] <= 30 
                or row['MACD'] <= -300 
                or row['Signal_Line'] <= -200 
                or row['close'] >= stop_loss_threshold_short
                or (row['previous_MACD'] is not None and row['MACD'] > row['previous_MACD'])  # 이전 틱의 MACD 값보다 현재 값이 높아졌을 때
                ):
                # 청산 로직 수행
                results.append({
                    "Position": position,
                    "Entry_RSI": entry_data['RSI'],  # RSI 값 유지
                    "Exit_RSI": row['RSI'],
                    "Max_Profit_RSI": min_profit_row['RSI'],
                    "Entry_MACD": entry_data['MACD'],
                    "Exit_MACD": row['MACD'],
                    "Max_Profit_MACD": min_profit_row['MACD'],
                    "Entry_Signal_Line": entry_data['Signal_Line'],
                    "Exit_Signal_Line": row['Signal_Line'],
                    "Max_Profit_Signal_Line": min_profit_row['Signal_Line'],
                    "Entry_Bollinger_Percentage": entry_data['Bollinger_Percentage'],
                    "Exit_Bollinger_Percentage": row['Bollinger_Percentage'],
                    "Max_Profit_Bollinger_Percentage": min_profit_row['Bollinger_Percentage'],
                    "Entry_Time": entry_time,
                    "Entry_Price": entry_price,
                    "Exit_Time": row['timestamp'],
                    "Exit_Price": exit_price,
                    "Profit_Loss": profit_loss,
                    "Max_Profit_Value": max_profit_value,  # 여기서 최대 이익을 기록
                    "Max_Profit_Time": min_profit_row['timestamp']
                })
                position = None
                min_price = np.inf  # 다음 포지션을 위해 초기화
                min_profit_row = None


        previous_macd = row['MACD']

    results_df = pd.DataFrame(results)
    print(results_df)

    # 양수인 경우의 개수
    positive = results_df[results_df['Max_Profit_Value'] > 0]
    negative = results_df[results_df['Max_Profit_Value'] < 0]
    num_positive_max_profit = len(positive)
    num_negative_max_profit = len(negative)
    total = sum(positive['Max_Profit_Value']) + sum(negative['Max_Profit_Value'])

    # 실제 수익
    positive_real = results_df[results_df['Profit_Loss'] > 0]
    negative_real = results_df[results_df['Profit_Loss'] < 0]
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
    first_date = data['timestamp'].iloc[0].date()  # 첫 번째 날짜
    last_date = data['timestamp'].iloc[-1].date()  # 마지막 날짜

    # 두 날짜의 차이 계산
    date_difference = (last_date - first_date).days + 1  # 1을 더해서 첫날도 포함

    # 결과 출력
    print("-------------------------------------------")

    print(f"첫 번째 날짜: {first_date}, 마지막 날짜: {last_date}")
    print(f"데이터에 포함된 총 날짜 수: {date_difference}일")
    print(f"1일 평균 포지션 갯수 : {round(total_entries/date_difference, 1)}개/일")
    return results_df

if __name__ == "__main__":
    results_df = back_testing()
    # DataFrame을 CSV 파일로 저장
    # results_df.to_csv("results.csv", index=False, encoding='utf-8')
