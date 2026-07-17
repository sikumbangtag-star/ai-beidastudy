from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TASK6 = ROOT / "task6"
OUTPUT_DIR = TASK6 / "outputs"
FIGURE_DIR = OUTPUT_DIR / "figures"


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def svg_line_chart(rows: list[dict], model: str, path: Path) -> None:
    selected = [row for row in rows if row["model"] == model]
    if not selected:
        return
    navs = []
    strategy = equal = hs300 = 1.0
    for row in selected:
        strategy *= 1 + float(row["strategy_return"])
        equal *= 1 + float(row["equal_weight_return"])
        hs300 *= 1 + float(row["hs300_return"])
        navs.append({"date": row["Date"], "strategy": strategy, "equal": equal, "hs300": hs300})
    values = [v for row in navs for v in [row["strategy"], row["equal"], row["hs300"]]]
    lo, hi = min(values + [0.95]), max(values + [1.05])

    def x(i: int) -> float:
        return 70 + (0 if len(navs) == 1 else i * 540 / (len(navs) - 1))

    def y(v: float) -> float:
        return 330 - (v - lo) / ((hi - lo) or 1) * 250

    def path_for(key: str) -> str:
        return " ".join(f"{'M' if i == 0 else 'L'} {x(i):.1f} {y(row[key]):.1f}" for i, row in enumerate(navs))

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="760" height="420" viewBox="0 0 760 420">
<rect width="760" height="420" fill="#ffffff"/>
<text x="24" y="34" font-family="Arial" font-size="20" fill="#111827">{model} strategy NAV</text>
<line x1="70" y1="330" x2="650" y2="330" stroke="#d1d5db"/>
<line x1="70" y1="70" x2="70" y2="330" stroke="#d1d5db"/>
<path d="{path_for('strategy')}" fill="none" stroke="#2563eb" stroke-width="4"/>
<path d="{path_for('equal')}" fill="none" stroke="#16a34a" stroke-width="3"/>
<path d="{path_for('hs300')}" fill="none" stroke="#d97706" stroke-width="3"/>
<text x="70" y="380" font-family="Arial" font-size="13" fill="#2563eb">strategy</text>
<text x="160" y="380" font-family="Arial" font-size="13" fill="#16a34a">equal-weight</text>
<text x="280" y="380" font-family="Arial" font-size="13" fill="#d97706">HS300</text>
</svg>"""
    path.write_text(svg, encoding="utf-8")


def svg_quarter_chart(rows: list[dict], model: str, path: Path) -> None:
    selected = [row for row in rows if row["model"] == model]
    if not selected:
        return
    vals = [float(row[key]) for row in selected for key in ["strategy_return", "equal_weight_return", "hs300_return"]]
    lo, hi = min(vals + [0]), max(vals + [0])

    def y(v: float) -> float:
        return 320 - (v - lo) / ((hi - lo) or 1) * 240

    zero = y(0)
    bars = []
    for i, row in enumerate(selected):
        base = 90 + i * 150
        for j, (key, color) in enumerate(
            [("strategy_return", "#2563eb"), ("equal_weight_return", "#16a34a"), ("hs300_return", "#d97706")]
        ):
            yy = y(float(row[key]))
            bars.append(
                f'<rect x="{base+j*28}" y="{min(yy, zero):.1f}" width="22" height="{abs(zero-yy):.1f}" fill="{color}"/>'
            )
        bars.append(f'<text x="{base+34}" y="360" font-family="Arial" font-size="12" text-anchor="middle">{row["Date"][:7]}</text>')

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="760" height="420" viewBox="0 0 760 420">
<rect width="760" height="420" fill="#ffffff"/>
<text x="24" y="34" font-family="Arial" font-size="20" fill="#111827">{model} quarterly returns</text>
<line x1="70" y1="{zero:.1f}" x2="650" y2="{zero:.1f}" stroke="#d1d5db"/>
{''.join(bars)}
<text x="70" y="395" font-family="Arial" font-size="13" fill="#2563eb">strategy</text>
<text x="160" y="395" font-family="Arial" font-size="13" fill="#16a34a">equal-weight</text>
<text x="280" y="395" font-family="Arial" font-size="13" fill="#d97706">HS300</text>
</svg>"""
    path.write_text(svg, encoding="utf-8")


def svg_model_comparison(metrics: list[dict], path: Path) -> None:
    values = [float(row["strategy_return"]) for row in metrics]
    lo, hi = min(values + [0]), max(values + [0])

    def y(v: float) -> float:
        return 320 - (v - lo) / ((hi - lo) or 1) * 240

    zero = y(0)
    bars = []
    for i, row in enumerate(metrics):
        x = 90 + i * 150
        value = float(row["strategy_return"])
        yy = y(value)
        bars.append(f'<rect x="{x}" y="{min(yy, zero):.1f}" width="56" height="{abs(zero-yy):.1f}" fill="#2563eb"/>')
        bars.append(f'<text x="{x+28}" y="360" font-family="Arial" font-size="12" text-anchor="middle">{row["model_label"]}</text>')
        bars.append(f'<text x="{x+28}" y="{min(yy, zero)-8:.1f}" font-family="Arial" font-size="12" text-anchor="middle">{pct(value)}</text>')
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="760" height="420" viewBox="0 0 760 420">
<rect width="760" height="420" fill="#ffffff"/>
<text x="24" y="34" font-family="Arial" font-size="20" fill="#111827">Model comparison: strategy return</text>
<line x1="70" y1="{zero:.1f}" x2="690" y2="{zero:.1f}" stroke="#d1d5db"/>
{''.join(bars)}
</svg>"""
    path.write_text(svg, encoding="utf-8")


def main() -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.loads((OUTPUT_DIR / "strategy_payload.json").read_text(encoding="utf-8"))
    rows = payload["quarterly_returns"]
    for model in payload["model_labels"]:
        svg_line_chart(rows, model, FIGURE_DIR / f"nav_{model}.svg")
        svg_quarter_chart(rows, model, FIGURE_DIR / f"quarterly_returns_{model}.svg")
    svg_model_comparison(payload["backtest_metrics"], FIGURE_DIR / "model_comparison_strategy_return.svg")
    print(FIGURE_DIR)


if __name__ == "__main__":
    main()

