import requests
import json
from datetime import datetime

def test_corporate_holdings():
    """기업 BTC 보유량 API 테스트"""
    print("=== 기업 BTC 보유량 API 테스트 ===")
    
    try:
        url = "https://api.coingecko.com/api/v3/companies/public_treasury/bitcoin"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            companies = data.get('companies', [])
            
            if companies:
                total_holdings = sum(company.get('total_holdings', 0) for company in companies)
                total_companies = len(companies)
                top_3 = sorted(companies, key=lambda x: x.get('total_holdings', 0), reverse=True)[:3]
                
                print(f"✅ 기업 BTC 보유량 데이터 수집 성공!")
                print(f"총 기업 수: {total_companies}개")
                print(f"총 보유량: {total_holdings:,.0f} BTC")
                print(f"상위 3개 기업:")
                for i, company in enumerate(top_3, 1):
                    print(f"  {i}. {company.get('name', 'Unknown')}: {company.get('total_holdings', 0):,.0f} BTC")
                
                return True
            else:
                print("❌ 기업 데이터가 비어있음")
                return False
        else:
            print(f"❌ API 호출 실패: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 기업 BTC 보유량 테스트 실패: {e}")
        return False

def test_market_structure():
    """시장 구조 지표 API 테스트"""
    print("\n=== 시장 구조 지표 API 테스트 ===")
    
    try:
        url = "https://api.coingecko.com/api/v3/global"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            global_data = data.get('data', {})
            
            btc_dominance = global_data.get('market_cap_percentage', {}).get('btc', 0)
            eth_dominance = global_data.get('market_cap_percentage', {}).get('eth', 0)
            total_market_cap = global_data.get('total_market_cap', {}).get('usd', 0)
            
            print(f"✅ 시장 구조 데이터 수집 성공!")
            print(f"BTC 도미넌스: {btc_dominance:.2f}%")
            print(f"ETH 도미넌스: {eth_dominance:.2f}%")
            print(f"총 시가총액: ${total_market_cap/1e12:.2f}T")
            print(f"알트코인 도미넌스: {100-btc_dominance-eth_dominance:.2f}%")
            
            return True
        else:
            print(f"❌ API 호출 실패: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 시장 구조 테스트 실패: {e}")
        return False

