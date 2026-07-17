from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[2]
TASK6 = ROOT / "task6"
TASK5_DATA = ROOT / "task5" / "data" / "model_data_stock.csv"
DATA_DIR = TASK6 / "data"
OUTPUT_DIR = TASK6 / "outputs"
FIGURE_DIR = OUTPUT_DIR / "figures"
ADJUSTED_RETURN_PATH = DATA_DIR / "adjusted_period_returns.csv"

MODEL_NAMES = ["linear_regression", "logistic_regression", "decision_tree", "random_forest"]
MODEL_LABELS = {
    "linear_regression": "线性回归",
    "logistic_regression": "逻辑回归",
    "decision_tree": "决策树",
    "random_forest": "随机森林",
}

BUY_COST_RATE = 0.0005441
SELL_COST_RATE = 0.0010441
TOP_N = 20

PE_COL = "市盈率PE(TTM)"
DIVIDEND_COL = "股息率(近12个月)"
GROWTH_WEIGHTS = {
    "净利润同比增长率": 0.40,
    "营业利润(同比增长率)": 0.20,
    "营业总收入(同比增长率)": 0.20,
    "基本每股收益(同比增长率)": 0.20,
}
RAW_FEATURES = [PE_COL, DIVIDEND_COL, *GROWTH_WEIGHTS.keys(), "growth_score"]


def ensure_dirs() -> None:
    for path in [DATA_DIR, OUTPUT_DIR, FIGURE_DIR, TASK6 / "notebooks", TASK6 / "design"]:
        path.mkdir(parents=True, exist_ok=True)


def load_sample(path: str | Path = TASK5_DATA) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["Date"] = pd.to_datetime(df["Date"])
    df["Code"] = df["Code"].map(lambda value: f"{int(value):06d}" if pd.notna(value) else "")
    df["symbol"] = df["Code"]
    return df.sort_values(["Date", "Code"]).reset_index(drop=True)


def copy_sample() -> None:
    ensure_dirs()
    target = DATA_DIR / "model_data_stock.csv"
    if not target.exists():
        target.write_bytes(TASK5_DATA.read_bytes())


def tushare_query(api_name: str, params: dict, fields: list[str]) -> pd.DataFrame:
    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is not set. Please set it before downloading price data.")
    payload = {
        "api_name": api_name,
        "token": token,
        "params": params,
        "fields": ",".join(fields),
    }
    response = requests.post("http://api.tushare.pro", json=payload, timeout=40)
    response.raise_for_status()
    data = response.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Tushare {api_name} error: {data.get('msg')}")
    values = data.get("data", {})
    return pd.DataFrame(values.get("items", []), columns=values.get("fields", fields))


def quarter_end_after(date: pd.Timestamp) -> pd.Timestamp:
    return date + pd.offsets.QuarterEnd(1)


def linked_total_return(daily_rows: pd.DataFrame, buy_date: str, sell_date: str) -> float:
    """Return the corporate-action-consistent holding return for one stock.

    The first session starts at the executable open. Every following session is
    linked through Tushare's ex-right reference price (pre_close), so the price
    chain remains consistent across dividends and other adjustment events.
    """
    rows = daily_rows.copy()
    rows["trade_date"] = rows["trade_date"].astype(str)
    rows = rows[(rows["trade_date"] >= str(buy_date)) & (rows["trade_date"] <= str(sell_date))]
    rows = rows.sort_values("trade_date")
    buy = rows[rows["trade_date"] == str(buy_date)]
    sell = rows[rows["trade_date"] == str(sell_date)]
    if buy.empty or sell.empty:
        return np.nan
    first = buy.iloc[0]
    open_price, close_price = float(first["open"]), float(first["close"])
    if open_price <= 0 or close_price <= 0:
        return np.nan
    factor = close_price / open_price
    for _, row in rows[rows["trade_date"] > str(buy_date)].iterrows():
        close_value, pre_close_value = float(row["close"]), float(row["pre_close"])
        if close_value <= 0 or pre_close_value <= 0:
            return np.nan
        factor *= close_value / pre_close_value
    return factor - 1


def get_index_trade_dates(start_date: str = "20210630", end_date: str = "20220930") -> list[str]:
    df = tushare_query(
        "trade_cal",
        {"exchange": "SSE", "start_date": start_date, "end_date": end_date, "is_open": "1"},
        ["exchange", "cal_date", "is_open", "pretrade_date"],
    )
    dates = sorted(df["cal_date"].astype(str).unique().tolist())
    if not dates:
        raise RuntimeError("No trade calendar dates returned from tushare.")
    return dates


def resolve_rebalance_dates(sample_dates: Iterable[pd.Timestamp], trade_dates: list[str]) -> pd.DataFrame:
    rows = []
    trade_ts = pd.to_datetime(pd.Series(trade_dates), format="%Y%m%d")
    for date in sorted(pd.to_datetime(pd.Series(sample_dates)).unique()):
        sample = pd.Timestamp(date)
        buy_candidates = trade_ts[trade_ts > sample]
        if buy_candidates.empty:
            continue
        sell_deadline = quarter_end_after(sample)
        sell_candidates = trade_ts[(trade_ts > sample) & (trade_ts <= sell_deadline)]
        if sell_candidates.empty:
            continue
        rows.append(
            {
                "Date": sample,
                "buy_date": buy_candidates.iloc[0].strftime("%Y%m%d"),
                "sell_date": sell_candidates.iloc[-1].strftime("%Y%m%d"),
                "quarter_end": sell_deadline.strftime("%Y-%m-%d"),
            }
        )
    return pd.DataFrame(rows)


def resolve_known_rebalance_dates(sample_dates: Iterable[pd.Timestamp]) -> pd.DataFrame:
    known = {
        "2021-06-30": ("20210701", "20210930"),
        "2021-09-30": ("20211008", "20211231"),
        "2021-12-31": ("20220104", "20220331"),
        "2022-03-31": ("20220401", "20220630"),
        "2022-06-30": ("20220701", "20220930"),
    }
    rows = []
    for date in sorted(pd.to_datetime(pd.Series(sample_dates)).unique()):
        sample = pd.Timestamp(date)
        key = sample.strftime("%Y-%m-%d")
        if key in known:
            buy_date, sell_date = known[key]
            rows.append(
                {
                    "Date": sample,
                    "buy_date": buy_date,
                    "sell_date": sell_date,
                    "quarter_end": quarter_end_after(sample).strftime("%Y-%m-%d"),
                }
            )
    return pd.DataFrame(rows)


