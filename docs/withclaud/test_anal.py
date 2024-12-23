import pandas as pd
import numpy as np
from datetime import datetime

import os

# Correct file path
file_path = os.path.join(os.path.dirname(__file__), 'data', 'BYBIT_BTCUSDT_P_5_e8295.csv')
print("Full resolved path:", file_path)

# Check if the file exists
print("File exists:", os.path.exists(file_path))

# Read the CSV if it exists
chart_df = pd.read_csv(file_path)
trades_df = pd.read_csv(os.path.join(os.path.dirname(__file__), 'data', 'Simplified_Multi_Indicator_Strategy_List_of_Trades_2024-12-22_6adec.csv'))

# 날짜/시간을 timestamp로 변환
trades_df['timestamp'] = pd.to_datetime(trades_df['날짜/시간']).view('int64') // 10**9

# 거래 데이터와 차트 데이터 매칭
matched_trades = []
for _, trade in trades_df.iterrows():
    chart_point = chart_df[chart_df['time'] == trade['timestamp']].iloc[0] if any(chart_df['time'] == trade['timestamp']) else None
    
    if chart_point is not None:
        matched_trades.append({
            'profit': trade['수익 USDT'],
            'type': trade['타입'],
            'RSI': chart_point['RSI'],
            'ADX': chart_point['ADX'],
            'DI+': chart_point['DI+'],
            'DI-': chart_point['DI-'],
            'MACD': chart_point['MACD'],
            'Histogram_Diff': chart_point['Histogram Difference']
        })

# DataFrame으로 변환
trades_analysis = pd.DataFrame(matched_trades)

# 승리/패배 그룹 분리
winning_trades = trades_analysis[trades_analysis['profit'] > 0]
losing_trades = trades_analysis[trades_analysis['profit'] < 0]

# 분석 함수
def analyze_indicators(df, group_name):
    print(f"\n=== {group_name} 분석 ({len(df)} 거래) ===")
    
    indicators = ['RSI', 'ADX', 'DI+', 'DI-', 'MACD', 'Histogram_Diff']
    for ind in indicators:
        print(f"\n{ind}:")
        stats = df[ind].describe()
        print(f"평균: {stats['mean']:.2f}")
        print(f"중앙값: {stats['50%']:.2f}")
        print(f"표준편차: {stats['std']:.2f}")
        print(f"최소: {stats['min']:.2f}")
        print(f"최대: {stats['max']:.2f}")
        
        # RSI와 ADX는 구간별 분포 추가
        if ind == 'RSI':
            print("\nRSI 구간 분포:")
            ranges = [(0,35), (35,45), (45,55), (55,65), (65,100)]
            for start, end in ranges:
                count = len(df[(df[ind] >= start) & (df[ind] < end)])
                pct = count / len(df) * 100 if len(df) > 0 else 0
                print(f"{start}-{end}: {count}건 ({pct:.1f}%)")
                
        if ind == 'ADX':
            print("\nADX 구간 분포:")
            ranges = [(0,15), (15,20), (20,25), (25,30), (30,100)]
            for start, end in ranges:
                count = len(df[(df[ind] >= start) & (df[ind] < end)])
                pct = count / len(df) * 100 if len(df) > 0 else 0
                print(f"{start}-{end}: {count}건 ({pct:.1f}%)")

print("=== 전체 거래 건수 ===")
print(f"총 매칭된 거래: {len(trades_analysis)}")
print(f"승리: {len(winning_trades)}")
print(f"패배: {len(losing_trades)}")

analyze_indicators(winning_trades, "승리 거래")
analyze_indicators(losing_trades, "패배 거래")