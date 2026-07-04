import unittest

from task2.scripts.build_multi_stock_panel import STOCKS, render_multi_stock_html


class MultiStockPanelTests(unittest.TestCase):
    def test_stock_universe_contains_requested_names_and_codes(self):
        names = {stock["name"] for stock in STOCKS}
        codes = {stock["ts_code"] for stock in STOCKS}

        self.assertEqual(
            names,
            {"金安国纪", "中际旭创", "德明利", "三环集团", "五洲新春"},
        )
        self.assertEqual(
            codes,
            {"002636.SZ", "300308.SZ", "001309.SZ", "300408.SZ", "603667.SH"},
        )

    def test_render_multi_stock_html_embeds_data_and_switch_handler(self):
        payload = {
            "stocks": [
                {"ts_code": "002636.SZ", "name": "金安国纪", "rows": [{"trade_date": "20260703", "close": 1}]},
                {"ts_code": "300308.SZ", "name": "中际旭创", "rows": [{"trade_date": "20260703", "close": 2}]},
            ]
        }

        html = render_multi_stock_html(payload)

        self.assertIn("股票技术指标交互分析工具", html)
        self.assertIn("金安国纪", html)
        self.assertIn("中际旭创", html)
        self.assertIn("stockSelect", html)
        self.assertIn("renderDashboard", html)
        self.assertIn("APP_DATA", html)


if __name__ == "__main__":
    unittest.main()
