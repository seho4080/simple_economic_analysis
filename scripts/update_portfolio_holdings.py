#!/usr/bin/env python3
"""Interactively update current portfolio holdings and rebuild rebalance orders."""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import generate_rebalance_orders as rebalance


DEFAULT_HOLDINGS = Path("config/portfolio_holdings.csv")
DEFAULT_DECISION = Path("data/processed/macro/decision_engine_latest.csv")
DEFAULT_SCENARIO_ETF = Path("data/processed/backtests/scenario_etf_backtests/scenario_etf_summary.csv")

FIELDNAMES = ["account", "asset", "symbol", "label", "shares", "price_krw", "market_value_krw", "notes"]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in FIELDNAMES} for row in rows])


def parse_float(value: str | float | int | None) -> float | None:
    return rebalance.parse_float(value)


def format_number(value: float | int | str | None) -> str:
    parsed = parse_float(value)
    if parsed is None:
        return ""
    if abs(parsed - round(parsed)) < 1e-9:
        return str(int(round(parsed)))
    return f"{parsed:.6f}".rstrip("0").rstrip(".")


def normalize_number(value: str | None) -> str:
    return format_number(value)


def existing_by_asset(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        asset = row.get("asset", "").strip()
        if asset:
            result[asset] = row
    return result


def defaults_from_decision(decision_path: Path, scenario_etf_path: Path) -> dict[str, dict[str, str]]:
    decision = rebalance.latest_row(read_csv(decision_path))
    variant = rebalance.selected_variant(decision, read_csv(scenario_etf_path))
    symbols = rebalance.symbol_map(variant)
    defaults: dict[str, dict[str, str]] = {}
    for asset, label in rebalance.ASSETS:
        symbol = symbols.get(asset, "")
        defaults[asset] = {
            "account": "isa",
            "asset": asset,
            "symbol": symbol,
            "label": rebalance.SYMBOL_LABELS.get(symbol, label),
            "shares": "0",
            "price_krw": "",
            "market_value_krw": "0",
            "notes": "Updated by scripts/update_portfolio_holdings.py",
        }
    return defaults


def merge_defaults(
    existing_rows: list[dict[str, str]],
    decision_path: Path = DEFAULT_DECISION,
    scenario_etf_path: Path = DEFAULT_SCENARIO_ETF,
) -> list[dict[str, str]]:
    defaults = defaults_from_decision(decision_path, scenario_etf_path)
    existing = existing_by_asset(existing_rows)
    rows: list[dict[str, str]] = []
    for asset, _label in rebalance.ASSETS:
        base = defaults[asset].copy()
        if asset in existing:
            for key in FIELDNAMES:
                value = existing[asset].get(key, "")
                if value != "":
                    base[key] = value
        rows.append(base)
    return rows


def calculated_market_value(shares: str, price_krw: str) -> str:
    shares_value = parse_float(shares)
    price_value = parse_float(price_krw)
    if shares_value is None or price_value is None:
        return ""
    return format_number(shares_value * price_value)


def prompt_value(
    prompt: Callable[[str], str],
    label: str,
    current: str,
    numeric: bool = False,
) -> str:
    suffix = f" [{current}]" if current not in {"", None} else ""
    while True:
        value = prompt(f"{label}{suffix}: ").strip()
        if value == "":
            return current
        if not numeric:
            return value
        normalized = normalize_number(value)
        if normalized != "":
            return normalized
        print("숫자로 입력해주세요. 예: 123000 또는 12.5")


def prompt_market_value(
    prompt: Callable[[str], str],
    current: str,
    shares: str,
    price_krw: str,
) -> str:
    auto_value = calculated_market_value(shares, price_krw)
    suffix = f" [{current}]" if current else ""
    hint = f" (Enter=auto {auto_value})" if auto_value and current in {"", "0"} else ""
    while True:
        value = prompt(f"market_value_krw{suffix}{hint}: ").strip()
        if value == "":
            if auto_value and current in {"", "0"}:
                return auto_value
            return current
        normalized = normalize_number(value)
        if normalized != "":
            return normalized
        print("숫자로 입력해주세요. 예: 123000 또는 12.5")


def interactive_update(
    rows: list[dict[str, str]],
    prompt: Callable[[str], str] = input,
) -> list[dict[str, str]]:
    updated: list[dict[str, str]] = []
    print("현재 보유 포트폴리오를 입력합니다. Enter를 누르면 기존 값을 유지합니다.")
    print("market_value_krw를 비워두면 shares x price_krw로 자동 계산합니다.")
    for row in rows:
        print(f"\n[{row['asset']}] {row.get('label', '')} ({row.get('symbol', '')})")
        next_row = row.copy()
        next_row["account"] = prompt_value(prompt, "account", next_row.get("account", "isa"))
        next_row["symbol"] = prompt_value(prompt, "symbol", next_row.get("symbol", ""))
        next_row["label"] = prompt_value(prompt, "label", next_row.get("label", ""))
        next_row["shares"] = prompt_value(prompt, "shares", format_number(next_row.get("shares", "")), numeric=True)
        next_row["price_krw"] = prompt_value(prompt, "price_krw", format_number(next_row.get("price_krw", "")), numeric=True)
        current_market = format_number(next_row.get("market_value_krw", ""))
        entered_market = prompt_market_value(prompt, current_market, next_row.get("shares", ""), next_row.get("price_krw", ""))
        next_row["market_value_krw"] = entered_market if entered_market else "0"
        next_row["notes"] = prompt_value(prompt, "notes", next_row.get("notes", ""))
        updated.append({key: next_row.get(key, "") for key in FIELDNAMES})
    return updated


def rebuild_orders(extra_args: list[str] | None = None) -> int:
    command = [sys.executable, "scripts/generate_rebalance_orders.py"]
    if extra_args:
        command.extend(extra_args)
    completed = subprocess.run(command, check=False)
    return completed.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Interactively update portfolio holdings CSV.")
    parser.add_argument("--holdings", default=str(DEFAULT_HOLDINGS))
    parser.add_argument("--decision", default=str(DEFAULT_DECISION))
    parser.add_argument("--scenario-etf", default=str(DEFAULT_SCENARIO_ETF))
    parser.add_argument("--no-rebuild", action="store_true", help="Only update the holdings CSV; do not rebuild orders.")
    parser.add_argument(
        "--print-template",
        action="store_true",
        help="Write missing/default rows without prompting. Useful for first setup.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    holdings_path = Path(args.holdings)
    rows = merge_defaults(read_csv(holdings_path), Path(args.decision), Path(args.scenario_etf))
    if not args.print_template:
        rows = interactive_update(rows)
    write_csv(holdings_path, rows)
    print(f"Updated holdings: {holdings_path}")
    if args.no_rebuild:
        return 0
    returncode = rebuild_orders()
    if returncode != 0:
        print(f"Failed to rebuild rebalance orders. returncode={returncode}")
        return returncode
    print("Rebuilt rebalance orders: reports/rebalance_orders.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
