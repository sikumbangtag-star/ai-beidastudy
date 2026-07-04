from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Iterable

import pandas as pd


SVG_WIDTH = 1100
SVG_HEIGHT = 420
PADDING_LEFT = 70
PADDING_RIGHT = 30
PADDING_TOP = 52
PADDING_BOTTOM = 58


def _fmt(value: object, digits: int = 2) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (float, int)):
        return f"{value:.{digits}f}"
    return str(value)


def _date_labels(dates: pd.Series) -> list[str]:
    labels = []
    for value in dates:
        if hasattr(value, "strftime"):
            labels.append(value.strftime("%Y-%m-%d"))
        else:
            labels.append(str(value))
    return labels


def _scale_points(values: Iterable[float], y_min: float, y_max: float) -> list[float]:
    plot_height = SVG_HEIGHT - PADDING_TOP - PADDING_BOTTOM
    if y_max == y_min:
        return [PADDING_TOP + plot_height / 2 for _ in values]
    return [
        PADDING_TOP + (y_max - float(value)) / (y_max - y_min) * plot_height
        for value in values
    ]


def _x_positions(count: int) -> list[float]:
    plot_width = SVG_WIDTH - PADDING_LEFT - PADDING_RIGHT
    if count <= 1:
        return [PADDING_LEFT + plot_width / 2]
    return [PADDING_LEFT + idx / (count - 1) * plot_width for idx in range(count)]


def _polyline(points: list[tuple[float, float]], color: str, width: float = 2.0) -> str:
    usable = [(x, y) for x, y in points if pd.notna(y)]
    if len(usable) < 2:
        return ""
    value = " ".join(f"{x:.1f},{y:.1f}" for x, y in usable)
    return (
        f'<polyline points="{value}" fill="none" stroke="{color}" '
        f'stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round" />'
    )


def _chart_frame(title: str, subtitle: str, y_min: float, y_max: float, dates: pd.Series) -> list[str]:
    labels = _date_labels(dates)
    left_label = labels[0] if labels else ""
    mid_label = labels[len(labels) // 2] if labels else ""
    right_label = labels[-1] if labels else ""
    plot_right = SVG_WIDTH - PADDING_RIGHT
    plot_bottom = SVG_HEIGHT - PADDING_BOTTOM

    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{SVG_HEIGHT}" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{PADDING_LEFT}" y="28" font-size="24" font-family="Arial, Microsoft YaHei, sans-serif" font-weight="700" fill="#111827">{escape(title)}</text>',
        f'<text x="{PADDING_LEFT}" y="48" font-size="13" font-family="Arial, Microsoft YaHei, sans-serif" fill="#6b7280">{escape(subtitle)}</text>',
        f'<line x1="{PADDING_LEFT}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" stroke="#d1d5db"/>',
        f'<line x1="{PADDING_LEFT}" y1="{PADDING_TOP}" x2="{PADDING_LEFT}" y2="{plot_bottom}" stroke="#d1d5db"/>',
        f'<text x="16" y="{PADDING_TOP + 5}" font-size="12" font-family="Arial" fill="#6b7280">{y_max:.2f}</text>',
        f'<text x="16" y="{plot_bottom}" font-size="12" font-family="Arial" fill="#6b7280">{y_min:.2f}</text>',
        f'<text x="{PADDING_LEFT}" y="{SVG_HEIGHT - 20}" font-size="12" font-family="Arial" fill="#6b7280">{escape(left_label)}</text>',
        f'<text x="{SVG_WIDTH / 2 - 40}" y="{SVG_HEIGHT - 20}" font-size="12" font-family="Arial" fill="#6b7280">{escape(mid_label)}</text>',
        f'<text x="{SVG_WIDTH - 118}" y="{SVG_HEIGHT - 20}" font-size="12" font-family="Arial" fill="#6b7280">{escape(right_label)}</text>',
    ]


def _write_svg(path: Path, parts: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts + ["</svg>"]), encoding="utf-8")
    return path


def write_line_chart(
    df: pd.DataFrame,
    path: Path,
    title: str,
    subtitle: str,
    series: list[tuple[str, str]],
) -> Path:
    chart_df = df.dropna(subset=[column for column, _ in series]).copy()
    if chart_df.empty:
        raise ValueError(f"No data available for chart: {title}")

    y_values = pd.concat([chart_df[column] for column, _ in series])
    y_min = float(y_values.min())
    y_max = float(y_values.max())
    y_pad = (y_max - y_min) * 0.08 if y_max != y_min else max(abs(y_max) * 0.08, 1)
    y_min -= y_pad
    y_max += y_pad
    x_values = _x_positions(len(chart_df))
    parts = _chart_frame(title, subtitle, y_min, y_max, chart_df["trade_date"])

    for idx, (column, color) in enumerate(series):
        y_values = _scale_points(chart_df[column], y_min, y_max)
        parts.append(_polyline(list(zip(x_values, y_values)), color, width=2.2 if idx == 0 else 1.7))

    legend_x = PADDING_LEFT
    for column, color in series:
        parts.append(f'<circle cx="{legend_x}" cy="72" r="5" fill="{color}"/>')
        parts.append(f'<text x="{legend_x + 10}" y="76" font-size="12" font-family="Arial" fill="#374151">{escape(column)}</text>')
        legend_x += 120

    return _write_svg(path, parts)


