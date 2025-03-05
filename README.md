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
| 2025.01.04 | 선형회귀전략 추가 | 파인스크립트 bar_index 대체 요망|
| 2025.01.05 | DI Slope + MACD 전략 승률 하락으로 조건 재설정 | |
| 2025.01.06 | 선형회귀전략 bar_index 대체 작업 | |
| 2025.01.07 | 승률에 따른 전략 수치 재조정 | MACD_div, supertrend| |
| 2025.01.09 | 변수 정리 | 전략 CONFIG로 통합 관리 |
| 2025.01.16 | 슬라이싱 오류 - 보완 코드 제작 | api 업데이트 문제로 예상 |



# 트레이딩 봇 로그 뷰어 설치 및 실행 가이드

이 가이드는 FastAPI를 사용하여 트레이딩 봇의 로그를 웹으로 확인할 수 있는 애플리케이션의 설치 및 실행 방법을 안내합니다.

## 1. 필요한 패키지 설치

```bash
pip install fastapi uvicorn jinja2
```

## 2. 프로젝트 구조 생성

다음과 같은 프로젝트 구조를 생성합니다:

```
log-viewer/
├── main.py          # FastAPI 애플리케이션 코드
├── templates/       # HTML 템플릿 디렉토리
│   ├── index.html   # 메인 페이지 템플릿
│   └── log_view.html # 로그 보기 페이지 템플릿
└── static/          # 정적 파일 디렉토리(필요시)
```

## 3. 설정 수정

`main.py` 파일에서 다음 부분을 실제 환경에 맞게 수정해야 합니다:

```python
# 로그 파일 경로 설정 - 실제 로그 파일 경로로 변경해야 합니다
LOG_DIR = "/path/to/your/logs"  # 실제 로그 파일 경로로 수정하세요
LOG_FILES = {
    "trading": "trading_bot.log",
    "backtest": "strategy_backtest.log"
}
```

EC2 서버에서 로그 파일의 실제 위치로 `LOG_DIR`을 변경하세요.

## 4. 애플리케이션 실행

개발 환경에서 실행:

```bash
cd log-viewer
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 5. EC2 서버에서 백그라운드로 실행하기

서버에서 애플리케이션을 백그라운드로 실행하려면 다음 방법 중 하나를 사용할 수 있습니다:

### 5.1. systemd 서비스 사용 (권장)

`/etc/systemd/system/log-viewer.service` 파일을 생성합니다:

```ini
[Unit]
Description=Trading Bot Log Viewer
After=network.target

[Service]
User=ubuntu  # 실행할 사용자 계정
WorkingDirectory=/home/ubuntu/log-viewer  # 프로젝트 디렉토리
ExecStart=/home/ubuntu/.local/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

그런 다음 서비스를 활성화하고 시작합니다:

```bash
sudo systemctl daemon-reload
sudo systemctl enable log-viewer
sudo systemctl start log-viewer
```

서비스 상태 확인:

```bash
sudo systemctl status log-viewer
```

### 5.2. nohup 사용 (간단한 방법)

```bash
cd log-viewer
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > log_viewer_output.log 2>&1 &
```

## 6. EC2 보안 그룹 설정

EC2 인스턴스의 보안 그룹에서 8000번 포트(또는 사용 중인 포트)에 대한 인바운드 트래픽을 허용해야 합니다:

1. AWS 콘솔에서 EC2 서비스로 이동
2. 해당 인스턴스의 보안 그룹 선택
3. 인바운드 규칙 편집
4. 규칙 추가: TCP 프로토콜, 포트 8000, 소스 IP 제한(필요한 경우)

## 7. 접속 방법

웹 브라우저에서 다음 URL로 접속합니다:

```
http://[EC2-인스턴스-IP]:8000
```

## 8. 주의사항

- 이 애플리케이션은 기본적인 인증이 없으므로, 필요한 경우 Basic Auth나 다른 인증 방식을 추가하는 것이 좋습니다.
- 프로덕션 환경에서는 Nginx나 Apache와 같은 웹 서버를 프록시로 사용하는 것이 권장됩니다.
- 로그 파일에 접근할 수 있는 권한이 있어야 합니다. 필요한 경우 실행 사용자에게 적절한 권한을 부여하세요.

```
pip install python-dotenv requests python-dateutil
```