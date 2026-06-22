#!/usr/bin/env python3
"""Rank an individual-stock watchlist against the latest macro decision context."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any


DEFAULT_WATCHLIST = Path("config/stock_watchlist.csv")
DEFAULT_DECISION = Path("data/processed/macro/decision_engine_latest.csv")
DEFAULT_RISK_HISTORY = Path("data/processed/macro/risk_score_history.csv")
DEFAULT_OUTPUT_CSV = Path("data/processed/portfolio/stock_watchlist_ranked.csv")
DEFAULT_PRICE_CSV = Path("data/processed/portfolio/stock_prices_latest.csv")
DEFAULT_HISTORY_CSV = Path("data/processed/portfolio/stock_price_history.csv")
DEFAULT_RAW_DIR = Path("data/raw/yahoo_stock_watchlist")
DEFAULT_HTML = Path("reports/stock_watchlist.html")
DEFAULT_PRICE_RANGE_DAYS = 3653
USER_AGENT = "stock-economic-indicators/0.3"
RETURN_HORIZONS = {
    "return_1m": 31,
    "return_3m": 92,
    "return_6m": 183,
    "return_1y": 366,
    "return_3y": 366 * 3,
    "return_5y": 366 * 5,
    "return_10y": 3650,
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
class StockCandidate:
    watch_rank: int
    symbol: str
    label: str
    company_name: str
    market: str
    country: str
    sector: str
    industry: str
    style: str
    risk_tags: tuple[str, ...]
    macro_fit: tuple[str, ...]
    watch_reason: str
    source_url: str


@dataclass(frozen=True)
class StockPrice:
    symbol: str
    status: str
    currency: str
    latest_date: str
    latest_price: float | None
    previous_date: str
    previous_close: float | None
    price_change: float | None
    price_change_pct: float | None
    fetched_at: str
    source_url: str
    message: str = ""
    history_start: str = ""
    history_end: str = ""
    history_rows: int = 0
    return_1m: float | None = None
    return_3m: float | None = None
    return_6m: float | None = None
    return_1y: float | None = None
    return_3y: float | None = None
    return_5y: float | None = None
    return_10y: float | None = None
    max_drawdown: float | None = None


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


def latest_row(rows: list[dict[str, str]]) -> dict[str, str]:
    return rows[-1] if rows else {}


def date_to_timestamp(value: date) -> int:
    return int(datetime(value.year, value.month, value.day, tzinfo=timezone.utc).timestamp())


def safe_symbol_filename(symbol: str) -> str:
    return symbol.replace("=", "_").replace("^", "_").replace("/", "_")


def yahoo_chart_url(symbol: str, start: date, end: date) -> str:
    quoted = urllib.parse.quote(symbol, safe="")
    return (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{quoted}"
        f"?period1={date_to_timestamp(start)}"
        f"&period2={date_to_timestamp(end + timedelta(days=1))}"
        "&interval=1d&events=history&includeAdjustedClose=true"
    )


def yahoo_quote_url(symbol: str) -> str:
    return f"https://finance.yahoo.com/quote/{urllib.parse.quote(symbol, safe='')}/"


def stock_price_to_row(price: StockPrice) -> dict[str, Any]:
    row = {
        "symbol": price.symbol,
        "status": price.status,
        "currency": price.currency,
        "latest_date": price.latest_date,
        "latest_price": price.latest_price if price.latest_price is not None else "",
        "previous_date": price.previous_date,
        "previous_close": price.previous_close if price.previous_close is not None else "",
        "price_change": price.price_change if price.price_change is not None else "",
        "price_change_pct": price.price_change_pct if price.price_change_pct is not None else "",
        "fetched_at": price.fetched_at,
        "source_url": price.source_url,
        "message": price.message,
        "history_start": price.history_start,
        "history_end": price.history_end,
        "history_rows": price.history_rows,
        "max_drawdown": price.max_drawdown if price.max_drawdown is not None else "",
    }
    for field in RETURN_HORIZONS:
        row[field] = getattr(price, field) if getattr(price, field) is not None else ""
    return row


def price_fieldnames() -> list[str]:
    return [
        "symbol",
        "status",
        "currency",
        "latest_date",
        "latest_price",
        "previous_date",
        "previous_close",
        "price_change",
        "price_change_pct",
        "fetched_at",
        "source_url",
        "message",
        "history_start",
        "history_end",
        "history_rows",
        "return_1m",
        "return_3m",
        "return_6m",
        "return_1y",
        "return_3y",
        "return_5y",
        "return_10y",
        "max_drawdown",
    ]


def history_fieldnames() -> list[str]:
    return ["symbol", "date", "close", "currency", "fetched_at", "source_url"]


def extract_price_points(payload: dict[str, Any]) -> tuple[str, list[tuple[date, float]], str]:
    chart = payload.get("chart", {})
    if chart.get("error"):
        return "", [], str(chart["error"])
    result = (chart.get("result") or [None])[0]
    if not result:
        return "", [], "No Yahoo chart result"

    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quote = (indicators.get("quote") or [{}])[0]
    closes = quote.get("close") or []

    points: list[tuple[date, float]] = []
    for timestamp, close in zip(timestamps, closes):
        value = parse_float(close)
        if value is None:
            continue
        points.append((datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date(), value))
    points.sort(key=lambda item: item[0])
    return str(meta.get("currency", "")), points, ""


def value_on_or_before(points: list[tuple[date, float]], target: date) -> tuple[date, float] | None:
    candidate: tuple[date, float] | None = None
    for point_date, value in points:
        if point_date <= target:
            candidate = (point_date, value)
        else:
            break
    return candidate


def trailing_return(points: list[tuple[date, float]], latest_date: date, latest_price: float, days: int) -> float | None:
    prior = value_on_or_before(points, latest_date - timedelta(days=days))
    if prior is None and points:
        first = points[0]
        if (latest_date - first[0]).days >= days - 14:
            prior = first
    if prior is None or prior[1] == 0:
        return None
    return latest_price / prior[1] - 1.0


def max_drawdown(points: list[tuple[date, float]]) -> float | None:
    if not points:
        return None
    peak = 0.0
    drawdown = 0.0
    for _point_date, value in points:
        peak = max(peak, value)
        if peak > 0:
            drawdown = min(drawdown, value / peak - 1.0)
    return drawdown


def history_rows_from_points(
    symbol: str,
    currency: str,
    points: list[tuple[date, float]],
    fetched_at: str,
    source_url: str,
) -> list[dict[str, Any]]:
    return [
        {
            "symbol": symbol,
            "date": point_date.isoformat(),
            "close": close,
            "currency": currency,
            "fetched_at": fetched_at,
            "source_url": source_url,
        }
        for point_date, close in points
    ]


def history_rows_from_payload(symbol: str, payload: dict[str, Any], fetched_at: str, source_url: str) -> list[dict[str, Any]]:
    currency, points, _message = extract_price_points(payload)
    return history_rows_from_points(symbol, currency, points, fetched_at, source_url)


def parse_stock_price_payload(symbol: str, payload: dict[str, Any], source_url: str, fetched_at: str) -> StockPrice:
    chart = payload.get("chart", {})
    if chart.get("error"):
        return StockPrice(symbol, "error", "", "", None, "", None, None, None, fetched_at, source_url, str(chart["error"]))

    currency, points, message = extract_price_points(payload)
    if not points:
        return StockPrice(symbol, "missing", currency, "", None, "", None, None, None, fetched_at, source_url, message or "No close prices")

    latest_date, latest_price = points[-1]
    previous_date = ""
    previous_close = None
    price_change = None
    price_change_pct = None
    if len(points) >= 2:
        prev_date, prev_value = points[-2]
        previous_date = prev_date.isoformat()
        previous_close = prev_value
        price_change = latest_price - prev_value
        price_change_pct = price_change / prev_value if prev_value else None
    returns = {
        field: trailing_return(points, latest_date, latest_price, days)
        for field, days in RETURN_HORIZONS.items()
    }

    return StockPrice(
        symbol=symbol,
        status="ok",
        currency=currency,
        latest_date=latest_date.isoformat(),
        latest_price=latest_price,
        previous_date=previous_date,
        previous_close=previous_close,
        price_change=price_change,
        price_change_pct=price_change_pct,
        fetched_at=fetched_at,
        source_url=source_url,
        history_start=points[0][0].isoformat(),
        history_end=points[-1][0].isoformat(),
        history_rows=len(points),
        max_drawdown=max_drawdown(points),
        **returns,
    )


def fetch_stock_price(symbol: str, raw_dir: Path, range_days: int = DEFAULT_PRICE_RANGE_DAYS) -> StockPrice:
    end = date.today()
    start = end - timedelta(days=max(range_days, 7))
    source_url = yahoo_quote_url(symbol)
    fetched_at = datetime.now().replace(microsecond=0).isoformat()
    url = yahoo_chart_url(symbol, start, end)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{safe_symbol_filename(symbol)}.json").write_bytes(raw)
    return parse_stock_price_payload(symbol, json.loads(raw.decode("utf-8")), source_url, fetched_at)


def fetch_price_outputs(
    candidates: list[StockCandidate],
    raw_dir: Path,
    range_days: int = DEFAULT_PRICE_RANGE_DAYS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    price_rows: list[dict[str, Any]] = []
    history_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        fetched_at = datetime.now().replace(microsecond=0).isoformat()
        try:
            price = fetch_stock_price(candidate.symbol, raw_dir, range_days)
            raw_path = raw_dir / f"{safe_symbol_filename(candidate.symbol)}.json"
            if raw_path.exists():
                payload = json.loads(raw_path.read_text(encoding="utf-8"))
                history_rows.extend(history_rows_from_payload(candidate.symbol, payload, price.fetched_at, price.source_url))
        except Exception as exc:
            price = StockPrice(
                symbol=candidate.symbol,
                status="error",
                currency="",
                latest_date="",
                latest_price=None,
                previous_date="",
                previous_close=None,
                price_change=None,
                price_change_pct=None,
                fetched_at=fetched_at,
                source_url=yahoo_quote_url(candidate.symbol),
                message=str(exc),
            )
        price_rows.append(stock_price_to_row(price))
    return price_rows, history_rows


def fetch_price_rows(candidates: list[StockCandidate], raw_dir: Path, range_days: int = DEFAULT_PRICE_RANGE_DAYS) -> list[dict[str, Any]]:
    return fetch_price_outputs(candidates, raw_dir, range_days)[0]


def price_map_from_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("symbol", "")): row for row in rows if row.get("symbol")}


def load_watchlist(path: Path) -> list[StockCandidate]:
    candidates: list[StockCandidate] = []
    for row in read_csv(path):
        if not row.get("symbol"):
            continue
        candidates.append(
            StockCandidate(
                watch_rank=parse_int(row.get("watch_rank")),
                symbol=(row.get("symbol") or "").strip(),
                label=(row.get("label") or "").strip(),
                company_name=(row.get("company_name") or "").strip(),
                market=(row.get("market") or "").strip(),
                country=(row.get("country") or "").strip(),
                sector=(row.get("sector") or "").strip(),
                industry=(row.get("industry") or "").strip(),
                style=(row.get("style") or "").strip(),
                risk_tags=split_list(row.get("risk_tags")),
                macro_fit=split_list(row.get("macro_fit")),
                watch_reason=(row.get("watch_reason") or "").strip(),
                source_url=(row.get("source_url") or "").strip(),
            )
        )
    return candidates


def build_context(decision: dict[str, str], risk_row: dict[str, str]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now().replace(microsecond=0).isoformat(),
        "report_date": decision.get("report_date") or risk_row.get("report_date") or "",
        "action_level": decision.get("action_level") or "Proceed with baseline accumulation",
        "risk_posture": decision.get("risk_posture") or "Balanced",
        "decision_confidence": decision.get("decision_confidence") or "",
        "current_regime": decision.get("current_regime") or risk_row.get("current_regime") or "",
        "risk_scores": {field: parse_float(risk_row.get(field)) or 0.0 for field in RISK_FIELDS},
    }


def _add(score: float, points: float, reason: str, reasons: list[str]) -> float:
    if points:
        reasons.append(f"{reason} ({points:+.0f})")
    return score + points


def score_candidate(candidate: StockCandidate, context: dict[str, Any]) -> tuple[float, list[str]]:
    tags = set(candidate.risk_tags)
    posture = str(context.get("risk_posture", "")).lower()
    action = str(context.get("action_level", "")).lower()
    fit_text = " ".join(candidate.macro_fit).lower()
    reasons: list[str] = []

    score = 45.0
    rank_bonus = max(0, 10 - candidate.watch_rank) * 2
    score = _add(score, rank_bonus, "watchlist rank", reasons)

    if posture and posture in fit_text:
        score = _add(score, 9, "posture match", reasons)
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
        if {"defensive", "consumer_staples", "healthcare", "quality", "dividend", "cash_flow"} & tags:
            score = _add(score, 12, "watch/defensive fit", reasons)
        if {"mega_cap", "software", "cloud", "global_revenue"} & tags:
            score = _add(score, 5, "quality scale", reasons)
        if {"high_beta", "semiconductor", "cyclical", "auto"} & tags:
            score = _add(score, -10, "watchlist beta penalty", reasons)
        if {"platform", "advertising", "growth"} & tags:
            score = _add(score, -3, "growth sensitivity", reasons)

    if "balanced" in posture or "baseline" in action:
        if {"quality", "mega_cap", "defensive", "dividend"} & tags:
            score = _add(score, 8, "core quality fit", reasons)
        if {"growth", "ai", "cloud", "software"} & tags:
            score = _add(score, 4, "growth option", reasons)

    if "inflation" in posture or "fx" in posture:
        if {"pricing_power", "consumer_staples", "healthcare"} & tags:
            score = _add(score, 8, "pricing power", reasons)
        if {"usd", "global_revenue", "exporter", "fx_sensitivity"} & tags:
            score = _add(score, 6, "FX exposure", reasons)

    risks = context.get("risk_scores", {})
    inflation = float(risks.get("inflation_risk", 0.0))
    fx = float(risks.get("fx_risk", 0.0))
    credit = float(risks.get("credit_stress_risk", 0.0))
    growth = float(risks.get("growth_slowdown_risk", 0.0))
    market = float(risks.get("market_stress_risk", 0.0))
    liquidity = float(risks.get("liquidity_bubble_risk", 0.0))

    if inflation >= 6 and {"pricing_power", "consumer_staples", "healthcare", "dividend"} & tags:
        score = _add(score, 7, "high inflation resilience", reasons)
    if fx >= 6 and {"usd", "global_revenue", "exporter"} & tags:
        score = _add(score, 6, "high FX fit", reasons)
    if max(credit, growth, market) >= 6:
        if {"defensive", "consumer_staples", "healthcare", "quality", "dividend"} & tags:
            score = _add(score, 9, "stress defense", reasons)
        if {"high_beta", "semiconductor", "auto", "cyclical", "advertising"} & tags:
            score = _add(score, -9, "stress beta penalty", reasons)
    if liquidity >= 6 and {"high_beta", "growth", "semiconductor", "ai"} & tags:
        score = _add(score, -6, "liquidity risk penalty", reasons)

    return max(0.0, min(100.0, round(score, 1))), reasons[:5]


def recommendation_band(score: float) -> str:
    if score >= 76:
        return "High fit"
    if score >= 62:
        return "Good fit"
    if score >= 48:
        return "Watchlist"
    return "Speculative"


def candidate_to_row(
    candidate: StockCandidate,
    score: float,
    reasons: list[str],
    rank: int,
    price_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    price = price_row or {}
    return {
        "rank": rank,
        "score": score,
        "recommendation_band": recommendation_band(score),
        "watch_rank": candidate.watch_rank,
        "symbol": candidate.symbol,
        "label": candidate.label,
        "company_name": candidate.company_name,
        "market": candidate.market,
        "country": candidate.country,
        "sector": candidate.sector,
        "industry": candidate.industry,
        "style": candidate.style,
        "score_drivers": "; ".join(reasons),
        "risk_tags": "; ".join(candidate.risk_tags),
        "macro_fit": "; ".join(candidate.macro_fit),
        "watch_reason": candidate.watch_reason,
        "source_url": candidate.source_url,
        "price_status": price.get("status", ""),
        "currency": price.get("currency", ""),
        "latest_date": price.get("latest_date", ""),
        "latest_price": price.get("latest_price", ""),
        "previous_date": price.get("previous_date", ""),
        "previous_close": price.get("previous_close", ""),
        "price_change": price.get("price_change", ""),
        "price_change_pct": price.get("price_change_pct", ""),
        "price_fetched_at": price.get("fetched_at", ""),
        "price_source_url": price.get("source_url", ""),
        "price_message": price.get("message", ""),
        "history_start": price.get("history_start", ""),
        "history_end": price.get("history_end", ""),
        "history_rows": price.get("history_rows", ""),
        "return_1m": price.get("return_1m", ""),
        "return_3m": price.get("return_3m", ""),
        "return_6m": price.get("return_6m", ""),
        "return_1y": price.get("return_1y", ""),
        "return_3y": price.get("return_3y", ""),
        "return_5y": price.get("return_5y", ""),
        "return_10y": price.get("return_10y", ""),
        "max_drawdown": price.get("max_drawdown", ""),
    }


def rank_candidates(
    candidates: list[StockCandidate],
    context: dict[str, Any],
    price_rows: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    scored = []
    for candidate in candidates:
        score, reasons = score_candidate(candidate, context)
        scored.append((candidate, score, reasons))
    scored.sort(key=lambda item: (item[1], -item[0].watch_rank, item[0].symbol), reverse=True)
    prices = price_rows or {}
    return [
        candidate_to_row(candidate, score, reasons, rank, prices.get(candidate.symbol))
        for rank, (candidate, score, reasons) in enumerate(scored, start=1)
    ]


def output_fieldnames() -> list[str]:
    return [
        "rank",
        "score",
        "recommendation_band",
        "watch_rank",
        "symbol",
        "label",
        "company_name",
        "market",
        "country",
        "sector",
        "industry",
        "style",
        "score_drivers",
        "risk_tags",
        "macro_fit",
        "watch_reason",
        "source_url",
        "price_status",
        "currency",
        "latest_date",
        "latest_price",
        "previous_date",
        "previous_close",
        "price_change",
        "price_change_pct",
        "price_fetched_at",
        "price_source_url",
        "price_message",
        "history_start",
        "history_end",
        "history_rows",
        "return_1m",
        "return_3m",
        "return_6m",
        "return_1y",
        "return_3y",
        "return_5y",
        "return_10y",
        "max_drawdown",
    ]


def render_html(context: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    top = rows[0] if rows else {}
    latest_fetch = max((str(row.get("price_fetched_at", "")) for row in rows if row.get("price_fetched_at")), default="NA")
    history_start = min((str(row.get("history_start", "")) for row in rows if row.get("history_start")), default="NA")
    history_end = max((str(row.get("history_end", "")) for row in rows if row.get("history_end")), default="NA")
    payload = json.dumps({"context": context, "rows": rows}, ensure_ascii=False).replace("</", "<\\/")
    cards = [
        ("Action", context.get("action_level", "NA")),
        ("Posture", context.get("risk_posture", "NA")),
        ("Top Stock", f"{top.get('symbol', 'NA')} / {top.get('score', 'NA')}"),
        ("Price Refresh", latest_fetch),
        ("History", f"{history_start} ~ {history_end}"),
    ]
    card_html = "".join(
        f"<div class=\"card\"><div class=\"label\">{escape(label)}</div><div class=\"value\">{escape(str(value))}</div></div>"
        for label, value in cards
    )
    risk_html = "".join(
        f"<span><strong>{escape(label)}</strong> {float(context.get('risk_scores', {}).get(field, 0.0)):.1f}</span>"
        for field, label in RISK_FIELDS.items()
    )
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stock Watchlist</title>
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
    .subtle, .label {{ color: var(--muted); font-size: 12px; line-height: 1.45; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 16px; }}
    .card, .panel, .note {{ background: var(--surface); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); }}
    .card {{ padding: 13px 14px; min-height: 76px; }}
    .value {{ font-weight: 760; font-size: 20px; line-height: 1.2; margin-top: 4px; overflow-wrap: anywhere; }}
    .note {{ padding: 12px 14px; margin-bottom: 16px; }}
    .risk-strip {{ display: flex; gap: 8px 14px; flex-wrap: wrap; color: var(--muted); font-size: 12px; }}
    .panel {{ overflow: hidden; }}
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
    .delta.positive {{ color: var(--good); font-weight: 720; }}
    .delta.negative {{ color: #b42318; font-weight: 720; }}
    .price {{ font-weight: 720; font-variant-numeric: tabular-nums; }}
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
      <h1>Stock Watchlist</h1>
      <div class="subtle">Generated {escape(str(context.get('generated_at', '')))} / Report {escape(str(context.get('report_date', '')))}</div>
    </div>
    <div class="subtle"><a href="etf_universe.html">ETF universe</a> / <a href="rebalance_orders.html">Rebalance orders</a> / <a href="sector_dashboard.html">Sector dashboard</a></div>
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
        <input id="searchInput" type="search" placeholder="Search stock, tag, sector">
        <select id="countrySelect" aria-label="Filter country">
          <option value="all">All countries</option>
          <option value="United States">United States</option>
          <option value="Korea">Korea</option>
        </select>
        <select id="bandSelect" aria-label="Filter score band">
          <option value="all">All score bands</option>
          <option value="High fit">High fit</option>
          <option value="Good fit">Good fit</option>
          <option value="Watchlist">Watchlist</option>
          <option value="Speculative">Speculative</option>
        </select>
      </div>
    </div>
    <div class="panel-body" id="tableWrap"></div>
  </section>
</div>
<script id="stock-data" type="application/json">{payload}</script>
<script>
const DATA = JSON.parse(document.getElementById('stock-data').textContent);
const searchInput = document.getElementById('searchInput');
const countrySelect = document.getElementById('countrySelect');
const bandSelect = document.getElementById('bandSelect');

function esc(value) {{
  return String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
}}

function scoreClass(score) {{
  if (score >= 76) return 'score high';
  if (score >= 62) return 'score mid';
  return 'score low';
}}

function bandClass(band) {{
  if (band === 'High fit') return 'band high';
  if (band === 'Watchlist' || band === 'Speculative') return 'band watch';
  return 'band';
}}

function numberOrNull(value) {{
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}}

function formatPrice(value, currency) {{
  const parsed = numberOrNull(value);
  if (parsed === null) return 'NA';
  const digits = currency === 'KRW' ? 0 : 2;
  return `${{parsed.toLocaleString(undefined, {{ maximumFractionDigits: digits, minimumFractionDigits: digits }})}} ${{currency || ''}}`.trim();
}}

function formatPct(value) {{
  const parsed = numberOrNull(value);
  if (parsed === null) return 'NA';
  return `${{(parsed * 100).toFixed(2)}}%`;
}}

function formatReturn(value) {{
  const parsed = numberOrNull(value);
  if (parsed === null) return 'NA';
  const sign = parsed > 0 ? '+' : '';
  return `${{sign}}${{(parsed * 100).toFixed(1)}}%`;
}}

function formatChange(value, currency) {{
  const parsed = numberOrNull(value);
  if (parsed === null) return 'NA';
  const digits = currency === 'KRW' ? 0 : 2;
  const sign = parsed > 0 ? '+' : '';
  return `${{sign}}${{parsed.toLocaleString(undefined, {{ maximumFractionDigits: digits, minimumFractionDigits: digits }})}}`;
}}

function deltaClass(value) {{
  const parsed = numberOrNull(value);
  if (parsed === null || parsed === 0) return 'delta';
  return parsed > 0 ? 'delta positive' : 'delta negative';
}}

function matches(row, query) {{
  if (!query) return true;
  const haystack = [row.symbol, row.label, row.company_name, row.country, row.sector, row.industry, row.style, row.risk_tags, row.macro_fit, row.watch_reason, row.price_status].join(' ').toLowerCase();
  return haystack.includes(query.toLowerCase());
}}

function filteredRows() {{
  const query = searchInput.value.trim();
  const country = countrySelect.value;
  const band = bandSelect.value;
  return DATA.rows.filter(row => {{
    if (country !== 'all' && row.country !== country) return false;
    if (band !== 'all' && row.recommendation_band !== band) return false;
    return matches(row, query);
  }});
}}

function renderTable() {{
  const rows = filteredRows();
  document.getElementById('tableMeta').textContent = `${{rows.length}} of ${{DATA.rows.length}} stocks visible`;
  const wrap = document.getElementById('tableWrap');
  if (!rows.length) {{
    wrap.innerHTML = '<div class="empty">No stocks match the current filter.</div>';
    return;
  }}
  const html = rows.map(row => `
    <tr>
      <td class="rank">${{esc(row.rank)}}</td>
      <td><span class="${{scoreClass(Number(row.score))}}">${{esc(row.score)}}</span><div><span class="${{bandClass(row.recommendation_band)}}">${{esc(row.recommendation_band)}}</span></div></td>
      <td><strong><a href="${{esc(row.source_url)}}">${{esc(row.label)}}</a></strong><div class="tagline">${{esc(row.symbol)}} / ${{esc(row.company_name)}} / ${{esc(row.market)}}</div></td>
      <td>${{esc(row.country)}}<div class="tagline">${{esc(row.sector)}} / ${{esc(row.industry)}}</div></td>
      <td><span class="price">${{formatPrice(row.latest_price, row.currency)}}</span><div class="tagline">${{esc(row.latest_date || row.price_status || 'NA')}}</div></td>
      <td><span class="${{deltaClass(row.price_change)}}">${{formatChange(row.price_change, row.currency)}} / ${{formatPct(row.price_change_pct)}}</span><div class="tagline">prev ${{formatPrice(row.previous_close, row.currency)}}</div></td>
      <td>
        <span class="${{deltaClass(row.return_1y)}}">1Y ${{formatReturn(row.return_1y)}}</span>
        <div class="tagline">3Y ${{formatReturn(row.return_3y)}} / 5Y ${{formatReturn(row.return_5y)}}</div>
        <div class="tagline">10Y ${{formatReturn(row.return_10y)}} / MDD ${{formatReturn(row.max_drawdown)}}</div>
      </td>
      <td>${{esc(row.score_drivers)}}</td>
    </tr>
  `).join('');
  wrap.innerHTML = `
    <table>
      <thead>
        <tr>
          <th style="width: 6%">Rank</th>
          <th style="width: 11%">Score</th>
          <th style="width: 20%">Stock</th>
          <th style="width: 15%">Exposure</th>
          <th style="width: 13%">Price</th>
          <th style="width: 13%">1D</th>
          <th style="width: 19%">Performance</th>
          <th style="width: 19%">Score drivers</th>
        </tr>
      </thead>
      <tbody>${{html}}</tbody>
    </table>
  `;
}}

searchInput.addEventListener('input', renderTable);
countrySelect.addEventListener('change', renderTable);
bandSelect.addEventListener('change', renderTable);
renderTable();
</script>
</body>
</html>
"""


