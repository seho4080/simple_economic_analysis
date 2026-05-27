"""Shared date defaults for monthly report and backtest CLIs."""

from __future__ import annotations

import calendar
from datetime import date


DEFAULT_REPORT_DAY = 6


def _previous_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def latest_report_month(today: date | None = None, report_day: int = DEFAULT_REPORT_DAY) -> str:
    """Return the latest month whose report day has already arrived."""
    today = today or date.today()
    year, month = today.year, today.month
    if today.day < report_day:
        year, month = _previous_month(year, month)
    return f"{year:04d}-{month:02d}"


def latest_report_date(today: date | None = None, report_day: int = DEFAULT_REPORT_DAY) -> date:
    month_text = latest_report_month(today, report_day)
    year_text, month_text_only = month_text.split("-", 1)
    year = int(year_text)
    month = int(month_text_only)
    day = min(report_day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def latest_report_date_iso(today: date | None = None, report_day: int = DEFAULT_REPORT_DAY) -> str:
    return latest_report_date(today, report_day).isoformat()


def today_iso() -> str:
    return date.today().isoformat()
