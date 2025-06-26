# AI 기반 비트코인 자동거래 시스템 설정 가이드

## 1. 시스템 개요

기존의 전략 기반 거래 시스템을 AI 기반 시스템으로 완전히 업그레이드했습니다.

### 주요 변경사항
- **기존**: `main.py` - 정적 전략 기반 거래
- **신규**: `main_ai.py` - AI 분석 기반 거래

### AI 시스템 구성
1. **6개 전문 분석기**
   - Position Analyzer: 포지션 상태 분석
   - Technical Analyzer: 기술적 지표 분석
   - Sentiment Analyzer: 시장 심리 분석 (공포/탐욕 지수 + 뉴스)
   - Macro Analyzer: 거시경제 분석
   - Onchain Analyzer: 온체인 데이터 분석
   - Institution Analyzer: 기관 투자 흐름 분석

2. **최종 결정 AI**: 모든 분석을 통합하여 최종 투자 결정

3. **통합 레이어**: AI 결정을 실제 거래로 실행

## 2. 환경 설정

### 필수 환경 변수
```bash
# .env 파일에 추가
BYBIT_ACCESS_KEY=your_bybit_api_key
BYBIT_SECRET_KEY=your_bybit_secret_key
AI_API_KEY=your_google_ai_api_key  # Gemini API 키
```

### Google AI API 키 발급
1. [Google AI Studio](https://aistudio.google.com/) 접속
2. API 키 생성
3. `.env` 파일에 `AI_API_KEY` 설정

### 필수 패키지 설치
```bash
pip install google-genai
pip install feedparser  # 뉴스 수집용
pip install requests
pip install pandas
pip install numpy
pip install ta  # 기술적 지표
pip install ccxt  # 거래소 API
pip install pymongo  # MongoDB
pip install python-dotenv
pip install tqdm
```

## 3. 설정 파일 확인

### `docs/investment_ai/config.py`
- AI 모델 우선순위
- 투자 설정 (레버리지, 포지션 크기 등)
- 상세한 프롬프트 템플릿들

### `TRADING_CONFIG` (main_ai.py)
```python
TRADING_CONFIG = {
    'symbol': 'BTCUSDT',
    'leverage': 5,
    'usdt_amount': 0.3,  # 자산의 30%
    'set_timevalue': '15m',  # 15분봉 (AI 최적화)
    'take_profit': 400,
    'stop_loss': 400
}
```

## 4. 실행 방법

### AI 기반 거래 시스템 실행
```bash
python main_ai.py
```

### 기존 전략 기반 시스템 (백업용)
```bash
python main.py
```

## 5. 시스템 동작 방식

### AI 트레이딩 사이클 (15분마다)
1. **차트 데이터 업데이트**
2. **6개 분석 병렬 실행**
   - 포지션, 기술적, 심리, 거시경제, 온체인, 기관 분석
3. **AI 최종 결정**
   - 모든 분석 결과를 가중치 기반으로 통합
   - 신뢰도와 리스크 평가
4. **거래 실행**
   - Buy/Sell/Hold/Reverse 결정
   - 자동 스톱로스/테이크프로핏 설정

### 안전 장치
- **신뢰도 필터**: 60% 미만 신뢰도 시 거래 대기
- **인간 검토**: 복잡한 상황에서 검토 요청
- **긴급 정지**: 과도한 손실 감지 시 자동 정지
- **승률 리버싱**: 기존 로직 유지

## 6. 모니터링

### 로그 파일
- `investment_ai.log`: AI 분석 로그
- `trading.log`: 거래 실행 로그

### 출력 파일
- `ai_decision_history.json`: AI 결정 히스토리
- `win_rate.json`: 승률 추적

### 실시간 모니터링
```bash
tail -f investment_ai.log
```

## 7. 트러블슈팅

### AI API 연결 실패
- `AI_API_KEY` 확인
- 인터넷 연결 확인
- 규칙 기반 분석으로 자동 전환됨

### 거래소 API 오류
- `BYBIT_ACCESS_KEY`, `BYBIT_SECRET_KEY` 확인
- API 권한 확인 (선물거래 권한 필요)

### MongoDB 연결 오류
- Docker MongoDB 컨테이너 상태 확인
- 포트 27017 확인

### 차트 데이터 오류
- 네트워크 연결 확인
- Bybit API 상태 확인

## 8. 성능 최적화

### AI 분석 속도
- 병렬 처리로 6개 분석을 동시 실행
- 모델 우선순위로 최적 모델 자동 선택

### 메모리 관리
- 결정 히스토리 100개로 제한
- 불필요한 데이터 자동 정리

### 네트워크 최적화
- API 호출 재시도 로직
- 타임아웃 설정

## 9. 백업 및 복구

### 기존 시스템 백업
- `main.py`: 기존 전략 기반 시스템 (그대로 유지)
- 모든 전략 파일들 보존

### AI 시스템 롤백
```bash
# 문제 발생 시 기존 시스템으로 복귀
python main.py
```

## 10. 업데이트 및 확장

### 새로운 분석기 추가
1. `docs/investment_ai/analyzers/` 에 새 분석기 생성
2. `ai_trading_integration.py` 에 분석 태스크 추가
3. `final_decisionmaker.py` 에 가중치 설정

### 프롬프트 개선
- `docs/investment_ai/config.py` 에서 프롬프트 수정
- A/B 테스트로 성능 비교

### 새로운 AI 모델 추가
- `MODEL_PRIORITY` 리스트에 모델 추가
- 자동 fallback 지원

## 주의사항

1. **실제 자금으로 테스트하기 전에 반드시 테스트넷에서 충분히 검증**
2. **AI 결정도 시장 조건에 따라 틀릴 수 있음**
3. **정기적인 성과 모니터링 필수**
4. **과도한 레버리지 사용 금지**
5. **리스크 관리 규칙 준수**

## 연락처

문의사항이나 버그 리포트는 개발팀에 연락 바랍니다.