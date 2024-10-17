import os
import pandas as pd
import ta  # make sure to install with 'pip install ta'
from ta.momentum import RSIIndicator
from ta.trend import MACD

# Configuration options for easy adjustment
CONFIG = {
    "rsi_period": 14,
    "rsi_long_threshold": 55,
    "rsi_short_threshold": 45,
    "bollinger_window": 20,
    "bollinger_std_dev": 2,
    "bollinger_long_threshold": 75,
    "bollinger_short_threshold": 0,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "macd_long_threshold": 0,
    "macd_short_threshold": -5,
    "volume_window": 50,
    "transaction_fee": 0.0006,
    "initial_balance": 10000,
    "long_exit_rsi_threshold": 50,
    "long_exit_signal_line_threshold": 25,
    "long_exit_macd_threshold": 25,
    "short_exit_macd_threshold": -25,
    "short_exit_signal_line_threshold": -15
}


def back_testing():
    # Get the current script's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Construct the relative path to your data file
    data_path = os.path.join(script_dir, "data", "bitcoin_chart_1m.csv")

    # Load the data
    data = pd.read_csv(data_path)
    data['timestamp'] = pd.to_datetime(data['timestamp'])

    # Bollinger Bands 계산
    data['SMA20'] = data['close'].rolling(window=CONFIG["bollinger_window"]).mean()
    data['Bollinger_Upper'] = data['SMA20'] + (data['close'].rolling(window=CONFIG["bollinger_window"]).std() * CONFIG["bollinger_std_dev"])
    data['Bollinger_Lower'] = data['SMA20'] - (data['close'].rolling(window=CONFIG["bollinger_window"]).std() * CONFIG["bollinger_std_dev"])
    data['Bollinger_Percentage'] = ((data['close'] - data['Bollinger_Lower']) /
                                    (data['Bollinger_Upper'] - data['Bollinger_Lower'])) * 100

    # RSI 계산
    rsi = RSIIndicator(data['close'], window=CONFIG["rsi_period"])
    data['RSI'] = rsi.rsi()

    # MACD 계산
    macd = MACD(data['close'], 
                window_slow=CONFIG["macd_slow"], 
                window_fast=CONFIG["macd_fast"], 
                window_sign=CONFIG["macd_signal"])
    data['MACD'] = macd.macd()
    data['Signal_Line'] = macd.macd_signal()

    # Volume 평균 계산
    data['Volume_Avg'] = data['volume'].rolling(window=CONFIG["volume_window"]).mean()


    # 초기 변수 설정

    balance = CONFIG["initial_balance"]
    position = None
    entry_price = 0
    results = []

    for i in range(len(data)):
        row = data.iloc[i]

        if position is None:
            if (row['RSI'] > CONFIG["rsi_long_threshold"] and 
                row['Bollinger_Percentage'] > CONFIG["bollinger_long_threshold"] and 
                row['MACD'] > row['Signal_Line'] and 
                row['MACD'] > CONFIG["macd_long_threshold"] and 
                row['volume'] > row['Volume_Avg']):
                position = 'Long'
                entry_price = row['close']
                entry_time = row['timestamp']
                entry_data = row.copy()
            elif (row['RSI'] < CONFIG["rsi_short_threshold"] and 
                row['Bollinger_Percentage'] < CONFIG["bollinger_short_threshold"] and 
                row['MACD'] < row['Signal_Line'] and 
                row['MACD'] < CONFIG["macd_short_threshold"] and 
                row['volume'] > row['Volume_Avg']):
                position = 'Short'
                entry_price = row['close']
                entry_time = row['timestamp']
                entry_data = row.copy()

        elif position == 'Long':
            if (row['RSI'] < CONFIG["long_exit_rsi_threshold"] or 
                row['Signal_Line'] > CONFIG["long_exit_signal_line_threshold"] or 
                row['MACD'] > CONFIG["long_exit_macd_threshold"]):
                exit_price = row['close']
                adjusted_entry_price = entry_price * (1 + CONFIG["transaction_fee"])
                adjusted_exit_price = exit_price * (1 - CONFIG["transaction_fee"])
                profit_loss = adjusted_exit_price - adjusted_entry_price
                balance += profit_loss
                
                # Improved max profit calculation for Long position
                trade_data = data[(data['timestamp'] >= entry_time) & (data['timestamp'] <= row['timestamp'])]
                max_price = trade_data['high'].max()
                max_profit_index = trade_data['high'].idxmax()
                max_profit_row = data.loc[max_profit_index]
                max_profit_value = max_price - adjusted_entry_price

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
                    "Entry_Price": adjusted_entry_price,
                    "Exit_Time": row['timestamp'],
                    "Exit_Price": adjusted_exit_price,
                    "Profit_Loss": profit_loss,
                    "Max_Profit_Value": max_profit_value,
                    "Max_Profit_Time": max_profit_row['timestamp']
                })
                position = None

        elif position == 'Short':
            if (row['MACD'] < CONFIG["short_exit_macd_threshold"] or 
                row['Signal_Line'] < CONFIG["short_exit_signal_line_threshold"]):
                exit_price = row['close']
                adjusted_entry_price = entry_price * (1 - CONFIG["transaction_fee"])
                adjusted_exit_price = exit_price * (1 + CONFIG["transaction_fee"])
                profit_loss = adjusted_entry_price - adjusted_exit_price
                balance += profit_loss
                
                # Improved max profit calculation for Short position
                trade_data = data[(data['timestamp'] >= entry_time) & (data['timestamp'] <= row['timestamp'])]
                min_price = trade_data['low'].min()
                max_profit_index = trade_data['low'].idxmin()
                max_profit_row = data.loc[max_profit_index]
                max_profit_value = adjusted_entry_price - min_price

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
                    "Entry_Price": adjusted_entry_price,
                    "Exit_Time": row['timestamp'],
                    "Exit_Price": adjusted_exit_price,
                    "Profit_Loss": profit_loss,
                    "Max_Profit_Value": max_profit_value,
                    "Max_Profit_Time": max_profit_row['timestamp']
                })
                position = None

    results_df = pd.DataFrame(results)
    print(results_df)
    print("Final Balance:", balance)
    return results_df

if __name__ == "__main__":
    back_testing()