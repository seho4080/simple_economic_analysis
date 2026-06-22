"""Macro regime scoring and allocation rule constants."""

TOTAL_INVESTMENT_MILLION_KRW = 150
ROUNDING_INCREMENT_MILLION_KRW = 5

SLEEVE_BOUNDS = {
    "cash": (0.10, 0.50),
    "hedge": (0.15, 0.50),
    "equity": (0.25, 0.65),
}

SLEEVE_LABELS = {
    "cash": "현금성/단기채",
    "hedge": "금/은·원자재 헤지",
    "equity": "주식/ETF",
}

ALLOCATION_FORMULAS = {
    "cash": "0.6 + 0.55*Credit + 0.36*Growth + 0.04*FX - 0.08*Liquidity",
    "hedge": "1.0 + 0.42*Inflation + 0.35*FX + 0.30*Climate",
    "equity": "1.2 + 0.34*Liquidity + 0.25*(10-Credit) + 0.20*(10-Growth) - 0.05*Inflation + 0.08*FX",
}

RISK_SCORE_FORMULAS = {
    "Inflation Risk": "CPI/Core CPI/PCE/Core PCE/Korea CPI/5Y breakeven/WTI threshold scores, simple average",
    "Liquidity Bubble Risk": "US M2 YoY, US M2 3M, Korea M2 YoY, Fed reserve balances 3M, NFCI, and DXY risk-appetite proxy",
    "Credit Stress Risk": "HY spread, BBB spread, lending standards, financial stress, and business-loan delinquency threshold scores",
    "FX Risk": "Weighted USD/KRW level, USD/KRW 3M, DXY, US-Korea policy-rate gap, foreign flows, and trade balance",
    "Climate Supply Shock Risk": "WTI, natural gas 3M, food/commodity 3M, fertilizer 3M, and GDACS non-green event count",
    "Growth Slowdown Risk": "Unemployment, payroll change, jobless claims, 10Y-2Y spread, and lending standards",
}

SUPPLEMENTAL_SCORE_FORMULAS = {
    "Market Stress Risk": "VIX level, KOSPI/S&P 500 3M, SOX/S&P 500 3M, Russell 2000 3M, and copper/gold 3M confirmation scores",
    "Global Rate Divergence Risk": "US-Japan, US-Germany, and US-Korea 10Y yield gaps plus major-market 10Y yield-level pressure",
}

KEY_METRIC_LABELS = {
    "kospi": "KOSPI",
    "kosdaq": "KOSDAQ",
    "nikkei_225": "Nikkei 225",
    "sp500": "S&P 500",
    "nasdaq_composite": "NASDAQ",
    "dow_jones": "Dow Jones",
    "russell_2000": "Russell 2000",
    "vix": "VIX",
    "sox": "SOX",
    "hang_seng": "Hang Seng",
    "shanghai_composite": "Shanghai Composite",
    "taiwan_weighted": "Taiwan Weighted",
    "japan_gov_bond_10y": "Japan 10Y",
    "germany_gov_bond_10y": "Germany 10Y",
    "uk_gov_bond_10y": "UK 10Y",
    "canada_gov_bond_10y": "Canada 10Y",
    "australia_gov_bond_10y": "Australia 10Y",
    "us_japan_10y_gap": "US-Japan 10Y gap",
    "us_germany_10y_gap": "US-Germany 10Y gap",
    "us_korea_10y_gap": "US-Korea 10Y gap",
    "kospi_vs_sp500": "KOSPI/S&P 500",
    "nasdaq_vs_sp500": "NASDAQ/S&P 500",
    "sox_vs_sp500": "SOX/S&P 500",
    "copper_gold_ratio": "Copper/gold",
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
    "market_stress_risk",
    "global_rate_divergence_risk",
    "cash_amount",
    "gold_amount",
    "silver_amount",
    "equity_amount",
]
