#!/usr/bin/env python3
"""Run a small local web form for editing portfolio holdings."""

from __future__ import annotations

import argparse
import html
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode

import generate_rebalance_orders as rebalance
import update_portfolio_holdings as holdings


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def number_value(value: object) -> str:
    return holdings.format_number(value)


def load_rows(path: Path) -> list[dict[str, str]]:
    return holdings.merge_defaults(holdings.read_csv(path))


def save_rows(path: Path, form: dict[str, list[str]]) -> list[dict[str, str]]:
    current = load_rows(path)
    rows: list[dict[str, str]] = []
    for row in current:
        asset = row["asset"]
        next_row = row.copy()
        for field in holdings.FIELDNAMES:
            if field == "asset":
                continue
            key = f"{asset}_{field}"
            if key in form:
                next_row[field] = form[key][0].strip()
        next_row["asset"] = asset
        next_row["shares"] = holdings.normalize_number(next_row.get("shares", ""))
        next_row["price_krw"] = holdings.normalize_number(next_row.get("price_krw", ""))
        next_row["market_value_krw"] = holdings.normalize_number(next_row.get("market_value_krw", ""))
        if next_row["market_value_krw"] in {"", "0"}:
            auto_value = holdings.calculated_market_value(next_row.get("shares", ""), next_row.get("price_krw", ""))
            if auto_value:
                next_row["market_value_krw"] = auto_value
        if next_row["market_value_krw"] == "":
            next_row["market_value_krw"] = "0"
        rows.append({key: next_row.get(key, "") for key in holdings.FIELDNAMES})
    holdings.write_csv(path, rows)
    return rows


def rebuild_orders(holdings_path: Path) -> tuple[bool, str]:
    parser = rebalance.build_parser()
    args = parser.parse_args(["--holdings", str(holdings_path)])
    try:
        html_path, markdown_path, order_csv, target_csv = rebalance.write_rebalance_orders(args)
    except Exception as exc:  # pragma: no cover - surfaced through local UI
        return False, str(exc)
    return True, f"{html_path} / {markdown_path} / {order_csv} / {target_csv}"


