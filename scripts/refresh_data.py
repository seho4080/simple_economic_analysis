#!/usr/bin/env python3
"""Run configured data-refresh tasks with state, logging, and health reports."""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path("config/data_refresh.json")
LOG_TEXT_LIMIT = 6000


@dataclass(frozen=True)
class RefreshTask:
    name: str
    description: str
    enabled: bool
    cadence_hours: float
    timeout_seconds: int
    command: list[str]


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def isoformat(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    with path.open(encoding="utf-8-sig") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object.")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def load_config(path: Path, root: Path) -> dict[str, Any]:
    config = load_json(path, {})
    config.setdefault("state_path", "data/processed/refresh_state.json")
    config.setdefault("log_path", "data/processed/refresh_runs.jsonl")
    config.setdefault("lock_path", "data/processed/refresh.lock")
    config.setdefault("status_report", "reports/data_refresh_status.md")
    config.setdefault("lock_stale_hours", 12)
    config.setdefault("tasks", [])
    for key in ("state_path", "log_path", "lock_path", "status_report"):
        config[key] = str(resolve_path(root, config[key]))
    return config


def parse_tasks(config: dict[str, Any]) -> list[RefreshTask]:
    tasks: list[RefreshTask] = []
    names: set[str] = set()
    for index, item in enumerate(config.get("tasks", []), start=1):
        if not isinstance(item, dict):
            raise ValueError(f"tasks[{index}] must be an object.")
        name = str(item.get("name", "")).strip()
        if not name:
            raise ValueError(f"tasks[{index}] is missing name.")
        if name in names:
            raise ValueError(f"Duplicate refresh task name: {name}")
        command = item.get("command")
        if not isinstance(command, list) or not command:
            raise ValueError(f"Task {name} must define a non-empty command list.")
        tasks.append(
            RefreshTask(
                name=name,
                description=str(item.get("description", "")).strip(),
                enabled=bool(item.get("enabled", True)),
                cadence_hours=float(item.get("cadence_hours", 24)),
                timeout_seconds=int(item.get("timeout_seconds", 3600)),
                command=[str(part) for part in command],
            )
        )
        names.add(name)
    return tasks


def expand_command(command: list[str], root: Path) -> list[str]:
    return [
        part.replace("{python}", sys.executable).replace("{root}", str(root))
        for part in command
    ]


def task_state(state: dict[str, Any], task_name: str) -> dict[str, Any]:
    tasks = state.setdefault("tasks", {})
    if not isinstance(tasks, dict):
        state["tasks"] = {}
        tasks = state["tasks"]
    entry = tasks.setdefault(task_name, {})
    if not isinstance(entry, dict):
        tasks[task_name] = {}
        entry = tasks[task_name]
    return entry


def next_due_at(task: RefreshTask, entry: dict[str, Any]) -> datetime | None:
    last_success = parse_timestamp(entry.get("last_success_at"))
    if last_success is None:
        return None
    return last_success + timedelta(hours=task.cadence_hours)


def is_due(task: RefreshTask, entry: dict[str, Any], now: datetime, force: bool) -> bool:
    if force:
        return True
    due_at = next_due_at(task, entry)
    return due_at is None or due_at <= now


def select_tasks(
    tasks: list[RefreshTask],
    state: dict[str, Any],
    selected_names: list[str],
    force: bool,
    include_disabled: bool,
    now: datetime,
) -> list[tuple[RefreshTask, str]]:
    explicit = [name for name in selected_names if name != "all"]
    all_selected = not selected_names or "all" in selected_names
    known = {task.name for task in tasks}
    unknown = [name for name in explicit if name not in known]
    if unknown:
        raise ValueError(f"Unknown refresh task(s): {', '.join(unknown)}")

    selected: list[tuple[RefreshTask, str]] = []
    for task in tasks:
        explicitly_selected = task.name in explicit
        if not (all_selected or explicitly_selected):
            continue
        if not task.enabled and not include_disabled and not explicitly_selected:
            continue

        entry = task_state(state, task.name)
        if explicitly_selected or is_due(task, entry, now, force):
            selected.append((task, "selected" if explicitly_selected else "due"))
    return selected


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def tail_text(value: str | None, limit: int = LOG_TEXT_LIMIT) -> str:
    if not value:
        return ""
    return value[-limit:]


def run_task(task: RefreshTask, root: Path) -> dict[str, Any]:
    command = expand_command(task.command, root)
    started = utc_now()
    started_monotonic = time.monotonic()
    result: dict[str, Any] = {
        "task": task.name,
        "description": task.description,
        "command": command,
        "started_at": isoformat(started),
        "host": platform.node(),
    }
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=task.timeout_seconds,
            check=False,
        )
        status = "ok" if completed.returncode == 0 else "error"
        result.update(
            {
                "status": status,
                "returncode": completed.returncode,
                "stdout_tail": tail_text(completed.stdout),
                "stderr_tail": tail_text(completed.stderr),
            }
        )
    except subprocess.TimeoutExpired as exc:
        result.update(
            {
                "status": "timeout",
                "returncode": "",
                "stdout_tail": tail_text(exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else exc.stdout),
                "stderr_tail": tail_text(exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else exc.stderr),
            }
        )
    finished = utc_now()
    result["finished_at"] = isoformat(finished)
    result["duration_seconds"] = round(time.monotonic() - started_monotonic, 2)
    return result


