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

        분석해야 할 지표들:
        1. 추세 지표: MACD, EMA, ADX
        2. 모멘텀 지표: RSI, Stochastic
        3. 변동성 지표: Bollinger Bands, ATR
        4. 볼륨 지표: Volume Trend, OBV

        다음 형식으로 결과를 제공해주세요:
        {{
            "overall_signal": "Strong Buy/Buy/Hold/Sell/Strong Sell",
            "trend_analysis": {{
                "trend_direction": "Strong Uptrend/Uptrend/Sideways/Downtrend/Strong Downtrend",
                "trend_strength": 0~100,
                "key_support_level": "주요 지지선",
                "key_resistance_level": "주요 저항선"
            }},
            "momentum_analysis": {{
                "momentum_direction": "Bullish/Neutral/Bearish",
                "momentum_strength": 0~100,
                "oversold_overbought": "Oversold/Normal/Overbought"
            }},
            "volatility_analysis": {{
                "volatility_level": "Low/Medium/High",
                "breakout_probability": 0~100,
                "expected_direction": "Up/Down/Uncertain"
            }},
            "volume_analysis": {{
                "volume_trend": "Increasing/Stable/Decreasing",
                "volume_confirmation": true/false,
                "institutional_flow": "Buying/Selling/Neutral"
            }},
            "entry_exit_points": {{
                "best_entry_long": "롱 진입 적정가",
                "best_entry_short": "숏 진입 적정가",
                "stop_loss_long": "롱 스톱로스",
                "stop_loss_short": "숏 스톱로스",
                "take_profit_long": "롱 테이크프로핏",
                "take_profit_short": "숏 테이크프로핏"
            }},
            "timeframe_analysis": {{
                "short_term": "1시간~4시간 전망",
                "medium_term": "일봉 전망", 
                "long_term": "주봉 전망"
            }},
            "confidence": 0~100 사이의 분석 신뢰도,
            "analysis_summary": "기술적 분석 요약"
        }}
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

        분석 기준:
        1. 네트워크 보안 및 해시레이트 트렌드 (채굴자 심리 포함)
        2. 보유자 행동 패턴 (HODL 강도, 매도 압력, 축적 신호)
        3. 네트워크 활성도 및 사용량 (주소 활성도, 거래 수요)
        4. 메모리풀 상태 및 네트워크 효율성
        5. 온체인 플로우 및 유동성 패턴

        중요 고려사항:
        - 해시레이트는 네트워크 보안의 핵심 지표
        - HODL 행동은 공급 부족을 나타내는 선행지표
        - 신규 주소 증가는 사용자 기반 확장 의미
        - 메모리풀 혼잡도는 네트워크 수요 반영
        - 채굴자 항복 위험은 매도 압력 증가 신호
        - API 오류로 hash_rate가 0으로 수집될 수 있습니다. 이 경우, 이 데이터는 분석에 포함하지 말고 그 외의 데이터로만 분석하시오.
        - hash_rate가 0으로 수집되어 분석에서 제외되었을 경우, 반드시 analysis_summary에 표기하여 최종 결정 AI가 분석할때 참고할 수 있도록 하시오.

        다음 형식으로 결과를 제공해주세요:
        {{
            "onchain_health_score": 0~100 사이의 온체인 건강도 점수,
            "investment_signal": "Strong Buy/Buy/Hold/Sell/Strong Sell",
            "network_security_analysis": {{
                "security_level": "네트워크 보안 수준 평가",
                "hash_rate_assessment": "해시레이트 트렌드 분석",
                "miner_sentiment": "채굴자 심리 및 행동 분석",
                "security_trend": "보안 강화/유지/약화 추세",
                "capitulation_risk": "채굴자 항복 위험도 평가"
            }},
            "holder_sentiment_analysis": {{
                "hodl_strength": "장기 보유 의지 강도",
                "selling_pressure": "현재 매도 압력 수준",
                "accumulation_signal": "기관/개인 축적 신호 여부",
                "distribution_risk": "대량 물량 출회 위험도",
                "investor_behavior": "투자자 행동 패턴 분석"
            }},
            "network_activity_analysis": {{
                "user_adoption": "사용자 채택 및 확산 분석",
                "transaction_demand": "거래 수요 수준 평가",
                "network_utilization": "네트워크 활용도 분석",
                "growth_indicators": "성장 지표 및 트렌드",
                "efficiency_metrics": "네트워크 효율성 지표"
            }},
            "liquidity_flow_analysis": {{
                "onchain_liquidity": "온체인 유동성 상황",
                "exchange_flows": "거래소 유입/유출 패턴",
                "whale_activity": "고래 지갑 활동 분석",
                "institutional_flow": "기관 자금 흐름 추정",
                "retail_participation": "개인 투자자 참여도"
            }},
            "key_insights": [
                "온체인 데이터에서 발견된 주요 인사이트들"
            ],
            "risk_assessment": {{
                "immediate_risks": ["단기 리스크 요인들"],
                "medium_term_risks": ["중기 리스크 요인들"],
                "systemic_risks": ["시스템적 리스크 요인들"],
                "risk_mitigation": "리스크 완화 방안"
            }},
            "opportunity_analysis": {{
                "bullish_signals": ["강세 신호들"],
                "accumulation_opportunities": ["축적 기회들"],
                "network_growth_potential": "네트워크 성장 잠재력",
                "adoption_catalysts": ["채택 확산 촉진 요인들"]
            }},
            "market_cycle_position": {{
                "cycle_phase": "현재 시장 사이클 위치",
                "onchain_maturity": "온체인 지표 성숙도",
                "trend_sustainability": "현재 트렌드 지속 가능성",
                "reversal_signals": "추세 반전 신호 여부"
            }},
            "comparative_analysis": {{
                "historical_comparison": "과거 유사 상황과의 비교",
                "relative_strength": "다른 시기 대비 상대적 강도",
                "anomaly_detection": "이상 징후 탐지 결과",
                "pattern_recognition": "인식된 패턴들"
            }},
            "actionable_recommendations": {{
                "short_term_strategy": "단기 전략 권장사항",
                "medium_term_outlook": "중기 전망 및 대응",
                "monitoring_points": ["모니터링해야 할 핵심 지표들"],
                "trigger_levels": {{
                    "bullish_triggers": ["강세 전환 트리거 수준들"],
                    "bearish_triggers": ["약세 전환 트리거 수준들"]
                }}
            }},
            "confidence_metrics": {{
                "data_quality": "데이터 품질 평가",
                "analysis_reliability": "분석 신뢰성 수준",
                "prediction_confidence": 0~100,
                "uncertainty_factors": ["불확실성 요인들"]
            }},
            "timeline_outlook": {{
                "next_24_hours": "24시간 이내 전망",
                "next_week": "1주일 이내 전망", 
                "next_month": "1개월 이내 전망",
                "key_events": ["주목해야 할 이벤트들"]
            }},
            "integration_notes": {{
                "macro_correlation": "거시경제 지표와의 상관관계",
                "technical_alignment": "기술적 분석과의 정합성",
                "sentiment_consistency": "시장 심리와의 일치도",
                "cross_validation": "다른 분석과의 교차 검증"
            }},
            "confidence": 0~100 사이의 전체 분석 신뢰도,
            "analysis_summary": "온체인 분석 종합 요약 (핵심 결론 및 투자 방향성)"
        }}
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

        Reverse 판단 기준:

        1. 현재 포지션 수익률 vs 새 신호 강도
        2. 시장 추세 전환 확실성
        3. 리스크 대비 보상 비율

        종합 분석 기준:

        1. 신호 강도가 최우선 (각 분석의 확실성과 일치도)
        2. 기술적 분석과 시장 심리 분석에 가장 높은 가중치 부여
        3. 각 분석의 신뢰도 가중 평가
        4. 상충되는 신호들의 우선순위 판단
        5. 리스크 대비 수익률 최적화
        6. 현재 포지션 상태에 따른 맞춤 전략

        중요 고려사항:

        - 1시간봉 기준 스윙 거래(하루 1-2회)이므로 기술적 분석과 시장 심리가 핵심
        - 거시경제와 온체인 분석은 1-2일 단기적 신호에 중점을 둔 방향성 고려용
        - 장기적 분석과 단기적 분석이 상충할 때는 단기 분석 우선
        - 기관 투자 흐름은 큰 틀에서의 자금 흐름 파악
        - 포지션 분석 결과는 현재 상황에 가장 적합한 정보
        - 신호 간 충돌 시에는 신뢰도가 높은 분석에 더 큰 가중치
        - 섣부른 포지션 변경보다는 확실한 신호에서만 진입

        needs_human_review 기준:

        - 기술적 분석과 시장심리가 정반대 신호이면서 둘 다 높은 신뢰도일 때
        - 포지션 분석과 기술적 분석이 완전히 상반될 때
        - 극단적 변동성 상황 (일시적 급락/급등)
        - 시스템/데이터 오류 감지 시
        - 장기 vs 단기 분석 상충은 단기 우선으로 진행 (심각한 상충이 아닐 시 needs_human_review : false 로 설정)

        리스크 관리 필수사항:

        - 진입 시 반드시 스톱로스와 테이크프로핏 설정
        - 포지션 크기는 신호 강도와 신뢰도에 비례
        - 레버리지는 5배 고정값임
        - 신호가 약하거나 충돌 시에는 포지션 크기 축소 또는 관망

        TP/SL 설정 기준:

        - TP는 반드시 300 이상 설정 (오프닝/클로징 수수료 고려)
        - SL은 기술적 지지선이 명확할 때 300-500까지 축소 가능
        - 지지선 불분명 시 800-1200 권장
        - 기술적 레벨 분석 > 고정 수치 우선

        포지션 이익 보호 SL 재조정:

        - Long 포지션: 현재가 ≥ 진입가+300 시, SL을 진입가+150 이상으로 상향 조정
        - Short 포지션: 현재가 ≤ 진입가-300 시, SL을 진입가-150 이하로 하향 조정
        - 현재가 ≥ 진입가+600 시, SL을 진입가+300으로 설정 (의미있는 이익 보호)
        - 수수료를 고려한 최소 순이익 확보를 우선

        기타 주의사항:

        - API 오류로 hash_rate가 0으로 수집될 수 있습니다. 이 경우, 이 데이터는 분석에 포함하지 말고 그 외의 데이터로만 분석하시오.

        다음 형식으로 결과를 제공해주세요:
        {{
            "final_decision": "Buy/Sell/Hold/Reverse",
            "decision_confidence": 0~100,
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