def test_volume_patterns():
    """거래량 패턴 API 테스트"""
    print("\n=== 거래량 패턴 API 테스트 ===")
    
    try:
        url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
        params = {
            'vs_currency': 'usd',
            'days': '30',
            'interval': 'daily'
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            volumes = data.get('total_volumes', [])
            prices = data.get('prices', [])
            
            if volumes and prices:
                recent_7d_volumes = [v[1] for v in volumes[-7:]]
                recent_7d_avg = sum(recent_7d_volumes) / len(recent_7d_volumes)
                
                # 고거래량 일수 계산
                high_volume_threshold = recent_7d_avg * 1.5
                high_volume_days = len([v for v in volumes[-30:] if v[1] > high_volume_threshold])
                
                print(f"✅ 거래량 패턴 데이터 수집 성공!")
                print(f"최근 7일 평균 거래량: ${recent_7d_avg/1e9:.1f}B")
                print(f"30일간 고거래량 일수: {high_volume_days}일")
                print(f"데이터 포인트: 가격 {len(prices)}개, 거래량 {len(volumes)}개")
                
                return True
            else:
                print("❌ 거래량/가격 데이터가 비어있음")
                return False
        else:
            print(f"❌ API 호출 실패: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 거래량 패턴 테스트 실패: {e}")
        return False

def test_derivatives_estimation():
    """파생상품 추정 API 테스트"""
    print("\n=== 파생상품 추정 API 테스트 ===")
    
    try:
        url = "https://api.coingecko.com/api/v3/coins/bitcoin"
        params = {
            'localization': 'false',
            'tickers': 'true',
            'market_data': 'true',
            'community_data': 'false',
            'developer_data': 'false'
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            tickers = data.get('tickers', [])
            market_data = data.get('market_data', {})
            
            # 현물 vs 선물 거래량 분석
            spot_volume = 0
            futures_volume = 0
            
            for ticker in tickers[:20]:  # 상위 20개만 테스트
                volume_usd = ticker.get('converted_volume', {}).get('usd', 0)
                market_name = ticker.get('market', {}).get('name', '').lower()
                
                if any(keyword in market_name for keyword in ['perp', 'future', 'swap']):
                    futures_volume += volume_usd
                else:
                    spot_volume += volume_usd
            
            total_volume = spot_volume + futures_volume
            futures_ratio = futures_volume / total_volume if total_volume > 0 else 0
            
            current_price = market_data.get('current_price', {}).get('usd', 0)
            price_change_24h = market_data.get('price_change_percentage_24h', 0)
            
            print(f"✅ 파생상품 추정 데이터 수집 성공!")
            print(f"현물 거래량: ${spot_volume/1e9:.1f}B")
            print(f"선물 거래량: ${futures_volume/1e9:.1f}B")
            print(f"선물/현물 비율: {futures_ratio:.3f}")
            print(f"현재 가격: ${current_price:,.0f}")
            print(f"24시간 변동률: {price_change_24h:+.2f}%")
            
            return True
        else:
            print(f"❌ API 호출 실패: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 파생상품 추정 테스트 실패: {e}")
        return False

def test_exchange_indicators():
    """거래소 지표 API 테스트"""
    print("\n=== 거래소 지표 API 테스트 ===")
    
    try:
        url = "https://api.coingecko.com/api/v3/exchanges"
        params = {'per_page': 10, 'page': 1}
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if isinstance(data, list) and data:
                # 기관용 vs 소매용 거래소 구분
                institutional_exchanges = ['coinbase-pro', 'kraken', 'bitstamp', 'gemini']
                retail_exchanges = ['binance', 'okex', 'huobi']
                
                institutional_volume = 0
                retail_volume = 0
                total_volume = 0
                
                print(f"상위 {len(data)}개 거래소 분석:")
                for exchange in data:
                    exchange_id = exchange.get('id', '')
                    exchange_name = exchange.get('name', '')
                    volume_btc = exchange.get('trade_volume_24h_btc', 0)
                    
                    total_volume += volume_btc
                    
                    if exchange_id in institutional_exchanges:
                        institutional_volume += volume_btc
                        exchange_type = "기관용"
                    elif exchange_id in retail_exchanges:
                        retail_volume += volume_btc
                        exchange_type = "소매용"
                    else:
                        exchange_type = "기타"
                    
                    print(f"  {exchange_name:15}: {volume_btc:8,.0f} BTC ({exchange_type})")
                
                institutional_ratio = institutional_volume / total_volume if total_volume > 0 else 0
                
                print(f"\n✅ 거래소 지표 분석 완료!")
                print(f"기관용 거래소 비중: {institutional_ratio:.3f}")
                print(f"총 거래량: {total_volume:,.0f} BTC")
                
                return True
            else:
                print("❌ 거래소 데이터가 비어있음")
                return False
        else:
            print(f"❌ API 호출 실패: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 거래소 지표 테스트 실패: {e}")
        return False

def test_calculation_logic():
    """기관 투자 계산 로직 테스트"""
    print("\n=== 기관 투자 계산 로직 테스트 ===")
    
    try:
        # 샘플 데이터로 계산 테스트
        sample_data = {
            'total_companies': 50,
            'total_corporate_btc': 2000000,
            'btc_dominance': 65.5,
            'institutional_volume_ratio': 0.42,
            'futures_to_spot_ratio': 0.65,
            'recent_7d_avg_volume': 35000000000
        }
        
        # 기관 채택 점수 계산
        adoption_score = min(100, (
            (sample_data['total_companies'] / 100 * 50) +
            (sample_data['total_corporate_btc'] / 1000000 * 50)
        ))
        print(f"✅ 기관 채택 점수: {adoption_score:.1f}")
        
        # 기관 선호도 점수
        preference_score = min(100, (
            (sample_data['btc_dominance'] / 70 * 40) +
            (sample_data['institutional_volume_ratio'] * 60)
        ))
        print(f"✅ 기관 선호도 점수: {preference_score:.1f}")
        
        # 파생상품 활용도
        derivatives_score = min(100, sample_data['futures_to_spot_ratio'] * 100)
        print(f"✅ 파생상품 활용도: {derivatives_score:.1f}")
        
        # 기관 활동 점수
        activity_score = min(100, (
            (sample_data['recent_7d_avg_volume'] / 50000000000 * 50) +
            (sample_data['institutional_volume_ratio'] * 50)
        ))
        print(f"✅ 기관 활동 점수: {activity_score:.1f}")
        
        # 종합 점수 (가중평균)
        institutional_score = (
            adoption_score * 0.25 +
            preference_score * 0.25 +
            derivatives_score * 0.25 +
            activity_score * 0.25
        )
        print(f"✅ 기관 투자 종합 점수: {institutional_score:.1f}")
        
        # 신호 분류
        if institutional_score >= 80:
            signal = "Strong Institutional Buy"
        elif institutional_score >= 65:
            signal = "Institutional Buy"
        elif institutional_score >= 45:
            signal = "Hold"
        elif institutional_score >= 30:
            signal = "Institutional Sell"
        else:
            signal = "Strong Institutional Sell"
        
        print(f"✅ 투자 신호: {signal}")
        
        print("✅ 모든 계산 로직 정상 작동")
        return True
        
    except Exception as e:
        print(f"❌ 계산 로직 오류: {e}")
        return False

def test_correlation_calculation():
    """상관관계 계산 테스트"""
    print("\n=== 상관관계 계산 테스트 ===")
    
    try:
        # 테스트 데이터
        prices = [100, 102, 98, 105, 103, 107, 104, 109, 106, 111]
        volumes = [1000, 950, 1100, 900, 980, 850, 1050, 800, 920, 750]
        
        # 상관관계 계산 (간단한 공식)
        n = len(prices)
        sum_x = sum(prices)
        sum_y = sum(volumes)
        sum_xy = sum(prices[i] * volumes[i] for i in range(n))
        sum_x2 = sum(x ** 2 for x in prices)
        sum_y2 = sum(y ** 2 for y in volumes)
        
        numerator = n * sum_xy - sum_x * sum_y
        denominator = ((n * sum_x2 - sum_x ** 2) * (n * sum_y2 - sum_y ** 2)) ** 0.5
        
        correlation = numerator / denominator if denominator != 0 else 0
        
        print(f"✅ 가격-거래량 상관관계: {correlation:.3f}")
        
        if correlation < -0.3:
            interpretation = "기관 축적 신호 (가격 상승 시 거래량 감소)"
        elif correlation > 0.3:
            interpretation = "기관 분산 신호 (가격 상승 시 거래량 증가)"
        else:
            interpretation = "중립적 패턴"
        
        print(f"✅ 해석: {interpretation}")
        print("✅ 상관관계 계산 정상 작동")
        return True
        
    except Exception as e:
        print(f"❌ 상관관계 계산 오류: {e}")
        return False

def main():
    """기관 투자 흐름 API 종합 테스트"""
    print("🔍 기관 투자 흐름 API 테스트를 시작합니다...\n")
    
    results = {}
    
    # API 테스트들
    results['corporate_holdings'] = test_corporate_holdings()
    results['market_structure'] = test_market_structure()
    results['volume_patterns'] = test_volume_patterns()
    results['derivatives_estimation'] = test_derivatives_estimation()
    results['exchange_indicators'] = test_exchange_indicators()
    
    # 계산 로직 테스트들
    results['calculation_logic'] = test_calculation_logic()
    results['correlation_calculation'] = test_correlation_calculation()
    
    # 결과 요약
    print("\n" + "="*60)
    print("🔍 기관 투자 흐름 API 테스트 결과 요약")
    print("="*60)
    
    success_count = sum(results.values())
    total_tests = len(results)
    
    for test_name, success in results.items():
        status = "✅ 성공" if success else "❌ 실패"
        print(f"{test_name:25}: {status}")
    
    print(f"\n전체 성공률: {success_count}/{total_tests} ({success_count/total_tests*100:.1f}%)")
    
    if success_count >= 5:
        print("🎉 기관 투자 흐름 분석에 필요한 핵심 기능들이 정상 작동합니다!")
        print("\n📌 캐싱 권장사항:")
        print("- 기업 BTC 보유량: 6시간 (느린 변화)")
        print("- 시장 구조 지표: 1시간 (도미넌스 변화)")
        print("- 거래량 패턴: 2시간 (기관 활동)")
        print("- 파생상품 플로우: 2시간 (선물/옵션)")
        print("- 거래소 지표: 2시간 (기관/소매 비중)")
        
        print("\n💡 기관 투자 분석 특징:")
        print("- 기업 BTC 채택 트렌드 추적")
        print("- 기관 vs 소매 거래 패턴 구분")
        print("- 파생상품 활용도 분석")
        print("- 시장 구조 성숙도 평가")
    else:
        print("⚠️ 일부 기능에 문제가 있습니다. 더미 데이터로 대체될 수 있습니다.")

if __name__ == "__main__":
    main()