import pandas as pd

def supertrend(df):
    """
    Determine Supertrend signal based on Trend changes.

    Parameters:
        df (DataFrame): DataFrame with 'UpperBand' and 'LowerBand'.

    Returns:
        str: 'Long', 'Short', or None.
    """
    # 마지막 두 개의 상태를 추적
    if len(df) < 2:
        raise ValueError("Not enough data to calculate signals.")

    # 이전 값과 현재 값의 상태에 따라 트렌드 갱신
    prev_upper = df['UpperBand'].iloc[-2]
    prev_lower = df['LowerBand'].iloc[-2]
    prev_close = df['close'].iloc[-2]

    curr_upper = df['UpperBand'].iloc[-1]
    curr_lower = df['LowerBand'].iloc[-1]
    curr_close = df['close'].iloc[-1]

    # 판별 조건
    if curr_close > prev_upper and prev_close <= prev_upper:
        return "Long"
    elif curr_close < prev_lower and prev_close >= prev_lower:
        return "Short"
    return None


# 밴드 값이 다른가? 데이터들이 조금씩 다름 이걸 맞춰야함

if __name__ == "__main__":
    # Provided data
    data = {
        'timestamp': [
            '2024-11-28 09:35:00', '2024-11-28 09:40:00', '2024-11-28 09:45:00',
            '2024-11-28 09:50:00', '2024-11-28 09:55:00'
        ],
        'close': [95396.7, 95272.3, 95268.7, 95177.6, 95029.9],
        'high': [95396.8, 95494.4, 95316.4, 95285.7, 95206.5],
        'low': [95278.5, 95250.0, 95225.1, 95176.4, 94992.4],
        'UpperBand': [96061.734976, 96098.820126, 95993.755925, 95951.197866, 95820.960387],
        'LowerBand': [94613.565024, 94547.744075, 94510.902134, 94377.939613, 94191.736717]
    }
    df = pd.DataFrame(data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)

    # Calculate Supertrend signals
    signal = supertrend(df)
    print(f"Latest Signal: {signal}")

