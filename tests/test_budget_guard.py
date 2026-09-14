"""budget_guard.py のユニットテスト。ネットワークアクセスなし・課金なしで実行できる。"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import budget_guard  # noqa: E402
import config  # noqa: E402


class TestCostCalculation(unittest.TestCase):
    def test_haiku_cost_matches_pricing_table(self):
        cost = budget_guard.calc_cost_usd(config.MODEL_HAIKU, input_tokens=1_000_000, output_tokens=1_000_000)
        self.assertAlmostEqual(cost, 1.00 + 5.00)

    def test_sonnet_cost_matches_pricing_table(self):
        cost = budget_guard.calc_cost_usd(config.MODEL_SONNET, input_tokens=1_000_000, output_tokens=1_000_000)
        self.assertAlmostEqual(cost, 2.00 + 10.00)

    def test_web_search_cost_matches_pricing_table(self):
        cost = budget_guard.calc_web_search_cost_usd(web_search_count=1000)
        self.assertAlmostEqual(cost, 10.00)


class TestUsageLedger(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmpdir.name) / "usage_log.json"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_record_and_total_same_month(self):
        budget_guard.record_usage("test_agent", config.MODEL_HAIKU, 100_000, 50_000, log_path=self.log_path)
        total = budget_guard.total_cost_jpy("month", log_path=self.log_path)
        self.assertGreater(total, 0)

    def test_record_usage_includes_web_search_cost(self):
        entry = budget_guard.record_usage(
            "test_agent", config.MODEL_HAIKU, 0, 0, web_search_count=10, log_path=self.log_path
        )
        expected_usd = budget_guard.calc_web_search_cost_usd(10)
        self.assertAlmostEqual(entry.cost_usd, expected_usd)
        self.assertEqual(entry.web_search_count, 10)

    def test_total_excludes_previous_month(self):
        old_entry = {
            "timestamp": (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(),
            "agent": "test_agent",
            "model": config.MODEL_HAIKU,
            "input_tokens": 1_000_000,
            "output_tokens": 1_000_000,
            "cost_usd": 6.0,
            "cost_jpy": 960.0,
        }
        budget_guard._save_entries([old_entry], self.log_path)
        total = budget_guard.total_cost_jpy("month", log_path=self.log_path)
        self.assertEqual(total, 0)


class TestBudgetThresholds(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmpdir.name) / "usage_log.json"

    def tearDown(self):
        self.tmpdir.cleanup()

    def _seed_month_total(self, jpy_amount: float):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": "seed",
            "model": config.MODEL_HAIKU,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0,
            "cost_jpy": jpy_amount,
        }
        budget_guard._save_entries([entry], self.log_path)

    def test_under_soft_limit_allows_generation(self):
        self._seed_month_total(config.MONTHLY_BUDGET_JPY * 0.5)
        budget_guard.check_before_call("generation", log_path=self.log_path)  # should not raise

    def test_soft_limit_blocks_generation_but_not_utility(self):
        self._seed_month_total(config.MONTHLY_BUDGET_JPY * 0.85)
        with self.assertRaises(budget_guard.SoftBudgetExceeded):
            budget_guard.check_before_call("generation", log_path=self.log_path)
        budget_guard.check_before_call("utility", log_path=self.log_path)  # should not raise

    def test_hard_limit_blocks_everything(self):
        self._seed_month_total(config.MONTHLY_BUDGET_JPY * 1.1)
        with self.assertRaises(budget_guard.HardBudgetExceeded):
            budget_guard.check_before_call("generation", log_path=self.log_path)
        with self.assertRaises(budget_guard.HardBudgetExceeded):
            budget_guard.check_before_call("utility", log_path=self.log_path)


if __name__ == "__main__":
    unittest.main()
