from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = ["trade_date", "open", "high", "low", "close", "vol"]
NUMERIC_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "vol",
    "amount",
    "change",
    "pct_chg",
]


def clean_price_data(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize daily price data before indicator calculations."""
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    cleaned = df.copy()
    cleaned["trade_date"] = pd.to_datetime(
        cleaned["trade_date"].astype(str), format="%Y%m%d", errors="coerce"
    )

    for column in NUMERIC_COLUMNS:
        if column in cleaned.columns:
            cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")

    cleaned = cleaned.sort_values("trade_date").reset_index(drop=True)
    cleaned = cleaned.drop_duplicates(subset=["trade_date"], keep="last").reset_index(drop=True)

    if cleaned["trade_date"].isna().any():
        raise ValueError("trade_date contains values that cannot be parsed as YYYYMMDD")

    return cleaned


def rma(series: pd.Series, period: int) -> pd.Series:
    """Wilder-style moving average."""
    return series.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def add_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    result = df.copy()
    delta = result["close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = rma(gain, period)
    avg_loss = rma(loss, period)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result[f"rsi_{period}"] = 100 - (100 / (1 + rs))
    result.loc[(avg_loss == 0) & (avg_gain > 0), f"rsi_{period}"] = 100
    result.loc[(avg_loss == 0) & (avg_gain == 0), f"rsi_{period}"] = 50
    return result


def add_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    result = df.copy()
    ema_fast = result["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = result["close"].ewm(span=slow, adjust=False).mean()
    result["macd_dif"] = ema_fast - ema_slow
    result["macd_dea"] = result["macd_dif"].ewm(span=signal, adjust=False).mean()
    result["macd_hist"] = 2 * (result["macd_dif"] - result["macd_dea"])
    return result


def add_bollinger_bands(
    df: pd.DataFrame,
    window: int = 20,
    num_std: float = 2.0,
) -> pd.DataFrame:
    result = df.copy()
    result["boll_mid"] = result["close"].rolling(window=window, min_periods=window).mean()
    boll_std = result["close"].rolling(window=window, min_periods=window).std()
    result["boll_upper"] = result["boll_mid"] + num_std * boll_std
    result["boll_lower"] = result["boll_mid"] - num_std * boll_std
    result["boll_width"] = (result["boll_upper"] - result["boll_lower"]) / result["boll_mid"]
    return result


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    result = df.copy()
    previous_close = result["close"].shift(1)
    tr_components = pd.concat(
        [
            result["high"] - result["low"],
            (result["high"] - previous_close).abs(),
            (result["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    result["tr"] = tr_components.max(axis=1)
    result[f"atr_{period}"] = rma(result["tr"], period)
    return result


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    result = add_rsi(df, period=14)
    result = add_macd(result, fast=12, slow=26, signal=9)
    result = add_bollinger_bands(result, window=20, num_std=2.0)
    result = add_atr(result, period=14)
    return result


def latest_indicator_summary(df: pd.DataFrame) -> dict[str, Any]:
    usable = df.dropna(subset=["rsi_14", "macd_dif", "macd_dea", "boll_mid", "atr_14"])
    if usable.empty:
        raise ValueError("No row has enough indicator data for a latest summary")

    row = usable.iloc[-1]
    close = float(row["close"])
    rsi = float(row["rsi_14"])
    macd_hist = float(row["macd_hist"])
    atr = float(row["atr_14"])
    boll_upper = float(row["boll_upper"])
    boll_lower = float(row["boll_lower"])
    boll_mid = float(row["boll_mid"])

    if rsi >= 70:
        rsi_view = "RSI 处于偏热区间，提示短期上涨动能较强，也需要留意回落风险。"
    elif rsi <= 30:
        rsi_view = "RSI 处于偏冷区间，提示短期下跌压力较大，也可能进入超跌修复观察区。"
    else:
        rsi_view = "RSI 位于中性区间，短期多空力量相对均衡。"

    macd_view = (
        "MACD 柱为正，动能偏多。"
        if macd_hist >= 0
        else "MACD 柱为负，动能偏弱。"
    )

    if close > boll_upper:
        boll_view = "收盘价高于布林带上轨，价格处于强势或短期过热状态。"
    elif close < boll_lower:
        boll_view = "收盘价低于布林带下轨，价格处于弱势或短期超跌状态。"
    elif close >= boll_mid:
        boll_view = "收盘价位于布林带中轨上方，价格相对均值偏强。"
    else:
        boll_view = "收盘价位于布林带中轨下方，价格相对均值偏弱。"

    atr_pct = atr / close if close else np.nan
    atr_view = f"ATR 占收盘价约 {atr_pct:.2%}，用于衡量近期单日波动风险。"

    trade_date = row["trade_date"]
    if hasattr(trade_date, "strftime"):
        trade_date = trade_date.strftime("%Y-%m-%d")

    return {
        "trade_date": trade_date,
        "ts_code": row.get("ts_code", ""),
        "close": close,
        "rsi_14": rsi,
        "macd_dif": float(row["macd_dif"]),
        "macd_dea": float(row["macd_dea"]),
        "macd_hist": macd_hist,
        "boll_upper": boll_upper,
        "boll_mid": boll_mid,
        "boll_lower": boll_lower,
        "atr_14": atr,
        "rsi_view": rsi_view,
        "macd_view": macd_view,
        "boll_view": boll_view,
        "atr_view": atr_view,
    }


def load_and_calculate(input_path: str | Path, output_path: str | Path | None = None) -> pd.DataFrame:
    raw = pd.read_csv(input_path)
    result = add_all_indicators(clean_price_data(raw))
    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output, index=False, encoding="utf-8-sig")
    return result
