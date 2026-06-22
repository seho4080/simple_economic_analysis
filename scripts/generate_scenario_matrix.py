#!/usr/bin/env python3
"""Generate saved scenario comparisons with historical analog returns."""

from __future__ import annotations

import argparse
import csv
import math
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from html import escape
from pathlib import Path
from statistics import median
from typing import Any

import analyze_macro_regime as regime


DEFAULT_RISK_HISTORY = Path("data/processed/macro/risk_score_history.csv")
DEFAULT_MONTHLY_HISTORY = Path("data/processed/macro/risk_score_history_monthly.csv")
DEFAULT_OBSERVATIONS = Path("data/processed/macro/observations_long.csv")
DEFAULT_SCENARIOS = Path("config/scenario_library.csv")
DEFAULT_REPORT = Path("reports/scenario_matrix.html")
DEFAULT_SUMMARY_CSV = Path("data/processed/macro/scenario_matrix_latest.csv")
DEFAULT_ANALOGS_CSV = Path("data/processed/macro/scenario_analogs_latest.csv")

HORIZONS_MONTHS = [1, 3, 6, 12]
ANALOG_LIMIT = 8
TOTAL_INVESTMENT_MILLION_KRW = 150

RISK_FIELDS = [
    ("inflation_risk", "Inflation Risk", "Inflation"),
    ("liquidity_bubble_risk", "Liquidity Bubble Risk", "Liquidity"),
    ("credit_stress_risk", "Credit Stress Risk", "Credit"),
    ("fx_risk", "FX Risk", "FX"),
    ("climate_supply_shock_risk", "Climate Supply Shock Risk", "Climate"),
    ("growth_slowdown_risk", "Growth Slowdown Risk", "Growth"),
    ("market_stress_risk", "Market Stress Risk", "Market Stress"),
    ("global_rate_divergence_risk", "Global Rate Divergence Risk", "Rate Divergence"),
]

ALLOCATION_FIELDS = [
    ("cash", "Cash/short bonds"),
    ("gold", "Gold"),
    ("silver", "Silver/commodities"),
    ("equity", "Equity/ETF"),
]

ASSET_INDICATORS = {
    "gold": "gold_futures",
    "silver": "silver_futures",
    "equity": "sp500",
}


@dataclass(frozen=True)
class ObservationPoint:
    date: date
    value: float


@dataclass(frozen=True)
class Scenario:
    slug: str
    title: str
    description: str
    scores: dict[str, float]


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


def clamp_score(value: float) -> float:
    return max(0.0, min(10.0, value))


