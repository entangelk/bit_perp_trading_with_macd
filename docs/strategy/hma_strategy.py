import numpy as np

def check_hma_signals(df):
    """
    HMA 기반 매수/매도 신호를 DataFrame에 추가하는 함수
    
    Parameters:
    df (pandas.DataFrame): HMA 값들이 계산된 데이터프레임
                         필요한 컬럼: hma1, hma2, hma3
    
    Returns:
    pandas.DataFrame: 신호가 추가된 데이터프레임
    """
    
    # 조건에 따라 신호 생성
    conditions = [
        # LONG 조건
        (df['hma3'] < df['hma2']) & 
        (df['hma3'] < df['hma1']) & 
        (df['hma1'] > df['hma2']),
        
        # SHORT 조건
        (df['hma3'] > df['hma2']) & 
        (df['hma3'] > df['hma1']) & 
        (df['hma2'] > df['hma1'])
    ]
    
    choices = ['Long', 'Short']
    
    # 신호를 DataFrame에 추가 (unique한 컬럼명 사용)
    df['signal_hma'] = np.select(conditions, choices, default=None)
    
    return df