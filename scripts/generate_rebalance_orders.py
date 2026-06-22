#!/usr/bin/env python3
"""Generate buy-only rebalance order guidance from holdings and the decision engine."""

from __future__ import annotations

import argparse
import csv
import math
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any


DEFAULT_DECISION = Path("data/processed/macro/decision_engine_latest.csv")
DEFAULT_SCENARIO_ETF = Path("data/processed/backtests/scenario_etf_backtests/scenario_etf_summary.csv")
DEFAULT_HOLDINGS = Path("config/portfolio_holdings.csv")
DEFAULT_HTML = Path("reports/rebalance_orders.html")
DEFAULT_MD = Path("reports/rebalance_orders_latest.md")
DEFAULT_ORDER_CSV = Path("data/processed/portfolio/rebalance_orders_latest.csv")
DEFAULT_TARGET_CSV = Path("data/processed/portfolio/portfolio_targets_latest.csv")

DEFAULT_MONTHLY_CONTRIBUTION_KRW = 1_500_000
DEFAULT_INCREMENT_KRW = 50_000

ASSETS = [
    ("cash", "Cash/short bonds"),
    ("gold", "Gold"),
    ("silver", "Silver/commodities"),
    ("equity", "Equity/ETF"),
]

SYMBOL_LABELS = {
    "153130.KS": "KODEX 단기채권",
    "273130.KS": "KODEX 종합채권(AA-이상)액티브",
    "305080.KS": "TIGER 미국채10년선물",
    "453850.KS": "ACE 미국30년국채액티브(H)",
    "304660.KS": "KODEX 미국30년국채울트라선물(H)",
    "132030.KS": "KODEX 골드선물(H)",
    "411060.KS": "ACE KRX금현물",
    "144600.KS": "KODEX 은선물(H)",
    "138910.KS": "KODEX 구리선물(H)",
    "219480.KS": "KODEX 미국S&P500선물(H)",
    "360750.KS": "TIGER 미국S&P500",
    "379800.KS": "KODEX 미국S&P500",
    "133690.KS": "TIGER 미국나스닥100",
    "379810.KS": "KODEX 미국나스닥100",
    "069500.KS": "KODEX 200",
    "241180.KS": "TIGER 일본니케이225",
    "458730.KS": "TIGER 미국배당다우존스",
    "381170.KS": "TIGER 미국테크TOP10 INDXX",
    "472160.KS": "TIGER 미국테크TOP10INDXX(H)",
    "381180.KS": "TIGER 미국필라델피아반도체나스닥",
}


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


def latest_row(rows: list[dict[str, str]]) -> dict[str, str]:
    return rows[-1] if rows else {}


def money(value: float | int | None) -> str:
    if value is None:
        return "NA"
    return f"{int(round(float(value))):,}원"


def pct(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:.1%}"


def round_to_increment(value: float, increment: int) -> int:
    if increment <= 0:
        return int(round(value))
    return int(math.floor(value / increment + 0.5) * increment)


def allocation_from_decision(decision: dict[str, str]) -> dict[str, int]:
    return {asset: parse_int(decision.get(f"{asset}_amount")) for asset, _label in ASSETS}


def target_shares(allocation: dict[str, int]) -> dict[str, float]:
    total = sum(allocation.values()) or 1
    return {asset: allocation[asset] / total for asset, _label in ASSETS}


def selected_variant(decision: dict[str, str], scenario_rows: list[dict[str, str]]) -> dict[str, str]:
    recommended = decision.get("recommended_variant", "")
    for row in scenario_rows:
        if row.get("scenario_slug") == "baseline" and row.get("variant") == recommended:
            return row
    for row in scenario_rows:
        if row.get("scenario_slug") == "baseline":
            return row
    return {}


def symbol_map(variant: dict[str, str]) -> dict[str, str]:
    return {asset: variant.get(f"{asset}_symbol", "") for asset, _label in ASSETS}


def holding_value(row: dict[str, str]) -> float:
    explicit = parse_float(row.get("market_value_krw"))
    if explicit is not None:
        return explicit
    shares = parse_float(row.get("shares")) or 0.0
    price = parse_float(row.get("price_krw")) or 0.0
    return shares * price


