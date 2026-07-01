#!/usr/bin/env python3
"""Fetch Jinan Guoji Tushare data and build a static HTML panel."""

from __future__ import annotations

import csv
import datetime as dt
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CODEX_CONFIG = Path.home() / ".codex" / "config.toml"
OUT_DIR = ROOT / "outputs" / "jinan_guoji"
TS_CODE = "002636.SZ"
COMPANY_NAME = "金安国纪"
END_DATE = dt.date(2026, 6, 30)
START_DATE = END_DATE - dt.timedelta(days=365)
FALLBACK_DIVIDEND_ROWS = [
    {"ts_code": TS_CODE, "end_date": "20230630", "ann_date": "20230831", "div_proc": "预案", "stk_div": 0.0, "cash_div": 0.0, "cash_div_tax": 0.0, "record_date": None, "ex_date": None, "pay_date": None},
    {"ts_code": TS_CODE, "end_date": "20231231", "ann_date": "20240429", "div_proc": "预案", "stk_div": 0.0, "cash_div": 0.0, "cash_div_tax": 0.06, "record_date": None, "ex_date": None, "pay_date": None},
    {"ts_code": TS_CODE, "end_date": "20231231", "ann_date": "20240429", "div_proc": "股东大会通过", "stk_div": 0.0, "cash_div": 0.0, "cash_div_tax": 0.06, "record_date": None, "ex_date": None, "pay_date": None},
    {"ts_code": TS_CODE, "end_date": "20231231", "ann_date": "20240429", "div_proc": "实施", "stk_div": 0.0, "cash_div": 0.06, "cash_div_tax": 0.06, "record_date": "20240617", "ex_date": "20240618", "pay_date": "20240618"},
    {"ts_code": TS_CODE, "end_date": "20240630", "ann_date": "20240831", "div_proc": "预案", "stk_div": 0.0, "cash_div": 0.0, "cash_div_tax": 0.0, "record_date": None, "ex_date": None, "pay_date": None},
    {"ts_code": TS_CODE, "end_date": "20241231", "ann_date": "20250429", "div_proc": "预案", "stk_div": 0.0, "cash_div": 0.0, "cash_div_tax": 0.085, "record_date": None, "ex_date": None, "pay_date": None},
    {"ts_code": TS_CODE, "end_date": "20241231", "ann_date": "20250429", "div_proc": "股东大会通过", "stk_div": 0.0, "cash_div": 0.0, "cash_div_tax": 0.085, "record_date": None, "ex_date": None, "pay_date": None},
    {"ts_code": TS_CODE, "end_date": "20241231", "ann_date": "20250429", "div_proc": "实施", "stk_div": 0.0, "cash_div": 0.085, "cash_div_tax": 0.085, "record_date": "20250528", "ex_date": "20250529", "pay_date": "20250529"},
    {"ts_code": TS_CODE, "end_date": "20250630", "ann_date": "20250830", "div_proc": "预案", "stk_div": 0.0, "cash_div": 0.0, "cash_div_tax": 0.0, "record_date": None, "ex_date": None, "pay_date": None},
    {"ts_code": TS_CODE, "end_date": "20251231", "ann_date": "20260429", "div_proc": "预案", "stk_div": 0.0, "cash_div": 0.0, "cash_div_tax": 0.125, "record_date": None, "ex_date": None, "pay_date": None},
    {"ts_code": TS_CODE, "end_date": "20251231", "ann_date": "20260429", "div_proc": "股东大会通过", "stk_div": 0.0, "cash_div": 0.0, "cash_div_tax": 0.125, "record_date": None, "ex_date": None, "pay_date": None},
    {"ts_code": TS_CODE, "end_date": "20251231", "ann_date": "20260429", "div_proc": "实施", "stk_div": 0.0, "cash_div": 0.125, "cash_div_tax": 0.125, "record_date": "20260527", "ex_date": "20260528", "pay_date": "20260528"},
]


class TushareApiError(RuntimeError):
    def __init__(self, api_name: str, code: Any, message: str) -> None:
        super().__init__(f"{api_name} failed [{code}]: {message}")
        self.api_name = api_name
        self.code = code
        self.message = message


def ymd(value: dt.date) -> str:
    return value.strftime("%Y%m%d")


def read_tushare_token() -> str:
    text = CODEX_CONFIG.read_text(encoding="utf-8-sig")
    match = re.search(r"https://api\.tushare\.pro/mcp/\?token=([A-Za-z0-9]+)", text)
    if not match:
        raise RuntimeError(f"Could not find Tushare MCP token in {CODEX_CONFIG}")
    return match.group(1)


def call_tushare(
    token: str,
    api_name: str,
    params: dict[str, Any] | None = None,
    fields: list[str] | None = None,
    retries: int = 3,
) -> list[dict[str, Any]]:
    payload = {
        "api_name": api_name,
        "token": token,
        "params": params or {},
        "fields": ",".join(fields or []),
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.tushare.pro",
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "codex-jinan-guoji-panel/1.0"},
        method="POST",
    )

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("code") != 0:
                raise TushareApiError(api_name, result.get("code"), result.get("msg") or "")
            data_block = result.get("data") or {}
            names = data_block.get("fields") or []
            rows = data_block.get("items") or []
            return [dict(zip(names, row)) for row in rows]
        except TushareApiError as exc:
            if exc.code in (40203, "40203"):
                raise
            last_error = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{api_name} failed after retries: {last_error}")


