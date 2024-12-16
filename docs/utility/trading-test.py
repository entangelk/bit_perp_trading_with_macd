import pandas as pd
import numpy as np

def create_test_data():
    """테스트용 데이터 생성"""
    # 기본 데이터 프레임 생성 (100개 행)
    df = pd.DataFrame()
    
    # 기본 DI+, DI-, ADX 값 생성
    df['DI+'] = 25 + np.random.randn(100) * 5
    df['DI-'] = 25 + np.random.randn(100) * 5
    df['ADX'] = 20 + np.random.randn(100) * 3
    
    # 특정 시나리오 생성
    
    # 시나리오 1: 트리거 시그널 선행, 이후 포지션 시그널 (인덱스 20-25)
    df.loc[20:22, 'DI+'] = [24, 25, 26]  # 상승 크로스
    df.loc[20:22, 'DI-'] = [26, 25, 24]
    df.loc[20:22, 'ADX'] = [20, 19, 18]  # ADX 낮음
    
    # 시나리오 2: 포지션 시그널 선행, 이후 트리거 시그널 (인덱스 40-45)
    df.loc[40:42, 'DI+'] = [26, 24, 22]  # 하락 크로스
    df.loc[40:42, 'DI-'] = [24, 26, 28]
    df.loc[40:42, 'ADX'] = [18, 17, 16]  # ADX 낮음
    
    # RSI 추가 (청산 조건용)
    df['rsi'] = 50 + np.random.randn(100) * 10
    
    return df

# 모의 거래 함수들
class MockTradeEnvironment:
    def __init__(self):
        self.position = None
        self.position_side = None
        
    def fetch_investment_status(self):
        """현재 포지션 상태 반환"""
        if self.position is None:
            return None, '[]', None
        else:
            positions_json = [{'info': {'curRealisedPnl': '0', 'unrealisedPnl': '0'}}]
            return None, str(positions_json), None
    
    def get_position_amount(self, symbol):
        """현재 포지션 정보 반환"""
        if self.position is None:
            return 0, None, 0
        return 1, self.position_side, 100  # amount, side, avgPrice
    
    def execute_order(self, symbol, position, usdt_amount, leverage, stop_loss, take_profit):
        """주문 실행 모의"""
        print(f"모의 주문 실행: {position} 포지션")
        self.position = position
        self.position_side = "Buy" if position == "Long" else "Sell"
        return True
    
    def close_position(self, symbol):
        """포지션 종료 모의"""
        print(f"모의 포지션 종료: {self.position}")
        self.position = None
        self.position_side = None
        return True
def should_close_position(current_side, new_position):
    """포지션 청산 여부 확인"""
    return ((current_side == 'Long' and new_position == 'Short') or 
            (current_side == 'Short' and new_position == 'Long'))
def check_adx_di_trigger(df, di_threshold=2.5, adx_threshold=2.5, lookback=2):
    """
    ADX/DI 크로스오버 또는 근접 상태를 확인하여 매매 신호를 생성
    """
    if len(df) < lookback:
        return None
        
    # 현재 및 이전 값 가져오기
    current_di_plus = df['DI+'].iloc[-1]
    current_di_minus = df['DI-'].iloc[-1]
    prev_di_plus = df['DI+'].iloc[-2]
    prev_di_minus = df['DI-'].iloc[-2]
    
    current_adx = df['ADX'].iloc[-1]
    prev_adx = df['ADX'].iloc[-2]
    
    # 평균값 계산
    adx_avg = (current_adx + prev_adx) / 2
    current_di_avg = (current_di_plus + current_di_minus) / 2
    
    # DI 차이 계산
    di_diff = current_di_plus - current_di_minus
    prev_di_diff = prev_di_plus - prev_di_minus
    
    # 교차 상태 확인
    crossover_long = prev_di_diff < 0 and di_diff > 0
    crossover_short = prev_di_diff > 0 and di_diff < 0
    
    # DI 근접 상태 확인
    proximity_long = prev_di_diff < 0 and abs(di_diff) <= di_threshold
    proximity_short = prev_di_diff > 0 and abs(di_diff) <= di_threshold
    
    # 교차와 근접 상황에 따른 ADX 조건 확인
    if crossover_long or crossover_short:
        cross_point = min(current_di_plus, current_di_minus)
        adx_condition = abs(adx_avg - cross_point) <= adx_threshold
    else:
        adx_condition = abs(adx_avg - current_di_avg) <= adx_threshold
    
    # 트렌드 확인
    if lookback > 2:
        di_diffs = [df['DI+'].iloc[i] - df['DI-'].iloc[i] for i in range(-lookback, -1)]
        trend_consistent = all(d < 0 for d in di_diffs) if (crossover_long or proximity_long) else all(d > 0 for d in di_diffs)
    else:
        trend_consistent = True
    
    # 신호 생성
    if (crossover_long or proximity_long) and adx_condition and trend_consistent:
        return 'long'
    elif (crossover_short or proximity_short) and adx_condition and trend_consistent:
        return 'short'
    
    return None

