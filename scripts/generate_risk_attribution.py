#!/usr/bin/env python3
"""Generate a risk-score attribution report from the latest macro snapshot."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    from macro_rules import KEY_METRIC_LABELS
except ImportError:  # pragma: no cover
    KEY_METRIC_LABELS = {}


DEFAULT_RISK_HISTORY = Path("data/processed/macro/risk_score_history.csv")
DEFAULT_SNAPSHOT = Path("data/processed/macro/latest_snapshot.csv")
DEFAULT_DASHBOARD = Path("data/processed/macro/requested_indicators_latest.csv")
DEFAULT_ALERTS = Path("data/processed/macro/change_alerts_latest.csv")
DEFAULT_OUTPUT_CSV = Path("data/processed/macro/risk_attribution_latest.csv")
DEFAULT_REPORT_DIR = Path("reports")
DEFAULT_LATEST_REPORT = Path("reports/risk_attribution_latest.md")

RISK_FIELDS = [
    ("inflation_risk", "Inflation Risk"),
    ("liquidity_bubble_risk", "Liquidity Bubble Risk"),
    ("credit_stress_risk", "Credit Stress Risk"),
    ("fx_risk", "FX Risk"),
    ("climate_supply_shock_risk", "Climate Supply Shock Risk"),
    ("growth_slowdown_risk", "Growth Slowdown Risk"),
    ("market_stress_risk", "Market Stress Risk"),
    ("global_rate_divergence_risk", "Global Rate Divergence Risk"),
]

# direction: +1 means a rising indicator usually raises that risk score,
# -1 means a rising indicator usually reduces that risk score.
RISK_DRIVER_MAP = {
    "Inflation Risk": [
        ("us_cpi_all_items", 1),
        ("us_core_cpi", 1),
        ("us_pce_price_index", 1),
        ("us_core_pce_price_index", 1),
        ("us_michigan_expected_inflation", 1),
        ("us_5y_breakeven_inflation", 1),
        ("us_10y_breakeven_inflation", 1),
        ("korea_cpi_all_items", 1),
        ("korea_cpi_food", 1),
        ("korea_cpi_energy", 1),
        ("us_cpi_food", 1),
        ("us_cpi_energy", 1),
        ("wti_spot", 1),
    ],
    "Liquidity Bubble Risk": [
        ("us_m2", 1),
        ("korea_m2", 1),
        ("fed_balance_sheet_assets", 1),
        ("fed_reserve_balances", 1),
        ("fed_reverse_repo", 1),
        ("us_chicago_fed_nfci", -1),
        ("dxy", -1),
    ],
    "Credit Stress Risk": [
        ("us_high_yield_spread", 1),
        ("us_bbb_spread", 1),
        ("us_bank_lending_standards", 1),
        ("us_financial_stress", 1),
        ("us_business_loan_delinquency_rate", 1),
    ],
    "FX Risk": [
        ("usd_krw", 1),
        ("dxy", 1),
        ("us_minus_korea_policy_rate_gap", 1),
        ("korea_foreign_stock_flows", -1),
        ("korea_foreign_bond_flows", -1),
        ("korea_trade_balance", -1),
        ("korea_current_account", -1),
    ],
    "Climate Supply Shock Risk": [
        ("wti_spot", 1),
        ("henry_hub_natural_gas", 1),
        ("wheat_futures", 1),
        ("corn_futures", 1),
        ("soybean_futures", 1),
        ("rough_rice_futures", 1),
        ("coffee_futures", 1),
        ("cocoa_futures", 1),
        ("sugar_futures", 1),
        ("fertilizer_ppi", 1),
        ("gdacs_non_green_events_count", 1),
    ],
    "Growth Slowdown Risk": [
        ("us_unemployment_rate", 1),
        ("us_nonfarm_payrolls", -1),
        ("us_initial_jobless_claims", 1),
        ("us_10y_2y_spread", -1),
        ("us_10y_3m_spread", -1),
        ("us_bank_lending_standards", 1),
        ("korea_unemployment_rate", 1),
        ("korea_employment_rate", -1),
    ],
    "Market Stress Risk": [
        ("vix", 1),
        ("kospi_vs_sp500", -1),
        ("sox_vs_sp500", -1),
        ("russell_2000", -1),
        ("copper_gold_ratio", -1),
    ],
    "Global Rate Divergence Risk": [
        ("us_japan_10y_gap", 1),
        ("us_germany_10y_gap", 1),
        ("us_korea_10y_gap", 1),
        ("us_treasury_10y", 1),
        ("germany_gov_bond_10y", 1),
        ("uk_gov_bond_10y", 1),
        ("canada_gov_bond_10y", 1),
        ("australia_gov_bond_10y", 1),
        ("japan_gov_bond_10y", 1),
    ],
}

OUTPUT_FIELDS = [
    "risk_name",
    "risk_score",
    "risk_score_delta",
    "indicator_id",
    "indicator_label",
    "category",
    "latest_date",
    "latest_value",
    "unit",
    "pct_change_3m",
    "pct_change_12m",
    "direction",
    "pressure",
    "pressure_label",
    "freshness_status",
    "alert_severity",
]


@dataclass(frozen=True)
class AttributionRow:
    risk_name: str
    risk_score: float | None
    risk_score_delta: float | None
    indicator_id: str
    indicator_label: str
    category: str
    latest_date: str
    latest_value: float | None
    unit: str
    pct_change_3m: float | None
    pct_change_12m: float | None
    direction: int
    pressure: float | None
    pressure_label: str
    freshness_status: str
    alert_severity: str


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip().replace(",", "")
    if text in {"", ".", "NA", "N/A", "null", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fmt_num(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "NA"
    if 0 < abs(value) < 0.01:
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    text = f"{value:,.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:+.1f}%"


def fmt_delta(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:+.1f}"


def latest_and_previous(rows: list[dict[str, str]]) -> tuple[dict[str, str], dict[str, str]]:
    if not rows:
        return {}, {}
    if len(rows) == 1:
        return rows[-1], {}
    return rows[-1], rows[-2]


def label_map(dashboard_rows: list[dict[str, str]]) -> dict[str, str]:
    labels = {}
    for row in dashboard_rows:
        indicator_id = row.get("indicator_id", "")
        label = row.get("field_ko", "")
        if indicator_id and label:
            labels[indicator_id] = label
    return labels


def alert_severity_by_item(alert_rows: list[dict[str, str]]) -> dict[str, str]:
    weights = {"major": 3, "watch": 2, "info": 1}
    result: dict[str, str] = {}
    for row in alert_rows:
        item_id = row.get("item_id", "")
        severity = row.get("severity", "")
        if not item_id:
            continue
        if weights.get(severity, 0) > weights.get(result.get(item_id, ""), 0):
            result[item_id] = severity
    return result


def pressure_label(pressure: float | None) -> str:
    if pressure is None:
        return "missing"
    if pressure >= 15:
        return "risk_up_major"
    if pressure >= 5:
        return "risk_up"
    if pressure <= -15:
        return "risk_down_major"
    if pressure <= -5:
        return "risk_down"
    return "neutral"


def build_attribution_rows(
    latest_risk: dict[str, str],
    previous_risk: dict[str, str],
    snapshot_rows: list[dict[str, str]],
    dashboard_rows: list[dict[str, str]],
    alert_rows: list[dict[str, str]],
) -> list[AttributionRow]:
    snapshot_by_id = {row.get("indicator_id", ""): row for row in snapshot_rows if row.get("indicator_id")}
    labels = label_map(dashboard_rows)
    severities = alert_severity_by_item(alert_rows)
    rows: list[AttributionRow] = []
    score_by_name = {label: parse_float(latest_risk.get(field)) for field, label in RISK_FIELDS}
    delta_by_name = {
        label: (
            parse_float(latest_risk.get(field)) - parse_float(previous_risk.get(field))
            if parse_float(latest_risk.get(field)) is not None and parse_float(previous_risk.get(field)) is not None
            else None
        )
        for field, label in RISK_FIELDS
    }
    for risk_name, drivers in RISK_DRIVER_MAP.items():
        for indicator_id, direction in drivers:
            source = snapshot_by_id.get(indicator_id)
            if not source:
                continue
            pct_3m = parse_float(source.get("pct_change_3m"))
            pressure = pct_3m * direction if pct_3m is not None else None
            latest_value = parse_float(source.get("latest_value"))
            rows.append(
                AttributionRow(
                    risk_name=risk_name,
                    risk_score=score_by_name.get(risk_name),
                    risk_score_delta=delta_by_name.get(risk_name),
                    indicator_id=indicator_id,
                    indicator_label=labels.get(indicator_id) or KEY_METRIC_LABELS.get(indicator_id) or source.get("name_ko", "") or indicator_id,
                    category=source.get("category", ""),
                    latest_date=source.get("latest_date", ""),
                    latest_value=latest_value,
                    unit=source.get("unit", ""),
                    pct_change_3m=pct_3m,
                    pct_change_12m=parse_float(source.get("pct_change_12m")),
                    direction=direction,
                    pressure=pressure,
                    pressure_label=pressure_label(pressure),
                    freshness_status=source.get("freshness_status", "") or "ok",
                    alert_severity=severities.get(indicator_id, ""),
                )
            )
    rows.sort(key=lambda row: (row.risk_name, abs(row.pressure or 0)), reverse=True)
    return rows


def row_to_dict(row: AttributionRow) -> dict[str, Any]:
    return {
        "risk_name": row.risk_name,
        "risk_score": row.risk_score,
        "risk_score_delta": row.risk_score_delta,
        "indicator_id": row.indicator_id,
        "indicator_label": row.indicator_label,
        "category": row.category,
        "latest_date": row.latest_date,
        "latest_value": row.latest_value,
        "unit": row.unit,
        "pct_change_3m": row.pct_change_3m,
        "pct_change_12m": row.pct_change_12m,
        "direction": row.direction,
        "pressure": row.pressure,
        "pressure_label": row.pressure_label,
        "freshness_status": row.freshness_status,
        "alert_severity": row.alert_severity,
    }


def markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell.replace("|", "/") for cell in row) + " |")
    return lines


def top_rows(rows: list[AttributionRow], risk_name: str, positive: bool, limit: int = 4) -> list[AttributionRow]:
    filtered = [row for row in rows if row.risk_name == risk_name and row.pressure is not None]
    if positive:
        filtered = [row for row in filtered if (row.pressure or 0) > 0]
        return sorted(filtered, key=lambda row: row.pressure or 0, reverse=True)[:limit]
    filtered = [row for row in filtered if (row.pressure or 0) < 0]
    return sorted(filtered, key=lambda row: row.pressure or 0)[:limit]


def format_driver_list(rows: list[AttributionRow]) -> str:
    if not rows:
        return "None"
    return "; ".join(
        f"{row.indicator_label} {fmt_pct(row.pct_change_3m)} pressure {fmt_delta(row.pressure)}"
        for row in rows
    )


def build_report(
    latest_risk: dict[str, str],
    previous_risk: dict[str, str],
    rows: list[AttributionRow],
) -> tuple[str, str]:
    report_date = latest_risk.get("report_date") or date.today().isoformat()
    current = latest_risk.get("current_regime", "NA")
    previous = previous_risk.get("current_regime", "NA")
    score_lines = []
    for field, risk_name in RISK_FIELDS:
        latest_score = parse_float(latest_risk.get(field))
        previous_score = parse_float(previous_risk.get(field))
        delta = latest_score - previous_score if latest_score is not None and previous_score is not None else None
        score_lines.append([risk_name, fmt_num(latest_score), fmt_num(previous_score), fmt_delta(delta)])

    lines = [
        "# Risk Attribution Report",
        "",
        f"Generated at: {datetime.now().replace(microsecond=0).isoformat()}",
        f"Report date: {report_date}",
        f"Regime: {previous} -> {current}" if previous != "NA" and previous != current else f"Regime: {current}",
        "",
        "## Score Changes",
        *markdown_table(["Risk", "Latest", "Previous", "Delta"], score_lines),
        "",
        "## Driver Attribution",
    ]
    for _field, risk_name in RISK_FIELDS:
        risk_rows = [row for row in rows if row.risk_name == risk_name]
        if not risk_rows:
            continue
        latest_score = risk_rows[0].risk_score
        score_delta = risk_rows[0].risk_score_delta
        lines.extend(
            [
                "",
                f"### {risk_name}",
                f"- Score: {fmt_num(latest_score)} ({fmt_delta(score_delta)} vs previous report)",
                f"- Risk-up pressure: {format_driver_list(top_rows(rows, risk_name, positive=True))}",
                f"- Risk-down pressure: {format_driver_list(top_rows(rows, risk_name, positive=False))}",
                "",
                *markdown_table(
                    ["Driver", "3M", "12M", "Pressure", "Fresh", "Alert"],
                    [
                        [
                            row.indicator_label,
                            fmt_pct(row.pct_change_3m),
                            fmt_pct(row.pct_change_12m),
                            fmt_delta(row.pressure),
                            row.freshness_status,
                            row.alert_severity,
                        ]
                        for row in sorted(risk_rows, key=lambda item: abs(item.pressure or 0), reverse=True)[:8]
                    ],
                ),
            ]
        )
    return "\n".join(lines) + "\n", report_date


def write_outputs(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    risk_rows = read_csv(Path(args.risk_history))
    latest_risk, previous_risk = latest_and_previous(risk_rows)
    rows = build_attribution_rows(
        latest_risk,
        previous_risk,
        read_csv(Path(args.snapshot)),
        read_csv(Path(args.dashboard)),
        read_csv(Path(args.alerts)),
    )
    report, report_date = build_report(latest_risk, previous_risk, rows)
    output_csv = Path(args.output_csv)
    write_csv(output_csv, [row_to_dict(row) for row in rows], OUTPUT_FIELDS)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = Path(args.output) if args.output else report_dir / f"risk_attribution_{report_date}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    latest_report = Path(args.latest_output)
    latest_report.parent.mkdir(parents=True, exist_ok=True)
    latest_report.write_text(report, encoding="utf-8")
    return report_path, latest_report, output_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate risk-score attribution from latest macro data.")
    parser.add_argument("--risk-history", default=str(DEFAULT_RISK_HISTORY))
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--dashboard", default=str(DEFAULT_DASHBOARD))
    parser.add_argument("--alerts", default=str(DEFAULT_ALERTS))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--output", default="")
    parser.add_argument("--latest-output", default=str(DEFAULT_LATEST_REPORT))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report_path, latest_report, output_csv = write_outputs(args)
    print(f"Generated attribution report: {report_path}")
    print(f"Updated latest attribution report: {latest_report}")
    print(f"Wrote attribution CSV: {output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
