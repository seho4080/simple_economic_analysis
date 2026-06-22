#!/usr/bin/env python3
"""Generate a static what-if scenario simulator for macro risk scores."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

import analyze_macro_regime as regime


DEFAULT_RISK_HISTORY = Path("data/processed/macro/risk_score_history.csv")
DEFAULT_OUTPUT = Path("reports/scenario_simulator.html")

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


@dataclass(frozen=True)
class ScenarioPayload:
    generated_at: str
    report_date: str
    baseline_scores: dict[str, float]
    baseline_regime: dict[str, str]
    baseline_allocation: dict[str, int]
    risk_fields: list[dict[str, str]]


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


def latest_row(path: Path) -> dict[str, str]:
    rows = read_csv(path)
    return rows[-1] if rows else {}


def scores_from_row(row: dict[str, str]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for field, score_name, _label in RISK_FIELDS:
        scores[score_name] = parse_float(row.get(field)) or 0.0
    return scores


def scenario_result(scores: dict[str, float]) -> dict[str, Any]:
    current, supporting, summary = regime.determine_regime(scores)
    allocation = regime.build_allocation(scores)
    return {
        "current_regime": current,
        "supporting_regime": supporting,
        "summary": summary,
        "allocation": allocation,
    }


def build_payload(risk_history: Path) -> ScenarioPayload:
    row = latest_row(risk_history)
    scores = scores_from_row(row)
    result = scenario_result(scores)
    return ScenarioPayload(
        generated_at=datetime.now().replace(microsecond=0).isoformat(),
        report_date=row.get("report_date", ""),
        baseline_scores=scores,
        baseline_regime={
            "current": result["current_regime"],
            "supporting": result["supporting_regime"],
        },
        baseline_allocation=result["allocation"],
        risk_fields=[
            {"field": field, "scoreName": score_name, "label": label}
            for field, score_name, label in RISK_FIELDS
        ],
    )


def render_html(payload: ScenarioPayload) -> str:
    data = json.dumps(payload.__dict__, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Macro Scenario Simulator</title>
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
      color: var(--ink);
      background: var(--bg);
      letter-spacing: 0;
    }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 22px 20px 34px; }}
    a {{ color: var(--accent); text-decoration: none; }}
    .topbar {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 16px;
    }}
    h1 {{ margin: 0; font-size: 28px; line-height: 1.1; }}
    .meta {{ color: var(--muted); font-size: 13px; margin-top: 7px; }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(320px, 0.95fr) minmax(0, 1.35fr);
      gap: 16px;
      align-items: start;
    }}
    .panel, .card {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    .panel h2 {{
      margin: 0;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      font-size: 16px;
    }}
    .panel-body {{ padding: 14px 16px; }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(4, minmax(130px, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }}
    .card {{ padding: 13px 14px; }}
    .label {{ color: var(--muted); font-size: 12px; }}
    .value {{ font-weight: 760; font-size: 22px; line-height: 1.2; margin-top: 4px; }}
    .controls {{ display: grid; gap: 12px; }}
    .slider-row {{
      display: grid;
      grid-template-columns: minmax(110px, 150px) 1fr 44px;
      gap: 10px;
      align-items: center;
    }}
    input[type="range"] {{ width: 100%; accent-color: var(--accent); }}
    .score-value {{
      text-align: right;
      font-variant-numeric: tabular-nums;
      color: var(--ink);
      font-weight: 700;
    }}
    .buttons {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      margin-top: 14px;
    }}
    button {{
      border: 1px solid var(--line);
      background: white;
      color: var(--ink);
      border-radius: 7px;
      min-height: 38px;
      padding: 8px 10px;
      cursor: pointer;
      font: inherit;
    }}
    button.primary {{
      background: var(--accent);
      border-color: var(--accent);
      color: white;
    }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; font-size: 13px; }}
    th {{ color: var(--muted); background: #fbfcfe; }}
    .delta.positive {{ color: var(--good); font-weight: 700; }}
    .delta.negative {{ color: var(--bad); font-weight: 700; }}
    .bar-wrap {{ display: grid; gap: 9px; }}
    .bar-row {{ display: grid; grid-template-columns: 110px 1fr 60px; gap: 10px; align-items: center; }}
    .bar-track {{ height: 12px; background: #edf1f5; border-radius: 999px; overflow: hidden; }}
    .bar {{ height: 100%; background: var(--accent); }}
    .subtle {{ color: var(--muted); font-size: 12px; }}
    @media (max-width: 900px) {{
      .grid {{ grid-template-columns: 1fr; }}
      .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 560px) {{
      .wrap {{ padding: 18px 12px 28px; }}
      .topbar {{ display: block; }}
      .cards {{ grid-template-columns: 1fr; }}
      .slider-row {{ grid-template-columns: 1fr 1fr 42px; }}
      .slider-row .label {{ grid-column: 1 / -1; }}
      .buttons {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div>
      <a href="sector_dashboard.html">Back to sector dashboard</a>
      <h1>Macro Scenario Simulator</h1>
      <div class="meta">Baseline {escape(payload.report_date or 'NA')} / Generated {escape(payload.generated_at)}</div>
    </div>
    <div class="meta"><a href="decision_engine.html">Decision engine</a> / <a href="scenario_matrix.html">Scenario matrix</a> / <a href="scenario_etf_backtests.html">Scenario ETF backtests</a> / <a href="daily_brief_latest.md">Daily brief</a></div>
  </div>
  <section class="cards">
    <div class="card"><div class="label">Regime</div><div class="value" id="regimeValue"></div></div>
    <div class="card"><div class="label">Supporting</div><div class="value" id="supportingValue"></div></div>
    <div class="card"><div class="label">Cash/short bonds</div><div class="value" id="cashValue"></div></div>
    <div class="card"><div class="label">Equity/ETF</div><div class="value" id="equityValue"></div></div>
  </section>
  <section class="grid">
    <div class="panel">
      <h2>Risk Score Inputs</h2>
      <div class="panel-body">
        <div class="controls" id="sliders"></div>
        <div class="buttons">
          <button class="primary" id="resetBtn">Reset baseline</button>
          <button id="inflationFxBtn">Inflation/FX shock</button>
          <button id="creditBtn">Credit shock</button>
          <button id="goldilocksBtn">Goldilocks</button>
        </div>
      </div>
    </div>
    <div class="panel">
      <h2>Allocation Result</h2>
      <div class="panel-body">
        <div class="bar-wrap" id="allocationBars"></div>
      </div>
    </div>
    <div class="panel">
      <h2>Score Delta</h2>
      <div class="panel-body" id="scoreTable"></div>
    </div>
    <div class="panel">
      <h2>Allocation Delta</h2>
      <div class="panel-body" id="allocationTable"></div>
    </div>
  </section>
</div>
<script id="scenario-data" type="application/json">{data}</script>
<script>
const DATA = JSON.parse(document.getElementById('scenario-data').textContent);
const TOTAL = 150;
const INCREMENT = 5;
const BOUNDS = {{ cash: [0.10, 0.50], hedge: [0.15, 0.50], equity: [0.25, 0.65] }};
const baseline = DATA.baseline_scores;
let scores = {{ ...baseline }};

function roundToIncrement(value) {{
  return Math.floor(value / INCREMENT + 0.5) * INCREMENT;
}}

function fmt(value) {{
  if (value === null || value === undefined || Number.isNaN(value)) return 'NA';
  return Number(value).toFixed(1).replace(/\\.0$/, '');
}}

function deltaClass(value) {{
  if (value > 0) return 'delta positive';
  if (value < 0) return 'delta negative';
  return 'delta';
}}

function determineRegime(s) {{
  const inflation = s['Inflation Risk'];
  const liquidity = s['Liquidity Bubble Risk'];
  const credit = s['Credit Stress Risk'];
  const fx = s['FX Risk'];
  const climate = s['Climate Supply Shock Risk'];
  const growth = s['Growth Slowdown Risk'];
  let current;
  if (credit >= 6.5) current = 'Credit Stress';
  else if (inflation >= 6.5 && growth >= 6.0) current = 'Stagflation Risk';
  else if (inflation >= 6.0 && fx >= 6.0) current = 'Inflation Rebound + Dollar/KRW Risk';
  else if (liquidity >= 7.0 && credit < 5.0) current = 'Liquidity Bubble';
  else if (inflation <= 4.5 && credit <= 4.0 && growth <= 4.5) current = 'Goldilocks';
  else current = 'Defensive Waiting Mode';

  const helpers = [];
  if (climate >= 6.5) helpers.push('Climate Supply Shock Risk');
  if (liquidity >= 6.0 && credit < 5.0) helpers.push('Liquidity Bubble');
  if (growth >= 5.5) helpers.push('Growth Slowdown Risk');
  if (fx >= 6.5 && !current.includes('Dollar/KRW Risk')) helpers.push('Dollar/KRW Risk');
  if (!helpers.length) helpers.push('Defensive Waiting Mode');
  return {{ current, supporting: helpers.join(' / ') }};
}}

function rawScores(s) {{
  return {{
    cash: Math.max(0.1, 0.6 + 0.55 * s['Credit Stress Risk'] + 0.36 * s['Growth Slowdown Risk'] + 0.04 * s['FX Risk'] - 0.08 * s['Liquidity Bubble Risk']),
    hedge: Math.max(0.1, 1.0 + 0.42 * s['Inflation Risk'] + 0.35 * s['FX Risk'] + 0.30 * s['Climate Supply Shock Risk']),
    equity: Math.max(0.1, 1.2 + 0.34 * s['Liquidity Bubble Risk'] + 0.25 * (10 - s['Credit Stress Risk']) + 0.20 * (10 - s['Growth Slowdown Risk']) - 0.05 * s['Inflation Risk'] + 0.08 * s['FX Risk'])
  }};
}}

function boundedShares(rawShares) {{
  const fixed = {{}};
  let remaining = new Set(Object.keys(rawShares));
  let shares = {{}};
  for (let i = 0; i < Object.keys(rawShares).length + 1; i++) {{
    const remainingTotal = 1 - Object.values(fixed).reduce((a, b) => a + b, 0);
    const rawTotal = [...remaining].reduce((sum, name) => sum + Math.max(rawShares[name], 0.01), 0);
    let changed = false;
    const candidates = {{}};
    remaining.forEach(name => {{
      const value = rawTotal ? remainingTotal * Math.max(rawShares[name], 0.01) / rawTotal : remainingTotal / remaining.size;
      const [low, high] = BOUNDS[name];
      if (value < low) {{ fixed[name] = low; changed = true; }}
      else if (value > high) {{ fixed[name] = high; changed = true; }}
      else candidates[name] = value;
    }});
    if (!changed) {{ shares = {{ ...fixed, ...candidates }}; break; }}
    remaining = new Set(Object.keys(rawShares).filter(name => fixed[name] === undefined));
    if (!remaining.size) {{ shares = {{ ...fixed }}; break; }}
  }}
  const total = Object.values(shares).reduce((a, b) => a + b, 0);
  return Object.fromEntries(Object.entries(shares).map(([name, value]) => [name, value / total]));
}}

function roundedSleeves(shares) {{
  const amounts = Object.fromEntries(Object.entries(shares).map(([name, share]) => [name, roundToIncrement(TOTAL * share)]));
  let diff = TOTAL - Object.values(amounts).reduce((a, b) => a + b, 0);
  while (diff !== 0) {{
    const step = diff > 0 ? INCREMENT : -INCREMENT;
    const names = Object.keys(amounts);
    const target = diff < 0
      ? names.reduce((a, b) => amounts[a] > amounts[b] ? a : b)
      : names.reduce((a, b) => amounts[a] < amounts[b] ? a : b);
    amounts[target] += step;
    diff -= step;
  }}
  return amounts;
}}

function goldRatio(s) {{
  let ratio = 0.66;
  if (s['Inflation Risk'] >= 6) ratio += 0.04;
  if (s['FX Risk'] >= 6) ratio += 0.04;
  if (s['Climate Supply Shock Risk'] >= 7) ratio -= 0.04;
  return Math.max(0.60, Math.min(0.78, ratio));
}}

function allocation(s) {{
  const raw = rawScores(s);
  const totalRaw = Object.values(raw).reduce((a, b) => a + b, 0);
  const rawShares = Object.fromEntries(Object.entries(raw).map(([name, value]) => [name, value / totalRaw]));
  const bounded = boundedShares(rawShares);
  const sleeves = roundedSleeves(bounded);
  const ratio = goldRatio(s);
  let gold = roundToIncrement(sleeves.hedge * ratio);
  let silver = sleeves.hedge - gold;
  if (sleeves.hedge >= 10 && silver < INCREMENT) {{
    silver = INCREMENT;
    gold = sleeves.hedge - silver;
  }}
  return {{ cash: sleeves.cash, gold, silver, equity: sleeves.equity }};
}}

function setScores(next) {{
  scores = {{ ...scores, ...next }};
  DATA.risk_fields.forEach(field => {{
    const el = document.querySelector(`[data-score="${{field.scoreName}}"]`);
    if (el) el.value = scores[field.scoreName];
  }});
  render();
}}

function renderSliders() {{
  const wrap = document.getElementById('sliders');
  wrap.innerHTML = DATA.risk_fields.map(field => `
    <div class="slider-row">
      <div class="label">${{field.label}}</div>
      <input type="range" min="0" max="10" step="0.1" value="${{scores[field.scoreName]}}" data-score="${{field.scoreName}}">
      <div class="score-value" id="value-${{field.field}}">${{fmt(scores[field.scoreName])}}</div>
    </div>
  `).join('');
  wrap.querySelectorAll('input[type="range"]').forEach(input => {{
    input.addEventListener('input', () => {{
      scores[input.dataset.score] = Number(input.value);
      render();
    }});
  }});
}}

function table(headers, rows) {{
  return `<table><thead><tr>${{headers.map(h => `<th>${{h}}</th>`).join('')}}</tr></thead><tbody>${{rows.map(row => `<tr>${{row.map(c => `<td>${{c}}</td>`).join('')}}</tr>`).join('')}}</tbody></table>`;
}}

function render() {{
  DATA.risk_fields.forEach(field => {{
    const value = scores[field.scoreName];
    const label = document.getElementById(`value-${{field.field}}`);
    if (label) label.textContent = fmt(value);
  }});
  const reg = determineRegime(scores);
  const alloc = allocation(scores);
  document.getElementById('regimeValue').textContent = reg.current;
  document.getElementById('supportingValue').textContent = reg.supporting;
  document.getElementById('cashValue').textContent = `${{alloc.cash}}m`;
  document.getElementById('equityValue').textContent = `${{alloc.equity}}m`;
  const allocationLabels = [
    ['cash', 'Cash/short bonds'],
    ['gold', 'Gold'],
    ['silver', 'Silver/commodities'],
    ['equity', 'Equity/ETF']
  ];
  document.getElementById('allocationBars').innerHTML = allocationLabels.map(([key, label]) => `
    <div class="bar-row">
      <div class="label">${{label}}</div>
      <div class="bar-track"><div class="bar" style="width:${{alloc[key] / TOTAL * 100}}%"></div></div>
      <div class="score-value">${{alloc[key]}}m</div>
    </div>
  `).join('');
  document.getElementById('scoreTable').innerHTML = table(
    ['Score', 'Scenario', 'Baseline', 'Delta'],
    DATA.risk_fields.map(field => {{
      const base = baseline[field.scoreName] || 0;
      const value = scores[field.scoreName] || 0;
      const delta = value - base;
      return [field.label, fmt(value), fmt(base), `<span class="${{deltaClass(delta)}}">${{delta >= 0 ? '+' : ''}}${{fmt(delta)}}</span>`];
    }})
  );
  document.getElementById('allocationTable').innerHTML = table(
    ['Sleeve', 'Scenario', 'Baseline', 'Delta'],
    allocationLabels.map(([key, label]) => {{
      const base = DATA.baseline_allocation[key] || 0;
      const value = alloc[key] || 0;
      const delta = value - base;
      return [label, `${{value}}m`, `${{base}}m`, `<span class="${{deltaClass(delta)}}">${{delta >= 0 ? '+' : ''}}${{delta}}m</span>`];
    }})
  );
}}

document.getElementById('resetBtn').addEventListener('click', () => setScores({{ ...baseline }}));
document.getElementById('inflationFxBtn').addEventListener('click', () => setScores({{
  'Inflation Risk': 7.2,
  'FX Risk': 7.0,
  'Climate Supply Shock Risk': Math.max(scores['Climate Supply Shock Risk'], 5.8)
}}));
document.getElementById('creditBtn').addEventListener('click', () => setScores({{
  'Credit Stress Risk': 7.2,
  'Growth Slowdown Risk': 6.4,
  'Liquidity Bubble Risk': Math.min(scores['Liquidity Bubble Risk'], 4.0)
}}));
document.getElementById('goldilocksBtn').addEventListener('click', () => setScores({{
  'Inflation Risk': 3.8,
  'Liquidity Bubble Risk': 5.0,
  'Credit Stress Risk': 2.0,
  'FX Risk': 3.8,
  'Climate Supply Shock Risk': 2.5,
  'Growth Slowdown Risk': 3.2,
  'Market Stress Risk': 2.0,
  'Global Rate Divergence Risk': 3.0
}}));

renderSliders();
render();
</script>
</body>
</html>
"""


def write_simulator(args: argparse.Namespace) -> Path:
    payload = build_payload(Path(args.risk_history))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(payload), encoding="utf-8")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a static macro scenario simulator.")
    parser.add_argument("--risk-history", default=str(DEFAULT_RISK_HISTORY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output = write_simulator(args)
    print(f"Generated scenario simulator: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
