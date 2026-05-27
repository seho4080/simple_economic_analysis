#!/usr/bin/env python3
"""Fetch macro indicators used by the regime-analysis workflow.

The pipeline writes normalized observations, latest snapshots, and a
dashboard-shaped CSV matching the user's macro checklist.
"""

from __future__ import annotations

import argparse
import csv
import email.utils
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

import fetch_interest_rates


USER_AGENT = "stock-economic-indicators/0.2"


@dataclass(frozen=True)
class SeriesSpec:
    indicator_id: str
    name_ko: str
    category: str
    country: str
    source_type: str
    source_series_id: str
    unit: str
    frequency: str
    source: str
    notes: str = ""

    @property
    def source_url(self) -> str:
        if self.source_type == "fred":
            return fred_url(self.source_series_id)
        if self.source_type == "yahoo":
            quoted = urllib.parse.quote(self.source_series_id, safe="")
            return f"https://query1.finance.yahoo.com/v8/finance/chart/{quoted}"
        if self.source_type == "ecos":
            return "https://ecos.bok.or.kr/api/"
        if self.source_type == "bok_key":
            return "https://ecos.bok.or.kr/api/KeyStatisticList/"
        if self.source_type == "derived":
            return "derived"
        if self.source_type == "manual":
            return "data/manual/manual_indicators.csv"
        return ""


@dataclass(frozen=True)
class DashboardField:
    field_ko: str
    category: str
    indicator_id: str
    metric: str
    metric_ko: str
    unit: str
    note: str = ""
    status_override: str = ""


ECOS_CONFIG = {
    "korea_cpi_all_items": ("901Y009", "0", "M", 24),
    "korea_cpi_food": ("901Y009", "A01", "M", 24),
    "korea_cpi_energy": ("901Y009", "D05", "M", 24),
    "korea_m2": ("161Y005", "BBHS00", "M", 24),
    "korea_trade_exports": ("901Y118", "T002", "M", 24),
    "korea_trade_imports": ("901Y118", "T004", "M", 24),
    "korea_foreign_stock_flows": ("301Y013", "BOPF22100000", "M", 24),
    "korea_foreign_bond_flows": ("301Y013", "BOPF22200000", "M", 24),
}


ECOS_SERIES: list[SeriesSpec] = [
    SeriesSpec("korea_cpi_all_items", "한국 CPI", "inflation", "Korea", "ecos", "901Y009:0", "index", "monthly", "Bank of Korea ECOS"),
    SeriesSpec("korea_cpi_food", "한국 식품 CPI", "inflation", "Korea", "ecos", "901Y009:A01", "index", "monthly", "Bank of Korea ECOS"),
    SeriesSpec("korea_cpi_energy", "한국 에너지 CPI", "inflation", "Korea", "ecos", "901Y009:D05", "index", "monthly", "Bank of Korea ECOS", "Electricity, gas, and other fuels CPI proxy."),
    SeriesSpec("korea_m2", "한국 M2", "liquidity", "Korea", "ecos", "161Y005:BBHS00", "billions_krw", "monthly", "Bank of Korea ECOS"),
    SeriesSpec("korea_trade_exports", "한국 통관수출", "fx", "Korea", "ecos", "901Y118:T002", "thousand_usd", "monthly", "Bank of Korea ECOS"),
    SeriesSpec("korea_trade_imports", "한국 통관수입", "fx", "Korea", "ecos", "901Y118:T004", "thousand_usd", "monthly", "Bank of Korea ECOS"),
    SeriesSpec("korea_foreign_stock_flows", "외국인 주식 자금흐름", "fx", "Korea", "ecos", "301Y013:BOPF22100000", "million_usd", "monthly", "Bank of Korea ECOS", "Balance of payments portfolio investment liabilities, equity securities."),
    SeriesSpec("korea_foreign_bond_flows", "외국인 채권 자금흐름", "fx", "Korea", "ecos", "301Y013:BOPF22200000", "million_usd", "monthly", "Bank of Korea ECOS", "Balance of payments portfolio investment liabilities, debt securities."),
]


BOK_KEYSTAT_MAP: dict[str, SeriesSpec] = {
    "원/달러 환율(종가)": SeriesSpec("usd_krw", "달러/원 환율", "fx", "Korea", "bok_key", "원/달러 환율(종가)", "krw_per_usd", "daily", "Bank of Korea ECOS KeyStatisticList"),
    "경상수지": SeriesSpec("korea_current_account", "한국 경상수지", "fx", "Korea", "bok_key", "경상수지", "million_usd", "monthly", "Bank of Korea ECOS KeyStatisticList"),
    "CD수익률(91일)": SeriesSpec("korea_short_rate_3m", "한국 CD91일 금리", "rates", "Korea", "bok_key", "CD수익률(91일)", "percent", "daily", "Bank of Korea ECOS KeyStatisticList"),
    "실업률": SeriesSpec("korea_unemployment_rate", "한국 실업률", "employment", "Korea", "bok_key", "실업률", "percent", "monthly", "Bank of Korea ECOS KeyStatisticList"),
    "고용률": SeriesSpec("korea_employment_rate", "한국 고용률", "employment", "Korea", "bok_key", "고용률", "percent", "monthly", "Bank of Korea ECOS KeyStatisticList"),
}


