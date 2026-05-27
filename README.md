# Macro Regime & ISA Allocation Lab

미국, 한국, 글로벌 원자재/유동성 데이터를 모아 매크로 레짐을 판정하고, 매월 신규 투자금 150만원을 어떻게 나눌지 계산하는 개인용 리서치 저장소입니다.

이 저장소는 다음 흐름을 자동화합니다.

- 매크로 지표 수집: 물가, 금리, 유동성, 신용, 환율, 고용, 원자재, 기후/공급 충격
- 6개 Risk Score 계산: Inflation, Liquidity, Credit, FX, Climate, Growth
- 현재 레짐 판정 및 월간 리포트 생성
- 월별 과거 리포트와 장기 대시보드 생성
- ISA에서 매수 가능한 국내 상장 ETF 조합으로 월 적립식 백테스트

투자 권유가 아니라 규칙 기반 점검 도구입니다. 실제 매수 전에는 세금, 수수료, 상품 구조, 환헤지 여부, 개인 자산 비중을 따로 확인해야 합니다.

## 빠른 실행

Bash 기준입니다.

```bash
python -m venv .venv
source .venv/bin/activate
# Git Bash에서 Windows Python으로 만든 venv라면: source .venv/Scripts/activate
python -m pip install --upgrade pip
python -m pip install matplotlib
python scripts/update_macro.py
```

기본 실행은 데이터를 새로 받고, 오늘 날짜의 매크로 레짐 리포트와 차트까지 만듭니다.

주요 결과:

- `reports/macro_regime_YYYY-MM-DD.md`
- `reports/archive/YYYY-MM/macro_regime_YYYY-MM-DD.md`
- `reports/assets/macro_regime_YYYY-MM-DD/*.png`
- `data/processed/macro/latest_snapshot.csv`
- `data/processed/macro/requested_indicators_latest.csv`
- `data/processed/macro/observations_long.csv`
- `data/processed/macro/fetch_status.csv`
- `data/processed/macro/risk_score_history.csv`

## 환경 변수

Bank of Korea ECOS API 키가 있으면 더 안정적으로 한국 데이터를 받을 수 있습니다.

```bash
export BOK_API_KEY="YOUR_ECOS_KEY"
python scripts/update_macro.py --bok-key "$BOK_API_KEY"
```

키가 없으면 가능한 범위에서 샘플 키, Bank of Korea 기준금리 페이지, FRED fallback 데이터를 사용합니다.

## 자주 쓰는 명령

전체 갱신:

```bash
python scripts/update_macro.py
```

데이터만 갱신:

```bash
python scripts/update_macro.py --no-report
```

차트 없이 리포트만 생성:

```bash
python scripts/update_macro.py --no-charts
```

특정 날짜 리포트 생성:

```bash
python scripts/update_macro.py --report-date 2026-05-27
```

금리 데이터만 갱신:

```bash
python scripts/fetch_interest_rates.py
```

매크로 지표 파이프라인만 실행:

```bash
python scripts/fetch_macro_pipeline.py
```

이미 처리된 최신 스냅샷으로 리포트만 재생성:

```bash
python scripts/analyze_macro_regime.py
```

매크로 차트만 다시 생성해서 리포트에 붙이기:

```bash
python scripts/visualize_macro_trends.py --report-date 2026-05-27 --report reports/macro_regime_2026-05-27.md
```

## 월간 히스토리

매월 6일 기준의 과거 레짐 리포트를 생성합니다. 기본 6일은 월급일 다음날에 신규 투자 배분을 점검한다는 가정입니다.

```bash
python scripts/generate_monthly_reports.py --start 2012-03 --end 2026-04
```

결과:

- `reports/monthly/YYYY-MM/macro_regime_YYYY-MM-06.md`
- `data/processed/macro/risk_score_history_monthly.csv`

월간 대시보드 생성:

```bash
python scripts/visualize_monthly_history.py
```

결과:

- `reports/monthly_dashboard.md`
- `reports/assets/monthly_dashboard/*.png`
- `data/processed/macro/monthly_dashboard/*.csv`

## ISA ETF 백테스트

월간 레짐 기반 배분을 ISA에서 매수 가능한 국내 상장 ETF로 대체해 백테스트합니다.

```bash
python scripts/generate_monthly_reports.py --start 2012-03 --end 2026-04
python scripts/run_isa_etf_max_backtests.py
```

결과:

- `reports/backtests/isa_etf_max_summary.md`
- `reports/backtests/isa_etf_max/*.md`
- `data/processed/backtests/isa_etf_max/variant_summary.csv`
- `data/processed/backtests/isa_etf_max/*/actual_etf_trades.csv`
- `data/processed/backtests/isa_etf_max/*/actual_etf_equity_curve.csv`

백테스트 상품 가정:

