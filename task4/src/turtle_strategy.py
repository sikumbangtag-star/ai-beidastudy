from __future__ import annotations

import math
from typing import Any


BUY_COST_RATE = 0.0005441
SELL_COST_RATE = 0.0010441

TURTLE_VARIANTS = {
    "short_20_10": {"label": "20/10", "entry_window": 20, "exit_window": 10},
    "long_55_20": {"label": "55/20", "entry_window": 55, "exit_window": 20},
}


def previous_high_channel(rows: list[dict[str, Any]], window: int) -> list[float | None]:
    if window <= 0:
        raise ValueError("window must be positive")
    values: list[float | None] = []
    for index in range(len(rows)):
        if index < window:
            values.append(None)
        else:
            values.append(max(float(row["high"]) for row in rows[index - window : index]))
    return values


def previous_low_channel(rows: list[dict[str, Any]], window: int) -> list[float | None]:
    if window <= 0:
        raise ValueError("window must be positive")
    values: list[float | None] = []
    for index in range(len(rows)):
        if index < window:
            values.append(None)
        else:
            values.append(min(float(row["low"]) for row in rows[index - window : index]))
    return values


def align_stock_and_benchmark(
    stock_rows: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    benchmark_by_date = {row["trade_date"]: row for row in benchmark_rows}
    return [
        (stock_row, benchmark_by_date[stock_row["trade_date"]])
        for stock_row in stock_rows
        if stock_row.get("trade_date") in benchmark_by_date
    ]


def annual_volatility(daily_returns: list[float]) -> float:
    if len(daily_returns) < 2:
        return 0.0
    mean = sum(daily_returns) / len(daily_returns)
    variance = sum((item - mean) ** 2 for item in daily_returns) / (len(daily_returns) - 1)
    return math.sqrt(variance) * math.sqrt(252)


def max_drawdown(nav_values: list[float]) -> float:
    if not nav_values:
        return 0.0
    peak = nav_values[0]
    drawdown = 0.0
    for value in nav_values:
        peak = max(peak, value)
        if peak:
            drawdown = min(drawdown, value / peak - 1)
    return drawdown


def compute_turtle_strategy(
    stock_rows: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
    variant: str = "short_20_10",
    entry_window: int | None = None,
    exit_window: int | None = None,
    buy_cost_rate: float = BUY_COST_RATE,
    sell_cost_rate: float = SELL_COST_RATE,
) -> dict[str, Any]:
    if variant not in TURTLE_VARIANTS:
        raise ValueError(f"Unknown turtle variant: {variant}")
    settings = TURTLE_VARIANTS[variant]
    entry_window = entry_window or int(settings["entry_window"])
    exit_window = exit_window or int(settings["exit_window"])
    if entry_window <= 0 or exit_window <= 0:
        raise ValueError("Turtle windows must be positive")

    aligned = align_stock_and_benchmark(stock_rows, benchmark_rows)
    if len(aligned) < max(entry_window, exit_window) + 1:
        return {"rows": [], "trades": [], "metrics": empty_metrics(variant, entry_window, exit_window, len(aligned))}

    aligned_stocks = [stock for stock, _ in aligned]
    entry_channel = previous_high_channel(aligned_stocks, entry_window)
    exit_channel = previous_low_channel(aligned_stocks, exit_window)
    benchmark_start = float(aligned[0][1]["close"])

    cash = 1.0
    shares = 0.0
    holding = False
    pending: dict[str, Any] | None = None
    entry_nav = 1.0
    entry_index: int | None = None
    total_cost = 0.0
    entry_breakout_count = 0
    effective_buy_count = 0
    exit_breakout_count = 0
    effective_sell_count = 0
    completed_returns: list[float] = []
    holding_days: list[int] = []
    trades: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []

    for index, (stock, benchmark) in enumerate(aligned):
        if pending and pending["exec_index"] == index:
            trade_price = float(stock["open"])
            if pending["side"] == "BUY":
                gross_cash = cash
                cost = gross_cash * buy_cost_rate
                shares = (gross_cash - cost) / trade_price
                cash = 0.0
                holding = True
                entry_nav = gross_cash
                entry_index = index
                total_cost += cost
                nav_after = shares * float(stock["close"])
                trades.append(
                    {
                        **pending,
                        "trade_date": stock["trade_date"],
                        "price": trade_price,
                        "cost_rate": buy_cost_rate,
                        "cost": cost,
                        "nav_after": nav_after,
                    }
                )
            else:
                gross_cash = shares * trade_price
                cost = gross_cash * sell_cost_rate
                cash = gross_cash - cost
                shares = 0.0
                holding = False
                total_cost += cost
                nav_after = cash
                if entry_index is not None:
                    completed_returns.append(nav_after / entry_nav - 1)
                    holding_days.append(index - entry_index)
                trades.append(
                    {
                        **pending,
                        "trade_date": stock["trade_date"],
                        "price": trade_price,
                        "cost_rate": sell_cost_rate,
                        "cost": cost,
                        "nav_after": nav_after,
                    }
                )
            pending = None

        close = float(stock["close"])
        entry_level = entry_channel[index]
        exit_level = exit_channel[index]
        entry_breakout = entry_level is not None and close > entry_level
        exit_breakout = exit_level is not None and close < exit_level

        if index < len(aligned) - 1 and pending is None:
            if not holding and entry_breakout:
                entry_breakout_count += 1
                effective_buy_count += 1
                pending = {
                    "side": "BUY",
                    "signal_date": stock["trade_date"],
                    "signal_index": index,
                    "exec_index": index + 1,
                    "entry_channel": entry_level,
                    "exit_channel": exit_level,
                }
            elif holding and exit_breakout:
                exit_breakout_count += 1
                effective_sell_count += 1
                pending = {
                    "side": "SELL",
                    "signal_date": stock["trade_date"],
                    "signal_index": index,
                    "exec_index": index + 1,
                    "entry_channel": entry_level,
                    "exit_channel": exit_level,
                }

        nav = shares * close if holding else cash
        benchmark_nav = float(benchmark["close"]) / benchmark_start if benchmark_start else 1.0
        result_rows.append(
            {
                **stock,
                "entry_channel": entry_level,
                "exit_channel": exit_level,
                "entry_breakout": bool(entry_breakout),
                "exit_breakout": bool(exit_breakout),
                "strategy_nav": nav,
                "benchmark_nav": benchmark_nav,
                "excess_nav": nav - benchmark_nav,
            }
        )

    nav_values = [float(row["strategy_nav"]) for row in result_rows]
    benchmark_values = [float(row["benchmark_nav"]) for row in result_rows]
    daily_returns = [nav_values[index] / nav_values[index - 1] - 1 for index in range(1, len(nav_values)) if nav_values[index - 1]]
    trading_days = max(1, len(daily_returns))
    strategy_return = nav_values[-1] - 1 if nav_values else 0.0
    benchmark_return = benchmark_values[-1] - 1 if benchmark_values else 0.0
    annual_return = nav_values[-1] ** (252 / trading_days) - 1 if nav_values else 0.0
    annual_vol = annual_volatility(daily_returns)
    completed_count = len(completed_returns)
    metrics = {
        "variant": variant,
        "entry_window": entry_window,
        "exit_window": exit_window,
        "strategy_return": strategy_return,
        "benchmark_return": benchmark_return,
        "excess_return": strategy_return - benchmark_return,
        "annual_return": annual_return,
        "annual_volatility": annual_vol,
        "max_drawdown": max_drawdown(nav_values),
        "sharpe_ratio": annual_return / annual_vol if annual_vol else 0.0,
        "trade_count": len(trades),
        "win_rate": sum(1 for item in completed_returns if item > 0) / completed_count if completed_count else 0.0,
        "average_holding_days": sum(holding_days) / len(holding_days) if holding_days else 0.0,
        "total_cost": total_cost,
        "entry_breakout_count": entry_breakout_count,
        "effective_buy_count": effective_buy_count,
        "exit_breakout_count": exit_breakout_count,
        "effective_sell_count": effective_sell_count,
        "aligned_days": len(result_rows),
    }
    return {"rows": result_rows, "trades": trades, "metrics": metrics}


def empty_metrics(variant: str, entry_window: int, exit_window: int, aligned_days: int = 0) -> dict[str, float | int | str]:
    return {
        "variant": variant,
        "entry_window": entry_window,
        "exit_window": exit_window,
        "strategy_return": 0.0,
        "benchmark_return": 0.0,
        "excess_return": 0.0,
        "annual_return": 0.0,
        "annual_volatility": 0.0,
        "max_drawdown": 0.0,
        "sharpe_ratio": 0.0,
        "trade_count": 0,
        "win_rate": 0.0,
        "average_holding_days": 0.0,
        "total_cost": 0.0,
        "entry_breakout_count": 0,
        "effective_buy_count": 0,
        "exit_breakout_count": 0,
        "effective_sell_count": 0,
        "aligned_days": aligned_days,
    }