def write_bar_chart(
    df: pd.DataFrame,
    path: Path,
    title: str,
    subtitle: str,
    column: str,
    color: str,
) -> Path:
    chart_df = df.dropna(subset=[column]).copy()
    if chart_df.empty:
        raise ValueError(f"No data available for chart: {title}")

    y_min = 0.0
    y_max = float(chart_df[column].max()) * 1.08
    x_values = _x_positions(len(chart_df))
    plot_bottom = SVG_HEIGHT - PADDING_BOTTOM
    plot_height = SVG_HEIGHT - PADDING_TOP - PADDING_BOTTOM
    bar_width = max(1.0, (SVG_WIDTH - PADDING_LEFT - PADDING_RIGHT) / max(len(chart_df), 1) * 0.65)
    parts = _chart_frame(title, subtitle, y_min, y_max, chart_df["trade_date"])

    for x, value in zip(x_values, chart_df[column]):
        height = 0 if y_max == 0 else float(value) / y_max * plot_height
        parts.append(
            f'<rect x="{x - bar_width / 2:.1f}" y="{plot_bottom - height:.1f}" '
            f'width="{bar_width:.1f}" height="{height:.1f}" fill="{color}" opacity="0.78"/>'
        )

    return _write_svg(path, parts)


def write_macd_chart(df: pd.DataFrame, path: Path) -> Path:
    chart_df = df.dropna(subset=["macd_dif", "macd_dea", "macd_hist"]).copy()
    if chart_df.empty:
        raise ValueError("No data available for MACD chart")

    y_values = pd.concat([chart_df["macd_dif"], chart_df["macd_dea"], chart_df["macd_hist"]])
    y_min = float(y_values.min())
    y_max = float(y_values.max())
    y_pad = (y_max - y_min) * 0.1 if y_max != y_min else 1
    y_min -= y_pad
    y_max += y_pad
    x_values = _x_positions(len(chart_df))
    y_zero = _scale_points([0], y_min, y_max)[0]
    plot_bottom = SVG_HEIGHT - PADDING_BOTTOM
    bar_width = max(1.0, (SVG_WIDTH - PADDING_LEFT - PADDING_RIGHT) / max(len(chart_df), 1) * 0.55)
    parts = _chart_frame("MACD 动能", "DIF / DEA 与 MACD 柱状图", y_min, y_max, chart_df["trade_date"])
    parts.append(f'<line x1="{PADDING_LEFT}" y1="{y_zero:.1f}" x2="{SVG_WIDTH - PADDING_RIGHT}" y2="{y_zero:.1f}" stroke="#9ca3af" stroke-dasharray="4 4"/>')

    for x, value in zip(x_values, chart_df["macd_hist"]):
        y = _scale_points([value], y_min, y_max)[0]
        color = "#ef4444" if value >= 0 else "#2563eb"
        parts.append(
            f'<rect x="{x - bar_width / 2:.1f}" y="{min(y, y_zero):.1f}" '
            f'width="{bar_width:.1f}" height="{abs(y_zero - y):.1f}" fill="{color}" opacity="0.58"/>'
        )

    dif_y = _scale_points(chart_df["macd_dif"], y_min, y_max)
    dea_y = _scale_points(chart_df["macd_dea"], y_min, y_max)
    parts.append(_polyline(list(zip(x_values, dif_y)), "#111827", 2.0))
    parts.append(_polyline(list(zip(x_values, dea_y)), "#f59e0b", 2.0))
    return _write_svg(path, parts)


def write_all_svg_charts(df: pd.DataFrame, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = [
        write_line_chart(
            df,
            output_dir / "price_bollinger.svg",
            "收盘价与布林带",
            "Close / Bollinger Upper / Mid / Lower",
            [
                ("close", "#111827"),
                ("boll_upper", "#ef4444"),
                ("boll_mid", "#f59e0b"),
                ("boll_lower", "#2563eb"),
            ],
        ),
        write_bar_chart(df, output_dir / "volume.svg", "成交量", "Volume", "vol", "#14b8a6"),
        write_line_chart(
            df,
            output_dir / "rsi.svg",
            "RSI 14",
            "70/30 是常见超买超卖参考线",
            [("rsi_14", "#7c3aed")],
        ),
        write_macd_chart(df, output_dir / "macd.svg"),
        write_line_chart(
            df,
            output_dir / "kdj.svg",
            "KDJ 9,3,3",
            "K / D / J 随机指标",
            [
                ("kdj_k", "#2563eb"),
                ("kdj_d", "#f59e0b"),
                ("kdj_j", "#7c3aed"),
            ],
        ),
        write_line_chart(df, output_dir / "atr.svg", "ATR 14", "平均真实波幅", [("atr_14", "#dc2626")]),
    ]
    return paths


def build_summary_markdown(summary: dict[str, object]) -> str:
    return "\n".join(
        [
            "# 金安国纪 Task2 指标摘要",
            "",
            f"- 交易日期: {summary['trade_date']}",
            f"- 股票代码: {summary['ts_code']}",
            f"- 收盘价: {_fmt(summary['close'])}",
            f"- RSI(14): {_fmt(summary['rsi_14'])}",
            f"- MACD DIF / DEA / 柱: {_fmt(summary['macd_dif'])} / {_fmt(summary['macd_dea'])} / {_fmt(summary['macd_hist'])}",
            f"- 布林带上/中/下轨: {_fmt(summary['boll_upper'])} / {_fmt(summary['boll_mid'])} / {_fmt(summary['boll_lower'])}",
            f"- ATR(14): {_fmt(summary['atr_14'])}",
            "",
            "## 解读",
            "",
            f"- RSI: {summary['rsi_view']}",
            f"- MACD: {summary['macd_view']}",
            f"- 布林带: {summary['boll_view']}",
            f"- ATR: {summary['atr_view']}",
            "",
            "> 技术指标只描述历史价格和波动特征，不构成投资建议。",
            "",
        ]
    )


def write_summary_markdown(summary: dict[str, object], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_summary_markdown(summary), encoding="utf-8")
    return output_path