def download_market_prices(force: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ensure_dirs()
    daily_path = DATA_DIR / "market_daily_required_dates.csv"
    adj_path = DATA_DIR / "market_adj_factor_required_dates.csv"
    index_path = DATA_DIR / "hs300_required_dates.csv"
    schedule_path = DATA_DIR / "rebalance_schedule.csv"

    if all(path.exists() for path in [daily_path, adj_path, index_path, schedule_path]) and not force:
        return pd.read_csv(daily_path), pd.read_csv(adj_path), pd.read_csv(index_path)

    sample = load_sample()
    try:
        trade_dates = get_index_trade_dates()
        schedule = resolve_rebalance_dates(sample["Date"].unique(), trade_dates)
    except Exception as exc:
        schedule = resolve_known_rebalance_dates(sample["Date"].unique())
        (DATA_DIR / "trade_calendar_warning.txt").write_text(str(exc), encoding="utf-8")
    required_dates = sorted(set(schedule["buy_date"]).union(set(schedule["sell_date"])))

    daily_frames = []
    adj_frames = []
    adj_warning = None
    for date in required_dates:
        one_daily = tushare_query("daily", {"trade_date": date}, ["ts_code", "trade_date", "open", "close"])
        daily_frames.append(one_daily)
        try:
            adj_frames.append(tushare_query("adj_factor", {"trade_date": date}, ["ts_code", "trade_date", "adj_factor"]))
        except Exception as exc:
            adj_warning = str(exc)
            fallback = one_daily[["ts_code", "trade_date"]].copy()
            fallback["adj_factor"] = 1.0
            adj_frames.append(fallback)
        time.sleep(0.18)

    daily = pd.concat(daily_frames, ignore_index=True)
    adj = pd.concat(adj_frames, ignore_index=True)
    if adj_warning:
        adj = daily[["ts_code", "trade_date"]].copy()
        adj["adj_factor"] = 1.0
        (DATA_DIR / "adj_factor_download_warning.txt").write_text(
            adj_warning + "\nFallback: adj_factor is set to 1.0, returns use unadjusted prices consistently.",
            encoding="utf-8",
        )
    try:
        index_daily = tushare_query(
            "index_daily",
            {"ts_code": "000300.SH", "start_date": min(required_dates), "end_date": max(required_dates)},
            ["ts_code", "trade_date", "open", "close"],
        )
        index_daily = index_daily[index_daily["trade_date"].astype(str).isin(required_dates)].copy()
    except Exception as exc:
        # Some accounts have strict hourly limits for index_daily. Use a narrow
        # Eastmoney fallback for HS300 so the second benchmark remains available.
        warning = str(exc)
        try:
            index_daily = fetch_hs300_from_yahoo(min(required_dates), max(required_dates))
            index_daily = index_daily[index_daily["trade_date"].astype(str).isin(required_dates)].copy()
        except Exception as yahoo_exc:
            warning += "\nYahoo fallback failed: " + str(yahoo_exc)
            try:
                index_daily = fetch_hs300_from_eastmoney(min(required_dates), max(required_dates))
                index_daily = index_daily[index_daily["trade_date"].astype(str).isin(required_dates)].copy()
            except Exception as fallback_exc:
                warning += "\nEastmoney fallback failed: " + str(fallback_exc)
                index_daily = pd.DataFrame(columns=["ts_code", "trade_date", "open", "close"])
        (DATA_DIR / "hs300_download_warning.txt").write_text(warning, encoding="utf-8")

    daily.to_csv(daily_path, index=False, encoding="utf-8-sig")
    adj.to_csv(adj_path, index=False, encoding="utf-8-sig")
    index_daily.to_csv(index_path, index=False, encoding="utf-8-sig")
    schedule.to_csv(schedule_path, index=False, encoding="utf-8-sig")
    return daily, adj, index_daily


def fetch_hs300_from_yahoo(start_date: str, end_date: str) -> pd.DataFrame:
    import datetime as dt

    start = dt.datetime.strptime(start_date, "%Y%m%d").replace(tzinfo=dt.timezone.utc)
    end = (dt.datetime.strptime(end_date, "%Y%m%d") + dt.timedelta(days=1)).replace(tzinfo=dt.timezone.utc)
    url = "https://query1.finance.yahoo.com/v8/finance/chart/000300.SS"
    params = {
        "period1": int(start.timestamp()),
        "period2": int(end.timestamp()),
        "interval": "1d",
        "events": "history",
    }
    response = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    response.raise_for_status()
    result = response.json()["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    rows = []
    for ts, open_price, close_price in zip(timestamps, quote["open"], quote["close"]):
        if open_price is None or close_price is None:
            continue
        trade_date = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).strftime("%Y%m%d")
        rows.append({"ts_code": "000300.SH", "trade_date": trade_date, "open": float(open_price), "close": float(close_price)})
    return pd.DataFrame(rows, columns=["ts_code", "trade_date", "open", "close"])


def fetch_hs300_from_eastmoney(start_date: str, end_date: str) -> pd.DataFrame:
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": "1.000300",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
        "beg": start_date,
        "end": end_date,
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json().get("data") or {}
    rows = []
    for line in data.get("klines", []):
        values = line.split(",")
        rows.append(
            {
                "ts_code": "000300.SH",
                "trade_date": values[0].replace("-", ""),
                "open": float(values[1]),
                "close": float(values[2]),
            }
        )
    return pd.DataFrame(rows, columns=["ts_code", "trade_date", "open", "close"])


def build_price_returns(force_download: bool = False) -> pd.DataFrame:
    copy_sample()
    sample = load_sample(DATA_DIR / "model_data_stock.csv")

    # The original endpoint for adjustment factors is rate-limited.  We therefore
    # construct holding-period total returns from daily ex-right reference prices
    # (pre_close) and cache only the resulting sample-period observations.
    # Never fall back to a raw-price end-point ratio: that would silently omit
    # dividends, rights issues, and other corporate actions.
    if ADJUSTED_RETURN_PATH.exists() and not force_download:
        adjusted = pd.read_csv(ADJUSTED_RETURN_PATH, dtype={"Code": str})
        adjusted["Code"] = adjusted["Code"].str.zfill(6)
        adjusted["Date"] = pd.to_datetime(adjusted["Date"])
        adjusted["buy_date"] = adjusted["buy_date"].astype(str)
        adjusted["sell_date"] = adjusted["sell_date"].astype(str)
        required = ["Date", "Code", "buy_date", "sell_date", "gross_return", "price_matched"]
        missing = [column for column in required if column not in adjusted.columns]
        if missing:
            raise RuntimeError(f"Adjusted return cache is missing columns: {missing}")

        schedule = pd.read_csv(DATA_DIR / "rebalance_schedule.csv")
        schedule["Date"] = pd.to_datetime(schedule["Date"])
        index_daily = pd.read_csv(DATA_DIR / "hs300_required_dates.csv")
        index_daily["trade_date"] = index_daily["trade_date"].astype(str)
        index_daily["open"] = pd.to_numeric(index_daily["open"], errors="coerce")
        index_daily["close"] = pd.to_numeric(index_daily["close"], errors="coerce")

        merged = sample[["Date", "Code", "symbol"]].merge(
            adjusted,
            on=["Date", "Code"],
            how="left",
            validate="one_to_one",
        )
        merged["gross_return"] = pd.to_numeric(merged["gross_return"], errors="coerce")
        merged["net_return"] = (
            (1 + merged["gross_return"]) * (1 - SELL_COST_RATE) / (1 + BUY_COST_RATE) - 1
        )
        merged["future_return"] = merged["gross_return"]
        merged["target_up"] = (merged["future_return"] > 0).astype(int)
        merged["price_matched"] = merged["price_matched"].fillna(False).astype(bool)
        merged["return_method"] = "daily_pre_close_total_return"

        idx_buy = index_daily[["trade_date", "open"]].rename(
            columns={"trade_date": "buy_date", "open": "hs300_buy_open"}
        )
        idx_sell = index_daily[["trade_date", "close"]].rename(
            columns={"trade_date": "sell_date", "close": "hs300_sell_close"}
        )
        merged = merged.merge(idx_buy, on="buy_date", how="left").merge(idx_sell, on="sell_date", how="left")
        merged["hs300_return"] = merged["hs300_sell_close"] / merged["hs300_buy_open"] - 1
        merged.to_csv(DATA_DIR / "price_returns.csv", index=False, encoding="utf-8-sig")
        return merged

    raise RuntimeError(
        "Forward-adjusted holding-period returns have not been generated. "
        "Run the Task6 adjusted-return downloader before training the models."
    )

    # Legacy implementation retained below for reference only. It must not be
    # reached because a raw-price ratio is not an acceptable return definition.
    daily, adj, index_daily = download_market_prices(force_download)
    schedule = pd.read_csv(DATA_DIR / "rebalance_schedule.csv")
    schedule["Date"] = pd.to_datetime(schedule["Date"])

    daily = daily.merge(adj, on=["ts_code", "trade_date"], how="left")
    daily["trade_date"] = daily["trade_date"].astype(str)
    daily["symbol"] = daily["ts_code"].astype(str).str.slice(0, 6)
    for column in ["open", "close", "adj_factor"]:
        daily[column] = pd.to_numeric(daily[column], errors="coerce")
    daily["open_adj"] = daily["open"] * daily["adj_factor"]
    daily["close_adj"] = daily["close"] * daily["adj_factor"]

    merged = sample[["Date", "Code", "symbol"]].merge(schedule, on="Date", how="left")
    merged["buy_date"] = merged["buy_date"].astype(str)
    merged["sell_date"] = merged["sell_date"].astype(str)
    buy = daily[["symbol", "trade_date", "ts_code", "open", "open_adj"]].rename(
        columns={
            "trade_date": "buy_date",
            "ts_code": "ts_code",
            "open": "buy_open",
            "open_adj": "buy_open_adj",
        }
    )
    sell = daily[["symbol", "trade_date", "close", "close_adj"]].rename(
        columns={"trade_date": "sell_date", "close": "sell_close", "close_adj": "sell_close_adj"}
    )
    merged = merged.merge(buy, on=["symbol", "buy_date"], how="left")
    merged = merged.merge(sell, on=["symbol", "sell_date"], how="left")

    merged["gross_return"] = merged["sell_close_adj"] / merged["buy_open_adj"] - 1
    merged["net_return"] = (
        merged["sell_close_adj"] * (1 - SELL_COST_RATE) / (merged["buy_open_adj"] * (1 + BUY_COST_RATE)) - 1
    )
    merged["future_return"] = merged["gross_return"]
    merged["target_up"] = (merged["future_return"] > 0).astype(int)
    merged["price_matched"] = merged[["buy_open_adj", "sell_close_adj"]].notna().all(axis=1)

    idx = index_daily.copy()
    idx["trade_date"] = idx["trade_date"].astype(str)
    idx["open"] = pd.to_numeric(idx["open"], errors="coerce")
    idx["close"] = pd.to_numeric(idx["close"], errors="coerce")
    idx_buy = idx[["trade_date", "open"]].rename(columns={"trade_date": "buy_date", "open": "hs300_buy_open"})
    idx_sell = idx[["trade_date", "close"]].rename(columns={"trade_date": "sell_date", "close": "hs300_sell_close"})
    merged = merged.merge(idx_buy, on="buy_date", how="left").merge(idx_sell, on="sell_date", how="left")
    merged["hs300_return"] = merged["hs300_sell_close"] / merged["hs300_buy_open"] - 1

    output = DATA_DIR / "price_returns.csv"
    merged.to_csv(output, index=False, encoding="utf-8-sig")
    return merged


def winsorize_train_apply(train: pd.DataFrame, parts: list[pd.DataFrame], columns: list[str]) -> list[pd.DataFrame]:
    low = train[columns].quantile(0.01, numeric_only=True)
    high = train[columns].quantile(0.99, numeric_only=True)
    out = []
    for part in parts:
        clipped = part.copy()
        for column in columns:
            clipped[column] = pd.to_numeric(clipped[column], errors="coerce").clip(low[column], high[column])
        out.append(clipped)
    return out


def add_growth_score(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    score = pd.Series(0.0, index=data.index)
    for column, weight in GROWTH_WEIGHTS.items():
        numeric = pd.to_numeric(data[column], errors="coerce")
        ranked = numeric.groupby(data["Date"]).rank(pct=True)
        ranked = ranked.fillna(0.5)
        score += weight * ranked
    data["growth_score"] = score
    return data


def prepare_model_data(returns: pd.DataFrame) -> pd.DataFrame:
    sample = load_sample(DATA_DIR / "model_data_stock.csv")
    returns = returns[returns["price_matched"]].copy()
    df = sample.merge(
        returns[
            [
                "Date",
                "Code",
                "ts_code",
                "buy_date",
                "sell_date",
                "buy_open_raw",
                "sell_close_raw",
                "gross_return",
                "net_return",
                "future_return",
                "target_up",
                "hs300_return",
            ]
        ],
        on=["Date", "Code"],
        how="inner",
    )
    df = add_growth_score(df)
    for column in RAW_FEATURES:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df.sort_values(["Date", "Code"]).reset_index(drop=True)


def split_by_dates(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dates = sorted(pd.to_datetime(df["Date"]).dropna().unique())
    train_n = max(1, int(len(dates) * 0.60))
    valid_n = max(1, int(len(dates) * 0.20))
    train_dates = dates[:train_n]
    valid_dates = dates[train_n : train_n + valid_n]
    test_dates = dates[train_n + valid_n :]
    train = df[df["Date"].isin(train_dates)].copy()
    valid = df[df["Date"].isin(valid_dates)].copy()
    test = df[df["Date"].isin(test_dates)].copy()
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


def build_feature_data(train: pd.DataFrame, valid: pd.DataFrame, test: pd.DataFrame) -> FeatureData:
    columns = RAW_FEATURES
    train, valid, test = winsorize_train_apply(train, [train, valid, test], columns)
    medians = train[columns].median(numeric_only=True).fillna(0)

    def mat(part: pd.DataFrame) -> np.ndarray:
        return part[columns].fillna(medians).to_numpy(dtype=float)

    x_train = mat(train)
    x_valid = mat(valid)
    x_test = mat(test)
    means = x_train.mean(axis=0)
    stds = x_train.std(axis=0)
    stds[stds == 0] = 1

    meta_cols = [
        "Date",
        "Code",
        "ts_code",
        "buy_date",
        "sell_date",
        "gross_return",
        "net_return",
        "future_return",
        "target_up",
        "hs300_return",
    ]
    return FeatureData(
        columns=columns,
        train_meta=train[meta_cols].copy(),
        valid_meta=valid[meta_cols].copy(),
        test_meta=test[meta_cols].copy(),
        x_train_raw=x_train,
        x_valid_raw=x_valid,
        x_test_raw=x_test,
        x_train_scaled=(x_train - means) / stds,
        x_valid_scaled=(x_valid - means) / stds,
        x_test_scaled=(x_test - means) / stds,
        y_train=train["target_up"].to_numpy(dtype=int),
        y_valid=valid["target_up"].to_numpy(dtype=int),
        y_test=test["target_up"].to_numpy(dtype=int),
    )


def add_intercept(x: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(x)), x])


def sigmoid(values: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(values, -35, 35)))


