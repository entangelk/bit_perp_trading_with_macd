# bitcoin perpatual trading with macd'stg


## 정리

MACD를 활용, RSI도 활용
200일 이평선 활용
볼린저 밴드도 활용

1분봉 단타? 5분봉 단타? 이거 좀 고민해봐야겠음


## 해야할일

1. 코드 디버깅 : 스타트 시그널 신호 유지 되고 있음 고쳐야함. adx_di.py
2. ut bot 시그널이 돌파가 아닌 유지로 되어있음. 고쳐야함
3. start_signal_final_check 로직 적용시켜야함
```
Bybit 서버에서 가져온 최신 데이터가 데이터베이스에 업데이트되었습니다: {'timestamp': datetime.datetime(2024, 11, 18, 9, 35), 'open': 92099.5, 'high': 92101.4, 'low': 92088.0, 'close': 92088.1, 'volume': 1.908}
Flow Line : None
ut bot : Long
macd stg : None
현재 save_signal: Short
현재 position: Long
```

1시간 트렌드라인 유티봇이 기준
동일 방향이면 길게 이건 어떻게 보지?
반대 방향이면 짧게 500원 정도.