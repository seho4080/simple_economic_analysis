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
python -m pip install -r requirements.txt
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
python scripts/update_macro.py --report-date "$(date +%F)"
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
REPORT_DATE="$(date +%F)"
python scripts/visualize_macro_trends.py --report-date "$REPORT_DATE" --report "reports/macro_regime_${REPORT_DATE}.md"
```

## 월간 히스토리

매월 6일 기준의 과거 레짐 리포트를 생성합니다. 기본 6일은 월급일 다음날에 신규 투자 배분을 점검한다는 가정입니다.

```bash
python scripts/generate_monthly_reports.py --start 2012-03
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

## 섹터별 HTML 대시보드

최신 매크로 스냅샷과 차트 자산을 묶어서 섹터별로 탐색할 수 있는 정적 HTML을 생성합니다.

```bash
python scripts/generate_sector_dashboard.py
```

결과:

- `reports/sector_dashboard.html`
- `reports/indicators/*.html`

생성된 HTML은 별도 서버 없이 브라우저에서 바로 열 수 있습니다. 지표가 추가되면 `latest_snapshot.csv`의 `category` 기준으로 탭이 자동 확장되고, 최신 `reports/assets/macro_regime_YYYY-MM-DD/*.png` 차트를 연결합니다. 각 지표명은 상세 페이지로 연결되며 최근 관측치, 3개월/12개월 변화, 알림 여부, 출처를 확인할 수 있습니다.

## 변화 감지 알림

최신 리스크 점수와 직전 리포트의 차이, 3개월 변화율이 큰 지표, stale 데이터 품질 이슈를 자동 요약합니다.

```bash
python scripts/generate_change_alerts.py
```

결과:

- `reports/alerts_YYYY-MM-DD.md`
- `reports/alerts_latest.md`
- `data/processed/macro/change_alerts_latest.csv`

## Risk attribution

Risk Score 변화가 어떤 지표 변화에서 왔는지 위험 상승 압력과 위험 완화 압력으로 나누어 설명합니다.

```bash
python scripts/generate_risk_attribution.py
```

결과:

- `reports/risk_attribution_YYYY-MM-DD.md`
- `reports/risk_attribution_latest.md`
- `data/processed/macro/risk_attribution_latest.csv`

## Data quality confidence

지표 최신성, 수집 성공률, 리스크별 드라이버 커버리지를 합산해 리포트 신뢰도 점수를 계산합니다.

```bash
python scripts/generate_data_quality_report.py
```

결과:

- `reports/data_quality_YYYY-MM-DD.md`
- `reports/data_quality_latest.md`
- `data/processed/macro/data_quality_latest.csv`

## Daily decision brief

최신 레짐, 배분, 주요 알림, attribution, 데이터 품질을 한 문서로 묶은 최종 의사결정 브리프입니다.

```bash
python scripts/generate_daily_brief.py
```

결과:

- `reports/daily_brief_YYYY-MM-DD.md`
- `reports/daily_brief_latest.md`

## Scenario simulator

최신 리스크 점수를 기준점으로 두고 인플레, 환율, 신용, 성장 둔화 같은 위험 점수를 슬라이더로 바꿔 레짐과 신규 150만원 배분이 어떻게 달라지는지 확인하는 정적 HTML입니다.

```bash
python scripts/generate_scenario_simulator.py
```

결과:

- `reports/scenario_simulator.html`

## Scenario matrix

`config/scenario_library.csv`에 저장한 가정별 리스크 점수를 읽어 레짐, 배분, 기준 대비 변화, 과거 유사 국면, 유사 국면 이후 1/3/6/12개월 프록시 수익률을 비교합니다. 프록시 수익률은 S&P 500, 금, 은, USD/KRW, 한국 단기금리 관측치를 사용합니다.

```bash
python scripts/generate_scenario_matrix.py
```

결과:

- `reports/scenario_matrix.html`
- `data/processed/macro/scenario_matrix_latest.csv`
- `data/processed/macro/scenario_analogs_latest.csv`

## Scenario ISA ETF backtests

