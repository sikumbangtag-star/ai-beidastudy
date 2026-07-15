from __future__ import annotations

import math
import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
TASK5 = ROOT / "task5"
DATA_PATH = TASK5 / "data" / "model_data_stock.csv"
OUTPUT_DIR = TASK5 / "outputs"
FIGURE_DIR = OUTPUT_DIR / "figures"

ID_COLUMNS = ["Date", "Code"]
TARGET_COLUMN = "Y"
MODEL_NAMES = ["linear_regression", "logistic_regression", "decision_tree", "random_forest"]
MODEL_DISPLAY_NAMES = {
    "linear_regression": "线性回归",
    "logistic_regression": "逻辑回归",
    "decision_tree": "决策树",
    "random_forest": "随机森林",
}


def load_raw_data(path: str | Path = DATA_PATH) -> pd.DataFrame:
    return pd.read_csv(path)


def prepare_dataset(df: pd.DataFrame) -> pd.DataFrame:
    required = set(ID_COLUMNS + [TARGET_COLUMN])
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    prepared = df.copy()
    prepared["Date"] = pd.to_datetime(prepared["Date"])
    prepared["Code"] = prepared["Code"].astype(str)
    prepared[TARGET_COLUMN] = prepared[TARGET_COLUMN].map(_target_to_int).astype(int)

    for column in feature_columns(prepared):
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

    return prepared.sort_values(["Date", "Code"]).reset_index(drop=True)


def _target_to_int(value) -> int:
    if isinstance(value, str):
        return 1 if value.strip().lower() in {"true", "1", "yes", "y"} else 0
    return int(bool(value))


def feature_columns(df: pd.DataFrame) -> list[str]:
    return [column for column in df.columns if column not in ID_COLUMNS + [TARGET_COLUMN]]


def split_by_date_order(df: pd.DataFrame, train_ratio: float = 0.7, valid_ratio: float = 0.2):
    ordered = df.sort_values(["Date", "Code"]).reset_index(drop=True)
    train_end = int(len(ordered) * train_ratio)
    valid_end = train_end + int(len(ordered) * valid_ratio)
    train = ordered.iloc[:train_end].copy()
    valid = ordered.iloc[train_end:valid_end].copy()
    test = ordered.iloc[valid_end:].copy()
    return train, valid, test


@dataclass
class FeatureData:
    columns: list[str]
    train_meta: pd.DataFrame
    valid_meta: pd.DataFrame
    test_meta: pd.DataFrame
    x_train_raw: np.ndarray
    x_valid_raw: np.ndarray
    x_test_raw: np.ndarray
    x_train_scaled: np.ndarray
    x_valid_scaled: np.ndarray
    x_test_scaled: np.ndarray
    y_train: np.ndarray
    y_valid: np.ndarray
    y_test: np.ndarray
    medians: pd.Series
    means: np.ndarray
    stds: np.ndarray


def build_feature_frame(train: pd.DataFrame, valid: pd.DataFrame, test: pd.DataFrame) -> FeatureData:
    columns = feature_columns(train)
    medians = train[columns].median(numeric_only=True).fillna(0)

    def matrix(part: pd.DataFrame) -> np.ndarray:
        return part[columns].fillna(medians).to_numpy(dtype=float)

    x_train = matrix(train)
    x_valid = matrix(valid)
    x_test = matrix(test)
    means = x_train.mean(axis=0)
    stds = x_train.std(axis=0)
    stds[stds == 0] = 1

    return FeatureData(
        columns=columns,
        train_meta=train[ID_COLUMNS + [TARGET_COLUMN]].copy(),
        valid_meta=valid[ID_COLUMNS + [TARGET_COLUMN]].copy(),
        test_meta=test[ID_COLUMNS + [TARGET_COLUMN]].copy(),
        x_train_raw=x_train,
        x_valid_raw=x_valid,
        x_test_raw=x_test,
        x_train_scaled=(x_train - means) / stds,
        x_valid_scaled=(x_valid - means) / stds,
        x_test_scaled=(x_test - means) / stds,
        y_train=train[TARGET_COLUMN].to_numpy(dtype=int),
        y_valid=valid[TARGET_COLUMN].to_numpy(dtype=int),
        y_test=test[TARGET_COLUMN].to_numpy(dtype=int),
        medians=medians,
        means=means,
        stds=stds,
    )


def add_intercept(x: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(x)), x])