def fmt_num(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "NA"
    text = f"{value:,.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:.1%}"


def fmt_delta(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "NA"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.{digits}f}"


def latest_row(rows: list[dict[str, str]]) -> dict[str, str]:
    return rows[-1] if rows else {}


def scores_from_row(row: dict[str, str]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for field, score_name, _label in RISK_FIELDS:
        scores[score_name] = parse_float(row.get(field)) or 0.0
    return scores


def allocation_from_row(row: dict[str, str]) -> dict[str, int]:
    return {
        "cash": int(parse_float(row.get("cash_amount")) or 0),
        "gold": int(parse_float(row.get("gold_amount")) or 0),
        "silver": int(parse_float(row.get("silver_amount")) or 0),
        "equity": int(parse_float(row.get("equity_amount")) or 0),
    }


def scenario_result(scores: dict[str, float]) -> dict[str, Any]:
    current, supporting, summary = regime.determine_regime(scores)
    allocation = regime.build_allocation(scores)
    return {
        "current_regime": current,
        "supporting_regime": supporting,
        "summary": summary,
        "allocation": allocation,
    }


def default_scenario_rows() -> list[dict[str, str]]:
    return [
        {"slug": "baseline", "title": "Baseline", "description": "Latest measured macro risk scores"},
        {
            "slug": "inflation_fx_shock",
            "title": "Inflation/FX shock",
            "description": "Inflation and USD/KRW pressure re-accelerate",
            "inflation_risk": "7.2",
            "fx_risk": "7.0",
            "climate_supply_shock_risk": "5.8",
        },
        {
            "slug": "credit_shock",
            "title": "Credit shock",
            "description": "Credit stress rises with growth slowdown",
            "liquidity_bubble_risk": "4.0",
            "credit_stress_risk": "7.2",
            "growth_slowdown_risk": "6.4",
        },
        {
            "slug": "stagflation",
            "title": "Stagflation risk",
            "description": "Inflation stays high while growth slows",
            "inflation_risk": "7.0",
            "liquidity_bubble_risk": "4.5",
            "credit_stress_risk": "5.0",
            "fx_risk": "6.3",
            "climate_supply_shock_risk": "6.0",
            "growth_slowdown_risk": "6.6",
            "market_stress_risk": "5.5",
            "global_rate_divergence_risk": "6.0",
        },
        {
            "slug": "liquidity_bubble",
            "title": "Liquidity bubble",
            "description": "Easing liquidity supports risk appetite without credit stress",
            "inflation_risk": "4.8",
            "liquidity_bubble_risk": "8.0",
            "credit_stress_risk": "3.0",
            "fx_risk": "4.2",
            "climate_supply_shock_risk": "3.5",
            "growth_slowdown_risk": "3.8",
            "market_stress_risk": "3.0",
            "global_rate_divergence_risk": "3.5",
        },
        {
            "slug": "goldilocks",
            "title": "Goldilocks",
            "description": "Low inflation and low credit stress with resilient growth",
            "inflation_risk": "3.8",
            "liquidity_bubble_risk": "5.0",
            "credit_stress_risk": "2.0",
            "fx_risk": "3.8",
            "climate_supply_shock_risk": "2.5",
            "growth_slowdown_risk": "3.2",
            "market_stress_risk": "2.0",
            "global_rate_divergence_risk": "3.0",
        },
    ]


def load_scenarios(path: Path, baseline_scores: dict[str, float]) -> list[Scenario]:
    rows = read_csv(path) or default_scenario_rows()
    scenarios: list[Scenario] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, 1):
        slug = (row.get("slug") or f"scenario_{index}").strip()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        scores = dict(baseline_scores)
        for field, score_name, _label in RISK_FIELDS:
            absolute = parse_float(row.get(field))
            delta = parse_float(row.get(f"{field}_delta"))
            if absolute is not None:
                scores[score_name] = clamp_score(absolute)
            elif delta is not None:
                scores[score_name] = clamp_score(scores.get(score_name, 0.0) + delta)
        scenarios.append(
            Scenario(
                slug=slug,
                title=(row.get("title") or slug).strip(),
                description=(row.get("description") or "").strip(),
                scores=scores,
            )
        )
    return scenarios


def parse_observations(path: Path) -> dict[str, list[ObservationPoint]]:
    series: dict[str, list[ObservationPoint]] = {}
    for row in read_csv(path):
        indicator_id = row.get("indicator_id", "")
        value = parse_float(row.get("value"))
        if not indicator_id or value is None:
            continue
        try:
            obs_date = date.fromisoformat(row["date"])
        except (KeyError, ValueError):
            continue
        series.setdefault(indicator_id, []).append(ObservationPoint(obs_date, value))
    for points in series.values():
        points.sort(key=lambda point: point.date)
    return series


def value_on_or_before(points: list[ObservationPoint], target: date) -> ObservationPoint | None:
    candidate: ObservationPoint | None = None
    for point in points:
        if point.date <= target:
            candidate = point
        else:
            break
    return candidate


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def latest_common_observation_date(series: dict[str, list[ObservationPoint]]) -> date | None:
    required = ["usd_krw", *ASSET_INDICATORS.values()]
    dates = [points[-1].date for key in required if (points := series.get(key))]
    return min(dates) if len(dates) == len(required) else None


def asset_forward_return(
    series: dict[str, list[ObservationPoint]],
    indicator_id: str,
    start: date,
    end: date,
) -> float | None:
    asset_points = series.get(indicator_id, [])
    fx_points = series.get("usd_krw", [])
    start_asset = value_on_or_before(asset_points, start)
    end_asset = value_on_or_before(asset_points, end)
    start_fx = value_on_or_before(fx_points, start)
    end_fx = value_on_or_before(fx_points, end)
    if not start_asset or not end_asset or not start_fx or not end_fx:
        return None
    start_value = start_asset.value * start_fx.value
    end_value = end_asset.value * end_fx.value
    if start_value <= 0:
        return None
    return end_value / start_value - 1.0


def cash_forward_return(series: dict[str, list[ObservationPoint]], start: date, end: date) -> float | None:
    rate_point = value_on_or_before(series.get("korea_short_rate_3m", []), start)
    if not rate_point:
        return None
    days = max((end - start).days, 0)
    return (1 + rate_point.value / 100.0) ** (days / 365.0) - 1.0


def portfolio_forward_return(
    allocation: dict[str, int],
    series: dict[str, list[ObservationPoint]],
    start: date,
    months: int,
) -> float | None:
    end = add_months(start, months)
    returns = {
        "cash": cash_forward_return(series, start, end),
        "gold": asset_forward_return(series, ASSET_INDICATORS["gold"], start, end),
        "silver": asset_forward_return(series, ASSET_INDICATORS["silver"], start, end),
        "equity": asset_forward_return(series, ASSET_INDICATORS["equity"], start, end),
    }
    if any(value is None for value in returns.values()):
        return None
    total = sum(allocation.values()) or TOTAL_INVESTMENT_MILLION_KRW
    weighted = sum(allocation[name] * (returns[name] or 0.0) for name in allocation)
    return weighted / total


def distance(scenario_scores: dict[str, float], row_scores: dict[str, float]) -> float:
    total = 0.0
    weights = 0.0
    for _field, score_name, _label in RISK_FIELDS:
        weight = 0.75 if score_name in {"Market Stress Risk", "Global Rate Divergence Risk"} else 1.0
        total += weight * (scenario_scores.get(score_name, 0.0) - row_scores.get(score_name, 0.0)) ** 2
        weights += weight
    return math.sqrt(total / weights) if weights else 0.0


def find_analogs(
    scenario: Scenario,
    monthly_rows: list[dict[str, str]],
    observations: dict[str, list[ObservationPoint]],
    limit: int = ANALOG_LIMIT,
) -> list[dict[str, Any]]:
    latest_common_date = latest_common_observation_date(observations)
    cutoff = add_months(latest_common_date, -max(HORIZONS_MONTHS)) if latest_common_date else None
    candidates = []
    for row in monthly_rows:
        try:
            report_date = date.fromisoformat(row["report_date"])
        except (KeyError, ValueError):
            continue
        if cutoff and report_date > cutoff:
            continue
        row_scores = scores_from_row(row)
        candidates.append((distance(scenario.scores, row_scores), report_date, row, row_scores))
    candidates.sort(key=lambda item: (item[0], item[1]))

    result = scenario_result(scenario.scores)
    allocation = result["allocation"]
    analogs: list[dict[str, Any]] = []
    for rank, (dist, report_date, row, _row_scores) in enumerate(candidates[:limit], 1):
        analog: dict[str, Any] = {
            "scenario_slug": scenario.slug,
            "scenario_title": scenario.title,
            "analog_rank": rank,
            "analog_date": report_date.isoformat(),
            "distance": round(dist, 3),
            "historical_regime": row.get("current_regime", ""),
            "historical_supporting_regime": row.get("supporting_regime", ""),
            "historical_cash": allocation_from_row(row)["cash"],
            "historical_gold": allocation_from_row(row)["gold"],
            "historical_silver": allocation_from_row(row)["silver"],
            "historical_equity": allocation_from_row(row)["equity"],
            "scenario_cash": allocation["cash"],
            "scenario_gold": allocation["gold"],
            "scenario_silver": allocation["silver"],
            "scenario_equity": allocation["equity"],
        }
        for months in HORIZONS_MONTHS:
            analog[f"forward_return_{months}m"] = portfolio_forward_return(
                allocation, observations, report_date, months
            )
        analogs.append(analog)
    return analogs


def summarize_returns(analogs: list[dict[str, Any]], months: int) -> dict[str, Any]:
    key = f"forward_return_{months}m"
    values = [value for row in analogs if (value := row.get(key)) is not None]
    if not values:
        return {
            f"avg_forward_{months}m": None,
            f"median_forward_{months}m": None,
            f"worst_forward_{months}m": None,
            f"best_forward_{months}m": None,
            f"win_rate_{months}m": None,
            f"samples_{months}m": 0,
        }
    return {
        f"avg_forward_{months}m": sum(values) / len(values),
        f"median_forward_{months}m": median(values),
        f"worst_forward_{months}m": min(values),
        f"best_forward_{months}m": max(values),
        f"win_rate_{months}m": sum(1 for value in values if value > 0) / len(values),
        f"samples_{months}m": len(values),
    }


def build_outputs(
    scenarios: list[Scenario],
    baseline_scores: dict[str, float],
    monthly_rows: list[dict[str, str]],
    observations: dict[str, list[ObservationPoint]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    baseline_result = scenario_result(baseline_scores)
    baseline_allocation = baseline_result["allocation"]
    summary_rows: list[dict[str, Any]] = []
    analog_rows: list[dict[str, Any]] = []

    for scenario in scenarios:
        result = scenario_result(scenario.scores)
        allocation = result["allocation"]
        analogs = find_analogs(scenario, monthly_rows, observations)
        analog_rows.extend(analogs)
        row: dict[str, Any] = {
            "scenario_slug": scenario.slug,
            "title": scenario.title,
            "description": scenario.description,
            "current_regime": result["current_regime"],
            "supporting_regime": result["supporting_regime"],
            "nearest_analog_date": analogs[0]["analog_date"] if analogs else "",
            "nearest_distance": analogs[0]["distance"] if analogs else "",
        }
        for field, score_name, _label in RISK_FIELDS:
            row[field] = round(scenario.scores.get(score_name, 0.0), 2)
            row[f"{field}_delta"] = round(
                scenario.scores.get(score_name, 0.0) - baseline_scores.get(score_name, 0.0), 2
            )
        for key, _label in ALLOCATION_FIELDS:
            row[f"{key}_amount"] = allocation[key]
            row[f"{key}_delta"] = allocation[key] - baseline_allocation[key]
        for months in HORIZONS_MONTHS:
            row.update(summarize_returns(analogs, months))
        summary_rows.append(row)
    return summary_rows, analog_rows


def csv_value(value: Any) -> Any:
    if isinstance(value, float):
        return "" if math.isnan(value) else round(value, 6)
    if value is None:
        return ""
    return value


def delta_class(value: float | int | None) -> str:
    if value is None:
        return "neutral"
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def render_html(summary_rows: list[dict[str, Any]], analog_rows: list[dict[str, Any]], generated_at: str) -> str:
    analogs_by_slug: dict[str, list[dict[str, Any]]] = {}
    for row in analog_rows:
        analogs_by_slug.setdefault(row["scenario_slug"], []).append(row)

    rows_html = []
    for row in summary_rows:
        allocation = " / ".join(
            f"{label} {row[f'{key}_amount']}m"
            for key, label in ALLOCATION_FIELDS
        )
        deltas = " / ".join(
            f"{label} <span class=\"{delta_class(row[f'{key}_delta'])}\">{fmt_delta(row[f'{key}_delta'], 0)}m</span>"
            for key, label in ALLOCATION_FIELDS
        )
        returns = " / ".join(
            f"{months}M {fmt_pct(row.get(f'avg_forward_{months}m'))}"
            for months in HORIZONS_MONTHS
        )
        rows_html.append(
            "<tr>"
            f"<td><strong>{escape(str(row['title']))}</strong><div class=\"subtle\">{escape(str(row['description']))}</div></td>"
            f"<td>{escape(str(row['current_regime']))}<div class=\"subtle\">{escape(str(row['supporting_regime']))}</div></td>"
            f"<td>{allocation}</td>"
            f"<td>{deltas}</td>"
            f"<td>{returns}</td>"
            f"<td>{escape(str(row['nearest_analog_date']))}<div class=\"subtle\">distance {escape(str(row['nearest_distance']))}</div></td>"
            "</tr>"
        )

    detail_sections = []
    for row in summary_rows:
        analog_items = []
        for analog in analogs_by_slug.get(row["scenario_slug"], []):
            returns = " / ".join(
                f"{months}M {fmt_pct(analog.get(f'forward_return_{months}m'))}"
                for months in HORIZONS_MONTHS
            )
            analog_items.append(
                "<tr>"
                f"<td>{analog['analog_rank']}</td>"
                f"<td>{escape(str(analog['analog_date']))}</td>"
                f"<td>{escape(str(analog['historical_regime']))}</td>"
                f"<td>{returns}</td>"
                f"<td>{escape(str(analog['distance']))}</td>"
                "</tr>"
            )
        detail_sections.append(
            "<section class=\"panel\">"
            f"<h2>{escape(str(row['title']))}</h2>"
            "<div class=\"panel-body\">"
            "<table><thead><tr><th>Rank</th><th>Analog date</th><th>Historical regime</th><th>Forward proxy return</th><th>Distance</th></tr></thead>"
            f"<tbody>{''.join(analog_items)}</tbody></table>"
            "</div></section>"
        )

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Macro Scenario Matrix</title>
  <style>
    :root {{
      --bg: #f7f8fa;
      --surface: #ffffff;
      --ink: #1f2933;
      --muted: #66717f;
      --line: #d9dee5;
      --accent: #2563eb;
      --positive: #16835f;
      --negative: #c2413a;
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
    .wrap {{ max-width: 1240px; margin: 0 auto; padding: 22px 20px 36px; }}
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
    .subtle {{ color: var(--muted); font-size: 12px; line-height: 1.45; }}
    .panel {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      margin-bottom: 16px;
      overflow: hidden;
    }}
    .panel-body {{ padding: 0; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 920px; }}
    th, td {{ padding: 11px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ color: var(--muted); background: #fbfcfe; font-weight: 700; }}
    .positive {{ color: var(--positive); font-weight: 700; }}
    .negative {{ color: var(--negative); font-weight: 700; }}
    .neutral {{ color: var(--muted); }}
    .note {{
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 16px;
    }}
    @media (max-width: 760px) {{
      .wrap {{ padding: 18px 12px 28px; }}
      .topbar {{ display: block; }}
    }}
  </style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div>
      <a href="sector_dashboard.html">Back to sector dashboard</a>
      <h1>Macro Scenario Matrix</h1>
      <div class="subtle">Generated {escape(generated_at)} / scenarios {len(summary_rows)} / analogs {len(analog_rows)}</div>
    </div>
    <div class="subtle"><a href="decision_engine.html">Decision engine</a> / <a href="scenario_etf_backtests.html">Scenario ETF backtests</a> / <a href="scenario_simulator.html">Scenario simulator</a> / <a href="daily_brief_latest.md">Daily brief</a></div>
  </div>
  <div class="note">Forward proxy returns use historical analog dates, the scenario allocation, S&amp;P 500, gold futures, silver futures, USD/KRW, and Korean short-rate observations. They are analog evidence, not a trade guarantee.</div>
  <section class="panel">
    <h2>Scenario Summary</h2>
    <div class="panel-body">
      <table>
        <thead><tr><th>Scenario</th><th>Regime</th><th>Allocation</th><th>Delta vs baseline</th><th>Avg forward proxy return</th><th>Nearest analog</th></tr></thead>
        <tbody>{''.join(rows_html)}</tbody>
      </table>
    </div>
  </section>
  {''.join(detail_sections)}
</div>
</body>
</html>
"""


def build_fieldnames(summary_rows: list[dict[str, Any]], analog_rows: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    summary_fields = [
        "scenario_slug",
        "title",
        "description",
        "current_regime",
        "supporting_regime",
        "nearest_analog_date",
        "nearest_distance",
    ]
    for field, _score_name, _label in RISK_FIELDS:
        summary_fields.extend([field, f"{field}_delta"])
    for key, _label in ALLOCATION_FIELDS:
        summary_fields.extend([f"{key}_amount", f"{key}_delta"])
    for months in HORIZONS_MONTHS:
        summary_fields.extend(
            [
                f"avg_forward_{months}m",
                f"median_forward_{months}m",
                f"worst_forward_{months}m",
                f"best_forward_{months}m",
                f"win_rate_{months}m",
                f"samples_{months}m",
            ]
        )

    analog_fields = [
        "scenario_slug",
        "scenario_title",
        "analog_rank",
        "analog_date",
        "distance",
        "historical_regime",
        "historical_supporting_regime",
        "historical_cash",
        "historical_gold",
        "historical_silver",
        "historical_equity",
        "scenario_cash",
        "scenario_gold",
        "scenario_silver",
        "scenario_equity",
    ] + [f"forward_return_{months}m" for months in HORIZONS_MONTHS]
    return summary_fields, analog_fields


def write_matrix(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    risk_rows = read_csv(Path(args.risk_history))
    latest = latest_row(risk_rows)
    baseline_scores = scores_from_row(latest)
    scenarios = load_scenarios(Path(args.scenarios), baseline_scores)
    monthly_rows = read_csv(Path(args.monthly_history))
    observations = parse_observations(Path(args.observations))
    summary_rows, analog_rows = build_outputs(scenarios, baseline_scores, monthly_rows, observations)
    summary_fields, analog_fields = build_fieldnames(summary_rows, analog_rows)

    summary_csv = Path(args.summary_csv)
    analogs_csv = Path(args.analogs_csv)
    report = Path(args.report)
    write_csv(summary_csv, [{key: csv_value(row.get(key)) for key in summary_fields} for row in summary_rows], summary_fields)
    write_csv(analogs_csv, [{key: csv_value(row.get(key)) for key in analog_fields} for row in analog_rows], analog_fields)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        render_html(summary_rows, analog_rows, datetime.now().replace(microsecond=0).isoformat()),
        encoding="utf-8",
    )
    return report, summary_csv, analogs_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate saved macro scenario comparison matrix.")
    parser.add_argument("--risk-history", default=str(DEFAULT_RISK_HISTORY))
    parser.add_argument("--monthly-history", default=str(DEFAULT_MONTHLY_HISTORY))
    parser.add_argument("--observations", default=str(DEFAULT_OBSERVATIONS))
    parser.add_argument("--scenarios", default=str(DEFAULT_SCENARIOS))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--summary-csv", default=str(DEFAULT_SUMMARY_CSV))
    parser.add_argument("--analogs-csv", default=str(DEFAULT_ANALOGS_CSV))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report, summary_csv, analogs_csv = write_matrix(args)
    print(f"Generated scenario matrix: {report}")
    print(f"Generated scenario summary: {summary_csv}")
    print(f"Generated scenario analogs: {analogs_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
