import tempfile
import unittest
from pathlib import Path

import pandas as pd

from task2.src.indicators import add_all_indicators, clean_price_data, latest_indicator_summary
from task2.src.reporting import (
    build_summary_markdown,
    write_all_svg_charts,
)


class ReportingTests(unittest.TestCase):
    def sample_indicator_data(self):
        rows = []
        dates = pd.date_range("2025-01-01", periods=40, freq="D").strftime("%Y%m%d")
        for idx in range(40):
            close = 10 + idx * 0.2 + (0.15 if idx % 3 == 0 else -0.05)
            rows.append(
                {
                    "trade_date": dates[idx],
                    "ts_code": "002636.SZ",
                    "open": close - 0.1,
                    "high": close + 0.35,
                    "low": close - 0.45,
                    "close": close,
                    "pre_close": close - 0.2,
                    "vol": 1000 + idx * 50,
                    "amount": 10000 + idx * 100,
                    "change": 0.0,
                    "pct_chg": 0.0,
                }
            )
        return add_all_indicators(clean_price_data(pd.DataFrame(rows)))

    def test_build_summary_markdown_contains_indicator_sections(self):
        data = self.sample_indicator_data()
        markdown = build_summary_markdown(latest_indicator_summary(data))

        self.assertIn("# 金安国纪 Task2 指标摘要", markdown)
        self.assertIn("RSI", markdown)
        self.assertIn("MACD", markdown)
        self.assertIn("布林带", markdown)
        self.assertIn("ATR", markdown)

    def test_write_all_svg_charts_creates_expected_files(self):
        data = self.sample_indicator_data()

        with tempfile.TemporaryDirectory() as tmp:
            paths = write_all_svg_charts(data, Path(tmp))
            names = {path.name for path in paths}

            self.assertEqual(
                names,
                {
                    "price_bollinger.svg",
                    "volume.svg",
                    "rsi.svg",
                    "macd.svg",
                    "atr.svg",
                },
            )
            for path in paths:
                text = path.read_text(encoding="utf-8")
                self.assertIn("<svg", text)
                self.assertIn("</svg>", text)


if __name__ == "__main__":
    unittest.main()
