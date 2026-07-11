import unittest

from task4.src.turtle_strategy import BUY_COST_RATE, SELL_COST_RATE, compute_turtle_strategy


def stock_rows():
    dates = [
        "20260101",
        "20260102",
        "20260103",
        "20260104",
        "20260105",
        "20260106",
        "20260107",
        "20260108",
    ]
    opens = [10.0, 10.2, 10.4, 10.7, 12.0, 11.0, 9.5, 8.0]
    closes = [10.1, 10.3, 10.5, 11.5, 11.2, 9.6, 8.8, 8.2]
    highs = [10.4, 10.6, 10.8, 11.8, 12.2, 11.1, 9.7, 8.5]
    lows = [9.8, 10.0, 10.2, 10.6, 10.9, 9.4, 8.6, 7.9]
    rows = []
    for index, trade_date in enumerate(dates):
        rows.append(
            {
                "trade_date": trade_date,
                "open": opens[index],
                "high": highs[index],
                "low": lows[index],
                "close": closes[index],
                "pre_close": closes[index - 1] if index else closes[index],
                "change": 0,
                "pct_chg": 0,
                "vol": 1000 + index,
                "amount": 10000 + index,
            }
        )
    return rows


def benchmark_rows():
    closes = [100, 101, 102, 103, 104, 102, 101, 100]
    return [
        {
            "trade_date": f"2026010{index + 1}",
            "open": close - 0.2,
            "high": close + 0.8,
            "low": close - 1,
            "close": close,
            "pre_close": closes[index - 1] if index else close,
            "change": 0,
            "pct_chg": 0,
            "vol": 0,
            "amount": 0,
        }
        for index, close in enumerate(closes)
    ]


class TurtleStrategyTests(unittest.TestCase):
    def test_turtle_variant_parameters_are_supported(self):
        short = compute_turtle_strategy(stock_rows(), benchmark_rows(), variant="short_20_10", entry_window=3, exit_window=2)
        long = compute_turtle_strategy(stock_rows(), benchmark_rows(), variant="long_55_20", entry_window=4, exit_window=3)

        self.assertEqual(short["metrics"]["variant"], "short_20_10")
        self.assertEqual(short["metrics"]["entry_window"], 3)
        self.assertEqual(short["metrics"]["exit_window"], 2)
        self.assertEqual(long["metrics"]["variant"], "long_55_20")

    def test_entry_channel_uses_previous_days_without_lookahead(self):
        result = compute_turtle_strategy(stock_rows(), benchmark_rows(), variant="short_20_10", entry_window=3, exit_window=2)
        rows = result["rows"]

        self.assertIsNone(rows[2]["entry_channel"])
        self.assertAlmostEqual(rows[3]["entry_channel"], 10.8)
        self.assertTrue(rows[3]["entry_breakout"])

    def test_breakout_buys_next_open_and_exit_sells_next_open_with_costs(self):
        result = compute_turtle_strategy(stock_rows(), benchmark_rows(), variant="short_20_10", entry_window=3, exit_window=2)

        trades = result["trades"]
        self.assertEqual(len(trades), 2)
        self.assertEqual(trades[0]["side"], "BUY")
        self.assertEqual(trades[0]["signal_date"], "20260104")
        self.assertEqual(trades[0]["trade_date"], "20260105")
        self.assertAlmostEqual(trades[0]["price"], 12.0)
        self.assertEqual(trades[0]["cost_rate"], BUY_COST_RATE)

        self.assertEqual(trades[1]["side"], "SELL")
        self.assertEqual(trades[1]["signal_date"], "20260106")
        self.assertEqual(trades[1]["trade_date"], "20260107")
        self.assertAlmostEqual(trades[1]["price"], 9.5)
        self.assertEqual(trades[1]["cost_rate"], SELL_COST_RATE)

        metrics = result["metrics"]
        self.assertEqual(metrics["entry_breakout_count"], 1)
        self.assertEqual(metrics["effective_buy_count"], 1)
        self.assertEqual(metrics["exit_breakout_count"], 1)
        self.assertEqual(metrics["effective_sell_count"], 1)
        self.assertEqual(metrics["trade_count"], 2)
        self.assertLess(metrics["strategy_return"], 0)
        self.assertIn("benchmark_return", metrics)
        self.assertIn("max_drawdown", metrics)


if __name__ == "__main__":
    unittest.main()
