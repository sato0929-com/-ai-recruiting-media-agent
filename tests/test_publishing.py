"""publishing.py の日付スケジュール判定ロジックのユニットテスト。
ネットワークアクセス・課金なしで実行できる(APIは一切呼ばない)。"""
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import publishing  # noqa: E402


class TestIsDue(unittest.TestCase):
    def test_empty_value_is_always_due(self):
        self.assertTrue(publishing._is_due(""))

    def test_unparseable_value_is_due(self):
        self.assertTrue(publishing._is_due("来週の月曜"))

    def test_past_date_is_due(self):
        yesterday = (publishing._today_jst() - timedelta(days=1)).isoformat()
        self.assertTrue(publishing._is_due(yesterday))

    def test_today_is_due(self):
        today = publishing._today_jst().isoformat()
        self.assertTrue(publishing._is_due(today))

    def test_future_date_is_not_due(self):
        tomorrow = (publishing._today_jst() + timedelta(days=1)).isoformat()
        self.assertFalse(publishing._is_due(tomorrow))


if __name__ == "__main__":
    unittest.main()
