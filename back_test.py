from pymongo import MongoClient
import pandas as pd
import numpy as np
from docs.cal_chart import process_chart_data

# MongoDB에 접속
mongoClient = MongoClient("mongodb://localhost:27017")
database = mongoClient["bitcoin"]

# set_timevalue 값에 따라 적절한 차트 컬렉션 선택
chart_collections = {
    '1m': 'chart_1m',
    '3m': 'chart_3m',
    '5m': 'chart_5m',
    '15m': 'chart_15m',
    '1h': 'chart_1h',
    '30d': 'chart_30d'
}
set_timevalue = '5m'

if set_timevalue not in chart_collections:
    raise ValueError(f"Invalid time value: {set_timevalue}")

chart_collection = database[chart_collections[set_timevalue]] 

# MongoDB 쿼리 단계에서 필터링
start_date = pd.Timestamp('2024-11-11')
end_date = pd.Timestamp('2024-12-22')

data_cursor = chart_collection.find({
    "timestamp": {
        "$gte": start_date.to_pydatetime(),
        "$lte": end_date.to_pydatetime()
    }
}).sort("timestamp", -1)

# 최신 데이터부터 과거 데이터까지 모두 가져오기
data_cursor = chart_collection.find().sort("timestamp", -1)
data_list = list(data_cursor)

# MongoDB 데이터를 DataFrame으로 변환
df = pd.DataFrame(data_list)

# 타임스탬프를 datetime 형식으로 변환
df['timestamp'] = pd.to_datetime(df['timestamp'])

# 불필요한 ObjectId 필드 제거
if '_id' in df.columns:
    df.drop('_id', axis=1, inplace=True)

# 인덱스를 타임스탬프로 설정
# df.set_index('timestamp', inplace=True)

df = process_chart_data(df)