FRED_SERIES: list[SeriesSpec] = [
    SeriesSpec("us_cpi_all_items", "미국 CPI", "inflation", "United States", "fred", "CPIAUCSL", "index", "monthly", "FRED"),
    SeriesSpec("us_core_cpi", "미국 Core CPI", "inflation", "United States", "fred", "CPILFESL", "index", "monthly", "FRED"),
    SeriesSpec("us_cpi_food", "미국 식품 CPI", "inflation", "United States", "fred", "CPIUFDSL", "index", "monthly", "FRED"),
    SeriesSpec("us_cpi_energy", "미국 에너지 CPI", "inflation", "United States", "fred", "CPIENGSL", "index", "monthly", "FRED"),
    SeriesSpec("us_pce_price_index", "미국 PCE 물가지수", "inflation", "United States", "fred", "PCEPI", "index", "monthly", "FRED"),
    SeriesSpec("us_core_pce_price_index", "미국 Core PCE 물가지수", "inflation", "United States", "fred", "PCEPILFE", "index", "monthly", "FRED"),
    SeriesSpec("korea_cpi_all_items_fred", "한국 CPI(FRED fallback)", "inflation", "Korea", "fred", "KORCPIALLMINMEI", "index", "monthly", "FRED", "OECD/FRED fallback; primary feed is Bank of Korea ECOS."),
    SeriesSpec("korea_cpi_food_fred", "한국 식품 CPI(FRED fallback)", "inflation", "Korea", "fred", "KORCPIFODMINMEI", "index", "monthly", "FRED", "OECD/FRED fallback; primary feed is Bank of Korea ECOS."),
    SeriesSpec("korea_cpi_energy_fred", "한국 에너지 CPI(FRED fallback)", "inflation", "Korea", "fred", "KORCPIENGMINMEI", "index", "monthly", "FRED", "OECD/FRED fallback; primary feed is Bank of Korea ECOS."),
    SeriesSpec("us_michigan_expected_inflation", "미국 미시간대 1년 기대인플레", "inflation", "United States", "fred", "MICH", "percent", "monthly", "FRED"),
    SeriesSpec("us_5y_breakeven_inflation", "미국 5년 기대인플레", "inflation", "United States", "fred", "T5YIE", "percent", "daily", "FRED"),
    SeriesSpec("us_10y_breakeven_inflation", "미국 10년 기대인플레", "inflation", "United States", "fred", "T10YIE", "percent", "daily", "FRED"),
    SeriesSpec("us_treasury_3m", "미국 3개월 국채금리", "rates", "United States", "fred", "DGS3MO", "percent", "daily", "FRED"),
    SeriesSpec("us_treasury_2y", "미국 2년 국채금리", "rates", "United States", "fred", "DGS2", "percent", "daily", "FRED"),
    SeriesSpec("us_treasury_10y", "미국 10년 국채금리", "rates", "United States", "fred", "DGS10", "percent", "daily", "FRED"),
    SeriesSpec("us_10y_2y_spread", "미국 10년-2년 금리차", "rates", "United States", "fred", "T10Y2Y", "percentage_point", "daily", "FRED"),
    SeriesSpec("us_10y_3m_spread", "미국 10년-3개월 금리차", "rates", "United States", "fred", "T10Y3M", "percentage_point", "daily", "FRED"),
    SeriesSpec("korea_short_rate_3m", "한국 3개월 단기금리", "rates", "Korea", "fred", "IR3TIB01KRM156N", "percent", "monthly", "FRED"),
    SeriesSpec("korea_gov_bond_10y", "한국 10년 국채금리", "rates", "Korea", "fred", "IRLTLT01KRM156N", "percent", "monthly", "FRED"),
    SeriesSpec("us_m2", "미국 M2", "liquidity", "United States", "fred", "M2SL", "billions_usd", "monthly", "FRED"),
    SeriesSpec("korea_m2_fred", "한국 M2(FRED fallback)", "liquidity", "Korea", "fred", "MYAGM2KRM189S", "krw", "monthly", "FRED", "FRED fallback; primary feed is Bank of Korea ECOS."),
    SeriesSpec("us_chicago_fed_nfci", "미국 금융여건지수", "liquidity", "United States", "fred", "NFCI", "index", "weekly", "FRED"),
    SeriesSpec("fed_balance_sheet_assets", "연준 총자산", "liquidity", "United States", "fred", "WALCL", "millions_usd", "weekly", "FRED"),
    SeriesSpec("fed_reserve_balances", "연준 지급준비금", "liquidity", "United States", "fred", "WRESBAL", "millions_usd", "weekly", "FRED"),
    SeriesSpec("fed_reverse_repo", "연준 역레포", "liquidity", "United States", "fred", "RRPONTSYD", "billions_usd", "daily", "FRED"),
    SeriesSpec("us_sofr", "미국 SOFR", "liquidity", "United States", "fred", "SOFR", "percent", "daily", "FRED"),
    SeriesSpec("us_high_yield_spread", "미국 하이일드 스프레드", "credit", "United States", "fred", "BAMLH0A0HYM2", "percentage_point", "daily", "FRED"),
    SeriesSpec("us_bbb_spread", "미국 BBB 스프레드", "credit", "United States", "fred", "BAMLC0A4CBBB", "percentage_point", "daily", "FRED"),
    SeriesSpec("us_bank_lending_standards", "미국 은행 대출태도", "credit", "United States", "fred", "DRTSCILM", "net_percent", "quarterly", "FRED"),
    SeriesSpec("us_financial_stress", "미국 금융시장 스트레스 지표", "credit", "United States", "fred", "STLFSI4", "index", "weekly", "FRED"),
    SeriesSpec("us_business_loan_delinquency_rate", "미국 기업대출 연체율", "credit", "United States", "fred", "DRBLACBS", "percent", "quarterly", "FRED", "Proxy for default stress; exact US corporate default-rate series is usually proprietary or report-based."),
    SeriesSpec("usd_krw", "달러/원 환율", "fx", "Korea", "fred", "DEXKOUS", "krw_per_usd", "daily", "FRED"),
    SeriesSpec("us_broad_dollar_index", "미국 광의 달러지수", "fx", "United States", "fred", "DTWEXBGS", "index", "daily", "FRED"),
    SeriesSpec("korea_current_account_fred", "한국 경상수지(FRED fallback)", "fx", "Korea", "fred", "KORBCABP6USD", "usd", "annual", "FRED", "Annual IMF/FRED fallback; primary latest feed is Bank of Korea KeyStatisticList."),
    SeriesSpec("korea_trade_balance_fred", "한국 무역수지(FRED fallback)", "fx", "Korea", "fred", "XTNTVA01KRM664S", "usd", "monthly", "FRED", "Fallback only; primary feed is derived from BOK ECOS customs exports minus imports."),
    SeriesSpec("us_unemployment_rate", "미국 실업률", "employment", "United States", "fred", "UNRATE", "percent", "monthly", "FRED"),
    SeriesSpec("us_nonfarm_payrolls", "미국 비농업고용", "employment", "United States", "fred", "PAYEMS", "thousands_persons", "monthly", "FRED"),
    SeriesSpec("us_initial_jobless_claims", "미국 신규 실업수당 청구", "employment", "United States", "fred", "ICSA", "persons", "weekly", "FRED"),
    SeriesSpec("us_avg_hourly_earnings", "미국 시간당 임금", "employment", "United States", "fred", "CES0500000003", "usd_per_hour", "monthly", "FRED"),
    SeriesSpec("korea_unemployment_rate", "한국 실업률", "employment", "Korea", "fred", "LRUN64TTKRM156S", "percent", "monthly", "FRED"),
    SeriesSpec("korea_employment_rate", "한국 고용률", "employment", "Korea", "fred", "LREM64TTKRM156S", "percent", "monthly", "FRED"),
    SeriesSpec("wti_spot", "WTI", "commodities", "United States", "fred", "DCOILWTICO", "usd_per_barrel", "daily", "FRED"),
    SeriesSpec("henry_hub_natural_gas", "미국 천연가스", "commodities", "United States", "fred", "DHHNGSP", "usd_per_mmbtu", "daily", "FRED"),
    SeriesSpec("fertilizer_ppi", "비료 가격지수", "commodities", "United States", "fred", "WPS0652", "index", "monthly", "FRED"),
]