- 현금/단기채: 국내 단기채 ETF
- 금: 실전 ISA 기준으로 `411060.KS` ACE KRX금현물을 우선 사용
- 과거 장기 구간이 필요한 경우 금 선물 ETF `132030.KS`를 프록시로 사용
- 은/원자재: 국내 선택지가 제한적이어서 `144600.KS` 은 선물 ETF를 보조 헤지로 사용
- 주식/ETF: S&P500, Nasdaq100, 환헤지/비환헤지 조합을 variant별로 비교

레거시 또는 민감도 확인용 스크립트:

- `scripts/backtest_monthly_allocation.py`
- `scripts/backtest_actual_etfs.py`
- `scripts/run_actual_etf_variants.py`

## 데이터 소스

자동 수집 소스:

- Bank of Korea ECOS: 한국 CPI, M2, 무역, 국제수지, 주요 통계
- Bank of Korea 기준금리 페이지: 기준금리 이벤트 및 일별 확장 시계열
- Federal Reserve H.15: Fed Funds Effective Rate
- Federal Reserve Open Market Operations: FOMC 목표금리 이벤트
- FRED: 미국 물가, 금리, 유동성, 신용스프레드, 금융 스트레스, 고용, 원자재 프록시
- Yahoo Finance chart API: DXY, 원자재 선물, 국내 상장 ETF 가격
- GDACS RSS: 현재 자연재해/공급 충격 이벤트

수동 입력 파일:

- `data/manual/manual_indicators.csv`

유료 또는 별도 출처가 필요한 지표는 수동 입력 파일로 보완할 수 있습니다. 예를 들어 정확한 회사채 부도율, 외국인 주식/채권 자금 흐름의 별도 집계치, 기후/공급망 메모 등이 여기에 들어갑니다.

## 모델 구조

핵심 규칙은 `scripts/macro_rules.py`와 `scripts/analyze_macro_regime.py`에 있습니다.

Risk Score는 0~10점입니다. 점수가 높을수록 해당 위험이 강하다는 뜻입니다.

- Inflation Risk: CPI, Core CPI, PCE, 기대인플레이션, WTI 등
- Liquidity Bubble Risk: M2, Fed 지급준비금, 금융여건, 위험선호 등
- Credit Stress Risk: HY/BBB 스프레드, 대출태도, 금융 스트레스, 연체율 프록시 등
- FX Risk: USD/KRW, DXY, 한미 기준금리차, 외국인 자금 흐름, 무역수지 등
- Climate Supply Shock Risk: 에너지, 농산물, 비료, GDACS 이벤트 등
- Growth Slowdown Risk: 실업률, 비농업고용, 실업수당, 장단기 금리차 등

신규 투자금 배분은 세 개의 큰 sleeve를 먼저 계산한 뒤 금/은을 나눕니다.

- 현금/단기채
- 금 및 은/원자재 헤지
- 주식/ETF

기본 신규 투자금은 150만원이며, 5만원 단위로 반올림합니다. 상한/하한, 점수 공식, 라벨은 `scripts/macro_rules.py`에서 관리합니다.

## 디렉터리 구조

```text
data/
  raw/                 원천 응답 원본
  processed/           정규화된 CSV, 스냅샷, 백테스트 결과
  manual/              수동 보완 지표
reports/
  macro_regime_*.md    최신 일자별 레짐 리포트
  archive/             월별 리포트 아카이브
  monthly/             과거 월간 리포트
  monthly_dashboard.md 장기 월간 대시보드
  assets/              리포트 PNG 차트
  backtests/           백테스트 리포트
scripts/
  update_macro.py                  전체 갱신 진입점
  fetch_macro_pipeline.py          매크로 지표 수집/정규화
  fetch_interest_rates.py          BOK/Fed 금리 수집
  analyze_macro_regime.py          레짐 판정 및 리포트 생성
  visualize_macro_trends.py        최신 리포트 차트 생성
  generate_monthly_reports.py      월간 과거 리포트 생성
  visualize_monthly_history.py     월간 대시보드 생성
  run_isa_etf_max_backtests.py     ISA ETF 장기 백테스트
```

## 문제 해결

`ModuleNotFoundError: matplotlib`가 나오면:

```bash
python -m pip install matplotlib
```

ECOS 호출이 제한되거나 실패하면:

```bash
python scripts/update_macro.py --bok-source homepage-events
```

Yahoo Finance 호출이 실패하면 네트워크 상태를 확인한 뒤 다시 실행하세요. 원천 응답은 `data/raw/yahoo*` 아래에 저장됩니다.

`fetch_status.csv`에서 `stale` 또는 `error`가 보이면 해당 지표가 오래되었거나 수집에 실패한 것입니다. 리포트는 가능한 데이터로 생성되지만, 레짐 확신도는 낮춰서 해석해야 합니다.