def load_holdings(rows: list[dict[str, str]], symbols: dict[str, str]) -> dict[str, dict[str, Any]]:
    holdings: dict[str, dict[str, Any]] = {}
    for asset, label in ASSETS:
        symbol = symbols.get(asset, "")
        holdings[asset] = {
            "asset": asset,
            "asset_label": label,
            "symbol": symbol,
            "label": SYMBOL_LABELS.get(symbol, symbol),
            "shares": 0.0,
            "price_krw": None,
            "market_value_krw": 0.0,
        }
    for row in rows:
        asset = row.get("asset", "").strip()
        if asset not in holdings:
            continue
        value = holding_value(row)
        shares = parse_float(row.get("shares")) or 0.0
        price = parse_float(row.get("price_krw"))
        if row.get("symbol"):
            holdings[asset]["symbol"] = row.get("symbol", "")
        if row.get("label"):
            holdings[asset]["label"] = row.get("label", "")
        holdings[asset]["shares"] += shares
        holdings[asset]["market_value_krw"] += value
        if price is not None:
            holdings[asset]["price_krw"] = price
    return holdings


def allocate_buys(
    target_rows: list[dict[str, Any]],
    contribution_krw: int,
    increment_krw: int,
) -> dict[str, int]:
    positive_gaps = {row["asset"]: max(float(row["gap_krw"]), 0.0) for row in target_rows}
    gap_total = sum(positive_gaps.values())
    if gap_total > 0:
        raw = {asset: contribution_krw * gap / gap_total for asset, gap in positive_gaps.items()}
    else:
        raw = {row["asset"]: contribution_krw * float(row["target_share"]) for row in target_rows}

    orders = {asset: max(0, round_to_increment(value, increment_krw)) for asset, value in raw.items()}
    while sum(orders.values()) > contribution_krw and any(value > 0 for value in orders.values()):
        target = max(orders, key=orders.get)
        orders[target] = max(0, orders[target] - increment_krw)
    while contribution_krw - sum(orders.values()) >= increment_krw:
        underweights = {
            row["asset"]: float(row["target_value_after_contribution_krw"]) - float(row["current_value_krw"]) - orders[row["asset"]]
            for row in target_rows
        }
        target = max(underweights, key=underweights.get)
        if underweights[target] <= 0:
            target = max(target_rows, key=lambda row: float(row["target_share"]))["asset"]
        orders[target] += increment_krw
    return orders


