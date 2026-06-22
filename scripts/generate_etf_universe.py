#!/usr/bin/env python3
"""Rank an ETF candidate universe against the latest macro decision context."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any


DEFAULT_UNIVERSE = Path("config/etf_universe.csv")
DEFAULT_DECISION = Path("data/processed/macro/decision_engine_latest.csv")
DEFAULT_RISK_HISTORY = Path("data/processed/macro/risk_score_history.csv")
DEFAULT_OUTPUT_CSV = Path("data/processed/portfolio/etf_universe_ranked.csv")
DEFAULT_HTML = Path("reports/etf_universe.html")

SLEEVE_LABELS = {
    "cash": "Cash / Short Bonds",
    "duration": "Duration Bonds",
    "gold": "Gold",
    "silver": "Silver / Resources",
    "equity": "Equity ETFs",
}

SLEEVE_TARGET_FIELD = {
    "cash": "cash_amount",
    "duration": "cash_amount",
    "gold": "gold_amount",
    "silver": "silver_amount",
    "equity": "equity_amount",
}

RISK_FIELDS = {
    "inflation_risk": "Inflation",
    "liquidity_bubble_risk": "Liquidity",
    "credit_stress_risk": "Credit",
    "fx_risk": "FX",
    "climate_supply_shock_risk": "Climate",
    "growth_slowdown_risk": "Growth",
    "market_stress_risk": "Market Stress",
    "global_rate_divergence_risk": "Rate Divergence",
}


@dataclass(frozen=True)
class EtfCandidate:
    sleeve: str
    role: str
    symbol: str
    label: str
    provider: str
    asset_class: str
    region: str
    currency_exposure: str
    hedged: bool
    core_rank: int
    risk_tags: tuple[str, ...]
    regime_fit: tuple[str, ...]
    notes: str
    source_url: str


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
        number = float(value)
        return None if math.isnan(number) else number
    text = value.strip().replace(",", "")
    if text in {"", ".", "NA", "N/A", "null", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value: str | int | None, default: int = 99) -> int:
    parsed = parse_float(value)
    return int(round(parsed)) if parsed is not None else default


def split_list(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in re.split(r"[;,|]", value) if item.strip())


def parse_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "y", "hedged"}


def latest_row(rows: list[dict[str, str]]) -> dict[str, str]:
    return rows[-1] if rows else {}


def load_universe(path: Path) -> list[EtfCandidate]:
    rows = read_csv(path)
    candidates: list[EtfCandidate] = []
    for row in rows:
        if not row.get("symbol"):
            continue
        candidates.append(
            EtfCandidate(
                sleeve=(row.get("sleeve") or "other").strip(),
                role=(row.get("role") or "").strip(),
                symbol=(row.get("symbol") or "").strip(),
                label=(row.get("label") or "").strip(),
                provider=(row.get("provider") or "").strip(),
                asset_class=(row.get("asset_class") or "").strip(),
                region=(row.get("region") or "").strip(),
                currency_exposure=(row.get("currency_exposure") or "").strip(),
                hedged=parse_bool(row.get("hedged")),
                core_rank=parse_int(row.get("core_rank")),
                risk_tags=split_list(row.get("risk_tags")),
                regime_fit=split_list(row.get("regime_fit")),
                notes=(row.get("notes") or "").strip(),
                source_url=(row.get("source_url") or "").strip(),
            )
        )
    return candidates


def build_context(decision: dict[str, str], risk_row: dict[str, str]) -> dict[str, Any]:
    allocations = {
        "cash_amount": parse_float(decision.get("cash_amount")) or 0.0,
        "gold_amount": parse_float(decision.get("gold_amount")) or 0.0,
        "silver_amount": parse_float(decision.get("silver_amount")) or 0.0,
        "equity_amount": parse_float(decision.get("equity_amount")) or 0.0,
    }
    risk_scores = {field: parse_float(risk_row.get(field)) or 0.0 for field in RISK_FIELDS}
    return {
        "generated_at": datetime.now().replace(microsecond=0).isoformat(),
        "report_date": decision.get("report_date") or risk_row.get("report_date") or "",
        "action_level": decision.get("action_level") or "Proceed with baseline accumulation",
        "risk_posture": decision.get("risk_posture") or "Balanced",
        "decision_confidence": decision.get("decision_confidence") or "",
        "current_regime": decision.get("current_regime") or risk_row.get("current_regime") or "",
        "allocations": allocations,
        "risk_scores": risk_scores,
    }


def target_share_for_sleeve(candidate: EtfCandidate, context: dict[str, Any]) -> float:
    allocations = context["allocations"]
    total = sum(float(value) for value in allocations.values()) or 1.0
    field = SLEEVE_TARGET_FIELD.get(candidate.sleeve)
    if not field:
        return 0.0
    return float(allocations.get(field, 0.0)) / total


def _add(score: float, points: float, reason: str, reasons: list[str]) -> float:
    if points != 0:
        reasons.append(f"{reason} ({points:+.0f})")
    return score + points


def score_candidate(candidate: EtfCandidate, context: dict[str, Any]) -> tuple[float, list[str]]:
    tags = set(candidate.risk_tags)
    posture = str(context.get("risk_posture", "")).lower()
    action = str(context.get("action_level", "")).lower()
    fit_text = " ".join(candidate.regime_fit).lower()
    reasons: list[str] = []

    score = 48.0
    rank_bonus = max(0, 6 - candidate.core_rank) * 4
    score = _add(score, rank_bonus, "core list rank", reasons)

    target_share = target_share_for_sleeve(candidate, context)
    if target_share > 0:
        score = _add(score, target_share * 24, "current sleeve budget", reasons)

    if posture and posture in fit_text:
        score = _add(score, 8, "posture match", reasons)
    elif any(token in fit_text for token in posture.split("/") if token):
        score = _add(score, 5, "partial posture match", reasons)

    is_watch = (
        "watch" in posture
        or "defensive" in posture
        or "data constrained" in posture
        or "confirm" in action
        or "review" in action
    )
    if is_watch:
        if {"defensive", "cash", "low_vol", "quality", "dividend", "duration"} & tags:
            score = _add(score, 10, "defensive/watch fit", reasons)
        if candidate.hedged:
            score = _add(score, 4, "hedged exposure", reasons)
        if {"high_beta", "high_vol", "semiconductor", "cyclical"} & tags:
            score = _add(score, -8, "watchlist risk penalty", reasons)
        if "futures" in tags and "duration" not in tags:
            score = _add(score, -3, "futures complexity", reasons)

    if "inflation" in posture or "fx" in posture:
        if {"gold", "inflation", "commodity", "silver", "copper"} & tags:
            score = _add(score, 12, "inflation hedge fit", reasons)
        if {"usd", "unhedged"} <= tags:
            score = _add(score, 6, "USD exposure", reasons)
        if candidate.hedged and "equity" in tags:
            score = _add(score, -3, "hedged equity in FX posture", reasons)

    if "balanced" in posture or "baseline" in action:
        if "core" in tags:
            score = _add(score, 8, "core accumulation fit", reasons)
        if "equity" in tags:
            score = _add(score, 4, "equity budget fit", reasons)
        if {"quality", "gold", "cash"} & tags:
            score = _add(score, 3, "balance stabilizer", reasons)

    risks = context.get("risk_scores", {})
    inflation = float(risks.get("inflation_risk", 0.0))
    fx = float(risks.get("fx_risk", 0.0))
    credit = float(risks.get("credit_stress_risk", 0.0))
    growth = float(risks.get("growth_slowdown_risk", 0.0))
    market = float(risks.get("market_stress_risk", 0.0))
    liquidity = float(risks.get("liquidity_bubble_risk", 0.0))
    rate_divergence = float(risks.get("global_rate_divergence_risk", 0.0))

    if inflation >= 6 and {"gold", "inflation", "commodity", "silver", "copper"} & tags:
        score = _add(score, 8, "high inflation score", reasons)
    if fx >= 6 and ({"usd", "unhedged", "gold"} & tags):
        score = _add(score, 7, "high FX score", reasons)
    if max(credit, growth, market) >= 6:
        if {"defensive", "cash", "duration", "quality", "dividend"} & tags:
            score = _add(score, 9, "stress defense", reasons)
        if {"high_beta", "semiconductor", "cyclical"} & tags:
            score = _add(score, -7, "stress beta penalty", reasons)
    if liquidity >= 6:
        if {"high_beta", "growth", "tech", "semiconductor"} & tags:
            score = _add(score, -5, "liquidity risk penalty", reasons)
        if {"cash", "gold", "quality"} & tags:
            score = _add(score, 4, "liquidity risk stabilizer", reasons)
    if rate_divergence >= 6 and (candidate.hedged or "duration" in tags):
        score = _add(score, 4, "rate divergence fit", reasons)

    return max(0.0, min(100.0, round(score, 1))), reasons[:5]


def recommendation_band(score: float) -> str:
    if score >= 78:
        return "High fit"
    if score >= 64:
        return "Good fit"
    if score >= 50:
        return "Watchlist"
    return "Secondary"


def candidate_to_row(
    candidate: EtfCandidate,
    score: float,
    reasons: list[str],
    global_rank: int,
    sleeve_rank: int,
) -> dict[str, Any]:
    return {
        "global_rank": global_rank,
        "sleeve_rank": sleeve_rank,
        "score": score,
        "recommendation_band": recommendation_band(score),
        "sleeve": candidate.sleeve,
        "sleeve_label": SLEEVE_LABELS.get(candidate.sleeve, candidate.sleeve.title()),
        "role": candidate.role,
        "symbol": candidate.symbol,
        "label": candidate.label,
        "provider": candidate.provider,
        "asset_class": candidate.asset_class,
        "region": candidate.region,
        "currency_exposure": candidate.currency_exposure,
        "hedged": "yes" if candidate.hedged else "no",
        "core_rank": candidate.core_rank,
        "score_drivers": "; ".join(reasons),
        "risk_tags": "; ".join(candidate.risk_tags),
        "regime_fit": "; ".join(candidate.regime_fit),
        "notes": candidate.notes,
        "source_url": candidate.source_url,
    }


def rank_candidates(candidates: list[EtfCandidate], context: dict[str, Any]) -> list[dict[str, Any]]:
    scored = []
    for candidate in candidates:
        score, reasons = score_candidate(candidate, context)
        scored.append((candidate, score, reasons))
    scored.sort(key=lambda item: (item[1], -item[0].core_rank, item[0].symbol), reverse=True)

    sleeve_counts: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for global_index, (candidate, score, reasons) in enumerate(scored, start=1):
        sleeve_counts[candidate.sleeve] = sleeve_counts.get(candidate.sleeve, 0) + 1
        rows.append(candidate_to_row(candidate, score, reasons, global_index, sleeve_counts[candidate.sleeve]))
    return rows


def output_fieldnames() -> list[str]:
    return [
        "global_rank",
        "sleeve_rank",
        "score",
        "recommendation_band",
        "sleeve",
        "sleeve_label",
        "role",
        "symbol",
        "label",
        "provider",
        "asset_class",
        "region",
        "currency_exposure",
        "hedged",
        "core_rank",
        "score_drivers",
        "risk_tags",
        "regime_fit",
        "notes",
        "source_url",
    ]


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    top = rows[0] if rows else {}
    sleeve_counts: dict[str, int] = {}
    for row in rows:
        sleeve_counts[str(row["sleeve"])] = sleeve_counts.get(str(row["sleeve"]), 0) + 1
    return {
        "candidate_count": len(rows),
        "top_symbol": top.get("symbol", "NA"),
        "top_label": top.get("label", "NA"),
        "top_score": top.get("score", "NA"),
        "sleeve_counts": sleeve_counts,
    }


def render_html(context: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    summary = summarize_rows(rows)
    payload = json.dumps({"context": context, "rows": rows, "summary": summary}, ensure_ascii=False).replace("</", "<\\/")
    cards = [
        ("Action", context.get("action_level", "NA")),
        ("Posture", context.get("risk_posture", "NA")),
        ("Top Candidate", f"{summary['top_symbol']} / {summary['top_score']}"),
        ("Universe", f"{summary['candidate_count']} ETFs"),
    ]
    card_html = "".join(
        f"<div class=\"card\"><div class=\"label\">{escape(label)}</div><div class=\"value\">{escape(str(value))}</div></div>"
        for label, value in cards
    )
    risk_items = []
    for field, label in RISK_FIELDS.items():
        value = context.get("risk_scores", {}).get(field, 0.0)
        risk_items.append(f"<span><strong>{escape(label)}</strong> {float(value):.1f}</span>")
    risk_html = "".join(risk_items)
    sleeve_options = "".join(
        f"<option value=\"{escape(key)}\">{escape(label)}</option>"
        for key, label in SLEEVE_LABELS.items()
    )
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ETF Universe</title>
  <style>
    :root {{
      --bg: #f7f8fa;
      --surface: #ffffff;
      --ink: #1f2933;
      --muted: #66717f;
      --line: #d9dee5;
      --accent: #2563eb;
      --good: #17803d;
      --warn: #b7791f;
      --bad: #b42318;
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
    .wrap {{ max-width: 1220px; margin: 0 auto; padding: 22px 20px 36px; }}
    a {{ color: var(--accent); text-decoration: none; }}
    .topbar {{
      display: grid;
      grid-template-columns: minmax(260px, 1fr) auto;
      gap: 14px;
      align-items: end;
      margin-bottom: 16px;
    }}
    h1 {{ margin: 0; font-size: 28px; line-height: 1.12; }}
    h2 {{ margin: 0; padding: 14px 16px; border-bottom: 1px solid var(--line); font-size: 16px; }}
    .subtle, .label {{ color: var(--muted); font-size: 12px; line-height: 1.45; }}
    .cards {{ display: grid; grid-template-columns: repeat(4, minmax(150px, 1fr)); gap: 10px; margin-bottom: 16px; }}
    .card, .panel, .note {{ background: var(--surface); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); }}
    .card {{ padding: 13px 14px; min-height: 76px; }}
    .value {{ font-weight: 760; font-size: 20px; line-height: 1.2; margin-top: 4px; overflow-wrap: anywhere; }}
    .note {{ padding: 12px 14px; margin-bottom: 16px; }}
    .risk-strip {{ display: flex; gap: 8px 14px; flex-wrap: wrap; color: var(--muted); font-size: 12px; }}
    .panel {{ margin-bottom: 16px; overflow: hidden; }}
    .panel-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 12px 16px;
      border-bottom: 1px solid var(--line);
    }}
    .panel-title {{ font-weight: 720; }}
    .controls {{ display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }}
    input, select {{
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      min-height: 38px;
      padding: 8px 10px;
      font: inherit;
      color: var(--ink);
    }}
    input {{ width: min(320px, 100%); }}
    .panel-body {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 960px; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ color: var(--muted); background: #fbfcfe; font-weight: 700; }}
    tbody tr:hover {{ background: #fbfcfe; }}
    .rank {{ color: var(--muted); font-variant-numeric: tabular-nums; }}
    .score {{ font-weight: 760; font-variant-numeric: tabular-nums; }}
    .score.high {{ color: var(--good); }}
    .score.mid {{ color: var(--accent); }}
    .score.low {{ color: var(--warn); }}
    .band {{
      display: inline-flex;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 700;
      background: #eef3fb;
      color: #38506f;
      white-space: nowrap;
    }}
    .band.high {{ background: #e9f7ef; color: var(--good); }}
    .band.watch {{ background: #fff7e6; color: var(--warn); }}
    .tagline {{ color: var(--muted); font-size: 12px; margin-top: 4px; line-height: 1.45; }}
    .empty {{ padding: 34px 16px; color: var(--muted); text-align: center; }}
    @media (max-width: 820px) {{
      .wrap {{ padding: 18px 12px 28px; }}
      .topbar {{ grid-template-columns: 1fr; }}
      .cards {{ grid-template-columns: 1fr; }}
      .controls {{ justify-content: flex-start; }}
    }}
  </style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div>
      <a href="decision_engine.html">Back to decision engine</a>
      <h1>ETF Universe</h1>
      <div class="subtle">Generated {escape(str(context.get('generated_at', '')))} / Report {escape(str(context.get('report_date', '')))}</div>
    </div>
    <div class="subtle"><a href="stock_watchlist.html">Stock watchlist</a> / <a href="rebalance_orders.html">Rebalance orders</a> / <a href="sector_dashboard.html">Sector dashboard</a> / <a href="daily_brief_latest.md">Daily brief</a></div>
  </div>
  <section class="cards">{card_html}</section>
  <div class="note">
    <div class="risk-strip">{risk_html}</div>
  </div>
  <section class="panel">
    <div class="panel-head">
      <div>
        <div class="panel-title">Candidates</div>
        <div class="subtle" id="tableMeta"></div>
      </div>
      <div class="controls">
        <input id="searchInput" type="search" placeholder="Search ETF, tag, region">
        <select id="sleeveSelect" aria-label="Filter sleeve">
          <option value="all">All sleeves</option>
          {sleeve_options}
        </select>
        <select id="bandSelect" aria-label="Filter score band">
          <option value="all">All score bands</option>
          <option value="High fit">High fit</option>
          <option value="Good fit">Good fit</option>
          <option value="Watchlist">Watchlist</option>
          <option value="Secondary">Secondary</option>
        </select>
      </div>
    </div>
    <div class="panel-body" id="tableWrap"></div>
  </section>
</div>
<script id="etf-data" type="application/json">{payload}</script>
<script>
const DATA = JSON.parse(document.getElementById('etf-data').textContent);
const searchInput = document.getElementById('searchInput');
const sleeveSelect = document.getElementById('sleeveSelect');
const bandSelect = document.getElementById('bandSelect');

function esc(value) {{
  return String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
}}

function scoreClass(score) {{
  if (score >= 78) return 'score high';
  if (score >= 64) return 'score mid';
  return 'score low';
}}

function bandClass(band) {{
  if (band === 'High fit') return 'band high';
  if (band === 'Watchlist' || band === 'Secondary') return 'band watch';
  return 'band';
}}

function matches(row, query) {{
  if (!query) return true;
  const haystack = [row.symbol, row.label, row.provider, row.sleeve_label, row.asset_class, row.region, row.currency_exposure, row.risk_tags, row.regime_fit, row.notes].join(' ').toLowerCase();
  return haystack.includes(query.toLowerCase());
}}

function filteredRows() {{
  const query = searchInput.value.trim();
  const sleeve = sleeveSelect.value;
  const band = bandSelect.value;
  return DATA.rows.filter(row => {{
    if (sleeve !== 'all' && row.sleeve !== sleeve) return false;
    if (band !== 'all' && row.recommendation_band !== band) return false;
    return matches(row, query);
  }});
}}

function renderTable() {{
  const rows = filteredRows();
  document.getElementById('tableMeta').textContent = `${{rows.length}} of ${{DATA.rows.length}} candidates visible`;
  const wrap = document.getElementById('tableWrap');
  if (!rows.length) {{
    wrap.innerHTML = '<div class="empty">No ETF candidates match the current filter.</div>';
    return;
  }}
  const html = rows.map(row => `
    <tr>
      <td class="rank">${{esc(row.global_rank)}} / ${{esc(row.sleeve_rank)}}</td>
      <td><span class="${{scoreClass(Number(row.score))}}">${{esc(row.score)}}</span><div><span class="${{bandClass(row.recommendation_band)}}">${{esc(row.recommendation_band)}}</span></div></td>
      <td><strong><a href="${{esc(row.source_url)}}">${{esc(row.label)}}</a></strong><div class="tagline">${{esc(row.symbol)}} / ${{esc(row.provider)}} / ${{esc(row.sleeve_label)}}</div></td>
      <td>${{esc(row.asset_class)}}<div class="tagline">${{esc(row.region)}} / ${{esc(row.currency_exposure)}} / hedge ${{esc(row.hedged)}}</div></td>
      <td>${{esc(row.score_drivers)}}</td>
      <td>${{esc(row.risk_tags)}}</td>
      <td>${{esc(row.notes)}}</td>
    </tr>
  `).join('');
  wrap.innerHTML = `
    <table>
      <thead>
        <tr>
          <th style="width: 7%">Rank</th>
          <th style="width: 11%">Score</th>
          <th style="width: 22%">ETF</th>
          <th style="width: 15%">Exposure</th>
          <th style="width: 20%">Score drivers</th>
          <th style="width: 13%">Tags</th>
          <th style="width: 12%">Notes</th>
        </tr>
      </thead>
      <tbody>${{html}}</tbody>
    </table>
  `;
}}

searchInput.addEventListener('input', renderTable);
sleeveSelect.addEventListener('change', renderTable);
bandSelect.addEventListener('change', renderTable);
renderTable();
</script>
</body>
</html>
"""


def write_etf_universe(args: argparse.Namespace) -> tuple[Path, Path]:
    candidates = load_universe(Path(args.universe))
    context = build_context(
        latest_row(read_csv(Path(args.decision))),
        latest_row(read_csv(Path(args.risk_history))),
    )
    rows = rank_candidates(candidates, context)

    output_csv = Path(args.output_csv)
    html = Path(args.html)
    html.parent.mkdir(parents=True, exist_ok=True)
    write_csv(output_csv, rows, output_fieldnames())
    html.write_text(render_html(context, rows), encoding="utf-8")
    return output_csv, html


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rank ETF universe candidates against the latest macro decision context.")
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE))
    parser.add_argument("--decision", default=str(DEFAULT_DECISION))
    parser.add_argument("--risk-history", default=str(DEFAULT_RISK_HISTORY))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--html", default=str(DEFAULT_HTML))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_csv, html = write_etf_universe(args)
    print(f"Generated ETF universe CSV: {output_csv}")
    print(f"Generated ETF universe HTML: {html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