저장된 시나리오의 고정 배분을 기존 ISA ETF 최장 구간 백테스트의 월별 실제 ETF 수익률 경로에 얹어 비교합니다. 네트워크로 가격을 다시 받지 않고 `data/processed/backtests/isa_etf_max/*/actual_etf_trades.csv`를 재사용하므로 빠르게 갱신됩니다.

```bash
python scripts/generate_scenario_etf_backtests.py
```

결과:

- `reports/scenario_etf_backtests.html`
- `data/processed/backtests/scenario_etf_backtests/scenario_etf_summary.csv`
- `data/processed/backtests/scenario_etf_backtests/scenario_etf_lots.csv`

## Decision engine

최신 레짐, 알림, 데이터 품질, 저장 시나리오, 시나리오별 ISA ETF 백테스트를 묶어 오늘의 액션 레벨, 기준 배분, ETF 실행 후보, 스트레스 체크를 자동으로 정리합니다.

```bash
python scripts/generate_decision_engine.py
```

결과:

- `reports/decision_engine.html`
- `reports/decision_engine_latest.md`
- `data/processed/macro/decision_engine_latest.csv`
- `data/processed/macro/decision_actions_latest.csv`

## Rebalance order ticket

`config/portfolio_holdings.csv`에 현재 보유 ETF 수량, 가격, 평가금액을 입력하면 decision engine의 기준 배분과 추천 ETF variant를 사용해 이번 달 매수 주문표를 생성합니다. 가격을 입력하면 예상 매수 수량까지 계산하고, 가격이 없으면 원화 주문 예산을 표시합니다.

보유 현황을 터미널에서 직접 입력하려면:

```bash
python scripts/update_portfolio_holdings.py
```

각 항목에서 Enter를 누르면 기존 값을 유지합니다. 입력이 끝나면 `config/portfolio_holdings.csv`가 저장되고 주문표가 자동 재생성됩니다.

브라우저 입력 폼을 쓰려면:

```bash
python scripts/portfolio_input_server.py
```

실행 후 열리는 `http://127.0.0.1:8765`에서 보유 수량, 가격, 평가금액을 입력하고 저장하면 CSV와 주문표가 함께 갱신됩니다.

```bash
python scripts/generate_rebalance_orders.py
```

결과:

- `reports/rebalance_orders.html`
- `reports/rebalance_orders_latest.md`
- `data/processed/portfolio/rebalance_orders_latest.csv`
- `data/processed/portfolio/portfolio_targets_latest.csv`

## Continuous data refresh

The refresh runner gives the project one operational entry point for scheduled updates. It reads `config/data_refresh.json`, runs only tasks that are due, keeps local state/log files, and writes a health summary.

```bash
python scripts/refresh_data.py --list-tasks
python scripts/refresh_data.py --dry-run
python scripts/refresh_data.py
```

Generated operational files:

- `data/processed/refresh_state.json`
- `data/processed/refresh_runs.jsonl`
- `reports/data_refresh_status.md`

To run a heavier task on demand:

```bash
python scripts/refresh_data.py --task isa_backtests
```

For Windows Task Scheduler, point the action at the repository directory and run:

```powershell
python scripts/refresh_data.py
```

The default config refreshes macro data, change alerts, risk attribution, data quality, the daily decision brief, the scenario simulator, the scenario matrix, scenario ETF backtests, the decision engine, rebalance orders, monthly score history, the monthly dashboard, and the sector HTML dashboard every 24 hours. Edit `config/data_refresh.json` to change cadence, disable tasks, or add new commands.

## ISA ETF 백테스트

월간 레짐 기반 배분을 ISA에서 매수 가능한 국내 상장 ETF로 대체해 백테스트합니다.

