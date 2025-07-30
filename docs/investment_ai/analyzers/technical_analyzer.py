import json
import re
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types
import sys
import os
import ta
from scipy import stats

# 상위 디렉토리의 모듈 import를 위한 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../'))

from docs.investment_ai.config import CONFIG, API_KEY, MODEL_PRIORITY
from docs.investment_ai.indicators.technical_indicators import calculate_technical_indicators, get_latest_indicators

# 🔧 새로 추가: 동적 timeframe 설정을 위한 import
from main_ai_new import TRADING_CONFIG, TIME_VALUES

# 로깅 설정
logger = logging.getLogger("enhanced_technical_analyzer")

class EnhancedTechnicalAnalyzer:
    """기술적 지표 분석 AI + 반전 신호 분석 - 통합 버전"""
    
    def __init__(self):
        # AI 모델 초기화 제거 - 실제 호출 시에만 초기화
        self.client = None
        self.model_name = None
        
        # 🔧 새로 추가: 동적 timeframe 설정
        self.get_timevalue = TRADING_CONFIG.get('set_timevalue', '1h')  # 기본값을 1h로 변경
        self.int_timevalue = TIME_VALUES.get(self.get_timevalue, 60)  # 기본값은 60분 (1시간)
        logger.info(f"동적 timeframe 설정: {self.get_timevalue} ({self.int_timevalue}분)")
        
        # 반전 분석 설정 (1시간봉 최적화)
        self.reversal_config = {
            'LINEAR_REG': {
                'LENGTH': 168,  # 1주일 (24h * 7d = 168h)
                'UPPER_MULTIPLIER': 2.0,
                'LOWER_MULTIPLIER': 2.0,
                'MIN_SLOPE_THRESHOLD': 0.0005,
                'MIN_TREND_DURATION': 24  # 1일 = 24시간
            },
            'DIVERGENCE': {
                'LOOKBACK_PERIOD': 120,  # 5일 (120시간)
                'MIN_PEAK_DISTANCE': 8,  # 8시간 간격
                'PRICE_THRESHOLD': 0.015,  # 1.5% 이상 움직임
                'INDICATOR_THRESHOLD': 8   # 지표 변화량 증가
            },
            'PATTERN': {
                'DOUBLE_TOP_BOTTOM_TOLERANCE': 0.02,  # 2%
                'MIN_PATTERN_BARS': 24,  # 최소 1일 (24시간)
                'MAX_PATTERN_BARS': 168  # 최대 1주일 (168시간)
            },
            'MOMENTUM': {
                'RSI_PERIOD': 14,
                'STOCH_K': 14,
                'STOCH_D': 3,
                'WILLIAMS_R': 14
            },
            'VOLUME': {
                'OBV_SMOOTHING': 12,  # 12시간 평활화
                'VOLUME_SMA': 24,     # 24시간 평균 볼륨
                'TREND_PERIOD': 48    # 2일간 볼륨 트렌드
            },
            'SUPPORT_RESISTANCE': {
                'LOOKBACK_PERIOD': 240,  # 10일 (240시간)
                'PIVOT_DISTANCE': 6,     # 6시간 간격
                'PROXIMITY_THRESHOLD': 0.015,  # 1.5% 이내를 근접으로 판단
                'RECENT_LEVELS_COUNT': 5  # 최근 5개 레벨 고려
            }
        }
    
    def get_chart_data(self, symbol='BTCUSDT', timeframe=None, limit=300):
        """차트 데이터 수집 (동적 timeframe 사용, 미완성 캔들 제외)"""
        try:
            # 🔧 수정: timeframe이 None이면 TRADING_CONFIG에서 가져오기
            if timeframe is None:
                timeframe = self.get_timevalue
            
            from pymongo import MongoClient
            
            mongoClient = MongoClient("mongodb://mongodb:27017")
            database = mongoClient["bitcoin"]
            
            # 🔧 수정: 동적 컬렉션 이름 생성
            chart_collections = {
                '1m': 'chart_1m',
                '3m': 'chart_3m', 
                '5m': 'chart_5m',
                '15m': 'chart_15m',
                '60m': 'chart_60m',  # 새로 추가
                '1h': 'chart_60m',   # 1h는 60m과 동일
                '30d': 'chart_30d'
            }
            
            if timeframe not in chart_collections:
                raise ValueError(f"지원하지 않는 시간봉: {timeframe}")
            
            chart_collection = database[chart_collections[timeframe]]
            
            # 분석에 필요한 완성된 캔들 수만큼 가져오기 위해 1개를 더 요청
            data_cursor = chart_collection.find().sort("timestamp", -1).limit(limit + 1)
            data_list = list(data_cursor)
            
            if not data_list:
                raise ValueError("차트 데이터가 없습니다")
            
            df = pd.DataFrame(data_list)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            if '_id' in df.columns:
                df.drop('_id', axis=1, inplace=True)
            
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)  # 시간순 정렬
            
            # --- 핵심 수정 사항 ---
            # 가장 최신 데이터는 미완성 캔들일 가능성이 높으므로 제거합니다.
            # iloc[:-1]은 마지막 행을 제외한 모든 행을 선택합니다.
            df = df.iloc[:-1]
            
            logger.info(f"완성된 차트 데이터 수집 완료: {len(df)}개 캔들 ({timeframe})")
            return df
            
        except Exception as e:
            logger.error(f"차트 데이터 수집 중 오류: {e}")
            return None
    
    def find_peaks_and_troughs(self, series: pd.Series, distance: int = None) -> Tuple[List[int], List[int]]:
        """피크와 골 찾기 (다이버전스 분석용) - 1시간봉 최적화"""
        try:
            # distance가 지정되지 않으면 config에서 가져오기
            if distance is None:
                distance = self.reversal_config['DIVERGENCE']['MIN_PEAK_DISTANCE']
                
            peaks = []
            troughs = []
            
            for i in range(distance, len(series) - distance):
                # 피크 찾기
                is_peak = True
                for j in range(i - distance, i + distance + 1):
                    if j != i and series.iloc[j] >= series.iloc[i]:
                        is_peak = False
                        break
                if is_peak:
                    peaks.append(i)
                
                # 골 찾기
                is_trough = True
                for j in range(i - distance, i + distance + 1):
                    if j != i and series.iloc[j] <= series.iloc[i]:
                        is_trough = False
                        break
                if is_trough:
                    troughs.append(i)
            
            return peaks, troughs
            
        except Exception as e:
            logger.error(f"피크/골 찾기 중 오류: {e}")
            return [], []
    
    def calculate_linear_regression_channel(self, df: pd.DataFrame) -> pd.DataFrame:
        """수정된 선형회귀 채널 계산"""
        try:
            length = self.reversal_config['LINEAR_REG']['LENGTH']
            upper_mult = self.reversal_config['LINEAR_REG']['UPPER_MULTIPLIER']
            lower_mult = self.reversal_config['LINEAR_REG']['LOWER_MULTIPLIER']
            
            # 결과 저장용 컬럼 초기화
            df['lr_slope'] = np.nan
            df['lr_intercept'] = np.nan
            df['lr_middle'] = np.nan
            df['lr_upper'] = np.nan
            df['lr_lower'] = np.nan
            df['lr_std'] = np.nan
            df['lr_trend_strength'] = np.nan
            df['lr_position'] = np.nan
            
            # 선형회귀 계산
            for i in range(length - 1, len(df)):
                # 최근 length개의 데이터 사용
                y_data = df['close'].iloc[i-length+1:i+1].values
                x_data = np.arange(length)
                
                # 선형회귀 계산
                slope, intercept, r_value, p_value, std_err = stats.linregress(x_data, y_data)
                
                # 현재 시점의 회귀선 값
                current_regression_value = intercept + slope * (length - 1)
                
                # 표준편차 계산 (잔차 기반)
                predicted_values = intercept + slope * x_data
                residuals = y_data - predicted_values
                std_dev = np.std(residuals)
                
                # 결과 저장
                df.loc[df.index[i], 'lr_slope'] = slope
                df.loc[df.index[i], 'lr_intercept'] = intercept
                df.loc[df.index[i], 'lr_middle'] = current_regression_value
                df.loc[df.index[i], 'lr_upper'] = current_regression_value + (std_dev * upper_mult)
                df.loc[df.index[i], 'lr_lower'] = current_regression_value - (std_dev * lower_mult)
                df.loc[df.index[i], 'lr_std'] = std_dev
                df.loc[df.index[i], 'lr_trend_strength'] = abs(r_value)
                
                # 현재 가격의 채널 내 위치 (0~1)
                channel_range = df.loc[df.index[i], 'lr_upper'] - df.loc[df.index[i], 'lr_lower']
                if channel_range > 0:
                    position = (df['close'].iloc[i] - df.loc[df.index[i], 'lr_lower']) / channel_range
                    df.loc[df.index[i], 'lr_position'] = max(0, min(1, position))
                
            logger.info("선형회귀 채널 계산 완료")
            return df
            
        except Exception as e:
            logger.error(f"선형회귀 채널 계산 중 오류: {e}")
            return df
    
    def detect_divergence(self, df: pd.DataFrame, price_col: str = 'close', 
                         indicator_col: str = 'rsi') -> pd.DataFrame:
        """다이버전스 감지"""
        try:
            lookback = self.reversal_config['DIVERGENCE']['LOOKBACK_PERIOD']
            min_distance = self.reversal_config['DIVERGENCE']['MIN_PEAK_DISTANCE']
            
            # 최근 데이터만 사용
            recent_df = df.tail(lookback).copy()
            
            # 피크와 골 찾기
            price_peaks, price_troughs = self.find_peaks_and_troughs(recent_df[price_col], min_distance)
            indicator_peaks, indicator_troughs = self.find_peaks_and_troughs(recent_df[indicator_col], min_distance)
            
            # 다이버전스 신호 초기화
            df['bullish_divergence'] = False
            df['bearish_divergence'] = False
            df['divergence_strength'] = 0
            
            # 강세 다이버전스 (가격은 하락, 지표는 상승)
            if len(price_troughs) >= 2 and len(indicator_troughs) >= 2:
                recent_price_troughs = [t for t in price_troughs if t >= len(recent_df) - 20]
                recent_indicator_troughs = [t for t in indicator_troughs if t >= len(recent_df) - 20]
                
                if len(recent_price_troughs) >= 2 and len(recent_indicator_troughs) >= 2:
                    p1, p2 = recent_price_troughs[-2], recent_price_troughs[-1]
                    i1, i2 = recent_indicator_troughs[-2], recent_indicator_troughs[-1]
                    
                    price_declining = recent_df[price_col].iloc[p2] < recent_df[price_col].iloc[p1]
                    indicator_rising = recent_df[indicator_col].iloc[i2] > recent_df[indicator_col].iloc[i1]
                    
                    if price_declining and indicator_rising:
                        current_idx = df.index[-1]
                        df.loc[current_idx, 'bullish_divergence'] = True
                        price_change = abs(recent_df[price_col].iloc[p2] - recent_df[price_col].iloc[p1]) / recent_df[price_col].iloc[p1]
                        indicator_change = abs(recent_df[indicator_col].iloc[i2] - recent_df[indicator_col].iloc[i1])
                        df.loc[current_idx, 'divergence_strength'] = min(price_change * 100, indicator_change)
            
            # 약세 다이버전스 (가격은 상승, 지표는 하락)
            if len(price_peaks) >= 2 and len(indicator_peaks) >= 2:
                recent_price_peaks = [p for p in price_peaks if p >= len(recent_df) - 20]
                recent_indicator_peaks = [p for p in indicator_peaks if p >= len(recent_df) - 20]
                
                if len(recent_price_peaks) >= 2 and len(recent_indicator_peaks) >= 2:
                    p1, p2 = recent_price_peaks[-2], recent_price_peaks[-1]
                    i1, i2 = recent_indicator_peaks[-2], recent_indicator_peaks[-1]
                    
                    price_rising = recent_df[price_col].iloc[p2] > recent_df[price_col].iloc[p1]
                    indicator_declining = recent_df[indicator_col].iloc[i2] < recent_df[indicator_col].iloc[i1]
                    
                    if price_rising and indicator_declining:
                        current_idx = df.index[-1]
                        df.loc[current_idx, 'bearish_divergence'] = True
                        price_change = abs(recent_df[price_col].iloc[p2] - recent_df[price_col].iloc[p1]) / recent_df[price_col].iloc[p1]
                        indicator_change = abs(recent_df[indicator_col].iloc[i2] - recent_df[indicator_col].iloc[i1])
                        df.loc[current_idx, 'divergence_strength'] = min(price_change * 100, indicator_change)
            
            return df
            
        except Exception as e:
            logger.error(f"다이버전스 감지 중 오류: {e}")
            return df
    
    def detect_double_patterns(self, df: pd.DataFrame) -> pd.DataFrame:
        """이중 천정/바닥 패턴 감지"""
        try:
            tolerance = self.reversal_config['PATTERN']['DOUBLE_TOP_BOTTOM_TOLERANCE']
            min_bars = self.reversal_config['PATTERN']['MIN_PATTERN_BARS']
            max_bars = self.reversal_config['PATTERN']['MAX_PATTERN_BARS']
            
            df['double_top'] = False
            df['double_bottom'] = False
            df['pattern_strength'] = 0
            
            if len(df) < min_bars * 2:
                return df
            
            # 최근 데이터에서 패턴 찾기
            recent_data = df.tail(max_bars)
            highs = recent_data['high']
            lows = recent_data['low']
            
            # 이중 천정 패턴
            high_peaks, _ = self.find_peaks_and_troughs(highs, 3)
            if len(high_peaks) >= 2:
                peak1_val = highs.iloc[high_peaks[-2]]
                peak2_val = highs.iloc[high_peaks[-1]]
                
                if abs(peak1_val - peak2_val) / peak1_val <= tolerance:
                    between_min = highs.iloc[high_peaks[-2]:high_peaks[-1]].min()
                    if (peak1_val - between_min) / peak1_val > tolerance:
                        current_idx = df.index[-1]
                        df.loc[current_idx, 'double_top'] = True
                        df.loc[current_idx, 'pattern_strength'] = 1 - abs(peak1_val - peak2_val) / peak1_val
            
            # 이중 바닥 패턴
            _, low_troughs = self.find_peaks_and_troughs(lows, 3)
            if len(low_troughs) >= 2:
                trough1_val = lows.iloc[low_troughs[-2]]
                trough2_val = lows.iloc[low_troughs[-1]]
                
                if abs(trough1_val - trough2_val) / trough1_val <= tolerance:
                    between_max = lows.iloc[low_troughs[-2]:low_troughs[-1]].max()
                    if (between_max - trough1_val) / trough1_val > tolerance:
                        current_idx = df.index[-1]
                        df.loc[current_idx, 'double_bottom'] = True
                        df.loc[current_idx, 'pattern_strength'] = 1 - abs(trough1_val - trough2_val) / trough1_val
            
            return df
            
        except Exception as e:
            logger.error(f"이중 패턴 감지 중 오류: {e}")
            return df
    
    def calculate_reversal_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """반전 신호 종합 계산"""
        try:
            # 1. 선형회귀 채널
            df = self.calculate_linear_regression_channel(df)
            
            # 2. 기본 모멘텀 지표들 (다이버전스 분석용)
            rsi_period = self.reversal_config['MOMENTUM']['RSI_PERIOD']
            df['reversal_rsi'] = ta.momentum.rsi(df['close'], window=rsi_period)
            df['reversal_stoch'] = ta.momentum.stoch(df['high'], df['low'], df['close'], window=14)
            df['reversal_williams'] = ta.momentum.williams_r(df['high'], df['low'], df['close'], lbp=14)
            
            # 3. 볼륨 지표들
            df['obv'] = ta.volume.on_balance_volume(df['close'], df['volume'])
            df['obv_smooth'] = df['obv'].rolling(window=self.reversal_config['VOLUME']['OBV_SMOOTHING']).mean()
            
            # 4. 다이버전스 분석 (여러 지표)
            momentum_indicators = ['reversal_rsi', 'reversal_stoch', 'reversal_williams']
            df['momentum_bullish_signals'] = 0
            df['momentum_bearish_signals'] = 0
            
            for indicator in momentum_indicators:
                if indicator in df.columns and not df[indicator].isna().all():
                    temp_df = self.detect_divergence(df.copy(), 'close', indicator)
                    
                    if len(temp_df) > 0 and temp_df['bullish_divergence'].iloc[-1]:
                        df.loc[df.index[-1], 'momentum_bullish_signals'] += 1
                    
                    if len(temp_df) > 0 and temp_df['bearish_divergence'].iloc[-1]:
                        df.loc[df.index[-1], 'momentum_bearish_signals'] += 1
            
            # 5. 볼륨 다이버전스
            df = self.detect_divergence(df, 'close', 'obv_smooth')
            df['volume_divergence_bullish'] = df['bullish_divergence']
            df['volume_divergence_bearish'] = df['bearish_divergence']
            
            # 6. 패턴 분석
            df = self.detect_double_patterns(df)
            
            # 7. 지지/저항 분석
            df = self.calculate_support_resistance_levels(df)
            
            logger.info("반전 지표 계산 완료")
            return df
            
        except Exception as e:
            logger.error(f"반전 지표 계산 중 오류: {e}")
            return df
    
    def calculate_support_resistance_levels(self, df: pd.DataFrame) -> pd.DataFrame:
        """지지/저항 레벨 계산"""
        try:
            lookback = min(self.reversal_config['SUPPORT_RESISTANCE']['LOOKBACK_PERIOD'], len(df))
            pivot_distance = self.reversal_config['SUPPORT_RESISTANCE']['PIVOT_DISTANCE']
            proximity_threshold = self.reversal_config['SUPPORT_RESISTANCE']['PROXIMITY_THRESHOLD']
            
            recent_data = df.tail(lookback)
            high_peaks, low_troughs = self.find_peaks_and_troughs(recent_data['close'], pivot_distance)
            
            if high_peaks and low_troughs:
                # 저항선과 지지선 계산
                resistance_levels = [recent_data['high'].iloc[i] for i in high_peaks[-5:]]
                support_levels = [recent_data['low'].iloc[i] for i in low_troughs[-5:]]
                
                current_resistance = np.mean(resistance_levels) if resistance_levels else recent_data['high'].max()
                current_support = np.mean(support_levels) if support_levels else recent_data['low'].min()
                
                current_price = df['close'].iloc[-1]
                resistance_distance = (current_resistance - current_price) / current_price
                support_distance = (current_price - current_support) / current_price
                
                df['resistance_level'] = current_resistance
                df['support_level'] = current_support
                df['resistance_distance'] = resistance_distance
                df['support_distance'] = support_distance
                
                # 반전 신호
                df['near_resistance'] = resistance_distance < proximity_threshold
                df['near_support'] = support_distance < proximity_threshold
                df['resistance_reversal'] = df['near_resistance'] & (df['close'] < df['close'].shift(1))
                df['support_reversal'] = df['near_support'] & (df['close'] > df['close'].shift(1))
            
            return df
            
        except Exception as e:
            logger.error(f"지지/저항 레벨 계산 중 오류: {e}")
            return df
    
    def calculate_technical_indicators(self, df):
        """기술적 지표 계산 - 새로운 정리된 코드 사용 + 반전 분석 추가"""
        try:
            # 기존 기술적 지표 계산
            processed_df, config_info = calculate_technical_indicators(df)
            
            # 반전 분석 추가
            processed_df = self.calculate_reversal_indicators(processed_df)
            
            logger.info("기술적 지표 + 반전 분석 계산 완료")
            return processed_df, config_info
            
        except Exception as e:
            logger.error(f"지표 계산 중 오류: {e}")
            # 백업: 기본 지표만 계산
            return self.calculate_basic_indicators(df)
    
    def calculate_basic_indicators(self, df):
        """기본 기술적 지표 계산 (백업용)"""
        try:
            import ta
            
            # 기본 지표들
            df['rsi'] = ta.momentum.rsi(df['close'], window=14)
            df['ema_20'] = df['close'].ewm(span=20).mean()
            df['ema_50'] = df['close'].ewm(span=50).mean()
            
            # MACD
            ema_12 = df['close'].ewm(span=12).mean()
            ema_26 = df['close'].ewm(span=26).mean()
            df['macd'] = ema_12 - ema_26
            df['macd_signal'] = df['macd'].ewm(span=9).mean()
            df['macd_histogram'] = df['macd'] - df['macd_signal']
            
            # Bollinger Bands
            df['bb_middle'] = df['close'].rolling(window=20).mean()
            bb_std = df['close'].rolling(window=20).std()
            df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
            df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
            df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower']) * 100
            
            logger.info("기본 기술적 지표 계산 완료")
            return df, {}
            
        except Exception as e:
            logger.error(f"기본 지표 계산 중 오류: {e}")
            return df, {}
    
    def extract_key_indicators(self, df, config_info):
        """AI 분석용 핵심 지표 추출 - 반전 분석 포함"""
        try:
            # 기존 지표 추출
            latest_indicators = get_latest_indicators(df)
            
            if not latest_indicators:
                raise ValueError("지표 추출 실패")
            
            # 동적 24시간 변동률 계산
            current_price = latest_indicators['basic']['current_price']
            price_change_24h = 0
            
            candles_per_24h = int(24 * 60 / self.int_timevalue)
            
            if len(df) >= candles_per_24h:
                price_24h_ago = float(df.iloc[-candles_per_24h]['close'])
                price_change_24h = ((current_price - price_24h_ago) / price_24h_ago * 100)
                logger.info(f"24시간 변동률 계산: {candles_per_24h}개 캔들 사용 ({self.get_timevalue})")
            
            # 반전 분석 데이터 추출
            latest = df.iloc[-1]
            
            # 강세 반전 신호들
            bullish_signals = []
            if latest.get('bullish_divergence', False):
                bullish_signals.append('price_momentum_divergence')
            if latest.get('double_bottom', False):
                bullish_signals.append('double_bottom_pattern')
            if latest.get('momentum_bullish_signals', 0) > 0:
                bullish_signals.append(f'momentum_divergence_{latest.get("momentum_bullish_signals", 0)}_indicators')
            if latest.get('volume_divergence_bullish', False):
                bullish_signals.append('volume_divergence')
            if latest.get('support_reversal', False):
                bullish_signals.append('support_level_bounce')
            if latest.get('lr_position', 0.5) < 0.2:
                bullish_signals.append('linear_regression_oversold')
            
            # 약세 반전 신호들
            bearish_signals = []
            if latest.get('bearish_divergence', False):
                bearish_signals.append('price_momentum_divergence')
            if latest.get('double_top', False):
                bearish_signals.append('double_top_pattern')
            if latest.get('momentum_bearish_signals', 0) > 0:
                bearish_signals.append(f'momentum_divergence_{latest.get("momentum_bearish_signals", 0)}_indicators')
            if latest.get('volume_divergence_bearish', False):
                bearish_signals.append('volume_divergence')
            if latest.get('resistance_reversal', False):
                bearish_signals.append('resistance_level_rejection')
            if latest.get('lr_position', 0.5) > 0.8:
                bearish_signals.append('linear_regression_overbought')
            
            # AI가 이해하기 쉬운 형태로 재구성 (기존 + 반전 분석)
            analysis_data = {
                'current_price': current_price,
                'price_change_24h': round(price_change_24h, 2),
                'volume': latest_indicators['basic']['volume'],
                'timestamp': latest_indicators['basic']['timestamp'],
                'timeframe_info': {
                    'timeframe': self.get_timevalue,
                    'minutes_per_candle': self.int_timevalue,
                    'candles_per_24h': candles_per_24h
                },
                
                # 기존 추세 분석
                'trend_indicators': {
                    'ema_fast': latest_indicators['trend']['ema_fast'],
                    'ema_slow': latest_indicators['trend']['ema_slow'],
                    'ema_signal': 'bullish' if latest_indicators['trend']['ema_fast'] > latest_indicators['trend']['ema_slow'] else 'bearish',
                    'macd': latest_indicators['trend']['macd'],
                    'macd_signal': latest_indicators['trend']['macd_signal'],
                    'macd_histogram': latest_indicators['trend']['macd_histogram'],
                    'macd_status': 'bullish' if latest_indicators['trend']['macd'] > latest_indicators['trend']['macd_signal'] else 'bearish',
                    'adx': latest_indicators['trend']['adx'],
                    'adx_strength': 'strong' if latest_indicators['trend']['adx'] > 25 else 'weak',
                    'di_plus': latest_indicators['trend']['di_plus'],
                    'di_minus': latest_indicators['trend']['di_minus'],
                    'di_signal': 'bullish' if latest_indicators['trend']['di_plus'] > latest_indicators['trend']['di_minus'] else 'bearish'
                },
                
                # 기존 모멘텀 분석
                'momentum_indicators': {
                    'rsi': latest_indicators['momentum']['rsi'],
                    'rsi_state': latest_indicators['momentum']['momentum_state'],
                    'stoch_k': latest_indicators['momentum']['stoch_k'],
                    'stoch_d': latest_indicators['momentum']['stoch_d'],
                    'stoch_signal': 'bullish' if latest_indicators['momentum']['stoch_k'] > latest_indicators['momentum']['stoch_d'] else 'bearish',
                    'williams_r': latest_indicators['momentum']['williams_r'],
                    'williams_state': 'oversold' if latest_indicators['momentum']['williams_r'] > -20 else 'overbought' if latest_indicators['momentum']['williams_r'] < -80 else 'neutral'
                },
                
                # 기존 변동성 분석
                'volatility_indicators': {
                    'bb_position': latest_indicators['volatility']['bb_position'],
                    'bb_upper': latest_indicators['volatility']['bb_upper'],
                    'bb_lower': latest_indicators['volatility']['bb_lower'],
                    'bb_middle': latest_indicators['volatility']['bb_middle'],
                    'bb_signal': 'overbought' if latest_indicators['volatility']['bb_position'] > 80 else 'oversold' if latest_indicators['volatility']['bb_position'] < 20 else 'neutral',
                    'atr': latest_indicators['volatility']['atr'],
                    'atr_percent': latest_indicators['volatility']['atr_percent'],
                    'volatility_level': latest_indicators['volatility']['volatility_level']
                },
                
                # 기존 볼륨 분석
                'volume_indicators': {
                    'volume_ratio': latest_indicators['volume']['volume_ratio'],
                    'volume_state': latest_indicators['volume']['volume_state'],
                    'obv_trend': 'bullish' if latest_indicators['volume']['obv_trend'] > 0 else 'bearish',
                    'mfi': latest_indicators['volume']['mfi'],
                    'mfi_state': 'overbought' if latest_indicators['volume']['mfi'] > 80 else 'oversold' if latest_indicators['volume']['mfi'] < 20 else 'neutral'
                },
                
                # 기존 지지/저항 분석
                'support_resistance': {
                    'support_level': latest_indicators['support_resistance']['support'],
                    'resistance_level': latest_indicators['support_resistance']['resistance'],
                    'price_position': latest_indicators['support_resistance']['price_position'],
                    'breakout_potential': latest_indicators['support_resistance']['breakout_potential'],
                    'support_distance': round(((current_price - latest_indicators['support_resistance']['support']) / current_price) * 100, 2),
                    'resistance_distance': round(((latest_indicators['support_resistance']['resistance'] - current_price) / current_price) * 100, 2)
                },
                
                # 🆕 새로 추가된 반전 분석
                'reversal_analysis': {
                    'bullish_reversal_signals': bullish_signals,
                    'bearish_reversal_signals': bearish_signals,
                    'bullish_signal_count': len(bullish_signals),
                    'bearish_signal_count': len(bearish_signals),
                    'net_signal_bias': len(bullish_signals) - len(bearish_signals),
                    
                    'pattern_analysis': {
                        'double_top_detected': bool(latest.get('double_top', False)),
                        'double_bottom_detected': bool(latest.get('double_bottom', False)),
                        'pattern_strength': float(latest.get('pattern_strength', 0))
                    },
                    
                    'divergence_analysis': {
                        'price_momentum_divergence': bool(latest.get('bullish_divergence', False) or latest.get('bearish_divergence', False)),
                        'volume_divergence': bool(latest.get('volume_divergence_bullish', False) or latest.get('volume_divergence_bearish', False)),
                        'divergence_strength': float(latest.get('divergence_strength', 0)),
                        'momentum_signals': int(latest.get('momentum_bullish_signals', 0) + latest.get('momentum_bearish_signals', 0))
                    },
                    
                    'linear_regression_analysis': {
                        'trend_direction': 'bullish' if latest.get('lr_slope', 0) > 0 else 'bearish',
                        'trend_strength': float(latest.get('lr_trend_strength', 0)),
                        'channel_position': float(latest.get('lr_position', 0.5)),
                        'channel_upper': float(latest.get('lr_upper', 0)),
                        'channel_lower': float(latest.get('lr_lower', 0)),
                        'channel_middle': float(latest.get('lr_middle', 0)),
                        'breakout_potential': 'high' if latest.get('lr_position', 0.5) > 0.9 or latest.get('lr_position', 0.5) < 0.1 else 'low'
                    },
                    
                    'support_resistance_reversal': {
                        'near_support': bool(latest.get('near_support', False)),
                        'near_resistance': bool(latest.get('near_resistance', False)),
                        'support_reversal': bool(latest.get('support_reversal', False)),
                        'resistance_reversal': bool(latest.get('resistance_reversal', False)),
                        'enhanced_support_level': float(latest.get('support_level', 0)),
                        'enhanced_resistance_level': float(latest.get('resistance_level', 0))
                    }
                }
            }
            
            logger.info("AI용 핵심 지표 + 반전 분석 추출 완료")
            return analysis_data
            
        except Exception as e:
            logger.error(f"핵심 지표 추출 중 오류: {e}")
            return {
                'current_price': 0,
                'price_change_24h': 0,
                'volume': 0,
                'error': str(e)
            }
    
    def get_model(self):
        """AI 모델을 필요할 때만 초기화"""
        if not API_KEY:
            return None, None
            
        try:
            client = genai.Client(api_key=API_KEY)
            
            for model_name in MODEL_PRIORITY:
                try:
                    return client, model_name
                except Exception as e:
                    logger.warning(f"기술적 분석 모델 {model_name} 초기화 실패: {e}")
                    continue
            
            return None, None
            
        except Exception as e:
            logger.error(f"기술적 분석 모델 초기화 중 오류: {e}")
            return None, None

    async def analyze_with_ai(self, indicators_data: Dict) -> Dict:
        """AI 모델을 사용하여 기술적 지표 + 반전 분석"""
        # 필요할 때만 모델 초기화
        if self.client is None:
            self.client, self.model_name = self.get_model()
        
        try:
            # 반전 분석이 포함된 향상된 프롬프트 구성
            enhanced_prompt = f"""
당신은 전문 비트코인 기술적 분석가입니다. 다음 데이터를 바탕으로 종합적인 분석을 수행하세요.

기본 정보:
- 현재 가격: ${indicators_data['current_price']:,.2f}
- 24시간 변동: {indicators_data['price_change_24h']:.2f}%
- 시간봉: {indicators_data['timeframe_info']['timeframe']}
- 볼륨: {indicators_data['volume']:,.0f}

기술적 지표 데이터:
{json.dumps(indicators_data, ensure_ascii=False, indent=2)}

특히 다음 반전 신호들에 주목하세요:
- 강세 반전 신호: {indicators_data.get('reversal_analysis', {}).get('bullish_reversal_signals', [])}
- 약세 반전 신호: {indicators_data.get('reversal_analysis', {}).get('bearish_reversal_signals', [])}
- 다이버전스 분석: {indicators_data.get('reversal_analysis', {}).get('divergence_analysis', {})}
- 패턴 분석: {indicators_data.get('reversal_analysis', {}).get('pattern_analysis', {})}
- 선형회귀 채널: {indicators_data.get('reversal_analysis', {}).get('linear_regression_analysis', {})}

다음 JSON 형식으로 응답해주세요:
{{
  "overall_signal": "Strong Buy/Buy/Hold/Sell/Strong Sell",
  "trend_analysis": {{
    "trend_direction": "상승/하락/횡보",
    "trend_strength": 0-100,
    "reversal_probability": 0-100,
    "key_support_level": 숫자,
    "key_resistance_level": 숫자
  }},
  "momentum_analysis": {{
    "momentum_direction": "상승/하락/중립",
    "momentum_strength": 0-100,
    "divergence_signals": "강세/약세/없음",
    "oversold_overbought": "과매수/과매도/중립"
  }},
  "reversal_analysis": {{
    "reversal_probability": 0-100,
    "reversal_direction": "상승반전/하락반전/없음",
    "key_reversal_signals": ["신호1", "신호2"],
    "pattern_confirmation": "확인됨/미확인",
    "divergence_strength": 0-100
  }},
  "volatility_analysis": {{
    "volatility_level": "높음/중간/낮음",
    "breakout_probability": 0-100,
    "expected_direction": "상승/하락/불확실"
  }},
  "volume_analysis": {{
    "volume_trend": "증가/감소/보통",
    "volume_confirmation": true/false,
    "institutional_flow": "매수/매도/중립"
  }},
  "entry_exit_points": {{
    "best_entry_long": 숫자,
    "best_entry_short": 숫자,
    "stop_loss_long": 숫자,
    "stop_loss_short": 숫자,
    "take_profit_long": 숫자,
    "take_profit_short": 숫자
  }},
  "timeframe_analysis": {{
    "short_term": "1시간-4시간 전망",
    "medium_term": "1일-1주일 전망", 
    "long_term": "1주일-1개월 전망"
  }},
  "confidence": 0-100,
  "analysis_summary": "핵심 분석 요약"
}}
"""
            
            # AI 모델에 질의
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=enhanced_prompt
            )
            
            # JSON 파싱
            result_text = response.text
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                result_json = json.loads(json_match.group(0))
                
                # 분석 메타데이터 추가
                result_json['analysis_metadata'] = {
                    'analysis_type': 'ai_based_enhanced',
                    'data_timestamp': datetime.now(timezone.utc).isoformat(),
                    'model_used': self.model_name,
                    'timeframe_used': self.get_timevalue,
                    'reversal_signals_analyzed': True,
                    'raw_data': indicators_data
                }
                
                return result_json
            else:
                logger.error("AI 응답에서 JSON을 찾을 수 없습니다.")
                return self.rule_based_analysis_enhanced(indicators_data)
                
        except Exception as e:
            logger.error(f"AI 기술적 분석 중 오류: {e}")
            return self.rule_based_analysis_enhanced(indicators_data)
    
    def rule_based_analysis_enhanced(self, indicators_data: Dict) -> Dict:
        """규칙 기반 기술적 분석 + 반전 분석 (AI 모델 없을 때 백업)"""
        try:
            trend_indicators = indicators_data.get('trend_indicators', {})
            momentum_indicators = indicators_data.get('momentum_indicators', {})
            volatility_indicators = indicators_data.get('volatility_indicators', {})
            volume_indicators = indicators_data.get('volume_indicators', {})
            support_resistance = indicators_data.get('support_resistance', {})
            reversal_analysis = indicators_data.get('reversal_analysis', {})
            
            # 신호 점수 계산 (기존 + 반전 신호 추가)
            signal_score = 0
            total_signals = 0
            
            # 기존 추세 신호들
            if trend_indicators.get('ema_signal') == 'bullish':
                signal_score += 1
            elif trend_indicators.get('ema_signal') == 'bearish':
                signal_score -= 1
            total_signals += 1
            
            if trend_indicators.get('macd_status') == 'bullish':
                signal_score += 1
            elif trend_indicators.get('macd_status') == 'bearish':
                signal_score -= 1
            total_signals += 1
            
            # 기존 모멘텀 신호들
            rsi = momentum_indicators.get('rsi', 50)
            if rsi < 30:
                signal_score += 1  # 과매도에서 매수
            elif rsi > 70:
                signal_score -= 1  # 과매수에서 매도
            total_signals += 1
            
            # 🆕 반전 신호들 추가
            bullish_reversal_count = reversal_analysis.get('bullish_signal_count', 0)
            bearish_reversal_count = reversal_analysis.get('bearish_signal_count', 0)
            
            # 반전 신호 가중치 (더 높게)
            signal_score += bullish_reversal_count * 2  # 강세 반전 신호
            signal_score -= bearish_reversal_count * 2  # 약세 반전 신호
            total_signals += max(bullish_reversal_count, bearish_reversal_count) * 2
            
            # 다이버전스 신호
            divergence_signals = reversal_analysis.get('divergence_analysis', {}).get('momentum_signals', 0)
            if divergence_signals > 0:
                signal_score += divergence_signals
                total_signals += divergence_signals
            
            # 패턴 신호
            if reversal_analysis.get('pattern_analysis', {}).get('double_bottom_detected', False):
                signal_score += 2
                total_signals += 2
            elif reversal_analysis.get('pattern_analysis', {}).get('double_top_detected', False):
                signal_score -= 2
                total_signals += 2
            
            # 선형회귀 채널 신호
            lr_position = reversal_analysis.get('linear_regression_analysis', {}).get('channel_position', 0.5)
            if lr_position < 0.2:  # 채널 하단 = 강세 신호
                signal_score += 1
            elif lr_position > 0.8:  # 채널 상단 = 약세 신호
                signal_score -= 1
            total_signals += 1
            
            # 전체 신호 강도
            signal_strength = abs(signal_score) / total_signals * 100 if total_signals > 0 else 0
            
            # 반전 확률 계산
            reversal_probability = min(100, (bullish_reversal_count + bearish_reversal_count) * 25)
            reversal_direction = "상승반전" if bullish_reversal_count > bearish_reversal_count else "하락반전" if bearish_reversal_count > bullish_reversal_count else "없음"
            
            # 최종 신호 결정 (반전 신호 고려)
            if signal_score >= 4:
                overall_signal = "Strong Buy"
            elif signal_score >= 2:
                overall_signal = "Buy"
            elif signal_score <= -4:
                overall_signal = "Strong Sell"
            elif signal_score <= -2:
                overall_signal = "Sell"
            else:
                overall_signal = "Hold"
            
            # 결과 구성
            result = {
                "overall_signal": overall_signal,
                "trend_analysis": {
                    "trend_direction": trend_indicators.get('ema_signal', 'neutral').replace('bullish', '상승').replace('bearish', '하락').replace('neutral', '횡보'),
                    "trend_strength": int(signal_strength),
                    "reversal_probability": int(reversal_probability),
                    "key_support_level": support_resistance.get('support_level', 0),
                    "key_resistance_level": support_resistance.get('resistance_level', 0)
                },
                "momentum_analysis": {
                    "momentum_direction": momentum_indicators.get('rsi_state', 'neutral').replace('bullish', '상승').replace('bearish', '하락').replace('neutral', '중립'),
                    "momentum_strength": int(signal_strength),
                    "divergence_signals": "강세" if bullish_reversal_count > bearish_reversal_count else "약세" if bearish_reversal_count > bullish_reversal_count else "없음",
                    "oversold_overbought": momentum_indicators.get('rsi_state', 'neutral').replace('oversold', '과매도').replace('overbought', '과매수').replace('neutral', '중립')
                },
                "reversal_analysis": {
                    "reversal_probability": int(reversal_probability),
                    "reversal_direction": reversal_direction,
                    "key_reversal_signals": reversal_analysis.get('bullish_reversal_signals', []) + reversal_analysis.get('bearish_reversal_signals', []),
                    "pattern_confirmation": "확인됨" if reversal_analysis.get('pattern_analysis', {}).get('pattern_strength', 0) > 0.5 else "미확인",
                    "divergence_strength": int(reversal_analysis.get('divergence_analysis', {}).get('divergence_strength', 0))
                },
                "volatility_analysis": {
                    "volatility_level": volatility_indicators.get('volatility_level', 'medium').replace('high', '높음').replace('medium', '중간').replace('low', '낮음'),
                    "breakout_probability": int(signal_strength),
                    "expected_direction": "상승" if signal_score > 0 else "하락" if signal_score < 0 else "불확실"
                },
                "volume_analysis": {
                    "volume_trend": volume_indicators.get('volume_state', 'normal').replace('high', '증가').replace('normal', '보통').replace('low', '감소'),
                    "volume_confirmation": volume_indicators.get('volume_ratio', 1) > 1.2,
                    "institutional_flow": volume_indicators.get('obv_trend', 'neutral').replace('bullish', '매수').replace('bearish', '매도').replace('neutral', '중립')
                },
                "entry_exit_points": {
                    "best_entry_long": reversal_analysis.get('support_resistance_reversal', {}).get('enhanced_support_level', support_resistance.get('support_level', 0)),
                    "best_entry_short": reversal_analysis.get('support_resistance_reversal', {}).get('enhanced_resistance_level', support_resistance.get('resistance_level', 0)),
                    "stop_loss_long": reversal_analysis.get('support_resistance_reversal', {}).get('enhanced_support_level', support_resistance.get('support_level', 0)) * 0.97,
                    "stop_loss_short": reversal_analysis.get('support_resistance_reversal', {}).get('enhanced_resistance_level', support_resistance.get('resistance_level', 0)) * 1.03,
                    "take_profit_long": reversal_analysis.get('support_resistance_reversal', {}).get('enhanced_resistance_level', support_resistance.get('resistance_level', 0)),
                    "take_profit_short": reversal_analysis.get('support_resistance_reversal', {}).get('enhanced_support_level', support_resistance.get('support_level', 0))
                },
                "timeframe_analysis": {
                    "short_term": f"{'상승' if signal_score > 0 else '하락' if signal_score < 0 else '횡보'} 움직임 예상 (반전 확률: {reversal_probability}%)",
                    "medium_term": f"추세 {'지속' if abs(signal_score) >= 2 else '전환'} 가능성 높음",
                    "long_term": f"{'강세' if signal_score >= 3 else '약세' if signal_score <= -3 else '중립'} 기조 유지"
                },
                "confidence": max(50, int(signal_strength + reversal_probability / 2)),  # 반전 확률도 신뢰도에 반영
                "analysis_summary": f"규칙 기반 종합 분석: {total_signals}개 지표 중 순신호 {signal_score}개 ({'상승' if signal_score > 0 else '하락' if signal_score < 0 else '중립'}), 반전 확률 {reversal_probability}%"
            }
            
            # 메타데이터 추가
            result['analysis_metadata'] = {
                'analysis_type': 'rule_based_enhanced',
                'data_timestamp': datetime.now(timezone.utc).isoformat(),
                'model_used': 'rule_based_enhanced_fallback',
                'timeframe_used': self.get_timevalue,
                'reversal_signals_analyzed': True,
                'signal_score': signal_score,
                'total_signals': total_signals,
                'raw_data': indicators_data
            }
            
            return result
            
        except Exception as e:
            logger.error(f"규칙 기반 종합 분석 중 오류: {e}")
            return {
                "overall_signal": "Hold",
                "error": str(e),
                "confidence": 0,
                "analysis_summary": f"종합 분석 중 오류 발생: {str(e)}"
            }
    
    async def analyze_technical_indicators(self, symbol='BTCUSDT', timeframe=None, limit=300) -> Dict:
        """기술적 지표 + 반전 분석 메인 함수 (동적 timeframe 사용)"""
        try:
            # timeframe이 None이면 TRADING_CONFIG에서 가져오기
            if timeframe is None:
                timeframe = self.get_timevalue
                
            logger.info(f"종합 기술적 지표 + 반전 분석 시작 - timeframe: {timeframe}")
            
            # 1. 차트 데이터 수집
            df = self.get_chart_data(symbol, timeframe, limit)
            if df is None or df.empty:
                return {
                    "success": False,
                    "error": "차트 데이터 수집 실패",
                    "analysis_type": "enhanced_technical_analysis"
                }
            
            # 2. 기술적 지표 + 반전 분석 계산
            processed_df, config_info = self.calculate_technical_indicators(df)
            
            # 3. 핵심 지표 + 반전 신호 추출
            indicators_data = self.extract_key_indicators(processed_df, config_info)
            
            if 'error' in indicators_data:
                return {
                    "success": False,
                    "error": indicators_data['error'],
                    "analysis_type": "enhanced_technical_analysis"
                }
            
            # 4. AI 종합 분석 수행
            analysis_result = await self.analyze_with_ai(indicators_data)
            
            logger.info(f"종합 기술적 지표 + 반전 분석 완료 - timeframe: {timeframe}")
            
            return {
                "success": True,
                "result": analysis_result,
                "analysis_type": "enhanced_technical_analysis"
            }
            
        except Exception as e:
            logger.error(f"종합 기술적 지표 + 반전 분석 중 오류: {e}")
            return {
                "success": False,
                "error": f"분석 중 오류 발생: {str(e)}",
                "analysis_type": "enhanced_technical_analysis"
            }

# 외부에서 사용할 함수 (기본값을 1h로 변경)
async def analyze_enhanced_technical_indicators(symbol='BTCUSDT', timeframe=None, limit=300) -> Dict:
    """기술적 지표 + 반전 분석을 수행하는 함수 (1시간봉 최적화)"""
    analyzer = EnhancedTechnicalAnalyzer()
    return await analyzer.analyze_technical_indicators(symbol, timeframe, limit)

# 테스트용 코드
if __name__ == "__main__":
    import asyncio
    
    async def test():
        result = await analyze_enhanced_technical_indicators()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())