def build_targets_and_orders(
    decision: dict[str, str],
    variant: dict[str, str],
    holding_rows: list[dict[str, str]],
    contribution_krw: int = DEFAULT_MONTHLY_CONTRIBUTION_KRW,
    increment_krw: int = DEFAULT_INCREMENT_KRW,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    allocation = allocation_from_decision(decision)
    shares = target_shares(allocation)
    symbols = symbol_map(variant)
    holdings = load_holdings(holding_rows, symbols)
    current_total = sum(float(holdings[asset]["market_value_krw"]) for asset, _label in ASSETS)
    target_total = current_total + contribution_krw

    target_rows: list[dict[str, Any]] = []
    for asset, label in ASSETS:
        holding = holdings[asset]
        current = float(holding["market_value_krw"])
        target_value = target_total * shares[asset]
        target_rows.append(
            {
                "asset": asset,
                "asset_label": label,
                "symbol": holding["symbol"],
                "label": holding["label"],
                "current_value_krw": round(current),
                "target_share": shares[asset],
                "target_value_after_contribution_krw": round(target_value),
                "gap_krw": round(target_value - current),
                "current_share_before_contribution": (current / current_total) if current_total else 0.0,
                "target_allocation_manwon": allocation[asset],
                "shares": round(float(holding["shares"]), 6),
                "price_krw": holding["price_krw"] if holding["price_krw"] is not None else "",
            }
        )

    buy_budgets = allocate_buys(target_rows, contribution_krw, increment_krw)
    order_rows: list[dict[str, Any]] = []
    for row in target_rows:
        asset = row["asset"]
        budget = buy_budgets[asset]
        price = parse_float(row.get("price_krw"))
        estimated_units = ""
        estimated_order_value = budget
        if price and price > 0:
            units = int(math.floor(budget / price))
            estimated_units = units
            estimated_order_value = round(units * price)
        order_rows.append(
            {
                "asset": asset,
                "asset_label": row["asset_label"],
                "symbol": row["symbol"],
                "label": row["label"],
                "action": "BUY" if estimated_order_value > 0 else "HOLD",
                "order_budget_krw": budget,
                "estimated_units": estimated_units,
                "estimated_order_value_krw": estimated_order_value,
                "target_share": row["target_share"],
                "current_value_krw": row["current_value_krw"],
                "target_value_after_contribution_krw": row["target_value_after_contribution_krw"],
                "gap_krw": row["gap_krw"],
            }
        )

    summary = {
        "generated_at": datetime.now().replace(microsecond=0).isoformat(),
        "report_date": decision.get("report_date", ""),
        "action_level": decision.get("action_level", ""),
        "risk_posture": decision.get("risk_posture", ""),
        "decision_confidence": decision.get("decision_confidence", ""),
        "recommended_variant": decision.get("recommended_variant", ""),
        "recommended_variant_title": decision.get("recommended_variant_title", ""),
        "monthly_contribution_krw": contribution_krw,
        "order_increment_krw": increment_krw,
        "current_total_krw": round(current_total),
        "target_total_after_contribution_krw": round(target_total),
        "planned_order_value_krw": sum(int(row["estimated_order_value_krw"]) for row in order_rows),
        "unallocated_cash_krw": contribution_krw - sum(int(row["estimated_order_value_krw"]) for row in order_rows),
    }
    return target_rows, order_rows, summary


def csv_value(value: Any) -> Any:
    if isinstance(value, float):
        return "" if math.isnan(value) else round(value, 8)
    if value is None:
        return ""
    return value


def render_markdown(summary: dict[str, Any], orders: list[dict[str, Any]], targets: list[dict[str, Any]]) -> str:
    lines = [
        "# Rebalance Orders",
        "",
        f"Generated at: {summary['generated_at']}",
        f"Report date: {summary['report_date']}",
        "",
        "## Decision Context",
        f"- Action level: {summary['action_level']}",
        f"- Risk posture: {summary['risk_posture']}",
        f"- Confidence: {summary['decision_confidence']}",
        f"- ETF variant: {summary['recommended_variant_title']} ({summary['recommended_variant']})",
        f"- Monthly contribution: {money(summary['monthly_contribution_krw'])}",
        f"- Current portfolio value: {money(summary['current_total_krw'])}",
        f"- Planned order value: {money(summary['planned_order_value_krw'])}",
        f"- Unallocated cash: {money(summary['unallocated_cash_krw'])}",
        "",
        "## Order Ticket",
        "| Action | Asset | Symbol | Budget | Est. units | Est. value | Target |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in orders:
        lines.append(
            f"| {row['action']} | {row['asset_label']} | {row['symbol']} | {money(row['order_budget_krw'])} | {row['estimated_units']} | {money(row['estimated_order_value_krw'])} | {pct(row['target_share'])} |"
        )
    lines.extend(["", "## Target State", "| Asset | Current | Target after contribution | Gap | Target share |", "|---|---:|---:|---:|---:|"])
    for row in targets:
        lines.append(
            f"| {row['asset_label']} | {money(row['current_value_krw'])} | {money(row['target_value_after_contribution_krw'])} | {money(row['gap_krw'])} | {pct(row['target_share'])} |"
        )
    return "\n".join(lines) + "\n"


def render_html(summary: dict[str, Any], orders: list[dict[str, Any]], targets: list[dict[str, Any]]) -> str:
    cards = [
        ("Action", summary["action_level"]),
        ("ETF Variant", summary["recommended_variant_title"]),
        ("Contribution", money(summary["monthly_contribution_krw"])),
        ("Unallocated", money(summary["unallocated_cash_krw"])),
    ]
    card_html = "".join(
        f"<div class=\"card\"><div class=\"label\">{escape(label)}</div><div class=\"value\">{escape(str(value))}</div></div>"
        for label, value in cards
    )
    order_html = "".join(
        "<tr>"
        f"<td><span class=\"pill\">{escape(str(row['action']))}</span></td>"
        f"<td><strong>{escape(str(row['asset_label']))}</strong><div class=\"subtle\">{escape(str(row['label']))}</div></td>"
        f"<td>{escape(str(row['symbol']))}</td>"
        f"<td>{money(row['order_budget_krw'])}</td>"
        f"<td>{escape(str(row['estimated_units']))}</td>"
        f"<td>{money(row['estimated_order_value_krw'])}</td>"
        f"<td>{pct(row['target_share'])}</td>"
        "</tr>"
        for row in orders
    )
    target_html = "".join(
        "<tr>"
        f"<td>{escape(str(row['asset_label']))}</td>"
        f"<td>{money(row['current_value_krw'])}</td>"
        f"<td>{pct(row['current_share_before_contribution'])}</td>"
        f"<td>{money(row['target_value_after_contribution_krw'])}</td>"
        f"<td>{money(row['gap_krw'])}</td>"
        f"<td>{pct(row['target_share'])}</td>"
        "</tr>"
        for row in targets
    )
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Rebalance Orders</title>
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
    .pill {{ display: inline-block; border: 1px solid var(--line); border-radius: 999px; padding: 3px 8px; font-weight: 700; color: var(--accent); }}
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
      <a href="decision_engine.html">Back to decision engine</a>
      <h1>Rebalance Orders</h1>
      <div class="subtle">Generated {escape(str(summary['generated_at']))} / Report {escape(str(summary['report_date']))}</div>
    </div>
    <div class="subtle"><a href="http://127.0.0.1:8765">Edit holdings</a> / <a href="rebalance_orders_latest.md">Markdown</a> / <a href="etf_universe.html">ETF universe</a> / <a href="sector_dashboard.html">Sector dashboard</a></div>
  </div>
  <section class="cards">{card_html}</section>
  <div class="note">Run <code>python scripts/portfolio_input_server.py</code> to edit holdings in a browser. If prices are filled, estimated units are calculated; otherwise the table shows KRW order budgets.</div>
  <section class="panel">
    <h2>Order Ticket</h2>
    <div class="panel-body"><table><thead><tr><th>Action</th><th>Asset</th><th>Symbol</th><th>Budget</th><th>Est. units</th><th>Est. value</th><th>Target</th></tr></thead><tbody>{order_html}</tbody></table></div>
  </section>
  <section class="panel">
    <h2>Target State</h2>
    <div class="panel-body"><table><thead><tr><th>Asset</th><th>Current</th><th>Current share</th><th>Target after contribution</th><th>Gap</th><th>Target share</th></tr></thead><tbody>{target_html}</tbody></table></div>
  </section>
</div>
</body>
</html>
"""


def order_fieldnames() -> list[str]:
    return [
        "asset",
        "asset_label",
        "symbol",
        "label",
        "action",
        "order_budget_krw",
        "estimated_units",
        "estimated_order_value_krw",
        "target_share",
        "current_value_krw",
        "target_value_after_contribution_krw",
        "gap_krw",
    ]


def target_fieldnames() -> list[str]:
    return [
        "asset",
        "asset_label",
        "symbol",
        "label",
        "current_value_krw",
        "target_share",
        "target_value_after_contribution_krw",
        "gap_krw",
        "current_share_before_contribution",
        "target_allocation_manwon",
        "shares",
        "price_krw",
    ]


def write_rebalance_orders(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    decision = latest_row(read_csv(Path(args.decision)))
    scenario_rows = read_csv(Path(args.scenario_etf))
    variant = selected_variant(decision, scenario_rows)
    holdings = read_csv(Path(args.holdings))
    targets, orders, summary = build_targets_and_orders(
        decision,
        variant,
        holdings,
        parse_int(args.monthly_contribution_krw),
        parse_int(args.increment_krw),
    )

    html = Path(args.html)
    markdown = Path(args.markdown)
    order_csv = Path(args.order_csv)
    target_csv = Path(args.target_csv)
    html.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    html.write_text(render_html(summary, orders, targets), encoding="utf-8")
    markdown.write_text(render_markdown(summary, orders, targets), encoding="utf-8")
    write_csv(order_csv, [{key: csv_value(row.get(key)) for key in order_fieldnames()} for row in orders], order_fieldnames())
    write_csv(target_csv, [{key: csv_value(row.get(key)) for key in target_fieldnames()} for row in targets], target_fieldnames())
    return html, markdown, order_csv, target_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate buy-only rebalance order guidance.")
    parser.add_argument("--decision", default=str(DEFAULT_DECISION))
    parser.add_argument("--scenario-etf", default=str(DEFAULT_SCENARIO_ETF))
    parser.add_argument("--holdings", default=str(DEFAULT_HOLDINGS))
    parser.add_argument("--html", default=str(DEFAULT_HTML))
    parser.add_argument("--markdown", default=str(DEFAULT_MD))
    parser.add_argument("--order-csv", default=str(DEFAULT_ORDER_CSV))
    parser.add_argument("--target-csv", default=str(DEFAULT_TARGET_CSV))
    parser.add_argument("--monthly-contribution-krw", default=str(DEFAULT_MONTHLY_CONTRIBUTION_KRW))
    parser.add_argument("--increment-krw", default=str(DEFAULT_INCREMENT_KRW))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    html, markdown, order_csv, target_csv = write_rebalance_orders(args)
    print(f"Generated rebalance orders HTML: {html}")
    print(f"Generated rebalance orders markdown: {markdown}")
    print(f"Generated rebalance order CSV: {order_csv}")
    print(f"Generated portfolio target CSV: {target_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
