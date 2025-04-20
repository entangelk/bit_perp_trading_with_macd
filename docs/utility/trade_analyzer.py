import json
import pandas as pd
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from pathlib import Path

class TradeAnalyzer:
    def __init__(self, mongo_uri="mongodb://mongodb:27017", db_name="bitcoin", collection_name="chart_5m", logs_dir="logs"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        self.logs_dir = Path(logs_dir)
        self.logs_file = self.logs_dir / "snapshots_daily.json"
        
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
        
        # 타임스탬프를 UTC로 변환
        for item in data:
            # JSON에 저장된 시간이 로컬 시간이라고 가정
            local_time = datetime.strptime(item['timestamp'], "%Y-%m-%d %H:%M:%S")
            # UTC로 변환
            utc_time = local_time.astimezone(timezone.utc)
            item['timestamp'] = utc_time.isoformat()
            
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
                signal_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                closest_chart = None
                min_diff = float('inf')
                
                for chart_item in chart_data:
                    chart_time = datetime.fromisoformat(chart_item['timestamp'].replace('Z', '+00:00'))
                    diff = abs((chart_time - signal_time).total_seconds())
                    if diff < min_diff:
                        min_diff = diff
                        closest_chart = chart_item
                
                if closest_chart and min_diff <= 300:  # 5분 이내
                    strategy_signals[tag].append({
                        'timestamp': timestamp,
                        'position': position,
                        'price': closest_chart['close']  # 가격 정보 추가
                    })
            
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