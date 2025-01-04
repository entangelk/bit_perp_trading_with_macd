# Bitcoin Perpetual Trading with MACD Strategy

## Development Log

| Date | Details | Notes |
|------|---------|-------|
| 2024.10.13 | Development started | |
| 2024.10.21 | Basic implementation with MACD and related indicators | Visual analysis conducted ([Analysis](./docs/analysis/backtest.ipynb)) |
| 2024.10.23 | Ported TradingView indicators to Python | Issues encountered with Supertrend implementation |
| 2024.10.26 | Discovered discrepancy between TradingView and Python RSI calculations | |
| 2024.10.30 | Implemented alternative indicators due to real-time calculation issues | Added 2B reversal pattern and high/low optimized trend tracker |
| 2024.11.04 | Signal detection strategy setup | Implemented dual approach for false signal detection (UT bot, MACD, follow line, 2B) |
| 2024.11.11 | Signal detection strategy reset | Added ADX_DI signals |
| 2024.11.14 | Signal detection bug fixes | Initiated Bybit perpetual futures API connection and testing |
| 2024.12.12 | Strategy review and testing | |
| 2024.12.15 | AI-assisted code optimization | Synchronized indicators with TradingView |
| 2024.12.18 | Added HMA strategy | Modified and implemented Squeeze Momentum Oscillator |
| 2024.12.19 | Trading tests | Fixed Squeeze Momentum error when squeeze_d = 0 |
| 2024.12.20 | Identified gaps in trade execution despite trend presence | Started developing new indicator using MACD and DI slope trendlines |
| 2024.12.21 | Strategy backtesting and implementation | MACD focused |
| 2024.12.23 | Testing after strategy modification | DI Slope + MACD with recovery |
| 2024.12.24 | Testing after implementing two primary strategies | |
| 2024.12.25 | Added Supertrend strategy for volatile position coverage | Changed ATR calculation from SMA to RMA due to deviation |
| 2024.12.27 | Created and implemented MACD divergence strategy | |
| 2024.12.31 | Server deployment | AWS implementation |
| 2025.01.01 | Added MongoDB and log size limits | Due to free tier server capacity constraints |
| 2025.01.02 | Added Volume Stg | |
| 2025.01.04 | Added Linear Regression Strategy | |

## 개발 일지

| 날짜 | 내용 | 비고 |
|------|------|------|
| 2024.10.13 | 개발시작 | |
| 2024.10.21 | MACD와 부속 지표를 이용한 기초 제작 | 시각화를 이용한 분석 진행 ([분석](./docs/analysis/backtest.ipynb)) |
| 2024.10.23 | 트레이딩 뷰의 지표들을 파이썬에 이식 | 슈퍼트렌드 등 - 문제 발생 |
| 2024.10.26 | RSI와 기타 지표가 트레이딩뷰와 파이썬간 완전히 같지 않는 오류 확인 | |
| 2024.10.30 | 호환되지 않는 실시간 계산 지표 말고 다른 지표 적용 시도 및 트랩 횡보 방지 | 2B reversal pattern, high and low optimized trend tracker |
| 2024.11.04 | 신호 감지 전략 세팅 및 거짓 신호 판별 전략을 2분화 | UT bot, MACD, follow line, 2B |
| 2024.11.11 | 신호 감지 전략 재설정 및 신호 점검 작업 | ADX_DI 신호 추가 |
| 2024.11.14 | 신호 감지 전략 오류 픽스 시도 | Bybit 무기한 선물거래 API 연결 및 테스팅 |
| 2024.12.12 | 전략 점검 및 테스팅 진행 | |
| 2024.12.15 | AI를 통한 코드 정리 및 지표 트레이딩 뷰와 동일화 작업 진행 | |
| 2024.12.18 | HMA 전략 추가 | 스퀴즈 모멘텀 오실레이터 편집 후 사용 추가 |
| 2024.12.19 | 거래 테스팅 | 스퀴즈 모멘텀에서 오류 발생 - squeeze_d가 0일때 처리 |
| 2024.12.20 | 중간중간 추세는 있지만 거래가 이루어지지 않는 곳이 있음 | MACD 및 DI 기울기 추세선을 이용한 새 지표 개발시작 |
| 2024.12.21 | 전략 백테스팅 후 적용 | MACD |
| 2024.12.23 | 전략 변경 후 테스팅 | DI Slope + MACD with recovery |
| 2024.12.24 | 1차 전략 2종 적용 후 테스팅 | |
| 2024.12.25 | 급등락 포지션 커버를 위한 슈퍼트렌드 전략 추가 적용 | 오차 발생으로 ATR 계산에 SMA -> RMA 방식 변경 |
| 2024.12.27 | MACD를 이용한 다이버전스 전략 생성 및 적용 | |
| 2024.12.31 | 서버 업로드 및 서버 실행 | AWS |
| 2025.01.01 | 프리티어 서버 용량 문제로 몽고, 로그 용량제한 | |
| 2025.01.02 | 볼륨기반 전략 추가 | |
| 2025.01.04 | 선형회귀전략 추가 | |