def analyze_macd_consecutive_drops(df, lookback=2, tp_long=400, sl_long=400, tp_short=400, sl_short=400, 
                                 fee_rate=0.00044, investment_usdt=1):
    """
    MACD 연속 변화 전략 분석 함수
    
    Parameters:
    df : DataFrame - 'timestamp', 'close', 'high', 'low', 'macd_diff' 컬럼 포함
    lookback : int - 몇 단계 이전까지 비교할지 설정
    tp_long : float - 롱 포지션 이익실현 지점 (BTC 가격 변동폭)
    sl_long : float - 롱 포지션 손절 지점 (BTC 가격 변동폭)
    tp_short : float - 숏 포지션 이익실현 지점 (BTC 가격 변동폭)
    sl_short : float - 숏 포지션 손절 지점 (BTC 가격 변동폭)
    fee_rate : float - 거래 수수료율 (기본값: 0.011%)
    investment_usdt : float - 목표 투자금액 (USDT)
    """
    MIN_BTC = 0.001  # 최소 BTC 주문 수량
    
    # 먼저 데이터를 시간순으로 정렬
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    results = {
        'long_win': 0, 'long_loss': 0,
        'short_win': 0, 'short_loss': 0,
        'total_long_profit': 0,
        'total_long_loss': 0,
        'total_short_profit': 0,
        'total_short_loss': 0,
        'total_fees': 0,
        'max_profit': float('-inf'),
        'max_loss': float('inf'),
        'all_trades': []
    }
    
    debug_info = []
    in_position = False
    position_type = None
    entry_price = 0
    entry_index = 0
    
    for i in range(lookback, len(df)):
        current = df['macd_diff'].iloc[i]
        prev_values = [df['macd_diff'].iloc[i-j] for j in range(1, lookback+1)]
        current_price = df['close'].iloc[i]
        
        # 현재 가격에서 0.001 BTC의 USDT 가치 계산
        min_investment_usdt = MIN_BTC * current_price
        # 실제 투자금액 결정 (목표 투자금액과 최소 투자금액 중 큰 값)
        actual_investment = max(investment_usdt, min_investment_usdt)
        
        debug_point = {
            'timestamp': df['timestamp'].iloc[i],
            'current_macd': current,
            'prev_values': prev_values,
            'close_price': current_price,
            'actual_investment': actual_investment
        }
        
        if not in_position:
            # 이전 값과의 차이 계산
            prev_macd = df['macd_diff'].iloc[i-1]
            current = df['macd_diff'].iloc[i]
            macd_change = current - prev_macd
            
            debug_point['macd_change'] = macd_change
            
                
            # MACD 변화량이 10 이상일 때만 거래
            if abs(macd_change) >= 35:
                if macd_change < 0:  # MACD가 크게 하락
                    in_position = True
                    position_type = 'short'
                    entry_price = current_price
                    # 진입 수수료 계산 (USDT)
                    entry_fee = actual_investment * fee_rate
                    results['total_fees'] += entry_fee
                    debug_point['action'] = f'Enter Short with {actual_investment:.6f} USDT (Fee: {entry_fee:.6f} USDT)'
                elif macd_change > 0:  # MACD가 크게 상승
                    in_position = True
                    position_type = 'long'
                    entry_price = current_price
                    # 진입 수수료 계산 (USDT)
                    entry_fee = actual_investment * fee_rate
                    results['total_fees'] += entry_fee
                    debug_point['action'] = f'Enter Long with {actual_investment:.6f} USDT (Fee: {entry_fee:.6f} USDT)'
        
        elif in_position:
            high_diff = df['high'].iloc[i] - entry_price
            low_diff = df['low'].iloc[i] - entry_price
            
            if position_type == 'long':
                if high_diff >= tp_long:
                    # BTC 가격 변동을 USDT 수익으로 변환
                    profit_usdt = (tp_long / entry_price) * actual_investment
                    exit_fee = actual_investment * fee_rate
                    profit_after_fees = profit_usdt - (2 * exit_fee)  # 진입/청산 수수료
                    
                    results['long_win'] += 1
                    results['total_long_profit'] += profit_after_fees
                    results['all_trades'].append(profit_after_fees)
                    results['max_profit'] = max(results['max_profit'], profit_after_fees)
                    results['total_fees'] += exit_fee
                    in_position = False
                    debug_point['action'] = f'Long Win +{profit_after_fees:.6f} USDT (Fee: {exit_fee:.6f} USDT)'
                elif low_diff <= -sl_long:
                    # BTC 가격 변동을 USDT 손실로 변환
                    loss_usdt = (sl_long / entry_price) * actual_investment
                    exit_fee = actual_investment * fee_rate
                    loss_after_fees = -(loss_usdt + (2 * exit_fee))  # 진입/청산 수수료
                    
                    results['long_loss'] += 1
                    results['total_long_loss'] += loss_after_fees
                    results['all_trades'].append(loss_after_fees)
                    results['max_loss'] = min(results['max_loss'], loss_after_fees)
                    results['total_fees'] += exit_fee
                    in_position = False
                    debug_point['action'] = f'Long Loss {loss_after_fees:.6f} USDT (Fee: {exit_fee:.6f} USDT)'
            elif position_type == 'short':
                if low_diff <= -tp_short:
                    # BTC 가격 변동을 USDT 수익으로 변환
                    profit_usdt = (tp_short / entry_price) * actual_investment
                    exit_fee = actual_investment * fee_rate
                    profit_after_fees = profit_usdt - (2 * exit_fee)  # 진입/청산 수수료
                    
                    results['short_win'] += 1
                    results['total_short_profit'] += profit_after_fees
                    results['all_trades'].append(profit_after_fees)
                    results['max_profit'] = max(results['max_profit'], profit_after_fees)
                    results['total_fees'] += exit_fee
                    in_position = False
                    debug_point['action'] = f'Short Win +{profit_after_fees:.6f} USDT (Fee: {exit_fee:.6f} USDT)'
                elif high_diff >= sl_short:
                    # BTC 가격 변동을 USDT 손실로 변환
                    loss_usdt = (sl_short / entry_price) * actual_investment
                    exit_fee = actual_investment * fee_rate
                    loss_after_fees = -(loss_usdt + (2 * exit_fee))  # 진입/청산 수수료
                    
                    results['short_loss'] += 1
                    results['total_short_loss'] += loss_after_fees
                    results['all_trades'].append(loss_after_fees)
                    results['max_loss'] = min(results['max_loss'], loss_after_fees)
                    results['total_fees'] += exit_fee
                    in_position = False
                    debug_point['action'] = f'Short Loss {loss_after_fees:.6f} USDT (Fee: {exit_fee:.6f} USDT)'
        
        debug_point['in_position'] = in_position
        debug_point['position_type'] = position_type
        debug_info.append(debug_point)
    
    # 결과 집계
    results['total_trades'] = results['long_win'] + results['long_loss'] + results['short_win'] + results['short_loss']
    
    # 수익/손실 계산
    results['total_long_net'] = results['total_long_profit'] + results['total_long_loss']
    results['total_short_net'] = results['total_short_profit'] + results['total_short_loss']
    results['total_profit_only'] = results['total_long_profit'] + results['total_short_profit']
    results['total_loss_only'] = results['total_long_loss'] + results['total_short_loss']
    results['net_profit'] = results['total_profit_only'] + results['total_loss_only']
    
    if results['total_trades'] > 0:
        results['win_rate'] = (results['long_win'] + results['short_win']) / results['total_trades'] * 100
        results['avg_profit_per_trade'] = results['net_profit'] / results['total_trades']
    
    # 처음 10개의 중요 시그널 출력
    print("\n처음 10개의 중요 시그널:")
    signal_count = 0
    for info in debug_info:
        if 'action' in info:
            print(f"\n시간: {info['timestamp']}")
            print(f"현재 MACD: {info['current_macd']:.6f}")
            print(f"이전 값들: {[f'{x:.6f}' for x in info['prev_values']]}")
            print(f"행동: {info['action']}")
            print(f"가격: {info['close_price']}")
            print(f"실제 투자금액: {info.get('actual_investment', 0):.6f} USDT")
            signal_count += 1
            if signal_count >= 10:
                break
    
    print(f"\n수익성 분석 (목표 투자금액: {investment_usdt} USDT, 최소 BTC: {MIN_BTC}):")
    print(f"설정값: TP롱 {tp_long}, SL롱 {sl_long}, TP숏 {tp_short}, SL숏 {sl_short}")
    print(f"총 거래 횟수: {results['total_trades']}")
    print(f"롱 포지션: 성공 {results['long_win']}, 실패 {results['long_loss']}")
    print(f"숏 포지션: 성공 {results['short_win']}, 실패 {results['short_loss']}")
    print(f"전체 승률: {results.get('win_rate', 0):.2f}%")
    print("\n수익/손실 내역 (USDT):")
    print(f"총 수수료 지출: -{results['total_fees']:.6f}")
    print(f"롱 포지션 수익: +{results['total_long_profit']:.6f}")
    print(f"롱 포지션 손실: {results['total_long_loss']:.6f}")
    print(f"롱 포지션 순수익: {results['total_long_net']:.6f}")
    print(f"숏 포지션 수익: +{results['total_short_profit']:.6f}")
    print(f"숏 포지션 손실: {results['total_short_loss']:.6f}")
    print(f"숏 포지션 순수익: {results['total_short_net']:.6f}")
    print(f"\n전체 수익: +{results['total_profit_only']:.6f}")
    print(f"전체 손실: {results['total_loss_only']:.6f}")
    print(f"최종 순수익: {results['net_profit']:.6f}")
    print(f"거래당 평균 수익: {results.get('avg_profit_per_trade', 0):.6f}")
    print(f"단일 최대 수익: {results['max_profit']:.6f}")
    print(f"단일 최대 손실: {results['max_loss']:.6f}")
    print(f"테스트 기간: {df['timestamp'].iloc[0]} ~ {df['timestamp'].iloc[-1]}")
    
    return results, debug_info