def write_stock_watchlist(args: argparse.Namespace) -> tuple[Path, Path]:
    candidates = load_watchlist(Path(args.watchlist))
    prices_csv = Path(args.prices_csv)
    history_csv = Path(args.history_csv)
    if args.skip_price_fetch:
        price_rows = read_csv(prices_csv)
    else:
        price_rows, history_rows = fetch_price_outputs(candidates, Path(args.raw_dir), parse_int(args.price_range_days, DEFAULT_PRICE_RANGE_DAYS))
        write_csv(prices_csv, price_rows, price_fieldnames())
        write_csv(history_csv, history_rows, history_fieldnames())

    context = build_context(
        latest_row(read_csv(Path(args.decision))),
        latest_row(read_csv(Path(args.risk_history))),
    )
    rows = rank_candidates(candidates, context, price_map_from_rows(price_rows))
    output_csv = Path(args.output_csv)
    html = Path(args.html)
    html.parent.mkdir(parents=True, exist_ok=True)
    write_csv(output_csv, rows, output_fieldnames())
    html.write_text(render_html(context, rows), encoding="utf-8")
    return output_csv, html


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rank individual stock watchlist candidates against the latest macro decision context.")
    parser.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST))
    parser.add_argument("--decision", default=str(DEFAULT_DECISION))
    parser.add_argument("--risk-history", default=str(DEFAULT_RISK_HISTORY))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--prices-csv", default=str(DEFAULT_PRICE_CSV))
    parser.add_argument("--history-csv", default=str(DEFAULT_HISTORY_CSV))
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--price-range-days", default=str(DEFAULT_PRICE_RANGE_DAYS))
    parser.add_argument("--skip-price-fetch", action="store_true", help="Use an existing prices CSV instead of fetching Yahoo prices.")
    parser.add_argument("--html", default=str(DEFAULT_HTML))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_csv, html = write_stock_watchlist(args)
    print(f"Generated stock watchlist CSV: {output_csv}")
    print(f"Generated stock watchlist HTML: {html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
