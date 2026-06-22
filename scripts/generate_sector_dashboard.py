#!/usr/bin/env python3
"""Generate a static HTML dashboard for browsing indicators by sector."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any


DEFAULT_SNAPSHOT = Path("data/processed/macro/latest_snapshot.csv")
DEFAULT_DASHBOARD = Path("data/processed/macro/requested_indicators_latest.csv")
DEFAULT_FETCH_STATUS = Path("data/processed/macro/fetch_status.csv")
DEFAULT_RISK_HISTORY = Path("data/processed/macro/risk_score_history.csv")
DEFAULT_MONTHLY_SUMMARY = Path("data/processed/macro/monthly_dashboard/supplemental_score_summary.csv")
DEFAULT_OBSERVATIONS = Path("data/processed/macro/observations_long.csv")
DEFAULT_ALERTS = Path("data/processed/macro/change_alerts_latest.csv")
DEFAULT_REPORT = Path("reports/sector_dashboard.html")
DEFAULT_DETAIL_DIR = Path("reports/indicators")
DEFAULT_ASSET_ROOT = Path("reports/assets")
DETAIL_SERIES_LIMIT = 60

CATEGORY_LABELS = {
    "market": "Market",
    "market_derived": "Relative Strength",
    "market_stress": "Market Stress",
    "rates": "Rates",
    "rates_global": "Global Rates",
    "inflation": "Inflation",
    "liquidity": "Liquidity",
    "credit": "Credit",
    "fx": "FX",
    "employment": "Employment",
    "commodities": "Commodities",
    "climate": "Climate",
}

CATEGORY_ORDER = [
    "market",
    "market_derived",
    "market_stress",
    "rates_global",
    "rates",
    "fx",
    "credit",
    "liquidity",
    "inflation",
    "employment",
    "commodities",
    "climate",
]

CHART_SPECS = [
    {
        "title": "Global equity indexes",
        "category": "market",
        "filename": "global_market_indices.png",
        "scope": "macro",
    },
    {
        "title": "Market confirmation",
        "category": "market_derived",
        "filename": "market_confirmation.png",
        "scope": "macro",
    },
    {
        "title": "Global 10Y yields",
        "category": "rates_global",
        "filename": "global_10y_yields.png",
        "scope": "macro",
    },
    {
        "title": "Policy rates",
        "category": "rates",
        "filename": "policy_rates.png",
        "scope": "macro",
    },
    {
        "title": "FX trend",
        "category": "fx",
        "filename": "fx_trend.png",
        "scope": "macro",
    },
    {
        "title": "Credit stress",
        "category": "credit",
        "filename": "credit_stress.png",
        "scope": "macro",
    },
    {
        "title": "Liquidity trend",
        "category": "liquidity",
        "filename": "liquidity_trend.png",
        "scope": "macro",
    },
    {
        "title": "Inflation YoY",
        "category": "inflation",
        "filename": "inflation_yoy.png",
        "scope": "macro",
    },
    {
        "title": "Commodity shock",
        "category": "commodities",
        "filename": "commodity_trend.png",
        "scope": "macro",
    },
    {
        "title": "Risk scores",
        "category": "all",
        "filename": "risk_scores.png",
        "scope": "macro",
    },
    {
        "title": "Monthly supplemental scores",
        "category": "all",
        "filename": "supplemental_scores_over_time.png",
        "scope": "monthly",
    },
]


@dataclass(frozen=True)
class DashboardData:
    generated_at: str
    indicators: list[dict[str, Any]]
    categories: list[dict[str, Any]]
    score_cards: list[dict[str, Any]]
    fetch_health: dict[str, Any]
    chart_assets: list[dict[str, str]]
    alert_summary: dict[str, Any]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip().replace(",", "")
    if text in {"", ".", "NA", "N/A", "null"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def format_number(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "NA"
    if 0 < abs(value) < 0.01:
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 100:
        return f"{value:,.1f}"
    text = f"{value:,.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def format_percent(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:+.1f}%"


def normalize_category(category: str) -> str:
    return category.strip() or "other"


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " ").title())


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned.strip("._") or "indicator"


def alert_weight(severity: str) -> int:
    return {"major": 3, "watch": 2, "info": 1}.get(severity, 0)


def severity_class(severity: str) -> str:
    if severity == "major":
        return "bad"
    if severity == "watch":
        return "warn"
    return "info"


def group_alerts(alert_rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in alert_rows:
        item_id = row.get("item_id", "")
        if not item_id:
            continue
        grouped.setdefault(item_id, []).append(row)
    return grouped


def build_alert_summary(alert_rows: list[dict[str, str]]) -> dict[str, Any]:
    severity_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    ranked = sorted(
        alert_rows,
        key=lambda row: alert_weight(row.get("severity", "")),
        reverse=True,
    )
    for row in alert_rows:
        severity = row.get("severity", "") or "blank"
        alert_type = row.get("alert_type", "") or "blank"
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        type_counts[alert_type] = type_counts.get(alert_type, 0) + 1
    return {
        "total": len(alert_rows),
        "severityCounts": severity_counts,
        "typeCounts": type_counts,
        "top": [
            {
                "type": row.get("alert_type", ""),
                "severity": row.get("severity", ""),
                "label": row.get("item_label", "") or row.get("item_id", ""),
                "detail": row.get("detail", ""),
                "delta": row.get("delta", ""),
                "change3m": row.get("pct_change_3m", ""),
            }
            for row in ranked[:6]
        ],
    }


def merge_indicator_rows(snapshot_rows: list[dict[str, str]], dashboard_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    labels = {
        row.get("indicator_id", ""): row.get("field_ko", "")
        for row in dashboard_rows
        if row.get("indicator_id")
    }
    status_by_id = {
        row.get("indicator_id", ""): row.get("status", "")
        for row in dashboard_rows
        if row.get("indicator_id")
    }

    indicators: list[dict[str, Any]] = []
    for row in snapshot_rows:
        indicator_id = row.get("indicator_id", "")
        if not indicator_id:
            continue
        latest_value = parse_float(row.get("latest_value"))
        pct_3m = parse_float(row.get("pct_change_3m"))
        pct_12m = parse_float(row.get("pct_change_12m"))
        category = normalize_category(row.get("category", ""))
        indicators.append(
            {
                "id": indicator_id,
                "label": labels.get(indicator_id) or row.get("name_ko") or indicator_id,
                "category": category,
                "categoryLabel": category_label(category),
                "country": row.get("country", ""),
                "latestDate": row.get("latest_date", ""),
                "latestValue": latest_value,
                "latestDisplay": format_number(latest_value),
                "unit": row.get("unit", ""),
                "ageDays": parse_float(row.get("age_days")),
                "freshness": row.get("freshness_status", "") or status_by_id.get(indicator_id, ""),
                "change3m": pct_3m,
                "change3mDisplay": format_percent(pct_3m),
                "change12m": pct_12m,
                "change12mDisplay": format_percent(pct_12m),
                "source": row.get("source", ""),
                "series": row.get("source_series_id", ""),
                "url": row.get("source_url", ""),
                "notes": row.get("notes", ""),
            }
        )
    indicators.sort(key=lambda item: (CATEGORY_ORDER.index(item["category"]) if item["category"] in CATEGORY_ORDER else 99, item["label"]))
    return indicators


def enrich_indicators_with_links_and_alerts(
    indicators: list[dict[str, Any]],
    report_path: Path,
    detail_dir: Path,
    alerts_by_id: dict[str, list[dict[str, str]]],
) -> list[dict[str, Any]]:
    base_dir = report_path.parent
    enriched: list[dict[str, Any]] = []
    for item in indicators:
        detail_path = detail_dir / f"{safe_filename(item['id'])}.html"
        item_alerts = alerts_by_id.get(item["id"], [])
        top_alert = max(item_alerts, key=lambda row: alert_weight(row.get("severity", "")), default={})
        enriched.append(
            {
                **item,
                "detailPath": relative_path(base_dir, detail_path),
                "alertCount": len(item_alerts),
                "alertSeverity": top_alert.get("severity", ""),
                "alertType": top_alert.get("alert_type", ""),
                "alertDetail": top_alert.get("detail", ""),
            }
        )
    return enriched


def build_categories(indicators: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    stale: dict[str, int] = {}
    for item in indicators:
        category = item["category"]
        counts[category] = counts.get(category, 0) + 1
        if item["freshness"] not in {"ok", ""}:
            stale[category] = stale.get(category, 0) + 1
    categories = sorted(
        counts,
        key=lambda key: CATEGORY_ORDER.index(key) if key in CATEGORY_ORDER else 99,
    )
    return [
        {
            "id": category,
            "label": category_label(category),
            "count": counts[category],
            "stale": stale.get(category, 0),
        }
        for category in categories
    ]


def latest_risk_row(path: Path) -> dict[str, str]:
    rows = read_csv(path)
    return rows[-1] if rows else {}


def build_score_cards(risk_history: Path, supplemental_summary: Path) -> list[dict[str, Any]]:
    row = latest_risk_row(risk_history)
    cards: list[dict[str, Any]] = []
    mapping = [
        ("inflation_risk", "Inflation"),
        ("liquidity_bubble_risk", "Liquidity"),
        ("credit_stress_risk", "Credit"),
        ("fx_risk", "FX"),
        ("climate_supply_shock_risk", "Climate"),
        ("growth_slowdown_risk", "Growth"),
        ("market_stress_risk", "Market Stress"),
        ("global_rate_divergence_risk", "Rate Divergence"),
    ]
    for key, label in mapping:
        value = parse_float(row.get(key))
        cards.append(
            {
                "label": label,
                "value": value,
                "display": format_number(value, 1),
                "kind": "supplemental" if key in {"market_stress_risk", "global_rate_divergence_risk"} else "core",
            }
        )

    supplemental = read_csv(supplemental_summary)
    for item in supplemental:
        name = item.get("confirmation_signal", "")
        for card in cards:
            if card["label"] == name:
                card["avg"] = item.get("long_run_avg", "")
                card["change12m"] = item.get("change_12m", "")
    return cards


def build_fetch_health(path: Path) -> dict[str, Any]:
    rows = read_csv(path)
    counts: dict[str, int] = {}
    for row in rows:
        status = row.get("status") or "blank"
        counts[status] = counts.get(status, 0) + 1
    problems = [
        {
            "indicator": row.get("indicator_id", ""),
            "source": row.get("source_type", ""),
            "status": row.get("status", ""),
            "message": row.get("message", ""),
        }
        for row in rows
        if row.get("status") not in {"", "ok"}
    ][:12]
    return {"total": len(rows), "counts": counts, "problems": problems}


def latest_macro_asset_dir(asset_root: Path, risk_history: Path) -> Path | None:
    latest_report_date = latest_risk_row(risk_history).get("report_date", "")
    if latest_report_date:
        candidate = asset_root / f"macro_regime_{latest_report_date}"
        if candidate.exists():
            return candidate
    candidates = [path for path in asset_root.glob("macro_regime_*") if path.is_dir()]
    return sorted(candidates, key=lambda path: path.name)[-1] if candidates else None


def relative_path(from_dir: Path, target: Path) -> str:
    from_dir = from_dir.resolve()
    target = target.resolve()
    try:
        return target.relative_to(from_dir).as_posix()
    except ValueError:
        return Path(os.path.relpath(target, from_dir)).as_posix()


def discover_chart_assets(report_path: Path, asset_root: Path, risk_history: Path) -> list[dict[str, str]]:
    base_dir = report_path.parent
    macro_dir = latest_macro_asset_dir(asset_root, risk_history)
    monthly_dir = asset_root / "monthly_dashboard"
    scope_dirs = {"macro": macro_dir, "monthly": monthly_dir}
    assets: list[dict[str, str]] = []
    for spec in CHART_SPECS:
        directory = scope_dirs.get(spec["scope"])
        if directory is None:
            continue
        target = directory / spec["filename"]
        if not target.exists():
            continue
        assets.append(
            {
                "title": spec["title"],
                "category": spec["category"],
                "path": relative_path(base_dir, target),
            }
        )
    return assets


def group_recent_observations(observation_rows: list[dict[str, str]], limit: int = DETAIL_SERIES_LIMIT) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in observation_rows:
        indicator_id = row.get("indicator_id", "")
        value = parse_float(row.get("value"))
        if not indicator_id or value is None:
            continue
        grouped.setdefault(indicator_id, []).append(
            {
                "date": row.get("date", ""),
                "value": value,
                "display": format_number(value),
            }
        )
    for indicator_id, rows in grouped.items():
        rows.sort(key=lambda item: item["date"])
        grouped[indicator_id] = rows[-limit:]
    return grouped


def detail_alert_rows(alerts: list[dict[str, str]]) -> list[str]:
    if not alerts:
        return ['<div class="empty">No active alert for this indicator.</div>']
    rows = []
    for alert in sorted(alerts, key=lambda row: alert_weight(row.get("severity", "")), reverse=True):
        move = alert.get("delta", "") or alert.get("pct_change_3m", "") or ""
        move_value = parse_float(move)
        move_display = format_number(move_value, 1) if move_value is not None else move
        rows.append(
            "<tr>"
            f"<td><span class=\"pill {severity_class(alert.get('severity', ''))}\">{escape(alert.get('severity', '') or 'info')}</span></td>"
            f"<td>{escape(alert.get('alert_type', ''))}</td>"
            f"<td>{escape(alert.get('detail', ''))}</td>"
            f"<td>{escape(move_display)}</td>"
            "</tr>"
        )
    return [
        "<table>",
        "<thead><tr><th>Severity</th><th>Type</th><th>Detail</th><th>Move</th></tr></thead>",
        "<tbody>",
        *rows,
        "</tbody></table>",
    ]


def detail_observation_rows(series: list[dict[str, Any]]) -> list[str]:
    if not series:
        return ['<div class="empty">No observation history available.</div>']
    rows = [
        f"<tr><td>{escape(item['date'])}</td><td>{escape(item['display'])}</td></tr>"
        for item in reversed(series[-24:])
    ]
    return [
        "<table>",
        "<thead><tr><th>Date</th><th>Value</th></tr></thead>",
        "<tbody>",
        *rows,
        "</tbody></table>",
    ]


def render_detail_page(
    indicator: dict[str, Any],
    series: list[dict[str, Any]],
    alerts: list[dict[str, str]],
    dashboard_path: Path,
    detail_path: Path,
) -> str:
    dashboard_link = relative_path(detail_path.parent, dashboard_path)
    payload = json.dumps({"series": series}, ensure_ascii=False).replace("</", "<\\/")
    alert_html = "\n".join(detail_alert_rows(alerts))
    history_html = "\n".join(detail_observation_rows(series))
    latest = f"{indicator['latestDisplay']} {indicator.get('unit', '')}".strip()
    source_url = indicator.get("url", "")
    source_link = (
        f"<a href=\"{escape(source_url)}\">{escape(indicator.get('source', ''))}</a>"
        if source_url.startswith("http")
        else escape(indicator.get("source", ""))
    )
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(indicator['label'])} Detail</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --surface: #ffffff;
      --ink: #1f2933;
      --muted: #64707d;
      --line: #d9dee5;
      --accent: #1f6feb;
      --good: #198754;
      --warn: #b7791f;
      --bad: #c2413a;
      --shadow: 0 8px 22px rgba(28, 39, 49, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
      letter-spacing: 0;
    }}
    .wrap {{ max-width: 1120px; margin: 0 auto; padding: 22px 20px 36px; }}
    a {{ color: var(--accent); text-decoration: none; }}
    .back {{ display: inline-flex; margin-bottom: 16px; font-size: 13px; }}
    .head {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 18px;
      align-items: end;
      margin-bottom: 16px;
    }}
    h1 {{ margin: 0; font-size: 28px; line-height: 1.1; }}
    .meta {{ color: var(--muted); font-size: 13px; margin-top: 7px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(130px, 1fr)); gap: 10px; margin-bottom: 16px; }}
    .card, .panel {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    .card {{ padding: 13px 14px; }}
    .label {{ color: var(--muted); font-size: 12px; }}
    .value {{ font-weight: 760; font-size: 22px; margin-top: 4px; line-height: 1.2; }}
    .main {{ display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(280px, 0.8fr); gap: 16px; align-items: start; }}
    .panel h2 {{ margin: 0; padding: 14px 16px; border-bottom: 1px solid var(--line); font-size: 16px; }}
    .panel-body {{ padding: 14px 16px; }}
    canvas {{ display: block; width: 100%; height: 280px; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid var(--line); text-align: left; font-size: 13px; vertical-align: middle; }}
    th {{ color: var(--muted); background: #fbfcfe; }}
    .pill {{
      display: inline-flex;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 700;
      background: #eef3fb;
      color: #475569;
    }}
    .pill.bad {{ background: #ffefef; color: var(--bad); }}
    .pill.warn {{ background: #fff7e6; color: var(--warn); }}
    .empty {{ color: var(--muted); padding: 18px 0; }}
    .notes {{ color: var(--muted); line-height: 1.55; }}
    @media (max-width: 840px) {{
      .head, .main {{ grid-template-columns: 1fr; }}
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 560px) {{
      .wrap {{ padding: 18px 12px 28px; }}
      .grid {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 23px; }}
    }}
  </style>
</head>
<body>
<div class="wrap">
  <a class="back" href="{escape(dashboard_link)}">Back to sector dashboard</a>
  <div class="head">
    <div>
      <h1>{escape(indicator['label'])}</h1>
      <div class="meta">{escape(indicator['id'])} / {escape(indicator.get('categoryLabel', ''))} / {escape(indicator.get('country', ''))}</div>
    </div>
    <div class="meta">Generated {escape(datetime.now().replace(microsecond=0).isoformat())}</div>
  </div>
  <section class="grid">
    <div class="card"><div class="label">Latest</div><div class="value">{escape(latest)}</div></div>
    <div class="card"><div class="label">Latest date</div><div class="value">{escape(indicator.get('latestDate', '') or 'NA')}</div></div>
    <div class="card"><div class="label">3M change</div><div class="value">{escape(indicator.get('change3mDisplay', 'NA'))}</div></div>
    <div class="card"><div class="label">12M change</div><div class="value">{escape(indicator.get('change12mDisplay', 'NA'))}</div></div>
  </section>
  <section class="main">
    <div class="panel">
      <h2>Recent Trend</h2>
      <div class="panel-body"><canvas id="trendCanvas" width="920" height="320"></canvas></div>
    </div>
    <div class="panel">
      <h2>Alerts</h2>
      <div class="panel-body">{alert_html}</div>
    </div>
    <div class="panel">
      <h2>Recent Observations</h2>
      <div class="panel-body">{history_html}</div>
    </div>
    <div class="panel">
      <h2>Source</h2>
      <div class="panel-body notes">
        <div>Freshness: {escape(indicator.get('freshness', '') or 'ok')}</div>
        <div>Source: {source_link}</div>
        <div>Series: {escape(indicator.get('series', ''))}</div>
        <div>Notes: {escape(indicator.get('notes', '') or 'None')}</div>
      </div>
    </div>
  </section>
</div>
<script id="detail-data" type="application/json">{payload}</script>
<script>
const DATA = JSON.parse(document.getElementById('detail-data').textContent);
const canvas = document.getElementById('trendCanvas');
const ctx = canvas.getContext('2d');
const rows = DATA.series || [];
function draw() {{
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!rows.length) {{
    ctx.fillStyle = '#64707d';
    ctx.font = '16px system-ui';
    ctx.fillText('No observation history available.', 24, 54);
    return;
  }}
  const pad = {{ left: 64, right: 22, top: 24, bottom: 56 }};
  const values = rows.map(row => row.value).filter(value => typeof value === 'number');
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max === min ? 1 : max - min;
  const w = canvas.width - pad.left - pad.right;
  const h = canvas.height - pad.top - pad.bottom;
  ctx.strokeStyle = '#d9dee5';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top);
  ctx.lineTo(pad.left, pad.top + h);
  ctx.lineTo(canvas.width - pad.right, pad.top + h);
  ctx.stroke();
  ctx.strokeStyle = '#1f6feb';
  ctx.lineWidth = 2;
  ctx.beginPath();
  rows.forEach((row, index) => {{
    const x = pad.left + (rows.length === 1 ? 0 : index / (rows.length - 1) * w);
    const y = pad.top + h - ((row.value - min) / span * h);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }});
  ctx.stroke();
  const last = rows[rows.length - 1];
  ctx.fillStyle = '#1f2933';
  ctx.font = '12px system-ui';
  ctx.fillText(`${{last.date}} / ${{last.display}}`, pad.left, 18);
  ctx.fillStyle = '#64707d';
  ctx.fillText(String(rows[0].date), pad.left, canvas.height - 18);
  ctx.textAlign = 'right';
  ctx.fillText(String(last.date), canvas.width - pad.right, canvas.height - 18);
}}
draw();
</script>
</body>
</html>
"""