def fit_linear_regression(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    coef, *_ = np.linalg.lstsq(add_intercept(x), y.astype(float), rcond=None)
    return coef


def predict_linear_regression(coef: np.ndarray, x: np.ndarray) -> np.ndarray:
    return np.clip(add_intercept(x) @ coef, 0, 1)


def sigmoid(values: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(values, -35, 35)))


def fit_logistic_regression(
    x: np.ndarray,
    y: np.ndarray,
    learning_rate: float = 0.08,
    epochs: int = 900,
    l2: float = 0.001,
) -> np.ndarray:
    xb = add_intercept(x)
    weights = np.zeros(xb.shape[1], dtype=float)
    y_float = y.astype(float)
    for _ in range(epochs):
        pred = sigmoid(xb @ weights)
        grad = xb.T @ (pred - y_float) / len(y_float)
        grad[1:] += l2 * weights[1:]
        weights -= learning_rate * grad
    return weights


def predict_logistic_regression(weights: np.ndarray, x: np.ndarray) -> np.ndarray:
    return sigmoid(add_intercept(x) @ weights)


@dataclass
class TreeNode:
    probability: float
    feature_index: int | None = None
    threshold: float | None = None
    left: "TreeNode | None" = None
    right: "TreeNode | None" = None

    @property
    def is_leaf(self) -> bool:
        return self.feature_index is None


class SimpleDecisionTree:
    def __init__(
        self,
        max_depth: int = 5,
        min_samples_leaf: int = 80,
        max_thresholds: int = 16,
        max_features: int | None = None,
        random_state: int = 42,
    ):
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.max_thresholds = max_thresholds
        self.max_features = max_features
        self.random = np.random.default_rng(random_state)
        self.root: TreeNode | None = None

    def fit(self, x: np.ndarray, y: np.ndarray):
        self.root = self._build(x, y, depth=0)
        return self

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        if self.root is None:
            raise ValueError("Tree has not been fitted.")
        return np.array([self._predict_row(row, self.root) for row in x])

    def _predict_row(self, row: np.ndarray, node: TreeNode) -> float:
        while not node.is_leaf:
            assert node.feature_index is not None and node.threshold is not None
            node = node.left if row[node.feature_index] <= node.threshold else node.right
            assert node is not None
        return node.probability

    def _build(self, x: np.ndarray, y: np.ndarray, depth: int) -> TreeNode:
        probability = float(y.mean()) if len(y) else 0.0
        node = TreeNode(probability=probability)
        if depth >= self.max_depth or len(y) < self.min_samples_leaf * 2 or len(np.unique(y)) == 1:
            return node

        split = self._best_split(x, y)
        if split is None:
            return node

        feature_index, threshold = split
        mask = x[:, feature_index] <= threshold
        node.feature_index = feature_index
        node.threshold = threshold
        node.left = self._build(x[mask], y[mask], depth + 1)
        node.right = self._build(x[~mask], y[~mask], depth + 1)
        return node

    def _best_split(self, x: np.ndarray, y: np.ndarray):
        feature_indices = np.arange(x.shape[1])
        if self.max_features and self.max_features < len(feature_indices):
            feature_indices = self.random.choice(feature_indices, size=self.max_features, replace=False)

        base_score = gini(y)
        best_gain = 0.0
        best = None
        for feature_index in feature_indices:
            values = x[:, feature_index]
            thresholds = candidate_thresholds(values, self.max_thresholds)
            for threshold in thresholds:
                left = values <= threshold
                right = ~left
                if left.sum() < self.min_samples_leaf or right.sum() < self.min_samples_leaf:
                    continue
                score = (left.sum() * gini(y[left]) + right.sum() * gini(y[right])) / len(y)
                gain = base_score - score
                if gain > best_gain:
                    best_gain = gain
                    best = (int(feature_index), float(threshold))
        return best


def candidate_thresholds(values: np.ndarray, max_thresholds: int) -> np.ndarray:
    values = values[np.isfinite(values)]
    unique = np.unique(values)
    if len(unique) <= 1:
        return np.array([])
    if len(unique) <= max_thresholds:
        return (unique[:-1] + unique[1:]) / 2
    quantiles = np.linspace(0.05, 0.95, max_thresholds)
    return np.unique(np.quantile(unique, quantiles))


def gini(y: np.ndarray) -> float:
    if len(y) == 0:
        return 0.0
    p = float(y.mean())
    return 1 - p**2 - (1 - p) ** 2


