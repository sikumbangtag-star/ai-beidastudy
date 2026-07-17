from task6.src.ml_strategy_backtest import run_pipeline


if __name__ == "__main__":
    result = run_pipeline()
    print(result["metrics"].to_string(index=False))
    print(result["backtest_metrics"].to_string(index=False))