YAHOO_SERIES: list[SeriesSpec] = [
    SeriesSpec("dxy", "DXY", "fx", "United States", "yahoo", "DX-Y.NYB", "index", "daily", "Yahoo Finance"),
    SeriesSpec("gold_futures", "금 선물", "commodities", "Global", "yahoo", "GC=F", "usd_per_oz", "daily", "Yahoo Finance"),
    SeriesSpec("silver_futures", "은 선물", "commodities", "Global", "yahoo", "SI=F", "usd_per_oz", "daily", "Yahoo Finance"),
    SeriesSpec("wheat_futures", "밀 선물", "commodities", "Global", "yahoo", "ZW=F", "us_cents_per_bushel", "daily", "Yahoo Finance"),
    SeriesSpec("corn_futures", "옥수수 선물", "commodities", "Global", "yahoo", "ZC=F", "us_cents_per_bushel", "daily", "Yahoo Finance"),
    SeriesSpec("soybean_futures", "대두 선물", "commodities", "Global", "yahoo", "ZS=F", "us_cents_per_bushel", "daily", "Yahoo Finance"),
    SeriesSpec("rough_rice_futures", "쌀 선물", "commodities", "Global", "yahoo", "ZR=F", "usd_per_cwt", "daily", "Yahoo Finance"),
    SeriesSpec("coffee_futures", "커피 선물", "commodities", "Global", "yahoo", "KC=F", "us_cents_per_lb", "daily", "Yahoo Finance"),
    SeriesSpec("cocoa_futures", "코코아 선물", "commodities", "Global", "yahoo", "CC=F", "usd_per_tonne", "daily", "Yahoo Finance"),
    SeriesSpec("sugar_futures", "설탕 선물", "commodities", "Global", "yahoo", "SB=F", "us_cents_per_lb", "daily", "Yahoo Finance"),
]


DERIVED_SERIES: list[SeriesSpec] = [
    SeriesSpec("fed_policy_rate_mid", "Fed 기준금리 중간값", "rates", "United States", "derived", "fed_funds_target_daily.csv", "percent", "daily", "Federal Reserve Open Market Operations"),
    SeriesSpec("fed_funds_effective", "Fed 유효연방기금금리", "rates", "United States", "derived", "fed_funds_effective_daily.csv", "percent", "daily", "Federal Reserve H.15"),
    SeriesSpec("bok_base_rate", "한국은행 기준금리", "rates", "Korea", "derived", "bok_base_rate_daily.csv", "percent", "daily", "Bank of Korea"),
    SeriesSpec("us_minus_korea_policy_rate_gap", "한미 기준금리차(미국-한국)", "rates", "United States/Korea", "derived", "fed_policy_rate_mid-bok_base_rate", "percentage_point", "daily", "Derived"),
    SeriesSpec("korea_10y_3m_spread", "한국 10년-3개월 금리차", "rates", "Korea", "derived", "korea_gov_bond_10y-korea_short_rate_3m", "percentage_point", "monthly", "Derived"),
    SeriesSpec("korea_trade_balance", "한국 무역수지", "fx", "Korea", "derived", "korea_trade_exports-korea_trade_imports", "million_usd", "monthly", "Derived from Bank of Korea ECOS"),
    SeriesSpec("gdacs_current_events_count", "GDACS 현재 자연재해 이벤트 수", "climate", "Global", "derived", "gdacs_rss", "events", "snapshot", "GDACS"),
    SeriesSpec("gdacs_non_green_events_count", "GDACS 주황/적색 자연재해 이벤트 수", "climate", "Global", "derived", "gdacs_rss", "events", "snapshot", "GDACS"),
]


MANUAL_SERIES: list[SeriesSpec] = [
    SeriesSpec("us_default_rate", "미국 부도율", "credit", "United States", "manual", "manual_indicators.csv", "percent", "monthly", "Manual", "Optional exact corporate default rate override if a licensed/report source is available."),
    SeriesSpec("korea_foreign_stock_flows_manual", "외국인 주식 자금흐름(수기)", "fx", "Korea", "manual", "manual_indicators.csv", "krw", "daily_or_monthly", "Manual"),
    SeriesSpec("korea_foreign_bond_flows_manual", "외국인 채권 자금흐름(수기)", "fx", "Korea", "manual", "manual_indicators.csv", "krw", "daily_or_monthly", "Manual"),
    SeriesSpec("climate_supply_shock_note", "이상기후/공급충격 메모", "climate", "Global", "manual", "manual_indicators.csv", "text", "event", "Manual"),
]