```bash
python scripts/generate_monthly_reports.py --start 2012-03
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

### Extending ETF variants

ETF variant runners can load combinations from CSV, so new experiments do not require code edits.

```bash
python scripts/run_actual_etf_variants.py --variants-csv config/actual_etf_variants.example.csv
python scripts/run_isa_etf_max_backtests.py --variants-csv config/isa_etf_max_variants.example.csv
```

CSV columns:

```text
slug,title,start,end,cash_symbol,cash_label,gold_symbol,gold_label,silver_symbol,silver_label,equity_symbol,equity_label,note
```

Use `end` as `latest`, `default`, or blank to follow the script's latest monthly report date. `slug` becomes the output folder/file stem, so use only letters, numbers, underscores, or hyphens.

## Added market and global-rate layer

The macro pipeline also tracks market-confirmation indicators that help validate or challenge the rule-based macro scores.

New market series:

- KOSPI, KOSDAQ, Nikkei 225, S&P 500, NASDAQ Composite, Dow Jones, Russell 2000
- VIX, SOX, Hang Seng, Shanghai Composite, Taiwan Weighted
- Copper futures

New major-rate series:

- Japan, Germany, United Kingdom, Canada, and Australia 10-year government bond yields

New derived indicators:

- US-Japan, US-Germany, and US-Korea 10-year yield gaps
- KOSPI/S&P 500, NASDAQ/S&P 500, SOX/S&P 500, and copper/gold relative strength ratios

These appear in `data/processed/macro/requested_indicators_latest.csv`, `data/processed/macro/observations_long.csv`, and the visual dashboard charts generated by `scripts/visualize_macro_trends.py`.

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
  sector_dashboard.html 섹터별 HTML 대시보드
  decision_engine.html 의사결정 엔진
  decision_engine_latest.md 의사결정 액션 브리프
  rebalance_orders.html 리밸런싱 주문표
  rebalance_orders_latest.md 리밸런싱 주문 브리프
  scenario_simulator.html 시나리오 시뮬레이터
  scenario_matrix.html 시나리오 비교 매트릭스
  scenario_etf_backtests.html 시나리오 ISA ETF 백테스트
  indicators/          지표별 상세 HTML 페이지
  alerts_*.md          변화 감지 알림 리포트
  risk_attribution_*.md 리스크 원인분해 리포트
  data_quality_*.md    데이터 품질/신뢰도 리포트
  daily_brief_*.md     일일 의사결정 브리프
  assets/              리포트 PNG 차트
  backtests/           백테스트 리포트
scripts/
  update_macro.py                  전체 갱신 진입점
  fetch_macro_pipeline.py          매크로 지표 수집/정규화
  fetch_interest_rates.py          BOK/Fed 금리 수집
  analyze_macro_regime.py          레짐 판정 및 리포트 생성
  visualize_macro_trends.py        최신 리포트 차트 생성
  generate_change_alerts.py        변화 감지 알림 생성
  generate_risk_attribution.py     리스크 원인분해 생성
  generate_data_quality_report.py  데이터 품질 점수 생성
  generate_daily_brief.py          일일 의사결정 브리프 생성
  generate_decision_engine.py      의사결정 엔진 생성
  portfolio_input_server.py        보유 포트폴리오 로컬 웹 입력
  update_portfolio_holdings.py     보유 포트폴리오 대화형 입력
  generate_rebalance_orders.py     리밸런싱 주문표 생성
  generate_scenario_simulator.py   시나리오 시뮬레이터 생성
  generate_scenario_matrix.py      저장 시나리오 비교 생성
  generate_scenario_etf_backtests.py 시나리오 ISA ETF 백테스트 연결
  generate_monthly_reports.py      월간 과거 리포트 생성
  visualize_monthly_history.py     월간 대시보드 생성
  generate_sector_dashboard.py     섹터별 HTML 대시보드 생성
  run_isa_etf_max_backtests.py     ISA ETF 장기 백테스트
```

## 문제 해결

`ModuleNotFoundError: matplotlib`가 나오면:

```bash
python -m pip install -r requirements.txt
```

ECOS 호출이 제한되거나 실패하면:

```bash
python scripts/update_macro.py --bok-source homepage-events
```

한글이 터미널이나 에디터에서 깨져 보이면 UTF-8로 열었는지 확인하세요. 저장소는 `.editorconfig`로 `charset = utf-8`을 고정합니다.

Yahoo Finance 호출이 실패하면 네트워크 상태를 확인한 뒤 다시 실행하세요. 원천 응답은 `data/raw/yahoo*` 아래에 저장됩니다.

`fetch_status.csv`에서 `stale` 또는 `error`가 보이면 해당 지표가 오래되었거나 수집에 실패한 것입니다. 리포트는 가능한 데이터로 생성되지만, 레짐 확신도는 낮춰서 해석해야 합니다.