def optional_call(
    token: str,
    api_name: str,
    errors: list[str],
    params: dict[str, Any] | None = None,
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    try:
        return call_tushare(token, api_name, params, fields)
    except TushareApiError as exc:
        errors.append(str(exc))
        return []


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sort_by_date(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: str(row.get(key) or ""))


def latest_by_period(rows: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: (str(item.get("end_date") or ""), str(item.get("ann_date") or "")), reverse=True):
        marker = (str(row.get("end_date") or ""), str(row.get("report_type") or ""))
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(row)
        if len(deduped) >= limit:
            break
    return list(reversed(deduped))


def num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt_amount(value: Any) -> str:
    number = num(value)
    if number is None:
        return "-"
    abs_number = abs(number)
    if abs_number >= 100_000_000:
        return f"{number / 100_000_000:.2f}亿"
    if abs_number >= 10_000:
        return f"{number / 10_000:.2f}万"
    return f"{number:.2f}"


def build_html(panel: dict[str, Any]) -> str:
    data_json = json.dumps(panel, ensure_ascii=False)
    escaped_title = html.escape(f"{COMPANY_NAME}（{TS_CODE}）近一年交易与财务面板")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7fb;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #61708a;
      --grid: #e1e7f0;
      --red: #d94b3d;
      --green: #15956f;
      --blue: #2d6cdf;
      --amber: #b7791f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      background: var(--bg);
      color: var(--ink);
    }}
    header {{
      padding: 22px 28px 14px;
      background: #ffffff;
      border-bottom: 1px solid var(--grid);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 24px;
      letter-spacing: 0;
    }}
    .subtle {{ color: var(--muted); font-size: 13px; }}
    main {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 360px;
      gap: 14px;
      padding: 14px;
      max-width: 1500px;
      margin: 0 auto;
    }}
    section, aside > div {{
      background: var(--panel);
      border: 1px solid var(--grid);
      border-radius: 8px;
      padding: 14px;
    }}
    .chart-wrap {{ min-height: 620px; }}
    canvas {{
      display: block;
      width: 100%;
      height: 560px;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin: 12px 0 4px;
    }}
    .stat {{
      border: 1px solid var(--grid);
      border-radius: 6px;
      padding: 10px;
      min-height: 74px;
    }}
    .label {{ font-size: 12px; color: var(--muted); }}
    .value {{ margin-top: 8px; font-size: 20px; font-weight: 700; }}
    aside {{
      display: grid;
      gap: 14px;
      align-content: start;
    }}
    h2 {{
      margin: 0 0 10px;
      font-size: 16px;
      letter-spacing: 0;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }}
    th, td {{
      border-bottom: 1px solid var(--grid);
      padding: 7px 4px;
      text-align: right;
      vertical-align: top;
    }}
    th:first-child, td:first-child, .left {{ text-align: left; }}
    .scroll {{ max-height: 350px; overflow: auto; }}
    .positive {{ color: var(--red); }}
    .negative {{ color: var(--green); }}
    .note {{ margin-top: 8px; color: var(--muted); font-size: 12px; line-height: 1.6; }}
    @media (max-width: 980px) {{
      main {{ grid-template-columns: 1fr; padding: 10px; }}
      .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      canvas {{ height: 470px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{escaped_title}</h1>
    <div class="subtle" id="meta"></div>
  </header>
  <main>
    <section class="chart-wrap">
      <h2>K线与成交量</h2>
      <canvas id="priceChart" width="1100" height="560" aria-label="金安国纪K线和成交量图"></canvas>
      <div class="stats" id="stats"></div>
      <div class="note">红色表示收盘高于或等于开盘，绿色表示收盘低于开盘；下方柱形为成交量。</div>
    </section>
    <aside>
      <div>
        <h2>交易活跃度</h2>
        <div class="scroll" id="turnover"></div>
      </div>
      <div>
        <h2>财务摘要</h2>
        <div class="scroll" id="finance"></div>
      </div>
      <div>
        <h2>数据文件</h2>
        <div class="note" id="files"></div>
      </div>
    </aside>
  </main>
  <script>
    const panel = {data_json};
    const daily = panel.daily;
    const basics = new Map(panel.daily_basic.map(row => [row.trade_date, row]));

    function n(v) {{
      const x = Number(v);
      return Number.isFinite(x) ? x : null;
    }}

    function money(v) {{
      const x = n(v);
      if (x === null) return "-";
      if (Math.abs(x) >= 100000000) return (x / 100000000).toFixed(2) + "亿";
      if (Math.abs(x) >= 10000) return (x / 10000).toFixed(2) + "万";
      return x.toFixed(2);
    }}

    function pct(v) {{
      const x = n(v);
      return x === null ? "-" : x.toFixed(2) + "%";
    }}

    function dateLabel(raw) {{
      return raw.slice(0, 4) + "-" + raw.slice(4, 6) + "-" + raw.slice(6, 8);
    }}

    function drawChart() {{
      const canvas = document.getElementById("priceChart");
      const ctx = canvas.getContext("2d");
      const dpr = window.devicePixelRatio || 1;
      const cssWidth = canvas.clientWidth;
      const cssHeight = canvas.clientHeight;
      canvas.width = Math.floor(cssWidth * dpr);
      canvas.height = Math.floor(cssHeight * dpr);
      ctx.scale(dpr, dpr);

      const width = cssWidth;
      const height = cssHeight;
      const pad = {{ left: 58, right: 18, top: 20, bottom: 34 }};
      const volTop = Math.floor(height * 0.73);
      const candleBottom = volTop - 18;
      const plotW = width - pad.left - pad.right;
      const candleH = candleBottom - pad.top;
      const volH = height - volTop - pad.bottom;

      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, width, height);

      const highs = daily.map(r => n(r.high)).filter(v => v !== null);
      const lows = daily.map(r => n(r.low)).filter(v => v !== null);
      const volumes = daily.map(r => n(r.vol)).filter(v => v !== null);
      const maxPrice = Math.max(...highs) * 1.02;
      const minPrice = Math.min(...lows) * 0.98;
      const maxVol = Math.max(...volumes) * 1.08;
      const xStep = plotW / Math.max(daily.length, 1);
      const candleW = Math.max(2, Math.min(9, xStep * 0.62));
      const yPrice = v => pad.top + (maxPrice - v) / (maxPrice - minPrice) * candleH;
      const yVol = v => volTop + (maxVol - v) / maxVol * volH;

      ctx.strokeStyle = "#e1e7f0";
      ctx.lineWidth = 1;
      ctx.fillStyle = "#61708a";
      ctx.font = "12px Microsoft YaHei, Arial";
      for (let i = 0; i <= 5; i++) {{
        const y = pad.top + i / 5 * candleH;
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(width - pad.right, y);
        ctx.stroke();
        const value = maxPrice - i / 5 * (maxPrice - minPrice);
        ctx.fillText(value.toFixed(2), 8, y + 4);
      }}
      ctx.beginPath();
      ctx.moveTo(pad.left, volTop);
      ctx.lineTo(width - pad.right, volTop);
      ctx.stroke();

      daily.forEach((row, i) => {{
        const open = n(row.open);
        const close = n(row.close);
        const high = n(row.high);
        const low = n(row.low);
        const vol = n(row.vol);
        if ([open, close, high, low, vol].some(v => v === null)) return;
        const x = pad.left + i * xStep + xStep / 2;
        const up = close >= open;
        const color = up ? "#d94b3d" : "#15956f";
        ctx.strokeStyle = color;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(x, yPrice(high));
        ctx.lineTo(x, yPrice(low));
        ctx.stroke();
        const top = yPrice(Math.max(open, close));
        const bottom = yPrice(Math.min(open, close));
        ctx.fillRect(x - candleW / 2, top, candleW, Math.max(1, bottom - top));
        const vy = yVol(vol);
        ctx.globalAlpha = 0.32;
        ctx.fillRect(x - candleW / 2, vy, candleW, volTop + volH - vy);
        ctx.globalAlpha = 1;
      }});

      const marks = 6;
      ctx.fillStyle = "#61708a";
      for (let i = 0; i < marks; i++) {{
        const index = Math.floor(i * (daily.length - 1) / (marks - 1));
        const row = daily[index];
        const x = pad.left + index * xStep;
        ctx.fillText(dateLabel(row.trade_date).slice(5), x, height - 10);
      }}
      ctx.fillText("成交量", 8, volTop + 18);
    }}

    function renderStats() {{
      const first = daily[0];
      const last = daily[daily.length - 1];
      const lastBasic = basics.get(last.trade_date) || {{}};
      const change = ((n(last.close) - n(first.close)) / n(first.close)) * 100;
      const maxClose = Math.max(...daily.map(r => n(r.close)).filter(v => v !== null));
      const minClose = Math.min(...daily.map(r => n(r.close)).filter(v => v !== null));
      const items = [
        ["最新收盘", n(last.close)?.toFixed(2) ?? "-"],
        ["区间涨跌幅", Number.isFinite(change) ? change.toFixed(2) + "%" : "-"],
        ["区间最高/最低收盘", maxClose.toFixed(2) + " / " + minClose.toFixed(2)],
        ["最新PE(TTM)/PB", (n(lastBasic.pe_ttm)?.toFixed(2) ?? "-") + " / " + (n(lastBasic.pb)?.toFixed(2) ?? "-")],
      ];
      document.getElementById("stats").innerHTML = items.map(([label, value]) =>
        `<div class="stat"><div class="label">${{label}}</div><div class="value">${{value}}</div></div>`
      ).join("");
    }}

    function renderTurnover() {{
      const rows = daily
        .map(r => ({{...r, basic: basics.get(r.trade_date) || {{}}}}))
        .sort((a, b) => (n(b.amount) || 0) - (n(a.amount) || 0))
        .slice(0, 10);
      document.getElementById("turnover").innerHTML = `<table>
        <thead><tr><th>日期</th><th>涨跌幅</th><th>成交额</th><th>换手率</th></tr></thead>
        <tbody>${{rows.map(r => `<tr>
          <td class="left">${{dateLabel(r.trade_date)}}</td>
          <td class="${{n(r.pct_chg) >= 0 ? "positive" : "negative"}}">${{pct(r.pct_chg)}}</td>
          <td>${{money((n(r.amount) || 0) * 1000)}}</td>
          <td>${{pct(r.basic.turnover_rate)}}</td>
        </tr>`).join("")}}</tbody>
      </table>`;
    }}

    function renderFinance() {{
      const rows = panel.finance.indicator;
      const dividends = panel.finance.dividend || [];
      if (!rows.length && dividends.length) {{
        const note = panel.api_errors.length
          ? `<div class="note">利润表、资产负债表、现金流和财务指标接口当前无权限；下表展示可获取的分红记录。</div>`
          : "";
        document.getElementById("finance").innerHTML = `${{note}}<table>
          <thead><tr><th>报告期</th><th>进度</th><th>现金分红</th><th>除权日</th><th>派息日</th></tr></thead>
          <tbody>${{dividends.map(r => `<tr>
            <td class="left">${{dateLabel(r.end_date)}}</td>
            <td>${{r.div_proc || "-"}}</td>
            <td>${{n(r.cash_div)?.toFixed(3) ?? "-"}}</td>
            <td>${{r.ex_date ? dateLabel(r.ex_date) : "-"}}</td>
            <td>${{r.pay_date ? dateLabel(r.pay_date) : "-"}}</td>
          </tr>`).join("")}}</tbody>
        </table>`;
        return;
      }}
      if (!rows.length) {{
        const detail = panel.api_errors.length ? panel.api_errors.join("<br>") : "未查询到财务指标记录。";
        document.getElementById("finance").innerHTML = `<div class='note'>${{detail}}</div>`;
        return;
      }}
      document.getElementById("finance").innerHTML = `<table>
        <thead><tr><th>报告期</th><th>EPS</th><th>ROE</th><th>毛利率</th><th>负债率</th></tr></thead>
        <tbody>${{rows.map(r => `<tr>
          <td class="left">${{dateLabel(r.end_date)}}</td>
          <td>${{n(r.eps)?.toFixed(3) ?? "-"}}</td>
          <td>${{pct(r.roe)}}</td>
          <td>${{pct(r.grossprofit_margin)}}</td>
          <td>${{pct(r.debt_to_assets)}}</td>
        </tr>`).join("")}}</tbody>
      </table>`;
    }}

    function renderMeta() {{
      document.getElementById("meta").textContent =
        `数据源：Tushare Pro；区间：${{dateLabel(panel.meta.start_date)}} 至 ${{dateLabel(panel.meta.end_date)}}；生成时间：${{panel.meta.generated_at}}`;
      document.getElementById("files").innerHTML = panel.meta.files.map(f => `<div>${{f}}</div>`).join("");
    }}

    renderMeta();
    drawChart();
    renderStats();
    renderTurnover();
    renderFinance();
    window.addEventListener("resize", drawChart);
  </script>
</body>
</html>
"""


def build_html_v2(panel: dict[str, Any]) -> str:
    data_json = json.dumps(panel, ensure_ascii=False)
    escaped_title = html.escape(f"{COMPANY_NAME}（{TS_CODE}）研究面板")
    template = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f6f9;
      --panel: #ffffff;
      --panel-soft: #f9fbff;
      --ink: #172033;
      --muted: #69758a;
      --line: #dfe6ef;
      --red: #d84a3a;
      --green: #128764;
      --blue: #2563eb;
      --amber: #b7791f;
      --shadow: 0 12px 30px rgba(23, 32, 51, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      color: var(--ink);
      background: var(--bg);
    }
    header {
      padding: 22px 24px 16px;
      background: linear-gradient(180deg, #ffffff 0%, #f7faff 100%);
      border-bottom: 1px solid var(--line);
    }
    .header-inner {
      max-width: 1500px;
      margin: 0 auto;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 16px;
      align-items: end;
    }
    h1 {
      margin: 0;
      font-size: 26px;
      letter-spacing: 0;
    }
    .subtitle {
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
    }
    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }
    .chip {
      padding: 7px 10px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #fff;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }
    main {
      max-width: 1500px;
      margin: 0 auto;
      padding: 14px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 390px;
      gap: 14px;
    }
    .kpis {
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
    }
    .card, .metric {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .metric {
      min-height: 92px;
      padding: 12px;
    }
    .metric .label, .label {
      color: var(--muted);
      font-size: 12px;
    }
    .metric .value {
      margin-top: 8px;
      font-size: 22px;
      font-weight: 750;
      letter-spacing: 0;
    }
    .metric .hint {
      margin-top: 6px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .workspace {
      min-width: 0;
      display: grid;
      gap: 14px;
    }
    .side {
      display: grid;
      gap: 14px;
      align-content: start;
    }
    .card {
      padding: 14px;
    }
    .card-title {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: baseline;
      margin-bottom: 10px;
    }
    h2 {
      margin: 0;
      font-size: 16px;
      letter-spacing: 0;
    }
    .canvas-shell {
      height: 610px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
    }
    canvas {
      display: block;
      width: 100%;
      height: 100%;
    }
    .mini-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }
    .mini {
      padding: 10px;
      background: var(--panel-soft);
      border: 1px solid var(--line);
      border-radius: 6px;
      min-height: 72px;
    }
    .mini strong {
      display: block;
      margin-top: 7px;
      font-size: 16px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    th, td {
      padding: 8px 4px;
      border-bottom: 1px solid var(--line);
      text-align: right;
      vertical-align: top;
    }
    th:first-child, td:first-child, .left { text-align: left; }
    .scroll { max-height: 360px; overflow: auto; }
    .positive { color: var(--red); }
    .negative { color: var(--green); }
    .note {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.7;
    }
    .timeline {
      display: grid;
      gap: 8px;
    }
    .event {
      display: grid;
      grid-template-columns: 82px minmax(0, 1fr);
      gap: 8px;
      padding: 9px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel-soft);
      font-size: 12px;
    }
    .links {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }
    .links a {
      display: block;
      padding: 9px 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--blue);
      text-decoration: none;
      background: #fff;
      font-size: 12px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    footer {
      max-width: 1500px;
      margin: 0 auto;
      padding: 0 14px 24px;
    }
    @media (max-width: 1120px) {
      main { grid-template-columns: 1fr; }
      .kpis { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .header-inner { grid-template-columns: 1fr; }
      .chips { justify-content: flex-start; }
    }
    @media (max-width: 720px) {
      header { padding: 18px 14px 12px; }
      main { padding: 10px; }
      .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .mini-grid { grid-template-columns: 1fr; }
      .canvas-shell { height: 500px; }
      .links { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <div>
        <h1>金安国纪研究面板</h1>
        <div class="subtitle" id="meta"></div>
      </div>
      <div class="chips">
        <span class="chip">Tushare Pro</span>
        <span class="chip">近一年日线</span>
        <span class="chip">静态 GitHub Pages</span>
      </div>
    </div>
  </header>
  <main>
    <section class="kpis" id="kpis"></section>
    <section class="workspace">
      <div class="card">
        <div class="card-title">
          <h2>K线、均线与成交量</h2>
          <span class="note">MA5 / MA20；红涨绿跌</span>
        </div>
        <div class="canvas-shell">
          <canvas id="priceChart" aria-label="金安国纪K线与成交量"></canvas>
        </div>
      </div>
      <div class="card">
        <div class="card-title">
          <h2>区间统计</h2>
          <span class="note">由本地日线数据计算</span>
        </div>
        <div class="mini-grid" id="rangeStats"></div>
      </div>
    </section>
    <aside class="side">
      <div class="card">
        <div class="card-title">
          <h2>交易活跃度 Top 10</h2>
          <span class="note">按成交额排序</span>
        </div>
        <div class="scroll" id="turnover"></div>
      </div>
      <div class="card">
        <div class="card-title">
          <h2>分红与财务可得性</h2>
          <span class="note">受账号权限影响</span>
        </div>
        <div id="finance"></div>
      </div>
      <div class="card">
        <div class="card-title">
          <h2>数据下载</h2>
          <span class="note">CSV / JSON / HTML</span>
        </div>
        <div class="links" id="files"></div>
      </div>
    </aside>
  </main>
  <footer>
    <div class="card note" id="dataNotes"></div>
  </footer>
  <script>
    const panel = __DATA__;
    const daily = panel.daily || [];
    const basics = new Map((panel.daily_basic || []).map(row => [row.trade_date, row]));

    function n(v) {
      const x = Number(v);
      return Number.isFinite(x) ? x : null;
    }
    function fmtNum(v, digits = 2) {
      const x = n(v);
      return x === null ? "-" : x.toFixed(digits);
    }
    function money(v) {
      const x = n(v);
      if (x === null) return "-";
      if (Math.abs(x) >= 100000000) return (x / 100000000).toFixed(2) + "亿";
      if (Math.abs(x) >= 10000) return (x / 10000).toFixed(2) + "万";
      return x.toFixed(2);
    }
    function pct(v) {
      const x = n(v);
      return x === null ? "-" : x.toFixed(2) + "%";
    }
    function dateLabel(raw) {
      if (!raw) return "-";
      return raw.slice(0, 4) + "-" + raw.slice(4, 6) + "-" + raw.slice(6, 8);
    }
    function cls(v) {
      const x = n(v);
      return x === null ? "" : x >= 0 ? "positive" : "negative";
    }
    function ma(values, windowSize) {
      return values.map((_, i) => {
        if (i + 1 < windowSize) return null;
        let total = 0;
        for (let j = i - windowSize + 1; j <= i; j++) total += values[j];
        return total / windowSize;
      });
    }
    function calc() {
      const first = daily[0] || {};
      const last = daily[daily.length - 1] || {};
      const closes = daily.map(r => n(r.close)).filter(v => v !== null);
      const highs = daily.map(r => n(r.high)).filter(v => v !== null);
      const lows = daily.map(r => n(r.low)).filter(v => v !== null);
      const amounts = daily.map(r => n(r.amount) || 0);
      const volumes = daily.map(r => n(r.vol) || 0);
      const ret = n(first.close) ? ((n(last.close) - n(first.close)) / n(first.close)) * 100 : null;
      const avgAmount = amounts.reduce((a, b) => a + b, 0) / Math.max(amounts.length, 1) * 1000;
      const avgVol = volumes.reduce((a, b) => a + b, 0) / Math.max(volumes.length, 1);
      const maxClose = Math.max(...closes);
      const minClose = Math.min(...closes);
      const maxHigh = Math.max(...highs);
      const minLow = Math.min(...lows);
      return { first, last, ret, avgAmount, avgVol, maxClose, minClose, maxHigh, minLow };
    }

    function renderMeta() {
      document.getElementById("meta").textContent =
        `${panel.meta.company} ${panel.meta.ts_code} · ${dateLabel(panel.meta.start_date)} 至 ${dateLabel(panel.meta.end_date)} · 生成于 ${panel.meta.generated_at}`;
    }

    function renderKpis() {
      const s = calc();
      const dividends = panel.finance?.dividend || [];
      const latestDividend = dividends[dividends.length - 1];
      const lastBasic = basics.get(s.last.trade_date) || {};
      const items = [
        ["最新收盘", fmtNum(s.last.close), dateLabel(s.last.trade_date), cls(s.last.pct_chg)],
        ["当日涨跌幅", pct(s.last.pct_chg), `涨跌额 ${fmtNum(s.last.change)}`, cls(s.last.pct_chg)],
        ["区间涨跌幅", pct(s.ret), `${dateLabel(s.first.trade_date)} 起`, cls(s.ret)],
        ["区间高低", `${fmtNum(s.maxHigh)} / ${fmtNum(s.minLow)}`, "最高价 / 最低价", ""],
        ["平均成交额", money(s.avgAmount), "日均成交额", ""],
        ["PE(TTM) / PB", `${fmtNum(lastBasic.pe_ttm)} / ${fmtNum(lastBasic.pb)}`, "受 daily_basic 权限影响", ""],
      ];
      document.getElementById("kpis").innerHTML = items.map(([label, value, hint, klass]) =>
        `<div class="metric"><div class="label">${label}</div><div class="value ${klass}">${value}</div><div class="hint">${hint}</div></div>`
      ).join("");
    }

    function drawChart() {
      const canvas = document.getElementById("priceChart");
      const ctx = canvas.getContext("2d");
      const dpr = window.devicePixelRatio || 1;
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      canvas.width = Math.max(1, Math.floor(width * dpr));
      canvas.height = Math.max(1, Math.floor(height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, width, height);
      if (!daily.length) return;

      const pad = { left: 58, right: 22, top: 22, bottom: 38 };
      const volTop = Math.floor(height * 0.74);
      const candleBottom = volTop - 20;
      const plotW = width - pad.left - pad.right;
      const candleH = candleBottom - pad.top;
      const volH = height - volTop - pad.bottom;
      const highs = daily.map(r => n(r.high)).filter(v => v !== null);
      const lows = daily.map(r => n(r.low)).filter(v => v !== null);
      const vols = daily.map(r => n(r.vol)).filter(v => v !== null);
      const closes = daily.map(r => n(r.close) || 0);
      const ma5 = ma(closes, 5);
      const ma20 = ma(closes, 20);
      const maxPrice = Math.max(...highs, ...ma5.filter(Boolean), ...ma20.filter(Boolean)) * 1.02;
      const minPrice = Math.min(...lows, ...ma5.filter(Boolean), ...ma20.filter(Boolean)) * 0.98;
      const maxVol = Math.max(...vols) * 1.08;
      const xStep = plotW / Math.max(daily.length, 1);
      const candleW = Math.max(2, Math.min(8, xStep * 0.62));
      const xAt = i => pad.left + i * xStep + xStep / 2;
      const yPrice = v => pad.top + (maxPrice - v) / (maxPrice - minPrice) * candleH;
      const yVol = v => volTop + (maxVol - v) / maxVol * volH;

      ctx.strokeStyle = "#dfe6ef";
      ctx.lineWidth = 1;
      ctx.fillStyle = "#69758a";
      ctx.font = "12px Microsoft YaHei, Arial";
      for (let i = 0; i <= 5; i++) {
        const y = pad.top + i / 5 * candleH;
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(width - pad.right, y);
        ctx.stroke();
        const value = maxPrice - i / 5 * (maxPrice - minPrice);
        ctx.fillText(value.toFixed(2), 8, y + 4);
      }
      ctx.beginPath();
      ctx.moveTo(pad.left, volTop);
      ctx.lineTo(width - pad.right, volTop);
      ctx.stroke();

      daily.forEach((row, i) => {
        const open = n(row.open), close = n(row.close), high = n(row.high), low = n(row.low), vol = n(row.vol);
        if ([open, close, high, low, vol].some(v => v === null)) return;
        const x = xAt(i);
        const up = close >= open;
        const color = up ? "#d84a3a" : "#128764";
        ctx.strokeStyle = color;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(x, yPrice(high));
        ctx.lineTo(x, yPrice(low));
        ctx.stroke();
        const top = yPrice(Math.max(open, close));
        const bottom = yPrice(Math.min(open, close));
        ctx.fillRect(x - candleW / 2, top, candleW, Math.max(1, bottom - top));
        ctx.globalAlpha = 0.28;
        ctx.fillRect(x - candleW / 2, yVol(vol), candleW, volTop + volH - yVol(vol));
        ctx.globalAlpha = 1;
      });

      function line(values, color, labelY) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        let started = false;
        values.forEach((v, i) => {
          if (v == null) return;
          const x = xAt(i), y = yPrice(v);
          if (!started) { ctx.moveTo(x, y); started = true; }
          else ctx.lineTo(x, y);
        });
        ctx.stroke();
      }
      line(ma5, "#2563eb");
      line(ma20, "#b7791f");
      ctx.fillStyle = "#2563eb";
      ctx.fillText("MA5", width - 86, 20);
      ctx.fillStyle = "#b7791f";
      ctx.fillText("MA20", width - 46, 20);
      ctx.fillStyle = "#69758a";
      ctx.fillText("成交量", 8, volTop + 18);
      for (let i = 0; i < 6; i++) {
        const idx = Math.floor(i * (daily.length - 1) / 5);
        ctx.fillText(dateLabel(daily[idx].trade_date).slice(5), xAt(idx) - 16, height - 12);
      }
    }

    function renderRangeStats() {
      const s = calc();
      const upDays = daily.filter(r => n(r.pct_chg) > 0).length;
      const downDays = daily.filter(r => n(r.pct_chg) < 0).length;
      const maxDay = [...daily].sort((a, b) => (n(b.pct_chg) || 0) - (n(a.pct_chg) || 0))[0] || {};
      const minDay = [...daily].sort((a, b) => (n(a.pct_chg) || 0) - (n(b.pct_chg) || 0))[0] || {};
      const items = [
        ["交易日数量", `${daily.length} 天`, "覆盖 Tushare 日线记录"],
        ["上涨 / 下跌天数", `${upDays} / ${downDays}`, "按日涨跌幅统计"],
        ["最大单日上涨", `${dateLabel(maxDay.trade_date)} · ${pct(maxDay.pct_chg)}`, `收盘 ${fmtNum(maxDay.close)}`],
        ["最大单日下跌", `${dateLabel(minDay.trade_date)} · ${pct(minDay.pct_chg)}`, `收盘 ${fmtNum(minDay.close)}`],
        ["最高 / 最低价", `${fmtNum(s.maxHigh)} / ${fmtNum(s.minLow)}`, "区间 high / low"],
        ["日均成交量", `${fmtNum(s.avgVol, 0)} 手`, "Tushare vol 字段"],
      ];
      document.getElementById("rangeStats").innerHTML = items.map(([label, value, hint]) =>
        `<div class="mini"><div class="label">${label}</div><strong>${value}</strong><div class="note">${hint}</div></div>`
      ).join("");
    }

    function renderTurnover() {
      const rows = [...daily].sort((a, b) => (n(b.amount) || 0) - (n(a.amount) || 0)).slice(0, 10);
      document.getElementById("turnover").innerHTML = `<table>
        <thead><tr><th>日期</th><th>涨跌幅</th><th>成交额</th><th>收盘</th></tr></thead>
        <tbody>${rows.map(r => `<tr>
          <td class="left">${dateLabel(r.trade_date)}</td>
          <td class="${cls(r.pct_chg)}">${pct(r.pct_chg)}</td>
          <td>${money((n(r.amount) || 0) * 1000)}</td>
          <td>${fmtNum(r.close)}</td>
        </tr>`).join("")}</tbody>
      </table>`;
    }

    function renderFinance() {
      const dividends = panel.finance?.dividend || [];
      const latest = dividends.slice(-6).reverse();
      const accessNote = panel.meta?.data_notes?.financial_statement_access || "";
      document.getElementById("finance").innerHTML = `
        <div class="note">${accessNote}</div>
        <div class="timeline" style="margin-top:10px;">
          ${latest.map(r => `<div class="event">
            <div>${dateLabel(r.end_date)}</div>
            <div><strong>${r.div_proc || "-"}</strong><br>现金分红 ${fmtNum(r.cash_div, 3)}；除权日 ${r.ex_date ? dateLabel(r.ex_date) : "-"}</div>
          </div>`).join("")}
        </div>`;
    }

    function renderFiles() {
      const files = panel.meta.files || [];
      document.getElementById("files").innerHTML = files.map(f => `<a href="${f}" download>${f}</a>`).join("");
      const rows = panel.meta.row_counts || {};
      document.getElementById("dataNotes").innerHTML =
        `数据行数：日线 ${rows.daily || 0}，每日指标 ${rows.daily_basic || 0}，分红 ${rows.dividend || 0}。` +
        `财务报表接口受当前 Tushare token 权限限制；面板保留空 CSV 和错误摘要，便于后续升级权限后重新生成。`;
    }

    renderMeta();
    renderKpis();
    drawChart();
    renderRangeStats();
    renderTurnover();
    renderFinance();
    renderFiles();
    window.addEventListener("resize", drawChart);
  </script>
</body>
</html>
"""
    return template.replace("__TITLE__", escaped_title).replace("__DATA__", data_json)


def main() -> None:
    token = read_tushare_token()
    start = ymd(START_DATE)
    end = ymd(END_DATE)
    api_errors: list[str] = []

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    stock_basic = [
        {
            "ts_code": TS_CODE,
            "symbol": "002636",
            "name": COMPANY_NAME,
            "market": "主板",
            "note": "静态写入，避免触发 Tushare stock_basic 每小时频率限制。",
        }
    ]
    daily = sort_by_date(
        call_tushare(
            token,
            "daily",
            {"ts_code": TS_CODE, "start_date": start, "end_date": end},
            ["ts_code", "trade_date", "open", "high", "low", "close", "pre_close", "change", "pct_chg", "vol", "amount"],
        ),
        "trade_date",
    )
    daily_basic = sort_by_date(
        optional_call(
            token,
            "daily_basic",
            api_errors,
            {"ts_code": TS_CODE, "start_date": start, "end_date": end},
            ["ts_code", "trade_date", "close", "turnover_rate", "volume_ratio", "pe", "pe_ttm", "pb", "ps_ttm", "total_mv", "circ_mv"],
        ),
        "trade_date",
    )

    finance_start = ymd(END_DATE - dt.timedelta(days=365 * 3))
    income = latest_by_period(
        optional_call(
            token,
            "income",
            api_errors,
            {"ts_code": TS_CODE, "start_date": finance_start, "end_date": end},
            ["ts_code", "ann_date", "f_ann_date", "end_date", "report_type", "basic_eps", "total_revenue", "revenue", "operate_profit", "total_profit", "n_income", "n_income_attr_p", "rd_exp"],
        )
    )
    balance = latest_by_period(
        optional_call(
            token,
            "balancesheet",
            api_errors,
            {"ts_code": TS_CODE, "start_date": finance_start, "end_date": end},
            ["ts_code", "ann_date", "end_date", "report_type", "total_assets", "total_liab", "total_hldr_eqy_inc_min_int", "money_cap", "accounts_receiv", "inventories"],
        )
    )
    cashflow = latest_by_period(
        optional_call(
            token,
            "cashflow",
            api_errors,
            {"ts_code": TS_CODE, "start_date": finance_start, "end_date": end},
            ["ts_code", "ann_date", "f_ann_date", "end_date", "report_type", "net_profit", "n_cashflow_act", "free_cashflow", "c_cash_equ_end_period"],
        )
    )
    indicator = latest_by_period(
        optional_call(
            token,
            "fina_indicator",
            api_errors,
            {"ts_code": TS_CODE, "start_date": finance_start, "end_date": end},
            ["ts_code", "ann_date", "end_date", "eps", "dt_eps", "roe", "roa", "grossprofit_margin", "netprofit_margin", "debt_to_assets", "current_ratio", "quick_ratio", "ocfps"],
        )
    )
    dividend = sort_by_date(
        optional_call(
            token,
            "dividend",
            api_errors,
            {"ts_code": TS_CODE},
            ["ts_code", "end_date", "ann_date", "div_proc", "stk_div", "cash_div", "cash_div_tax", "record_date", "ex_date", "pay_date"],
        ),
        "end_date",
    )[-12:]
    dividend_source = "Tushare dividend API"
    if not dividend:
        dividend = FALLBACK_DIVIDEND_ROWS
        dividend_source = "Tushare MCP snapshot captured during setup; direct dividend API was rate-limited"

    files = {
        "stock_basic": "stock_basic.csv",
        "daily": "daily_prices.csv",
        "daily_basic": "daily_basic.csv",
        "income": "income.csv",
        "balancesheet": "balancesheet.csv",
        "cashflow": "cashflow.csv",
        "fina_indicator": "fina_indicator.csv",
        "dividend": "dividend.csv",
    }
    write_csv(OUT_DIR / files["stock_basic"], stock_basic)
    write_csv(OUT_DIR / files["daily"], daily)
    write_csv(OUT_DIR / files["daily_basic"], daily_basic)
    write_csv(OUT_DIR / files["income"], income)
    write_csv(OUT_DIR / files["balancesheet"], balance)
    write_csv(OUT_DIR / files["cashflow"], cashflow)
    write_csv(OUT_DIR / files["fina_indicator"], indicator)
    write_csv(OUT_DIR / files["dividend"], dividend)

    panel = {
        "meta": {
            "company": COMPANY_NAME,
            "ts_code": TS_CODE,
            "start_date": start,
            "end_date": end,
            "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "row_counts": {
                "daily": len(daily),
                "daily_basic": len(daily_basic),
                "income": len(income),
                "balancesheet": len(balance),
                "cashflow": len(cashflow),
                "fina_indicator": len(indicator),
                "dividend": len(dividend),
                "api_errors": len(api_errors),
            },
            "data_notes": {
                "dividend_source": dividend_source,
                "financial_statement_access": "income, balancesheet, cashflow and fina_indicator require additional Tushare permissions for this token.",
            },
            "files": list(files.values()) + ["panel_data.json", "index.html"],
        },
        "stock_basic": stock_basic,
        "daily": daily,
        "daily_basic": daily_basic,
        "finance": {
            "income": income,
            "balancesheet": balance,
            "cashflow": cashflow,
            "indicator": indicator,
            "dividend": dividend,
        },
        "api_errors": api_errors,
    }
    write_json(OUT_DIR / "panel_data.json", panel)
    (OUT_DIR / "index.html").write_text(build_html_v2(panel), encoding="utf-8")

    print(json.dumps(panel["meta"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
