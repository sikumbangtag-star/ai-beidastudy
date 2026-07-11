import unittest

from task3.src.dual_ma_strategy import BUY_COST_RATE, SELL_COST_RATE, compute_dual_ma_strategy


def stock_rows():
    dates = ["20260101", "20260102", "20260103", "20260104", "20260105", "20260106", "20260107", "20260108"]
    closes = [10, 9, 10, 12, 13, 11, 9, 8]
    opens = [10.2, 8.5, 9.5, 11.5, 12.8, 11.2, 9.4, 8.2]
    rows = []
    for index, (trade_date, open_price, close_price) in enumerate(zip(dates, opens, closes)):
        rows.append(
            {
                "trade_date": trade_date,
                "open": open_price,
                "high": max(open_price, close_price) + 0.5,
                "low": min(open_price, close_price) - 0.5,
                "close": close_price,
                "pre_close": closes[index - 1] if index else close_price,
                "change": 0,
                "pct_chg": 0,
                "vol": 1000 + index,
                "amount": 10000 + index,
            }
        )
    return rows


def benchmark_rows(market_up_on_signal=True):
    closes = [100, 99, 100, 101 if market_up_on_signal else 99, 102, 101, 100, 98]
    rows = []
    for index, close_price in enumerate(closes):
        rows.append(
            {
                "trade_date": f"2026010{index + 1}",
                "open": close_price - 0.2,
                "high": close_price + 0.8,
                "low": close_price - 1,
                "close": close_price,
                "pre_close": closes[index - 1] if index else close_price,
                "change": 0,
                "pct_chg": 0,
                "vol": 0,
                "amount": 0,
            }
        )
    return rows


class DualMaStrategyTests(unittest.TestCase):
    def test_fast_window_must_be_less_than_slow_window(self):
        with self.assertRaises(ValueError):
            compute_dual_ma_strategy(stock_rows(), benchmark_rows(), fast_window=3, slow_window=3)

    def test_golden_cross_filters_and_next_open_execution(self):
        result = compute_dual_ma_strategy(stock_rows(), benchmark_rows(), fast_window=2, slow_window=3)

        trades = result["trades"]
        self.assertEqual(len(trades), 2)
        self.assertEqual(trades[0]["side"], "BUY")
        self.assertEqual(trades[0]["signal_date"], "20260104")
        self.assertEqual(trades[0]["trade_date"], "20260105")
        self.assertAlmostEqual(trades[0]["price"], 12.8)
        self.assertEqual(trades[0]["cost_rate"], BUY_COST_RATE)
        self.assertTrue(trades[0]["three_bullish"])
        self.assertTrue(trades[0]["market_up"])

        self.assertEqual(trades[1]["side"], "SELL")
        self.assertEqual(trades[1]["signal_date"], "20260107")
        self.assertEqual(trades[1]["trade_date"], "20260108")
        self.assertAlmostEqual(trades[1]["price"], 8.2)
        self.assertEqual(trades[1]["cost_rate"], SELL_COST_RATE)

        metrics = result["metrics"]
        self.assertEqual(metrics["golden_cross_count"], 1)
        self.assertEqual(metrics["effective_buy_count"], 1)
        self.assertEqual(metrics["filtered_buy_count"], 0)
        self.assertEqual(metrics["trade_count"], 2)
        self.assertLess(metrics["strategy_return"], 0)
        self.assertGreater(metrics["total_cost"], 0)

    def test_filtered_golden_cross_does_not_buy_or_delay(self):
        result = compute_dual_ma_strategy(
            stock_rows(),
            benchmark_rows(market_up_on_signal=False),
            fast_window=2,
            slow_window=3,
        )

        self.assertEqual(result["metrics"]["golden_cross_count"], 1)
        self.assertEqual(result["metrics"]["effective_buy_count"], 0)
        self.assertEqual(result["metrics"]["filtered_buy_count"], 1)
        self.assertEqual(result["trades"], [])


if __name__ == "__main__":
    unittest.main()
