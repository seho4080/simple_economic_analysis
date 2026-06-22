"""CSV loading helpers for ETF backtest variant definitions."""

from __future__ import annotations

import csv
import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import TypeVar


T = TypeVar("T")

VARIANT_FIELDS = [
    "slug",
    "title",
    "start",
    "end",
    "cash_symbol",
    "cash_label",
    "gold_symbol",
    "gold_label",
    "silver_symbol",
    "silver_label",
    "equity_symbol",
    "equity_label",
    "note",
]

OPTIONAL_FIELDS = {"end", "note"}
SLUG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _validate_slug(path: Path, line_number: int, slug: str) -> None:
    if not SLUG_PATTERN.fullmatch(slug):
        raise ValueError(
            f"{path}:{line_number}: slug must use letters, numbers, underscores, or hyphens."
        )


def _validate_date(path: Path, line_number: int, field: str, value: str) -> None:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{path}:{line_number}: {field} must use YYYY-MM-DD format.") from exc


def _normalize_end(value: str, default_end: str) -> str:
    if value.strip().lower() in {"", "latest", "default"}:
        return default_end
    return value.strip()


def read_variant_config(path: Path, variant_cls: Callable[..., T], default_end: str) -> list[T]:
    """Read ETF backtest variants from a CSV file."""

    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: CSV header is missing.")

        missing_columns = [field for field in VARIANT_FIELDS if field not in reader.fieldnames]
        if missing_columns:
            raise ValueError(f"{path}: missing columns: {', '.join(missing_columns)}")

        variants: list[T] = []
        seen_slugs: set[str] = set()
        for line_number, row in enumerate(reader, start=2):
            if not any((value or "").strip() for value in row.values() if isinstance(value, str)):
                continue

            data = {field: (row.get(field) or "").strip() for field in VARIANT_FIELDS}
            data["end"] = _normalize_end(data["end"], default_end)
            missing_fields = [
                field for field in VARIANT_FIELDS if field not in OPTIONAL_FIELDS and not data[field]
            ]
            if missing_fields:
                raise ValueError(
                    f"{path}:{line_number}: missing required fields: {', '.join(missing_fields)}"
                )

            _validate_slug(path, line_number, data["slug"])
            _validate_date(path, line_number, "start", data["start"])
            _validate_date(path, line_number, "end", data["end"])

            if data["slug"] in seen_slugs:
                raise ValueError(f"{path}:{line_number}: duplicate slug: {data['slug']}")
            seen_slugs.add(data["slug"])
            variants.append(variant_cls(**data))

    if not variants:
        raise ValueError(f"{path}: no variants found.")
    return variants
