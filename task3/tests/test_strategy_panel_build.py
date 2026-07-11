import unittest

from task3.scripts.build_strategy_panel import render_panel_html
from task3.tests.test_dual_ma_strategy import benchmark_rows, stock_rows


class StrategyPanelBuildTests(unittest.TestCase):
    def test_render_panel_html_contains_strategy_targets(self):
        payload = {
            "start_date": "20260101",
            "end_date": "20260108",
            "benchmark": {"ts_code": "000300.SH", "name": "沪深300", "rows": benchmark_rows()},
            "stocks": [{"ts_code": "002636.SZ", "name": "金安国纪", "rows": stock_rows()}],
        }

        html = render_panel_html(payload)

        for marker in [
            "APP_DATA",
            "stockSelect",
            "fastMaWindow",
            "slowMaWindow",
            "requireThreeBullish",
            "requireMarketUp",
            "strategyPriceChart",
            "strategyNavChart",
            "strategyMetrics",
            "tradeRows",
            "computeDualMaStrategy",
            "benchmark",
        ]:
            self.assertIn(marker, html)

    def test_strategy_parameters_are_slider_controls_with_live_values(self):
        payload = {
            "start_date": "20260101",
            "end_date": "20260108",
            "benchmark": {"ts_code": "000300.SH", "name": "沪深300", "rows": benchmark_rows()},
            "stocks": [{"ts_code": "002636.SZ", "name": "金安国纪", "rows": stock_rows()}],
        }

        html = render_panel_html(payload)

        self.assertIn('id="fastMaWindow" type="range"', html)
        self.assertIn('id="slowMaWindow" type="range"', html)
        self.assertIn('id="displayCount" type="range"', html)
        self.assertIn('id="fastMaValue"', html)
        self.assertIn('id="slowMaValue"', html)
        self.assertIn('id="displayCountValue"', html)
        self.assertIn("syncSliderValues", html)
        self.assertIn('input[type=range]', html)

    def test_metrics_section_appears_before_parameter_and_signal_chart(self):
        payload = {
            "start_date": "20260101",
            "end_date": "20260108",
            "benchmark": {"ts_code": "000300.SH", "name": "沪深300", "rows": benchmark_rows()},
            "stocks": [{"ts_code": "002636.SZ", "name": "金安国纪", "rows": stock_rows()}],
        }

        html = render_panel_html(payload)

        metrics_index = html.index('id="strategyMetrics"')
        params_index = html.index("策略参数")
        chart_index = html.index('id="strategyPriceChart"')
        self.assertLess(metrics_index, params_index)
        self.assertLess(metrics_index, chart_index)


if __name__ == "__main__":
    unittest.main()
