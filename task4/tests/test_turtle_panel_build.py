import unittest
from pathlib import Path

from task4.scripts.build_turtle_panel import render_panel_html
from task4.tests.test_turtle_strategy import benchmark_rows, stock_rows


class TurtlePanelBuildTests(unittest.TestCase):
    def test_render_panel_html_contains_turtle_dashboard_targets(self):
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
            "variantSelect",
            "short_20_10",
            "long_55_20",
            "turtlePriceChart",
            "turtleNavChart",
            "turtleMetrics",
            "tradeRows",
            "computeTurtleStrategy",
            "entry_channel",
            "exit_channel",
        ]:
            self.assertIn(marker, html)

    def test_task4_spec_file_describes_dual_turtle_variants(self):
        root = Path(__file__).resolve().parents[2]
        spec = (root / "task4" / "specs" / "turtle_strategy_spec.md").read_text(encoding="utf-8")

        self.assertIn("20/10", spec)
        self.assertIn("55/20", spec)
        self.assertIn("海龟策略", spec)
        self.assertIn("T+1", spec)

    def test_turtle_charts_do_not_truncate_long_cycle_signals(self):
        payload = {
            "start_date": "20260101",
            "end_date": "20260108",
            "benchmark": {"ts_code": "000300.SH", "name": "沪深300", "rows": benchmark_rows()},
            "stocks": [{"ts_code": "002636.SZ", "name": "金安国纪", "rows": stock_rows()}],
        }

        html = render_panel_html(payload)

        self.assertNotIn("result.rows.slice(-220)", html)
        self.assertIn("const rows = result.rows;", html)

    def test_line_path_restarts_after_null_channel_values(self):
        payload = {
            "start_date": "20260101",
            "end_date": "20260108",
            "benchmark": {"ts_code": "000300.SH", "name": "沪深300", "rows": benchmark_rows()},
            "stocks": [{"ts_code": "002636.SZ", "name": "金安国纪", "rows": stock_rows()}],
        }

        html = render_panel_html(payload)

        self.assertIn("started = false", html)
        self.assertIn('const command = started ? "L" : "M";', html)

    def test_turtle_windows_are_adjustable_parameters(self):
        payload = {
            "start_date": "20260101",
            "end_date": "20260108",
            "benchmark": {"ts_code": "000300.SH", "name": "沪深300", "rows": benchmark_rows()},
            "stocks": [{"ts_code": "002636.SZ", "name": "金安国纪", "rows": stock_rows()}],
        }

        html = render_panel_html(payload)

        self.assertIn('id="entryWindow" type="range"', html)
        self.assertIn('id="exitWindow" type="range"', html)
        self.assertIn('id="entryWindowValue"', html)
        self.assertIn('id="exitWindowValue"', html)
        self.assertIn("syncTurtleWindows", html)
        self.assertIn("applyVariantPreset", html)
        self.assertIn('Number(byId("entryWindow").value)', html)
        self.assertIn('Number(byId("exitWindow").value)', html)

    def test_turtle_panel_displays_atr_value(self):
        payload = {
            "start_date": "20260101",
            "end_date": "20260108",
            "benchmark": {"ts_code": "000300.SH", "name": "000300", "rows": benchmark_rows()},
            "stocks": [{"ts_code": "002636.SZ", "name": "002636", "rows": stock_rows()}],
        }

        html = render_panel_html(payload)

        self.assertIn("function trueRange", html)
        self.assertIn("function calculateAtr", html)
        self.assertIn("latest_atr", html)
        self.assertIn("latest_atr_pct", html)
        self.assertIn("ATR(20)", html)

    def test_strategy_parameters_are_in_left_sidebar(self):
        payload = {
            "start_date": "20260101",
            "end_date": "20260108",
            "benchmark": {"ts_code": "000300.SH", "name": "000300", "rows": benchmark_rows()},
            "stocks": [{"ts_code": "002636.SZ", "name": "002636", "rows": stock_rows()}],
        }

        html = render_panel_html(payload)

        self.assertIn('class="workbench"', html)
        self.assertIn('class="panel strategy-sidebar"', html)
        self.assertIn('class="dashboard-content"', html)
        sidebar_start = html.index('class="panel strategy-sidebar"')
        sidebar_end = html.index('class="dashboard-content"')
        self.assertGreater(html.index('id="variantSelect"'), sidebar_start)
        self.assertLess(html.index('id="variantSelect"'), sidebar_end)
        self.assertLess(html.index('id="entryWindow"'), sidebar_end)
        topbar = html[html.index('<header class="topbar">'):html.index('</header>')]
        self.assertNotIn('id="variantSelect"', topbar)

    def test_sidebar_explains_cost_rates_and_exit_rule(self):
        payload = {
            "start_date": "20260101",
            "end_date": "20260108",
            "benchmark": {"ts_code": "000300.SH", "name": "000300", "rows": benchmark_rows()},
            "stocks": [{"ts_code": "002636.SZ", "name": "002636", "rows": stock_rows()}],
        }

        html = render_panel_html(payload)

        self.assertIn("买入成本率 0.0005441", html)
        self.assertIn("卖出成本率 0.0010441", html)
        self.assertIn("跌破出场低价通道", html)
        self.assertIn("ATR 仅作为波动指标展示", html)

    def test_panel_supports_atr_stop_and_position_sizing(self):
        payload = {
            "start_date": "20260101",
            "end_date": "20260108",
            "benchmark": {"ts_code": "000300.SH", "name": "000300", "rows": benchmark_rows()},
            "stocks": [{"ts_code": "002636.SZ", "name": "002636", "rows": stock_rows()}],
        }

        html = render_panel_html(payload)

        for marker in [
            'id="stopMode"',
            'value="channel"',
            'value="atr"',
            'value="both"',
            'id="atrWindow"',
            'id="atrMultiplier"',
            'id="riskPerTrade"',
            'id="maxPosition"',
            "function positionSizeByAtr",
            "atr_stop_price",
            "stop_reason",
            "atr_stop_count",
            'byId("stopMode").value',
            'Number(byId("riskPerTrade").value)',
        ]:
            self.assertIn(marker, html)


if __name__ == "__main__":
    unittest.main()
