"""weekly_pipeline.py のCTA UTMパラメータ付与ロジックのユニットテスト。
ネットワークアクセス・課金なしで実行できる(APIは一切呼ばない)。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import weekly_pipeline  # noqa: E402


class TestAddUtmTracking(unittest.TestCase):
    def test_instagram_uses_instagram_utm_source(self):
        caption = "お問い合わせはこちら\nhttps://liftercorp.co/contact"
        result = weekly_pipeline._add_utm_tracking(caption, "Instagram", "abc12345")
        self.assertIn("utm_source=instagram", result)
        self.assertIn("utm_content=abc12345", result)

    def test_youtube_uses_youtube_utm_source(self):
        caption = "https://liftercorp.co/contact からご相談ください"
        result = weekly_pipeline._add_utm_tracking(caption, "YouTube Shorts", "xyz98765")
        self.assertIn("utm_source=youtube", result)

    def test_base_url_no_longer_appears_bare(self):
        caption = "https://liftercorp.co/contact"
        result = weekly_pipeline._add_utm_tracking(caption, "Instagram", "id1")
        self.assertNotEqual(result, caption)
        self.assertTrue(result.startswith("https://liftercorp.co/contact?"))

    def test_caption_without_cta_url_is_unchanged(self):
        caption = "CTAリンクが含まれていない本文"
        result = weekly_pipeline._add_utm_tracking(caption, "Instagram", "id1")
        self.assertEqual(result, caption)


if __name__ == "__main__":
    unittest.main()
