import os
import pandas as pd
import ta  # make sure to install with 'pip install ta'

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

    # Calculate indicators using ta
    data['SMA20'] = ta.trend.sma_indicator(data['close'], window=CONFIG["bollinger_window"])
    data['Bollinger_Upper'] = data['SMA20'] + (data['close'].rolling(window=CONFIG["bollinger_window"]).std() * CONFIG["bollinger_std_dev"])
    data['Bollinger_Lower'] = data['SMA20'] - (data['close'].rolling(window=CONFIG["bollinger_window"]).std() * CONFIG["bollinger_std_dev"])
    data['Bollinger_Percentage'] = ((data['close'] - data['Bollinger_Lower']) /
                                    (data['Bollinger_Upper'] - data['Bollinger_Lower'])) * 100

    # RSI calculation
    data['RSI'] = ta.momentum.rsi(data['close'], window=CONFIG["rsi_period"])

    # MACD calculation
    macd = ta.trend.MACD(data['close'], 
                         window_slow=CONFIG["macd_slow"], 
                         window_fast=CONFIG["macd_fast"], 
                         window_sign=CONFIG["macd_signal"])
    data['MACD'] = macd.macd()
    data['Signal_Line'] = macd.macd_signal()

    # Volume condition
    data['Volume_Avg'] = data['volume'].rolling(window=CONFIG["volume_window"]).mean()

    # Initialize backtest variables
    balance = CONFIG["initial_balance"]
    position = None
    entry_price = 0
    results = []

    # Backtest loop
    for i in range(len(data)):
        row = data.iloc[i]

        # Long Position Entry Conditions
        if position is None:
            if (row['RSI'] > CONFIG["rsi_long_threshold"] and 
                row['Bollinger_Percentage'] > CONFIG["bollinger_long_threshold"] and 
                row['MACD'] > row['Signal_Line'] and 
                row['MACD'] > CONFIG["macd_long_threshold"] and 
                row['volume'] > row['Volume_Avg']):
                position = 'Long'
                entry_price = row['close']
                entry_time = row['timestamp']
                entry_rsi = row['RSI']
                entry_macd = row['MACD']
                entry_signal_line = row['Signal_Line']
                entry_bollinger_perc = row['Bollinger_Percentage']

        # Short Position Entry Conditions
            elif (row['RSI'] < CONFIG["rsi_short_threshold"] and 
                row['Bollinger_Percentage'] < CONFIG["bollinger_short_threshold"] and 
                row['MACD'] < row['Signal_Line'] and 
                row['MACD'] < CONFIG["macd_short_threshold"] and 
                row['volume'] > row['Volume_Avg']):
                position = 'Short'
                entry_price = row['close']
                entry_time = row['timestamp']
                entry_rsi = row['RSI']
                entry_macd = row['MACD']
                entry_signal_line = row['Signal_Line']
                entry_bollinger_perc = row['Bollinger_Percentage']

        # Long Position Exit Conditions
        elif position == 'Long':
            if (row['RSI'] < CONFIG["long_exit_rsi_threshold"] or 
                row['Signal_Line'] > CONFIG["long_exit_signal_line_threshold"] or 
                row['MACD'] > CONFIG["long_exit_macd_threshold"]):
                exit_price = row['close']
                adjusted_entry_price = entry_price * (1 + CONFIG["transaction_fee"])
                adjusted_exit_price = exit_price * (1 - CONFIG["transaction_fee"])
                profit_loss = adjusted_exit_price - adjusted_entry_price
                balance += profit_loss
                
                max_price = data.loc[data['timestamp'] > entry_time, 'high'].max()
                max_profit_value = max_price - adjusted_entry_price
                max_profit_row = data[data['high'] == max_price].iloc[0]
                
                results.append({
                    "Position": position,
                    "Entry_RSI": entry_rsi,
                    "Exit_RSI": row['RSI'],
                    "Max_Profit_RSI": max_profit_row['RSI'],
                    "Entry_MACD": entry_macd,
                    "Exit_MACD": row['MACD'],
                    "Max_Profit_MACD": max_profit_row['MACD'],
                    "Entry_Signal_Line": entry_signal_line,
                    "Exit_Signal_Line": row['Signal_Line'],
                    "Max_Profit_Signal_Line": max_profit_row['Signal_Line'],
                    "Entry_Bollinger_Percentage": entry_bollinger_perc,
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

        # Short Position Exit Conditions
        elif position == 'Short':
            if (row['MACD'] < CONFIG["short_exit_macd_threshold"] or 
                row['Signal_Line'] < CONFIG["short_exit_signal_line_threshold"]):
                exit_price = row['close']
                adjusted_entry_price = entry_price * (1 - CONFIG["transaction_fee"])
                adjusted_exit_price = exit_price * (1 + CONFIG["transaction_fee"])
                profit_loss = adjusted_entry_price - adjusted_exit_price
                balance += profit_loss
                
                min_price = data.loc[data['timestamp'] > entry_time, 'low'].min()
                max_profit_value = adjusted_entry_price - min_price
                max_profit_row = data[data['low'] == min_price].iloc[0]
                
                results.append({
                    "Position": position,
                    "Entry_RSI": entry_rsi,
                    "Exit_RSI": row['RSI'],
                    "Max_Profit_RSI": max_profit_row['RSI'],
                    "Entry_MACD": entry_macd,
                    "Exit_MACD": row['MACD'],
                    "Max_Profit_MACD": max_profit_row['MACD'],
                    "Entry_Signal_Line": entry_signal_line,
                    "Exit_Signal_Line": row['Signal_Line'],
                    "Max_Profit_Signal_Line": max_profit_row['Signal_Line'],
                    "Entry_Bollinger_Percentage": entry_bollinger_perc,
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

    # Convert results to DataFrame
    results_df = pd.DataFrame(results)

    # Show final results
    print(results_df)
    print("Final Balance:", balance)
    return results_df


if __name__ == "__main__":
    back_testing()
