# 월별 매크로 히스토리 대시보드

기준 데이터: `data/processed/macro/risk_score_history_monthly.csv`
기간: 2012-03-06 ~ 2026-04-06 (170개월)

## 대시보드 읽는 법

- 이 대시보드는 월별 리포트 생성 결과를 다시 모아 복기하는 화면입니다. 매월 6일 기준으로 당시 보였던 리스크 점수와 신규 150만원 배분 판단을 비교합니다.
- Risk Score는 0~10점입니다. 점수가 높을수록 해당 위험이 강하다는 뜻이고, 모든 점수가 동시에 낮아야 공격적 배분이 자연스러워집니다.
- 배분 그래프는 기존 보유자산 전체 리밸런싱이 아니라, 매월 새로 넣는 150만원을 어디에 배분했는지를 보여줍니다.
- 레짐 빈도는 모델이 어떤 시장 환경을 가장 자주 봤는지 확인하는 용도입니다. 수익률 우열을 직접 뜻하지는 않습니다.
- Latest vs Average는 최근 리스크가 장기 평균보다 높은지 낮은지 빠르게 보는 비교표입니다.

## 금/은 상품 가정

- 실전 ISA 기준 금 헤지는 `411060.KS ACE KRX금현물`을 더 자연스러운 기본 후보로 봅니다.
- 긴 과거 구간이 필요한 백테스트에서는 상장 기간 때문에 `132030.KS KODEX 골드선물(H)`을 과거 프록시로 쓸 수 있습니다.
- 은은 국내 상장 은현물 ETF가 마땅치 않아 `144600.KS KODEX 은선물(H)`을 보조 헤지로 유지합니다.
- 따라서 은/원자재 비중은 장기 핵심 방어자산이라기보다, 인플레나 원자재 충격에 대한 작은 선택 옵션으로 해석합니다.

## 핵심 Risk Score 요약

| risk_bucket | latest | long_run_avg | min | max | change_12m |
| --- | --- | --- | --- | --- | --- |
| Inflation | 6.0 | 3.1 | 1.0 | 8.9 | +2.8 |
| Liquidity | 5.0 | 5.0 | 2.0 | 8.4 | -0.1 |
| Credit | 1.8 | 1.8 | 1.0 | 5.5 | -1.1 |
| FX | 6.5 | 2.7 | 1.0 | 6.8 | +1.3 |
| Climate | 6.0 | 3.0 | 1.1 | 6.9 | +4.2 |
| Growth | 3.8 | 4.0 | 1.9 | 7.1 | -0.3 |

## 최근 월 배분

최근 기준일: 2026-04-06

| asset | amount_manwon | share |
| --- | --- | --- |
| Cash/short bonds | 55 | 36.7% |
| Gold | 50 | 33.3% |
| Silver/resources | 15 | 10.0% |
| Stocks/ETF | 30 | 20.0% |

## 레짐 빈도

| regime | months | share |
| --- | --- | --- |
| Goldilocks | 98 | 57.6% |
| Defensive Waiting Mode | 54 | 31.8% |
| Liquidity Bubble | 15 | 8.8% |
| Inflation Rebound + Dollar/KRW Risk | 3 | 1.8% |

## 그래프

### Risk Score Trend

![Risk Score Trend](assets/monthly_dashboard/risk_scores_over_time.png)

월별 6개 Risk Score의 장기 흐름입니다.

### Risk Score Heatmap

![Risk Score Heatmap](assets/monthly_dashboard/risk_score_heatmap.png)

어느 구간에서 어떤 리스크가 강했는지 한눈에 보는 표입니다.

### Allocation Trend

![Allocation Trend](assets/monthly_dashboard/allocation_over_time.png)

월별 150만원 신규 투자금의 제안 배분 비중 변화입니다.

### Regime Counts

![Regime Counts](assets/monthly_dashboard/regime_counts.png)

월별 리포트에서 가장 자주 나온 메인 레짐입니다.

### Latest vs Average

![Latest vs Average](assets/monthly_dashboard/latest_vs_average.png)

최근 점수가 장기 평균 대비 높은지 낮은지 비교합니다.

## 연도별 평균 Risk Score

| year | months | inflation | liquidity | credit | fx | climate | growth |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2012 | 10 | 2.4 | 5.2 | 1.4 | 1.4 | 4.7 | 5.0 |
| 2013 | 12 | 2.1 | 6.8 | 1.0 | 1.6 | 4.9 | 4.6 |
| 2014 | 12 | 2.0 | 5.9 | 1.0 | 1.8 | 4.5 | 4.2 |
| 2015 | 12 | 1.0 | 5.1 | 1.4 | 2.2 | 1.6 | 3.8 |
| 2016 | 12 | 1.3 | 4.7 | 3.0 | 2.0 | 2.1 | 4.0 |
| 2017 | 12 | 1.4 | 5.0 | 1.3 | 1.7 | 1.7 | 3.2 |
| 2018 | 12 | 2.2 | 3.8 | 1.2 | 2.2 | 2.4 | 2.9 |
| 2019 | 12 | 1.4 | 4.8 | 1.4 | 2.7 | 1.8 | 2.9 |
| 2020 | 12 | 1.2 | 7.0 | 3.2 | 1.8 | 2.1 | 5.3 |
| 2021 | 12 | 5.3 | 7.4 | 1.1 | 1.9 | 3.2 | 4.0 |
| 2022 | 12 | 8.3 | 3.5 | 2.1 | 3.9 | 4.8 | 2.9 |
| 2023 | 12 | 6.2 | 2.8 | 3.1 | 4.0 | 3.1 | 4.4 |
| 2024 | 12 | 4.6 | 3.9 | 1.9 | 4.8 | 3.3 | 4.0 |
| 2025 | 12 | 3.8 | 4.8 | 1.7 | 4.9 | 2.4 | 4.1 |
| 2026 | 4 | 4.7 | 5.0 | 1.6 | 5.6 | 3.1 | 3.6 |
