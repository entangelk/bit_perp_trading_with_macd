from openai import OpenAI
from docs.cal_chart import cal_chart
from dotenv import load_dotenv
import os
import json

# 포지션이 없을 때
def ai_choice(current_price):

    # 환경 변수 로드
    load_dotenv()
    OPEN_API_KEY = os.getenv("OPEN_API_KEY")

    # OpenAI 클라이언트 초기화
    client = OpenAI(api_key=OPEN_API_KEY)

    # 분봉별 기술적 분석 (1분, 5분, 15분, 1시간, 30일 차트 데이터)
    df_1m, df_5m, df_15m, df_1h, df_30d = cal_chart()

    # 각 데이터프레임을 JSON 형식으로 변환
    df_1m_json = df_1m[-100:].to_json()  # 최근 50개의 1분봉 데이터
    df_5m_json = df_5m[-40:].to_json()  # 최근 50개의 5분봉 데이터
    df_15m_json = df_15m[-30:].to_json()  # 최근 50개의 15분봉 데이터
    df_1h_json = df_1h[-24:].to_json()  # 최근 12개의 1시간봉 데이터
    df_30d_json = df_30d[-5:].to_json()  # 최근 5일의 일간 데이터

    # GPT 모델에 기술적 분석 및 시장 상황 전달
    response = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": """You are a Bitcoin perpetual futures short-term investment expert. Your goal is to use the provided technical analysis data to determine the most optimal trade direction (buy or sell) that will result in a 20% profit when using 100x leverage. When interpreting, keep the following in mind

We will be making ultra-short-term investments, so the short-term view of 1-minute and 5-minute data is more important than the long-term view. In general, 130 USDT is the target profit, so pay special attention to this. Make sure to recommend the right position direction to reach first at the current price."""
            },
            {
                "role": "user",
                "content": [
                    { "type" : "text",
                        "text" :f"""
                The current price of Bitcoin (BTC/USDT) is: {current_price} USDT.

                Below are the most recent technical analysis data across different time intervals. Each dataset includes OHLCV (Open, High, Low, Close, Volume) data with additional indicators:

                - **1-Minute Interval (Last 50 Points)**: {df_1m_json}
                - **5-Minute Interval (Last 50 Points)**: {df_5m_json}
                - **15-Minute Interval (Last 50 Points)**: {df_15m_json}
                - **1-Hour Interval (Last 12 Points)**: {df_1h_json}
                - **Daily Interval (Last 30 Points)**: {df_30d_json}

                ### Your task:
                Based on this analysis, please determine whether opening a **long (buy)** or **short (sell)** position will most likely result in a 20% profit first, using 100x leverage. Consider short-term price movements, volatility, trading volume, and any relevant indicators across these time frames.

                Please specify your recommendation as either **buy** or **sell** and provide a brief explanation for your decision based on the provided data.
                """
            },]}
        ], 
        response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "trading_decision",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "position": {"type": "string", "enum": ["buy","stay" ,"sell"]},
                            "decision": {"type": "string"}
                        },
                        "required": ["position","decision"],
                        "additionalProperties": False
                    }
                }
            },
            max_tokens=4095,  # 최대 토큰 수 제한
            temperature=0.5,  # 응답의 다양성 제어
        )

    # 응답의 텍스트를 JSON 형식으로 변환
    response_content = response.choices[0].message.content
    response_json = json.loads(response_content)

    # 포지션 및 결정을 추출
    side = response_json['position']
    decision = response_json['decision']

    return side, decision


if __name__ == "__main__":
    # 테스트를 위한 임의 값 (실제 호출 시 매개변수 전달)
    current_price = 50000  # 예: BTC/USDT 가격
    positions_json = None  # 현재 포지션 정보가 없다면 None으로 설정

    # 함수 호출
    side, decision = ai_choice(current_price, positions_json)
    print(f"Position: {side}, Decision: {decision}")
