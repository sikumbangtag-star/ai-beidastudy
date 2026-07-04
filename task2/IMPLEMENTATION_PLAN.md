# Task2 Implementation Plan

> For this project: all new files stay under `task2/`. The implementation reuses `task1/outputs/jinan_guoji/daily_prices.csv` and does not call Tushare again.

## Goal

Build a runnable notebook that calculates RSI, MACD, Bollinger Bands, and ATR for 金安国纪 using the existing task1 daily price data.

## Files

- `task2/src/indicators.py`: indicator calculations, data validation, summary helpers.
- `task2/tests/test_indicators.py`: standard-library tests for the indicator functions.
- `task2/notebooks/jinan_guoji_indicators.ipynb`: teaching notebook with calculation process and charts.
- `task2/data/jinan_guoji_indicators.csv`: generated dataset with indicator columns.
- `task2/outputs/jinan_guoji_indicator_summary.md`: generated latest-day summary.
- `task2/outputs/figures/`: generated SVG charts.

## Steps

1. Add failing tests for validation, RSI/MACD/Bollinger/ATR output columns, and CSV output shape.
2. Implement indicator functions with pandas and numpy only.
3. Run tests with `python -m unittest`.
4. Generate the notebook as plain `.ipynb` JSON to avoid depending on `nbformat`.
5. Execute the notebook cells with the local Python runtime to verify it runs from top to bottom.
6. Commit the task2 implementation locally after verification.