def fit_linear_regression(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    coef, *_ = np.linalg.lstsq(add_intercept(x), y.astype(float), rcond=None)
    return coef


def fit_logistic_regression(x: np.ndarray, y: np.ndarray, epochs: int = 900, lr: float = 0.08) -> np.ndarray:
    xb = add_intercept(x)
    weights = np.zeros(xb.shape[1])
    yf = y.astype(float)
    for _ in range(epochs):
        pred = sigmoid(xb @ weights)
        grad = xb.T @ (pred - yf) / len(yf)
        grad[1:] += 0.001 * weights[1:]
        weights -= lr * grad
    return weights


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
    def __init__(self, max_depth: int = 5, min_samples_leaf: int = 80, max_features: int | None = None, seed: int = 42):
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.max_features = max_features
        self.random = np.random.default_rng(seed)
        self.root: TreeNode | None = None

    def fit(self, x: np.ndarray, y: np.ndarray):
        self.root = self._build(x, y, 0)
        return self

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        if self.root is None:
            raise ValueError("Tree not fitted.")
        return np.array([self._predict_row(row, self.root) for row in x])

    def _predict_row(self, row: np.ndarray, node: TreeNode) -> float:
        while not node.is_leaf:
            assert node.feature_index is not None and node.threshold is not None
            node = node.left if row[node.feature_index] <= node.threshold else node.right
            assert node is not None
        return node.probability

    def _build(self, x: np.ndarray, y: np.ndarray, depth: int) -> TreeNode:
        node = TreeNode(probability=float(y.mean()) if len(y) else 0.0)
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
        base = gini(y)
        best_gain = 0.0
        best = None
        for feature in feature_indices:
            thresholds = candidate_thresholds(x[:, feature])
            for threshold in thresholds:
                left = x[:, feature] <= threshold
                if left.sum() < self.min_samples_leaf or (~left).sum() < self.min_samples_leaf:
                    continue
                score = (left.sum() * gini(y[left]) + (~left).sum() * gini(y[~left])) / len(y)
                gain = base - score
                if gain > best_gain:
                    best_gain = gain
                    best = (int(feature), float(threshold))
        return best


class SimpleRandomForest:
    def __init__(self, n_estimators: int = 35, max_depth: int = 5, min_samples_leaf: int = 80, seed: int = 42):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.seed = seed
        self.trees: list[SimpleDecisionTree] = []

    def fit(self, x: np.ndarray, y: np.ndarray):
        rng = np.random.default_rng(self.seed)
        max_features = max(1, int(math.sqrt(x.shape[1])))
        self.trees = []
        for i in range(self.n_estimators):
            idx = rng.integers(0, len(y), len(y))
            tree = SimpleDecisionTree(self.max_depth, self.min_samples_leaf, max_features, self.seed + i + 1)
            tree.fit(x[idx], y[idx])
            self.trees.append(tree)
        return self

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        return np.mean([tree.predict_proba(x) for tree in self.trees], axis=0)


def candidate_thresholds(values: np.ndarray, max_thresholds: int = 16) -> np.ndarray:
    values = values[np.isfinite(values)]
    unique = np.unique(values)
    if len(unique) <= 1:
        return np.array([])
    if len(unique) <= max_thresholds:
        return (unique[:-1] + unique[1:]) / 2
    return np.unique(np.quantile(unique, np.linspace(0.05, 0.95, max_thresholds)))


def gini(y: np.ndarray) -> float:
    if len(y) == 0:
        return 0.0
    p = float(y.mean())
    return 1 - p**2 - (1 - p) ** 2


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
        ranks[order[i:j]] = (i + 1 + j) / 2
        i = j
    rank_sum = ranks[pos].sum()
    return float((rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def classification_metrics(model: str, split: str, y_true: np.ndarray, score: np.ndarray, threshold: float = 0.5) -> dict:
    pred = (score >= threshold).astype(int)
    tp = int(((pred == 1) & (y_true == 1)).sum())
    fp = int(((pred == 1) & (y_true == 0)).sum())
    tn = int(((pred == 0) & (y_true == 0)).sum())
    fn = int(((pred == 0) & (y_true == 1)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "model": model,
        "split": split,
        "auc": auc_score(y_true, score),
        "accuracy": (tp + tn) / len(y_true) if len(y_true) else 0.0,
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
            collect_splits(tree.root, counts)
    total = counts.sum() or 1
    return [
        {"model": model, "feature": feature, "importance": float(value / total), "raw_value": float(value)}
        for feature, value in zip(columns, counts)
    ]


def collect_splits(node: TreeNode, counts: np.ndarray) -> None:
    if node.is_leaf:
        return
    assert node.feature_index is not None
    counts[node.feature_index] += 1
    if node.left:
        collect_splits(node.left, counts)
    if node.right:
        collect_splits(node.right, counts)


def fit_models(features: FeatureData) -> dict[str, pd.DataFrame]:
    scores = {}
    importances = []

    linear_coef = fit_linear_regression(features.x_train_scaled, features.y_train)
    scores["linear_regression"] = {
        "valid": np.clip(add_intercept(features.x_valid_scaled) @ linear_coef, 0, 1),
        "test": np.clip(add_intercept(features.x_test_scaled) @ linear_coef, 0, 1),
    }
    importances.extend(coef_importance("linear_regression", features.columns, linear_coef[1:]))

    logistic_weights = fit_logistic_regression(features.x_train_scaled, features.y_train)
    scores["logistic_regression"] = {
        "valid": sigmoid(add_intercept(features.x_valid_scaled) @ logistic_weights),
        "test": sigmoid(add_intercept(features.x_test_scaled) @ logistic_weights),
    }
    importances.extend(coef_importance("logistic_regression", features.columns, logistic_weights[1:]))

    tree = SimpleDecisionTree(max_depth=5, min_samples_leaf=80).fit(features.x_train_raw, features.y_train)
    scores["decision_tree"] = {"valid": tree.predict_proba(features.x_valid_raw), "test": tree.predict_proba(features.x_test_raw)}
    importances.extend(tree_importance("decision_tree", features.columns, [tree]))

    forest = SimpleRandomForest(n_estimators=35, max_depth=5, min_samples_leaf=80).fit(features.x_train_raw, features.y_train)
    scores["random_forest"] = {
        "valid": forest.predict_proba(features.x_valid_raw),
        "test": forest.predict_proba(features.x_test_raw),
    }
    importances.extend(tree_importance("random_forest", features.columns, forest.trees))

    predictions = []
    metrics = []
    for model, split_scores in scores.items():
        for split, score in split_scores.items():
            meta = features.valid_meta if split == "valid" else features.test_meta
            y = features.y_valid if split == "valid" else features.y_test
            metrics.append(classification_metrics(model, split, y, score))
            pred = meta.copy()
            pred["model"] = model
            pred["model_label"] = MODEL_LABELS[model]
            pred["split"] = split
            pred["score"] = score
            pred["pred_label"] = (score >= 0.5).astype(int)
            predictions.append(pred)

    return {
        "metrics": pd.DataFrame(metrics),
        "predictions": pd.concat(predictions, ignore_index=True),
        "feature_importance": pd.DataFrame(importances),
    }


def nav_from_returns(returns: pd.Series) -> pd.Series:
    return (1 + returns).cumprod()


def max_drawdown(nav: pd.Series) -> float:
    if nav.empty:
        return 0.0
    drawdown = nav / nav.cummax() - 1
    return float(drawdown.min())


def backtest_predictions(predictions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    test = predictions[predictions["split"] == "test"].copy()
    quarter_rows = []
    holding_rows = []
    for model, model_df in test.groupby("model"):
        for date, group in model_df.groupby("Date"):
            ranked = group.sort_values("score", ascending=False)
            selected = ranked.head(TOP_N).copy()
            selected["rank"] = np.arange(1, len(selected) + 1)
            # Raw model scores have incompatible scales (and can be negative for
            # linear regression), so use each model's within-quarter percentile
            # as a positive, monotonic prediction weight.
            ranked["score_percentile"] = ranked["score"].rank(pct=True, ascending=True)
            selected = selected.merge(
                ranked[["Code", "score_percentile"]], on="Code", how="left", validate="one_to_one"
            )
            selected["prediction_weight"] = selected["score_percentile"] / selected["score_percentile"].sum()
            holding_rows.append(selected)
            quarter_rows.append(
                {
                    "model": model,
                    "model_label": MODEL_LABELS[model],
                    "Date": pd.to_datetime(date).strftime("%Y-%m-%d"),
                    "n_available": int(len(group)),
                    "n_selected": int(len(selected)),
                    "strategy_return": float(selected["net_return"].mean()),
                    "strategy_gross_return": float(selected["gross_return"].mean()),
                    "prediction_weighted_return": float((selected["prediction_weight"] * selected["net_return"]).sum()),
                    "prediction_weighted_gross_return": float((selected["prediction_weight"] * selected["gross_return"]).sum()),
                    "equal_weight_return": float(group["net_return"].mean()),
                    "hs300_return": float(group["hs300_return"].iloc[0]) if pd.notna(group["hs300_return"].iloc[0]) else np.nan,
                    "excess_equal": float(selected["net_return"].mean() - group["net_return"].mean()),
                    "excess_hs300": float(selected["net_return"].mean() - group["hs300_return"].iloc[0])
                    if pd.notna(group["hs300_return"].iloc[0])
                    else np.nan,
                }
            )

    quarterly = pd.DataFrame(quarter_rows).sort_values(["model", "Date"]).reset_index(drop=True)
    holdings = pd.concat(holding_rows, ignore_index=True) if holding_rows else pd.DataFrame()
    metric_rows = []
    for model, group in quarterly.groupby("model"):
        group = group.sort_values("Date")
        strategy_nav = nav_from_returns(group["strategy_return"])
        equal_nav = nav_from_returns(group["equal_weight_return"])
        hs300_nav = nav_from_returns(group["hs300_return"])
        quarters = max(1, len(group))
        vol = float(group["strategy_return"].std(ddof=0) * math.sqrt(4)) if quarters > 1 else 0.0
        final_nav = float(strategy_nav.iloc[-1]) if not strategy_nav.empty else 1.0
        annual_return = final_nav ** (4 / quarters) - 1
        metric_rows.append(
            {
                "model": model,
                "model_label": MODEL_LABELS[model],
                "quarters": quarters,
                "strategy_return": final_nav - 1,
                "equal_weight_return": float(equal_nav.iloc[-1] - 1) if not equal_nav.empty else 0.0,
                "hs300_return": float(hs300_nav.iloc[-1] - 1) if not hs300_nav.empty and pd.notna(hs300_nav.iloc[-1]) else np.nan,
                "excess_equal": final_nav - float(equal_nav.iloc[-1]) if not equal_nav.empty else 0.0,
                "excess_hs300": final_nav - float(hs300_nav.iloc[-1])
                if not hs300_nav.empty and pd.notna(hs300_nav.iloc[-1])
                else np.nan,
                "annual_return": float(annual_return),
                "annual_volatility": vol,
                "max_drawdown": max_drawdown(strategy_nav),
                "sharpe": float(annual_return / vol) if vol else 0.0,
                "quarter_win_rate": float((group["strategy_return"] > 0).mean()),
                "excess_equal_win_rate": float((group["excess_equal"] > 0).mean()),
                "excess_hs300_win_rate": float((group["excess_hs300"] > 0).mean()) if group["excess_hs300"].notna().any() else np.nan,
                "avg_quarter_return": float(group["strategy_return"].mean()),
                "best_quarter_return": float(group["strategy_return"].max()),
                "worst_quarter_return": float(group["strategy_return"].min()),
            }
        )
    return quarterly, holdings, pd.DataFrame(metric_rows)


def backtest_ensemble_strategies(
    predictions: pd.DataFrame,
    base_quarterly: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Backtest two ensemble portfolios on the same test-quarter universe.

    The first allocates equal capital to the four model sleeves. The second
    converts each model's cross-sectional prediction to a percentile, averages
    the percentiles into a consensus score, then weights the selected stocks by
    that consensus score. Percentiles make linear-model scores and probabilities
    comparable without changing their within-quarter ordering.
    """
    test = predictions[predictions["split"] == "test"].copy()
    rows: list[dict] = []
    holding_rows: list[pd.DataFrame] = []
    for date, group in test.groupby("Date"):
        base_rows = base_quarterly[base_quarterly["Date"] == pd.to_datetime(date).strftime("%Y-%m-%d")]
        sleeve_returns = base_rows.set_index("model")["strategy_return"]
        if sleeve_returns.empty:
            continue
        reference = group[group["model"] == MODEL_NAMES[0]].copy()
        score_matrix = group.pivot(index="Code", columns="model", values="score")
        percentile_matrix = score_matrix.rank(pct=True, ascending=True)
        reference = reference.set_index("Code")
        reference["consensus_score"] = percentile_matrix.reindex(reference.index).mean(axis=1)
        reference = reference.reset_index().dropna(subset=["consensus_score"])
        selected = reference.sort_values("consensus_score", ascending=False).head(TOP_N).copy()
        selected["rank"] = np.arange(1, len(selected) + 1)
        selected["portfolio_weight"] = selected["consensus_score"] / selected["consensus_score"].sum()
        selected["strategy"] = "prediction_weighted_combo"
        holding_rows.append(selected)

        common = {
            "Date": pd.to_datetime(date).strftime("%Y-%m-%d"),
            "n_available": int(len(reference)),
            "n_selected": int(len(selected)),
            "equal_weight_return": float(reference["net_return"].mean()),
            "hs300_return": float(reference["hs300_return"].iloc[0])
            if pd.notna(reference["hs300_return"].iloc[0])
            else np.nan,
        }
        rows.append(
            {
                **common,
                "strategy": "model_equal_weight_combo",
                "strategy_label": "四模型等资金组合",
                "strategy_return": float(sleeve_returns.reindex(MODEL_NAMES).mean()),
                "strategy_gross_return": np.nan,
            }
        )
        rows.append(
            {
                **common,
                "strategy": "prediction_weighted_combo",
                "strategy_label": "预测值加权组合",
                "strategy_return": float((selected["portfolio_weight"] * selected["net_return"]).sum()),
                "strategy_gross_return": float((selected["portfolio_weight"] * selected["gross_return"]).sum()),
            }
        )

    quarterly = pd.DataFrame(rows)
    if quarterly.empty:
        return quarterly, pd.DataFrame(), pd.DataFrame()
    quarterly["excess_equal"] = quarterly["strategy_return"] - quarterly["equal_weight_return"]
    quarterly["excess_hs300"] = quarterly["strategy_return"] - quarterly["hs300_return"]
    metric_rows = []
    for strategy, group in quarterly.groupby("strategy"):
        group = group.sort_values("Date")
        strategy_nav = nav_from_returns(group["strategy_return"])
        equal_nav = nav_from_returns(group["equal_weight_return"])
        hs300_nav = nav_from_returns(group["hs300_return"])
        quarters = max(1, len(group))
        final_nav = float(strategy_nav.iloc[-1])
        vol = float(group["strategy_return"].std(ddof=0) * math.sqrt(4)) if quarters > 1 else 0.0
        annual_return = final_nav ** (4 / quarters) - 1
        metric_rows.append(
            {
                "strategy": strategy,
                "strategy_label": group["strategy_label"].iloc[0],
                "quarters": quarters,
                "strategy_return": final_nav - 1,
                "equal_weight_return": float(equal_nav.iloc[-1] - 1),
                "hs300_return": float(hs300_nav.iloc[-1] - 1) if pd.notna(hs300_nav.iloc[-1]) else np.nan,
                "excess_equal": final_nav - float(equal_nav.iloc[-1]),
                "excess_hs300": final_nav - float(hs300_nav.iloc[-1]) if pd.notna(hs300_nav.iloc[-1]) else np.nan,
                "annual_return": float(annual_return),
                "annual_volatility": vol,
                "max_drawdown": max_drawdown(strategy_nav),
                "sharpe": float(annual_return / vol) if vol else 0.0,
                "quarter_win_rate": float((group["strategy_return"] > 0).mean()),
                "avg_quarter_return": float(group["strategy_return"].mean()),
            }
        )
    return quarterly, pd.concat(holding_rows, ignore_index=True) if holding_rows else pd.DataFrame(), pd.DataFrame(metric_rows)


def backtest_weighting_schemes(quarterly: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare equal capital and prediction-weighted Top20 portfolios per model."""
    rows = []
    for _, row in quarterly.iterrows():
        for scheme, label, return_column in [
            ("equal_weight", "Top20 等资金", "strategy_return"),
            ("prediction_weighted", "Top20 预测值加权", "prediction_weighted_return"),
        ]:
            rows.append(
                {
                    "strategy": f"{row['model']}__{scheme}",
                    "model": row["model"],
                    "model_label": row["model_label"],
                    "scheme": scheme,
                    "strategy_label": f"{row['model_label']} · {label}",
                    "Date": row["Date"],
                    "n_available": row["n_available"],
                    "n_selected": row["n_selected"],
                    "strategy_return": float(row[return_column]),
                    "equal_weight_return": float(row["equal_weight_return"]),
                    "hs300_return": float(row["hs300_return"]),
                }
            )
    scheme_quarterly = pd.DataFrame(rows)
    if scheme_quarterly.empty:
        return scheme_quarterly, pd.DataFrame()
    scheme_quarterly["excess_equal"] = scheme_quarterly["strategy_return"] - scheme_quarterly["equal_weight_return"]
    scheme_quarterly["excess_hs300"] = scheme_quarterly["strategy_return"] - scheme_quarterly["hs300_return"]
    metric_rows = []
    for strategy, group in scheme_quarterly.groupby("strategy"):
        group = group.sort_values("Date")
        nav = nav_from_returns(group["strategy_return"])
        equal_nav = nav_from_returns(group["equal_weight_return"])
        hs300_nav = nav_from_returns(group["hs300_return"])
        quarters = max(1, len(group))
        final_nav = float(nav.iloc[-1])
        vol = float(group["strategy_return"].std(ddof=0) * math.sqrt(4)) if quarters > 1 else 0.0
        annual_return = final_nav ** (4 / quarters) - 1
        metric_rows.append(
            {
                "strategy": strategy,
                "model": group["model"].iloc[0],
                "model_label": group["model_label"].iloc[0],
                "scheme": group["scheme"].iloc[0],
                "strategy_label": group["strategy_label"].iloc[0],
                "quarters": quarters,
                "strategy_return": final_nav - 1,
                "equal_weight_return": float(equal_nav.iloc[-1] - 1),
                "hs300_return": float(hs300_nav.iloc[-1] - 1),
                "excess_equal": final_nav - float(equal_nav.iloc[-1]),
                "excess_hs300": final_nav - float(hs300_nav.iloc[-1]),
                "annual_return": annual_return,
                "annual_volatility": vol,
                "max_drawdown": max_drawdown(nav),
                "sharpe": float(annual_return / vol) if vol else 0.0,
                "avg_quarter_return": float(group["strategy_return"].mean()),
            }
        )
    return scheme_quarterly, pd.DataFrame(metric_rows)


def roc_points(y_true: Iterable[int], score: Iterable[float]) -> list[dict]:
    pairs = sorted(zip(score, y_true), reverse=True)
    positives = max(1, sum(1 for _, y in pairs if y == 1))
    negatives = max(1, sum(1 for _, y in pairs if y == 0))
    tp = fp = 0
    points = [{"fpr": 0.0, "tpr": 0.0}]
    for _, y in pairs:
        if y == 1:
            tp += 1
        else:
            fp += 1
        points.append({"fpr": fp / negatives, "tpr": tp / positives})
    points.append({"fpr": 1.0, "tpr": 1.0})
    return points


def build_payload(
    model_data: pd.DataFrame,
    metrics: pd.DataFrame,
    predictions: pd.DataFrame,
    feature_importance: pd.DataFrame,
    quarterly: pd.DataFrame,
    backtest_metrics: pd.DataFrame,
    holdings: pd.DataFrame,
    ensemble_quarterly: pd.DataFrame,
    ensemble_metrics: pd.DataFrame,
    ensemble_holdings: pd.DataFrame,
) -> dict:
    metrics = metrics.copy()
    predictions = predictions.copy()
    feature_importance = feature_importance.copy()
    quarterly = quarterly.copy()
    backtest_metrics = backtest_metrics.copy()
    holdings = holdings.copy()
    ensemble_quarterly = ensemble_quarterly.copy()
    ensemble_metrics = ensemble_metrics.copy()
    ensemble_holdings = ensemble_holdings.copy()
    for frame in [predictions, quarterly, holdings, ensemble_quarterly, ensemble_holdings]:
        if "Date" in frame.columns:
            frame["Date"] = pd.to_datetime(frame["Date"]).dt.strftime("%Y-%m-%d")
    if not feature_importance.empty:
        denominator = feature_importance.groupby("model")["importance"].transform("sum").replace(0, np.nan)
        feature_importance["importance_normalized"] = (feature_importance["importance"] / denominator).fillna(0.0)
    split_summary = []
    for split, group in predictions.groupby("split"):
        split_summary.append(
            {
                "split": split,
                "n_samples": int(len(group) / len(MODEL_NAMES)),
                "start_date": str(pd.to_datetime(group["Date"]).min().date()),
                "end_date": str(pd.to_datetime(group["Date"]).max().date()),
            }
        )
    target_counts = model_data["target_up"].value_counts().sort_index()
    roc = {}
    threshold_grid = []
    for model, group in predictions[predictions["split"] == "test"].groupby("model"):
        roc[model] = roc_points(group["target_up"], group["score"])
        for threshold in np.round(np.arange(0.0, 1.001, 0.01), 2):
            row = classification_metrics(
                model,
                "test",
                group["target_up"].to_numpy(dtype=int),
                group["score"].to_numpy(dtype=float),
                float(threshold),
            )
            row["threshold"] = float(threshold)
            threshold_grid.append(row)
    price_summary = {
        "price_basis": "逐日除权参考价链接的总收益率口径",
        "return_formula": "gross_total_return = close_buy/open_buy × Π(close_t/pre_close_t) - 1; net_return = (1 + gross_total_return) × (1 - sell_cost)/(1 + buy_cost) - 1",
        "price_match_rate": None,
        "matched_rows": None,
        "total_rows": None,
        "hs300_missing_quarters": None,
    }
    price_path = DATA_DIR / "price_returns.csv"
    if price_path.exists():
        price_returns = pd.read_csv(price_path)
        total_rows = len(price_returns)
        matched_rows = int(price_returns["price_matched"].sum()) if "price_matched" in price_returns.columns else None
        price_summary.update(
            {
                "price_match_rate": float(matched_rows / total_rows) if total_rows and matched_rows is not None else None,
                "matched_rows": matched_rows,
                "total_rows": int(total_rows),
                "hs300_missing_quarters": int(price_returns["hs300_return"].isna().sum())
                if "hs300_return" in price_returns.columns
                else None,
            }
        )
    summary = {
        "test_quarters": int(quarterly["Date"].nunique()) if "Date" in quarterly.columns else 0,
        "models": MODEL_NAMES,
        "benchmarks": ["测试集股票池等权组合", "沪深300"],
        "selection_rule": f"每个测试季度按模型分数动态选择 Top {TOP_N} 股票等权持有",
        "target_definition": "下一季度收益率大于 0 记为 1，否则记为 0",
        "split_rule": "按日期前后切分：60% 训练集、20% 验证集、20% 测试集",
    }
    return {
        "model_labels": MODEL_LABELS,
        "summary": summary,
        "price_info": price_summary,
        "growth_score_formula": [
            {"feature": feature, "weight": weight} for feature, weight in GROWTH_WEIGHTS.items()
        ],
        "costs": {
            "buy_cost_rate": BUY_COST_RATE,
            "sell_cost_rate": SELL_COST_RATE,
            "top_n": TOP_N,
            "price_adjustment": "买入日开盘到收盘使用实际价格；后续逐日以除权参考价 pre_close 链接，统一计入区间公司行为",
        },
        "target_distribution": [{"label": int(k), "count": int(v)} for k, v in target_counts.items()],
        "split_summary": split_summary,
        "metrics": metrics.round(6).to_dict(orient="records"),
        "backtest_metrics": backtest_metrics.round(6).to_dict(orient="records"),
        "quarterly_returns": quarterly.round(6).to_dict(orient="records"),
        "ensemble_quarterly_returns": ensemble_quarterly.round(6).to_dict(orient="records"),
        "ensemble_metrics": ensemble_metrics.round(6).to_dict(orient="records"),
        "feature_importance": feature_importance.round(6).to_dict(orient="records"),
        "holdings": holdings.round(6).to_dict(orient="records") if not holdings.empty else [],
        "ensemble_holdings": ensemble_holdings.round(6).to_dict(orient="records") if not ensemble_holdings.empty else [],
        "roc_points": roc,
        "threshold_metrics": threshold_grid,
    }


def save_outputs(result: dict[str, pd.DataFrame], model_data: pd.DataFrame, payload: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result["metrics"].to_csv(OUTPUT_DIR / "model_metrics.csv", index=False, encoding="utf-8-sig")
    result["predictions"].to_csv(OUTPUT_DIR / "model_predictions.csv", index=False, encoding="utf-8-sig")
    result["feature_importance"].to_csv(OUTPUT_DIR / "feature_importance.csv", index=False, encoding="utf-8-sig")
    result["quarterly"].to_csv(OUTPUT_DIR / "quarterly_returns.csv", index=False, encoding="utf-8-sig")
    result["holdings"].to_csv(OUTPUT_DIR / "selected_holdings.csv", index=False, encoding="utf-8-sig")
    result["backtest_metrics"].to_csv(OUTPUT_DIR / "backtest_metrics.csv", index=False, encoding="utf-8-sig")
    result["ensemble_quarterly"].to_csv(OUTPUT_DIR / "top20_weighting_quarterly_returns.csv", index=False, encoding="utf-8-sig")
    result["ensemble_metrics"].to_csv(OUTPUT_DIR / "top20_weighting_backtest_metrics.csv", index=False, encoding="utf-8-sig")
    result["ensemble_holdings"].to_csv(OUTPUT_DIR / "top20_weighting_holdings.csv", index=False, encoding="utf-8-sig")
    model_data.to_csv(OUTPUT_DIR / "model_dataset_with_returns.csv", index=False, encoding="utf-8-sig")
    (OUTPUT_DIR / "strategy_payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_pipeline(force_download: bool = False) -> dict[str, pd.DataFrame]:
    ensure_dirs()
    returns = build_price_returns(force_download)
    model_data = prepare_model_data(returns)
    train, valid, test = split_by_dates(model_data)
    features = build_feature_data(train, valid, test)
    model_result = fit_models(features)
    quarterly, holdings, backtest_metrics = backtest_predictions(model_result["predictions"])
    # Compare two weighting rules inside each individual model's own Top20.
    ensemble_quarterly, ensemble_metrics = backtest_weighting_schemes(quarterly)
    ensemble_holdings = holdings
    result = {
        **model_result,
        "quarterly": quarterly,
        "holdings": holdings,
        "backtest_metrics": backtest_metrics,
        "ensemble_quarterly": ensemble_quarterly,
        "ensemble_holdings": ensemble_holdings,
        "ensemble_metrics": ensemble_metrics,
    }
    payload = build_payload(
        model_data,
        result["metrics"],
        result["predictions"],
        result["feature_importance"],
        quarterly,
        backtest_metrics,
        holdings,
        ensemble_quarterly,
        ensemble_metrics,
        ensemble_holdings,
    )
    save_outputs(result, model_data, payload)
    return result


if __name__ == "__main__":
    output = run_pipeline()
    print(output["metrics"].to_string(index=False))
    print(output["backtest_metrics"].to_string(index=False))
