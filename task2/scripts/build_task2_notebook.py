from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from task2.src.indicators import load_and_calculate, latest_indicator_summary
from task2.src.reporting import write_all_svg_charts, write_summary_markdown

TASK2 = ROOT / "task2"
INPUT_CSV = ROOT / "task1" / "outputs" / "jinan_guoji" / "daily_prices.csv"
DATA_CSV = TASK2 / "data" / "jinan_guoji_indicators.csv"
SUMMARY_MD = TASK2 / "outputs" / "jinan_guoji_indicator_summary.md"
FIGURE_DIR = TASK2 / "outputs" / "figures"
NOTEBOOK = TASK2 / "notebooks" / "jinan_guoji_indicators.ipynb"


def markdown_cell(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code_cell(code: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": code.splitlines(keepends=True),
    }


def build_notebook() -> dict:
    cells = [
        markdown_cell(
            "# 金安国纪价格技术指标分析\n\n"
            "本 notebook 使用 task1 已经保存的金安国纪日线行情数据，不重新调用 Tushare。"
            "计算 RSI、MACD、布林带和 ATR，并展示计算过程、图表和最近交易日摘要。"
        ),
        code_cell(
            "from pathlib import Path\n"
            "import sys\n"
            "import pandas as pd\n\n"
            "def find_project_root(start):\n"
            "    start = Path(start).resolve()\n"
            "    for candidate in [start, *start.parents]:\n"
            "        if (candidate / 'task1').exists() and (candidate / 'task2').exists():\n"
            "            return candidate\n"
            "    raise FileNotFoundError('无法定位项目根目录：需要同时包含 task1 和 task2')\n\n"
            "ROOT = find_project_root(Path.cwd())\n"
            "sys.path.insert(0, str(ROOT))\n\n"
            "from task2.src.indicators import clean_price_data, add_all_indicators, latest_indicator_summary\n"
            "from task2.src.reporting import write_all_svg_charts, write_summary_markdown\n\n"
            "INPUT_CSV = ROOT / 'task1' / 'outputs' / 'jinan_guoji' / 'daily_prices.csv'\n"
            "DATA_CSV = ROOT / 'task2' / 'data' / 'jinan_guoji_indicators.csv'\n"
            "SUMMARY_MD = ROOT / 'task2' / 'outputs' / 'jinan_guoji_indicator_summary.md'\n"
            "FIGURE_DIR = ROOT / 'task2' / 'outputs' / 'figures'\n"
            "INPUT_CSV"
        ),
        markdown_cell("## 1. 读取原始数据\n\n原始数据来自 task1，不在本任务中重新拉取。"),
        code_cell(
            "raw = pd.read_csv(INPUT_CSV)\n"
            "print(raw.shape)\n"
            "raw.head()"
        ),
        markdown_cell("## 2. 清洗和排序\n\n将交易日期转为日期类型，核心价格和成交量字段转为数值，并按交易日期升序排列。"),
        code_cell(
            "prices = clean_price_data(raw)\n"
            "print(prices[['trade_date', 'open', 'high', 'low', 'close', 'vol']].dtypes)\n"
            "prices.head()"
        ),
        markdown_cell("## 3. 数据质量检查\n\n检查缺失值、重复交易日和价格字段的基本合理性。"),
        code_cell(
            "required = ['trade_date', 'open', 'high', 'low', 'close', 'vol']\n"
            "quality = pd.DataFrame({\n"
            "    'missing_count': prices[required].isna().sum(),\n"
            "})\n"
            "duplicate_dates = prices['trade_date'].duplicated().sum()\n"
            "invalid_price_rows = ((prices['high'] < prices['low']) | (prices['close'] <= 0)).sum()\n"
            "print(f'重复交易日数量: {duplicate_dates}')\n"
            "print(f'价格异常行数量: {invalid_price_rows}')\n"
            "quality"
        ),
        markdown_cell(
            "## 4. 计算技术指标\n\n"
            "- RSI 使用 14 日 Wilder 平滑。\n"
            "- MACD 使用 12、26、9 参数。\n"
            "- 布林带使用 20 日均线和 2 倍标准差。\n"
            "- ATR 使用 14 日真实波幅 Wilder 平滑。"
        ),
        code_cell(
            "indicators = add_all_indicators(prices)\n"
            "DATA_CSV.parent.mkdir(parents=True, exist_ok=True)\n"
            "indicators.to_csv(DATA_CSV, index=False, encoding='utf-8-sig')\n"
            "print(f'指标数据已保存: {DATA_CSV}')\n"
            "indicators.tail()"
        ),
        markdown_cell("## 5. 最近交易日摘要"),
        code_cell(
            "summary = latest_indicator_summary(indicators)\n"
            "write_summary_markdown(summary, SUMMARY_MD)\n"
            "summary"
        ),
        markdown_cell("## 6. 生成图表\n\n下面代码生成 SVG 图表，后面的 Markdown 单元格会直接展示这些图。"),
        code_cell(
            "figure_paths = write_all_svg_charts(indicators, FIGURE_DIR)\n"
            "for path in figure_paths:\n"
            "    print(path)"
        ),
        markdown_cell("### 收盘价与布林带\n\n![收盘价与布林带](../outputs/figures/price_bollinger.svg)"),
        markdown_cell("### 成交量\n\n![成交量](../outputs/figures/volume.svg)"),
        markdown_cell("### RSI\n\n![RSI](../outputs/figures/rsi.svg)"),
        markdown_cell("### MACD\n\n![MACD](../outputs/figures/macd.svg)"),
        markdown_cell("### ATR\n\n![ATR](../outputs/figures/atr.svg)"),
        markdown_cell(
            "## 7. 简短结论和风险提示\n\n"
            "技术指标显示的是历史价格、趋势动能和波动状态。RSI 用于观察短期强弱，MACD 用于观察趋势动能，"
            "布林带用于观察价格相对均值的位置，ATR 用于观察波动风险。以上结果不构成投资建议。"
        ),
    ]

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "pygments_lexer": "ipython3",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    indicators = load_and_calculate(INPUT_CSV, DATA_CSV)
    summary = latest_indicator_summary(indicators)
    write_summary_markdown(summary, SUMMARY_MD)
    write_all_svg_charts(indicators, FIGURE_DIR)

    NOTEBOOK.parent.mkdir(parents=True, exist_ok=True)
    NOTEBOOK.write_text(
        json.dumps(build_notebook(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {NOTEBOOK}")
    print(f"Wrote {DATA_CSV}")
    print(f"Wrote {SUMMARY_MD}")
    print(f"Wrote figures to {FIGURE_DIR}")


if __name__ == "__main__":
    main()