def write_indicator_detail_pages(
    indicators: list[dict[str, Any]],
    observation_rows: list[dict[str, str]],
    alert_rows: list[dict[str, str]],
    dashboard_path: Path,
    detail_dir: Path,
) -> int:
    detail_dir.mkdir(parents=True, exist_ok=True)
    series_by_id = group_recent_observations(observation_rows)
    alerts_by_id = group_alerts(alert_rows)
    count = 0
    for indicator in indicators:
        detail_path = detail_dir / f"{safe_filename(indicator['id'])}.html"
        detail_path.write_text(
            render_detail_page(
                indicator,
                series_by_id.get(indicator["id"], []),
                alerts_by_id.get(indicator["id"], []),
                dashboard_path,
                detail_path,
            ),
            encoding="utf-8",
        )
        count += 1
    return count


def build_dashboard_data(args: argparse.Namespace) -> DashboardData:
    snapshot_rows = read_csv(Path(args.snapshot))
    dashboard_rows = read_csv(Path(args.dashboard))
    alert_rows = read_csv(Path(args.alerts))
    indicators = merge_indicator_rows(snapshot_rows, dashboard_rows)
    report_path = Path(args.output)
    detail_dir = Path(args.detail_dir)
    alerts_by_id = group_alerts(alert_rows)
    indicators = enrich_indicators_with_links_and_alerts(indicators, report_path, detail_dir, alerts_by_id)
    return DashboardData(
        generated_at=datetime.now().replace(microsecond=0).isoformat(),
        indicators=indicators,
        categories=build_categories(indicators),
        score_cards=build_score_cards(Path(args.risk_history), Path(args.supplemental_summary)),
        fetch_health=build_fetch_health(Path(args.fetch_status)),
        chart_assets=discover_chart_assets(report_path, Path(args.asset_root), Path(args.risk_history)),
        alert_summary=build_alert_summary(alert_rows),
    )