class SimpleRandomForest:
    def __init__(
        self,
        n_estimators: int = 35,
        max_depth: int = 5,
        min_samples_leaf: int = 80,
        random_state: int = 42,
    ):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.random_state = random_state
        self.trees: list[SimpleDecisionTree] = []

    def fit(self, x: np.ndarray, y: np.ndarray):
        rng = np.random.default_rng(self.random_state)
        max_features = max(1, int(math.sqrt(x.shape[1])))
        self.trees = []
        for i in range(self.n_estimators):
            sample_index = rng.integers(0, len(y), size=len(y))
            tree = SimpleDecisionTree(
                max_depth=self.max_depth,
                min_samples_leaf=self.min_samples_leaf,
                max_features=max_features,
                random_state=self.random_state + i + 1,
            )
            tree.fit(x[sample_index], y[sample_index])
            self.trees.append(tree)
        return self

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        if not self.trees:
            raise ValueError("Forest has not been fitted.")
        return np.mean([tree.predict_proba(x) for tree in self.trees], axis=0)


def fit_all_models(features: FeatureData) -> dict[str, pd.DataFrame]:
    predictions = []
    metrics = []
    model_importances = []

    model_scores = {}

    linear_coef = fit_linear_regression(features.x_train_scaled, features.y_train)
    model_scores["linear_regression"] = {
        "valid": predict_linear_regression(linear_coef, features.x_valid_scaled),
        "test": predict_linear_regression(linear_coef, features.x_test_scaled),
    }
    model_importances.extend(coef_importance("linear_regression", features.columns, linear_coef[1:]))

    logistic_weights = fit_logistic_regression(features.x_train_scaled, features.y_train)
    model_scores["logistic_regression"] = {
        "valid": predict_logistic_regression(logistic_weights, features.x_valid_scaled),
        "test": predict_logistic_regression(logistic_weights, features.x_test_scaled),
    }
    model_importances.extend(coef_importance("logistic_regression", features.columns, logistic_weights[1:]))

    tree = SimpleDecisionTree(max_depth=5, min_samples_leaf=80, random_state=42).fit(
        features.x_train_raw, features.y_train
    )
    model_scores["decision_tree"] = {
        "valid": tree.predict_proba(features.x_valid_raw),
        "test": tree.predict_proba(features.x_test_raw),
    }
    model_importances.extend(tree_importance("decision_tree", features.columns, [tree]))

    forest = SimpleRandomForest(n_estimators=35, max_depth=5, min_samples_leaf=80, random_state=42).fit(
        features.x_train_raw, features.y_train
    )
    model_scores["random_forest"] = {
        "valid": forest.predict_proba(features.x_valid_raw),
        "test": forest.predict_proba(features.x_test_raw),
    }
    model_importances.extend(tree_importance("random_forest", features.columns, forest.trees))

    for model_name, split_scores in model_scores.items():
        for split_name, score in split_scores.items():
            y_true = features.y_valid if split_name == "valid" else features.y_test
            meta = features.valid_meta if split_name == "valid" else features.test_meta
            pred_class = (score >= 0.5).astype(int)
            metrics.append(classification_metrics(model_name, split_name, y_true, score, pred_class))
            split_predictions = meta.copy()
            split_predictions["split"] = split_name
            split_predictions["model"] = model_name
            split_predictions["score"] = score
            split_predictions["pred_label"] = pred_class
            predictions.append(split_predictions)

    return {
        "metrics": pd.DataFrame(metrics),
        "predictions": pd.concat(predictions, ignore_index=True),
        "feature_importance": pd.DataFrame(model_importances),
    }


def coef_importance(model: str, columns: list[str], coef: np.ndarray) -> list[dict]:
    values = np.abs(coef)
    total = values.sum() or 1
    return [
        {"model": model, "feature": feature, "importance": float(value / total), "raw_value": float(raw)}
        for feature, value, raw in zip(columns, values, coef)
    ]


def tree_importance(model: str, columns: list[str], trees: list[SimpleDecisionTree]) -> list[dict]:
    counts = np.zeros(len(columns), dtype=float)
    for tree in trees:
        if tree.root is not None:
            collect_tree_splits(tree.root, counts)
    total = counts.sum() or 1
    return [
        {"model": model, "feature": feature, "importance": float(value / total), "raw_value": float(value)}
        for feature, value in zip(columns, counts)
    ]


def collect_tree_splits(node: TreeNode, counts: np.ndarray) -> None:
    if node.is_leaf:
        return
    assert node.feature_index is not None
    counts[node.feature_index] += 1
    if node.left is not None:
        collect_tree_splits(node.left, counts)
    if node.right is not None:
        collect_tree_splits(node.right, counts)


