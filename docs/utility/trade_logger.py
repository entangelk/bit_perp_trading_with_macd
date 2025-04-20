import json
from datetime import datetime, timedelta
from pathlib import Path

class TradeLogger:
    def __init__(self, base_dir="logs"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        self.filename = self.base_dir / "snapshots_daily.json"
        
    def log_snapshot(self, server_time, tag, position):
        """
        5분 단위 스냅샷 저장
        
        Args:
            server_time: 서버 시간 (UTC로 가정)
            tag: 전략 태그
            position: 포지션 방향
        """
        # 5분 단위로 반올림
        rounded_time = server_time.replace(minute=(server_time.minute // 5) * 5, second=0, microsecond=0)
        
        snapshot = {
            "timestamp": rounded_time.isoformat(),  # ISO 형식으로 저장
            "tag": tag,
            "position": position
        }
        
        # 파일에 로그 추가 (파일이 없으면 생성)
        if self.filename.exists():
            with open(self.filename, 'r') as f:
                data = json.load(f)
        else:
            data = []
        
        # 동일 타임스탬프 데이터는 덮어쓰기
        data = [log for log in data if log["timestamp"] != snapshot["timestamp"]]
        data.append(snapshot)
        
        # 오래된 데이터 제거 (24시간 이전)
        cutoff_time = server_time - timedelta(hours=24)
        data = [log for log in data if datetime.strptime(log["timestamp"], "%Y-%m-%d %H:%M:%S") > cutoff_time]
        
        # 시간 순으로 정렬
        data.sort(key=lambda x: x["timestamp"])
        
        with open(self.filename, 'w') as f:
            json.dump(data, f, indent=2)