def render_html(data: DashboardData) -> str:
    payload = json.dumps(data.__dict__, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Macro Sector Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --surface: #ffffff;
      --ink: #1f2933;
      --muted: #64707d;
      --line: #d9dee5;
      --accent: #1f6feb;
      --accent-soft: #e6f0ff;
      --good: #198754;
      --warn: #b7791f;
      --bad: #c2413a;
      --shadow: 0 8px 22px rgba(28, 39, 49, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
      letter-spacing: 0;
    }}
    .app {{
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(230px, 290px) 1fr;
    }}
    aside {{
      background: #111827;
      color: white;
      padding: 22px 18px;
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
    }}
    .brand {{
      font-size: 20px;
      font-weight: 760;
      line-height: 1.2;
      margin-bottom: 6px;
    }}
    .stamp {{
      color: #aeb8c4;
      font-size: 12px;
      margin-bottom: 20px;
    }}
    .nav {{
      display: grid;
      gap: 6px;
    }}
    .nav button {{
      appearance: none;
      border: 1px solid rgba(255,255,255,0.08);
      background: transparent;
      color: #dbe4ef;
      min-height: 38px;
      width: 100%;
      padding: 8px 10px;
      border-radius: 7px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      cursor: pointer;
      font: inherit;
      text-align: left;
    }}
    .nav button.active {{
      background: #2563eb;
      border-color: #2563eb;
      color: white;
    }}
    .count {{
      min-width: 26px;
      text-align: center;
      border-radius: 999px;
      background: rgba(255,255,255,0.13);
      padding: 2px 7px;
      font-size: 12px;
    }}
    main {{
      min-width: 0;
      padding: 20px 24px 32px;
    }}
    .topbar {{
      display: grid;
      grid-template-columns: minmax(260px, 1fr) auto;
      gap: 14px;
      align-items: center;
      margin-bottom: 16px;
    }}
    h1 {{
      margin: 0;
      font-size: 24px;
      line-height: 1.15;
    }}
    .controls {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    input, select {{
      border: 1px solid var(--line);
      background: white;
      color: var(--ink);
      border-radius: 7px;
      min-height: 38px;
      padding: 8px 10px;
      font: inherit;
    }}
    input {{ width: min(340px, 100%); }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(4, minmax(130px, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 13px 14px;
      box-shadow: var(--shadow);
    }}
    .card .label {{
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .card .value {{
      font-size: 23px;
      line-height: 1.2;
      font-weight: 760;
      margin-top: 5px;
    }}
    .card.supplemental {{
      border-left: 4px solid #264653;
    }}
    .alert-strip {{
      display: grid;
      grid-template-columns: minmax(180px, 0.7fr) minmax(0, 1.3fr);
      gap: 10px;
      margin-bottom: 16px;
    }}
    .alert-panel {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px 14px;
      box-shadow: var(--shadow);
    }}
    .alert-panel strong {{
      display: block;
      font-size: 14px;
      margin-bottom: 7px;
    }}
    .alert-list {{
      display: grid;
      gap: 6px;
    }}
    .mini-alert {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
      min-width: 0;
    }}
    .mini-alert span:first-child {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 720;
      background: #eef3fb;
      color: #475569;
      white-space: nowrap;
    }}
    .badge.bad {{ background: #ffefef; color: var(--bad); }}
    .badge.warn {{ background: #fff7e6; color: var(--warn); }}
    .detail-link {{
      color: var(--ink);
      text-decoration: none;
    }}
    a {{
      color: var(--accent);
    }}
    .detail-link:hover {{
      color: var(--accent);
      text-decoration: underline;
    }}
    .content-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.5fr) minmax(280px, 0.8fr);
      gap: 16px;
      align-items: start;
    }}
    .panel {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .panel-head {{
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
    }}
    .panel-title {{
      font-weight: 720;
    }}
    .subtle {{
      color: var(--muted);
      font-size: 12px;
    }}
    .chart-box {{
      padding: 12px 16px 16px;
    }}
    canvas {{
      width: 100%;
      height: 260px;
      display: block;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: middle;
      font-size: 13px;
    }}
    th {{
      color: var(--muted);
      font-weight: 680;
      background: #fbfcfe;
    }}
    tbody tr:hover {{
      background: #fbfcfe;
    }}
    td strong {{
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .status {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      background: #edf7f1;
      color: var(--good);
      font-weight: 650;
    }}
    .status.warn {{
      background: #fff7e6;
      color: var(--warn);
    }}
    .status.bad {{
      background: #ffefef;
      color: var(--bad);
    }}
    .delta.positive {{ color: #0f7a45; font-weight: 680; }}
    .delta.negative {{ color: #b42318; font-weight: 680; }}
    .gallery {{
      display: grid;
      gap: 12px;
      padding: 12px;
    }}
    .gallery figure {{
      margin: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: #fff;
    }}
    .gallery img {{
      display: block;
      width: 100%;
      height: auto;
      background: #fff;
    }}
    figcaption {{
      padding: 8px 10px;
      color: var(--muted);
      font-size: 12px;
      border-top: 1px solid var(--line);
    }}
    .empty {{
      padding: 30px;
      color: var(--muted);
      text-align: center;
    }}
    @media (max-width: 980px) {{
      .app {{ grid-template-columns: 1fr; }}
      aside {{ position: static; height: auto; }}
      .nav {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .topbar {{ grid-template-columns: 1fr; }}
      .controls {{ justify-content: flex-start; }}
      .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .alert-strip {{ grid-template-columns: 1fr; }}
      .content-grid {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 620px) {{
      main {{ padding: 16px 12px 24px; }}
      .nav {{ grid-template-columns: 1fr; }}
      .cards {{ grid-template-columns: 1fr; }}
      th:nth-child(3), td:nth-child(3), th:nth-child(5), td:nth-child(5) {{ display: none; }}
      th, td {{ padding: 9px 8px; }}
    }}
  </style>
</head>
<body>
<div class="app">
  <aside>
    <div class="brand">Macro Sector Dashboard</div>
    <div class="stamp">Generated {escape(data.generated_at)}</div>
    <nav class="nav" id="categoryNav"></nav>
  </aside>
  <main>
    <div class="topbar">
      <div>
        <h1 id="pageTitle">All Sectors</h1>
        <div class="subtle" id="pageMeta"></div>
      </div>
      <div class="controls">
        <input id="searchInput" type="search" placeholder="Search indicator, source, country">
        <select id="sortSelect" aria-label="Sort indicators">
          <option value="label">Name</option>
          <option value="change3m">3M change</option>
          <option value="change12m">12M change</option>
          <option value="alert">Alert severity</option>
          <option value="freshness">Freshness</option>
        </select>
      </div>
    </div>
    <section class="cards" id="scoreCards"></section>
    <section class="alert-strip">
      <div class="alert-panel">
        <strong>Change Alerts</strong>
        <div class="subtle" id="alertSummary"></div>
        <div class="subtle"><a href="daily_brief_latest.md">Daily brief</a> / <a href="decision_engine.html">Decision engine</a> / <a href="rebalance_orders.html">Rebalance orders</a> / <a href="scenario_simulator.html">Scenario simulator</a> / <a href="scenario_matrix.html">Scenario matrix</a> / <a href="scenario_etf_backtests.html">Scenario ETF backtests</a> / <a href="alerts_latest.md">Alerts report</a> / <a href="risk_attribution_latest.md">Risk attribution</a> / <a href="data_quality_latest.md">Data quality</a></div>
      </div>
      <div class="alert-panel">
        <strong>Top Alerts</strong>
        <div class="alert-list" id="topAlerts"></div>
      </div>
    </section>
    <section class="content-grid">
      <div class="panel">
        <div class="panel-head">
          <div>
            <div class="panel-title" id="tableTitle">Indicators</div>
            <div class="subtle" id="tableMeta"></div>
          </div>
          <div class="subtle" id="healthMeta"></div>
        </div>
        <div class="chart-box">
          <canvas id="sectorCanvas" width="960" height="300"></canvas>
        </div>
        <div id="tableWrap"></div>
      </div>
      <div class="panel">
        <div class="panel-head">
          <div>
            <div class="panel-title">Charts</div>
            <div class="subtle">Sector-linked report assets</div>
          </div>
        </div>
        <div class="gallery" id="chartGallery"></div>
      </div>
    </section>
  </main>
</div>
<script id="dashboard-data" type="application/json">{payload}</script>
<script>
const DATA = JSON.parse(document.getElementById('dashboard-data').textContent);
let activeCategory = 'all';

const categoryNav = document.getElementById('categoryNav');
const searchInput = document.getElementById('searchInput');
const sortSelect = document.getElementById('sortSelect');

function numberOrZero(value) {{
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}}

function deltaClass(value) {{
  if (typeof value !== 'number' || !Number.isFinite(value)) return '';
  if (value > 0) return 'positive';
  if (value < 0) return 'negative';
  return '';
}}

function statusClass(status) {{
  if (!status || status === 'ok') return 'status';
  if (status === 'stale') return 'status warn';
  return 'status bad';
}}

function severityWeight(severity) {{
  if (severity === 'major') return 3;
  if (severity === 'watch') return 2;
  if (severity === 'info') return 1;
  return 0;
}}

function severityBadgeClass(severity) {{
  if (severity === 'major') return 'badge bad';
  if (severity === 'watch') return 'badge warn';
  return 'badge';
}}

function renderAlertSummary() {{
  const summary = DATA.alert_summary || {{ total: 0, severityCounts: {{}}, top: [] }};
  const major = summary.severityCounts.major || 0;
  const watch = summary.severityCounts.watch || 0;
  document.getElementById('alertSummary').textContent = `${{summary.total || 0}} total, ${{major}} major, ${{watch}} watch`;
  const top = document.getElementById('topAlerts');
  if (!summary.top || !summary.top.length) {{
    top.innerHTML = '<div class="subtle">No active change alerts.</div>';
    return;
  }}
  top.innerHTML = summary.top.map(alert => `
    <div class="mini-alert">
      <span>${{alert.label}}</span>
      <span class="${{severityBadgeClass(alert.severity)}}">${{alert.severity || 'info'}}</span>
    </div>
  `).join('');
}}

function indicatorMatches(item, query) {{
  if (!query) return true;
  const haystack = [item.label, item.id, item.country, item.source, item.series, item.categoryLabel, item.alertSeverity, item.alertType].join(' ').toLowerCase();
  return haystack.includes(query.toLowerCase());
}}

function filteredIndicators() {{
  const query = searchInput.value.trim();
  const sort = sortSelect.value;
  let rows = DATA.indicators.filter(item => activeCategory === 'all' || item.category === activeCategory);
  rows = rows.filter(item => indicatorMatches(item, query));
  rows.sort((a, b) => {{
    if (sort === 'change3m') return numberOrZero(b.change3m) - numberOrZero(a.change3m);
    if (sort === 'change12m') return numberOrZero(b.change12m) - numberOrZero(a.change12m);
    if (sort === 'alert') return severityWeight(b.alertSeverity) - severityWeight(a.alertSeverity) || numberOrZero(b.change3m) - numberOrZero(a.change3m);
    if (sort === 'freshness') return String(a.freshness).localeCompare(String(b.freshness));
    return String(a.label).localeCompare(String(b.label));
  }});
  return rows;
}}

function renderNav() {{
  const total = DATA.indicators.length;
  const allButton = document.createElement('button');
  allButton.className = activeCategory === 'all' ? 'active' : '';
  allButton.innerHTML = `<span>All sectors</span><span class="count">${{total}}</span>`;
  allButton.addEventListener('click', () => {{ activeCategory = 'all'; render(); }});
  categoryNav.appendChild(allButton);

  DATA.categories.forEach(category => {{
    const button = document.createElement('button');
    button.className = activeCategory === category.id ? 'active' : '';
    button.innerHTML = `<span>${{category.label}}</span><span class="count">${{category.count}}</span>`;
    button.addEventListener('click', () => {{ activeCategory = category.id; render(); }});
    categoryNav.appendChild(button);
  }});
}}

function renderScoreCards() {{
  const wrap = document.getElementById('scoreCards');
  wrap.innerHTML = '';
  DATA.score_cards.forEach(card => {{
    const el = document.createElement('div');
    el.className = `card ${{card.kind === 'supplemental' ? 'supplemental' : ''}}`;
    el.innerHTML = `<div class="label">${{card.label}}</div><div class="value">${{card.display}}</div>`;
    wrap.appendChild(el);
  }});
}}

function renderTable(rows) {{
  const wrap = document.getElementById('tableWrap');
  if (!rows.length) {{
    wrap.innerHTML = '<div class="empty">No indicators match the current filter.</div>';
    return;
  }}
  const html = rows.map(item => `
    <tr>
      <td><strong title="${{item.label}}"><a class="detail-link" href="${{item.detailPath}}">${{item.label}}</a></strong><span class="subtle">${{item.id}}</span></td>
      <td>${{item.latestDisplay}} <span class="subtle">${{item.unit}}</span></td>
      <td>${{item.latestDate}}</td>
      <td class="delta ${{deltaClass(item.change3m)}}">${{item.change3mDisplay}}</td>
      <td class="delta ${{deltaClass(item.change12m)}}">${{item.change12mDisplay}}</td>
      <td>${{item.alertSeverity ? `<span class="${{severityBadgeClass(item.alertSeverity)}}">${{item.alertSeverity}}</span>` : ''}}</td>
      <td><span class="${{statusClass(item.freshness)}}">${{item.freshness || 'ok'}}</span></td>
      <td><span title="${{item.source}}">${{item.source}}</span></td>
    </tr>
  `).join('');
  wrap.innerHTML = `
    <table>
      <thead>
        <tr>
          <th style="width: 26%">Indicator</th>
          <th style="width: 13%">Latest</th>
          <th style="width: 12%">Date</th>
          <th style="width: 9%">3M</th>
          <th style="width: 9%">12M</th>
          <th style="width: 9%">Alert</th>
          <th style="width: 9%">Fresh</th>
          <th style="width: 13%">Source</th>
        </tr>
      </thead>
      <tbody>${{html}}</tbody>
    </table>
  `;
}}

function drawBarChart(rows) {{
  const canvas = document.getElementById('sectorCanvas');
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const chartRows = rows.filter(item => typeof item.change3m === 'number').slice(0, 12);
  if (!chartRows.length) {{
    ctx.fillStyle = '#64707d';
    ctx.font = '16px system-ui';
    ctx.fillText('No 3M change data for this sector.', 24, 56);
    return;
  }}
  const pad = {{ left: 54, right: 24, top: 20, bottom: 88 }};
  const width = canvas.width - pad.left - pad.right;
  const height = canvas.height - pad.top - pad.bottom;
  const values = chartRows.map(item => item.change3m);
  const maxAbs = Math.max(5, ...values.map(value => Math.abs(value)));
  const zeroY = pad.top + height / 2;
  ctx.strokeStyle = '#d9dee5';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.left, zeroY);
  ctx.lineTo(canvas.width - pad.right, zeroY);
  ctx.stroke();
  const barW = width / chartRows.length * 0.62;
  chartRows.forEach((item, index) => {{
    const x = pad.left + index * (width / chartRows.length) + (width / chartRows.length - barW) / 2;
    const barH = Math.abs(item.change3m) / maxAbs * (height / 2);
    const y = item.change3m >= 0 ? zeroY - barH : zeroY;
    ctx.fillStyle = item.change3m >= 0 ? '#198754' : '#c2413a';
    ctx.fillRect(x, y, barW, Math.max(2, barH));
    ctx.save();
    ctx.translate(x + barW / 2, canvas.height - 12);
    ctx.rotate(-Math.PI / 5);
    ctx.fillStyle = '#64707d';
    ctx.font = '12px system-ui';
    ctx.textAlign = 'right';
    ctx.fillText(item.label.slice(0, 18), 0, 0);
    ctx.restore();
  }});
  ctx.fillStyle = '#64707d';
  ctx.font = '12px system-ui';
  ctx.fillText(`3M change, max scale +/-${{maxAbs.toFixed(1)}}%`, pad.left, 14);
}}

function renderGallery() {{
  const gallery = document.getElementById('chartGallery');
  const assets = DATA.chart_assets.filter(asset => asset.category === 'all' || activeCategory === 'all' || asset.category === activeCategory);
  if (!assets.length) {{
    gallery.innerHTML = '<div class="empty">No chart asset for this sector.</div>';
    return;
  }}
  gallery.innerHTML = assets.map(asset => `
    <figure>
      <img src="${{asset.path}}" alt="${{asset.title}}">
      <figcaption>${{asset.title}}</figcaption>
    </figure>
  `).join('');
}}

function renderMeta(rows) {{
  const category = activeCategory === 'all'
    ? {{ label: 'All Sectors', count: DATA.indicators.length, stale: DATA.indicators.filter(item => item.freshness && item.freshness !== 'ok').length }}
    : DATA.categories.find(item => item.id === activeCategory);
  document.getElementById('pageTitle').textContent = category ? category.label : 'Sector';
  document.getElementById('pageMeta').textContent = `${{rows.length}} visible indicators`;
  document.getElementById('tableTitle').textContent = `${{category ? category.label : 'Sector'}} indicators`;
  document.getElementById('tableMeta').textContent = `${{rows.length}} rows, sorted by ${{sortSelect.options[sortSelect.selectedIndex].text}}`;
  const health = DATA.fetch_health;
  const ok = health.counts.ok || 0;
  document.getElementById('healthMeta').textContent = `${{ok}}/${{health.total}} sources ok`;
}}

function render() {{
  categoryNav.innerHTML = '';
  renderNav();
  renderScoreCards();
  renderAlertSummary();
  const rows = filteredIndicators();
  renderMeta(rows);
  renderTable(rows);
  drawBarChart(rows);
  renderGallery();
}}

searchInput.addEventListener('input', render);
sortSelect.addEventListener('change', render);
render();
</script>
</body>
</html>
"""


def write_dashboard(args: argparse.Namespace) -> Path:
    data = build_dashboard_data(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_indicator_detail_pages(
        data.indicators,
        read_csv(Path(args.observations)),
        read_csv(Path(args.alerts)),
        output,
        Path(args.detail_dir),
    )
    output.write_text(render_html(data), encoding="utf-8")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a static sector-based macro dashboard.")
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--dashboard", default=str(DEFAULT_DASHBOARD))
    parser.add_argument("--fetch-status", default=str(DEFAULT_FETCH_STATUS))
    parser.add_argument("--risk-history", default=str(DEFAULT_RISK_HISTORY))
    parser.add_argument("--supplemental-summary", default=str(DEFAULT_MONTHLY_SUMMARY))
    parser.add_argument("--observations", default=str(DEFAULT_OBSERVATIONS))
    parser.add_argument("--alerts", default=str(DEFAULT_ALERTS))
    parser.add_argument("--detail-dir", default=str(DEFAULT_DETAIL_DIR))
    parser.add_argument("--asset-root", default=str(DEFAULT_ASSET_ROOT))
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output = write_dashboard(args)
    print(f"Generated sector dashboard: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
