#!/usr/bin/env python3
"""Generate a decision engine report from macro, alert, quality, scenario, and ETF outputs."""

from __future__ import annotations

import argparse
import csv
import math
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any


DEFAULT_RISK_HISTORY = Path("data/processed/macro/risk_score_history.csv")
DEFAULT_ALERTS = Path("data/processed/macro/change_alerts_latest.csv")
DEFAULT_QUALITY = Path("data/processed/macro/data_quality_latest.csv")
DEFAULT_SCENARIO_MATRIX = Path("data/processed/macro/scenario_matrix_latest.csv")
DEFAULT_SCENARIO_ETF = Path("data/processed/backtests/scenario_etf_backtests/scenario_etf_summary.csv")
DEFAULT_HTML = Path("reports/decision_engine.html")
DEFAULT_MD = Path("reports/decision_engine_latest.md")
DEFAULT_SUMMARY_CSV = Path("data/processed/macro/decision_engine_latest.csv")
DEFAULT_ACTIONS_CSV = Path("data/processed/macro/decision_actions_latest.csv")

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
    ("cash", "Cash/short bonds"),
    ("gold", "Gold"),
    ("silver", "Silver/commodities"),
    ("equity", "Equity/ETF"),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_float(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (float, int)):
        return None if math.isnan(float(value)) else float(value)
    text = value.strip().replace(",", "")
    if text in {"", ".", "NA", "N/A", "null", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value: str | float | int | None) -> int:
    parsed = parse_float(value)
    return int(round(parsed)) if parsed is not None else 0


def fmt_num(value: float | int | None, digits: int = 1) -> str:
    if value is None:
        return "NA"
    text = f"{float(value):,.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:.1%}"


def latest_row(rows: list[dict[str, str]]) -> dict[str, str]:
    return rows[-1] if rows else {}


def quality_overall(rows: list[dict[str, str]]) -> dict[str, str]:
    for row in rows:
        if row.get("scope_type") == "overall":
            return row
    return {}


def alert_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts = {"major": 0, "watch": 0, "info": 0, "total": 0}
    for row in rows:
        severity = row.get("severity", "info")
        counts[severity] = counts.get(severity, 0) + 1
        counts["total"] += 1
    return counts


def severity_weight(row: dict[str, str]) -> tuple[int, float]:
    severity_score = {"major": 3, "watch": 2, "info": 1}.get(row.get("severity", ""), 0)
    move = abs(parse_float(row.get("delta")) or parse_float(row.get("pct_change_3m")) or 0.0)
    return severity_score, move


def top_alerts(rows: list[dict[str, str]], limit: int = 6) -> list[dict[str, str]]:
    return sorted(rows, key=severity_weight, reverse=True)[:limit]


def allocation_from_latest(row: dict[str, str]) -> dict[str, int]:
    return {
        "cash": parse_int(row.get("cash_amount")),
        "gold": parse_int(row.get("gold_amount")),
        "silver": parse_int(row.get("silver_amount")),
        "equity": parse_int(row.get("equity_amount")),
    }


def policy_from_inputs(
    latest: dict[str, str],
    alert_rows: list[dict[str, str]],
    quality: dict[str, str],
) -> dict[str, Any]:
    qscore = parse_float(quality.get("overall_score"))
    counts = alert_counts(alert_rows)
    regime_changed = any(row.get("alert_type") == "regime_change" for row in alert_rows)
    inflation = parse_float(latest.get("inflation_risk")) or 0.0
    fx = parse_float(latest.get("fx_risk")) or 0.0
    credit = parse_float(latest.get("credit_stress_risk")) or 0.0
    growth = parse_float(latest.get("growth_slowdown_risk")) or 0.0
    market = parse_float(latest.get("market_stress_risk")) or 0.0

    if qscore is not None and qscore < 75:
        action_level = "Review only"
        posture = "Data constrained"
    elif credit >= 6.5 or growth >= 6.5 or market >= 7.0:
        action_level = "Defensive rebalance"
        posture = "Defensive"
    elif inflation >= 6.0 and fx >= 6.0:
        action_level = "Hedge tilt"
        posture = "Inflation/FX hedge"
    elif counts["major"] >= 5 or regime_changed:
        action_level = "Confirm before adding risk"
        posture = "Watch"
    else:
        action_level = "Proceed with baseline accumulation"
        posture = "Balanced"

    if qscore is None or qscore < 80 or counts["major"] >= 8:
        confidence = "Medium"
    elif counts["major"] >= 3:
        confidence = "Medium-high"
    else:
        confidence = "High"

    return {
        "action_level": action_level,
        "risk_posture": posture,
        "decision_confidence": confidence,
        "quality_score": qscore,
        "quality_grade": quality.get("grade", "NA"),
        "major_alerts": counts["major"],
        "watch_alerts": counts["watch"],
        "regime_changed": regime_changed,
    }