def validate_di_difference(df, position):
    """DI 차이 검증"""
    if not position:
        return None
    di_diff = abs(df['DI+'].iloc[-1] - df['DI-'].iloc[-1])
    return position if di_diff >= 10 else None
    
def run_test():
    """테스트 실행"""
    # 테스트 데이터 생성
    df = create_test_data()
    mock_env = MockTradeEnvironment()
    
    # 전역 변수 초기화
    trigger_first_active = False
    trigger_first_count = 4
    position_first_active = False
    position_first_count = 2
    position_save = None
    
    print("테스트 시작...")
    
    # 데이터 순회하며 로직 테스트
    for i in range(2, len(df)-1):
        test_df = df.iloc[:i+1].copy()
        
        # 시그널 체크
        position = "Long" if test_df['DI+'].iloc[-1] > test_df['DI-'].iloc[-1] else "Short"
        trigger_signal = check_adx_di_trigger(test_df)
        
        print(f"\n타임스텝 {i}")
        print(f"DI+ = {test_df['DI+'].iloc[-1]:.2f}, DI- = {test_df['DI-'].iloc[-1]:.2f}")
        print(f"ADX = {test_df['ADX'].iloc[-1]:.2f}")
        print(f"포지션 시그널: {position}, 트리거 시그널: {trigger_signal}")
        
        # 포지션 상태 확인
        balance, positions_json, ledger = mock_env.fetch_investment_status()
        positions_flag = positions_json != '[]' and positions_json is not None
        
        if positions_flag:
            current_amount, current_side, current_avgPrice = mock_env.get_position_amount("BTCUSDT")
            current_side = 'Long' if current_side == 'Buy' else 'Short'
            
            if should_close_position(current_side, position) or test_df['rsi'].iloc[-1] > 75:
                mock_env.close_position("BTCUSDT")
                trigger_first_active = False
                position_first_active = False
        else:
            # 트리거 시그널 선행
            if trigger_signal:
                print("트리거 조건 충족")
                trigger_first_active = True
                trigger_first_count = 4
            
            if trigger_first_active:
                trigger_first_count -= 1
                print(f"트리거 카운트다운: {trigger_first_count}")
                
                if position:
                    validated_position = validate_di_difference(test_df, position)
                    if validated_position:
                        mock_env.execute_order("BTCUSDT", validated_position, 0.1, 5, 500, 500)
                        trigger_first_active = False
                
                if trigger_first_count <= 0:
                    trigger_first_active = False
            
            # 포지션 시그널 선행
            if position and not position_first_active and not trigger_first_active:
                validated_position = validate_di_difference(test_df, position)
                if validated_position:
                    print("포지션 시그널 발생")
                    position_first_active = True
                    position_first_count = 2
                    position_save = validated_position
            
            if position_first_active:
                position_first_count -= 1
                print(f"포지션 카운트다운: {position_first_count}")
                
                if trigger_signal:
                    if ((position_save == 'Long' and trigger_signal == 'long') or 
                        (position_save == 'Short' and trigger_signal == 'short')):
                        mock_env.execute_order("BTCUSDT", position_save, 0.1, 5, 500, 500)
                        position_first_active = False
                
                if position_first_count <= 0:
                    position_first_active = False
                    position_save = None
        
        # 시뮬레이션 속도 조절
        if i % 10 == 0:
            print("\n--- 10틱 경과 ---\n")

if __name__ == "__main__":
    run_test()