def apply_result_to_state(state: dict[str, Any], result: dict[str, Any]) -> None:
    entry = task_state(state, result["task"])
    entry["last_started_at"] = result["started_at"]
    entry["last_finished_at"] = result["finished_at"]
    entry["last_status"] = result["status"]
    entry["last_returncode"] = result["returncode"]
    entry["last_duration_seconds"] = result["duration_seconds"]
    if result["status"] == "ok":
        entry["last_success_at"] = result["finished_at"]


class RefreshLock:
    def __init__(self, path: Path, stale_after: timedelta) -> None:
        self.path = path
        self.stale_after = stale_after
        self.acquired = False

    def __enter__(self) -> "RefreshLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            mtime = datetime.fromtimestamp(self.path.stat().st_mtime, tz=UTC)
            if utc_now() - mtime > self.stale_after:
                self.path.unlink()
        try:
            with self.path.open("x", encoding="utf-8") as f:
                f.write(f"pid={os.getpid()}\nstarted_at={isoformat(utc_now())}\n")
            self.acquired = True
        except FileExistsError as exc:
            raise RuntimeError(f"Refresh lock already exists: {self.path}") from exc
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.acquired and self.path.exists():
            self.path.unlink()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def count_by(rows: list[dict[str, str]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(field) or "blank"
        counts[value] = counts.get(value, 0) + 1
    return counts


def markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def format_due(task: RefreshTask, entry: dict[str, Any]) -> str:
    due = next_due_at(task, entry)
    return "now" if due is None else isoformat(due)


def write_status_report(path: Path, root: Path, tasks: list[RefreshTask], state: dict[str, Any]) -> None:
    fetch_rows = read_csv_rows(root / "data/processed/macro/fetch_status.csv")
    snapshot_rows = read_csv_rows(root / "data/processed/macro/latest_snapshot.csv")
    fetch_counts = count_by(fetch_rows, "status")
    freshness_counts = count_by(snapshot_rows, "freshness_status")
    problem_fetches = [
        row for row in fetch_rows if row.get("status") not in {"ok", ""}
    ][:12]
    stale_snapshot = [
        row for row in snapshot_rows if row.get("freshness_status") == "stale"
    ][:12]

    task_rows: list[list[str]] = []
    for task in tasks:
        entry = task_state(state, task.name)
        task_rows.append(
            [
                task.name,
                "yes" if task.enabled else "no",
                str(task.cadence_hours),
                entry.get("last_status", "never"),
                entry.get("last_success_at", ""),
                format_due(task, entry),
            ]
        )

    lines = [
        "# Data Refresh Status",
        "",
        f"Generated at: {isoformat(utc_now())}",
        "",
        "## Tasks",
        *markdown_table(
            ["task", "enabled", "cadence_hours", "last_status", "last_success_at", "next_due_at"],
            task_rows,
        ),
        "",
        "## Source Health",
        f"- Fetch status rows: {len(fetch_rows)}",
        f"- Fetch statuses: {json.dumps(fetch_counts, ensure_ascii=False, sort_keys=True)}",
        f"- Snapshot rows: {len(snapshot_rows)}",
        f"- Freshness statuses: {json.dumps(freshness_counts, ensure_ascii=False, sort_keys=True)}",
    ]
    if problem_fetches:
        lines.extend(
            [
                "",
                "## Fetch Problems",
                *markdown_table(
                    ["source_type", "indicator_id", "status", "message"],
                    [
                        [
                            row.get("source_type", ""),
                            row.get("indicator_id", ""),
                            row.get("status", ""),
                            (row.get("message", "") or "").replace("|", "/")[:160],
                        ]
                        for row in problem_fetches
                    ],
                ),
            ]
        )
    if stale_snapshot:
        lines.extend(
            [
                "",
                "## Stale Snapshot Items",
                *markdown_table(
                    ["indicator_id", "latest_date", "age_days", "source"],
                    [
                        [
                            row.get("indicator_id", ""),
                            row.get("latest_date", ""),
                            row.get("age_days", ""),
                            row.get("source", ""),
                        ]
                        for row in stale_snapshot
                    ],
                ),
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run due data-refresh tasks from config/data_refresh.json.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Refresh config JSON path.")
    parser.add_argument(
        "--task",
        action="append",
        default=[],
        help="Task name to run. Repeat for multiple tasks, or use all. Defaults to due enabled tasks.",
    )
    parser.add_argument("--force", action="store_true", help="Run selected tasks even if cadence says they are not due.")
    parser.add_argument("--dry-run", action="store_true", help="Print selected tasks without executing them.")
    parser.add_argument("--include-disabled", action="store_true", help="Include disabled tasks when selecting all tasks.")
    parser.add_argument("--list-tasks", action="store_true", help="List configured tasks and exit.")
    parser.add_argument("--stop-on-failure", action="store_true", help="Stop after the first failing task.")
    parser.add_argument("--no-status-report", action="store_true", help="Do not write reports/data_refresh_status.md.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = repo_root()
    config_path = resolve_path(root, args.config)
    config = load_config(config_path, root)
    tasks = parse_tasks(config)
    state_path = Path(config["state_path"])
    log_path = Path(config["log_path"])
    lock_path = Path(config["lock_path"])
    report_path = Path(config["status_report"])
    state = load_json(state_path, {"version": 1, "tasks": {}})
    now = utc_now()

    if args.list_tasks:
        for task in tasks:
            enabled = "enabled" if task.enabled else "disabled"
            due = "due" if is_due(task, task_state(state, task.name), now, args.force) else "not due"
            print(f"{task.name}: {enabled}, {due}, cadence={task.cadence_hours}h")
        return 0

    selected = select_tasks(tasks, state, args.task, args.force, args.include_disabled, now)
    if args.dry_run:
        if not selected:
            print("No refresh tasks selected.")
        for task, reason in selected:
            print(f"{task.name}: {reason} -> {' '.join(expand_command(task.command, root))}")
        return 0

    if not selected:
        print("No refresh tasks are due.")
        if not args.no_status_report:
            write_status_report(report_path, root, tasks, state)
            print(f"Status report: {report_path}")
        return 0

    state["last_run_started_at"] = isoformat(now)
    failures = 0
    stale_after = timedelta(hours=float(config.get("lock_stale_hours", 12)))
    with RefreshLock(lock_path, stale_after):
        for task, reason in selected:
            print(f"[refresh] {task.name} ({reason})")
            result = run_task(task, root)
            append_jsonl(log_path, result)
            apply_result_to_state(state, result)
            write_json(state_path, state)
            print(f"  status={result['status']} duration={result['duration_seconds']}s")
            if result["status"] != "ok":
                failures += 1
                if args.stop_on_failure:
                    break

    state["last_run_finished_at"] = isoformat(utc_now())
    write_json(state_path, state)
    if not args.no_status_report:
        write_status_report(report_path, root, tasks, state)
        print(f"Status report: {report_path}")
    print(f"Refresh log: {log_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
