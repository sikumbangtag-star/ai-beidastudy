import unittest

import pandas as pd

from task6.src.ml_strategy_backtest import (
    BUY_COST_RATE,
    SELL_COST_RATE,
    add_growth_score,
    linked_total_return,
    split_by_dates,
)


class Task6StrategyTests(unittest.TestCase):
    def test_net_return_formula(self):
        buy_open = 10.0
        sell_close = 11.0
        expected = sell_close * (1 - SELL_COST_RATE) / (buy_open * (1 + BUY_COST_RATE)) - 1
        self.assertAlmostEqual(expected, 0.098254, places=5)

    def test_growth_score_uses_weighted_components(self):
        df = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2022-06-30"] * 3),
                "净利润同比增长率": [1, 2, 3],
                "营业利润(同比增长率)": [1, 2, 3],
                "营业总收入(同比增长率)": [1, 2, 3],
                "基本每股收益(同比增长率)": [1, 2, 3],
            }
        )
        out = add_growth_score(df)
        self.assertTrue(out["growth_score"].is_monotonic_increasing)
        self.assertAlmostEqual(out["growth_score"].iloc[-1], 1.0)

    def test_split_by_dates_uses_60_20_20(self):
        rows = []
        for date in pd.to_datetime(["2021-06-30", "2021-09-30", "2021-12-31", "2022-03-31", "2022-06-30"]):
            for code in ["000001", "000002"]:
                rows.append({"Date": date, "Code": code})
        train, valid, test = split_by_dates(pd.DataFrame(rows))
        self.assertEqual(train["Date"].nunique(), 3)
        self.assertEqual(valid["Date"].nunique(), 1)
        self.assertEqual(test["Date"].nunique(), 1)

    def test_linked_total_return_uses_ex_right_reference_price(self):
        rows = pd.DataFrame(
            {
                "trade_date": ["20220103", "20220104", "20220105"],
                "open": [10.0, 11.0, 12.0],
                "close": [11.0, 12.0, 13.0],
                # The 20220104 reference price reflects an ex-right adjustment.
                "pre_close": [9.5, 10.0, 12.0],
            }
        )
        expected = 11 / 10 * (12 / 10) * (13 / 12) - 1
        self.assertAlmostEqual(linked_total_return(rows, "20220103", "20220105"), expected)


if __name__ == "__main__":
    unittest.main()
