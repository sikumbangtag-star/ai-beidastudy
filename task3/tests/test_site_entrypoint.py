import unittest
from pathlib import Path


class SiteEntrypointTests(unittest.TestCase):
    def test_root_index_links_to_task3_panel(self):
        root = Path(__file__).resolve().parents[2]
        html = (root / "index.html").read_text(encoding="utf-8")

        self.assertIn("task3/design/dual_ma_strategy_panel.html", html)
        self.assertIn("task2/design/multi_stock_indicator_panel.html", html)
        self.assertIn("task1/outputs/jinan_guoji/index.html", html)
        self.assertIn("Task3", html)
        self.assertIn("Task2", html)
        self.assertIn("Task1", html)

    def test_root_index_does_not_auto_redirect(self):
        root = Path(__file__).resolve().parents[2]
        html = (root / "index.html").read_text(encoding="utf-8")

        self.assertNotIn("http-equiv=\"refresh\"", html)
        self.assertNotIn("window.location.replace", html)


if __name__ == "__main__":
    unittest.main()
