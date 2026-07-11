from __future__ import annotations

import math
from typing import Any


BUY_COST_RATE = 0.0005441
SELL_COST_RATE = 0.0010441


def moving_average(values: list[float], window: int) -> list[float | None]:
    if window <= 0:
        raise ValueError("window must be positive")
    result: list[float | None] = []
    rolling_sum = 0.0
    for index, value in enumerate(values):
        rolling_sum += value
        if index >= window:
            rolling_sum -= values[index - window]
        result.append(rolling_sum / window if index >= window - 1 else None)
    return result


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


def compute_dual_ma_strategy(
    stock_rows: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
    fast_window: int = 5,
    slow_window: int = 20,
    require_three_bullish: bool = True,
    require_market_up: bool = True,
    buy_cost_rate: float = BUY_COST_RATE,
    sell_cost_rate: float = SELL_COST_RATE,
) -> dict[str, Any]:
    if fast_window <= 0 or slow_window <= 0:
        raise ValueError("MA windows must be positive")
    if fast_window >= slow_window:
        raise ValueError("fast_window must be less than slow_window")

    aligned = align_stock_and_benchmark(stock_rows, benchmark_rows)
    if len(aligned) < slow_window + 1:
        return {"rows": [], "trades": [], "metrics": empty_metrics(len(aligned))}

    closes = [float(stock["close"]) for stock, _ in aligned]
    fast_ma = moving_average(closes, fast_window)
    slow_ma = moving_average(closes, slow_window)
    benchmark_start = float(aligned[0][1]["close"])

    cash = 1.0
    shares = 0.0
    holding = False
    pending: dict[str, Any] | None = None
    entry_nav = 1.0
    entry_index: int | None = None
    total_cost = 0.0
    golden_cross_count = 0
    effective_buy_count = 0
    filtered_buy_count = 0
    completed_returns: list[float] = []
    holding_days: list[int] = []
    trades: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []

    def three_bullish(index: int) -> bool:
        if index < 2:
            return False
        return all(float(aligned[item][0]["close"]) > float(aligned[item][0]["open"]) for item in range(index - 2, index + 1))

    def market_up(index: int) -> bool:
        if index < 1:
            return False
        return float(aligned[index][1]["close"]) > float(aligned[index - 1][1]["close"])

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

        nav = shares * float(stock["close"]) if holding else cash
        benchmark_nav = float(benchmark["close"]) / benchmark_start if benchmark_start else 1.0
        prev_fast = fast_ma[index - 1] if index else None
        prev_slow = slow_ma[index - 1] if index else None
        curr_fast = fast_ma[index]
        curr_slow = slow_ma[index]
        golden_cross = (
            prev_fast is not None
            and prev_slow is not None
            and curr_fast is not None
            and curr_slow is not None
            and prev_fast <= prev_slow
            and curr_fast > curr_slow
        )
        death_cross = (
            prev_fast is not None
            and prev_slow is not None
            and curr_fast is not None
            and curr_slow is not None
            and prev_fast >= prev_slow
            and curr_fast < curr_slow
        )
        three_bullish_ok = three_bullish(index)
        market_up_ok = market_up(index)
        filtered_buy = False

        if index < len(aligned) - 1 and pending is None:
            if not holding and golden_cross:
                golden_cross_count += 1
                passes_three = three_bullish_ok or not require_three_bullish
                passes_market = market_up_ok or not require_market_up
                if passes_three and passes_market:
                    effective_buy_count += 1
                    pending = {
                        "side": "BUY",
                        "signal_date": stock["trade_date"],
                        "signal_index": index,
                        "exec_index": index + 1,
                        "three_bullish": three_bullish_ok,
                        "market_up": market_up_ok,
                    }
                else:
                    filtered_buy_count += 1
                    filtered_buy = True
            elif holding and death_cross:
                pending = {
                    "side": "SELL",
                    "signal_date": stock["trade_date"],
                    "signal_index": index,
                    "exec_index": index + 1,
                    "three_bullish": three_bullish_ok,
                    "market_up": market_up_ok,
                }

        result_rows.append(
            {
                **stock,
                "fast_ma": curr_fast,
                "slow_ma": curr_slow,
                "golden_cross": golden_cross,
                "death_cross": death_cross,
                "filtered_buy": filtered_buy,
                "three_bullish": three_bullish_ok,
                "market_up": market_up_ok,
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
        "golden_cross_count": golden_cross_count,
        "effective_buy_count": effective_buy_count,
        "filtered_buy_count": filtered_buy_count,
        "aligned_days": len(result_rows),
    }
    return {"rows": result_rows, "trades": trades, "metrics": metrics}


def empty_metrics(aligned_days: int = 0) -> dict[str, float | int]:
    return {
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
        "golden_cross_count": 0,
        "effective_buy_count": 0,
        "filtered_buy_count": 0,
        "aligned_days": aligned_days,
    }