def classification_metrics(model: str, split: str, y_true: np.ndarray, score: np.ndarray, pred: np.ndarray) -> dict:
    tp = int(((pred == 1) & (y_true == 1)).sum())
    fp = int(((pred == 1) & (y_true == 0)).sum())
    tn = int(((pred == 0) & (y_true == 0)).sum())
    fn = int(((pred == 0) & (y_true == 1)).sum())
    accuracy = (tp + tn) / len(y_true) if len(y_true) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "model": model,
        "split": split,
        "auc": auc_score(y_true, score),
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "positive_rate": float(y_true.mean()) if len(y_true) else 0.0,
        "n_samples": int(len(y_true)),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def auc_score(y_true: Iterable[int], score: Iterable[float]) -> float:
    y = np.asarray(list(y_true), dtype=int)
    s = np.asarray(list(score), dtype=float)
    pos = y == 1
    neg = y == 0
    n_pos = int(pos.sum())
    n_neg = int(neg.sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = np.argsort(s)
    ranks = np.empty(len(s), dtype=float)
    sorted_scores = s[order]
    i = 0
    while i < len(s):
        j = i + 1
        while j < len(s) and sorted_scores[j] == sorted_scores[i]:
            j += 1
        avg_rank = (i + 1 + j) / 2
        ranks[order[i:j]] = avg_rank
        i = j
    rank_sum_pos = ranks[pos].sum()
    return float((rank_sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def roc_curve_points(y_true: Iterable[int], score: Iterable[float]) -> list[tuple[float, float]]:
    y = np.asarray(list(y_true), dtype=int)
    s = np.asarray(list(score), dtype=float)
    order = np.argsort(-s)
    y_sorted = y[order]
    positives = max(1, int((y == 1).sum()))
    negatives = max(1, int((y == 0).sum()))
    tp = 0
    fp = 0
    points = [(0.0, 0.0)]
    for label in y_sorted:
        if label == 1:
            tp += 1
        else:
            fp += 1
        points.append((fp / negatives, tp / positives))
    if points[-1] != (1.0, 1.0):
        points.append((1.0, 1.0))
    return points


def build_eda_payload(prepared: pd.DataFrame, features: FeatureData, result: dict[str, pd.DataFrame]) -> dict:
    columns = features.columns
    corr = prepared[columns].corr(numeric_only=True).fillna(0)
    target_counts = prepared[TARGET_COLUMN].value_counts().sort_index()
    split_summary = []
    for name, meta in [
        ("train", features.train_meta),
        ("valid", features.valid_meta),
        ("test", features.test_meta),
    ]:
        split_summary.append(
            {
                "split": name,
                "n_samples": int(len(meta)),
                "positive_rate": float(meta[TARGET_COLUMN].mean()),
                "start_date": str(meta["Date"].min().date()),
                "end_date": str(meta["Date"].max().date()),
            }
        )
    return {
        "target_distribution": [
            {"label": int(label), "count": int(count)} for label, count in target_counts.items()
        ],
        "split_summary": split_summary,
        "feature_columns": columns,
        "correlation_matrix": {
            "columns": list(corr.columns),
            "values": corr.round(4).values.tolist(),
        },
        "metrics": result["metrics"].round(6).to_dict(orient="records"),
        "feature_importance": result["feature_importance"].round(6).to_dict(orient="records"),
    }


def save_results(metrics: pd.DataFrame, predictions: pd.DataFrame, feature_importance: pd.DataFrame | None = None) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(OUTPUT_DIR / "model_metrics.csv", index=False, encoding="utf-8-sig")
    predictions.to_csv(OUTPUT_DIR / "model_predictions.csv", index=False, encoding="utf-8-sig")
    if feature_importance is not None:
        feature_importance.to_csv(OUTPUT_DIR / "feature_importance.csv", index=False, encoding="utf-8-sig")
    save_roc_png(predictions, FIGURE_DIR / "roc_curve.png")
    save_individual_roc_pngs(predictions, FIGURE_DIR)


def save_roc_png(predictions: pd.DataFrame, path: str | Path, width: int = 900, height: int = 620) -> None:
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    margin_left, margin_right, margin_top, margin_bottom = 70, 40, 50, 70
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    draw_line(canvas, margin_left, margin_top, margin_left, height - margin_bottom, (40, 40, 40))
    draw_line(canvas, margin_left, height - margin_bottom, width - margin_right, height - margin_bottom, (40, 40, 40))
    draw_line(canvas, margin_left, height - margin_bottom, width - margin_right, margin_top, (180, 180, 180))

    colors = {
        "linear_regression": (37, 99, 235),
        "logistic_regression": (22, 133, 103),
        "decision_tree": (217, 119, 6),
        "random_forest": (124, 58, 237),
    }
    test_predictions = predictions[predictions["split"] == "test"]
    for model, group in test_predictions.groupby("model"):
        points = roc_curve_points(group[TARGET_COLUMN].to_numpy(), group["score"].to_numpy())
        pixel_points = [
            (
                int(margin_left + fpr * plot_w),
                int(height - margin_bottom - tpr * plot_h),
            )
            for fpr, tpr in points
        ]
        for (x1, y1), (x2, y2) in zip(pixel_points, pixel_points[1:]):
            draw_line(canvas, x1, y1, x2, y2, colors.get(model, (0, 0, 0)), thickness=2)

    write_png(path, canvas)


def save_individual_roc_pngs(predictions: pd.DataFrame, figure_dir: str | Path) -> None:
    figure_dir = Path(figure_dir)
    figure_dir.mkdir(parents=True, exist_ok=True)
    test_predictions = predictions[predictions["split"] == "test"]
    for model in MODEL_NAMES:
        group = test_predictions[test_predictions["model"] == model]
        if group.empty:
            continue
        save_single_roc_png(
            y_true=group[TARGET_COLUMN].to_numpy(),
            score=group["score"].to_numpy(),
            auc=auc_score(group[TARGET_COLUMN].to_numpy(), group["score"].to_numpy()),
            title=MODEL_DISPLAY_NAMES.get(model, model),
            path=figure_dir / f"roc_{model}.png",
        )


def save_single_roc_png(
    y_true: Iterable[int],
    score: Iterable[float],
    auc: float,
    title: str,
    path: str | Path,
    width: int = 760,
    height: int = 560,
) -> None:
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    margin_left, margin_right, margin_top, margin_bottom = 70, 45, 55, 70
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    draw_line(canvas, margin_left, margin_top, margin_left, height - margin_bottom, (40, 40, 40))
    draw_line(canvas, margin_left, height - margin_bottom, width - margin_right, height - margin_bottom, (40, 40, 40))
    draw_line(canvas, margin_left, height - margin_bottom, width - margin_right, margin_top, (185, 185, 185))

    points = roc_curve_points(y_true, score)
    pixel_points = [
        (
            int(margin_left + fpr * plot_w),
            int(height - margin_bottom - tpr * plot_h),
        )
        for fpr, tpr in points
    ]
    for (x1, y1), (x2, y2) in zip(pixel_points, pixel_points[1:]):
        draw_line(canvas, x1, y1, x2, y2, (37, 99, 235), thickness=3)

    # Lightweight title and AUC label using simple bars so the PNG remains dependency-free.
    draw_label_blocks(canvas, 70, 22, len(title), (37, 99, 235))
    draw_label_blocks(canvas, 70, height - 38, len(f"AUC={auc:.4f}"), (22, 133, 103))
    write_png(path, canvas)


def draw_label_blocks(canvas: np.ndarray, x: int, y: int, count: int, color: tuple[int, int, int]) -> None:
    for i in range(min(count, 28)):
        left = x + i * 9
        canvas[y : y + 8, left : left + 5] = color


def draw_line(canvas: np.ndarray, x1: int, y1: int, x2: int, y2: int, color: tuple[int, int, int], thickness: int = 1):
    dx = abs(x2 - x1)
    dy = -abs(y2 - y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    err = dx + dy
    x, y = x1, y1
    while True:
        draw_point(canvas, x, y, color, thickness)
        if x == x2 and y == y2:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy


def draw_point(canvas: np.ndarray, x: int, y: int, color: tuple[int, int, int], thickness: int):
    half = max(0, thickness // 2)
    h, w, _ = canvas.shape
    for yy in range(max(0, y - half), min(h, y + half + 1)):
        for xx in range(max(0, x - half), min(w, x + half + 1)):
            canvas[yy, xx] = color


def write_png(path: str | Path, rgb: np.ndarray) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    height, width, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[row].tobytes() for row in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, level=9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def run_pipeline(data_path: str | Path = DATA_PATH) -> dict[str, pd.DataFrame]:
    raw = load_raw_data(data_path)
    prepared = prepare_dataset(raw)
    train, valid, test = split_by_date_order(prepared)
    features = build_feature_frame(train, valid, test)
    result = fit_all_models(features)
    save_results(result["metrics"], result["predictions"], result["feature_importance"])
    eda_payload = build_eda_payload(prepared, features, result)
    (OUTPUT_DIR / "eda_model_payload.json").write_text(json.dumps(eda_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    output = run_pipeline()
    print(output["metrics"].to_string(index=False))
