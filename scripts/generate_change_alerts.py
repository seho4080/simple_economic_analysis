#!/usr/bin/env python3
"""Generate change alerts from macro score history and latest indicators."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    from macro_rules import KEY_METRIC_LABELS
except ImportError:  # pragma: no cover - allows isolated script tests
    KEY_METRIC_LABELS = {}


DEFAULT_RISK_HISTORY = Path("data/processed/macro/risk_score_history.csv")
DEFAULT_SNAPSHOT = Path("data/processed/macro/latest_snapshot.csv")
DEFAULT_DASHBOARD = Path("data/processed/macro/requested_indicators_latest.csv")
DEFAULT_ALERT_CSV = Path("data/processed/macro/change_alerts_latest.csv")
DEFAULT_REPORT_DIR = Path("reports")
DEFAULT_LATEST_REPORT = Path("reports/alerts_latest.md")

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

ALLOCATION_FIELDS = [
    ("cash_amount", "Cash/short bonds"),
    ("gold_amount", "Gold"),
    ("silver_amount", "Silver/commodities"),
    ("equity_amount", "Equity/ETF"),
]

ALERT_FIELDS = [
    "alert_type",
    "severity",
    "category",
    "item_id",
    "item_label",
    "latest_date",
    "latest_value",
    "previous_value",
    "delta",
    "pct_change_3m",
    "pct_change_12m",
    "detail",
]


@dataclass(frozen=True)
class RiskChange:
    field: str
    label: str
    latest: float | None
    previous: float | None
    delta: float | None
    severity: str


@dataclass(frozen=True)
class IndicatorMove:
    indicator_id: str
    label: str
    category: str
    latest_date: str
    latest_value: float | None
    unit: str
    pct_change_3m: float | None
    pct_change_12m: float | None
    freshness: str
    source: str


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


def fmt_delta(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "NA"
    return f"{value:+.{digits}f}"


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:+.1f}%"


def severity_from_delta(delta: float | None, warn_threshold: float, major_threshold: float) -> str:
    if delta is None:
        return "none"
    abs_delta = abs(delta)
    if abs_delta >= major_threshold:
        return "major"
    if abs_delta >= warn_threshold:
        return "watch"
    return "info"


def severity_from_pct(pct_change: float | None, watch_threshold: float, major_threshold: float) -> str:
    if pct_change is None:
        return "none"
    abs_change = abs(pct_change)
    if abs_change >= major_threshold:
        return "major"
    if abs_change >= watch_threshold:
        return "watch"
    return "info"


def label_map(dashboard_rows: list[dict[str, str]]) -> dict[str, str]:
    labels = {}
    for row in dashboard_rows:
        indicator_id = row.get("indicator_id", "")
        label = row.get("field_ko", "")
        if indicator_id and label:
            labels[indicator_id] = label
    return labels


def latest_and_previous(rows: list[dict[str, str]]) -> tuple[dict[str, str], dict[str, str]]:
    if not rows:
        return {}, {}
    if len(rows) == 1:
        return rows[-1], {}
    return rows[-1], rows[-2]


def build_risk_changes(
    latest: dict[str, str],
    previous: dict[str, str],
    warn_threshold: float,
    major_threshold: float,
) -> list[RiskChange]:
    changes = []
    for field, label in RISK_FIELDS:
        latest_value = parse_float(latest.get(field))
        previous_value = parse_float(previous.get(field))
        delta = None
        if latest_value is not None and previous_value is not None:
            delta = latest_value - previous_value
        changes.append(
            RiskChange(
                field=field,
                label=label,
                latest=latest_value,
                previous=previous_value,
                delta=delta,
                severity=severity_from_delta(delta, warn_threshold, major_threshold),
            )
        )
    return sorted(
        changes,
        key=lambda item: abs(item.delta) if item.delta is not None else -1,
        reverse=True,
    )


def build_indicator_moves(
    snapshot_rows: list[dict[str, str]],
    labels: dict[str, str],
    pct_threshold: float,
    major_pct_threshold: float,
    include_stale: bool,
    limit: int,
) -> list[IndicatorMove]:
    moves: list[IndicatorMove] = []
    for row in snapshot_rows:
        indicator_id = row.get("indicator_id", "")
        pct_3m = parse_float(row.get("pct_change_3m"))
        if pct_3m is None or abs(pct_3m) < pct_threshold:
            continue
        freshness = row.get("freshness_status", "") or "ok"
        if freshness != "ok" and not include_stale:
            continue
        move = IndicatorMove(
            indicator_id=indicator_id,
            label=labels.get(indicator_id) or KEY_METRIC_LABELS.get(indicator_id) or row.get("name_ko") or indicator_id,
            category=row.get("category", ""),
            latest_date=row.get("latest_date", ""),
            latest_value=parse_float(row.get("latest_value")),
            unit=row.get("unit", ""),
            pct_change_3m=pct_3m,
            pct_change_12m=parse_float(row.get("pct_change_12m")),
            freshness=freshness,
            source=row.get("source", ""),
        )
        # Attach severity lazily through alert rows/report formatting.
        severity_from_pct(move.pct_change_3m, pct_threshold, major_pct_threshold)
        moves.append(move)
    moves.sort(key=lambda item: abs(item.pct_change_3m or 0), reverse=True)
    return moves[:limit]


def build_watchlist_moves(
    snapshot_rows: list[dict[str, str]],
    labels: dict[str, str],
    pct_threshold: float,
    include_stale: bool,
    limit: int,
) -> list[IndicatorMove]:
    watch_ids = set(KEY_METRIC_LABELS)
    rows = [row for row in snapshot_rows if row.get("indicator_id") in watch_ids]
    return build_indicator_moves(
        rows,
        labels,
        pct_threshold=pct_threshold,
        major_pct_threshold=max(pct_threshold * 2, 1),
        include_stale=include_stale,
        limit=limit,
    )


def notable_risk_changes(changes: list[RiskChange]) -> list[RiskChange]:
    return [item for item in changes if item.severity in {"major", "watch"}]


def allocation_changes(latest: dict[str, str], previous: dict[str, str]) -> list[dict[str, Any]]:
    changes = []
    for field, label in ALLOCATION_FIELDS:
        latest_value = parse_float(latest.get(field))
        previous_value = parse_float(previous.get(field))
        if latest_value is None or previous_value is None:
            continue
        delta = latest_value - previous_value
        if delta == 0:
            continue
        changes.append(
            {
                "field": field,
                "label": label,
                "latest": latest_value,
                "previous": previous_value,
                "delta": delta,
            }
        )
    return changes


def stale_items(snapshot_rows: list[dict[str, str]], limit: int = 10) -> list[dict[str, str]]:
    rows = [row for row in snapshot_rows if row.get("freshness_status") == "stale"]
    rows.sort(key=lambda row: parse_float(row.get("age_days")) or 0, reverse=True)
    return rows[:limit]


def markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        safe = [cell.replace("|", "/") for cell in row]
        lines.append("| " + " | ".join(safe) + " |")
    return lines


def risk_table(changes: list[RiskChange]) -> list[str]:
    return markdown_table(
        ["Risk", "Latest", "Previous", "Delta", "Severity"],
        [
            [
                item.label,
                fmt_num(item.latest),
                fmt_num(item.previous),
                fmt_delta(item.delta),
                item.severity,
            ]
            for item in changes
        ],
    )


def indicator_table(moves: list[IndicatorMove], pct_threshold: float, major_pct_threshold: float) -> list[str]:
    return markdown_table(
        ["Indicator", "Category", "Latest", "3M", "12M", "Fresh", "Source"],
        [
            [
                item.label,
                item.category,
                f"{fmt_num(item.latest_value)} {item.unit}".strip(),
                f"{fmt_pct(item.pct_change_3m)} ({severity_from_pct(item.pct_change_3m, pct_threshold, major_pct_threshold)})",
                fmt_pct(item.pct_change_12m),
                item.freshness,
                item.source,
            ]
            for item in moves
        ],
    )


def build_alert_rows(
    latest: dict[str, str],
    previous: dict[str, str],
    risk_changes: list[RiskChange],
    indicator_moves: list[IndicatorMove],
    pct_threshold: float,
    major_pct_threshold: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    report_date = latest.get("report_date", "")
    if latest.get("current_regime") and previous.get("current_regime") and latest.get("current_regime") != previous.get("current_regime"):
        rows.append(
            {
                "alert_type": "regime_change",
                "severity": "major",
                "category": "regime",
                "item_id": "current_regime",
                "item_label": "Current regime",
                "latest_date": report_date,
                "latest_value": latest.get("current_regime", ""),
                "previous_value": previous.get("current_regime", ""),
                "delta": "",
                "pct_change_3m": "",
                "pct_change_12m": "",
                "detail": "Regime changed from previous report.",
            }
        )
    for item in notable_risk_changes(risk_changes):
        rows.append(
            {
                "alert_type": "risk_score_change",
                "severity": item.severity,
                "category": "risk_score",
                "item_id": item.field,
                "item_label": item.label,
                "latest_date": report_date,
                "latest_value": item.latest,
                "previous_value": item.previous,
                "delta": item.delta,
                "pct_change_3m": "",
                "pct_change_12m": "",
                "detail": "Risk score changed versus previous report.",
            }
        )
    for item in indicator_moves:
        rows.append(
            {
                "alert_type": "indicator_mover",
                "severity": severity_from_pct(item.pct_change_3m, pct_threshold, major_pct_threshold),
                "category": item.category,
                "item_id": item.indicator_id,
                "item_label": item.label,
                "latest_date": item.latest_date,
                "latest_value": item.latest_value,
                "previous_value": "",
                "delta": "",
                "pct_change_3m": item.pct_change_3m,
                "pct_change_12m": item.pct_change_12m,
                "detail": f"3M move crossed {pct_threshold:g}% threshold.",
            }
        )
    return rows


def build_report(
    risk_rows: list[dict[str, str]],
    snapshot_rows: list[dict[str, str]],
    dashboard_rows: list[dict[str, str]],
    score_warn_threshold: float,
    score_major_threshold: float,
    pct_threshold: float,
    major_pct_threshold: float,
    include_stale: bool,
    indicator_limit: int,
    watchlist_threshold: float,
) -> tuple[str, list[dict[str, Any]], str]:
    latest, previous = latest_and_previous(risk_rows)
    labels = label_map(dashboard_rows)
    report_date = latest.get("report_date") or date.today().isoformat()
    changes = build_risk_changes(latest, previous, score_warn_threshold, score_major_threshold)
    movers = build_indicator_moves(
        snapshot_rows,
        labels,
        pct_threshold=pct_threshold,
        major_pct_threshold=major_pct_threshold,
        include_stale=include_stale,
        limit=indicator_limit,
    )
    watchlist = build_watchlist_moves(
        snapshot_rows,
        labels,
        pct_threshold=watchlist_threshold,
        include_stale=include_stale,
        limit=12,
    )
    alloc_changes = allocation_changes(latest, previous)
    stale = stale_items(snapshot_rows)
    alerts = build_alert_rows(latest, previous, changes, movers, pct_threshold, major_pct_threshold)
    notable = notable_risk_changes(changes)
    latest_regime = latest.get("current_regime", "NA")
    previous_regime = previous.get("current_regime", "NA")
    regime_line = (
        f"- Regime changed: {previous_regime} -> {latest_regime}"
        if previous_regime != "NA" and latest_regime != previous_regime
        else f"- Regime unchanged: {latest_regime}"
    )
    risk_summary = ", ".join(f"{item.label} {fmt_delta(item.delta)}" for item in notable[:3]) or "No score moves crossed alert thresholds."
    mover_summary = ", ".join(f"{item.label} {fmt_pct(item.pct_change_3m)}" for item in movers[:5]) or "No indicator movers crossed threshold."

    lines = [
        "# Macro Change Alerts",
        "",
        f"Generated at: {datetime.now().replace(microsecond=0).isoformat()}",
        f"Report date: {report_date}",
        f"Baseline: {previous.get('report_date', 'NA')} -> {latest.get('report_date', 'NA')}",
        "",
        "## Summary",
        regime_line,
        f"- Risk score movers: {risk_summary}",
        f"- Indicator movers: {mover_summary}",
        f"- Structured alert rows: {len(alerts)}",
        "",
        "## Risk Score Changes",
        *risk_table(changes),
        "",
        "## Allocation Changes",
    ]
    if alloc_changes:
        lines.extend(
            markdown_table(
                ["Sleeve", "Latest", "Previous", "Delta"],
                [
                    [
                        item["label"],
                        f"{fmt_num(item['latest'], 0)}m KRW",
                        f"{fmt_num(item['previous'], 0)}m KRW",
                        f"{fmt_delta(item['delta'], 0)}m KRW",
                    ]
                    for item in alloc_changes
                ],
            )
        )
    else:
        lines.append("No allocation sleeve changed versus the previous report.")
    lines.extend(
        [
            "",
            "## Top Indicator Movers",
        ]
    )
    if movers:
        lines.extend(indicator_table(movers, pct_threshold, major_pct_threshold))
    else:
        lines.append("No indicator crossed the configured 3M move threshold.")
    lines.extend(
        [
            "",
            "## Watchlist Movers",
        ]
    )
    if watchlist:
        lines.extend(indicator_table(watchlist, watchlist_threshold, max(watchlist_threshold * 2, 1)))
    else:
        lines.append("No key watchlist indicator crossed the configured 3M threshold.")
    lines.extend(
        [
            "",
            "## Data Quality Notes",
            f"- Snapshot indicators: {len(snapshot_rows)}",
            f"- Stale indicators: {sum(1 for row in snapshot_rows if row.get('freshness_status') == 'stale')}",
        ]
    )
    if stale:
        lines.extend(
            [
                "",
                *markdown_table(
                    ["Indicator", "Latest date", "Age days", "Source"],
                    [
                        [
                            labels.get(row.get("indicator_id", "")) or row.get("name_ko", "") or row.get("indicator_id", ""),
                            row.get("latest_date", ""),
                            row.get("age_days", ""),
                            row.get("source", ""),
                        ]
                        for row in stale
                    ],
                ),
            ]
        )
    return "\n".join(lines) + "\n", alerts, report_date


def write_outputs(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    risk_rows = read_csv(Path(args.risk_history))
    snapshot_rows = read_csv(Path(args.snapshot))
    dashboard_rows = read_csv(Path(args.dashboard))
    report, alert_rows, report_date = build_report(
        risk_rows,
        snapshot_rows,
        dashboard_rows,
        score_warn_threshold=args.score_warn_threshold,
        score_major_threshold=args.score_major_threshold,
        pct_threshold=args.indicator_pct_threshold,
        major_pct_threshold=args.indicator_major_pct_threshold,
        include_stale=args.include_stale,
        indicator_limit=args.indicator_limit,
        watchlist_threshold=args.watchlist_pct_threshold,
    )
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    output = Path(args.output) if args.output else report_dir / f"alerts_{report_date}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    latest_output = Path(args.latest_output)
    latest_output.parent.mkdir(parents=True, exist_ok=True)
    latest_output.write_text(report, encoding="utf-8")
    alert_csv = Path(args.alert_csv)
    write_csv(alert_csv, alert_rows, ALERT_FIELDS)
    return output, latest_output, alert_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate macro change alerts from processed data.")
    parser.add_argument("--risk-history", default=str(DEFAULT_RISK_HISTORY))
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--dashboard", default=str(DEFAULT_DASHBOARD))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--output", default="")
    parser.add_argument("--latest-output", default=str(DEFAULT_LATEST_REPORT))
    parser.add_argument("--alert-csv", default=str(DEFAULT_ALERT_CSV))
    parser.add_argument("--score-warn-threshold", type=float, default=0.7)
    parser.add_argument("--score-major-threshold", type=float, default=1.0)
    parser.add_argument("--indicator-pct-threshold", type=float, default=15.0)
    parser.add_argument("--indicator-major-pct-threshold", type=float, default=30.0)
    parser.add_argument("--watchlist-pct-threshold", type=float, default=8.0)
    parser.add_argument("--indicator-limit", type=int, default=20)
    parser.add_argument("--include-stale", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output, latest_output, alert_csv = write_outputs(args)
    print(f"Generated alert report: {output}")
    print(f"Updated latest alert report: {latest_output}")
    print(f"Wrote alert CSV: {alert_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
