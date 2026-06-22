# Data Quality Report

Generated at: 2026-06-21T23:42:33
Report date: 2026-06-21

## Summary
- Overall confidence score: 98.0 / 100 (A)
- Freshness score: 95.9 / 100
- Fetch score: 100.0 / 100
- Risk coverage score: 100.0 / 100

## Scores By Category
| Category | Indicators | Stale | Freshness | Grade |
| --- | --- | --- | --- | --- |
| climate | 2 | 0 | 100.0 | A |
| commodities | 13 | 0 | 100.0 | A |
| credit | 5 | 0 | 100.0 | A |
| employment | 6 | 0 | 100.0 | A |
| fx | 11 | 2 | 88.2 | A |
| inflation | 15 | 3 | 87.0 | A |
| liquidity | 8 | 1 | 91.9 | A |
| market | 11 | 0 | 100.0 | A |
| market_derived | 4 | 0 | 100.0 | A |
| market_stress | 1 | 0 | 100.0 | A |
| rates | 12 | 0 | 100.0 | A |
| rates_global | 8 | 0 | 100.0 | A |

## Scores By Risk
| Risk | Drivers | Stale | Coverage | Overall | Grade |
| --- | --- | --- | --- | --- | --- |
| Climate Supply Shock Risk | 11 | 0 | 100.0 | 100.0 | A |
| Credit Stress Risk | 5 | 0 | 100.0 | 100.0 | A |
| FX Risk | 7 | 0 | 100.0 | 100.0 | A |
| Global Rate Divergence Risk | 9 | 0 | 100.0 | 100.0 | A |
| Growth Slowdown Risk | 8 | 0 | 100.0 | 100.0 | A |
| Inflation Risk | 13 | 0 | 100.0 | 100.0 | A |
| Liquidity Bubble Risk | 7 | 0 | 100.0 | 100.0 | A |
| Market Stress Risk | 5 | 0 | 100.0 | 100.0 | A |

## Stale Indicators
| Indicator | Category | Latest date | Age days | Source |
| --- | --- | --- | --- | --- |
| korea_m2_fred | liquidity | 2017-05-01 | 3338 | FRED |
| korea_cpi_food_fred | inflation | 2018-05-01 | 2973 | FRED |
| korea_cpi_all_items_fred | inflation | 2023-11-01 | 963 | FRED |
| korea_current_account_fred | fx | 2024-01-01 | 902 | FRED |
| korea_trade_balance_fred | fx | 2024-12-01 | 567 | FRED |
| korea_cpi_energy_fred | inflation | 2025-04-01 | 446 | FRED |

## Fetch Problems
No fetch problems in the latest status table.

## Method
- Overall = 50% freshness + 30% fetch health + 20% risk-driver coverage.
- Stale indicators receive partial freshness credit rather than zero, because fallback series can still be useful with caution.
- Risk coverage is based on mapped drivers in `risk_attribution_latest.csv`.
- Raw status counts: {"snapshot_rows": 96, "fetch_rows": 84}
