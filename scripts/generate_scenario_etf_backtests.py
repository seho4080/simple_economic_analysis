#!/usr/bin/env python3
"""Apply saved scenario allocations to existing ISA ETF backtest return paths."""

from __future__ import annotations

import argparse
import csv
import math
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Any

from backtest_monthly_allocation import MANWON_TO_KRW, xirr


DEFAULT_SCENARIO_MATRIX = Path("data/processed/macro/scenario_matrix_latest.csv")
DEFAULT_VARIANT_SUMMARY = Path("data/processed/backtests/isa_etf_max/variant_summary.csv")
DEFAULT_BACKTEST_ROOT = Path("data/processed/backtests/isa_etf_max")
DEFAULT_OUTPUT_DIR = Path("data/processed/backtests/scenario_etf_backtests")
DEFAULT_REPORT = Path("reports/scenario_etf_backtests.html")

ASSETS = [
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


def pct(value: float | None) -> str:
    return "NA" if value is None else f"{value:.1%}"


def money(value: float | int | None) -> str:
    if value is None:
        return "NA"
    return f"{int(round(float(value))):,}원"


def csv_value(value: Any) -> Any:
    if isinstance(value, float):
        return "" if math.isnan(value) else round(value, 8)
    if value is None:
        return ""
    return value


def scenario_allocations(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    scenarios = []
    for row in rows:
        slug = row.get("scenario_slug", "").strip()
        if not slug:
            continue
        allocation = {asset: parse_int(row.get(f"{asset}_amount")) for asset, _label in ASSETS}
        if sum(allocation.values()) <= 0:
            continue
        scenarios.append(
            {
                "scenario_slug": slug,
                "scenario_title": row.get("title", slug),
                "current_regime": row.get("current_regime", ""),
                "supporting_regime": row.get("supporting_regime", ""),
                **{f"{asset}_amount": allocation[asset] for asset, _label in ASSETS},
            }
        )
    return scenarios


def trade_returns_by_date(trade_rows: list[dict[str, str]]) -> dict[str, dict[str, dict[str, Any]]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for row in trade_rows:
        report_date = row.get("report_date", "")
        asset = row.get("asset", "")
        asset_return = parse_float(row.get("return"))
        if not report_date or not asset or asset_return is None:
            continue
        grouped.setdefault(report_date, {})[asset] = {
            "return": asset_return,
            "label": row.get("label", ""),
            "symbol": row.get("symbol", ""),
            "buy_date": row.get("buy_date", ""),
            "buy_price_krw": row.get("buy_price_krw", ""),
            "final_price_krw": row.get("final_price_krw", ""),
        }
    return grouped


def simulate_scenario_variant(
    scenario: dict[str, Any],
    variant: dict[str, str],
    trade_rows: list[dict[str, str]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    returns_by_date = trade_returns_by_date(trade_rows)
    valuation_date = variant.get("valuation_date", "")
    if not returns_by_date or not valuation_date:
        raise ValueError(f"Missing trade returns or valuation date for {variant.get('variant', '')}")

    lot_rows: list[dict[str, Any]] = []
    missing_lots = 0
    for report_date in sorted(returns_by_date):
        for asset, _label in ASSETS:
            amount_krw = parse_int(scenario.get(f"{asset}_amount")) * MANWON_TO_KRW
            ref = returns_by_date[report_date].get(asset)
            if amount_krw <= 0:
                continue
            if not ref:
                missing_lots += 1
                continue
            final_value = amount_krw * (1.0 + float(ref["return"]))
            lot_rows.append(
                {
                    "scenario_slug": scenario["scenario_slug"],
                    "scenario_title": scenario["scenario_title"],
                    "variant": variant["variant"],
                    "variant_title": variant["title"],
                    "report_date": report_date,
                    "asset": asset,
                    "label": ref["label"],
                    "symbol": ref["symbol"],
                    "scenario_amount_krw": round(amount_krw),
                    "reference_return": ref["return"],
                    "final_value_krw": round(final_value),
                    "profit_krw": round(final_value - amount_krw),
                    "buy_date": ref["buy_date"],
                    "buy_price_krw": ref["buy_price_krw"],
                    "final_price_krw": ref["final_price_krw"],
                }
            )

    if not lot_rows:
        raise ValueError(f"No reusable lot rows for {scenario['scenario_slug']} / {variant['variant']}")

    contribution = sum(float(row["scenario_amount_krw"]) for row in lot_rows)
    final_value = sum(float(row["final_value_krw"]) for row in lot_rows)
    profit = final_value - contribution
    flows = [(date.fromisoformat(row["report_date"]), -float(row["scenario_amount_krw"])) for row in lot_rows]
    flows.append((date.fromisoformat(valuation_date), final_value))
    scenario_xirr = xirr(flows)
    reference_return = parse_float(variant.get("simple_return"))
    reference_xirr = parse_float(variant.get("xirr"))
    start = min(row["report_date"] for row in lot_rows)
    end = max(row["report_date"] for row in lot_rows)

    summary = {
        "scenario_slug": scenario["scenario_slug"],
        "scenario_title": scenario["scenario_title"],
        "current_regime": scenario.get("current_regime", ""),
        "variant": variant["variant"],
        "variant_title": variant["title"],
        "start": start,
        "end": end,
        "valuation_date": valuation_date,
        "cash_amount": scenario["cash_amount"],
        "gold_amount": scenario["gold_amount"],
        "silver_amount": scenario["silver_amount"],
        "equity_amount": scenario["equity_amount"],
        "cash_symbol": variant.get("cash_symbol", ""),
        "gold_symbol": variant.get("gold_symbol", ""),
        "silver_symbol": variant.get("silver_symbol", ""),
        "equity_symbol": variant.get("equity_symbol", ""),
        "contribution_krw": round(contribution),
        "final_value_krw": round(final_value),
        "profit_krw": round(profit),
        "simple_return": final_value / contribution - 1.0 if contribution else None,
        "xirr": scenario_xirr,
        "reference_dynamic_return": reference_return,
        "reference_dynamic_xirr": reference_xirr,
        "excess_simple_return": (final_value / contribution - 1.0 - reference_return) if reference_return is not None and contribution else None,
        "excess_xirr": (scenario_xirr - reference_xirr) if scenario_xirr is not None and reference_xirr is not None else None,
        "missing_lots": missing_lots,
    }
    return summary, lot_rows


def build_outputs(
    scenario_rows: list[dict[str, str]],
    variant_rows: list[dict[str, str]],
    backtest_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scenarios = scenario_allocations(scenario_rows)
    summaries: list[dict[str, Any]] = []
    lots: list[dict[str, Any]] = []
    for variant in variant_rows:
        slug = variant.get("variant", "")
        if not slug:
            continue
        trade_path = backtest_root / slug / "actual_etf_trades.csv"
        trades = read_csv(trade_path)
        if not trades:
            continue
        for scenario in scenarios:
            summary, lot_rows = simulate_scenario_variant(scenario, variant, trades)
            summaries.append(summary)
            lots.extend(lot_rows)
    summaries.sort(key=lambda row: (row["scenario_slug"], -(row.get("xirr") or -999), row["variant"]))
    return summaries, lots


def best_rows_by_scenario(summary_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in summary_rows:
        slug = row["scenario_slug"]
        current = best.get(slug)
        if current is None or (row.get("xirr") or -999) > (current.get("xirr") or -999):
            best[slug] = row
    return sorted(best.values(), key=lambda row: row["scenario_slug"])


def delta_class(value: float | None) -> str:
    if value is None:
        return "neutral"
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def render_html(summary_rows: list[dict[str, Any]], generated_at: str) -> str:
    best_rows = best_rows_by_scenario(summary_rows)
    best_html = []
    for row in best_rows:
        allocation = f"{row['cash_amount']}/{row['gold_amount']}/{row['silver_amount']}/{row['equity_amount']}m"
        best_html.append(
            "<tr>"
            f"<td><strong>{escape(str(row['scenario_title']))}</strong><div class=\"subtle\">{escape(str(row['current_regime']))}</div></td>"
            f"<td>{escape(str(row['variant_title']))}</td>"
            f"<td>{allocation}</td>"
            f"<td>{money(row['contribution_krw'])}</td>"
            f"<td>{money(row['final_value_krw'])}</td>"
            f"<td>{pct(row.get('simple_return'))}</td>"
            f"<td>{pct(row.get('xirr'))}</td>"
            f"<td class=\"{delta_class(row.get('excess_xirr'))}\">{pct(row.get('excess_xirr'))}</td>"
            "</tr>"
        )

    detail_html = []
    for row in summary_rows:
        combo = " / ".join(row.get(f"{asset}_symbol", "") for asset, _label in ASSETS)
        detail_html.append(
            "<tr>"
            f"<td>{escape(str(row['scenario_title']))}</td>"
            f"<td>{escape(str(row['variant_title']))}<div class=\"subtle\">{escape(combo)}</div></td>"
            f"<td>{row['start']}~{row['end']}</td>"
            f"<td>{money(row['profit_krw'])}</td>"
            f"<td>{pct(row.get('simple_return'))}</td>"
            f"<td>{pct(row.get('xirr'))}</td>"
            f"<td>{pct(row.get('reference_dynamic_xirr'))}</td>"
            f"<td class=\"{delta_class(row.get('excess_xirr'))}\">{pct(row.get('excess_xirr'))}</td>"
            f"<td>{row.get('missing_lots', 0)}</td>"
            "</tr>"
        )

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Scenario ISA ETF Backtests</title>
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
    .note {{
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 16px;
    }}
    table {{ width: 100%; border-collapse: collapse; min-width: 940px; }}
    th, td {{ padding: 11px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ color: var(--muted); background: #fbfcfe; font-weight: 700; }}
    .positive {{ color: var(--positive); font-weight: 700; }}
    .negative {{ color: var(--negative); font-weight: 700; }}
    .neutral {{ color: var(--muted); }}
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
      <h1>Scenario ISA ETF Backtests</h1>
      <div class="subtle">Generated {escape(generated_at)} / rows {len(summary_rows)}</div>
    </div>
    <div class="subtle"><a href="decision_engine.html">Decision engine</a> / <a href="scenario_matrix.html">Scenario matrix</a> / <a href="scenario_simulator.html">Scenario simulator</a> / <a href="daily_brief_latest.md">Daily brief</a></div>
  </div>
  <div class="note">This report reuses the existing ISA ETF max backtest trade-return paths and applies each saved scenario's fixed monthly allocation. It is a fast scenario bridge; full path drawdown is not recomputed here.</div>
  <section class="panel">
    <h2>Best ETF Variant By Scenario</h2>
    <div class="panel-body">
      <table>
        <thead><tr><th>Scenario</th><th>Best variant</th><th>Allocation</th><th>Contribution</th><th>Final value</th><th>Return</th><th>XIRR</th><th>XIRR vs dynamic baseline</th></tr></thead>
        <tbody>{''.join(best_html)}</tbody>
      </table>
    </div>
  </section>
  <section class="panel">
    <h2>Scenario x ETF Variant Matrix</h2>
    <div class="panel-body">
      <table>
        <thead><tr><th>Scenario</th><th>ETF variant</th><th>Period</th><th>Profit</th><th>Return</th><th>XIRR</th><th>Dynamic baseline XIRR</th><th>XIRR gap</th><th>Missing lots</th></tr></thead>
        <tbody>{''.join(detail_html)}</tbody>
      </table>
    </div>
  </section>
</div>
</body>
</html>
"""


def summary_fieldnames() -> list[str]:
    fields = [
        "scenario_slug",
        "scenario_title",
        "current_regime",
        "variant",
        "variant_title",
        "start",
        "end",
        "valuation_date",
    ]
    fields.extend([f"{asset}_amount" for asset, _label in ASSETS])
    fields.extend([f"{asset}_symbol" for asset, _label in ASSETS])
    fields.extend(
        [
            "contribution_krw",
            "final_value_krw",
            "profit_krw",
            "simple_return",
            "xirr",
            "reference_dynamic_return",
            "reference_dynamic_xirr",
            "excess_simple_return",
            "excess_xirr",
            "missing_lots",
        ]
    )
    return fields


def lot_fieldnames() -> list[str]:
    return [
        "scenario_slug",
        "scenario_title",
        "variant",
        "variant_title",
        "report_date",
        "asset",
        "label",
        "symbol",
        "scenario_amount_krw",
        "reference_return",
        "final_value_krw",
        "profit_krw",
        "buy_date",
        "buy_price_krw",
        "final_price_krw",
    ]


def write_outputs(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    scenario_rows = read_csv(Path(args.scenario_matrix))
    variant_rows = read_csv(Path(args.variant_summary))
    summary_rows, lot_rows = build_outputs(scenario_rows, variant_rows, Path(args.backtest_root))

    output_dir = Path(args.output_dir)
    summary_csv = Path(args.summary_csv) if args.summary_csv else output_dir / "scenario_etf_summary.csv"
    lots_csv = Path(args.lots_csv) if args.lots_csv else output_dir / "scenario_etf_lots.csv"
    report = Path(args.report)

    summary_fields = summary_fieldnames()
    lot_fields = lot_fieldnames()
    write_csv(summary_csv, [{key: csv_value(row.get(key)) for key in summary_fields} for row in summary_rows], summary_fields)
    write_csv(lots_csv, [{key: csv_value(row.get(key)) for key in lot_fields} for row in lot_rows], lot_fields)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        render_html(summary_rows, datetime.now().replace(microsecond=0).isoformat()),
        encoding="utf-8",
    )
    return report, summary_csv, lots_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate scenario ISA ETF backtest bridge.")
    parser.add_argument("--scenario-matrix", default=str(DEFAULT_SCENARIO_MATRIX))
    parser.add_argument("--variant-summary", default=str(DEFAULT_VARIANT_SUMMARY))
    parser.add_argument("--backtest-root", default=str(DEFAULT_BACKTEST_ROOT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--summary-csv", default="")
    parser.add_argument("--lots-csv", default="")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report, summary_csv, lots_csv = write_outputs(args)
    print(f"Generated scenario ETF backtests: {report}")
    print(f"Generated scenario ETF summary: {summary_csv}")
    print(f"Generated scenario ETF lots: {lots_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