def select_best_etf_rows(rows: list[dict[str, str]], scenario_slug: str = "baseline", limit: int = 3) -> list[dict[str, str]]:
    candidates = [
        row
        for row in rows
        if row.get("scenario_slug") == scenario_slug and parse_int(row.get("missing_lots")) == 0
    ]
    if not candidates:
        candidates = [row for row in rows if parse_int(row.get("missing_lots")) == 0]
    return sorted(
        candidates,
        key=lambda row: (
            parse_float(row.get("xirr")) or -999,
            parse_float(row.get("excess_xirr")) or -999,
            parse_float(row.get("simple_return")) or -999,
        ),
        reverse=True,
    )[:limit]


def scenario_context(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    baseline = next((row for row in rows if row.get("scenario_slug") == "baseline"), {})
    nonbaseline = [row for row in rows if row.get("scenario_slug") != "baseline"]
    closest = min(nonbaseline, key=lambda row: parse_float(row.get("nearest_distance")) or 999, default={})
    downside = min(nonbaseline, key=lambda row: parse_float(row.get("worst_forward_3m")) or 999, default={})
    return {"baseline": baseline, "closest_stress": closest, "downside_stress": downside}


def build_actions(
    latest: dict[str, str],
    policy: dict[str, Any],
    best_etf_rows: list[dict[str, str]],
    context: dict[str, dict[str, str]],
    alert_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    allocation = allocation_from_latest(latest)
    best = best_etf_rows[0] if best_etf_rows else {}
    downside = context.get("downside_stress", {})
    actions: list[dict[str, Any]] = [
        {
            "priority": 1,
            "severity": "primary",
            "title": policy["action_level"],
            "detail": (
                f"Use current baseline allocation: cash {allocation['cash']}m, gold {allocation['gold']}m, "
                f"silver/resources {allocation['silver']}m, equity/ETF {allocation['equity']}m."
            ),
        }
    ]
    if best:
        actions.append(
            {
                "priority": 2,
                "severity": "implementation",
                "title": "Implementation candidate",
                "detail": (
                    f"{best.get('variant_title', best.get('variant', 'ETF variant'))}: "
                    f"scenario XIRR {fmt_pct(parse_float(best.get('xirr')))}, "
                    f"gap vs dynamic baseline {fmt_pct(parse_float(best.get('excess_xirr')))}."
                ),
            }
        )
    if downside:
        actions.append(
            {
                "priority": 3,
                "severity": "stress",
                "title": "Stress check",
                "detail": (
                    f"Most negative saved stress scenario is {downside.get('title', downside.get('scenario_slug', 'NA'))}; "
                    f"3M worst analog return {fmt_pct(parse_float(downside.get('worst_forward_3m')))}."
                ),
            }
        )
    if policy["major_alerts"]:
        actions.append(
            {
                "priority": 4,
                "severity": "alert",
                "title": "Review major alerts",
                "detail": f"{policy['major_alerts']} major alerts are active; confirm the top movers before increasing risk.",
            }
        )
    if policy["quality_score"] is not None:
        actions.append(
            {
                "priority": 5,
                "severity": "data",
                "title": "Data confidence",
                "detail": f"Quality score is {fmt_num(policy['quality_score'])}/100 ({policy['quality_grade']}).",
            }
        )
    return actions


def build_summary(
    latest: dict[str, str],
    policy: dict[str, Any],
    best_etf_rows: list[dict[str, str]],
    context: dict[str, dict[str, str]],
) -> dict[str, Any]:
    allocation = allocation_from_latest(latest)
    best = best_etf_rows[0] if best_etf_rows else {}
    baseline = context.get("baseline", {})
    downside = context.get("downside_stress", {})
    closest = context.get("closest_stress", {})
    summary = {
        "generated_at": datetime.now().replace(microsecond=0).isoformat(),
        "report_date": latest.get("report_date", ""),
        "current_regime": latest.get("current_regime", ""),
        "supporting_regime": latest.get("supporting_regime", ""),
        "action_level": policy["action_level"],
        "risk_posture": policy["risk_posture"],
        "decision_confidence": policy["decision_confidence"],
        "quality_score": policy["quality_score"],
        "quality_grade": policy["quality_grade"],
        "major_alerts": policy["major_alerts"],
        "watch_alerts": policy["watch_alerts"],
        "regime_changed": policy["regime_changed"],
        "recommended_variant": best.get("variant", ""),
        "recommended_variant_title": best.get("variant_title", ""),
        "recommended_xirr": parse_float(best.get("xirr")),
        "recommended_excess_xirr": parse_float(best.get("excess_xirr")),
        "baseline_analog_12m_avg": parse_float(baseline.get("avg_forward_12m")),
        "closest_stress_scenario": closest.get("title", ""),
        "closest_stress_distance": parse_float(closest.get("nearest_distance")),
        "downside_stress_scenario": downside.get("title", ""),
        "downside_stress_3m_worst": parse_float(downside.get("worst_forward_3m")),
    }
    for asset, _label in ALLOCATION_FIELDS:
        summary[f"{asset}_amount"] = allocation[asset]
    return summary


def csv_value(value: Any) -> Any:
    if isinstance(value, float):
        return "" if math.isnan(value) else round(value, 8)
    if value is None:
        return ""
    return value


def render_markdown(summary: dict[str, Any], actions: list[dict[str, Any]], top_etfs: list[dict[str, str]], alerts: list[dict[str, str]]) -> str:
    lines = [
        "# Decision Engine",
        "",
        f"Generated at: {summary['generated_at']}",
        f"Report date: {summary['report_date']}",
        "",
        "## Decision",
        f"- Action level: {summary['action_level']}",
        f"- Risk posture: {summary['risk_posture']}",
        f"- Confidence: {summary['decision_confidence']} ({summary['quality_score']} / 100, {summary['quality_grade']})",
        f"- Regime: {summary['current_regime']} / {summary['supporting_regime']}",
        f"- Allocation: cash {summary['cash_amount']}m, gold {summary['gold_amount']}m, silver/resources {summary['silver_amount']}m, equity/ETF {summary['equity_amount']}m",
        "",
        "## Action Queue",
    ]
    for action in actions:
        lines.append(f"- P{action['priority']} {action['title']}: {action['detail']}")
    lines.extend(["", "## ETF Candidates", "| Variant | XIRR | Gap |", "|---|---:|---:|"])
    for row in top_etfs:
        lines.append(
            f"| {row.get('variant_title', row.get('variant', ''))} | {fmt_pct(parse_float(row.get('xirr')))} | {fmt_pct(parse_float(row.get('excess_xirr')))} |"
        )
    lines.extend(["", "## Top Alerts"])
    for row in alerts:
        lines.append(f"- {row.get('severity', '')}: {row.get('item_label', '')} / {row.get('detail', '')}")
    return "\n".join(lines) + "\n"


def render_html(
    summary: dict[str, Any],
    actions: list[dict[str, Any]],
    top_etfs: list[dict[str, str]],
    alerts: list[dict[str, str]],
) -> str:
    cards = [
        ("Action", summary["action_level"]),
        ("Posture", summary["risk_posture"]),
        ("Confidence", f"{summary['decision_confidence']} / {fmt_num(summary['quality_score'])}"),
        ("Regime", summary["current_regime"]),
    ]
    card_html = "".join(
        f"<div class=\"card\"><div class=\"label\">{escape(label)}</div><div class=\"value\">{escape(str(value))}</div></div>"
        for label, value in cards
    )
    action_html = "".join(
        "<tr>"
        f"<td>{action['priority']}</td>"
        f"<td>{escape(str(action['severity']))}</td>"
        f"<td><strong>{escape(str(action['title']))}</strong><div class=\"subtle\">{escape(str(action['detail']))}</div></td>"
        "</tr>"
        for action in actions
    )
    etf_html = "".join(
        "<tr>"
        f"<td>{escape(row.get('variant_title', row.get('variant', '')))}</td>"
        f"<td>{escape(row.get('cash_symbol', ''))} / {escape(row.get('gold_symbol', ''))} / {escape(row.get('silver_symbol', ''))} / {escape(row.get('equity_symbol', ''))}</td>"
        f"<td>{fmt_pct(parse_float(row.get('xirr')))}</td>"
        f"<td>{fmt_pct(parse_float(row.get('excess_xirr')))}</td>"
        "</tr>"
        for row in top_etfs
    )
    alert_html = "".join(
        "<tr>"
        f"<td>{escape(row.get('severity', ''))}</td>"
        f"<td>{escape(row.get('item_label', ''))}</td>"
        f"<td>{escape(row.get('detail', ''))}</td>"
        "</tr>"
        for row in alerts
    )
    allocation = " / ".join(
        f"{label} {summary[f'{asset}_amount']}m"
        for asset, label in ALLOCATION_FIELDS
    )
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Decision Engine</title>
  <style>
    :root {{
      --bg: #f7f8fa;
      --surface: #ffffff;
      --ink: #1f2933;
      --muted: #66717f;
      --line: #d9dee5;
      --accent: #2563eb;
      --shadow: 0 8px 22px rgba(28, 39, 49, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 22px 20px 36px; }}
    a {{ color: var(--accent); text-decoration: none; }}
    .topbar {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 16px;
    }}
    h1 {{ margin: 0; font-size: 28px; line-height: 1.12; }}
    h2 {{ margin: 0; padding: 14px 16px; border-bottom: 1px solid var(--line); font-size: 16px; }}
    .cards {{ display: grid; grid-template-columns: repeat(4, minmax(150px, 1fr)); gap: 10px; margin-bottom: 16px; }}
    .card, .panel, .note {{ background: var(--surface); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); }}
    .card {{ padding: 13px 14px; }}
    .label, .subtle {{ color: var(--muted); font-size: 12px; line-height: 1.45; }}
    .value {{ font-weight: 760; font-size: 20px; line-height: 1.2; margin-top: 4px; }}
    .panel {{ margin-bottom: 16px; overflow: hidden; }}
    .panel-body {{ padding: 0; overflow-x: auto; }}
    .note {{ padding: 12px 14px; color: var(--muted); font-size: 13px; margin-bottom: 16px; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 780px; }}
    th, td {{ padding: 11px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ color: var(--muted); background: #fbfcfe; font-weight: 700; }}
    @media (max-width: 760px) {{
      .wrap {{ padding: 18px 12px 28px; }}
      .topbar {{ display: block; }}
      .cards {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div>
      <a href="sector_dashboard.html">Back to sector dashboard</a>
      <h1>Decision Engine</h1>
      <div class="subtle">Generated {escape(str(summary['generated_at']))} / Report {escape(str(summary['report_date']))}</div>
    </div>
    <div class="subtle"><a href="decision_engine_latest.md">Markdown</a> / <a href="rebalance_orders.html">Rebalance orders</a> / <a href="scenario_etf_backtests.html">Scenario ETF backtests</a> / <a href="scenario_matrix.html">Scenario matrix</a> / <a href="daily_brief_latest.md">Daily brief</a></div>
  </div>
  <section class="cards">{card_html}</section>
  <div class="note">Baseline allocation: {escape(allocation)}. Downside stress: {escape(str(summary.get('downside_stress_scenario', 'NA')))} with 3M worst analog return {fmt_pct(summary.get('downside_stress_3m_worst'))}.</div>
  <section class="panel">
    <h2>Action Queue</h2>
    <div class="panel-body"><table><thead><tr><th>Priority</th><th>Type</th><th>Action</th></tr></thead><tbody>{action_html}</tbody></table></div>
  </section>
  <section class="panel">
    <h2>ETF Implementation Candidates</h2>
    <div class="panel-body"><table><thead><tr><th>Variant</th><th>ETF symbols</th><th>XIRR</th><th>Gap vs dynamic</th></tr></thead><tbody>{etf_html}</tbody></table></div>
  </section>
  <section class="panel">
    <h2>Top Alerts</h2>
    <div class="panel-body"><table><thead><tr><th>Severity</th><th>Item</th><th>Detail</th></tr></thead><tbody>{alert_html}</tbody></table></div>
  </section>
</div>
</body>
</html>
"""


def summary_fieldnames() -> list[str]:
    fields = [
        "generated_at",
        "report_date",
        "current_regime",
        "supporting_regime",
        "action_level",
        "risk_posture",
        "decision_confidence",
        "quality_score",
        "quality_grade",
        "major_alerts",
        "watch_alerts",
        "regime_changed",
        "recommended_variant",
        "recommended_variant_title",
        "recommended_xirr",
        "recommended_excess_xirr",
        "baseline_analog_12m_avg",
        "closest_stress_scenario",
        "closest_stress_distance",
        "downside_stress_scenario",
        "downside_stress_3m_worst",
    ]
    fields.extend([f"{asset}_amount" for asset, _label in ALLOCATION_FIELDS])
    return fields


def action_fieldnames() -> list[str]:
    return ["priority", "severity", "title", "detail"]


def write_decision_engine(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    risk_rows = read_csv(Path(args.risk_history))
    latest = latest_row(risk_rows)
    alert_rows = read_csv(Path(args.alerts))
    quality = quality_overall(read_csv(Path(args.quality)))
    scenario_rows = read_csv(Path(args.scenario_matrix))
    etf_rows = read_csv(Path(args.scenario_etf))

    policy = policy_from_inputs(latest, alert_rows, quality)
    top_etfs = select_best_etf_rows(etf_rows)
    context = scenario_context(scenario_rows)
    actions = build_actions(latest, policy, top_etfs, context, alert_rows)
    summary = build_summary(latest, policy, top_etfs, context)
    top = top_alerts(alert_rows)

    html_path = Path(args.html)
    md_path = Path(args.markdown)
    summary_csv = Path(args.summary_csv)
    actions_csv = Path(args.actions_csv)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(render_html(summary, actions, top_etfs, top), encoding="utf-8")
    md_path.write_text(render_markdown(summary, actions, top_etfs, top), encoding="utf-8")
    write_csv(summary_csv, [{key: csv_value(summary.get(key)) for key in summary_fieldnames()}], summary_fieldnames())
    write_csv(actions_csv, [{key: csv_value(action.get(key)) for key in action_fieldnames()} for action in actions], action_fieldnames())
    return html_path, md_path, summary_csv, actions_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate macro decision engine outputs.")
    parser.add_argument("--risk-history", default=str(DEFAULT_RISK_HISTORY))
    parser.add_argument("--alerts", default=str(DEFAULT_ALERTS))
    parser.add_argument("--quality", default=str(DEFAULT_QUALITY))
    parser.add_argument("--scenario-matrix", default=str(DEFAULT_SCENARIO_MATRIX))
    parser.add_argument("--scenario-etf", default=str(DEFAULT_SCENARIO_ETF))
    parser.add_argument("--html", default=str(DEFAULT_HTML))
    parser.add_argument("--markdown", default=str(DEFAULT_MD))
    parser.add_argument("--summary-csv", default=str(DEFAULT_SUMMARY_CSV))
    parser.add_argument("--actions-csv", default=str(DEFAULT_ACTIONS_CSV))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    html_path, md_path, summary_csv, actions_csv = write_decision_engine(args)
    print(f"Generated decision engine HTML: {html_path}")
    print(f"Generated decision engine markdown: {md_path}")
    print(f"Generated decision engine summary: {summary_csv}")
    print(f"Generated decision engine actions: {actions_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