DASHBOARD_FIELDS: list[DashboardField] = [
    DashboardField("미국 CPI YoY", "inflation", "us_cpi_all_items", "pct_change_12m", "YoY", "percent"),
    DashboardField("미국 Core CPI YoY", "inflation", "us_core_cpi", "pct_change_12m", "YoY", "percent"),
    DashboardField("미국 PCE YoY", "inflation", "us_pce_price_index", "pct_change_12m", "YoY", "percent"),
    DashboardField("미국 Core PCE YoY", "inflation", "us_core_pce_price_index", "pct_change_12m", "YoY", "percent"),
    DashboardField("한국 CPI YoY", "inflation", "korea_cpi_all_items", "pct_change_12m", "YoY", "percent"),
    DashboardField("식품 CPI YoY", "inflation", "korea_cpi_food", "pct_change_12m", "YoY", "percent", "현재는 한국 식품 CPI 기준"),
    DashboardField("에너지 CPI YoY", "inflation", "korea_cpi_energy", "pct_change_12m", "YoY", "percent", "현재는 한국 에너지 CPI 기준"),
    DashboardField("기대인플레", "inflation", "us_5y_breakeven_inflation", "latest_value", "Latest", "percent", "시장 기반 5년 기대인플레. 설문형은 MICH도 함께 수집"),
    DashboardField("Fed 기준금리", "rates", "fed_policy_rate_mid", "latest_value", "Latest", "percent", "상하단 범위의 중간값"),
    DashboardField("한국은행 기준금리", "rates", "bok_base_rate", "latest_value", "Latest", "percent"),
    DashboardField("미국 3개월물", "rates", "us_treasury_3m", "latest_value", "Latest", "percent"),
    DashboardField("미국 2년물", "rates", "us_treasury_2y", "latest_value", "Latest", "percent"),
    DashboardField("미국 10년물", "rates", "us_treasury_10y", "latest_value", "Latest", "percent"),
    DashboardField("한국 3개월물/CD91일", "rates", "korea_short_rate_3m", "latest_value", "Latest", "percent", "FRED/OECD 3개월 단기금리 프록시"),
    DashboardField("한국 10년물", "rates", "korea_gov_bond_10y", "latest_value", "Latest", "percent"),
    DashboardField("한미 기준금리차", "rates", "us_minus_korea_policy_rate_gap", "latest_value", "Latest", "percentage_point", "미국 Fed target midpoint - 한국은행 기준금리"),
    DashboardField("장단기 금리차(미국 10Y-2Y)", "rates", "us_10y_2y_spread", "latest_value", "Latest", "percentage_point"),
    DashboardField("장단기 금리차(한국 10Y-3M)", "rates", "korea_10y_3m_spread", "latest_value", "Latest", "percentage_point"),
    DashboardField("미국 M2 YoY", "liquidity", "us_m2", "pct_change_12m", "YoY", "percent"),
    DashboardField("미국 M2 3개월 변화율", "liquidity", "us_m2", "pct_change_3m", "3M change", "percent"),
    DashboardField("한국 M2 YoY", "liquidity", "korea_m2", "pct_change_12m", "YoY", "percent"),
    DashboardField("금융여건지수", "liquidity", "us_chicago_fed_nfci", "latest_value", "Latest", "index"),
    DashboardField("달러 유동성: 연준 총자산 3M", "liquidity", "fed_balance_sheet_assets", "pct_change_3m", "3M change", "percent"),
    DashboardField("달러 유동성: 지급준비금 3M", "liquidity", "fed_reserve_balances", "pct_change_3m", "3M change", "percent"),
    DashboardField("달러 유동성: 역레포", "liquidity", "fed_reverse_repo", "latest_value", "Latest", "billions_usd"),
    DashboardField("미국 하이일드 스프레드", "credit", "us_high_yield_spread", "latest_value", "Latest", "percentage_point"),
    DashboardField("BBB 스프레드", "credit", "us_bbb_spread", "latest_value", "Latest", "percentage_point"),
    DashboardField("부도율", "credit", "us_business_loan_delinquency_rate", "latest_value", "Latest", "percent", "정확한 회사채 부도율이 아니라 미국 기업대출 연체율 프록시"),
    DashboardField("은행 대출태도", "credit", "us_bank_lending_standards", "latest_value", "Latest", "net_percent"),
    DashboardField("금융시장 스트레스 지표", "credit", "us_financial_stress", "latest_value", "Latest", "index"),
    DashboardField("USD/KRW", "fx", "usd_krw", "latest_value", "Latest", "krw_per_usd"),
    DashboardField("DXY", "fx", "dxy", "latest_value", "Latest", "index"),
    DashboardField("경상수지", "fx", "korea_current_account", "latest_value", "Latest", "million_usd", "BOK KeyStatisticList 최신값"),
    DashboardField("무역수지", "fx", "korea_trade_balance", "latest_value", "Latest", "million_usd", "ECOS 통관수출-통관수입 계산값"),
    DashboardField("외국인 주식 자금흐름", "fx", "korea_foreign_stock_flows", "latest_value", "Latest", "million_usd", "국제수지 증권투자 부채 중 주식"),
    DashboardField("외국인 채권 자금흐름", "fx", "korea_foreign_bond_flows", "latest_value", "Latest", "million_usd", "국제수지 증권투자 부채 중 부채성증권"),
    DashboardField("미국 실업률", "employment", "us_unemployment_rate", "latest_value", "Latest", "percent"),
    DashboardField("미국 비농업고용", "employment", "us_nonfarm_payrolls", "change_1_obs", "MoM change", "thousands_persons"),
    DashboardField("신규 실업수당 청구", "employment", "us_initial_jobless_claims", "latest_value", "Latest", "persons"),
    DashboardField("임금상승률", "employment", "us_avg_hourly_earnings", "pct_change_12m", "YoY", "percent"),
    DashboardField("한국 실업률", "employment", "korea_unemployment_rate", "latest_value", "Latest", "percent"),
    DashboardField("한국 고용률", "employment", "korea_employment_rate", "latest_value", "Latest", "percent"),
    DashboardField("금 가격", "commodities", "gold_futures", "latest_value", "Latest", "usd_per_oz"),
    DashboardField("은 가격", "commodities", "silver_futures", "latest_value", "Latest", "usd_per_oz"),
    DashboardField("WTI", "commodities", "wti_spot", "latest_value", "Latest", "usd_per_barrel"),
    DashboardField("천연가스/LNG", "commodities", "henry_hub_natural_gas", "latest_value", "Latest", "usd_per_mmbtu", "Henry Hub 프록시"),
    DashboardField("밀", "commodities", "wheat_futures", "latest_value", "Latest", "us_cents_per_bushel"),
    DashboardField("옥수수", "commodities", "corn_futures", "latest_value", "Latest", "us_cents_per_bushel"),
    DashboardField("대두", "commodities", "soybean_futures", "latest_value", "Latest", "us_cents_per_bushel"),
    DashboardField("쌀", "commodities", "rough_rice_futures", "latest_value", "Latest", "usd_per_cwt"),
    DashboardField("커피", "commodities", "coffee_futures", "latest_value", "Latest", "us_cents_per_lb"),
    DashboardField("코코아", "commodities", "cocoa_futures", "latest_value", "Latest", "usd_per_tonne"),
    DashboardField("설탕", "commodities", "sugar_futures", "latest_value", "Latest", "us_cents_per_lb"),
    DashboardField("비료 가격", "commodities", "fertilizer_ppi", "latest_value", "Latest", "index"),
    DashboardField("주요 이상기후 이벤트", "climate", "gdacs_non_green_events_count", "latest_value", "Latest", "events", "상세 이벤트는 climate_events_gdacs.csv 확인"),
]


OBSERVATION_FIELDS = [
    "date",
    "indicator_id",
    "name_ko",
    "category",
    "country",
    "value",
    "unit",
    "frequency",
    "source_type",
    "source",
    "source_series_id",
    "source_url",
    "notes",
]


SNAPSHOT_FIELDS = [
    "indicator_id",
    "name_ko",
    "category",
    "country",
    "latest_date",
    "latest_value",
    "age_days",
    "freshness_status",
    "unit",
    "frequency",
    "previous_date",
    "previous_value",
    "change_1_obs",
    "pct_change_1_obs",
    "date_1m",
    "value_1m",
    "change_1m",
    "pct_change_1m",
    "date_3m",
    "value_3m",
    "change_3m",
    "pct_change_3m",
    "date_6m",
    "value_6m",
    "change_6m",
    "pct_change_6m",
    "date_12m",
    "value_12m",
    "change_12m",
    "pct_change_12m",
    "source",
    "source_series_id",
    "source_url",
    "notes",
]


DASHBOARD_FIELDS_OUT = [
    "field_ko",
    "category",
    "indicator_id",
    "metric",
    "metric_ko",
    "value",
    "unit",
    "latest_date",
    "latest_raw_value",
    "latest_raw_unit",
    "age_days",
    "freshness_status",
    "pct_change_3m",
    "pct_change_6m",
    "pct_change_12m",
    "source",
    "source_series_id",
    "source_url",
    "status",
    "note",
]


FETCH_STATUS_FIELDS = [
    "source_type",
    "indicator_id",
    "source_series_id",
    "status",
    "rows",
    "message",
]


def fred_url(series_id: str) -> str:
    return f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"