def analyze_histogram_ma_strategy(df, lookback=1, tp_long=200, sl_long=300, tp_short=200, sl_short=300, 
                               fee_rate=0.00044, investment_usdt=1):
    """
    히스토그램 차이값 MA의 방향성을 이용한 전략 분석
    
    Parameters:
    df : DataFrame - 'timestamp', 'close', 'high', 'low', 'histogram_diff_MA' 컬럼 포함
    lookback : int - 몇 단계 이전과 비교할지 설정
    """
    MIN_BTC = 0.001  # 최소 BTC 주문 수량
    
    # 먼저 데이터를 시간순으로 정렬
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    results = {
        'long_win': 0, 'long_loss': 0,
        'short_win': 0, 'short_loss': 0,
        'total_long_profit': 0,  # 롱 수익
        'total_long_loss': 0,    # 롱 손실
        'total_short_profit': 0,  # 숏 수익
        'total_short_loss': 0,    # 숏 손실
        'total_fees': 0,
        'max_profit': float('-inf'),
        'max_loss': float('inf'),
        'all_trades': []
    }
    
    in_position = False
    position_type = None
    entry_price = 0
    entry_index = 0
    
    for i in range(1, len(df)):  # 1부터 시작하여 이전값과 비교
        current_price = df['close'].iloc[i]
        
        # 현재 가격에서 0.001 BTC의 USDT 가치 계산
        min_investment_usdt = MIN_BTC * current_price
        # 실제 투자금액 결정 (목표 투자금액과 최소 투자금액 중 큰 값)
        actual_investment = max(investment_usdt, min_investment_usdt)
        
        current_ma = df['histogram_diff_MA'].iloc[i]
        lookback_ma = df['histogram_diff_MA'].iloc[i-lookback]
        
        if not in_position:
            # MA가 상승하면 롱 진입
            if current_ma > lookback_ma:
                in_position = True
                position_type = 'long'
                entry_price = current_price
                entry_index = i
                # 진입 수수료 계산
                entry_fee = actual_investment * fee_rate
                results['total_fees'] += entry_fee
                
            # MA가 하락하면 숏 진입
            elif current_ma < lookback_ma:
                in_position = True
                position_type = 'short'
                entry_price = current_price
                entry_index = i
                # 진입 수수료 계산
                entry_fee = actual_investment * fee_rate
                results['total_fees'] += entry_fee
        
        elif in_position:
            high_diff = df['high'].iloc[i] - entry_price
            low_diff = df['low'].iloc[i] - entry_price
            
            if position_type == 'long':
                if high_diff >= tp_long:
                    # BTC 가격 변동을 USDT 수익으로 변환
                    profit_usdt = (tp_long / entry_price) * actual_investment
                    exit_fee = actual_investment * fee_rate
                    profit_after_fees = profit_usdt - (2 * exit_fee)
                    
                    results['long_win'] += 1
                    results['total_long_profit'] += profit_after_fees
                    results['all_trades'].append(profit_after_fees)
                    results['max_profit'] = max(results['max_profit'], profit_after_fees)
                    results['total_fees'] += exit_fee
                    in_position = False
                    
                elif low_diff <= -sl_long:
                    # BTC 가격 변동을 USDT 손실로 변환
                    loss_usdt = (sl_long / entry_price) * actual_investment
                    exit_fee = actual_investment * fee_rate
                    loss_after_fees = -(loss_usdt + (2 * exit_fee))
                    
                    results['long_loss'] += 1
                    results['total_long_loss'] += loss_after_fees
                    results['all_trades'].append(loss_after_fees)
                    results['max_loss'] = min(results['max_loss'], loss_after_fees)
                    results['total_fees'] += exit_fee
                    in_position = False
                    
            elif position_type == 'short':
                if low_diff <= -tp_short:
                    # BTC 가격 변동을 USDT 수익으로 변환
                    profit_usdt = (tp_short / entry_price) * actual_investment
                    exit_fee = actual_investment * fee_rate
                    profit_after_fees = profit_usdt - (2 * exit_fee)
                    
                    results['short_win'] += 1
                    results['total_short_profit'] += profit_after_fees
                    results['all_trades'].append(profit_after_fees)
                    results['max_profit'] = max(results['max_profit'], profit_after_fees)
                    results['total_fees'] += exit_fee
                    in_position = False
                    
                elif high_diff >= sl_short:
                    # BTC 가격 변동을 USDT 손실로 변환
                    loss_usdt = (sl_short / entry_price) * actual_investment
                    exit_fee = actual_investment * fee_rate
                    loss_after_fees = -(loss_usdt + (2 * exit_fee))
                    
                    results['short_loss'] += 1
                    results['total_short_loss'] += loss_after_fees
                    results['all_trades'].append(loss_after_fees)
                    results['max_loss'] = min(results['max_loss'], loss_after_fees)
                    results['total_fees'] += exit_fee
                    in_position = False
    
    # 결과 집계
    results['total_trades'] = results['long_win'] + results['long_loss'] + results['short_win'] + results['short_loss']
    results['total_profit_only'] = results['total_long_profit'] + results['total_short_profit']
    results['total_loss_only'] = results['total_long_loss'] + results['total_short_loss']
    results['net_profit'] = results['total_profit_only'] + results['total_loss_only']
    
    if results['total_trades'] > 0:
        results['win_rate'] = (results['long_win'] + results['short_win']) / results['total_trades'] * 100
        results['avg_profit_per_trade'] = results['net_profit'] / results['total_trades']
    
    print("\n=== 히스토그램 MA 전략 분석 결과 ===")
    print(f"설정값: TP롱/숏 {tp_long}/{tp_short}, SL롱/숏 {sl_long}/{sl_short}")
    print(f"총 거래 횟수: {results['total_trades']}")
    print(f"롱 포지션: 성공 {results['long_win']}, 실패 {results['long_loss']}")
    print(f"숏 포지션: 성공 {results['short_win']}, 실패 {results['short_loss']}")
    print(f"전체 승률: {results.get('win_rate', 0):.2f}%")
    print("\n수익/손실 내역 (USDT):")
    print(f"총 수수료 지출: -{results['total_fees']:.6f}")
    print(f"롱 포지션 수익: +{results['total_long_profit']:.6f}")
    print(f"롱 포지션 손실: {results['total_long_loss']:.6f}")
    print(f"숏 포지션 수익: +{results['total_short_profit']:.6f}")
    print(f"숏 포지션 손실: {results['total_short_loss']:.6f}")
    print(f"\n전체 수익: +{results['total_profit_only']:.6f}")
    print(f"전체 손실: {results['total_loss_only']:.6f}")
    print(f"최종 순수익: {results['net_profit']:.6f}")
    print(f"거래당 평균 수익: {results.get('avg_profit_per_trade', 0):.6f}")
    print(f"단일 최대 수익: {results['max_profit']:.6f}")
    print(f"단일 최대 손실: {results['max_loss']:.6f}")
    print(f"테스트 기간: {df['timestamp'].iloc[0]} ~ {df['timestamp'].iloc[-1]}")

    return results

