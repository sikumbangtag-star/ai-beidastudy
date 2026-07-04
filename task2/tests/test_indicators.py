import unittest
from pathlib import Path

import pandas as pd

from task2.src.indicators import (
    add_all_indicators,
    clean_price_data,
    latest_indicator_summary,
)


class IndicatorTests(unittest.TestCase):
    def sample_prices(self):
        rows = []
        closes = [
            10.0, 10.3, 10.1, 10.5, 10.8, 10.6, 10.9, 11.2, 11.0, 11.4,
            11.7, 11.5, 11.9, 12.2, 12.0, 12.4, 12.7, 12.5, 12.9, 13.2,
            13.0, 13.4, 13.7, 13.5, 13.9, 14.2, 14.0, 14.4, 14.7, 14.5,
        ]
        for idx, close in enumerate(closes):
            rows.append(
                {
                    "trade_date": 20250101 + idx,
                    "ts_code": "002636.SZ",
                    "open": close - 0.1,
                    "high": close + 0.3,
                    "low": close - 0.4,
                    "close": close,
                    "pre_close": closes[idx - 1] if idx else close - 0.2,
                    "vol": 1000 + idx * 10,
                    "amount": 10000 + idx * 100,
                    "change": 0.0,
                    "pct_chg": 0.0,
                }
            )
        return pd.DataFrame(rows)

    def test_clean_price_data_sorts_dates_and_casts_numbers(self):
        raw = self.sample_prices().iloc[::-1].copy()
        cleaned = clean_price_data(raw)

        self.assertTrue(cleaned["trade_date"].is_monotonic_increasing)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(cleaned["trade_date"]))
        self.assertTrue(pd.api.types.is_float_dtype(cleaned["close"]))

    def test_clean_price_data_rejects_missing_required_columns(self):
        raw = self.sample_prices().drop(columns=["high"])

        with self.assertRaisesRegex(ValueError, "Missing required columns: high"):
            clean_price_data(raw)

    def test_add_all_indicators_creates_expected_columns(self):
        cleaned = clean_price_data(self.sample_prices())
        result = add_all_indicators(cleaned)

        expected = {
            "rsi_14",
            "macd_dif",
            "macd_dea",
            "macd_hist",
            "boll_mid",
            "boll_upper",
            "boll_lower",
            "boll_width",
            "tr",
            "atr_14",
        }
        self.assertTrue(expected.issubset(result.columns))
        self.assertGreater(result["rsi_14"].dropna().iloc[-1], 0)
        self.assertLessEqual(result["rsi_14"].dropna().iloc[-1], 100)
        self.assertGreater(result["atr_14"].dropna().iloc[-1], 0)
        self.assertGreater(result["boll_upper"].dropna().iloc[-1], result["boll_lower"].dropna().iloc[-1])

    def test_latest_indicator_summary_returns_readable_fields(self):
        result = add_all_indicators(clean_price_data(self.sample_prices()))
        summary = latest_indicator_summary(result)

        self.assertEqual(summary["ts_code"], "002636.SZ")
        self.assertIn("rsi_view", summary)
        self.assertIn("macd_view", summary)
        self.assertIn("boll_view", summary)
        self.assertIn("atr_view", summary)


if __name__ == "__main__":
    unittest.main()
