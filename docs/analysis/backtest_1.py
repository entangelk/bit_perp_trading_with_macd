import os
import pandas as pd
import numpy as np

def back_testing():
    # 현재 스크립트 디렉토리를 기준으로 데이터 파일 경로 설정
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(script_dir, "data", "bitcoin_chart_1m.csv")

    # 데이터 로드
    data = pd.read_csv(data_path)
    data['timestamp'] = pd.to_datetime(data['timestamp'])

    # 지표 계산 - MACD, SMA, RSI, 볼린저 밴드, 볼륨
    # MACD
    data['EMA12'] = data['close'].ewm(span=12, adjust=False).mean()
    data['EMA26'] = data['close'].ewm(span=26, adjust=False).mean()
    data['MACD'] = data['EMA12'] - data['EMA26']
    data['Signal_Line'] = data['MACD'].ewm(span=9, adjust=False).mean()

    # 이동평균선 (계산만 유지)
    data['SMA50'] = data['close'].rolling(window=50).mean()
    data['SMA200'] = data['close'].rolling(window=200).mean()

    # RSI
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

    # 수수료 설정 및 거래량 (USDT)
    fee_rate = 0.0006  # 0.06%
    position_size_usdt = 10000  # 거래량을 10000 USDT로 가정

    # 포지션 추적을 위한 설정
    position = None
    entry_data = {}
    results = []
    previous_macd = None
    max_price = -np.inf
    min_price = np.inf
    max_profit_row = None
    min_profit_row = None

    for index, row in data.iterrows():
        if position is None:
            # 롱 포지션 진입 조건
            if (row['MACD'] > 1 and
                row['Signal_Line'] > 0 and
                row['RSI'] > 55 and
                row['Bollinger_Percentage'] > 40 and
                row['volume'] > row['Volume_Avg50']):
                
                position = 'Long'
                entry_time = row['timestamp']
                entry_data = row
                entry_price = row['close']
                position_size_btc = position_size_usdt / entry_price
                entry_fee = entry_price * position_size_btc * fee_rate
                max_price = row['high']
                max_profit_row = row  # 초기값 설정

            # 숏 포지션 진입 조건
            elif (row['MACD'] < -9 and
                  row['Signal_Line'] < 0 and
                  row['RSI'] < 45 and
                  row['Bollinger_Percentage'] < 45 and
                  row['volume'] > row['Volume_Avg50']):
                
                position = 'Short'
                entry_time = row['timestamp']
                entry_data = row
                entry_price = row['close']
                position_size_btc = position_size_usdt / entry_price
                entry_fee = entry_price * position_size_btc * fee_rate
                min_price = row['low']
                min_profit_row = row  # 초기값 설정

        elif position == 'Long':
            # 최대 가격 및 지표 업데이트
            if row['high'] > max_price:
                max_price = row['high']
                max_profit_row = row  # 이 시점의 지표 값으로 업데이트
            
            exit_price = row['close']
            exit_fee = exit_price * position_size_btc * fee_rate
            profit_loss = (exit_price - entry_price) * position_size_btc - (entry_fee + exit_fee)
            
            # 수수료 반영된 최대 이익 계산
            max_profit_value = (max_price - entry_price) * position_size_btc - (entry_fee + max_price * position_size_btc * fee_rate)

            # 롱 포지션 청산 조건
            if (row['MACD'] < entry_data['MACD'] or row['RSI'] < 70 or row['Bollinger_Percentage'] < 50):
                results.append({
                    "Position": position,
                    "Entry_RSI": entry_data['RSI'],
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
                    "Max_Profit_Value": max_profit_value,
                    "Max_Profit_Time": max_profit_row['timestamp']
                })
                position = None
                max_price = -np.inf
                max_profit_row = None

        elif position == 'Short':
            # 최소 가격 및 지표 업데이트
            if row['low'] < min_price:
                min_price = row['low']
                min_profit_row = row  # 이 시점의 지표 값으로 업데이트
            
            exit_price = row['close']
            exit_fee = exit_price * position_size_btc * fee_rate
            profit_loss = (entry_price - exit_price) * position_size_btc - (entry_fee + exit_fee)
            
            # 수수료 반영된 최대 이익 계산
            max_profit_value = (entry_price - min_price) * position_size_btc - (entry_fee + min_price * position_size_btc * fee_rate)

            # 숏 포지션 청산 조건
            if (row['MACD'] > entry_data['MACD'] or row['RSI'] > 35 or row['Bollinger_Percentage'] > 50):
                results.append({
                    "Position": position,
                    "Entry_RSI": entry_data['RSI'],
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
                    "Max_Profit_Value": max_profit_value,
                    "Max_Profit_Time": min_profit_row['timestamp']
                })
                position = None
                min_price = np.inf
                min_profit_row = None

        # 이전 MACD 값 업데이트
        previous_macd = row['MACD']

    results_df = pd.DataFrame(results)
    print(results_df)

    return results_df

if __name__ == "__main__":
    results_df = back_testing()
    # DataFrame을 CSV 파일로 저장
    # results_df.to_csv("results.csv", index=False, encoding='utf-8')