def analyze_di_histogram_strategy(df, lookback=2, tp_long=200, sl_long=300, tp_short=200, sl_short=300, 
                                 fee_rate=0.00044, investment_usdt=1):
    """
    DI 기울기 히스토그램의 연속적인 변화를 이용한 전략
    
    Parameters:
    df : DataFrame - 'timestamp', 'close', 'high', 'low', 'DI_slope_diff' 컬럼 포함
    lookback : int - 연속 상승/하락을 확인할 기간 수
    """
    MIN_BTC = 0.001
    
    # 데이터 시간순 정렬
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    results = {
        'long_win': 0, 'long_loss': 0,
        'short_win': 0, 'short_loss': 0,
        'total_long_profit': 0,
        'total_long_loss': 0,
        'total_short_profit': 0,
        'total_short_loss': 0,
        'total_fees': 0,
        'max_profit': float('-inf'),
        'max_loss': float('inf'),
        'all_trades': []
    }
    
    in_position = False
    position_type = None
    entry_price = 0
    entry_index = 0
    
    for i in range(lookback, len(df)):
        current_price = df['close'].iloc[i]
        min_investment_usdt = MIN_BTC * current_price
        actual_investment = max(investment_usdt, min_investment_usdt)
        
        # 최근 lookback+1개의 히스토그램 값 가져오기
        histogram_values = [df['DI_slope_diff'].iloc[i-j] for j in range(lookback+1)]
        
        # 연속 상승/하락 확인
        is_increasing = True
        is_decreasing = True
        
        for j in range(lookback):
            if histogram_values[j] <= histogram_values[j+1]:
                is_increasing = False
            if histogram_values[j] >= histogram_values[j+1]:
                is_decreasing = False
        
        if not in_position:
            if is_increasing:  # 연속 상승
                in_position = True
                position_type = 'long'
                entry_price = current_price
                entry_index = i
                entry_fee = actual_investment * fee_rate
                results['total_fees'] += entry_fee
                
            elif is_decreasing:  # 연속 하락
                in_position = True
                position_type = 'short'
                entry_price = current_price
                entry_index = i
                entry_fee = actual_investment * fee_rate
                results['total_fees'] += entry_fee
        
        elif in_position:
            high_diff = df['high'].iloc[i] - entry_price
            low_diff = df['low'].iloc[i] - entry_price
            
            if position_type == 'long':
                if high_diff >= tp_long:
                    profit_usdt = (tp_long / entry_price) * actual_investment
                    exit_fee = actual_investment * fee_rate
                    profit_after_fees = profit_usdt - (2 * exit_fee)
                    
                    results['long_win'] += 1
                    results['total_long_profit'] += profit_after_fees
                    results['all_trades'].append(profit_after_fees)
                    results['max_profit'] = max(results['max_profit'], profit_after_fees)
                    results['total_fees'] += exit_fee
                    in_position = False
                    
                elif low_diff <= -sl_long:
                    loss_usdt = (sl_long / entry_price) * actual_investment
                    exit_fee = actual_investment * fee_rate
                    loss_after_fees = -(loss_usdt + (2 * exit_fee))
                    
                    results['long_loss'] += 1
                    results['total_long_loss'] += loss_after_fees
                    results['all_trades'].append(loss_after_fees)
                    results['max_loss'] = min(results['max_loss'], loss_after_fees)
                    results['total_fees'] += exit_fee
                    in_position = False
                    
            elif position_type == 'short':
                if low_diff <= -tp_short:
                    profit_usdt = (tp_short / entry_price) * actual_investment
                    exit_fee = actual_investment * fee_rate
                    profit_after_fees = profit_usdt - (2 * exit_fee)
                    
                    results['short_win'] += 1
                    results['total_short_profit'] += profit_after_fees
                    results['all_trades'].append(profit_after_fees)
                    results['max_profit'] = max(results['max_profit'], profit_after_fees)
                    results['total_fees'] += exit_fee
                    in_position = False
                    
                elif high_diff >= sl_short:
                    loss_usdt = (sl_short / entry_price) * actual_investment
                    exit_fee = actual_investment * fee_rate
                    loss_after_fees = -(loss_usdt + (2 * exit_fee))
                    
                    results['short_loss'] += 1
                    results['total_short_loss'] += loss_after_fees
                    results['all_trades'].append(loss_after_fees)
                    results['max_loss'] = min(results['max_loss'], loss_after_fees)
                    results['total_fees'] += exit_fee
                    in_position = False
    
    # 결과 집계
    results['total_trades'] = results['long_win'] + results['long_loss'] + results['short_win'] + results['short_loss']
    results['total_profit_only'] = results['total_long_profit'] + results['total_short_profit']
    results['total_loss_only'] = results['total_long_loss'] + results['total_short_loss']
    results['net_profit'] = results['total_profit_only'] + results['total_loss_only']
    
    if results['total_trades'] > 0:
        results['win_rate'] = (results['long_win'] + results['short_win']) / results['total_trades'] * 100
        results['avg_profit_per_trade'] = results['net_profit'] / results['total_trades']
    
    print(f"\n=== DI 히스토그램 전략 분석 결과 (연속 {lookback}회) ===")
    print(f"설정값: TP롱/숏 {tp_long}/{tp_short}, SL롱/숏 {sl_long}/{sl_short}")
    print(f"총 거래 횟수: {results['total_trades']}")
    print(f"롱 포지션: 성공 {results['long_win']}, 실패 {results['long_loss']}")
    print(f"숏 포지션: 성공 {results['short_win']}, 실패 {results['short_loss']}")
    print(f"전체 승률: {results.get('win_rate', 0):.2f}%")
    print("\n수익/손실 내역 (USDT):")
    print(f"총 수수료 지출: -{results['total_fees']:.6f}")
    print(f"롱 포지션 수익: +{results['total_long_profit']:.6f}")
    print(f"롱 포지션 손실: {results['total_long_loss']:.6f}")
    print(f"숏 포지션 수익: +{results['total_short_profit']:.6f}")
    print(f"숏 포지션 손실: {results['total_short_loss']:.6f}")
    print(f"\n전체 수익: +{results['total_profit_only']:.6f}")
    print(f"전체 손실: {results['total_loss_only']:.6f}")
    print(f"최종 순수익: {results['net_profit']:.6f}")
    print(f"거래당 평균 수익: {results.get('avg_profit_per_trade', 0):.6f}")
    print(f"단일 최대 수익: {results['max_profit']:.6f}")
    print(f"단일 최대 손실: {results['max_loss']:.6f}")
    print(f"테스트 기간: {df['timestamp'].iloc[0]} ~ {df['timestamp'].iloc[-1]}")

    
    return results


if __name__ == "__main__":

    # results = analyze_histogram_ma_strategy(df,lookback=1, tp_long=200, sl_long=300, tp_short=200, sl_short=300)

    # results = analyze_di_histogram_strategy(df, lookback=1)

    # TP/SL 값을 다르게 설정하여 테스트
    results, debug_info = analyze_macd_consecutive_drops(
        df, 
        lookback=2,
        tp_long=300,   # 롱 포지션 이익실현
        sl_long=400,   # 롱 포지션 손절
        tp_short=300,  # 숏 포지션 이익실현
        sl_short=400   # 숏 포지션 손절
    )

    pass