def fetch_bytes(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def parse_float(value: str | int | float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if math.isnan(value):
            return None
        return float(value)
    stripped = str(value).strip().replace(",", "")
    if stripped in {"", ".", "NA", "N/A", "null", "None"}:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def write_csv(path: Path, rows: Iterable[dict], fieldnames: list[str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
            count += 1
    return count


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def observation(spec: SeriesSpec, obs_date: str, value: float) -> dict:
    return {
        "date": obs_date,
        "indicator_id": spec.indicator_id,
        "name_ko": spec.name_ko,
        "category": spec.category,
        "country": spec.country,
        "value": value,
        "unit": spec.unit,
        "frequency": spec.frequency,
        "source_type": spec.source_type,
        "source": spec.source,
        "source_series_id": spec.source_series_id,
        "source_url": spec.source_url,
        "notes": spec.notes,
    }


def fetch_fred_series(spec: SeriesSpec, raw_dir: Path) -> tuple[list[dict], dict]:
    url = fred_url(spec.source_series_id)
    raw = fetch_bytes(url, timeout=60)
    raw_path = raw_dir / f"{spec.source_series_id}.csv"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw)

    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    rows: list[dict] = []
    for row in reader:
        obs_date = row.get("observation_date")
        if not obs_date:
            continue
        value = parse_float(row.get(spec.source_series_id))
        if value is None:
            continue
        rows.append(observation(spec, obs_date, value))
    return rows, {
        "source_type": spec.source_type,
        "indicator_id": spec.indicator_id,
        "source_series_id": spec.source_series_id,
        "status": "ok",
        "rows": len(rows),
        "message": "",
    }


def fetch_yahoo_series(spec: SeriesSpec, raw_dir: Path, range_arg: str) -> tuple[list[dict], dict]:
    quoted = urllib.parse.quote(spec.source_series_id, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{quoted}"
        f"?range={urllib.parse.quote(range_arg)}&interval=1d"
    )
    raw = fetch_bytes(url, timeout=60)
    raw_path = raw_dir / f"{safe_filename(spec.source_series_id)}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw)

    payload = json.loads(raw.decode("utf-8"))
    chart = payload.get("chart", {})
    error = chart.get("error")
    if error:
        raise RuntimeError(error)
    results = chart.get("result") or []
    if not results:
        raise RuntimeError("No Yahoo chart result")
    result = results[0]
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []

    rows: list[dict] = []
    for ts, close in zip(timestamps, closes):
        value = parse_float(close)
        if value is None:
            continue
        obs_date = datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
        rows.append(observation(spec, obs_date, value))
    return rows, {
        "source_type": spec.source_type,
        "indicator_id": spec.indicator_id,
        "source_series_id": spec.source_series_id,
        "status": "ok",
        "rows": len(rows),
        "message": "",
    }


def ecos_url(
    api_key: str,
    start_count: int,
    end_count: int,
    stat_code: str,
    cycle: str,
    start_period: str,
    end_period: str,
    item_code: str,
) -> str:
    parts = [
        "https://ecos.bok.or.kr/api/StatisticSearch",
        urllib.parse.quote(api_key),
        "json",
        "kr",
        str(start_count),
        str(end_count),
        stat_code,
        cycle,
        start_period,
        end_period,
        urllib.parse.quote(item_code),
    ]
    return "/".join(parts)


def month_period(value: date) -> str:
    return f"{value.year:04d}{value.month:02d}"


def period_to_iso(period: str, cycle: str) -> str:
    if cycle == "D" or re.fullmatch(r"\d{8}", period):
        return datetime.strptime(period, "%Y%m%d").date().isoformat()
    if cycle == "M" or re.fullmatch(r"\d{6}", period):
        return datetime.strptime(period, "%Y%m").date().isoformat()
    quarter_match = re.fullmatch(r"(\d{4})Q([1-4])", period)
    if cycle == "Q" or quarter_match:
        if not quarter_match:
            raise ValueError(f"Unsupported quarter period: {period}")
        year = int(quarter_match.group(1))
        month = (int(quarter_match.group(2)) - 1) * 3 + 1
        return date(year, month, 1).isoformat()
    if cycle == "A" or re.fullmatch(r"\d{4}", period):
        return date(int(period), 1, 1).isoformat()
    raise ValueError(f"Unsupported ECOS period: {period}")


def fetch_ecos_series(
    spec: SeriesSpec,
    raw_dir: Path,
    api_key: str,
    page_delay: float,
) -> tuple[list[dict], dict]:
    stat_code, item_code, cycle, lookback_months = ECOS_CONFIG[spec.indicator_id]
    end_period = month_period(date.today())
    start_period = month_period(add_months(date.today().replace(day=1), -lookback_months))
    page_size = 10 if api_key == "sample" else 10000
    raw_rows: list[dict] = []

    first_url = ecos_url(api_key, 1, page_size, stat_code, cycle, start_period, end_period, item_code)
    first_payload = json.loads(fetch_bytes(first_url, timeout=60).decode("utf-8"))
    if "RESULT" in first_payload:
        result = first_payload["RESULT"]
        if result.get("CODE") == "INFO-200":
            return [], {
                "source_type": spec.source_type,
                "indicator_id": spec.indicator_id,
                "source_series_id": spec.source_series_id,
                "status": "missing",
                "rows": 0,
                "message": result.get("MESSAGE", ""),
            }
        raise RuntimeError(f"ECOS error {result.get('CODE')}: {result.get('MESSAGE')}")

    data = first_payload["StatisticSearch"]
    total = int(data["list_total_count"])
    raw_rows.extend(data.get("row", []))
    for start in range(page_size + 1, total + 1, page_size):
        if page_delay:
            import time

            time.sleep(page_delay)
        end = min(start + page_size - 1, total)
        url = ecos_url(api_key, start, end, stat_code, cycle, start_period, end_period, item_code)
        payload = json.loads(fetch_bytes(url, timeout=60).decode("utf-8"))
        if "RESULT" in payload:
            result = payload["RESULT"]
            raise RuntimeError(f"ECOS error {result.get('CODE')}: {result.get('MESSAGE')}")
        raw_rows.extend(payload["StatisticSearch"].get("row", []))

    raw_path = raw_dir / f"{safe_filename(spec.source_series_id)}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(
        json.dumps(
            {
                "stat_code": stat_code,
                "item_code": item_code,
                "cycle": cycle,
                "start_period": start_period,
                "end_period": end_period,
                "row_count": len(raw_rows),
                "raw_rows": raw_rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    rows: list[dict] = []
    for row in sorted(raw_rows, key=lambda item: item["TIME"]):
        value = parse_float(row.get("DATA_VALUE"))
        if value is None:
            continue
        rows.append(observation(spec, period_to_iso(row["TIME"], cycle), value))
    return rows, {
        "source_type": spec.source_type,
        "indicator_id": spec.indicator_id,
        "source_series_id": spec.source_series_id,
        "status": "ok",
        "rows": len(rows),
        "message": "",
    }


def fetch_bok_key_stats(raw_dir: Path, api_key: str, page_delay: float) -> tuple[list[dict], dict]:
    raw_rows: list[dict] = []
    total: int | None = None
    start = 1
    while total is None or start <= total:
        if start > 1 and page_delay:
            import time

            time.sleep(page_delay)
        end = start + 9 if total is None else min(start + 9, total)
        url = (
            "https://ecos.bok.or.kr/api/KeyStatisticList/"
            f"{urllib.parse.quote(api_key)}/json/kr/{start}/{end}/"
        )
        payload = json.loads(fetch_bytes(url, timeout=60).decode("utf-8"))
        if "RESULT" in payload:
            result = payload["RESULT"]
            raise RuntimeError(f"ECOS KeyStatistic error {result.get('CODE')}: {result.get('MESSAGE')}")
        data = payload.get("KeyStatisticList", {})
        total = int(data.get("list_total_count", total or 0))
        raw_rows.extend(data.get("row", []))
        start += 10

    raw_path = raw_dir / "key_statistic_list.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(
        json.dumps({"row_count": len(raw_rows), "raw_rows": raw_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    rows: list[dict] = []
    for row in raw_rows:
        key_name = row.get("KEYSTAT_NAME", "")
        spec = BOK_KEYSTAT_MAP.get(key_name)
        value = parse_float(row.get("DATA_VALUE"))
        cycle = row.get("CYCLE")
        if not spec or value is None or not cycle:
            continue
        rows.append(observation(spec, period_to_iso(cycle, ""), value))
    return rows, {
        "source_type": "bok_key",
        "indicator_id": "bok_key_statistics",
        "source_series_id": "KeyStatisticList",
        "status": "ok",
        "rows": len(rows),
        "message": "",
    }


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def make_rate_observations(data_dir: Path) -> list[dict]:
    path = data_dir / "processed" / "rates" / "all_interest_rates_daily.csv"
    source_rows = read_csv(path)
    specs = {spec.indicator_id: spec for spec in DERIVED_SERIES}
    rows: list[dict] = []
    for row in source_rows:
        central_bank = row.get("central_bank")
        series = row.get("series")
        indicator_id = ""
        if central_bank == "Federal Reserve" and series == "federal_funds_target_rate_or_range":
            indicator_id = "fed_policy_rate_mid"
        elif central_bank == "Federal Reserve" and series == "federal_funds_effective_rate":
            indicator_id = "fed_funds_effective"
        elif central_bank == "Bank of Korea" and series == "base_rate":
            indicator_id = "bok_base_rate"
        if not indicator_id:
            continue
        value = parse_float(row.get("rate_mid_pct") or row.get("rate_pct"))
        if value is None:
            continue
        rows.append(observation(specs[indicator_id], row["date"], value))
    return rows


def build_spread(
    rows: list[dict],
    left_indicator_id: str,
    right_indicator_id: str,
    output_spec: SeriesSpec,
) -> list[dict]:
    left = {
        row["date"]: parse_float(row.get("value"))
        for row in rows
        if row.get("indicator_id") == left_indicator_id and parse_float(row.get("value")) is not None
    }
    right = {
        row["date"]: parse_float(row.get("value"))
        for row in rows
        if row.get("indicator_id") == right_indicator_id and parse_float(row.get("value")) is not None
    }
    output: list[dict] = []
    for obs_date in sorted(set(left) & set(right)):
        output.append(observation(output_spec, obs_date, left[obs_date] - right[obs_date]))
    return output


def build_scaled_difference(
    rows: list[dict],
    left_indicator_id: str,
    right_indicator_id: str,
    output_spec: SeriesSpec,
    scale: float = 1.0,
) -> list[dict]:
    left = {
        row["date"]: parse_float(row.get("value"))
        for row in rows
        if row.get("indicator_id") == left_indicator_id and parse_float(row.get("value")) is not None
    }
    right = {
        row["date"]: parse_float(row.get("value"))
        for row in rows
        if row.get("indicator_id") == right_indicator_id and parse_float(row.get("value")) is not None
    }
    output: list[dict] = []
    for obs_date in sorted(set(left) & set(right)):
        output.append(observation(output_spec, obs_date, (left[obs_date] - right[obs_date]) * scale))
    return output


def create_manual_template(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OBSERVATION_FIELDS)
        writer.writeheader()


def read_manual_observations(path: Path) -> list[dict]:
    rows = read_csv(path)
    normalized: list[dict] = []
    specs = {spec.indicator_id: spec for spec in MANUAL_SERIES}
    for row in rows:
        indicator_id = row.get("indicator_id", "")
        if not indicator_id:
            continue
        spec = specs.get(indicator_id)
        value = parse_float(row.get("value"))
        if value is None:
            continue
        if spec:
            normalized.append(
                observation(spec, row["date"], value)
                | {
                    "source": row.get("source") or spec.source,
                    "source_url": row.get("source_url") or spec.source_url,
                    "notes": row.get("notes") or spec.notes,
                }
            )
        else:
            normalized.append({field: row.get(field, "") for field in OBSERVATION_FIELDS})
    return normalized


def parse_rfc822_date(value: str | None) -> str:
    if not value:
        return date.today().isoformat()
    try:
        return email.utils.parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError):
        return date.today().isoformat()


def text_of(item: ET.Element, tag: str, ns: dict[str, str] | None = None) -> str:
    found = item.find(tag, ns or {})
    return (found.text or "").strip() if found is not None else ""


def parse_event_type(item: ET.Element, link: str) -> str:
    match = re.search(r"eventtype=([A-Z]+)", link)
    if match:
        return match.group(1)
    subject = text_of(item, "dc:subject", {"dc": "http://purl.org/dc/elements/1.1/"})
    return re.sub(r"\d+", "", subject) or ""


def fetch_gdacs(raw_dir: Path, processed_dir: Path) -> tuple[list[dict], list[dict], dict]:
    url = "https://www.gdacs.org/xml/rss.xml"
    raw = fetch_bytes(url, timeout=60)
    raw_path = raw_dir / "gdacs_rss.xml"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw)

    text = raw.decode("utf-8-sig", errors="replace")
    root = ET.fromstring(text)
    channel = root.find("channel")
    event_rows: list[dict] = []
    if channel is not None:
        for item in channel.findall("item"):
            title = text_of(item, "title")
            link = text_of(item, "link")
            guid = text_of(item, "guid")
            pub_date = text_of(item, "pubDate")
            from_date = text_of(item, "gdacs:fromdate", {"gdacs": "http://www.gdacs.org"})
            is_current = text_of(item, "gdacs:iscurrent", {"gdacs": "http://www.gdacs.org"})
            alert_level = title.split(" ", 1)[0] if title else ""
            event_rows.append(
                {
                    "date": parse_rfc822_date(from_date or pub_date),
                    "event_id": guid,
                    "event_type": parse_event_type(item, link),
                    "alert_level": alert_level,
                    "is_current": is_current,
                    "title": title,
                    "description": text_of(item, "description"),
                    "source": "GDACS",
                    "source_url": link,
                }
            )
    event_fields = [
        "date",
        "event_id",
        "event_type",
        "alert_level",
        "is_current",
        "title",
        "description",
        "source",
        "source_url",
    ]
    write_csv(processed_dir / "climate_events_gdacs.csv", event_rows, event_fields)

    specs = {spec.indicator_id: spec for spec in DERIVED_SERIES}
    today = date.today().isoformat()
    current_events = [row for row in event_rows if row.get("is_current", "").lower() == "true"]
    non_green = [
        row
        for row in current_events
        if row.get("alert_level", "").lower() in {"orange", "red"}
    ]
    observations = [
        observation(specs["gdacs_current_events_count"], today, float(len(current_events))),
        observation(specs["gdacs_non_green_events_count"], today, float(len(non_green))),
    ]
    return observations, event_rows, {
        "source_type": "gdacs",
        "indicator_id": "climate_events",
        "source_series_id": "gdacs_rss",
        "status": "ok",
        "rows": len(event_rows),
        "message": "",
    }


def add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    day = min(value.day, days_in_month(year, month))
    return date(year, month, day)


def days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return (next_month - date(year, month, 1)).days


def find_on_or_before(points: list[tuple[date, float]], target: date) -> tuple[date, float] | None:
    candidate: tuple[date, float] | None = None
    for obs_date, value in points:
        if obs_date <= target:
            candidate = (obs_date, value)
        else:
            break
    return candidate


def pct_change(latest: float, prior: float | None) -> float | str:
    if prior is None or prior == 0:
        return ""
    return (latest / prior - 1.0) * 100.0


def delta(latest: float, prior: float | None) -> float | str:
    if prior is None:
        return ""
    return latest - prior


def freshness_status(latest_date: date, frequency: str) -> tuple[int, str]:
    age_days = max((date.today() - latest_date).days, 0)
    thresholds = {
        "daily": 14,
        "weekly": 35,
        "monthly": 120,
        "quarterly": 210,
        "annual": 550,
        "snapshot": 7,
        "event": 365,
        "daily_or_monthly": 120,
    }
    threshold = thresholds.get(frequency, 120)
    return age_days, "ok" if age_days <= threshold else "stale"


def build_snapshot(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        value = parse_float(row.get("value"))
        if value is None:
            continue
        grouped.setdefault(row["indicator_id"], []).append(row)

    snapshot: list[dict] = []
    for indicator_id, group in sorted(grouped.items()):
        points: list[tuple[date, float, dict]] = []
        for row in group:
            try:
                points.append((date.fromisoformat(row["date"]), float(row["value"]), row))
            except ValueError:
                continue
        if not points:
            continue
        points.sort(key=lambda item: item[0])
        latest_date, latest_value, latest_row = points[-1]
        previous = points[-2] if len(points) >= 2 else None
        compact_points = [(obs_date, value) for obs_date, value, _ in points]
        age_days, fresh_status = freshness_status(
            latest_date,
            latest_row.get("frequency", ""),
        )

        output = {
            "indicator_id": indicator_id,
            "name_ko": latest_row.get("name_ko", ""),
            "category": latest_row.get("category", ""),
            "country": latest_row.get("country", ""),
            "latest_date": latest_date.isoformat(),
            "latest_value": latest_value,
            "age_days": age_days,
            "freshness_status": fresh_status,
            "unit": latest_row.get("unit", ""),
            "frequency": latest_row.get("frequency", ""),
            "previous_date": previous[0].isoformat() if previous else "",
            "previous_value": previous[1] if previous else "",
            "change_1_obs": delta(latest_value, previous[1] if previous else None),
            "pct_change_1_obs": pct_change(latest_value, previous[1] if previous else None),
            "source": latest_row.get("source", ""),
            "source_series_id": latest_row.get("source_series_id", ""),
            "source_url": latest_row.get("source_url", ""),
            "notes": latest_row.get("notes", ""),
        }
        for months in (1, 3, 6, 12):
            prior = find_on_or_before(compact_points, add_months(latest_date, -months))
            prior_date = prior[0].isoformat() if prior else ""
            prior_value = prior[1] if prior else None
            output[f"date_{months}m"] = prior_date
            output[f"value_{months}m"] = prior_value if prior is not None else ""
            output[f"change_{months}m"] = delta(latest_value, prior_value)
            output[f"pct_change_{months}m"] = pct_change(latest_value, prior_value)
        snapshot.append(output)
    return snapshot


def build_dashboard(snapshot: list[dict]) -> list[dict]:
    by_indicator = {row["indicator_id"]: row for row in snapshot}
    rows: list[dict] = []
    for field in DASHBOARD_FIELDS:
        snap = by_indicator.get(field.indicator_id)
        status = field.status_override or (snap.get("freshness_status", "ok") if snap else "missing")
        value = ""
        if snap and not field.status_override:
            value = snap.get(field.metric, "")
        rows.append(
            {
                "field_ko": field.field_ko,
                "category": field.category,
                "indicator_id": field.indicator_id,
                "metric": field.metric,
                "metric_ko": field.metric_ko,
                "value": value,
                "unit": field.unit,
                "latest_date": snap.get("latest_date", "") if snap else "",
                "latest_raw_value": snap.get("latest_value", "") if snap else "",
                "latest_raw_unit": snap.get("unit", "") if snap else "",
                "age_days": snap.get("age_days", "") if snap else "",
                "freshness_status": snap.get("freshness_status", "") if snap else "",
                "pct_change_3m": snap.get("pct_change_3m", "") if snap else "",
                "pct_change_6m": snap.get("pct_change_6m", "") if snap else "",
                "pct_change_12m": snap.get("pct_change_12m", "") if snap else "",
                "source": snap.get("source", "") if snap else "",
                "source_series_id": snap.get("source_series_id", "") if snap else "",
                "source_url": snap.get("source_url", "") if snap else "",
                "status": status,
                "note": field.note,
            }
        )
    return rows


def write_catalog(path: Path) -> int:
    catalog_fields = [
        "indicator_id",
        "name_ko",
        "category",
        "country",
        "source_type",
        "source_series_id",
        "unit",
        "frequency",
        "source",
        "source_url",
        "notes",
    ]
    rows = []
    key_stat_specs = list(BOK_KEYSTAT_MAP.values())
    for spec in ECOS_SERIES + FRED_SERIES + YAHOO_SERIES + key_stat_specs + DERIVED_SERIES + MANUAL_SERIES:
        rows.append(
            {
                "indicator_id": spec.indicator_id,
                "name_ko": spec.name_ko,
                "category": spec.category,
                "country": spec.country,
                "source_type": spec.source_type,
                "source_series_id": spec.source_series_id,
                "unit": spec.unit,
                "frequency": spec.frequency,
                "source": spec.source,
                "source_url": spec.source_url,
                "notes": spec.notes,
            }
        )
    return write_csv(path, rows, catalog_fields)


def fetch_with_status(fetcher, spec: SeriesSpec, *args) -> tuple[list[dict], dict]:
    try:
        return fetcher(spec, *args)
    except Exception as exc:
        return [], {
            "source_type": spec.source_type,
            "indicator_id": spec.indicator_id,
            "source_series_id": spec.source_series_id,
            "status": "error",
            "rows": 0,
            "message": str(exc),
        }


def update_interest_rates(data_dir: Path, args: argparse.Namespace) -> None:
    rate_cli_args = [
        "--output-dir",
        str(data_dir),
        "--bok-source",
        args.bok_source,
    ]
    if args.bok_key:
        rate_cli_args.extend(["--bok-key", args.bok_key])
    rate_args = fetch_interest_rates.build_parser().parse_args(rate_cli_args)
    if args.target_end:
        rate_args.target_end = args.target_end
    fetch_interest_rates.run(rate_args)


def run(args: argparse.Namespace) -> dict:
    data_dir = Path(args.output_dir)
    raw_ecos_dir = data_dir / "raw" / "ecos"
    raw_fred_dir = data_dir / "raw" / "fred"
    raw_yahoo_dir = data_dir / "raw" / "yahoo"
    raw_bok_key_dir = data_dir / "raw" / "bok_key"
    raw_climate_dir = data_dir / "raw" / "climate"
    processed_macro_dir = data_dir / "processed" / "macro"
    manual_path = data_dir / "manual" / "manual_indicators.csv"

    create_manual_template(manual_path)

    if not args.skip_rates:
        update_interest_rates(data_dir, args)

    observations: list[dict] = []
    fetch_status: list[dict] = []
    ecos_key = args.bok_key or os.environ.get("BOK_API_KEY") or "sample"

    if not args.skip_ecos:
        for spec in ECOS_SERIES:
            rows, status = fetch_with_status(
                fetch_ecos_series,
                spec,
                raw_ecos_dir,
                ecos_key,
                args.ecos_page_delay,
            )
            observations.extend(rows)
            fetch_status.append(status)

    if not args.skip_bok_key:
        try:
            rows, status = fetch_bok_key_stats(raw_bok_key_dir, ecos_key, args.ecos_page_delay)
            observations.extend(rows)
            fetch_status.append(status)
        except Exception as exc:
            fetch_status.append(
                {
                    "source_type": "bok_key",
                    "indicator_id": "bok_key_statistics",
                    "source_series_id": "KeyStatisticList",
                    "status": "error",
                    "rows": 0,
                    "message": str(exc),
                }
            )

    if not args.skip_fred:
        for spec in FRED_SERIES:
            rows, status = fetch_with_status(fetch_fred_series, spec, raw_fred_dir)
            observations.extend(rows)
            fetch_status.append(status)

    if not args.skip_yahoo:
        for spec in YAHOO_SERIES:
            rows, status = fetch_with_status(fetch_yahoo_series, spec, raw_yahoo_dir, args.yahoo_range)
            observations.extend(rows)
            fetch_status.append(status)

    rate_rows = make_rate_observations(data_dir)
    observations.extend(rate_rows)
    fetch_status.append(
        {
            "source_type": "derived",
            "indicator_id": "policy_rates",
            "source_series_id": "all_interest_rates_daily.csv",
            "status": "ok" if rate_rows else "missing",
            "rows": len(rate_rows),
            "message": "",
        }
    )

    derived_specs = {spec.indicator_id: spec for spec in DERIVED_SERIES}
    observations.extend(
        build_spread(
            observations,
            "fed_policy_rate_mid",
            "bok_base_rate",
            derived_specs["us_minus_korea_policy_rate_gap"],
        )
    )
    observations.extend(
        build_spread(
            observations,
            "korea_gov_bond_10y",
            "korea_short_rate_3m",
            derived_specs["korea_10y_3m_spread"],
        )
    )
    observations.extend(
        build_scaled_difference(
            observations,
            "korea_trade_exports",
            "korea_trade_imports",
            derived_specs["korea_trade_balance"],
            scale=0.001,
        )
    )

    if not args.skip_climate:
        try:
            climate_obs, _event_rows, status = fetch_gdacs(raw_climate_dir, processed_macro_dir)
            observations.extend(climate_obs)
            fetch_status.append(status)
        except Exception as exc:
            fetch_status.append(
                {
                    "source_type": "gdacs",
                    "indicator_id": "climate_events",
                    "source_series_id": "gdacs_rss",
                    "status": "error",
                    "rows": 0,
                    "message": str(exc),
                }
            )

    manual_rows = read_manual_observations(manual_path)
    observations.extend(manual_rows)
    fetch_status.append(
        {
            "source_type": "manual",
            "indicator_id": "manual_indicators",
            "source_series_id": str(manual_path),
            "status": "ok",
            "rows": len(manual_rows),
            "message": "",
        }
    )

    observations.sort(key=lambda row: (row["indicator_id"], row["date"]))
    snapshot = build_snapshot(observations)
    dashboard = build_dashboard(snapshot)

    write_catalog(processed_macro_dir / "indicator_catalog.csv")
    observation_count = write_csv(
        processed_macro_dir / "observations_long.csv",
        observations,
        OBSERVATION_FIELDS,
    )
    snapshot_count = write_csv(
        processed_macro_dir / "latest_snapshot.csv",
        snapshot,
        SNAPSHOT_FIELDS,
    )
    dashboard_count = write_csv(
        processed_macro_dir / "requested_indicators_latest.csv",
        dashboard,
        DASHBOARD_FIELDS_OUT,
    )
    status_count = write_csv(
        processed_macro_dir / "fetch_status.csv",
        fetch_status,
        FETCH_STATUS_FIELDS,
    )

    return {
        "observations": observation_count,
        "snapshot": snapshot_count,
        "dashboard": dashboard_count,
        "fetch_status": status_count,
        "manual_path": str(manual_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch macro indicators into data/raw and data/processed/macro."
    )
    parser.add_argument(
        "--output-dir",
        default="data",
        help="Base data directory. Defaults to ./data.",
    )
    parser.add_argument(
        "--bok-source",
        default="auto",
        choices=["auto", "ecos", "homepage-events"],
        help="Passed through to scripts/fetch_interest_rates.py.",
    )
    parser.add_argument(
        "--bok-key",
        default=None,
        help="Bank of Korea ECOS API key. Defaults to BOK_API_KEY or sample.",
    )
    parser.add_argument(
        "--ecos-page-delay",
        type=float,
        default=0.2,
        help="Delay between ECOS sample-key page calls. Defaults to 0.2 seconds.",
    )
    parser.add_argument(
        "--target-end",
        default=None,
        help="End date for daily-expanded policy-rate series. Defaults to today.",
    )
    parser.add_argument(
        "--yahoo-range",
        default="max",
        help="Yahoo chart range, e.g. 5y, 10y, max. Defaults to max.",
    )
    parser.add_argument("--skip-rates", action="store_true", help="Skip BOK/Fed rate refresh.")
    parser.add_argument("--skip-ecos", action="store_true", help="Skip Bank of Korea ECOS series fetches.")
    parser.add_argument("--skip-bok-key", action="store_true", help="Skip Bank of Korea KeyStatisticList fetch.")
    parser.add_argument("--skip-fred", action="store_true", help="Skip FRED source fetches.")
    parser.add_argument("--skip-yahoo", action="store_true", help="Skip Yahoo Finance source fetches.")
    parser.add_argument("--skip-climate", action="store_true", help="Skip GDACS climate/natural hazard RSS.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        counts = run(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("Fetched macro indicator pipeline outputs:")
    print(f"  Observations: {counts['observations']}")
    print(f"  Latest snapshot rows: {counts['snapshot']}")
    print(f"  Requested dashboard rows: {counts['dashboard']}")
    print(f"  Fetch status rows: {counts['fetch_status']}")
    print(f"  Manual input file: {counts['manual_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
