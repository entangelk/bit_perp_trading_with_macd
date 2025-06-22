import pandas as pd
import numpy as np
import ta
import logging
from typing import Dict, Tuple

logger = logging.getLogger("technical_indicators")

class TechnicalIndicators:
    """정리된 기술적 지표 계산 클래스"""
    
    def __init__(self):
        # 지표 설정값들
        self.config = {
            # 추세 지표
            'trend': {
                'ema_fast': 12,
                'ema_slow': 26,
                'macd_signal': 9,
                'adx_period': 14,
                'di_period': 14
            },
            
            # 모멘텀 지표
            'momentum': {
                'rsi_period': 14,
                'stoch_k': 14,
                'stoch_d': 3,
                'williams_period': 14
            },
            
            # 변동성 지표
            'volatility': {
                'bb_period': 20,
                'bb_std': 2,
                'atr_period': 14
            },
            
            # 볼륨 지표
            'volume': {
                'vol_ma_period': 20,
                'obv_period': 10,
                'mfi_period': 14
            }
        }
    
    def calculate_trend_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """추세 지표 계산"""
        try:
            # EMA
            df['ema_fast'] = df['close'].ewm(span=self.config['trend']['ema_fast']).mean()
            df['ema_slow'] = df['close'].ewm(span=self.config['trend']['ema_slow']).mean()
            
            # MACD
            df['macd'] = df['ema_fast'] - df['ema_slow']
            df['macd_signal'] = df['macd'].ewm(span=self.config['trend']['macd_signal']).mean()
            df['macd_histogram'] = df['macd'] - df['macd_signal']
            
            # ADX와 DI 계산
            df = self._calculate_adx_di(df)
            
            # 추세 방향 (간단한 분류)
            df['trend_direction'] = np.where(df['ema_fast'] > df['ema_slow'], 1, -1)
            df['trend_strength'] = abs(df['macd_histogram'])
            
            logger.info("추세 지표 계산 완료")
            return df
            
        except Exception as e:
            logger.error(f"추세 지표 계산 중 오류: {e}")
            return df
    
    def calculate_momentum_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """모멘텀 지표 계산"""
        try:
            # RSI
            df['rsi'] = ta.momentum.rsi(df['close'], window=self.config['momentum']['rsi_period'])
            
            # Stochastic
            df['stoch_k'] = ta.momentum.stoch(
                df['high'], df['low'], df['close'], 
                window=self.config['momentum']['stoch_k']
            )
            df['stoch_d'] = df['stoch_k'].rolling(window=self.config['momentum']['stoch_d']).mean()
            
            # Williams %R
            df['williams_r'] = ta.momentum.williams_r(
                df['high'], df['low'], df['close'],
                lbp=self.config['momentum']['williams_period']
            )
            
            # 모멘텀 상태 분류
            df['momentum_state'] = np.select([
                df['rsi'] > 70,
                df['rsi'] < 30
            ], ['overbought', 'oversold'], default='neutral')
            
            logger.info("모멘텀 지표 계산 완료")
            return df
            
        except Exception as e:
            logger.error(f"모멘텀 지표 계산 중 오류: {e}")
            return df
    
    def calculate_volatility_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """변동성 지표 계산"""
        try:
            # Bollinger Bands
            bb_period = self.config['volatility']['bb_period']
            bb_std = self.config['volatility']['bb_std']
            
            df['bb_middle'] = df['close'].rolling(window=bb_period).mean()
            bb_std_dev = df['close'].rolling(window=bb_period).std()
            df['bb_upper'] = df['bb_middle'] + (bb_std_dev * bb_std)
            df['bb_lower'] = df['bb_middle'] - (bb_std_dev * bb_std)
            
            # 볼린저 밴드 포지션 (0-100%)
            df['bb_position'] = ((df['close'] - df['bb_lower']) / 
                               (df['bb_upper'] - df['bb_lower']) * 100).fillna(50)
            
            # ATR (Average True Range)
            df['atr'] = ta.volatility.average_true_range(
                df['high'], df['low'], df['close'],
                window=self.config['volatility']['atr_period']
            )
            
            # 정규화된 ATR (현재 가격 대비 %)
            df['atr_percent'] = (df['atr'] / df['close'] * 100).fillna(2)
            
            # 변동성 레벨 분류
            df['volatility_level'] = np.select([
                df['atr_percent'] > 3,
                df['atr_percent'] < 1
            ], ['high', 'low'], default='medium')
            
            logger.info("변동성 지표 계산 완료")
            return df
            
        except Exception as e:
            logger.error(f"변동성 지표 계산 중 오류: {e}")
            return df
    
    def calculate_volume_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """볼륨 지표 계산"""
        try:
            # 볼륨 이동평균
            vol_period = self.config['volume']['vol_ma_period']
            df['volume_ma'] = df['volume'].rolling(window=vol_period).mean()
            df['volume_ratio'] = (df['volume'] / df['volume_ma']).fillna(1)
            
            # OBV (On Balance Volume)
            df['obv'] = ta.volume.on_balance_volume(df['close'], df['volume'])
            df['obv_ma'] = df['obv'].rolling(window=self.config['volume']['obv_period']).mean()
            df['obv_trend'] = np.where(df['obv'] > df['obv_ma'], 1, -1)
            
            # MFI (Money Flow Index)
            df['mfi'] = ta.volume.money_flow_index(
                df['high'], df['low'], df['close'], df['volume'],
                window=self.config['volume']['mfi_period']
            )
            
            # 볼륨 상태 분류
            df['volume_state'] = np.select([
                df['volume_ratio'] > 1.5,
                df['volume_ratio'] < 0.7
            ], ['high', 'low'], default='normal')
            
            logger.info("볼륨 지표 계산 완료")
            return df
            
        except Exception as e:
            logger.error(f"볼륨 지표 계산 중 오류: {e}")
            return df
    
    def _calculate_adx_di(self, df: pd.DataFrame) -> pd.DataFrame:
        """ADX와 DI 계산 (내부 함수)"""
        try:
            # True Range 계산
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift(1))
            low_close = np.abs(df['low'] - df['close'].shift(1))
            true_range = np.maximum(high_low, np.maximum(high_close, low_close))
            
            # Directional Movement 계산
            plus_dm = np.where(
                (df['high'] - df['high'].shift(1)) > (df['low'].shift(1) - df['low']),
                np.maximum(df['high'] - df['high'].shift(1), 0), 0
            )
            minus_dm = np.where(
                (df['low'].shift(1) - df['low']) > (df['high'] - df['high'].shift(1)),
                np.maximum(df['low'].shift(1) - df['low'], 0), 0
            )
            
            period = self.config['trend']['di_period']
            
            # Smoothed 값들 계산
            atr_smooth = pd.Series(true_range).rolling(window=period).mean()
            plus_di_smooth = pd.Series(plus_dm).rolling(window=period).mean()
            minus_di_smooth = pd.Series(minus_dm).rolling(window=period).mean()
            
            # DI+ 및 DI- 계산
            df['di_plus'] = (plus_di_smooth / atr_smooth * 100).fillna(0)
            df['di_minus'] = (minus_di_smooth / atr_smooth * 100).fillna(0)
            
            # ADX 계산
            dx = abs(df['di_plus'] - df['di_minus']) / (df['di_plus'] + df['di_minus']) * 100
            df['adx'] = dx.rolling(window=period).mean().fillna(25)
            
            return df
            
        except Exception as e:
            logger.error(f"ADX/DI 계산 중 오류: {e}")
            return df
    
    def calculate_support_resistance(self, df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """지지/저항선 계산"""
        try:
            # 최근 period 기간의 고점/저점
            df['resistance'] = df['high'].rolling(window=period).max()
            df['support'] = df['low'].rolling(window=period).min()
            
            # 현재 가격의 지지/저항 대비 위치 (0-100%)
            df['price_position'] = ((df['close'] - df['support']) / 
                                  (df['resistance'] - df['support']) * 100).fillna(50)
            
            # 돌파 가능성 (지지/저항 근처일 때 높음)
            df['breakout_potential'] = np.where(
                (df['price_position'] > 90) | (df['price_position'] < 10), 
                'high', 'low'
            )
            
            logger.info("지지/저항선 계산 완료")
            return df
            
        except Exception as e:
            logger.error(f"지지/저항선 계산 중 오류: {e}")
            return df
    
    def calculate_all_indicators(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """모든 지표 통합 계산"""
        try:
            logger.info("기술적 지표 통합 계산 시작")
            
            # 입력 데이터 검증
            if df.empty or len(df) < 50:
                raise ValueError(f"데이터가 부족합니다. 최소 50개 캔들 필요, 현재: {len(df)}개")
            
            # 필수 컬럼 확인
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                raise ValueError(f"필수 컬럼이 없습니다: {missing_columns}")
            
            # 데이터 복사 (원본 보존)
            result_df = df.copy()
            
            # 각 카테고리별 지표 계산
            result_df = self.calculate_trend_indicators(result_df)
            result_df = self.calculate_momentum_indicators(result_df)
            result_df = self.calculate_volatility_indicators(result_df)
            result_df = self.calculate_volume_indicators(result_df)
            result_df = self.calculate_support_resistance(result_df)
            
            # NaN 값 처리
            result_df = result_df.fillna(method='bfill').fillna(method='ffill')
            
            # 설정값 반환 (참고용)
            config_info = {
                'indicators_calculated': [
                    'trend', 'momentum', 'volatility', 'volume', 'support_resistance'
                ],
                'config': self.config,
                'data_length': len(result_df),
                'calculation_timestamp': pd.Timestamp.now().isoformat()
            }
            
            logger.info(f"기술적 지표 통합 계산 완료: {len(result_df)}개 캔들")
            return result_df, config_info
            
        except Exception as e:
            logger.error(f"기술적 지표 통합 계산 중 오류: {e}")
            raise e

# 편의 함수들
def calculate_technical_indicators(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
    """기술적 지표 계산 편의 함수"""
    calculator = TechnicalIndicators()
    return calculator.calculate_all_indicators(df)

def get_latest_indicators(df: pd.DataFrame) -> Dict:
    """최신 지표값들만 추출"""
    try:
        if df.empty:
            return {}
        
        latest = df.iloc[-1]
        
        indicators = {
            # 추세
            'trend': {
                'ema_fast': float(latest.get('ema_fast', 0)),
                'ema_slow': float(latest.get('ema_slow', 0)),
                'macd': float(latest.get('macd', 0)),
                'macd_signal': float(latest.get('macd_signal', 0)),
                'macd_histogram': float(latest.get('macd_histogram', 0)),
                'adx': float(latest.get('adx', 25)),
                'di_plus': float(latest.get('di_plus', 25)),
                'di_minus': float(latest.get('di_minus', 25)),
                'trend_direction': int(latest.get('trend_direction', 0))
            },
            
            # 모멘텀
            'momentum': {
                'rsi': float(latest.get('rsi', 50)),
                'stoch_k': float(latest.get('stoch_k', 50)),
                'stoch_d': float(latest.get('stoch_d', 50)),
                'williams_r': float(latest.get('williams_r', -50)),
                'momentum_state': str(latest.get('momentum_state', 'neutral'))
            },
            
            # 변동성
            'volatility': {
                'bb_upper': float(latest.get('bb_upper', 0)),
                'bb_middle': float(latest.get('bb_middle', 0)),
                'bb_lower': float(latest.get('bb_lower', 0)),
                'bb_position': float(latest.get('bb_position', 50)),
                'atr': float(latest.get('atr', 0)),
                'atr_percent': float(latest.get('atr_percent', 2)),
                'volatility_level': str(latest.get('volatility_level', 'medium'))
            },
            
            # 볼륨
            'volume': {
                'volume_ma': float(latest.get('volume_ma', 0)),
                'volume_ratio': float(latest.get('volume_ratio', 1)),
                'obv': float(latest.get('obv', 0)),
                'obv_trend': int(latest.get('obv_trend', 0)),
                'mfi': float(latest.get('mfi', 50)),
                'volume_state': str(latest.get('volume_state', 'normal'))
            },
            
            # 지지/저항
            'support_resistance': {
                'support': float(latest.get('support', 0)),
                'resistance': float(latest.get('resistance', 0)),
                'price_position': float(latest.get('price_position', 50)),
                'breakout_potential': str(latest.get('breakout_potential', 'low'))
            },
            
            # 기본 정보
            'basic': {
                'current_price': float(latest.get('close', 0)),
                'volume': float(latest.get('volume', 0)),
                'timestamp': str(latest.name) if hasattr(latest, 'name') else ''
            }
        }
        
        return indicators
        
    except Exception as e:
        logger.error(f"최신 지표 추출 중 오류: {e}")
        return {}

# 테스트용 코드
if __name__ == "__main__":
    # 간단한 테스트
    import numpy as np
    
    # 더미 데이터 생성
    dates = pd.date_range('2024-01-01', periods=100, freq='15T')
    prices = 50000 + np.cumsum(np.random.randn(100) * 100)
    
    test_df = pd.DataFrame({
        'timestamp': dates,
        'open': prices + np.random.randn(100) * 10,
        'high': prices + np.abs(np.random.randn(100)) * 20,
        'low': prices - np.abs(np.random.randn(100)) * 20,
        'close': prices,
        'volume': np.random.randint(1000, 10000, 100)
    })
    
    test_df.set_index('timestamp', inplace=True)
    
    try:
        result_df, config = calculate_technical_indicators(test_df)
        latest_indicators = get_latest_indicators(result_df)
        
        print("✅ 지표 계산 테스트 성공!")
        print(f"계산된 지표 수: {len([col for col in result_df.columns if col not in test_df.columns])}")
        print(f"최신 RSI: {latest_indicators['momentum']['rsi']:.2f}")
        print(f"최신 MACD: {latest_indicators['trend']['macd']:.4f}")
        
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")