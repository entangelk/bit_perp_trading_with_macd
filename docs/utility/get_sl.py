def set_sl(df, position):
    stop_loss = None
    before_price = None

    # 역순으로 데이터 순환
    for i in range(len(df)-1, 0, -1):
        current_price = df.iloc[i]['close']
        before_price = df.iloc[i-1]['close']

        if position == 'Long':
            # Long 포지션: 이전 close 값이 현재 close 값보다 높았다가 낮아질 때 low 값을 가져옴
            if before_price > current_price:
                stop_loss = df.iloc[i]['low'] - 10
                break

        elif position == 'Short':
            # Short 포지션: 이전 close 값이 현재 close 값보다 낮았다가 높아질 때 high 값을 가져옴
            if before_price < current_price:
                stop_loss = df.iloc[i]['high'] + 10
                break

    # 반전이 발생하지 않았을 때, 최종적으로 마지막 고점/저점을 기준으로 설정
    if stop_loss is None:
        if position == 'Long':
            stop_loss = df.tail(1)['low'].values[0] - 10
        elif position == 'Short':
            stop_loss = df.tail(1)['high'].values[0] + 10

    return stop_loss

if __name__ == "__main__":
    import pandas as pd
    import os

    # 절대 경로를 사용하여 파일 경로를 설정
    script_dir = os.path.dirname(__file__)  # 현재 스크립트의 디렉토리 경로
    abs_file_path = os.path.join(script_dir, '../analysis/data/bitcoin_chart_3m.csv')

    # CSV 파일을 읽어서 DataFrame으로 변환
    df = pd.read_csv(os.path.abspath(abs_file_path))

    # stop_loss 계산을 위해 set_sl 함수에 포지션과 데이터프레임 전달
    stop_loss = set_sl(df, 'Long')  # 또는 'Short'로 포지션 설정 가능
