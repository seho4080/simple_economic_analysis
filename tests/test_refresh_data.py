from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import refresh_data  # noqa: E402


class RefreshDataTest(unittest.TestCase):
    def task(self) -> refresh_data.RefreshTask:
        return refresh_data.RefreshTask(
            name="macro",
            description="",
            enabled=True,
            cadence_hours=24,
            timeout_seconds=10,
            command=["{python}", "scripts/update_macro.py", "--root", "{root}"],
        )

    def test_task_without_success_is_due(self) -> None:
        now = datetime(2026, 6, 21, tzinfo=UTC)

        self.assertTrue(refresh_data.is_due(self.task(), {}, now, force=False))

    def test_task_inside_cadence_is_not_due(self) -> None:
        now = datetime(2026, 6, 21, 12, tzinfo=UTC)
        entry = {"last_success_at": "2026-06-21T00:00:00Z"}

        self.assertFalse(refresh_data.is_due(self.task(), entry, now, force=False))

    def test_force_makes_task_due(self) -> None:
        now = datetime(2026, 6, 21, 12, tzinfo=UTC)
        entry = {"last_success_at": "2026-06-21T00:00:00Z"}

        self.assertTrue(refresh_data.is_due(self.task(), entry, now, force=True))

    def test_expand_command_tokens(self) -> None:
        root = Path("C:/repo")

        command = refresh_data.expand_command(self.task().command, root)

        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[-1], str(root))

    def test_select_explicit_disabled_task(self) -> None:
        now = datetime(2026, 6, 21, tzinfo=UTC)
        task = refresh_data.RefreshTask(
            name="isa_backtests",
            description="",
            enabled=False,
            cadence_hours=168,
            timeout_seconds=10,
            command=["{python}", "scripts/run_isa_etf_max_backtests.py"],
        )

        selected = refresh_data.select_tasks(
            [task],
            {"tasks": {}},
            ["isa_backtests"],
            force=False,
            include_disabled=False,
            now=now,
        )

        self.assertEqual([(item.name, reason) for item, reason in selected], [("isa_backtests", "selected")])


if __name__ == "__main__":
    unittest.main()
