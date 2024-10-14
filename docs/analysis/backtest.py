import os
import pandas as pd


def back_testing():
    # Get the current script's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Construct the relative path to your data file
    data_path = os.path.join(script_dir, "data", "bitcoin_chart_1m.csv")

    # Load the data
    data = pd.read_csv(data_path)

    data['timestamp'] = pd.to_datetime(data['timestamp'])

    # Calculate indicators
    data['SMA20'] = data['close'].rolling(window=20).mean()
    data['STD20'] = data['close'].rolling(window=20).std()
    data['Bollinger_Upper'] = data['SMA20'] + (data['STD20'] * 2)
    data['Bollinger_Lower'] = data['SMA20'] - (data['STD20'] * 2)
    data['Bollinger_Percentage'] = ((data['close'] - data['Bollinger_Lower']) / 
                                (data['Bollinger_Upper'] - data['Bollinger_Lower'])) * 100

    # RSI calculation
    rsi_period = 14
    delta = data['close'].diff(1)
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=rsi_period, min_periods=1).mean()
    avg_loss = loss.rolling(window=rsi_period, min_periods=1).mean()
    rs = avg_gain / avg_loss
    data['RSI'] = 100 - (100 / (1 + rs))

    # MACD calculation
    data['EMA12'] = data['close'].ewm(span=12, adjust=False).mean()
    data['EMA26'] = data['close'].ewm(span=26, adjust=False).mean()
    data['MACD'] = data['EMA12'] - data['EMA26']
    data['Signal_Line'] = data['MACD'].ewm(span=9, adjust=False).mean()

    # Initialize backtest variables
    transaction_fee = 0.0006  # 0.06% fee
    initial_balance = 10000  # starting balance
    balance = initial_balance
    position = None
    entry_price = 0
    results = []

    # Backtest loop with balance tracking
    for i in range(len(data)):
        row = data.iloc[i]

        # Long Position Entry Conditions
        if position is None:
            if (row['RSI'] > 55 and row['Bollinger_Percentage'] > 75 and 
                row['MACD'] > row['Signal_Line'] and row['MACD'] > 0 and 
                row['volume'] > data['volume'].rolling(window=50).mean().iloc[i]):
                position = 'Long'
                entry_price = row['close']
                entry_time = row['timestamp']
                entry_rsi = row['RSI']
                entry_macd = row['MACD']
                entry_signal_line = row['Signal_Line']
                entry_bollinger_perc = row['Bollinger_Percentage']

        # Short Position Entry Conditions
            elif (row['RSI'] < 45 and row['Bollinger_Percentage'] < 0 and 
                row['MACD'] < row['Signal_Line'] and row['MACD'] < -5 and 
                row['volume'] > data['volume'].rolling(window=50).mean().iloc[i]):
                position = 'Short'
                entry_price = row['close']
                entry_time = row['timestamp']
                entry_rsi = row['RSI']
                entry_macd = row['MACD']
                entry_signal_line = row['Signal_Line']
                entry_bollinger_perc = row['Bollinger_Percentage']

        # Long Position Exit Conditions
        elif position == 'Long':
            if (row['RSI'] < 50 or row['Signal_Line'] > 25 or row['MACD'] > 25):
                exit_price = row['close']
                # Calculate adjusted profit/loss after applying fee
                adjusted_entry_price = entry_price * (1 + transaction_fee)
                adjusted_exit_price = exit_price * (1 - transaction_fee)
                profit_loss = adjusted_exit_price - adjusted_entry_price
                balance += profit_loss
                
                # Identify the max profit point during the trade period
                max_price = data.loc[data['timestamp'] > entry_time, 'high'].max()
                max_profit_value = max_price - adjusted_entry_price
                max_profit_time = data[data['high'] == max_price]['timestamp'].values[0]
                
                # Store max profit indicators
                max_profit_row = data[data['high'] == max_price].iloc[0]
                max_profit_rsi = max_profit_row['RSI']
                max_profit_macd = max_profit_row['MACD']
                max_profit_signal_line = max_profit_row['Signal_Line']
                max_profit_bollinger_perc = max_profit_row['Bollinger_Percentage']
                
                # Append results
                results.append({
                    "Position": position,
                    "Entry_RSI": entry_rsi,
                    "Exit_RSI": row['RSI'],
                    "Max_Profit_RSI": max_profit_rsi,
                    "Entry_MACD": entry_macd,
                    "Exit_MACD": row['MACD'],
                    "Max_Profit_MACD": max_profit_macd,
                    "Entry_Signal_Line": entry_signal_line,
                    "Exit_Signal_Line": row['Signal_Line'],
                    "Max_Profit_Signal_Line": max_profit_signal_line,
                    "Entry_Bollinger_Percentage": entry_bollinger_perc,
                    "Exit_Bollinger_Percentage": row['Bollinger_Percentage'],
                    "Max_Profit_Bollinger_Percentage": max_profit_bollinger_perc,
                    "Entry_Time": entry_time,
                    "Entry_Price": adjusted_entry_price,
                    "Exit_Time": row['timestamp'],
                    "Exit_Price": adjusted_exit_price,
                    "Profit_Loss": profit_loss,
                    "Max_Profit_Value": max_profit_value,
                    "Max_Profit_Time": max_profit_time
                })
                position = None

        # Short Position Exit Conditions
        elif position == 'Short':
            if (row['MACD'] < -25 or row['Signal_Line'] < -15):
                exit_price = row['close']
                # Calculate adjusted profit/loss after applying fee
                adjusted_entry_price = entry_price * (1 - transaction_fee)
                adjusted_exit_price = exit_price * (1 + transaction_fee)
                profit_loss = adjusted_entry_price - adjusted_exit_price
                balance += profit_loss
                
                # Identify the max profit point during the trade period
                min_price = data.loc[data['timestamp'] > entry_time, 'low'].min()
                max_profit_value = adjusted_entry_price - min_price
                max_profit_time = data[data['low'] == min_price]['timestamp'].values[0]
                
                # Store max profit indicators
                max_profit_row = data[data['low'] == min_price].iloc[0]
                max_profit_rsi = max_profit_row['RSI']
                max_profit_macd = max_profit_row['MACD']
                max_profit_signal_line = max_profit_row['Signal_Line']
                max_profit_bollinger_perc = max_profit_row['Bollinger_Percentage']
                
                # Append results
                results.append({
                    "Position": position,
                    "Entry_RSI": entry_rsi,
                    "Exit_RSI": row['RSI'],
                    "Max_Profit_RSI": max_profit_rsi,
                    "Entry_MACD": entry_macd,
                    "Exit_MACD": row['MACD'],
                    "Max_Profit_MACD": max_profit_macd,
                    "Entry_Signal_Line": entry_signal_line,
                    "Exit_Signal_Line": row['Signal_Line'],
                    "Max_Profit_Signal_Line": max_profit_signal_line,
                    "Entry_Bollinger_Percentage": entry_bollinger_perc,
                    "Exit_Bollinger_Percentage": row['Bollinger_Percentage'],
                    "Max_Profit_Bollinger_Percentage": max_profit_bollinger_perc,
                    "Entry_Time": entry_time,
                    "Entry_Price": adjusted_entry_price,
                    "Exit_Time": row['timestamp'],
                    "Exit_Price": adjusted_exit_price,
                    "Profit_Loss": profit_loss,
                    "Max_Profit_Value": max_profit_value,
                    "Max_Profit_Time": max_profit_time
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