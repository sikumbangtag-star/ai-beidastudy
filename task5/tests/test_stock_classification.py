import unittest

import numpy as np
import pandas as pd

from task5.src.stock_classification import (
    auc_score,
    build_eda_payload,
    build_feature_frame,
    fit_all_models,
    prepare_dataset,
    roc_curve_points,
    split_by_date_order,
)


def sample_frame(rows=90):
    dates = pd.date_range("2021-01-01", periods=(rows + 9) // 10, freq="ME")
    data = []
    for i in range(rows):
        value = i / rows
        data.append(
            {
                "Date": dates[i // 10].strftime("%Y-%m-%d"),
                "Code": 1000 + i,
                "factor_a": value,
                "factor_b": (i % 7) - 3,
                "factor_c": np.nan if i % 13 == 0 else value * 2,
                "Y": value > 0.52,
            }
        )
    return pd.DataFrame(data)


class StockClassificationTests(unittest.TestCase):
    def test_prepare_dataset_maps_boolean_target_to_zero_one(self):
        prepared = prepare_dataset(sample_frame())

        self.assertEqual(set(prepared["Y"].unique()), {0, 1})
        self.assertEqual(prepared["Y"].dtype.kind, "i")

    def test_split_by_date_order_uses_70_20_10_rows(self):
        prepared = prepare_dataset(sample_frame(100))
        train, valid, test = split_by_date_order(prepared)

        self.assertEqual(len(train), 70)
        self.assertEqual(len(valid), 20)
        self.assertEqual(len(test), 10)
        self.assertLessEqual(train["Date"].max(), valid["Date"].max())
        self.assertLessEqual(valid["Date"].max(), test["Date"].max())

    def test_auc_and_roc_are_computable(self):
        y_true = np.array([0, 0, 1, 1])
        score = np.array([0.1, 0.4, 0.35, 0.8])

        self.assertAlmostEqual(auc_score(y_true, score), 0.75)
        roc = roc_curve_points(y_true, score)
        self.assertEqual(roc[0], (0.0, 0.0))
        self.assertEqual(roc[-1], (1.0, 1.0))

    def test_all_models_return_validation_and_test_scores(self):
        prepared = prepare_dataset(sample_frame(120))
        train, valid, test = split_by_date_order(prepared)
        features = build_feature_frame(train, valid, test)
        result = fit_all_models(features)

        self.assertEqual(
            set(result["metrics"]["model"]),
            {"linear_regression", "logistic_regression", "decision_tree", "random_forest"},
        )
        self.assertTrue(result["predictions"]["score"].between(0, 1).all())
        self.assertEqual(set(result["predictions"]["split"]), {"valid", "test"})

    def test_eda_payload_contains_distribution_correlation_confusion_and_importance(self):
        prepared = prepare_dataset(sample_frame(120))
        train, valid, test = split_by_date_order(prepared)
        features = build_feature_frame(train, valid, test)
        result = fit_all_models(features)
        payload = build_eda_payload(prepared, features, result)

        self.assertIn("target_distribution", payload)
        self.assertIn("correlation_matrix", payload)
        self.assertIn("feature_importance", payload)
        self.assertIn("tp", result["metrics"].columns)
        self.assertIn("fp", result["metrics"].columns)
        self.assertEqual(set(result["feature_importance"]["model"]), {"linear_regression", "logistic_regression", "decision_tree", "random_forest"})


if __name__ == "__main__":
    unittest.main()
