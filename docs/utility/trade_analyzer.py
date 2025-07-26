import json
import pandas as pd
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from pathlib import Path
from main_ai_new import TRADING_CONFIG, TIME_VALUES

get_timevalue = TRADING_CONFIG.get('set_timevalue', '15m')
int_timevalue = TIME_VALUES.get(get_timevalue, 15)  # 기본값은 15분
collection_name =  f"chart_{get_timevalue}" if not get_timevalue.startswith("chart_") else get_timevalue

class TradeAnalyzer:
    def __init__(self, mongo_uri="mongodb://mongodb:27017", db_name="bitcoin", collection_name=collection_name,time_threshold=int_timevalue*60, logs_dir="logs"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        self.logs_dir = Path(logs_dir)
        self.logs_file = self.logs_dir / "snapshots_daily.json"
        
        # 시간 간격 설정 (15분 = 900초)
        self.time_threshold = time_threshold  # 자동 분분 간격에 맞춘 임계값
        
    def get_chart_data(self, hours=24):
        """MongoDB에서 차트 데이터 가져오기"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        query = {"timestamp": {"$gte": cutoff_time}}
        projection = {"_id": 0, "timestamp": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}
        
        cursor = self.collection.find(query, projection).sort("timestamp", 1)
        data = list(cursor)
        
        if not data:
            return []
            
        # timestamp를 ISO format 문자열로 변환 (UTC)
        for item in data:
            item['timestamp'] = item['timestamp'].isoformat()
            
        return data
    
    def get_signal_data(self):
        """JSON 파일에서 신호 데이터 가져오기"""
        if not self.logs_file.exists():
            return []
            
        with open(self.logs_file, 'r') as f:
            data = json.load(f)
        
        # 타임스탬프 처리
        for item in data:
            try:
                # 타임스탬프 확인 로깅 추가
                original_timestamp = item['timestamp']
                print(f"원본 타임스탬프: {original_timestamp}, 타입: {type(original_timestamp)}")
                
                # 밀리초 타임스탬프인 경우 (JavaScript 타임스탬프 형식)
                if isinstance(item['timestamp'], (int, float)) or (
                    isinstance(item['timestamp'], str) and item['timestamp'].isdigit() and len(item['timestamp']) > 10
                ):
                    # 이미 밀리초 형태라면 그대로 유지 (정수로 변환하여 확실히 함)
                    item['timestamp'] = int(float(item['timestamp']))
                    
                    # 2025년 이후의 타임스탬프는 초 단위일 수 있음
                    dt = datetime.fromtimestamp(item['timestamp'] / 1000)
                    if dt.year > 2025:
                        # 초 단위로 간주하고 밀리초로 변환
                        item['timestamp'] = int(float(item['timestamp']) * 1000)
                        print(f"미래 시간 감지, 초->밀리초 변환: {item['timestamp']}")
                
                # 초 단위 타임스탬프인 경우 (UNIX 타임스탬프)
                elif isinstance(item['timestamp'], (int, float)) or (
                    isinstance(item['timestamp'], str) and item['timestamp'].isdigit() and len(item['timestamp']) <= 10
                ):
                    # 초에서 밀리초로 변환
                    item['timestamp'] = int(float(item['timestamp']) * 1000)
                    print(f"초->밀리초 변환: {item['timestamp']}")
                
                # 문자열 형태의 시간이라면
                else:
                    try:
                        # 기본 포맷 시도
                        local_time = datetime.strptime(item['timestamp'], "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        try:
                            # ISO 포맷 시도
                            local_time = datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
                        except:
                            # 다른 포맷이 있다면 필요에 따라 추가
                            raise ValueError(f"지원되지 않는 시간 형식: {item['timestamp']}")
                    
                    # 밀리초 타임스탬프로 변환 (JavaScript에서 사용하는 형식)
                    item['timestamp'] = int(local_time.timestamp() * 1000)
                    print(f"문자열->밀리초 변환: {item['timestamp']}")
                    
                print(f"변환 후 타임스탬프: {item['timestamp']}")
                    
            except Exception as e:
                print(f"시간 변환 오류: {e} (값: {item['timestamp']})")
                # 오류 발생 시 현재 시간으로 대체하거나 None 처리
                item['timestamp'] = int(datetime.now().timestamp() * 1000)
            
        return data
    
    def process_data_for_visualization(self, hours=24):
        """프론트엔드 시각화를 위한 데이터 처리"""
        chart_data = self.get_chart_data(hours)
        signal_data = self.get_signal_data()
        
        # 신호 데이터를 전략별로 그룹화
        strategy_signals = {}
        position_timeline = []
        
        for signal in signal_data:
            timestamp = signal['timestamp']
            tag = signal['tag']
            position = signal['position']
            
            # 전략별 신호 저장
            if tag:
                if tag not in strategy_signals:
                    strategy_signals[tag] = []
                
                # 신호와 가장 가까운 차트 데이터 찾기
                try:
                    # 이 부분에서 오류 발생 - int 타입의 timestamp에 replace 메서드를 호출
                    # 타임스탬프 타입 확인하여 처리
                    if isinstance(timestamp, (int, float)) or (
                        isinstance(timestamp, str) and timestamp.isdigit()
                    ):
                        # 숫자형 타임스탬프는 datetime 객체로 변환
                        signal_time = datetime.fromtimestamp(int(timestamp) / 1000 
                                                            if len(str(int(timestamp))) > 10 
                                                            else int(timestamp))
                    else:
                        # 문자열 타임스탬프 처리
                        signal_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    
                    closest_chart = None
                    min_diff = float('inf')
                    
                    for chart_item in chart_data:
                        chart_time = datetime.fromisoformat(chart_item['timestamp'].replace('Z', '+00:00'))
                        diff = abs((chart_time - signal_time).total_seconds())
                        if diff < min_diff:
                            min_diff = diff
                            closest_chart = chart_item
                    
                    if closest_chart and min_diff <= self.time_threshold:  # 15분 이내
                        strategy_signals[tag].append({
                            'timestamp': timestamp,
                            'position': position,
                            'price': closest_chart['close']  # 가격 정보 추가
                        })
                except Exception as e:
                    print(f"타임스탬프 처리 오류: {e}")
            
            # 포지션 타임라인 생성
            position_value = 1 if position == 'Long' else -1 if position == 'Short' else 0
            position_timeline.append({
                'timestamp': timestamp,
                'position': position,
                'value': position_value
            })
        
        
        # 포지션 구간 계산 (배경색 영역을 위해)
        position_ranges = []
        if position_timeline:
            position_timeline.sort(key=lambda x: x['timestamp'])
            
            for i in range(len(position_timeline) - 1):
                current = position_timeline[i]
                next_item = position_timeline[i + 1]
                
                if current['position'] in ['Long', 'Short']:
                    position_ranges.append({
                        'start': current['timestamp'],
                        'end': next_item['timestamp'],
                        'position': current['position']
                    })
        
        # 최종 데이터 정리
        return {
            'chart_data': chart_data,
            'strategy_signals': strategy_signals,
            'position_timeline': position_timeline,
            'position_ranges': position_ranges
        }
    
    def get_visualization_data(self, hours=24):
        """FastAPI 라우터에서 호출할 메인 메서드"""
        return self.process_data_for_visualization(hours)