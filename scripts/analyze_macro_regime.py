#!/usr/bin/env python3
"""Generate a markdown macro regime report from processed indicator snapshots."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path


DEFAULT_ALLOCATION = {
    "cash": 100,
    "gold": 22,
    "silver": 8,
    "equity": 20,
}


@dataclass(frozen=True)
class Metric:
    indicator_id: str
    latest_value: float | None
    latest_date: str
    unit: str
    change_1_obs: float | None
    pct_change_3m: float | None
    pct_change_6m: float | None
    pct_change_12m: float | None
    freshness_status: str
    source: str


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip().replace(",", "")
    if value in {"", ".", "NA", "N/A"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_metrics(path: Path) -> dict[str, Metric]:
    rows = read_csv(path)
    metrics: dict[str, Metric] = {}
    for row in rows:
        indicator_id = row.get("indicator_id", "")
        if not indicator_id:
            continue
        metrics[indicator_id] = Metric(
            indicator_id=indicator_id,
            latest_value=parse_float(row.get("latest_value")),
            latest_date=row.get("latest_date", ""),
            unit=row.get("unit", ""),
            change_1_obs=parse_float(row.get("change_1_obs")),
            pct_change_3m=parse_float(row.get("pct_change_3m")),
            pct_change_6m=parse_float(row.get("pct_change_6m")),
            pct_change_12m=parse_float(row.get("pct_change_12m")),
            freshness_status=row.get("freshness_status", ""),
            source=row.get("source", ""),
        )
    return metrics


def clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return max(low, min(high, value))


def avg(values: list[float | None], default: float = 5.0) -> float:
    clean = [value for value in values if value is not None]
    if not clean:
        return default
    return sum(clean) / len(clean)


def weighted_avg(values: list[tuple[float | None, float]], default: float = 5.0) -> float:
    clean = [(value, weight) for value, weight in values if value is not None and weight > 0]
    if not clean:
        return default
    return sum(value * weight for value, weight in clean) / sum(weight for _, weight in clean)


def threshold_score(value: float | None, bands: list[tuple[float, float]], default: float | None = None) -> float | None:
    if value is None:
        return default
    score = bands[0][1]
    for threshold, band_score in bands:
        if value >= threshold:
            score = band_score
    return score


def inverse_threshold_score(
    value: float | None,
    bands: list[tuple[float, float]],
    default: float | None = None,
) -> float | None:
    if value is None:
        return default
    for threshold, band_score in bands:
        if value <= threshold:
            return band_score
    return bands[-1][1]


def value(metrics: dict[str, Metric], indicator_id: str) -> float | None:
    metric = metrics.get(indicator_id)
    return metric.latest_value if metric else None


def pct3(metrics: dict[str, Metric], indicator_id: str) -> float | None:
    metric = metrics.get(indicator_id)
    return metric.pct_change_3m if metric else None


def pct12(metrics: dict[str, Metric], indicator_id: str) -> float | None:
    metric = metrics.get(indicator_id)
    return metric.pct_change_12m if metric else None


def change1(metrics: dict[str, Metric], indicator_id: str) -> float | None:
    metric = metrics.get(indicator_id)
    return metric.change_1_obs if metric else None


def fmt_num(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "데이터 부족"
    text = f"{value:.{digits}f}"
    return text.rstrip("0").rstrip(".")


def fmt_pct(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "데이터 부족"
    return f"{fmt_num(value, digits)}%"


def latest(metrics: dict[str, Metric], indicator_id: str) -> str:
    metric = metrics.get(indicator_id)
    if not metric or metric.latest_value is None:
        return "데이터 부족"
    return f"{fmt_num(metric.latest_value)} ({metric.latest_date})"


def calc_inflation_risk(metrics: dict[str, Metric]) -> float:
    level_bands = [(0, 1), (2.0, 3), (2.5, 4.5), (3.0, 6.5), (4.0, 8), (5.0, 9.5)]
    expected_bands = [(0, 1), (2.0, 3), (2.5, 5.5), (3.0, 7.5), (3.5, 9)]
    oil_bands = [(0, 1), (70, 4), (85, 6), (100, 8), (120, 9.5)]
    return round(
        avg(
            [
                threshold_score(pct12(metrics, "us_cpi_all_items"), level_bands),
                threshold_score(pct12(metrics, "us_core_cpi"), level_bands),
                threshold_score(pct12(metrics, "us_pce_price_index"), level_bands),
                threshold_score(pct12(metrics, "us_core_pce_price_index"), level_bands),
                threshold_score(pct12(metrics, "korea_cpi_all_items"), level_bands),
                threshold_score(value(metrics, "us_5y_breakeven_inflation"), expected_bands),
                threshold_score(value(metrics, "wti_spot"), oil_bands),
            ]
        ),
        1,
    )


def calc_liquidity_bubble_risk(metrics: dict[str, Metric]) -> float:
    m2_yoy_bands = [(-10, 1), (0, 2.5), (3, 4.5), (5, 6.5), (8, 8.5)]
    m2_3m_bands = [(-10, 1), (0, 2.5), (1, 5), (2, 7), (4, 9)]
    reserves_bands = [(-20, 1), (0, 3), (3, 5.5), (6, 7), (10, 9)]
    nfci = inverse_threshold_score(
        value(metrics, "us_chicago_fed_nfci"),
        [(-0.75, 8), (-0.5, 7), (0, 5), (0.5, 3), (99, 1.5)],
    )
    hy_spread = value(metrics, "us_high_yield_spread")
    risk_appetite = None
    if hy_spread is not None:
        if hy_spread < 3:
            risk_appetite = 7.5
        elif hy_spread < 4:
            risk_appetite = 6
        elif hy_spread < 5:
            risk_appetite = 4
        else:
            risk_appetite = 2
    return round(
        avg(
            [
                threshold_score(pct12(metrics, "us_m2"), m2_yoy_bands),
                threshold_score(pct3(metrics, "us_m2"), m2_3m_bands),
                threshold_score(pct12(metrics, "korea_m2"), m2_yoy_bands),
                threshold_score(pct3(metrics, "fed_reserve_balances"), reserves_bands),
                nfci,
                risk_appetite,
            ]
        ),
        1,
    )


def calc_credit_stress_risk(metrics: dict[str, Metric]) -> float:
    hy_bands = [(0, 1.5), (3, 3), (4, 5), (6, 7), (8, 9)]
    bbb_bands = [(0, 1.5), (1.5, 4), (2, 6), (3, 8), (4, 9)]
    lending_bands = [(-100, 1), (0, 2.5), (10, 4), (25, 6), (50, 8.5)]
    stress_bands = [(-10, 1), (0, 3), (0.5, 6), (1.5, 8.5), (3, 9.5)]
    delinquency_bands = [(0, 1), (1.5, 3), (2.5, 5), (4, 7), (6, 9)]
    return round(
        avg(
            [
                threshold_score(value(metrics, "us_high_yield_spread"), hy_bands),
                threshold_score(value(metrics, "us_bbb_spread"), bbb_bands),
                threshold_score(value(metrics, "us_bank_lending_standards"), lending_bands),
                threshold_score(value(metrics, "us_financial_stress"), stress_bands),
                threshold_score(value(metrics, "us_business_loan_delinquency_rate"), delinquency_bands),
            ]
        ),
        1,
    )


def foreign_flow_score(metrics: dict[str, Metric]) -> float | None:
    stock = value(metrics, "korea_foreign_stock_flows")
    bond = value(metrics, "korea_foreign_bond_flows")
    if stock is None and bond is None:
        return None
    total = (stock or 0.0) + (bond or 0.0)
    if total <= -20000:
        return 8.5
    if total <= -10000:
        return 7.0
    if total <= -5000:
        return 6.0
    if total < 0:
        return 5.0
    if total < 10000:
        return 3.5
    return 2.0


def trade_balance_score(metrics: dict[str, Metric]) -> float | None:
    balance = value(metrics, "korea_trade_balance")
    if balance is None:
        return None
    if balance < -10000:
        return 8.5
    if balance < 0:
        return 7.0
    if balance < 5000:
        return 5.5
    if balance < 10000:
        return 4.0
    return 2.0


def calc_fx_risk(metrics: dict[str, Metric]) -> float:
    usdkrw_bands = [(0, 1), (1300, 3), (1350, 4.5), (1400, 6), (1450, 7), (1500, 8.5), (1550, 9.5)]
    usdkrw_3m_bands = [(-20, 1), (-3, 2), (0, 4), (3, 6), (5, 8), (8, 9.5)]
    dxy_bands = [(0, 1), (95, 3), (100, 5), (105, 6.5), (110, 8.5)]
    gap_bands = [(-5, 1), (0, 3), (0.5, 5), (1.0, 6.5), (1.5, 8)]
    return round(
        weighted_avg(
            [
                (threshold_score(value(metrics, "usd_krw"), usdkrw_bands), 2.0),
                (threshold_score(pct3(metrics, "usd_krw"), usdkrw_3m_bands), 1.5),
                (threshold_score(value(metrics, "dxy"), dxy_bands), 0.8),
                (threshold_score(value(metrics, "us_minus_korea_policy_rate_gap"), gap_bands), 1.0),
                (foreign_flow_score(metrics), 1.5),
                (trade_balance_score(metrics), 0.7),
            ]
        ),
        1,
    )


def calc_climate_supply_risk(metrics: dict[str, Metric]) -> float:
    oil_bands = [(0, 1), (70, 4), (85, 6), (100, 8), (120, 9.5)]
    gas_bands = [(-100, 1), (0, 3), (20, 5), (40, 7), (70, 9)]
    food_moves = [
        pct3(metrics, "wheat_futures"),
        pct3(metrics, "corn_futures"),
        pct3(metrics, "soybean_futures"),
        pct3(metrics, "rough_rice_futures"),
        pct3(metrics, "coffee_futures"),
        pct3(metrics, "cocoa_futures"),
        pct3(metrics, "sugar_futures"),
        pct3(metrics, "fertilizer_ppi"),
    ]
    food_3m = avg(food_moves, default=0)
    climate_events = value(metrics, "gdacs_non_green_events_count")
    event_score = 2
    if climate_events is not None and climate_events > 0:
        event_score = 6 + min(climate_events, 4)
    oil_score = threshold_score(value(metrics, "wti_spot"), oil_bands)
    raw_score = weighted_avg(
        [
            (oil_score, 2.0),
            (threshold_score(pct3(metrics, "henry_hub_natural_gas"), gas_bands), 1.0),
            (threshold_score(food_3m, [(-50, 1), (-5, 2), (0, 4), (5, 5.5), (10, 7), (20, 9)]), 1.0),
            (event_score, 0.5),
        ]
    )
    if value(metrics, "wti_spot") is not None and value(metrics, "wti_spot") >= 100:
        raw_score = max(raw_score, 6.0)
    return round(raw_score, 1)


def calc_growth_slowdown_risk(metrics: dict[str, Metric]) -> float:
    unemployment_bands = [(0, 1), (3.8, 3), (4.2, 4.5), (4.8, 6.5), (5.5, 8.5)]
    payroll_bands = [(-1000, 9), (0, 7), (100, 5.5), (150, 4), (250, 2.5)]
    claims_bands = [(0, 1.5), (200000, 3), (250000, 5), (300000, 7), (350000, 8.5)]
    spread_bands = [(-99, 8), (-0.5, 7), (0, 5.5), (0.5, 3.5), (1.5, 2)]
    lending_bands = [(-100, 1), (0, 2.5), (10, 4), (25, 6), (50, 8.5)]
    return round(
        avg(
            [
                threshold_score(value(metrics, "us_unemployment_rate"), unemployment_bands),
                threshold_score(change1(metrics, "us_nonfarm_payrolls"), payroll_bands, default=None),
                threshold_score(value(metrics, "us_initial_jobless_claims"), claims_bands),
                inverse_threshold_score(value(metrics, "us_10y_2y_spread"), spread_bands),
                threshold_score(value(metrics, "us_bank_lending_standards"), lending_bands),
            ]
        ),
        1,
    )


def calc_scores(metrics: dict[str, Metric]) -> dict[str, float]:
    return {
        "Inflation Risk": calc_inflation_risk(metrics),
        "Liquidity Bubble Risk": calc_liquidity_bubble_risk(metrics),
        "Credit Stress Risk": calc_credit_stress_risk(metrics),
        "FX Risk": calc_fx_risk(metrics),
        "Climate Supply Shock Risk": calc_climate_supply_risk(metrics),
        "Growth Slowdown Risk": calc_growth_slowdown_risk(metrics),
    }


def determine_regime(scores: dict[str, float]) -> tuple[str, str, str]:
    inflation = scores["Inflation Risk"]
    liquidity = scores["Liquidity Bubble Risk"]
    credit = scores["Credit Stress Risk"]
    fx = scores["FX Risk"]
    climate = scores["Climate Supply Shock Risk"]
    growth = scores["Growth Slowdown Risk"]

    if credit >= 6.5:
        current = "Credit Stress"
    elif inflation >= 6.5 and growth >= 6.0:
        current = "Stagflation Risk"
    elif inflation >= 6.0 and fx >= 6.0:
        current = "Inflation Rebound + Dollar/KRW Risk"
    elif liquidity >= 7.0 and credit < 5.0:
        current = "Liquidity Bubble"
    elif inflation <= 4.5 and credit <= 4.0 and growth <= 4.5:
        current = "Goldilocks"
    else:
        current = "Defensive Waiting Mode"

    helpers = []
    if climate >= 6.5:
        helpers.append("Climate Supply Shock Risk")
    if liquidity >= 6.0 and credit < 5.0:
        helpers.append("Liquidity Bubble")
    if growth >= 5.5:
        helpers.append("Growth Slowdown Risk")
    if fx >= 6.5 and "Dollar/KRW Risk" not in current:
        helpers.append("Dollar/KRW Risk")
    if not helpers:
        helpers.append("Defensive Waiting Mode")

    summary = (
        "인플레와 환율 부담이 남아 있어 공격적 위험자산 확대보다는 방어적 대기와 헤지 유지가 더 자연스러운 조합입니다."
    )
    if current == "Goldilocks":
        summary = "물가와 신용 스트레스가 완화되어 방어 일변도보다 일부 성장자산 노출을 열어둘 수 있는 조합입니다."
    elif current == "Credit Stress":
        summary = "신용 스트레스가 우선 리스크로 올라와 현금성 자산과 단기채의 방어 역할이 커진 조합입니다."
    elif current == "Liquidity Bubble":
        summary = "신용 스트레스는 낮지만 유동성과 위험선호가 강해 버블 가능성을 경계해야 하는 조합입니다."
    elif current == "Stagflation Risk":
        summary = "물가 부담과 성장 둔화 신호가 함께 보여 주식 비중 확대에는 더 높은 확인이 필요한 조합입니다."

    return current, " / ".join(helpers), summary


def score_label(score: float) -> str:
    if score >= 7.5:
        return "높음"
    if score >= 5.5:
        return "중간 이상"
    if score >= 3.5:
        return "중간"
    return "낮음"


def build_allocation(scores: dict[str, float]) -> dict[str, int]:
    allocation = DEFAULT_ALLOCATION.copy()
    if scores["Inflation Risk"] >= 6.5 or scores["FX Risk"] >= 6.5:
        allocation["cash"] -= 5
        allocation["gold"] += 4
        allocation["silver"] += 1
    if scores["Climate Supply Shock Risk"] >= 7.0:
        allocation["cash"] -= 5
        allocation["gold"] += 2
        allocation["silver"] += 3
    if scores["Credit Stress Risk"] >= 6.5 or scores["Growth Slowdown Risk"] >= 6.5:
        allocation["equity"] -= 5
        allocation["cash"] += 5
    if (
        scores["Liquidity Bubble Risk"] >= 7.0
        and scores["Credit Stress Risk"] < 5.0
        and scores["Inflation Risk"] < 7.0
    ):
        allocation["cash"] -= 5
        allocation["equity"] += 5

    allocation["cash"] = max(80, min(115, allocation["cash"]))
    allocation["equity"] = max(10, min(30, allocation["equity"]))
    allocation["gold"] = max(15, min(35, allocation["gold"]))
    allocation["silver"] = max(5, min(20, allocation["silver"]))

    total = sum(allocation.values())
    allocation["cash"] += 150 - total
    return allocation


def portfolio_eval(scores: dict[str, float], allocation: dict[str, int]) -> tuple[str, str, str]:
    keep = "주식/ETF 기본 20만원은 기회 상실 방지용으로 유지 가능"
    reduce = "현금성/단기채는 큰 폭 축소보다 일부만 헤지 자산으로 이동"
    expand = "FX·인플레 리스크가 높으면 금 중심 헤지 비중을 소폭 확대"
    if allocation["cash"] >= DEFAULT_ALLOCATION["cash"]:
        keep = "현금성/단기채 100만원 안팎의 방어 축은 유지"
        reduce = "금/은 또는 주식의 무리한 확대는 보류"
    if allocation["equity"] < DEFAULT_ALLOCATION["equity"]:
        reduce = "주식/ETF는 성장 둔화 또는 신용 리스크 확인 전까지 소폭 축소"
    if scores["Liquidity Bubble Risk"] >= 7 and scores["Credit Stress Risk"] < 5:
        keep = "주식/ETF는 완전 배제보다 최소 성장 노출 유지"
    return keep, reduce, expand


def risk_interpretation(name: str, score: float) -> str:
    label = score_label(score)
    if name == "Inflation Risk":
        return f"{label}: 미국 물가와 유가 레벨이 아직 2% 목표 복귀보다 재상승 경계를 요구"
    if name == "Liquidity Bubble Risk":
        return f"{label}: M2와 금융여건 완화가 위험선호를 지지하지만 버블 가능성도 동반"
    if name == "Credit Stress Risk":
        return f"{label}: 스프레드와 스트레스 지표 기준으로 급성 신용위기는 아직 제한적"
    if name == "FX Risk":
        return f"{label}: USD/KRW 레벨과 한미 금리차가 원화 방어 부담을 높임"
    if name == "Climate Supply Shock Risk":
        return f"{label}: 에너지 가격과 일부 원자재 변동성이 공급충격 리스크를 남김"
    return f"{label}: 고용은 버티지만 둔화 신호를 계속 확인해야 하는 구간"


def stale_items(metrics: dict[str, Metric]) -> list[str]:
    return [
        indicator_id
        for indicator_id, metric in sorted(metrics.items())
        if metric.freshness_status == "stale" and not indicator_id.endswith("_fred")
    ]


def build_report(metrics: dict[str, Metric], scores: dict[str, float], report_date: str) -> str:
    current_regime, sub_regime, summary = determine_regime(scores)
    allocation = build_allocation(scores)
    keep, reduce, expand = portfolio_eval(scores, allocation)
    stale = stale_items(metrics)

    cash_delta = allocation["cash"] - 100
    metals_delta = allocation["gold"] + allocation["silver"] - 30
    equity_delta = allocation["equity"] - 20

    if metals_delta > 0:
        month_action = f"현금성/단기채에서 {metals_delta}만원을 줄이고 금/은 헤지를 {metals_delta}만원 늘리는 선택지가 합리적"
    elif equity_delta > 0:
        month_action = f"현금성/단기채에서 {equity_delta}만원을 줄이고 주식/ETF를 {equity_delta}만원 늘리는 선택지가 가능"
    else:
        month_action = "기본 방어 배분을 유지하면서 핵심 지표 확인"

    data_quality_note = " / ".join(stale[:4]) if stale else "핵심 자동 수집 지표는 최신성 기준 통과"
    conclusion_action = (
        "현금성/단기채의 방어 축을 유지하되 금/은 헤지를 소폭 확대하는 것"
        if metals_delta > 0
        else "현금성/단기채의 방어 축과 기존 금/은 헤지를 유지하는 것"
    )

    lines = [
        "# 매크로 레짐 분석 리포트",
        "",
        "## 1. 현재 레짐",
        f"현재 레짐: {current_regime}",
        f"보조 레짐: {sub_regime}",
        f"한 줄 요약: {summary}",
        "",
        "## 2. 핵심 판단",
        f"- Inflation Risk {scores['Inflation Risk']}/10, FX Risk {scores['FX Risk']}/10로 물가·환율 방어 논리가 우세합니다.",
        f"- Credit Stress Risk {scores['Credit Stress Risk']}/10로 급성 신용위기 신호는 아직 제한적이지만, 성장 둔화 점수는 {scores['Growth Slowdown Risk']}/10입니다.",
        f"- 데이터 품질: {data_quality_note}. stale 또는 수기 지표는 레짐 확신도를 낮추는 요인입니다.",
        "",
        "## 3. 지표별 해석",
        "",
        "### 인플레",
        f"판단: {score_label(scores['Inflation Risk'])} 리스크",
        f"근거: 미국 CPI YoY {fmt_pct(pct12(metrics, 'us_cpi_all_items'))}, Core CPI YoY {fmt_pct(pct12(metrics, 'us_core_cpi'))}, Core PCE YoY {fmt_pct(pct12(metrics, 'us_core_pce_price_index'))}, 한국 CPI YoY {fmt_pct(pct12(metrics, 'korea_cpi_all_items'))}, WTI {latest(metrics, 'wti_spot')}.",
        "자산 영향: 금은 인플레·정책실수 헤지 역할이 커지고, 주식/ETF는 밸류에이션 부담을 함께 점검해야 합니다.",
        "",
        "### 금리",
        "판단: 인하 기대와 고금리 유지 부담이 공존",
        f"근거: Fed 기준금리 {latest(metrics, 'fed_policy_rate_mid')}, 한국은행 기준금리 {latest(metrics, 'bok_base_rate')}, 미국 10년물 {latest(metrics, 'us_treasury_10y')}, 미국 10Y-2Y 금리차 {latest(metrics, 'us_10y_2y_spread')}.",
        "자산 영향: 단기채/현금성 자산의 방어 역할은 유지되며, 장기채와 성장주는 금리 재상승에 취약할 수 있습니다.",
        "",
        "### M2/유동성",
        f"판단: {score_label(scores['Liquidity Bubble Risk'])} 수준의 유동성·위험선호",
        f"근거: 미국 M2 YoY {fmt_pct(pct12(metrics, 'us_m2'))}, 미국 M2 3M {fmt_pct(pct3(metrics, 'us_m2'))}, 한국 M2 YoY {fmt_pct(pct12(metrics, 'korea_m2'))}, NFCI {latest(metrics, 'us_chicago_fed_nfci')}.",
        "자산 영향: 유동성은 위험자산을 지지할 수 있지만, 버블 리스크가 커지면 현금 보유의 옵션 가치도 커집니다.",
        "",
        "### 신용스프레드",
        f"판단: {score_label(scores['Credit Stress Risk'])} 리스크",
        f"근거: 하이일드 스프레드 {latest(metrics, 'us_high_yield_spread')}, BBB 스프레드 {latest(metrics, 'us_bbb_spread')}, 금융시장 스트레스 {latest(metrics, 'us_financial_stress')}, 은행 대출태도 {latest(metrics, 'us_bank_lending_standards')}, 기업대출 연체율 프록시 {latest(metrics, 'us_business_loan_delinquency_rate')}.",
        "자산 영향: 신용 스트레스가 낮을 때는 주식 급감 리스크가 제한되지만, 스프레드 확대 전환 시 현금 비중의 방어성이 커집니다.",
        "",
        "### 환율",
        f"판단: {score_label(scores['FX Risk'])} 리스크",
        f"근거: USD/KRW {latest(metrics, 'usd_krw')}, DXY {latest(metrics, 'dxy')}, 한미 기준금리차 {latest(metrics, 'us_minus_korea_policy_rate_gap')}, 경상수지 {latest(metrics, 'korea_current_account')}, 무역수지 {latest(metrics, 'korea_trade_balance')}, 외국인 주식/채권 흐름 {latest(metrics, 'korea_foreign_stock_flows')} / {latest(metrics, 'korea_foreign_bond_flows')}.",
        "자산 영향: 원화 약세 리스크가 높을수록 금과 달러 노출 자산의 헤지 성격이 강화됩니다.",
        "",
        "### 고용",
        f"판단: {score_label(scores['Growth Slowdown Risk'])} 성장 둔화 리스크",
        f"근거: 미국 실업률 {latest(metrics, 'us_unemployment_rate')}, 비농업고용 월간 변화 {fmt_num(change1(metrics, 'us_nonfarm_payrolls'))}천명, 신규 실업수당 청구 {latest(metrics, 'us_initial_jobless_claims')}, 임금 YoY {fmt_pct(pct12(metrics, 'us_avg_hourly_earnings'))}.",
        "자산 영향: 고용이 급격히 꺾이지 않으면 주식의 성장 엔진은 유지되지만, 둔화가 확인되면 현금성 자산 비중을 낮추기 어렵습니다.",
        "",
        "### 이상기후/원자재",
        f"판단: {score_label(scores['Climate Supply Shock Risk'])} 공급충격 리스크",
        f"근거: WTI {latest(metrics, 'wti_spot')}, 천연가스 3M {fmt_pct(pct3(metrics, 'henry_hub_natural_gas'))}, 밀 3M {fmt_pct(pct3(metrics, 'wheat_futures'))}, 비료 3M {fmt_pct(pct3(metrics, 'fertilizer_ppi'))}, GDACS 주황/적색 이벤트 {latest(metrics, 'gdacs_non_green_events_count')}.",
        "자산 영향: 에너지·식품 충격 가능성이 남아 있으면 금/은과 일부 원자재 헤지의 방어 논리가 유지됩니다.",
        "",
        "## 4. Risk Score",
        "| 항목 | 점수 | 해석 |",
        "|---|---:|---|",
    ]
    for name in [
        "Inflation Risk",
        "Liquidity Bubble Risk",
        "Credit Stress Risk",
        "FX Risk",
        "Climate Supply Shock Risk",
        "Growth Slowdown Risk",
    ]:
        lines.append(f"| {name} | {scores[name]}/10 | {risk_interpretation(name, scores[name])} |")

    lines.extend(
        [
            "",
            "## 5. 현재 포트폴리오 평가",
            "기존 배분:",
            "- 현금성/3개월 이하 단기채: 100만원",
            "- 금/은: 30만원",
            "- 주식/ETF: 20만원",
            "",
            "평가:",
            f"- 유지: {keep}",
            f"- 축소: {reduce}",
            f"- 확대: {expand}",
            "",
            "## 6. 제안 배분",
            "월 ISA 150만원 기준:",
            "",
            "| 자산 | 금액 | 비중 | 이유 |",
            "|---|---:|---:|---|",
            f"| 현금성/3개월 이하 단기채 | {allocation['cash']}만원 | {allocation['cash'] / 150:.1%} | 변동성 방어와 폭락 시 매수 여력 보존 |",
            f"| 금 | {allocation['gold']}만원 | {allocation['gold'] / 150:.1%} | 인플레, 환율, 정책실수 리스크 헤지 |",
            f"| 은/원자재 | {allocation['silver']}만원 | {allocation['silver'] / 150:.1%} | 귀금속과 산업재 성격의 보조 헤지 |",
            f"| 주식/ETF | {allocation['equity']}만원 | {allocation['equity'] / 150:.1%} | 장기 성장 엔진과 기회 상실 방지 |",
            "",
            "## 7. 조정 액션",
            f"- 이번 달: {month_action}.",
            f"- 다음 달: CPI/PCE, USD/KRW, WTI, 하이일드 스프레드가 완화되면 현금 {abs(cash_delta)}만원 조정 여부를 재검토.",
            f"- 지표 변화 시: Core CPI 재가속, USD/KRW 추가 상승, WTI 급등이면 금/은 헤지를 유지하거나 소폭 확대하고, 신용스프레드 급등이면 주식/ETF 확대를 보류.",
            "",
            "## 8. 다음 체크포인트",
            "- 미국 CPI/Core CPI/PCE/Core PCE의 다음 발표에서 3개월 변화율이 둔화되는지 확인",
            "- USD/KRW, DXY, 한미 기준금리차가 동시에 완화되는지 확인",
            "- 하이일드 스프레드, BBB 스프레드, 신규 실업수당 청구가 동반 악화되는지 확인",
            "",
            "## 9. 반대 시나리오",
            "현재 판단이 틀릴 수 있는 조건:",
            "- 유가와 식품 원자재가 빠르게 안정되고 Core CPI/Core PCE가 2%대 초중반으로 내려오는 경우",
            "- USD/KRW가 안정되고 DXY가 하락하며 원화 약세 압력이 줄어드는 경우",
            "- 신용스프레드가 낮게 유지되고 고용이 견조해 주식/ETF의 기회비용이 더 커지는 경우",
            "",
            "## 10. 최종 결론",
            f"요약: 현재 지표 조합상 합리적인 선택지는 {current_regime} 레짐을 기본으로 보고, {conclusion_action}입니다. 이는 시장 방향을 단정하는 판단이 아니라, 인플레·환율·공급충격 리스크가 완전히 해소되지 않은 상태에서 월 ISA 150만원의 방어적 대기 전략을 유지하는 접근입니다.",
            "",
            f"작성일: {report_date}",
        ]
    )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate macro regime markdown report.")
    parser.add_argument(
        "--snapshot",
        default="data/processed/macro/latest_snapshot.csv",
        help="Input latest snapshot CSV.",
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Directory for generated markdown reports.",
    )
    parser.add_argument(
        "--report-date",
        default=date.today().isoformat(),
        help="Report date used in the output filename and footer.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    snapshot_path = Path(args.snapshot)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics = load_metrics(snapshot_path)
    scores = calc_scores(metrics)
    report = build_report(metrics, scores, args.report_date)
    output_path = output_dir / f"macro_regime_{args.report_date}.md"
    output_path.write_text(report, encoding="utf-8")

    print(f"Generated report: {output_path}")
    print("Risk scores:")
    for name, score in scores.items():
        print(f"  {name}: {score}/10")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
