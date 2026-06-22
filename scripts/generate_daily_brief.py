#!/usr/bin/env python3
"""Generate a concise daily decision brief from the latest macro outputs."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any


DEFAULT_RISK_HISTORY = Path("data/processed/macro/risk_score_history.csv")
DEFAULT_ALERTS = Path("data/processed/macro/change_alerts_latest.csv")
DEFAULT_ATTRIBUTION = Path("data/processed/macro/risk_attribution_latest.csv")
DEFAULT_QUALITY = Path("data/processed/macro/data_quality_latest.csv")
DEFAULT_REPORT_DIR = Path("reports")
DEFAULT_LATEST_REPORT = Path("reports/daily_brief_latest.md")

RISK_FIELDS = [
    ("inflation_risk", "Inflation"),
    ("liquidity_bubble_risk", "Liquidity"),
    ("credit_stress_risk", "Credit"),
    ("fx_risk", "FX"),
    ("climate_supply_shock_risk", "Climate"),
    ("growth_slowdown_risk", "Growth"),
    ("market_stress_risk", "Market Stress"),
    ("global_rate_divergence_risk", "Rate Divergence"),
]

ALLOCATION_FIELDS = [
    ("cash_amount", "Cash/short bonds"),
    ("gold_amount", "Gold"),
    ("silver_amount", "Silver/commodities"),
    ("equity_amount", "Equity/ETF"),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


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
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    text = f"{value:,.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


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


def severity_weight(severity: str) -> int:
    return {"major": 3, "watch": 2, "info": 1}.get(severity, 0)


def markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell.replace("|", "/") for cell in row) + " |")
    return lines


def score_rows(latest: dict[str, str], previous: dict[str, str]) -> list[list[str]]:
    rows = []
    for field, label in RISK_FIELDS:
        latest_value = parse_float(latest.get(field))
        previous_value = parse_float(previous.get(field))
        delta = latest_value - previous_value if latest_value is not None and previous_value is not None else None
        rows.append([label, fmt_num(latest_value), fmt_delta(delta)])
    return rows


def allocation_rows(latest: dict[str, str], previous: dict[str, str]) -> list[list[str]]:
    rows = []
    for field, label in ALLOCATION_FIELDS:
        latest_value = parse_float(latest.get(field))
        previous_value = parse_float(previous.get(field))
        delta = latest_value - previous_value if latest_value is not None and previous_value is not None else None
        rows.append([label, f"{fmt_num(latest_value, 0)}m", fmt_delta(delta)])
    return rows


def top_alerts(alert_rows: list[dict[str, str]], limit: int = 8) -> list[dict[str, str]]:
    return sorted(
        alert_rows,
        key=lambda row: (
            severity_weight(row.get("severity", "")),
            abs(parse_float(row.get("delta")) or parse_float(row.get("pct_change_3m")) or 0),
        ),
        reverse=True,
    )[:limit]


def top_attribution(attribution_rows: list[dict[str, str]], positive: bool, limit: int = 6) -> list[dict[str, str]]:
    rows = []
    for row in attribution_rows:
        pressure = parse_float(row.get("pressure"))
        if pressure is None:
            continue
        if positive and pressure <= 0:
            continue
        if not positive and pressure >= 0:
            continue
        rows.append(row)
    return sorted(rows, key=lambda row: abs(parse_float(row.get("pressure")) or 0), reverse=True)[:limit]


def quality_overall(quality_rows: list[dict[str, str]]) -> dict[str, str]:
    for row in quality_rows:
        if row.get("scope_type") == "overall":
            return row
    return {}


def action_lines(latest: dict[str, str], alerts: list[dict[str, str]], quality: dict[str, str]) -> list[str]:
    major_alerts = sum(1 for row in alerts if row.get("severity") == "major")
    quality_score = parse_float(quality.get("overall_score"))
    lines = []
    if quality_score is not None and quality_score < 80:
        lines.append("- Data confidence is below B; review stale/failing sources before changing allocation.")
    if major_alerts:
        lines.append(f"- Review {major_alerts} major change alerts before acting on the latest regime.")
    fx = parse_float(latest.get("fx_risk"))
    inflation = parse_float(latest.get("inflation_risk"))
    credit = parse_float(latest.get("credit_stress_risk"))
    if credit is not None and credit >= 6:
        lines.append("- Credit stress is elevated; prioritize cash/short-bond defense.")
    if inflation is not None and inflation >= 6:
        lines.append("- Inflation risk is elevated; keep hedge sleeve under review.")
    if fx is not None and fx >= 6:
        lines.append("- FX risk is elevated; watch USD/KRW and foreign-flow alerts.")
    if not lines:
        lines.append("- No emergency rule fired; follow the suggested sleeve allocation and monitor major alerts.")
    return lines


def build_report(
    risk_rows: list[dict[str, str]],
    alert_rows: list[dict[str, str]],
    attribution_rows: list[dict[str, str]],
    quality_rows: list[dict[str, str]],
) -> tuple[str, str]:
    latest, previous = latest_and_previous(risk_rows)
    report_date = latest.get("report_date") or date.today().isoformat()
    quality = quality_overall(quality_rows)
    alerts = top_alerts(alert_rows)
    risk_up = top_attribution(attribution_rows, positive=True)
    risk_down = top_attribution(attribution_rows, positive=False)
    regime = latest.get("current_regime", "NA")
    prev_regime = previous.get("current_regime", "NA")
    regime_text = f"{prev_regime} -> {regime}" if prev_regime != "NA" and prev_regime != regime else regime

    lines = [
        "# Daily Macro Decision Brief",
        "",
        f"Generated at: {datetime.now().replace(microsecond=0).isoformat()}",
        f"Report date: {report_date}",
        "",
        "## Dashboard Links",
        "- [Sector dashboard](sector_dashboard.html)",
        "- [Decision engine](decision_engine.html)",
        "- [Rebalance orders](rebalance_orders.html)",
        "- [Scenario simulator](scenario_simulator.html)",
        "- [Scenario matrix](scenario_matrix.html)",
        "- [Scenario ETF backtests](scenario_etf_backtests.html)",
        "- [Change alerts](alerts_latest.md)",
        "- [Risk attribution](risk_attribution_latest.md)",
        "- [Data quality](data_quality_latest.md)",
        "",
        "## Executive Summary",
        f"- Regime: {regime_text}",
        f"- Supporting regime: {latest.get('supporting_regime', 'NA')}",
        f"- Data confidence: {quality.get('overall_score', 'NA')} / 100 ({quality.get('grade', 'NA')})",
        f"- Major alerts: {sum(1 for row in alert_rows if row.get('severity') == 'major')}",
        "",
        "## Action Checklist",
        *action_lines(latest, alert_rows, quality),
        "",
        "## Risk Scores",
        *markdown_table(["Risk", "Latest", "Delta"], score_rows(latest, previous)),
        "",
        "## Suggested Allocation",
        *markdown_table(["Sleeve", "Latest", "Delta"], allocation_rows(latest, previous)),
        "",
        "## Top Alerts",
    ]
    if alerts:
        lines.extend(
            markdown_table(
                ["Severity", "Type", "Item", "Move"],
                [
                    [
                        row.get("severity", ""),
                        row.get("alert_type", ""),
                        row.get("item_label", ""),
                        fmt_num(parse_float(row.get("delta")) or parse_float(row.get("pct_change_3m"))),
                    ]
                    for row in alerts
                ],
            )
        )
    else:
        lines.append("No active alerts.")
    lines.extend(["", "## Main Risk-Up Drivers"])
    if risk_up:
        lines.extend(
            markdown_table(
                ["Risk", "Driver", "3M", "Pressure", "Alert"],
                [
                    [
                        row.get("risk_name", ""),
                        row.get("indicator_label", ""),
                        fmt_num(parse_float(row.get("pct_change_3m"))),
                        fmt_num(parse_float(row.get("pressure"))),
                        row.get("alert_severity", ""),
                    ]
                    for row in risk_up
                ],
            )
        )
    else:
        lines.append("No risk-up attribution rows.")
    lines.extend(["", "## Main Risk-Down Drivers"])
    if risk_down:
        lines.extend(
            markdown_table(
                ["Risk", "Driver", "3M", "Pressure", "Alert"],
                [
                    [
                        row.get("risk_name", ""),
                        row.get("indicator_label", ""),
                        fmt_num(parse_float(row.get("pct_change_3m"))),
                        fmt_num(parse_float(row.get("pressure"))),
                        row.get("alert_severity", ""),
                    ]
                    for row in risk_down
                ],
            )
        )
    else:
        lines.append("No risk-down attribution rows.")
    return "\n".join(lines) + "\n", report_date


def write_outputs(args: argparse.Namespace) -> tuple[Path, Path]:
    report, report_date = build_report(
        read_csv(Path(args.risk_history)),
        read_csv(Path(args.alerts)),
        read_csv(Path(args.attribution)),
        read_csv(Path(args.quality)),
    )
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = Path(args.output) if args.output else report_dir / f"daily_brief_{report_date}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    latest_report = Path(args.latest_output)
    latest_report.parent.mkdir(parents=True, exist_ok=True)
    latest_report.write_text(report, encoding="utf-8")
    return report_path, latest_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a daily macro decision brief.")
    parser.add_argument("--risk-history", default=str(DEFAULT_RISK_HISTORY))
    parser.add_argument("--alerts", default=str(DEFAULT_ALERTS))
    parser.add_argument("--attribution", default=str(DEFAULT_ATTRIBUTION))
    parser.add_argument("--quality", default=str(DEFAULT_QUALITY))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--output", default="")
    parser.add_argument("--latest-output", default=str(DEFAULT_LATEST_REPORT))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report_path, latest_report = write_outputs(args)
    print(f"Generated daily brief: {report_path}")
    print(f"Updated latest daily brief: {latest_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
