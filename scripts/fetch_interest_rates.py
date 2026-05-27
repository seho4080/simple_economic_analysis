#!/usr/bin/env python3
"""Fetch Korean and US policy-rate data for the analysis repo.

Sources:
  - Bank of Korea ECOS: base rate, STAT_CODE=722Y001, ITEM_CODE=0101000
  - Federal Reserve H.15 DDP: effective federal funds rate, RIFSPFF_N.D
  - Federal Reserve open market operations pages: FOMC target rate/range changes
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


BOK_STAT_CODE = "722Y001"
BOK_ITEM_CODE = "0101000"
BOK_START_DAILY = "19990506"
BOK_START_MONTHLY = "199905"
BOK_BASE_RATE_PAGE_URL = (
    "https://www.bok.or.kr/portal/singl/baseRate/list.do?"
    "dataSeCd=01&menuNo=200643"
)

FED_H15_EFFECTIVE_URL = (
    "https://www.federalreserve.gov/datadownload/Output.aspx?"
    "rel=H15&series=c5025f4bbbed155a6f17c587772ed69e&lastobs=&from=&to=&"
    "filetype=csv&label=include&layout=seriescolumn&type=package"
)
FED_OPEN_MARKET_URLS = [
    "https://www.federalreserve.gov/monetarypolicy/openmarket.htm",
    "https://www.federalreserve.gov/monetarypolicy/openmarket_archive.htm",
]

USER_AGENT = "stock-economic-indicators/0.1"


def fetch_bytes(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def write_csv(path: Path, rows: Iterable[dict], fieldnames: list[str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})
            count += 1
    return count


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if value in {"", ".", "ND", "N/A"}:
        return None
    return float(value)


def iso_date_from_ecos_time(period: str, cycle: str) -> str:
    if cycle == "D":
        return datetime.strptime(period, "%Y%m%d").date().isoformat()
    if cycle == "M":
        return datetime.strptime(period, "%Y%m").date().isoformat()
    raise ValueError(f"Unsupported ECOS cycle: {cycle}")


def bok_url(
    api_key: str,
    start_count: int,
    end_count: int,
    cycle: str,
    start_time: str,
    end_time: str,
) -> str:
    parts = [
        "https://ecos.bok.or.kr/api/StatisticSearch",
        urllib.parse.quote(api_key),
        "json",
        "kr",
        str(start_count),
        str(end_count),
        BOK_STAT_CODE,
        cycle,
        start_time,
        end_time,
        BOK_ITEM_CODE,
    ]
    return "/".join(parts)


def redacted_bok_url(cycle: str, start_time: str, end_time: str) -> str:
    return bok_url("{BOK_API_KEY}", 1, "{end_count}", cycle, start_time, end_time)


def fetch_bok_page(
    api_key: str,
    start_count: int,
    end_count: int,
    cycle: str,
    start_time: str,
    end_time: str,
) -> dict:
    url = bok_url(api_key, start_count, end_count, cycle, start_time, end_time)
    payload = json.loads(fetch_bytes(url, timeout=60).decode("utf-8"))
    if "RESULT" in payload:
        result = payload["RESULT"]
        raise RuntimeError(f"ECOS error {result.get('CODE')}: {result.get('MESSAGE')}")
    return payload["StatisticSearch"]


def fetch_bok_base_rate(
    api_key: str,
    cycle: str,
    start_time: str,
    end_time: str,
    max_workers: int,
    page_delay: float,
) -> tuple[list[dict], dict]:
    page_size = 10 if api_key == "sample" else 10000
    first = fetch_bok_page(api_key, 1, page_size, cycle, start_time, end_time)
    total = int(first["list_total_count"])
    raw_rows = list(first.get("row", []))

    ranges = [
        (start, min(start + page_size - 1, total))
        for start in range(page_size + 1, total + 1, page_size)
    ]
    if ranges and page_delay > 0:
        for start, end in ranges:
            time.sleep(page_delay)
            page = fetch_bok_page(api_key, start, end, cycle, start_time, end_time)
            raw_rows.extend(page.get("row", []))
    elif ranges:
        workers = min(max_workers, len(ranges))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    fetch_bok_page,
                    api_key,
                    start,
                    end,
                    cycle,
                    start_time,
                    end_time,
                ): (start, end)
                for start, end in ranges
            }
            for future in as_completed(futures):
                page = future.result()
                raw_rows.extend(page.get("row", []))

    raw_rows.sort(key=lambda row: row["TIME"])
    source_url = redacted_bok_url(cycle, start_time, end_time)
    normalized = []
    for row in raw_rows:
        rate = parse_float(row.get("DATA_VALUE"))
        normalized.append(
            {
                "date": iso_date_from_ecos_time(row["TIME"], cycle),
                "period": row["TIME"],
                "country": "Korea",
                "central_bank": "Bank of Korea",
                "series": "base_rate",
                "rate_pct": rate,
                "rate_lower_pct": rate,
                "rate_upper_pct": rate,
                "rate_mid_pct": rate,
                "frequency": "daily" if cycle == "D" else "monthly",
                "unit": row.get("UNIT_NAME", "연%"),
                "source": "Bank of Korea ECOS",
                "stat_code": row.get("STAT_CODE", BOK_STAT_CODE),
                "item_code": row.get("ITEM_CODE1", BOK_ITEM_CODE),
                "item_name": row.get("ITEM_NAME1", "한국은행 기준금리"),
                "source_url": source_url,
            }
        )

    metadata = {
        "source": "Bank of Korea ECOS",
        "stat_code": BOK_STAT_CODE,
        "item_code": BOK_ITEM_CODE,
        "cycle": cycle,
        "start_time": start_time,
        "end_time": end_time,
        "api_key": "sample" if api_key == "sample" else "env:BOK_API_KEY",
        "row_count": len(raw_rows),
        "source_url": source_url,
        "raw_rows": raw_rows,
    }
    return normalized, metadata


def parse_fed_h15_effective(raw_csv: bytes) -> list[dict]:
    text = raw_csv.decode("utf-8-sig")
    rows = list(csv.reader(text.splitlines()))
    data_start = None
    for index, row in enumerate(rows):
        if len(row) >= 2 and row[0] == "Time Period":
            data_start = index + 1
            break
    if data_start is None:
        raise RuntimeError("Could not find H.15 data header in Fed CSV.")

    normalized = []
    for row in rows[data_start:]:
        if len(row) < 2 or not row[0]:
            continue
        rate = parse_float(row[1])
        normalized.append(
            {
                "date": row[0],
                "country": "United States",
                "central_bank": "Federal Reserve",
                "series": "federal_funds_effective_rate",
                "rate_pct": rate,
                "rate_lower_pct": "",
                "rate_upper_pct": "",
                "rate_mid_pct": rate,
                "frequency": "daily",
                "unit": "Percent per year",
                "source": "Federal Reserve H.15",
                "source_series_id": "H15/H15/RIFSPFF_N.D",
                "source_url": FED_H15_EFFECTIVE_URL,
            }
        )
    return normalized


class FomcTargetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_year: int | None = None
        self.in_h4 = False
        self.h4_parts: list[str] = []
        self.in_tr = False
        self.in_cell = False
        self.cell_parts: list[str] = []
        self.current_row: list[str] = []
        self.rows: list[tuple[int, list[str]]] = []

    @staticmethod
    def clean(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h4":
            self.in_h4 = True
            self.h4_parts = []
        elif tag == "tr":
            self.in_tr = True
            self.current_row = []
        elif self.in_tr and tag in {"td", "th"}:
            self.in_cell = True
            self.cell_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_h4:
            self.h4_parts.append(data)
        if self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h4" and self.in_h4:
            text = self.clean("".join(self.h4_parts))
            if re.fullmatch(r"\d{4}", text):
                self.current_year = int(text)
            self.in_h4 = False
            self.h4_parts = []
        elif tag in {"td", "th"} and self.in_cell:
            self.current_row.append(self.clean("".join(self.cell_parts)))
            self.in_cell = False
            self.cell_parts = []
        elif tag == "tr" and self.in_tr:
            if self.current_year and len(self.current_row) >= 4:
                first = self.current_row[0].lower()
                if first not in {"date", ""} and "increase" not in first:
                    self.rows.append((self.current_year, self.current_row[:4]))
            self.in_tr = False
            self.current_row = []


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", data).strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts)


def fetch_bok_homepage_events() -> tuple[list[dict], bytes]:
    raw_html = fetch_bytes(BOK_BASE_RATE_PAGE_URL, timeout=60)
    parser = TextExtractor()
    parser.feed(raw_html.decode("utf-8", errors="replace"))
    text = parser.text()
    pattern = re.compile(
        r"(?P<year>(?:19|20)\d{2})\s+"
        r"(?P<month>\d{2})\uc6d4\s+"
        r"(?P<day>\d{2})\uc77c\s+"
        r"(?P<rate>\d+(?:\.\d+)?)"
    )
    events_by_date: dict[str, dict] = {}
    for match in pattern.finditer(text):
        event_date = date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        ).isoformat()
        rate = float(match.group("rate"))
        events_by_date[event_date] = {
            "date": event_date,
            "country": "Korea",
            "central_bank": "Bank of Korea",
            "series": "base_rate",
            "rate_pct": rate,
            "rate_lower_pct": rate,
            "rate_upper_pct": rate,
            "rate_mid_pct": rate,
            "frequency": "event",
            "unit": "Percent per year",
            "source": "Bank of Korea base-rate history page",
            "source_url": BOK_BASE_RATE_PAGE_URL,
            "note": "Before 2008-03 this is the target call rate; from 2008-03 it is the BOK base rate.",
        }

    events = sorted(events_by_date.values(), key=lambda row: row["date"])
    if not events:
        raise RuntimeError("No BOK base-rate events parsed from Bank of Korea page.")
    return events, raw_html


def expand_bok_events_daily(events: list[dict], end_date: date) -> list[dict]:
    expanded: list[dict] = []
    for index, event in enumerate(events):
        start = date.fromisoformat(event["date"])
        if index + 1 < len(events):
            end = date.fromisoformat(events[index + 1]["date"]) - timedelta(days=1)
        else:
            end = end_date
        if end < start:
            continue
        current = start
        while current <= end:
            expanded.append(
                {
                    "date": current.isoformat(),
                    "country": event["country"],
                    "central_bank": event["central_bank"],
                    "series": event["series"],
                    "rate_pct": event["rate_pct"],
                    "rate_lower_pct": event["rate_lower_pct"],
                    "rate_upper_pct": event["rate_upper_pct"],
                    "rate_mid_pct": event["rate_mid_pct"],
                    "frequency": "daily",
                    "unit": event["unit"],
                    "source": event["source"],
                    "source_event_date": event["date"],
                    "source_url": event["source_url"],
                    "note": event["note"],
                }
            )
            current += timedelta(days=1)
    return expanded


def parse_bps(value: str) -> int | None:
    value = re.sub(r"[^\d\-]", "", value)
    if not value or "-" in value:
        return None
    return int(value)


def is_zero_bps_text(value: str) -> bool:
    return re.sub(r"[^\d]", "", value) in {"", "0"}


def parse_level(level: str) -> tuple[float | None, float | None, float | None]:
    normalized = level.replace("\u2013", "-").replace("\u2014", "-")
    values = [float(match) for match in re.findall(r"\d+(?:\.\d+)?", normalized)]
    if len(values) >= 2 and "-" in normalized:
        lower, upper = values[0], values[1]
    elif len(values) == 1:
        lower = upper = values[0]
    else:
        return None, None, None
    return lower, upper, (lower + upper) / 2


def parse_fomc_event_date(year: int, value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 ]", "", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(f"{cleaned} {year}", fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Could not parse FOMC event date: {value!r} ({year})")


def fetch_fomc_target_events() -> list[dict]:
    events_by_key: dict[tuple[str, str], dict] = {}
    for url in FED_OPEN_MARKET_URLS:
        html = fetch_bytes(url, timeout=60).decode("utf-8", errors="replace")
        parser = FomcTargetParser()
        parser.feed(html)
        for year, cells in parser.rows:
            event_date = parse_fomc_event_date(year, cells[0])
            increase_bps = parse_bps(cells[1])
            decrease_bps = parse_bps(cells[2])
            lower, upper, mid = parse_level(cells[3])
            change_bps = None
            if increase_bps is not None and increase_bps > 0:
                change_bps = increase_bps
            elif decrease_bps is not None and decrease_bps > 0:
                change_bps = -decrease_bps
            elif is_zero_bps_text(cells[1]) and is_zero_bps_text(cells[2]):
                change_bps = 0
            row = {
                "date": event_date,
                "country": "United States",
                "central_bank": "Federal Reserve",
                "series": "federal_funds_target_rate_or_range",
                "change_bps": change_bps if change_bps is not None else "",
                "increase_bps": increase_bps if increase_bps is not None else "",
                "decrease_bps": decrease_bps if decrease_bps is not None else "",
                "increase_bps_text": cells[1],
                "decrease_bps_text": cells[2],
                "level_text": cells[3],
                "target_lower_pct": lower,
                "target_upper_pct": upper,
                "target_mid_pct": mid,
                "frequency": "event",
                "unit": "Percent per year",
                "source": "Federal Reserve Open Market Operations",
                "source_url": url,
            }
            events_by_key[(event_date, cells[3])] = row

    events = sorted(events_by_key.values(), key=lambda row: row["date"])
    if not events:
        raise RuntimeError("No FOMC target events parsed from Federal Reserve pages.")
    return events


def expand_fomc_events_daily(events: list[dict], end_date: date) -> list[dict]:
    expanded: list[dict] = []
    for index, event in enumerate(events):
        start = date.fromisoformat(event["date"])
        if index + 1 < len(events):
            end = date.fromisoformat(events[index + 1]["date"]) - timedelta(days=1)
        else:
            end = end_date
        if end < start:
            continue
        current = start
        while current <= end:
            expanded.append(
                {
                    "date": current.isoformat(),
                    "country": event["country"],
                    "central_bank": event["central_bank"],
                    "series": "federal_funds_target_rate_or_range",
                    "rate_pct": event["target_mid_pct"],
                    "rate_lower_pct": event["target_lower_pct"],
                    "rate_upper_pct": event["target_upper_pct"],
                    "rate_mid_pct": event["target_mid_pct"],
                    "level_text": event["level_text"],
                    "frequency": "daily",
                    "unit": event["unit"],
                    "source": event["source"],
                    "source_event_date": event["date"],
                    "source_url": event["source_url"],
                }
            )
            current += timedelta(days=1)
    return expanded


@dataclass
class OutputCounts:
    bok_rows: int
    fed_effective_rows: int
    fed_target_events: int
    fed_target_daily_rows: int
    combined_policy_rows: int


def run(args: argparse.Namespace) -> OutputCounts:
    raw_dir = Path(args.output_dir) / "raw" / "rates"
    processed_dir = Path(args.output_dir) / "processed" / "rates"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    bok_rows: list[dict] = []
    if not args.skip_bok:
        bok_key = args.bok_key or os.environ.get("BOK_API_KEY") or "sample"
        bok_source = args.bok_source
        if bok_source == "auto":
            bok_source = "ecos" if args.bok_key or os.environ.get("BOK_API_KEY") else "homepage-events"

        bok_fields = [
            "date",
            "country",
            "central_bank",
            "series",
            "rate_pct",
            "rate_lower_pct",
            "rate_upper_pct",
            "rate_mid_pct",
            "frequency",
            "unit",
            "source",
            "source_event_date",
            "source_url",
            "note",
        ]
        if bok_source == "homepage-events":
            bok_events, bok_raw_html = fetch_bok_homepage_events()
            (raw_dir / "bok_base_rate_events_homepage.html").write_bytes(bok_raw_html)
            bok_event_fields = [
                "date",
                "country",
                "central_bank",
                "series",
                "rate_pct",
                "rate_lower_pct",
                "rate_upper_pct",
                "rate_mid_pct",
                "frequency",
                "unit",
                "source",
                "source_url",
                "note",
            ]
            write_csv(processed_dir / "bok_base_rate_events.csv", bok_events, bok_event_fields)
            target_end = args.target_end or date.today().isoformat()
            bok_rows = expand_bok_events_daily(bok_events, date.fromisoformat(target_end))
            write_csv(processed_dir / "bok_base_rate_daily.csv", bok_rows, bok_fields)
        else:
            cycle = args.bok_frequency.upper()
            if cycle not in {"D", "M"}:
                raise ValueError("--bok-frequency must be D or M.")
            start_time = args.bok_start or (BOK_START_DAILY if cycle == "D" else BOK_START_MONTHLY)
            end_time = args.bok_end or date.today().strftime("%Y%m%d" if cycle == "D" else "%Y%m")
            page_delay = args.bok_page_delay
            if bok_key == "sample" and page_delay is None:
                page_delay = 0.75
            elif page_delay is None:
                page_delay = 0.0

            ecos_rows, bok_raw = fetch_bok_base_rate(
                bok_key,
                cycle,
                start_time,
                end_time,
                max_workers=args.max_workers,
                page_delay=page_delay,
            )
            bok_raw_path = raw_dir / f"bok_base_rate_{'daily' if cycle == 'D' else 'monthly'}_ecos.json"
            bok_raw_path.write_text(
                json.dumps(bok_raw, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            ecos_fields = [
                "date",
                "period",
                "country",
                "central_bank",
                "series",
                "rate_pct",
                "rate_lower_pct",
                "rate_upper_pct",
                "rate_mid_pct",
                "frequency",
                "unit",
                "source",
                "stat_code",
                "item_code",
                "item_name",
                "source_url",
            ]
            bok_path = processed_dir / f"bok_base_rate_{'daily' if cycle == 'D' else 'monthly'}.csv"
            write_csv(bok_path, ecos_rows, ecos_fields)
            for row in ecos_rows:
                bok_rows.append(
                    {
                        "date": row["date"],
                        "country": row["country"],
                        "central_bank": row["central_bank"],
                        "series": row["series"],
                        "rate_pct": row["rate_pct"],
                        "rate_lower_pct": row["rate_lower_pct"],
                        "rate_upper_pct": row["rate_upper_pct"],
                        "rate_mid_pct": row["rate_mid_pct"],
                        "frequency": row["frequency"],
                        "unit": row["unit"],
                        "source": row["source"],
                        "source_event_date": "",
                        "source_url": row["source_url"],
                        "note": "",
                    }
                )

    fed_effective_rows: list[dict] = []
    fed_target_events: list[dict] = []
    fed_target_daily_rows: list[dict] = []

    fed_effective_fields = [
        "date",
        "country",
        "central_bank",
        "series",
        "rate_pct",
        "rate_lower_pct",
        "rate_upper_pct",
        "rate_mid_pct",
        "frequency",
        "unit",
        "source",
        "source_series_id",
        "source_url",
    ]
    fed_event_fields = [
        "date",
        "country",
        "central_bank",
        "series",
        "change_bps",
        "increase_bps",
        "decrease_bps",
        "increase_bps_text",
        "decrease_bps_text",
        "level_text",
        "target_lower_pct",
        "target_upper_pct",
        "target_mid_pct",
        "frequency",
        "unit",
        "source",
        "source_url",
    ]
    fed_target_daily_fields = [
        "date",
        "country",
        "central_bank",
        "series",
        "rate_pct",
        "rate_lower_pct",
        "rate_upper_pct",
        "rate_mid_pct",
        "level_text",
        "frequency",
        "unit",
        "source",
        "source_event_date",
        "source_url",
    ]
    if not args.skip_fed:
        fed_raw_csv = fetch_bytes(FED_H15_EFFECTIVE_URL, timeout=60)
        fed_raw_path = raw_dir / "fed_funds_effective_daily_h15.csv"
        fed_raw_path.write_bytes(fed_raw_csv)
        fed_effective_rows = parse_fed_h15_effective(fed_raw_csv)
        fed_effective_path = processed_dir / "fed_funds_effective_daily.csv"
        write_csv(fed_effective_path, fed_effective_rows, fed_effective_fields)

        fed_target_events = fetch_fomc_target_events()
        fed_events_raw_path = raw_dir / "fed_funds_target_events_openmarket.json"
        fed_events_raw_path.write_text(
            json.dumps(
                {
                    "source": "Federal Reserve Open Market Operations",
                    "source_urls": FED_OPEN_MARKET_URLS,
                    "row_count": len(fed_target_events),
                    "raw_rows": fed_target_events,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        fed_events_path = processed_dir / "fed_funds_target_events.csv"
        write_csv(fed_events_path, fed_target_events, fed_event_fields)

        target_end = args.target_end or date.today().isoformat()
        fed_target_daily_rows = expand_fomc_events_daily(
            fed_target_events,
            date.fromisoformat(target_end),
        )
        fed_target_path = processed_dir / "fed_funds_target_daily.csv"
        write_csv(fed_target_path, fed_target_daily_rows, fed_target_daily_fields)

    combined_policy_rows = []
    for row in bok_rows:
        combined_policy_rows.append(
            {
                "date": row["date"],
                "country": row["country"],
                "central_bank": row["central_bank"],
                "series": row["series"],
                "rate_pct": row["rate_pct"],
                "rate_lower_pct": row["rate_lower_pct"],
                "rate_upper_pct": row["rate_upper_pct"],
                "rate_mid_pct": row["rate_mid_pct"],
                "frequency": row["frequency"],
                "unit": row["unit"],
                "source": row["source"],
                "source_url": row["source_url"],
            }
        )
    for row in fed_target_daily_rows:
        combined_policy_rows.append(
            {
                "date": row["date"],
                "country": row["country"],
                "central_bank": row["central_bank"],
                "series": row["series"],
                "rate_pct": row["rate_pct"],
                "rate_lower_pct": row["rate_lower_pct"],
                "rate_upper_pct": row["rate_upper_pct"],
                "rate_mid_pct": row["rate_mid_pct"],
                "frequency": row["frequency"],
                "unit": row["unit"],
                "source": row["source"],
                "source_url": row["source_url"],
            }
        )
    combined_policy_rows.sort(key=lambda row: (row["date"], row["central_bank"], row["series"]))
    combined_policy_path = processed_dir / "central_bank_policy_rates_daily.csv"
    combined_policy_fields = [
        "date",
        "country",
        "central_bank",
        "series",
        "rate_pct",
        "rate_lower_pct",
        "rate_upper_pct",
        "rate_mid_pct",
        "frequency",
        "unit",
        "source",
        "source_url",
    ]
    write_csv(combined_policy_path, combined_policy_rows, combined_policy_fields)

    all_rows = []
    for row in combined_policy_rows:
        all_rows.append(row)
    for row in fed_effective_rows:
        all_rows.append(
            {
                "date": row["date"],
                "country": row["country"],
                "central_bank": row["central_bank"],
                "series": row["series"],
                "rate_pct": row["rate_pct"],
                "rate_lower_pct": row["rate_lower_pct"],
                "rate_upper_pct": row["rate_upper_pct"],
                "rate_mid_pct": row["rate_mid_pct"],
                "frequency": row["frequency"],
                "unit": row["unit"],
                "source": row["source"],
                "source_url": row["source_url"],
            }
        )
    all_rows.sort(key=lambda row: (row["date"], row["central_bank"], row["series"]))
    all_rates_path = processed_dir / "all_interest_rates_daily.csv"
    write_csv(all_rates_path, all_rows, combined_policy_fields)

    return OutputCounts(
        bok_rows=len(bok_rows),
        fed_effective_rows=len(fed_effective_rows),
        fed_target_events=len(fed_target_events),
        fed_target_daily_rows=len(fed_target_daily_rows),
        combined_policy_rows=len(combined_policy_rows),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch BOK and Fed interest-rate datasets into data/raw and data/processed."
    )
    parser.add_argument(
        "--output-dir",
        default="data",
        help="Base data directory. Defaults to ./data.",
    )
    parser.add_argument(
        "--bok-key",
        default=None,
        help="Bank of Korea ECOS API key. Defaults to BOK_API_KEY or ECOS sample key.",
    )
    parser.add_argument(
        "--bok-source",
        default="auto",
        choices=["auto", "ecos", "homepage-events"],
        help=(
            "BOK source. auto uses ECOS when a real key is available, otherwise "
            "the official BOK base-rate history page."
        ),
    )
    parser.add_argument(
        "--bok-frequency",
        default="D",
        choices=["D", "M", "d", "m"],
        help="BOK base-rate frequency: D=daily, M=monthly. Defaults to D.",
    )
    parser.add_argument(
        "--bok-start",
        default=None,
        help="ECOS start period. Defaults to 19990506 for D or 199905 for M.",
    )
    parser.add_argument(
        "--bok-end",
        default=None,
        help="ECOS end period. Defaults to today for D or current month for M.",
    )
    parser.add_argument(
        "--target-end",
        default=None,
        help="End date for daily-expanded Fed target range. Defaults to today.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Concurrent ECOS page fetches. Ignored when --bok-page-delay is positive.",
    )
    parser.add_argument(
        "--bok-page-delay",
        type=float,
        default=None,
        help="Delay in seconds between ECOS page calls. Defaults to 0.75 for sample key, 0 otherwise.",
    )
    parser.add_argument(
        "--skip-bok",
        action="store_true",
        help="Skip Bank of Korea fetch.",
    )
    parser.add_argument(
        "--skip-fed",
        action="store_true",
        help="Skip Federal Reserve fetches.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        counts = run(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Fetched interest-rate datasets:")
    print(f"  BOK base rate rows: {counts.bok_rows}")
    print(f"  Fed effective funds daily rows: {counts.fed_effective_rows}")
    print(f"  Fed target events: {counts.fed_target_events}")
    print(f"  Fed target daily rows: {counts.fed_target_daily_rows}")
    print(f"  Combined central-bank policy rows: {counts.combined_policy_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
