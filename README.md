# Economic Indicator Analysis

This repo stores reproducible economic indicator datasets and analysis code.

## One-command refresh

Fetch all wired macro datasets and generate the regime report:

```powershell
python scripts/update_macro.py
```

Outputs:

- `data/processed/macro/requested_indicators_latest.csv`
- `data/processed/macro/latest_snapshot.csv`
- `data/processed/macro/observations_long.csv`
- `data/processed/macro/fetch_status.csv`
- `reports/macro_regime_YYYY-MM-DD.md`

Fetch data only:

```powershell
python scripts/update_macro.py --no-report
```

## Interest-rate data

Fetch only Bank of Korea and Federal Reserve rate datasets:

```powershell
python scripts/fetch_interest_rates.py
```

Outputs:

- `data/raw/rates/bok_base_rate_events_homepage.html`
- `data/raw/rates/fed_funds_effective_daily_h15.csv`
- `data/raw/rates/fed_funds_target_events_openmarket.json`
- `data/processed/rates/bok_base_rate_events.csv`
- `data/processed/rates/bok_base_rate_daily.csv`
- `data/processed/rates/fed_funds_effective_daily.csv`
- `data/processed/rates/fed_funds_target_events.csv`
- `data/processed/rates/fed_funds_target_daily.csv`
- `data/processed/rates/central_bank_policy_rates_daily.csv`
- `data/processed/rates/all_interest_rates_daily.csv`

Sources:

- Bank of Korea official base-rate history page: base-rate change events
- Federal Reserve H.15 DDP `H15/H15/RIFSPFF_N.D`: federal funds effective rate
- Federal Reserve Open Market Operations: FOMC target federal funds rate/range changes

The script uses `BOK_API_KEY` with ECOS when available. Without a real ECOS key,
it uses the official Bank of Korea base-rate history page and expands the event
history to a daily policy-rate series. To force ECOS, run:

```powershell
python scripts/fetch_interest_rates.py --bok-source ecos
```

## Macro indicator pipeline

Fetch only the broader macro checklist used by the regime-analysis agent:

```powershell
python scripts/fetch_macro_pipeline.py
```

Main outputs:

- `data/processed/macro/indicator_catalog.csv`: source catalog for each indicator
- `data/processed/macro/observations_long.csv`: normalized long-format observations
- `data/processed/macro/latest_snapshot.csv`: latest value plus 1M/3M/6M/12M changes
- `data/processed/macro/requested_indicators_latest.csv`: dashboard-shaped file matching the user checklist
- `data/processed/macro/fetch_status.csv`: source-by-source fetch status
- `data/processed/macro/climate_events_gdacs.csv`: current GDACS natural-hazard events
- `data/manual/manual_indicators.csv`: optional manual inputs for items that need paid/proprietary or local-market feeds

The dashboard file marks stale observations with `status=stale`, so lagged
fallback feeds do not silently look current.

Sources currently wired:

- Bank of Korea ECOS: Korea CPI, Korea M2, key Korean macro statistics
- Bank of Korea ECOS: customs exports/imports, derived trade balance, and balance-of-payments portfolio investment liabilities
- Bank of Korea base-rate history page: BOK policy-rate events
- Federal Reserve H.15 and Open Market Operations: Fed effective and target rates
- FRED: US inflation, Treasury yields, M2, financial conditions, credit spreads, business-loan delinquency proxy, FX, employment, and several commodity proxies
- Yahoo Finance chart API: DXY and commodity futures prices
- GDACS RSS: current natural-hazard events

Manual or future-feed items:

- `us_default_rate`: optional exact corporate default-rate override. The automated dashboard uses FRED `DRBLACBS` as a business-loan delinquency proxy.
- `korea_foreign_stock_flows_manual`: optional KRX/FSS daily or monthly override
- `korea_foreign_bond_flows_manual`: optional KOFIA/FSS daily or monthly override

Useful options:

```powershell
python scripts/fetch_macro_pipeline.py --skip-rates
python scripts/fetch_macro_pipeline.py --bok-key $env:BOK_API_KEY
python scripts/fetch_macro_pipeline.py --yahoo-range 10y
```

## Macro regime report

Generate a markdown regime report from the latest processed macro snapshot:

```powershell
python scripts/analyze_macro_regime.py
```

Output:

- `reports/macro_regime_YYYY-MM-DD.md`

The report uses the fixed Korean format for:

- current regime and supporting regime
- indicator-by-indicator interpretation
- six risk scores
- monthly ISA 150만원 allocation proposal
- adjustment actions, checkpoints, and opposite scenarios

Typical refresh flow:

```powershell
python scripts/update_macro.py
```
