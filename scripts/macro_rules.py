"""Macro regime scoring and allocation rule constants."""

TOTAL_INVESTMENT_MILLION_KRW = 150
ROUNDING_INCREMENT_MILLION_KRW = 5

SLEEVE_BOUNDS = {
    "cash": (0.35, 0.60),
    "hedge": (0.20, 0.45),
    "equity": (0.15, 0.40),
}

SLEEVE_LABELS = {
    "cash": "현금성/단기채",
    "hedge": "금/은·원자재 헤지",
    "equity": "주식/ETF",
}

ALLOCATION_FORMULAS = {
    "cash": "1.8 + 0.25*Credit + 0.22*Growth + 0.16*FX + 0.08*Inflation",
    "hedge": "1.2 + 0.35*Inflation + 0.30*FX + 0.25*Climate",
    "equity": "1.0 + 0.30*Liquidity + 0.20*(10-Credit) + 0.16*(10-Growth) - 0.15*Inflation - 0.12*FX",
}

RISK_SCORE_FORMULAS = {
    "Inflation Risk": "CPI/Core CPI/PCE/Core PCE/Korea CPI/5Y breakeven/WTI threshold scores, simple average",
    "Liquidity Bubble Risk": "US M2 YoY, US M2 3M, Korea M2 YoY, Fed reserve balances 3M, NFCI, and DXY risk-appetite proxy",
    "Credit Stress Risk": "HY spread, BBB spread, lending standards, financial stress, and business-loan delinquency threshold scores",
    "FX Risk": "Weighted USD/KRW level, USD/KRW 3M, DXY, US-Korea policy-rate gap, foreign flows, and trade balance",
    "Climate Supply Shock Risk": "WTI, natural gas 3M, food/commodity 3M, fertilizer 3M, and GDACS non-green event count",
    "Growth Slowdown Risk": "Unemployment, payroll change, jobless claims, 10Y-2Y spread, and lending standards",
}

KEY_METRIC_LABELS = {
    "us_cpi_all_items": "US CPI",
    "us_core_cpi": "US Core CPI",
    "us_core_pce_price_index": "US Core PCE",
    "korea_cpi_all_items": "Korea CPI",
    "wti_spot": "WTI",
    "fed_policy_rate_mid": "Fed policy",
    "bok_base_rate": "BOK base",
    "us_treasury_10y": "US 10Y",
    "us_10y_2y_spread": "US 10Y-2Y",
    "us_m2": "US M2",
    "korea_m2": "Korea M2",
    "us_chicago_fed_nfci": "NFCI",
    "us_high_yield_spread": "HY spread",
    "us_bbb_spread": "BBB spread",
    "us_financial_stress": "Financial stress",
    "us_bank_lending_standards": "Lending standards",
    "us_business_loan_delinquency_rate": "Delinquency proxy",
    "usd_krw": "USD/KRW",
    "dxy": "DXY",
    "us_minus_korea_policy_rate_gap": "US-Korea gap",
    "korea_current_account": "Current account",
    "korea_trade_balance": "Trade balance",
    "korea_foreign_stock_flows": "Foreign stock flows",
    "korea_foreign_bond_flows": "Foreign bond flows",
    "us_unemployment_rate": "US unemployment",
    "us_nonfarm_payrolls": "Payrolls",
    "us_initial_jobless_claims": "Jobless claims",
    "us_avg_hourly_earnings": "Hourly earnings",
    "henry_hub_natural_gas": "Natural gas",
    "wheat_futures": "Wheat",
    "fertilizer_ppi": "Fertilizer",
    "gdacs_non_green_events_count": "GDACS non-green",
}

HISTORY_FIELDS = [
    "report_date",
    "current_regime",
    "supporting_regime",
    "inflation_risk",
    "liquidity_bubble_risk",
    "credit_stress_risk",
    "fx_risk",
    "climate_supply_shock_risk",
    "growth_slowdown_risk",
    "cash_amount",
    "gold_amount",
    "silver_amount",
    "equity_amount",
]
