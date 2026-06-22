from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_scenario_simulator as simulator  # noqa: E402


class GenerateScenarioSimulatorTest(unittest.TestCase):
    def test_scores_from_row_maps_all_score_names_and_defaults_missing_values(self) -> None:
        row = {
            "inflation_risk": "6.5",
            "liquidity_bubble_risk": "",
            "credit_stress_risk": "2",
            "fx_risk": "NA",
        }

        scores = simulator.scores_from_row(row)

        self.assertEqual(scores["Inflation Risk"], 6.5)
        self.assertEqual(scores["Liquidity Bubble Risk"], 0.0)
        self.assertEqual(scores["Credit Stress Risk"], 2.0)
        self.assertEqual(scores["FX Risk"], 0.0)
        self.assertIn("Global Rate Divergence Risk", scores)

    def test_scenario_result_reuses_macro_regime_and_allocation_rules(self) -> None:
        scores = {
            "Inflation Risk": 4.0,
            "Liquidity Bubble Risk": 3.0,
            "Credit Stress Risk": 7.2,
            "FX Risk": 3.0,
            "Climate Supply Shock Risk": 2.0,
            "Growth Slowdown Risk": 6.4,
            "Market Stress Risk": 2.0,
            "Global Rate Divergence Risk": 3.0,
        }

        result = simulator.scenario_result(scores)

        self.assertEqual(result["current_regime"], "Credit Stress")
        self.assertEqual(set(result["allocation"]), {"cash", "gold", "silver", "equity"})
        self.assertEqual(sum(result["allocation"].values()), 150)

    def test_render_html_embeds_safe_json_payload(self) -> None:
        payload = simulator.ScenarioPayload(
            generated_at="2026-06-21T12:00:00",
            report_date="2026-06-21 </script>",
            baseline_scores={"Inflation Risk": 5.0},
            baseline_regime={"current": "Defensive Waiting Mode", "supporting": "NA"},
            baseline_allocation={"cash": 30, "gold": 40, "silver": 20, "equity": 60},
            risk_fields=[{"field": "inflation_risk", "scoreName": "Inflation Risk", "label": "Inflation"}],
        )

        html = simulator.render_html(payload)
        match = re.search(r'<script id="scenario-data" type="application/json">(.*?)</script>', html)

        self.assertIsNotNone(match)
        self.assertIn("Macro Scenario Simulator", html)
        self.assertIn("<\\/script>", match.group(1))
        data = json.loads(match.group(1))
        self.assertEqual(data["baseline_regime"]["current"], "Defensive Waiting Mode")

    def test_write_simulator_creates_static_html_from_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "risk_score_history.csv"
            output = root / "scenario_simulator.html"
            history.write_text(
                "report_date,inflation_risk,liquidity_bubble_risk,credit_stress_risk,fx_risk,"
                "climate_supply_shock_risk,growth_slowdown_risk,market_stress_risk,"
                "global_rate_divergence_risk\n"
                "2026-06-21,5,4,3,6,2,4,2,5\n",
                encoding="utf-8",
            )

            simulator.write_simulator(
                type("Args", (), {"risk_history": str(history), "output": str(output)})()
            )

            self.assertTrue(output.exists())
            self.assertIn("2026-06-21", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
