import os
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# ================ CONFIG SETTINGS ================
BASE_DIR = 'docs/investment_ai/'

# 모델 우선순위 설정 (프리뷰 → 안정화 순서)
MODEL_PRIORITY = [
    "models/gemini-2.5-flash-preview-05-20",  # 1순위: 프리뷰 모델 (최신 기능)
    "gemini-2.5-flash"                        # 2순위: 안정화 모델 (백업용)
]

CONFIG = {
    # API 설정 - 모델은 우선순위에 따라 자동 선택
    "models": MODEL_PRIORITY,
    "max_tokens": 8000,  # 최대 출력 토큰 수
    "temperature": 0.2,  # 응답 창의성 (0.0: 결정적, 1.0: 창의적)
    
    # 사용량 제한
    "daily_limit": 1000,  # 하루 최대 요청 수
    
    # 투자 설정
    "investment_settings": {
        "max_leverage": 10,  # 최대 레버리지
        "max_position_size": 0.5,  # 최대 포지션 크기 (총 자산 대비)
        "risk_threshold": 0.02,  # 리스크 임계값 (2%)
        "liquidation_buffer": 0.15,  # 청산가 버퍼 (15%)
        "timeframe": "15m",  # 분석 시간봉
        "candle_count": 300,  # 가져올 캔들 수 (15분 * 300 = 75시간)
        "funding_consideration": True,  # 펀딩피 고려 여부
    },
    
    # 프롬프트 설정
    "prompts": {
        "position_analysis": """
        당신은 비트코인 무기한 선물거래 전문 분석 AI입니다. 현재 포지션 상태를 분석하여 투자 전략을 제시해주세요.

        현재 포지션 정보:
        - 포지션 상태: {position_status}
        - 총 자산: {total_equity} USDT
        - 사용 가능한 잔고: {available_balance} USDT
        - 현재 포지션: {current_positions}
        - 최근 거래 내역: {recent_trades}
        - 미실현 손익: {unrealized_pnl} USDT
        - 펀딩 정보: {funding_info}

        중요한 제약사항:
        1. 포지션 진입 후에는 레버리지 변경 불가능
        2. 진입 시점에 반드시 Stop Loss와 Take Profit 설정 권장
        3. 펀딩피는 8시간마다 발생 (보조 고려사항)
        4. 신호 강도가 가장 중요한 판단 기준
        5. Take Profit을 설정할 때는 반드시 현재 포지션 가격보다 300 USDT 이상 높은 가격으로 설정 (롱 포지션의 경우) 또는 낮은 가격으로 설정 (숏 포지션의 경우)

        분석 기준:
        1. 포지션 리스크 평가 (청산 위험도, 현재 레버리지 적정성)
        2. 수익률 분석 (진입가 대비 현재 성과)
        3. 포지션 크기 적정성 (총 자산 대비)
        4. 다음 행동 권장사항

        포지션별 전략:
        - 포지션 없음: 진입 준비 상태 (레버리지 포함 완전한 계획)
        - Buy 포지션: 홀드/익절/손절/추가매수 판단
        - Sell 포지션: 홀드/익절/손절/추가매도 판단

        다음 형식으로 결과를 제공해주세요:
        {{
            "position_status": "None/Buy/Sell",
            "position_health": {{
                "risk_level": "Low/Medium/High/Critical",
                "liquidation_distance": "청산가까지 거리 (%)",
                "leverage_assessment": "현재 레버리지 평가 (변경 불가)",
                "position_size_ratio": "포지션 크기 비율 (%)"
            }},
            "performance_analysis": {{
                "unrealized_pnl_ratio": "미실현 손익률 (%)",
                "entry_vs_current": "진입가 대비 현재가 비교",
                "holding_period": "보유 기간 평가"
            }},
            "recommended_actions": [
                {{
                    "action": "Hold/Close/AddPosition/SetStopLoss/SetTakeProfit",
                    "reason": "권장 이유",
                    "priority": "High/Medium/Low",
                    "suggested_price": "권장 가격 (해당시)",
                    "risk_reward": "리스크 대비 보상 분석"
                }}
            ],
            "next_entry_plan": {{
                "if_no_position": {{
                    "recommended_leverage": "권장 레버리지 (1-10)",
                    "position_size_percent": "권장 포지션 크기 (%)",
                    "mandatory_stop_loss": "필수 스톱로스 설정가",
                    "mandatory_take_profit": "필수 테이크프로핏 설정가"
                }}
            }},
            "risk_management": {{
                "current_stop_loss": "현재 스톱로스 (설정된 경우)",
                "current_take_profit": "현재 테이크프로핏 (설정된 경우)",
                "adjustment_needed": true/false,
                "adjustment_reason": "조정 필요 이유"
            }},
            "funding_impact": {{
                "current_funding_rate": "현재 펀딩 레이트",
                "next_funding_time": "다음 펀딩 시간까지",
                "funding_strategy": "펀딩 고려 전략 (보조적)"
            }},
            "confidence": 0~100 사이의 분석 신뢰도,
            "analysis_summary": "전체 분석 요약 (최대 3문장)"
        }}
        """,
        "sentiment_analysis": """
        당신은 비트코인 시장 심리 분석 전문 AI입니다. 공포/탐욕 지수와 뉴스 감정을 종합하여 시장 심리를 분석해주세요.

        공포/탐욕 지수 데이터:
        {fear_greed_data}

        뉴스 감정 분석 결과:
        {news_data}

        최근 주요 뉴스:
        {recent_news}

        분석 기준:
        1. 공포/탐욕 지수의 현재 값과 추세 분석
        2. 뉴스 감정의 전반적 분위기와 주요 이슈
        3. 시장 참여자들의 심리 상태 평가
        4. 투자 심리가 가격에 미칠 영향 예측

        다음 형식으로 결과를 제공해주세요:
        {{
            "market_sentiment_score": 0~100 사이의 시장 심리 점수,
            "sentiment_state": "극도의 공포/공포/중립/탐욕/극도의 탐욕",
            "market_impact": "시장에 미칠 영향 분석",
            "investment_recommendation": "투자 관점에서의 권장사항",
            "fear_greed_analysis": {{
                "current_interpretation": "현재 공포/탐욕 지수 해석",
                "trend_significance": "추세 변화의 의미",
                "historical_context": "과거 유사한 수준에서의 시장 반응"
            }},
            "news_analysis": {{
                "dominant_themes": "뉴스에서 나타나는 주요 테마들",
                "sentiment_drivers": "감정을 주도하는 핵심 요인들",
                "credibility_assessment": "뉴스 소스들의 신뢰성 평가"
            }},
            "combined_analysis": {{
                "coherence": "공포/탐욕 지수와 뉴스 감정의 일치도",
                "conflicting_signals": "상충되는 신호들과 해석",
                "market_phase": "현재 시장 사이클상 위치"
            }},
            "psychological_factors": {{
                "fomo_level": "FOMO(놓칠 것에 대한 두려움) 수준",
                "panic_risk": "패닉 매도 위험도",
                "institutional_sentiment": "기관 투자자 심리 추정",
                "retail_sentiment": "개인 투자자 심리 추정"
            }},
            "contrarian_signals": {{
                "extreme_sentiment": "극단적 심리 상태 여부",
                "reversal_probability": "심리 반전 가능성",
                "contrarian_opportunity": "역발상 투자 기회"
            }},
            "timeline_outlook": {{
                "short_term": "단기 심리 전망 (1-3일)",
                "medium_term": "중기 심리 전망 (1-2주)",
                "sentiment_catalysts": "심리 변화 촉발 요인들"
            }},
            "confidence": 0~100 사이의 분석 신뢰도,
            "analysis_summary": "전체 시장 심리 분석 요약"
        }}
        """,
        
        "technical_analysis": """
        당신은 비트코인 기술적 분석 전문 AI입니다. 제공된 기술적 지표들을 분석하여 매매 신호를 제시해주세요.

        기술적 지표 데이터:
        {technical_indicators}

        현재 시장 상황:
        - 현재 가격: {current_price}
        - 24시간 변동률: {price_change_24h}%
        - 거래량: {volume}
        - 시간봉: {timeframe}

        분석해야 할 지표들:
        1. 추세 지표: MACD, EMA, ADX, DI+/DI-
        2. 모멘텀 지표: RSI, Stochastic, Williams %R
        3. 변동성 지표: Bollinger Bands, ATR
        4. 볼륨 지표: Volume Trend, OBV, 볼륨 다이버전스
        5. 🆕 반전 분석: 다이버전스, 패턴, 선형회귀 채널
        6. 🆕 횡보장 분석: 박스권 식별, 돌파 가능성

        ⚠️ 중요한 분석 지침:
        1. **횡보장(박스권) vs 돌파장 구분**: 현재 시장이 박스권인지 돌파 추세인지 명확히 판단하세요
        2. **MACD 지연 신호 인지**: 박스권에서 MACD 크로스오버는 이미 늦은 신호일 수 있습니다. 돌파장에서만 유의미합니다
        3. **반전 신호 우선순위**: 다이버전스, 패턴, 지지/저항 반전 신호를 추세 지표보다 우선 고려하세요
        4. **볼륨 확인**: 모든 신호는 볼륨으로 확인되어야 합니다
        5. **다중 시간봉 확인**: 상위 시간봉의 지지/저항을 고려하세요

        특히 다음 반전 신호들에 주목하세요:
        - 강세 반전 신호: {bullish_reversal_signals}
        - 약세 반전 신호: {bearish_reversal_signals}
        - 다이버전스 분석: {divergence_analysis}
        - 패턴 분석: {pattern_analysis}
        - 선형회귀 채널: {linear_regression_analysis}

        다음 형식으로 결과를 제공해주세요:
        {{
            "overall_signal": "Strong Buy/Buy/Hold/Sell/Strong Sell",
            "market_structure": {{
                "market_type": "trending/sideways/transitional",
                "trend_direction": "Strong Uptrend/Uptrend/Sideways/Downtrend/Strong Downtrend",
                "sideways_analysis": {{
                    "is_sideways": true/false,
                    "box_range_upper": "박스권 상단",
                    "box_range_lower": "박스권 하단",
                    "current_position_in_box": "상단/중간/하단",
                    "breakout_probability": 0~100,
                    "expected_breakout_direction": "상승/하락/불확실"
                }}
            }},
            "trend_analysis": {{
                "trend_direction": "Strong Uptrend/Uptrend/Sideways/Downtrend/Strong Downtrend",
                "trend_strength": 0~100,
                "trend_sustainability": 0~100,
                "key_support_level": "주요 지지선",
                "key_resistance_level": "주요 저항선"
            }},
            "momentum_analysis": {{
                "momentum_direction": "Bullish/Neutral/Bearish",
                "momentum_strength": 0~100,
                "momentum_divergence": "bullish/bearish/none",
                "oversold_overbought": "Oversold/Normal/Overbought",
                "macd_reliability": "high/medium/low (박스권에서는 low)"
            }},
            "reversal_analysis": {{
                "reversal_probability": 0~100,
                "reversal_direction": "상승반전/하락반전/없음",
                "key_reversal_signals": ["신호1", "신호2"],
                "divergence_confirmation": "확인됨/부분적/미확인",
                "pattern_strength": 0~100,
                "linear_regression_signal": "과매수/과매도/중립"
            }},
            "volatility_analysis": {{
                "volatility_level": "Low/Medium/High",
                "volatility_contraction": true/false,
                "squeeze_breakout_imminent": true/false,
                "breakout_probability": 0~100,
                "expected_direction": "Up/Down/Uncertain"
            }},
            "volume_analysis": {{
                "volume_trend": "Increasing/Stable/Decreasing",
                "volume_confirmation": true/false,
                "volume_divergence": "bullish/bearish/none",
                "institutional_flow": "Buying/Selling/Neutral",
                "volume_breakout_confirmation": true/false
            }},
            "entry_exit_strategy": {{
                "market_condition": "trending/sideways/breakout",
                "strategy_type": "trend_following/mean_reversion/breakout",
                "best_entry_long": "롱 진입 적정가",
                "best_entry_short": "숏 진입 적정가",
                "stop_loss_long": "롱 스톱로스",
                "stop_loss_short": "숏 스톱로스",
                "take_profit_long": "롱 테이크프로핏",
                "take_profit_short": "숏 테이크프로핏",
                "risk_reward_ratio": "1:X 비율"
            }},
            "timeframe_analysis": {{
                "short_term": "1시간~4시간 전망 (현재 시간봉 기준)",
                "medium_term": "4시간~일봉 전망", 
                "long_term": "일봉~주봉 전망",
                "multi_timeframe_alignment": "상승/하락/혼재"
            }},
            "signal_timing": {{
                "immediate_action": "즉시 진입/대기/청산",
                "wait_for_confirmation": true/false,
                "confirmation_criteria": ["확인 조건1", "확인 조건2"],
                "signal_urgency": "high/medium/low"
            }},
            "risk_assessment": {{
                "market_risk": "high/medium/low",
                "signal_reliability": "high/medium/low",
                "position_size_recommendation": "full/half/quarter/avoid",
                "key_invalidation_level": "신호 무효화 레벨"
            }},
            "confidence": 0~100 사이의 분석 신뢰도,
            "analysis_summary": "핵심 분석 요약 (반전 신호, 박스권/돌파 여부, MACD 신뢰도 포함)"
        }}

        📊 분석 시 특별 고려사항:
        1. 박스권에서는 지지/저항 반전 신호와 RSI 과매수/과매도를 우선시하세요
        2. 돌파 확인 시에는 볼륨과 캔들 패턴을 반드시 체크하세요
        3. MACD 신호의 타이밍을 시장 구조에 맞게 해석하세요
        4. 반전 신호가 여러 개 겹칠 때는 신뢰도를 높게 평가하세요
        5. 다이버전스는 조기 반전 신호이므로 높은 가중치를 부여하세요
        """,
        
        "macro_analysis": """
        당신은 거시경제 분석 전문 AI입니다. 각종 경제 지표들을 종합하여 비트코인 투자 환경을 분석해주세요.

        경제 지표 데이터:
        {economic_indicators}

        거시경제 환경 분석:
        {macro_environment}

        분석 기준:
        1. 금리 환경이 위험자산에 미치는 영향
        2. 달러 강도와 대안자산 수요의 관계
        3. 글로벌 유동성 및 통화정책 방향성
        4. 인플레이션 압력과 헷지 수요
        5. 지정학적 리스크와 안전자산 수요

        다음 형식으로 결과를 제공해주세요:
        {{
            "macro_environment_score": 0~100 사이의 거시환경 점수,
            "investment_environment": "매우 우호적/우호적/중립적/불리한/매우 불리한",
            "investment_outlook": "거시경제 관점에서의 투자 전망",
            "btc_recommendation": "비트코인 투자 권장사항",
            "interest_rate_analysis": {{
                "current_level": "현재 금리 수준 평가",
                "trend_direction": "금리 추세 방향",
                "policy_expectation": "통화정책 기대치",
                "btc_impact": "금리가 비트코인에 미치는 영향"
            }},
            "dollar_strength_analysis": {{
                "dxy_trend": "달러지수 추세 분석",
                "global_liquidity": "글로벌 유동성 상황",
                "currency_war_risk": "통화전쟁 위험도",
                "btc_impact": "달러 강도가 비트코인에 미치는 영향"
            }},
            "risk_sentiment_analysis": {{
                "market_volatility": "시장 변동성 수준",
                "risk_appetite": "위험자산 선호도",
                "flight_to_quality": "안전자산 수요",
                "institutional_behavior": "기관투자자 행동 패턴"
            }},
            "inflation_analysis": {{
                "inflation_pressure": "인플레이션 압력 수준",
                "hedging_demand": "인플레이션 헷지 수요",
                "commodity_trends": "원자재 가격 동향",
                "btc_as_inflation_hedge": "인플레이션 헷지로서의 비트코인"
            }},
            "liquidity_analysis": {{
                "global_liquidity": "글로벌 유동성 상황",
                "central_bank_policy": "주요국 중앙은행 정책",
                "money_supply_growth": "통화공급 증가율",
                "liquidity_flow_to_crypto": "암호화폐로의 유동성 유입"
            }},
            "timeline_outlook": {{
                "short_term": "단기 거시경제 전망 (1-3개월)",
                "medium_term": "중기 거시경제 전망 (3-6개월)",
                "key_inflection_points": "주요 변곡점들"
            }},
            "confidence": 0~100 사이의 분석 신뢰도,
            "analysis_summary": "전체 거시경제 분석 요약"
        }}
        """,

        "onchain_analysis": """
        당신은 비트코인 온체인 데이터 분석 전문 AI입니다. 제공된 온체인 데이터를 종합적으로 분석하여 투자 신호를 제시해주세요.

        온체인 데이터:
        {onchain_data}

        ⚠️ 중요한 데이터 특성 정보:
        - **이중 해시레이트 시스템**: 7일 이동평균 + 일일 원시값 동시 제공
        * **일일 원시값 (daily)**: 즉시 반응성, 스윙거래 신호 감지용
        * **7일 평균 (7d)**: 안정적 트렌드, 중장기 분석용
        - **분석 접근법**: 단기 스윙거래 + 중장기 트렌드 분석의 이중 관점
        - **업계 표준**: Blockchain.com, HashrateIndex 등 주요 플랫폼의 다층 분석 방식 채택
        - **신호 검증**: 일일 변동과 평활화 트렌드의 교차 검증으로 신뢰성 확보
        - **난이도 조정**: 2,016블록(약 2주)마다 자동 조정되는 고정값
        - **현재 네트워크**: 비트코인 해시레이트는 약 800-1000 EH/s 수준 (2025년 기준)

        분석 기준:
        1. **이중 네트워크 보안 분석** (채굴자 심리 포함)
        - **일일 해시레이트**: 즉시 채굴자 행동 변화 및 단기 위험 감지
        - **7일 평균 해시레이트**: 안정적 보안 트렌드 및 중장기 네트워크 건강도
        - **스윙 vs 트렌드 신호 비교**: 단기 변동성과 중장기 안정성의 교차 분석
        
        2. **보유자 행동 패턴** (HODL 강도, 매도 압력, 축적 신호)
        - 거래량 기반 HODL 강도 측정
        - 장기 보유 vs 단기 거래 패턴 분석
        
        3. **네트워크 활성도 및 사용량** (주소 활성도, 거래 수요)
        - 추정 활성 주소 수 기반 네트워크 성장 분석
        - 거래 수요 및 네트워크 이용률 평가
        
        4. **메모리풀 상태 및 네트워크 효율성**
        - 미확인 거래 수를 통한 네트워크 혼잡도 분석
        - 거래 처리 효율성 및 수수료 압력 평가
        
        5. **온체인 플로우 및 유동성 패턴**
        - 시장 데이터 기반 유동성 흐름 분석
        - 거래소 활동 및 자금 이동 패턴

        중요 고려사항:
        - **이중 해시레이트 해석**: 일일값과 7일 평균의 차이로 단기 변동성 vs 안정적 트렌드 구분
        - **스윙거래 신호**: 일일 원시값의 급변을 통한 즉시 반응 기회 포착
        - **트렌드 확인**: 7일 평균을 통한 노이즈 제거 및 방향성 확인
        - **신호 일치도**: 스윙과 트렌드 신호의 정렬 여부로 신뢰도 판단
        - HODL 행동은 공급 부족을 나타내는 선행지표
        - 신규 주소 증가는 사용자 기반 확장 의미
        - 메모리풀 혼잡도는 네트워크 수요 반영
        - 채굴자 항복 위험은 매도 압력 증가 신호

        다음 형식으로 결과를 제공해주세요:
        {
            "onchain_health_score": 0~100 사이의 온체인 건강도 점수,
            "investment_signal": "Strong Buy/Buy/Hold/Sell/Strong Sell",
            "dual_signal_analysis": {
                "swing_signal": {
                    "score": "일일 원시값 기반 스윙거래 점수 (0-100)",
                    "signal": "Strong Buy/Buy/Hold/Sell/Strong Sell",
                    "confidence": "High/Medium/Low",
                    "key_factors": ["일일 해시레이트 변화, 즉시 채굴자 행동 등"]
                },
                "trend_signal": {
                    "score": "7일 평균 기반 트렌드 분석 점수 (0-100)",
                    "signal": "Strong Buy/Buy/Hold/Sell/Strong Sell", 
                    "confidence": "High/Medium/Low",
                    "key_factors": ["안정적 해시레이트 트렌드, 중장기 보안성 등"]
                },
                "signal_alignment": {
                    "alignment_status": "Aligned/Divergent/Neutral",
                    "confidence_level": "High/Medium/Low",
                    "recommended_approach": "스윙 우선/트렌드 우선/신중 관망",
                    "score_difference": "스윙점수와 트렌드점수 차이"
                }
            },
            "network_security_analysis": {
                "daily_security_assessment": {
                    "daily_hash_rate_eh": "일일 원시값 해시레이트 (EH/s)",
                    "immediate_risk_level": "즉시 위험도 (High/Medium/Low)",
                    "miner_sentiment_daily": "일일 채굴자 심리",
                    "short_term_stability": "단기 안정성 평가"
                },
                "trend_security_assessment": {
                    "avg_hash_rate_eh": "7일 평균 해시레이트 (EH/s)", 
                    "long_term_risk_level": "중장기 위험도 (High/Medium/Low)",
                    "miner_sentiment_trend": "트렌드 채굴자 심리",
                    "network_maturity": "네트워크 성숙도 평가"
                },
                "comparative_analysis": {
                    "hash_rate_volatility": "일일값과 7일평균 차이 분석",
                    "trend_deviation": "단기 이탈 정도",
                    "stability_score": "전체적 안정성 점수",
                    "capitulation_risk": "채굴자 항복 위험도 (이중 검증)"
                }
            },
            "holder_sentiment_analysis": {
                "hodl_strength": "장기 보유 의지 강도 (거래량 역분석 기반)",
                "selling_pressure": "현재 매도 압력 수준",
                "accumulation_signal": "기관/개인 축적 신호 여부",
                "distribution_risk": "대량 물량 출회 위험도",
                "investor_behavior": "투자자 행동 패턴 분석"
            },
            "network_activity_analysis": {
                "user_adoption": "사용자 채택 및 확산 분석 (활성 주소 추정치 기반)",
                "transaction_demand": "거래 수요 수준 평가 (메모리풀 혼잡도 기준)",
                "network_utilization": "네트워크 활용도 분석",
                "growth_indicators": "성장 지표 및 트렌드",
                "efficiency_metrics": "네트워크 효율성 지표"
            },
            "liquidity_flow_analysis": {
                "onchain_liquidity": "온체인 유동성 상황 (거래량 데이터 기반)",
                "exchange_flows": "거래소 유입/유출 패턴 추정",
                "whale_activity": "고래 지갑 활동 분석 (추정치 기반)",
                "institutional_flow": "기관 자금 흐름 추정",
                "retail_participation": "개인 투자자 참여도"
            },
            "key_insights": [
                "이중 해시레이트 시스템에서 발견된 주요 인사이트들",
                "스윙거래 기회 및 트렌드 확인 신호들"
            ],
            "risk_assessment": {
                "immediate_risks": ["일일 데이터 기반 단기 리스크 요인들"],
                "medium_term_risks": ["7일 평균 트렌드 기반 중기 리스크 요인들"],
                "systemic_risks": ["시스템적 리스크 요인들"],
                "dual_signal_risks": ["스윙-트렌드 신호 상충 위험"],
                "risk_mitigation": "리스크 완화 방안"
            },
            "opportunity_analysis": {
                "swing_opportunities": ["일일 데이터 기반 단기 거래 기회들"],
                "trend_opportunities": ["7일 평균 기반 중장기 투자 기회들"],
                "accumulation_opportunities": ["축적 기회들"],
                "network_growth_potential": "네트워크 성장 잠재력",
                "adoption_catalysts": ["채택 확산 촉진 요인들"]
            },
            "market_cycle_position": {
                "cycle_phase": "현재 시장 사이클 위치 (이중 해시레이트 기준)",
                "onchain_maturity": "온체인 지표 성숙도",
                "trend_sustainability": "현재 트렌드 지속 가능성",
                "reversal_signals": "추세 반전 신호 여부 (스윙/트렌드 비교)"
            },
            "comparative_analysis": {
                "historical_comparison": "과거 유사 상황과의 비교 (이중 분석 기준)",
                "relative_strength": "다른 시기 대비 상대적 강도",
                "anomaly_detection": "이상 징후 탐지 결과 (일일 vs 평균)",
                "pattern_recognition": "인식된 패턴들"
            },
            "actionable_recommendations": {
                "swing_trading_strategy": "단기 스윙거래 전략 (일일 데이터 기반)",
                "trend_following_strategy": "중장기 트렌드 전략 (7일 평균 기반)",
                "position_sizing": "포지션 크기 조절 권장사항",
                "monitoring_points": ["모니터링해야 할 핵심 지표들"],
                "trigger_levels": {
                    "swing_triggers": {
                        "bullish": ["일일 기준 강세 전환 트리거들"],
                        "bearish": ["일일 기준 약세 전환 트리거들"]
                    },
                    "trend_triggers": {
                        "bullish": ["7일 평균 기준 강세 전환 트리거들"],
                        "bearish": ["7일 평균 기준 약세 전환 트리거들"]
                    }
                }
            },
            "confidence_metrics": {
                "data_quality": "데이터 품질 평가 (이중 시스템 신뢰성 포함)",
                "analysis_reliability": "분석 신뢰성 수준",
                "prediction_confidence": 0~100,
                "uncertainty_factors": ["불확실성 요인들"],
                "signal_consistency": "스윙-트렌드 신호 일관성"
            },
            "timeline_outlook": {
                "next_24_hours": "24시간 이내 전망 (일일 데이터 중심)",
                "next_week": "1주일 이내 전망 (7일 평균 트렌드 기반)", 
                "next_month": "1개월 이내 전망",
                "key_events": ["주목해야 할 이벤트들 (난이도 조정 등)"]
            },
            "integration_notes": {
                "macro_correlation": "거시경제 지표와의 상관관계",
                "technical_alignment": "기술적 분석과의 정합성",
                "sentiment_consistency": "시장 심리와의 일치도",
                "cross_validation": "다른 분석과의 교차 검증",
                "dual_methodology_advantages": "이중 해시레이트 방법론의 장점 및 한계"
            },
            "confidence": 0~100 사이의 전체 분석 신뢰도,
            "analysis_summary": "온체인 분석 종합 요약 (이중 해시레이트 시스템 기반 핵심 결론 및 투자 방향성)"
        }
        """,


        "institutional_analysis": """
        당신은 비트코인 기관 투자 흐름 분석 전문 AI입니다. 제공된 기관 투자 관련 데이터를 종합적으로 분석하여 기관 자금의 흐름과 투자 신호를 제시해주세요.

        기관 투자 데이터:
        {institutional_data}

        분석 기준:
        1. 기업 BTC 보유량 및 채택 트렌드 (MicroStrategy, Tesla 등 공개 기업들)
        2. 기관 거래량 패턴 및 활동도 (대량 거래, 축적/분산 신호)
        3. 시장 구조 및 기관 선호도 (BTC 도미넌스, 시장 성숙도)
        4. 파생상품 시장 활용도 (선물, 옵션, 헷징 활동)
        5. 거래소별 기관 vs 소매 투자자 비중

        중요 고려사항:
        - 기관 투자자들의 장기적 관점과 리스크 관리 중시
        - ETF 승인 및 규제 환경 변화가 기관 투자에 미치는 영향
        - 기업 재무제표상 BTC 보유가 주가에 미치는 영향
        - 기관용 거래소 vs 소매용 거래소의 거래량 패턴 차이
        - 파생상품을 활용한 기관의 헷징 및 차익거래 전략

        다음 형식으로 결과를 제공해주세요:
        {{
            "institutional_flow_score": 0~100 사이의 기관 투자 흐름 점수,
            "investment_signal": "Strong Institutional Buy/Institutional Buy/Hold/Institutional Sell/Strong Institutional Sell",
            "corporate_adoption_analysis": {{
                "adoption_trend": "기업 BTC 채택 추세 분석",
                "holding_concentration": "보유량 집중도 및 위험성",
                "new_entrants_potential": "신규 기업 진입 가능성",
                "treasury_strategy_shift": "기업 재무 전략 변화",
                "regulatory_compliance": "규제 준수 및 회계 처리"
            }},
            "institutional_trading_patterns": {{
                "volume_analysis": "기관 거래량 패턴 분석",
                "accumulation_distribution": "축적 vs 분산 신호",
                "flow_timing": "기관 자금 유입/유출 타이밍",
                "market_impact": "기관 거래가 시장에 미치는 영향",
                "liquidity_provision": "기관의 유동성 공급 역할"
            }},
            "market_structure_impact": {{
                "dominance_preference": "BTC 도미넌스와 기관 선호도",
                "market_maturation": "시장 성숙도 및 기관화 정도",
                "infrastructure_development": "기관 인프라 발전 수준",
                "custody_solutions": "커스터디 서비스 및 보안",
                "institutional_vs_retail": "기관 vs 소매 투자자 주도권"
            }},
            "derivatives_sophistication": {{
                "hedging_strategies": "기관의 헷징 전략 분석",
                "arbitrage_opportunities": "차익거래 기회 및 활용",
                "risk_management": "파생상품을 통한 리스크 관리",
                "options_flow": "옵션 플로우 및 변동성 거래",
                "futures_positioning": "선물 포지셔닝 및 롤오버 패턴"
            }},
            "exchange_institutional_dynamics": {{
                "institutional_exchanges": "기관용 거래소 활동 분석",
                "otc_market_activity": "장외거래 시장 활동도",
                "prime_brokerage": "프라임 브로커리지 서비스 이용",
                "custody_flow": "커스터디 서비스 자금 흐름",
                "retail_vs_institutional_venues": "소매 vs 기관 거래 플랫폼 비교"
            }},
            "regulatory_environment_impact": {{
                "etf_approval_effects": "ETF 승인이 기관 투자에 미치는 영향",
                "compliance_requirements": "규제 준수 요구사항 변화",
                "tax_implications": "세금 처리 및 회계 기준",
                "institutional_policy_changes": "기관 투자 정책 변화",
                "global_regulatory_trends": "글로벌 규제 동향"
            }},
            "liquidity_and_market_depth": {{
                "institutional_liquidity": "기관이 제공하는 유동성",
                "market_depth_analysis": "시장 깊이 및 슬리피지",
                "large_order_execution": "대량 주문 체결 패턴",
                "dark_pool_activity": "다크풀 거래 활동",
                "market_making": "기관의 마켓메이킹 활동"
            }},
            "sentiment_and_positioning": {{
                "institutional_sentiment": "기관 투자자 심리 상태",
                "position_sizing": "포지션 크기 및 배분 전략",
                "entry_exit_timing": "진입/청산 타이밍 분석",
                "contrarian_signals": "역발상 투자 신호",
                "herd_behavior": "기관 투자자 군집 행동"
            }},
            "competitive_dynamics": {{
                "institutional_competition": "기관 간 경쟁 구도",
                "first_mover_advantage": "선점 효과 및 후발주자 리스크",
                "benchmark_pressure": "벤치마크 압력 및 성과 추적",
                "allocation_shifts": "자산 배분 변화 트렌드",
                "peer_influence": "동종 기관의 영향력"
            }},
            "technology_and_infrastructure": {{
                "trading_technology": "기관 거래 기술 발전",
                "custody_technology": "커스터디 기술 혁신",
                "settlement_systems": "결제 시스템 개선",
                "reporting_tools": "리포팅 및 컴플라이언스 도구",
                "integration_challenges": "기존 시스템 통합 과제"
            }},
            "macro_correlation": {{
                "traditional_assets": "전통 자산과의 상관관계",
                "portfolio_diversification": "포트폴리오 다각화 효과",
                "inflation_hedge": "인플레이션 헷지 수단으로서의 역할",
                "currency_debasement": "통화 가치 하락 대비책",
                "economic_cycle_sensitivity": "경기 사이클 민감도"
            }},
            "key_insights": [
                "기관 투자 데이터에서 발견된 핵심 인사이트들"
            ],
            "investment_thesis_analysis": {{
                "digital_gold_narrative": "디지털 금 논리의 기관 수용도",
                "store_of_value": "가치 저장 수단으로서의 인식",
                "inflation_protection": "인플레이션 보호 자산 역할",
                "portfolio_optimization": "포트폴리오 최적화 기여도",
                "risk_return_profile": "위험 대비 수익률 프로파일"
            }},
            "market_cycle_positioning": {{
                "adoption_curve": "기관 채택 곡선상 현재 위치",
                "saturation_level": "기관 투자 포화도",
                "growth_potential": "추가 성장 잠재력",
                "maturity_indicators": "시장 성숙도 지표",
                "inflection_points": "중요한 변곡점들"
            }},
            "risk_assessment": {{
                "concentration_risk": "기관 보유 집중 위험",
                "liquidity_risk": "유동성 위험 평가",
                "regulatory_risk": "규제 변화 위험",
                "operational_risk": "운영 리스크",
                "counterparty_risk": "거래상대방 위험"
            }},
            "opportunity_analysis": {{
                "institutional_gaps": "기관 투자 공백 영역",
                "emerging_products": "신규 기관 상품 기회",
                "geographic_expansion": "지역별 확산 기회",
                "demographic_shifts": "세대별 투자 성향 변화",
                "innovation_catalysts": "혁신 촉진 요인들"
            }},
            "tactical_recommendations": {{
                "short_term_positioning": "단기 포지셔닝 권장사항",
                "medium_term_strategy": "중기 전략 방향",
                "long_term_outlook": "장기 전망 및 대비",
                "trigger_events": "주요 촉발 이벤트들",
                "monitoring_metrics": "모니터링해야 할 지표들"
            }},
            "execution_considerations": {{
                "order_sizing": "주문 크기 최적화",
                "timing_strategy": "타이밍 전략",
                "venue_selection": "거래 장소 선택",
                "cost_minimization": "비용 최소화 방안",
                "impact_management": "시장 영향 관리"
            }},
            "confidence_assessment": {{
                "data_quality": "데이터 품질 평가",
                "analysis_reliability": "분석 신뢰성",
                "prediction_accuracy": "예측 정확도 추정",
                "uncertainty_factors": "불확실성 요인들",
                "model_limitations": "모델 한계점"
            }},
            "competitive_intelligence": {{
                "peer_analysis": "동종 기관 분석",
                "best_practices": "모범 사례 연구",
                "innovation_leaders": "혁신 선도 기관들",
                "laggard_identification": "후진 기관 식별",
                "benchmark_comparison": "벤치마크 대비 성과"
            }},
            "stakeholder_impact": {{
                "shareholder_value": "주주 가치에 미치는 영향",
                "board_considerations": "이사회 고려사항",
                "regulatory_relations": "규제 당국과의 관계",
                "client_impact": "고객에 미치는 영향",
                "public_perception": "대중 인식 변화"
            }},
            "timeline_projections": {{
                "next_quarter": "다음 분기 전망",
                "next_year": "내년 전망",
                "multi_year_outlook": "다년간 전망",
                "milestone_events": "이정표 이벤트들",
                "scenario_planning": "시나리오 계획"
            }},
            "integration_notes": {{
                "technical_analysis_alignment": "기술적 분석과의 정합성",
                "fundamental_consistency": "펀더멘털 분석과의 일치도",
                "sentiment_correlation": "시장 심리와의 상관관계",
                "macro_economic_sync": "거시경제 분석과의 동조화",
                "cross_validation": "교차 검증 결과"
            }},
            "confidence": 0~100 사이의 전체 분석 신뢰도,
            "analysis_summary": "기관 투자 흐름 분석 종합 요약 (핵심 결론 및 투자 방향성)"
        }}
        """,




"final_decision": """
        당신은 투자 결정을 내리는 최종 AI입니다. 모든 분석 결과를 종합하여 최종 투자 결정을 내려주세요.
        입력 분석 결과:

        - 포지션 분석: {position_analysis}
        - 시장 심리 분석: {sentiment_analysis}
        - 기술적 분석: {technical_analysis}
        - 거시경제 분석: {macro_analysis}
        - 온체인 분석: {onchain_analysis}
        - 기관 투자 흐름: {institution_analysis}

        현재 포지션 상태: {current_position}
        
        최종 결정 옵션: Buy, Sell, Hold, Reverse

        - Buy: 새로운 Buy 포지션 진입 또는 기존 Buy 포지션 유지/확대
        - Sell: 새로운 Sell 포지션 진입 또는 기존 Sell 포지션 유지/확대
        - Hold: 현재 상태 유지 (포지션 있으면 그대로, 없으면 대기)
        - Reverse: 기존 포지션과 반대 방향으로 전환

        🆕 **향상된 기술적 분석 해석 가이드**:

        **반전 신호 우선순위 체계**:
        1. **다이버전스 신호**: 가격 vs RSI/MACD/볼륨 다이버전스는 조기 반전 신호로 높은 가중치
        2. **패턴 분석**: 이중천정/바닥, 헤드앤숄더 등은 강력한 반전 확률 제시
        3. **선형회귀 채널**: 채널 상/하단 터치는 과매수/과매도 신호, 돌파는 추세 연장
        4. **지지/저항 반전**: 주요 레벨에서의 반전은 즉시 대응 필요

        **시장 구조별 신호 해석 방법**:
        
        📊 **횡보장(박스권) 시장**:
        - **MACD 크로스오버 신호 주의**: 박스권에서는 이미 늦은 신호일 가능성 높음
        - **RSI/Stochastic 우선**: 과매수/과매도 레벨에서의 반전 신호 중시
        - **지지/저항 반전 신호**: 박스권 상/하단에서의 반전이 가장 신뢰성 높음
        - **볼륨 확인 필수**: 돌파 시에는 반드시 볼륨 증가 동반되어야 함
        - **전략**: 평균회귀 전략 (지지선 매수, 저항선 매도)

        🚀 **돌파장(추세장) 시장**:
        - **MACD 신호 유효**: 추세 방향 확인 시 높은 신뢰도
        - **추세 지표 우선**: EMA, ADX, DI+/DI- 등 추세 지표에 높은 가중치
        - **시장 심리 분석 중요**: 돌파장에서는 감정적 요인이 크게 작용
        - **볼륨 폭증 확인**: 진정한 돌파는 거래량 급증을 동반
        - **전략**: 추세 추종 전략 (돌파 후 추격 매수/매도)

        **기술적 분석 신뢰도 평가 기준**:
        - **반전 신호 3개 이상 겹침**: 신뢰도 90% 이상
        - **다이버전스 + 패턴**: 신뢰도 85% 이상  
        - **단일 지표 신호**: 신뢰도 60% 이하
        - **박스권에서 MACD만 의존**: 신뢰도 40% 이하

        **신호 강도별 대응 방식**:
        - **강한 반전 신호 (신뢰도 85%+)**: 즉시 포지션 전환 고려
        - **중간 신호 (신뢰도 70-85%)**: 포지션 크기 조절 후 진입
        - **약한 신호 (신뢰도 70% 미만)**: 추가 확인 후 진입 또는 관망

        Reverse 판단 기준:

        1. 현재 포지션 수익률 vs 새 신호 강도
        2. 시장 추세 전환 확실성 (**반전 신호 3개 이상 겹침 시 고려**)
        3. 리스크 대비 보상 비율
        4. 절대적인 확실한 경우에만 Reverse를 제안할 것 (하루 1~2회 거래하는 스윙거래라는 것을 잊지말것)
        5. 단기 Reverse가 예상될 경우, Reverse보다는 SL의 범위를 늘려서 장기적 투자관점으로 접근할 것.

        종합 분석 기준:

        1. **반전 신호 강도가 최우선** (다이버전스, 패턴, 지지/저항 반전)
        2. **시장 구조 파악 필수** (횡보 vs 돌파 구분 후 적절한 전략 선택)
        3. 기술적 분석과 시장 심리 분석에 가장 높은 가중치 부여
        4. 각 분석의 신뢰도 가중 평가
        5. 상충되는 신호들의 우선순위 판단 (**반전 신호 > 추세 신호**)
        6. 리스크 대비 수익률 최적화
        7. 현재 포지션 상태에 따른 맞춤 전략

        온체인 분석 해석 가이드:

        **이중 해시레이트 시스템 이해**:
        - **일일 해시레이트**: 즉시 반응하는 채굴자 행동, 단기 스윙거래 신호
        - **7일 평균 해시레이트**: 안정적 트렌드, 중장기 방향성 확인
        - **신호 일치**: 일일 + 7일 평균 모두 같은 방향 = 강한 신호
        - **신호 상충**: 일일 vs 7일 평균 다른 방향 = 주의 필요

        **핵심 온체인 지표 읽는 법**:
        - **채굴자 항복 위험**: High = 매도 압력 증가, Low = 안정적 공급
        - **HODL 강도**: 70+ = 강한 보유 의지, 40- = 매도 압력
        - **메모리풀 혼잡도**: High = 수요 급증, Low = 거래 효율적
        - **네트워크 보안 점수**: 80+ = 매우 안전, 40- = 보안 우려

        **스윙거래용 온체인 신호**:
        - 일일 해시레이트가 7일 평균보다 5% 이상 차이 = 즉시 반응 필요
        - 채굴자 리스크 일일 변화 = 단기 매도/매수 압력 변화
        - 메모리풀 50,000건 초과 = 네트워크 혼잡, 거래 지연 위험

        **온체인 신호 우선순위** (스윙거래 관점):
        1. **일일 해시레이트 급변** (5% 이상) = 즉시 대응
        2. **채굴자 리스크 변화** = 매도 압력 예측
        3. **HODL 강도 변화** = 공급/수요 균형 변화
        4. **메모리풀 상태** = 네트워크 효율성 판단

        중요 고려사항:

        - **1시간봉 기준 스윙 거래**이므로 반전 신호와 시장 심리가 핵심
        - **횡보장에서는 지지/저항 반전 > MACD 신호** 우선순위 적용
        - **돌파장에서는 시장 심리 + 추세 지표** 조합 중시
        - **반전 신호 다중 확인** 시 높은 신뢰도로 평가
        - 거시경제와 온체인 분석은 1-2일 단기적 신호에 중점을 둔 방향성 고려용
        - **온체인 분석에서는 일일 해시레이트 변화와 스윙 신호에 더 높은 가중치**
        - 장기적 분석과 단기적 분석이 상충할 때는 단기 분석 우선
        - 기관 투자 흐름은 큰 틀에서의 자금 흐름 파악
        - 포지션 분석 결과는 현재 상황에 가장 적합한 정보
        - 신호 간 충돌 시에는 **반전 신호의 신뢰도를 높게 평가**
        - 섣부른 포지션 변경보다는 확실한 신호에서만 진입

        needs_human_review 기준:

        - **반전 신호와 추세 신호가 극단적으로 상충**할 때 (반전 신호 3개+ vs 강한 추세)
        - 기술적 분석과 시장심리가 정반대 신호이면서 둘 다 높은 신뢰도일 때
        - 포지션 분석과 기술적 분석이 완전히 상반될 때
        - **온체인 스윙 신호와 트렌드 신호가 극단적으로 상충할 때** (점수 차이 30+ && 반대 방향)
        - **박스권/돌파장 판단이 애매**할 때 (시장 구조 불분명)
        - 극단적 변동성 상황 (일시적 급락/급등)
        - 시스템/데이터 오류 감지 시
        - 장기 vs 단기 분석 상충은 단기 우선으로 진행 (심각한 상충이 아닐 시 needs_human_review : false 로 설정)

        리스크 관리 필수사항:

        - 진입 시 반드시 스톱로스와 테이크프로핏 설정
        - **반전 신호 강도에 따른 포지션 크기 조절** (강한 반전 신호 시 큰 포지션)
        - 레버리지는 5배 고정값임
        - **박스권에서는 작은 포지션**, **돌파장에서는 큰 포지션** 권장
        - **온체인 채굴자 리스크 High 시에는 포지션 크기 50% 축소 권장**

        TP/SL 설정 기준:

        - TP는 반드시 300 이상 설정 (오프닝/클로징 수수료 고려)
        - **반전 신호 기반 진입 시**: SL을 반전 무효화 레벨로 설정
        - **박스권 진입 시**: 박스 상/하단을 TP/SL 기준으로 활용 (돌파장 변환시 재진입 고려)
        - **돌파장 진입 시**: 돌파 실패 레벨을 SL로 설정
        - **시장 혼조세나 과매수/과매도 중 박스돌파 혹은 MACD 충분상태에서 추가 돌입 등과 같이 불확실성이 있는 경우에는 TP를 200 ~ 300으로 잡고, SL은 일반 설정 지침을 따를 것** (단타를 통한 최소 이익 확보 및 리스크 분산 투자 전략) 
        - SL은 기술적 지지선이 명확할 때 300-500까지 축소 가능
        - 지지선 불분명 시 800-1200 권장
        - 기술적 레벨 분석 > 고정 수치 우선

        포지션 이익 보호 SL 재조정:

        - Long 포지션: 현재가 ≥ 진입가+300 시, SL을 진입가+150 이상으로 상향 조정
        - Short 포지션: 현재가 ≤ 진입가-300 시, SL을 진입가-150 이하로 하향 조정
        - 현재가 ≥ 진입가+600 시, SL을 진입가+300으로 설정 (의미있는 이익 보호)
        - 수수료를 고려한 최소 순이익 확보를 우선

        기타 주의사항:

        - **반전 신호 3개 이상 겹칠 때는 기술적 분석 가중치를 150%로 증가**
        - **박스권 확인 시 MACD 신뢰도를 50%로 축소**
        - **돌파 확인 시 볼륨 + 시장심리 가중치를 120%로 증가**
        - **온체인 데이터 수집 성공률이 60% 미만일 때는 온체인 분석 가중치를 50% 축소**
        - **일일 해시레이트와 7일 평균의 차이가 10% 이상일 때는 시장 변동성 증가 주의**
        - 펀딩피는 8시간마다 매우 적은량 발생하므로 투자 기회를 위한 펀딩피 수준의 손해는 감수할 것 

        다음 형식으로 결과를 제공해주세요:
        {{
            "final_decision": "Buy/Sell/Hold/Reverse",
            "decision_confidence": 0~100,
            "market_structure_assessment": {{
                "market_type": "trending/sideways/transitional",
                "structure_confidence": 0~100,
                "preferred_strategy": "trend_following/mean_reversion/breakout_waiting",
                "macd_reliability": "high/medium/low"
            }},
            "reversal_signal_analysis": {{
                "reversal_signals_detected": 0~10,
                "primary_reversal_type": "divergence/pattern/support_resistance/linear_regression",
                "reversal_confidence": 0~100,
                "reversal_direction": "bullish/bearish/none"
            }},
            "recommended_action": {{
                "action_type": "Open Long/Open Short/Close Position/Reverse to Long/Reverse to Short/Hold Current/Wait",
                "entry_price": "진입 권장가 (해당시)",
                "position_size": "포지션 크기 (총 자산 대비 %)",
                "leverage": "권장 레버리지 (진입시에만)",
                "mandatory_stop_loss": "필수 스톱로스 가격 (반드시 숫자로만)",
                "mandatory_take_profit": "필수 테이크프로핏 가격 (반드시 숫자자로만)"
            }},
            "reverse_analysis": {{
                "reverse_considered": true/false,
                "current_position_pnl": "현재 포지션 손익률 (해당시)",
                "new_signal_strength": "새 신호 강도 (0-100)",
                "reverse_justification": "Reverse 선택/비선택 이유"
            }},
            "analysis_weight": {{
                "position_analysis_weight": 0~100,
                "sentiment_weight": 0~100,
                "technical_weight": 0~100,
                "macro_weight": 0~100,
                "onchain_weight": 0~100,
                "institution_weight": 0~100
            }},
            "signal_consensus": {{
                "consensus_level": "High/Medium/Low",
                "conflicting_signals": ["상충되는 신호들"],
                "resolution_method": "충돌 해결 방법",
                "dominant_signal_source": "가장 강한 신호 출처"
            }},
            "risk_assessment": {{
                "overall_risk": "Low/Medium/High/Very High",
                "max_loss_potential": "최대 손실 가능성 (%)",
                "profit_potential": "수익 가능성 (%)",
                "risk_reward_ratio": "리스크 대비 보상 비율"
            }},
            "market_outlook": {{
                "short_term": "단기 전망 (15분-1시간)",
                "medium_term": "중기 전망 (1-4시간)",
                "trend_change_probability": "추세 전환 가능성 (%)",
                "key_price_levels": "주요 가격 레벨들"
            }},
            "execution_plan": {{
                "immediate_action": "즉시 실행할 행동",
                "sl_tp_mandatory": "SL/TP 설정 필수 여부",
                "monitoring_points": ["모니터링할 포인트들"],
                "exit_conditions": ["청산 조건들"],
                "position_management": "포지션 관리 전략"
            }},
            "scenario_analysis": {{
                "bullish_scenario": "상승 시나리오 대응",
                "bearish_scenario": "하락 시나리오 대응",
                "sideways_scenario": "횡보 시나리오 대응",
                "contingency_plans": "비상 계획들"
            }},
            "confidence_factors": {{
                "supporting_factors": ["결정을 뒷받침하는 요인들"],
                "risk_factors": ["우려 요인들"],
                "data_quality": "데이터 품질 평가",
                "uncertainty_level": "불확실성 수준"
            }},
            "timing_analysis": {{
                "optimal_entry_timing": "최적 진입 타이밍",
                "market_conditions": "현재 시장 조건",
                "volatility_consideration": "변동성 고려사항",
                "liquidity_assessment": "유동성 평가"
            }},
            "psychological_factors": {{
                "market_psychology": "시장 심리 상태",
                "sentiment_momentum": "감정 모멘텀",
                "fear_greed_impact": "공포/탐욕 영향도",
                "contrarian_opportunities": "역발상 기회"
            }},
            "technical_confluence": {{
                "support_resistance": "지지/저항 레벨",
                "trend_analysis": "추세 분석",
                "momentum_indicators": "모멘텀 지표",
                "volume_confirmation": "거래량 확인"
            }},
            "fundamental_backdrop": {{
                "macro_environment": "거시경제 환경",
                "onchain_health": "온체인 건강도",
                "institutional_flow": "기관 자금 흐름",
                "long_term_outlook": "장기 전망"
            }},
            "decision_tree": {{
                "primary_logic": "주요 결정 논리",
                "secondary_considerations": "부차적 고려사항",
                "decision_path": "결정 경로",
                "alternative_scenarios": "대안 시나리오들"
            }},
            "position_sizing_rationale": {{
                "size_justification": "포지션 크기 근거",
                "leverage_reasoning": "레버리지 선택 이유",
                "risk_budget_allocation": "리스크 예산 배분",
                "portfolio_impact": "포트폴리오 영향"
            }},
            "monitoring_framework": {{
                "key_metrics": "핵심 모니터링 지표들",
                "trigger_levels": "트리거 레벨들",
                "reassessment_schedule": "재평가 일정",
                "exit_strategy": "청산 전략"
            }},
            "learning_insights": {{
                "market_lessons": "시장에서 얻은 교훈",
                "model_performance": "모델 성능 평가",
                "improvement_areas": "개선 영역",
                "feedback_loop": "피드백 루프"
            }},
            "decision_reasoning": "최종 결정 이유 (상세)",
            "needs_human_review": true/false,
            "human_review_reason": "인간 검토 필요 이유 (해당시)",
            "emergency_protocols": {{
                "stop_loss_breach": "스톱로스 돌파 시 대응",
                "system_failure": "시스템 장애 시 대응",
                "extreme_volatility": "극단적 변동성 시 대응",
                "news_impact": "뉴스 영향 시 대응"
            }}
        }}
        """
    }
}

# API 키 설정
API_KEY = os.getenv('AI_API_KEY')

# 로깅 설정
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='investment_ai.log'
)