def render_page(rows: list[dict[str, str]], message: str = "", error: str = "") -> bytes:
    total_value = sum(rebalance.holding_value(row) for row in rows)
    row_html = []
    for row in rows:
        asset = row["asset"]
        value = rebalance.holding_value(row)
        row_html.append(
            f"""
            <tr>
              <td>
                <strong>{esc(row.get('label'))}</strong>
                <div class="subtle">{esc(asset)} / {esc(row.get('symbol'))}</div>
              </td>
              <td><input name="{esc(asset)}_account" value="{esc(row.get('account'))}"></td>
              <td><input name="{esc(asset)}_symbol" value="{esc(row.get('symbol'))}"></td>
              <td><input name="{esc(asset)}_label" value="{esc(row.get('label'))}"></td>
              <td><input class="num" name="{esc(asset)}_shares" value="{esc(number_value(row.get('shares')))}" inputmode="decimal"></td>
              <td><input class="num" name="{esc(asset)}_price_krw" value="{esc(number_value(row.get('price_krw')))}" inputmode="numeric"></td>
              <td><input class="num" name="{esc(asset)}_market_value_krw" value="{esc(number_value(row.get('market_value_krw')))}" inputmode="numeric"></td>
              <td>{esc(rebalance.money(value))}</td>
              <td><input name="{esc(asset)}_notes" value="{esc(row.get('notes'))}"></td>
            </tr>
            """
        )
    banner = ""
    if message:
        banner = f'<div class="notice ok">{esc(message)}</div>'
    if error:
        banner = f'<div class="notice bad">{esc(error)}</div>'
    page = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Portfolio Holdings Input</title>
  <style>
    :root {{
      --bg: #f7f8fa;
      --surface: #fff;
      --ink: #1f2933;
      --muted: #66717f;
      --line: #d9dee5;
      --accent: #2563eb;
      --bad: #c2413a;
      --ok: #16835f;
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
    .topbar {{ display: flex; justify-content: space-between; align-items: end; gap: 14px; margin-bottom: 16px; }}
    h1 {{ margin: 0; font-size: 28px; line-height: 1.12; }}
    .subtle {{ color: var(--muted); font-size: 12px; line-height: 1.45; }}
    .cards {{ display: grid; grid-template-columns: repeat(3, minmax(160px, 1fr)); gap: 10px; margin-bottom: 16px; }}
    .card, .panel, .notice {{ background: var(--surface); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); }}
    .card {{ padding: 13px 14px; }}
    .label {{ color: var(--muted); font-size: 12px; }}
    .value {{ font-weight: 760; font-size: 20px; margin-top: 4px; }}
    .panel {{ overflow: hidden; margin-bottom: 16px; }}
    .panel-head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--line); }}
    .panel-body {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 1080px; }}
    th, td {{ padding: 10px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ color: var(--muted); background: #fbfcfe; }}
    input {{ width: 100%; min-height: 34px; border: 1px solid var(--line); border-radius: 7px; padding: 7px 8px; font: inherit; background: #fff; }}
    input.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .actions {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
    button {{ border: 1px solid var(--accent); background: var(--accent); color: white; border-radius: 7px; min-height: 38px; padding: 8px 12px; font: inherit; cursor: pointer; }}
    .secondary {{ border-color: var(--line); background: #fff; color: var(--ink); }}
    .notice {{ padding: 12px 14px; margin-bottom: 16px; }}
    .notice.ok {{ color: var(--ok); }}
    .notice.bad {{ color: var(--bad); }}
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
      <h1>Portfolio Holdings Input</h1>
      <div class="subtle">Local form for config/portfolio_holdings.csv</div>
    </div>
    <div class="subtle"><a href="/rebalance">Open rebalance orders</a> / <a href="/reload">Reload</a></div>
  </div>
  {banner}
  <section class="cards">
    <div class="card"><div class="label">Current value</div><div class="value">{esc(rebalance.money(total_value))}</div></div>
    <div class="card"><div class="label">Rows</div><div class="value">{len(rows)}</div></div>
    <div class="card"><div class="label">Output</div><div class="value">rebalance_orders.html</div></div>
  </section>
  <form method="post" action="/save">
    <section class="panel">
      <div class="panel-head">
        <strong>Holdings</strong>
        <div class="actions">
          <button type="submit">Save and Rebuild</button>
          <button class="secondary" type="reset">Reset</button>
        </div>
      </div>
      <div class="panel-body">
        <table>
          <thead>
            <tr>
              <th>Asset</th><th>Account</th><th>Symbol</th><th>Label</th><th>Shares</th><th>Price KRW</th><th>Market Value KRW</th><th>Parsed Value</th><th>Notes</th>
            </tr>
          </thead>
          <tbody>{''.join(row_html)}</tbody>
        </table>
      </div>
    </section>
  </form>
</div>
</body>
</html>
"""
    return page.encode("utf-8")


class PortfolioHandler(BaseHTTPRequestHandler):
    holdings_path: Path = holdings.DEFAULT_HOLDINGS

    def send_html(self, body: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, path: str, params: dict[str, str] | None = None) -> None:
        location = path
        if params:
            location = f"{path}?{urlencode(params)}"
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        query = parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
        if path == "/rebalance":
            self.redirect("/static/rebalance_orders.html")
            return
        if path == "/static/rebalance_orders.html":
            target = Path("reports/rebalance_orders.html")
            if not target.exists():
                ok, message = rebuild_orders(self.holdings_path)
                if not ok:
                    self.send_html(render_page(load_rows(self.holdings_path), error=message), 500)
                    return
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        message = query.get("message", [""])[0]
        error = query.get("error", [""])[0]
        self.send_html(render_page(load_rows(self.holdings_path), message=message, error=error))

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/save":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        form = parse_qs(raw, keep_blank_values=True)
        try:
            save_rows(self.holdings_path, form)
            ok, message = rebuild_orders(self.holdings_path)
        except Exception as exc:  # pragma: no cover - surfaced through local UI
            self.redirect("/", {"error": str(exc)})
            return
        if ok:
            self.redirect("/", {"message": "Saved holdings and rebuilt rebalance orders."})
        else:
            self.redirect("/", {"error": message})

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run local portfolio holdings input server.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--holdings", default=str(holdings.DEFAULT_HOLDINGS))
    parser.add_argument("--no-browser", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    PortfolioHandler.holdings_path = Path(args.holdings)
    server = ThreadingHTTPServer((args.host, args.port), PortfolioHandler)
    url = f"http://{args.host}:{args.port}"
    print(f"Portfolio input server: {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping portfolio input server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
