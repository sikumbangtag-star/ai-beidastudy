from __future__ import annotations

import csv
import json
import re
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TASK2 = ROOT / "task2"
DATA_DIR = TASK2 / "data" / "stocks"
OUTPUT_JSON = TASK2 / "outputs" / "multi_stock_panel_data.json"
OUTPUT_HTML = TASK2 / "design" / "multi_stock_indicator_panel.html"
TUSHARE_URL = "https://api.tushare.pro"

STOCKS = [
    {"ts_code": "002636.SZ", "name": "金安国纪", "slug": "jinan_guoji"},
    {"ts_code": "300308.SZ", "name": "中际旭创", "slug": "zhongji_xuchuang"},
    {"ts_code": "001309.SZ", "name": "德明利", "slug": "demingli"},
    {"ts_code": "300408.SZ", "name": "三环集团", "slug": "sanhuan_jituan"},
    {"ts_code": "603667.SH", "name": "五洲新春", "slug": "wuzhou_xinchun"},
]

DAILY_FIELDS = [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "change",
    "pct_chg",
    "vol",
    "amount",
]


def project_today() -> date:
    return date(2026, 7, 4)


def two_year_window(today: date | None = None) -> tuple[str, str]:
    today = today or project_today()
    start = today - timedelta(days=365 * 2)
    return start.strftime("%Y%m%d"), today.strftime("%Y%m%d")


def read_tushare_token() -> str:
    config = Path.home() / ".codex" / "config.toml"
    if not config.exists():
        raise FileNotFoundError("未找到 Codex Tushare MCP 配置文件")
    text = config.read_text(encoding="utf-8")
    match = re.search(r"api\.tushare\.pro/mcp/\?token=([A-Za-z0-9]+)", text)
    if not match:
        raise ValueError("未在 Codex 配置中找到 Tushare token")
    return match.group(1)


def tushare_post(api_name: str, params: dict[str, Any], token: str) -> list[dict[str, Any]]:
    body = json.dumps(
        {
            "api_name": api_name,
            "token": token,
            "params": params,
            "fields": ",".join(DAILY_FIELDS),
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        TUSHARE_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if payload.get("code") != 0:
        raise RuntimeError(f"Tushare daily failed: {payload.get('msg')}")

    fields = payload["data"]["fields"]
    rows = payload["data"]["items"]
    return [dict(zip(fields, row)) for row in rows]


def normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        item = {}
        for field in DAILY_FIELDS:
            value = row.get(field)
            if field in {"open", "high", "low", "close", "pre_close", "change", "pct_chg", "vol", "amount"}:
                value = None if value in ("", None) else float(value)
            item[field] = value
        normalized.append(item)
    return sorted(normalized, key=lambda item: item["trade_date"])


def write_stock_csv(stock: dict[str, str], rows: list[dict[str, Any]]) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{stock['slug']}_{stock['ts_code'].replace('.', '_')}_daily_2y.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DAILY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def fetch_stock_data(token: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    stocks_payload = []
    for stock in STOCKS:
        rows = normalize_rows(
            tushare_post(
                "daily",
                {"ts_code": stock["ts_code"], "start_date": start_date, "end_date": end_date},
                token,
            )
        )
        csv_path = write_stock_csv(stock, rows)
        stocks_payload.append(
            {
                "ts_code": stock["ts_code"],
                "name": stock["name"],
                "slug": stock["slug"],
                "csv": str(csv_path.relative_to(ROOT)).replace("\\", "/"),
                "rows": rows,
            }
        )
    return stocks_payload


def build_payload(stocks_payload: list[dict[str, Any]], start_date: str, end_date: str) -> dict[str, Any]:
    return {
        "generated_at": date.today().isoformat(),
        "start_date": start_date,
        "end_date": end_date,
        "stocks": stocks_payload,
    }


def render_multi_stock_html(payload: dict[str, Any]) -> str:
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    start_date = payload.get("start_date", "")
    end_date = payload.get("end_date", "")
    options = "\n".join(
        f'<option value="{stock["ts_code"]}">{stock["name"]} {stock["ts_code"]}</option>'
        for stock in payload["stocks"]
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>多股票技术指标交互分析面板</title>
  <style>
    :root {{
      --bg:#f4f6f8; --panel:#fff; --line:#d9dee7; --text:#1f2937; --muted:#6b7280;
      --red:#d93f3f; --green:#1f9d72; --blue:#2563eb; --orange:#d97706; --purple:#7c3aed; --teal:#0f9f8f;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font-family:"Microsoft YaHei",Arial,sans-serif; font-size:14px; letter-spacing:0; }}
    .topbar {{ min-height:62px; display:flex; align-items:center; justify-content:space-between; gap:16px; padding:10px 18px; background:#111827; color:#fff; }}
    .brand strong {{ display:block; font-size:18px; }}
    .brand span {{ color:#cbd5e1; font-size:12px; }}
    .toolbar {{ display:flex; align-items:center; justify-content:flex-end; flex-wrap:wrap; gap:10px; }}
    select,input,button {{ height:34px; border:1px solid var(--line); border-radius:6px; background:#fff; color:var(--text); padding:0 10px; font:inherit; }}
    .topbar select,.topbar input {{ min-width:150px; background:#1f2937; border-color:#374151; color:#f9fafb; }}
    button {{ font-weight:700; }}
    .primary {{ background:var(--blue); border-color:var(--blue); color:#fff; }}
    .page {{ width:min(1500px,100%); margin:0 auto; padding:14px; display:flex; flex-direction:column; gap:14px; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; }}
    .overview {{ display:grid; grid-template-columns:1.35fr repeat(5,minmax(0,1fr)); gap:10px; }}
    .data-card,.kpi {{ min-height:86px; padding:12px; }}
    .data-card {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; align-items:end; }}
    label,.muted {{ color:var(--muted); font-size:12px; }}
    .value,.kpi strong {{ display:block; min-height:25px; font-size:20px; line-height:1.15; font-weight:800; color:#111827; }}
    .kpi small,.mini small {{ color:var(--muted); font-size:12px; }}
    .module {{ display:grid; grid-template-columns:320px minmax(0,1fr); overflow:hidden; min-height:260px; }}
    .left {{ padding:16px; border-right:1px solid var(--line); background:#fbfcfe; }}
    .right {{ min-width:0; padding:14px; }}
    .title {{ display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:12px; }}
    .title h2,.chart-head h3 {{ margin:0; color:#111827; }}
    .title h2 {{ font-size:17px; }}
    .title span {{ color:var(--muted); font-size:12px; white-space:nowrap; }}
    .param {{ display:grid; grid-template-columns:1fr 88px; align-items:center; gap:10px; margin:9px 0; }}
    .param input {{ width:88px; text-align:right; }}
    .note {{ margin:14px 0 0; padding-top:12px; border-top:1px solid #e9edf4; color:#4b5563; line-height:1.65; font-size:13px; }}
    .chart-head {{ display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:9px; }}
    .legend {{ display:flex; gap:12px; color:var(--muted); font-size:12px; flex-wrap:wrap; justify-content:flex-end; }}
    .dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:5px; vertical-align:1px; }}
    .chart {{ height:220px; border:1px solid #e5e7eb; border-radius:6px; background:#fff; overflow:hidden; }}
    .chart.large {{ height:310px; }}
    svg {{ width:100%; height:100%; display:block; }}
    .bottom {{ display:grid; grid-template-columns:minmax(0,1fr) 360px; gap:14px; }}
    .table-panel,.summary-panel {{ padding:14px; }}
    .section-title {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; font-weight:800; }}
    table {{ width:100%; border-collapse:collapse; font-size:12px; }}
    th,td {{ padding:8px 7px; border-bottom:1px solid #edf0f5; text-align:right; white-space:nowrap; }}
    th:first-child,td:first-child {{ text-align:left; }}
    th {{ background:#f8fafc; color:#4b5563; font-weight:800; }}
    .summary-list {{ display:flex; flex-direction:column; gap:10px; color:#4b5563; line-height:1.6; }}
    .warn {{ color:#7c2d12; background:#fff7ed; border-color:#fed7aa; }}
    @media (max-width:1120px) {{ .overview {{ grid-template-columns:repeat(3,minmax(0,1fr)); }} .data-card {{ grid-column:1/-1; }} .module {{ grid-template-columns:280px minmax(0,1fr); }} }}
    @media (max-width:760px) {{ .topbar {{ align-items:flex-start; flex-direction:column; }} .toolbar {{ justify-content:flex-start; }} .overview,.data-card,.module,.bottom {{ grid-template-columns:1fr; }} .left {{ border-right:0; border-bottom:1px solid var(--line); }} }}
  </style>
</head>
<body>
  <script>const APP_DATA = {data_json};</script>
  <header class="topbar">
    <div class="brand"><strong>多股票技术指标交互分析工具</strong><span>近两年日线数据，支持股票切换和 RSI / MACD / 布林带 / ATR 参数重算</span></div>
    <div class="toolbar">
      <select id="stockSelect" aria-label="股票选择">{options}</select>
      <input id="dateRange" readonly value="{start_date} 至 {end_date}">
      <button class="primary" id="recalcBtn">重新计算</button>
      <button id="resetBtn">恢复默认</button>
      <button id="exportBtn">导出当前CSV</button>
    </div>
  </header>
  <main class="page">
    <section class="overview">
      <div class="panel data-card">
        <div class="mini"><label>当前股票</label><span class="value" id="stockName">-</span><small id="stockCode">-</small></div>
        <div class="mini"><label>数据范围</label><span class="value" id="rowCount">-</span><small>近两年日线</small></div>
        <div class="mini"><label>最新交易日</label><span class="value" id="latestDate">-</span><small>来自 Tushare daily</small></div>
      </div>
      <div class="panel kpi"><label>最新收盘价</label><strong id="closeKpi">-</strong><small id="pctKpi">-</small></div>
      <div class="panel kpi"><label>RSI</label><strong id="rsiKpi">-</strong><small id="rsiView">-</small></div>
      <div class="panel kpi"><label>MACD 柱</label><strong id="macdKpi">-</strong><small id="macdView">-</small></div>
      <div class="panel kpi"><label>ATR</label><strong id="atrKpi">-</strong><small id="atrView">-</small></div>
      <div class="panel kpi"><label>布林带位置</label><strong id="bollKpi">-</strong><small id="bollView">-</small></div>
    </section>

    <section class="panel module">
      <div class="left"><div class="title"><h2>K线与布林带</h2><span>Price / Bollinger</span></div><div class="param"><label>布林带窗口</label><input id="bollWindow" type="number" value="20" min="5"></div><div class="param"><label>标准差倍数</label><input id="bollStd" type="number" value="2" min="0.5" step="0.1"></div><p class="note">股票切换或参数变化后，右侧 K 线和布林带会重新绘制。</p></div>
      <div class="right"><div class="chart-head"><h3>K线 + 布林带图</h3><div class="legend"><span><i class="dot" style="background:var(--red)"></i>上涨</span><span><i class="dot" style="background:var(--green)"></i>下跌</span><span><i class="dot" style="background:var(--blue)"></i>布林带</span></div></div><div class="chart large" id="priceChart"></div></div>
    </section>

    <section class="panel module">
      <div class="left"><div class="title"><h2>成交量</h2><span>Volume</span></div><div class="param"><label>显示最近 N 日</label><input id="displayCount" type="number" value="180" min="60" max="520"></div><p class="note">成交量跟随当前股票和显示区间切换，便于观察价格突破时是否放量。</p></div>
      <div class="right"><div class="chart-head"><h3>成交量图</h3><div class="legend"><span><i class="dot" style="background:var(--teal)"></i>vol</span></div></div><div class="chart" id="volumeChart"></div></div>
    </section>

    <section class="panel module">
      <div class="left"><div class="title"><h2>RSI</h2><span>Momentum</span></div><div class="param"><label>周期 period</label><input id="rsiPeriod" type="number" value="14" min="2"></div><div class="param"><label>超买线</label><input id="rsiUpper" type="number" value="70"></div><div class="param"><label>超卖线</label><input id="rsiLower" type="number" value="30"></div><p class="note">RSI 参数与 RSI 图放在同一模块，方便观察超买超卖阈值变化。</p></div>
      <div class="right"><div class="chart-head"><h3>RSI 图</h3><div class="legend"><span><i class="dot" style="background:var(--purple)"></i>RSI</span><span>阈值线</span></div></div><div class="chart" id="rsiChart"></div></div>
    </section>

    <section class="panel module">
      <div class="left"><div class="title"><h2>MACD</h2><span>Trend</span></div><div class="param"><label>Fast EMA</label><input id="macdFast" type="number" value="12" min="2"></div><div class="param"><label>Slow EMA</label><input id="macdSlow" type="number" value="26" min="3"></div><div class="param"><label>Signal EMA</label><input id="macdSignal" type="number" value="9" min="2"></div><p class="note">MACD 三个 EMA 参数和 DIF/DEA/柱状图相邻展示，便于比较趋势动能。</p></div>
      <div class="right"><div class="chart-head"><h3>MACD 图</h3><div class="legend"><span>DIF</span><span>DEA</span><span>柱状图</span></div></div><div class="chart" id="macdChart"></div></div>
    </section>

    <section class="panel module">
      <div class="left"><div class="title"><h2>ATR</h2><span>Risk</span></div><div class="param"><label>周期 period</label><input id="atrPeriod" type="number" value="14" min="2"></div><p class="note">ATR 只衡量波动，不判断方向。它适合辅助风险、止损距离和仓位判断。</p></div>
      <div class="right"><div class="chart-head"><h3>ATR 图</h3><div class="legend"><span><i class="dot" style="background:var(--orange)"></i>平均真实波幅</span></div></div><div class="chart" id="atrChart"></div></div>
    </section>

    <section class="bottom">
      <div class="panel table-panel"><div class="section-title">最近数据预览 <span id="previewTitle">Latest Rows</span></div><table><thead><tr><th>日期</th><th>收盘</th><th>涨跌幅</th><th>RSI</th><th>MACD柱</th><th>布林中轨</th><th>ATR</th></tr></thead><tbody id="previewRows"></tbody></table></div>
      <div class="panel summary-panel warn"><div class="section-title">指标解释 <span>Summary</span></div><div class="summary-list" id="summaryList"></div></div>
    </section>
  </main>

  <script>
    const fmt = (v,d=2) => Number.isFinite(v) ? Number(v).toFixed(d) : "-";
    const byId = id => document.getElementById(id);
    const num = id => Number(byId(id).value);
    const colors = {{ red:"#d93f3f", green:"#1f9d72", blue:"#2563eb", orange:"#d97706", purple:"#7c3aed", teal:"#0f9f8f", dark:"#111827" }};

    function ema(values, period) {{
      const alpha = 2 / (period + 1);
      const out = [];
      let prev = null;
      values.forEach(v => {{
        prev = prev === null ? v : alpha * v + (1 - alpha) * prev;
        out.push(prev);
      }});
      return out;
    }}
    function rma(values, period) {{
      const alpha = 1 / period;
      const out = [];
      let prev = null;
      values.forEach((v, i) => {{
        if (i < period - 1) {{ out.push(null); return; }}
        if (prev === null) {{
          const seed = values.slice(i - period + 1, i + 1).reduce((a,b)=>a+b,0) / period;
          prev = seed;
        }} else {{
          prev = alpha * v + (1 - alpha) * prev;
        }}
        out.push(prev);
      }});
      return out;
    }}
    function rolling(values, period, fn) {{
      return values.map((_, i) => i < period - 1 ? null : fn(values.slice(i - period + 1, i + 1)));
    }}
    function indicators(rows) {{
      const close = rows.map(r => r.close), high = rows.map(r => r.high), low = rows.map(r => r.low);
      const rsiPeriod = num("rsiPeriod"), atrPeriod = num("atrPeriod"), bollWindow = num("bollWindow"), bollStd = num("bollStd");
      const fast = num("macdFast"), slow = num("macdSlow"), signal = num("macdSignal");
      const delta = close.map((v,i)=> i ? v - close[i-1] : 0);
      const gain = delta.map(v=>Math.max(v,0)), loss = delta.map(v=>Math.max(-v,0));
      const avgGain = rma(gain, rsiPeriod), avgLoss = rma(loss, rsiPeriod);
      const rsi = avgGain.map((g,i)=> g == null || avgLoss[i] == null ? null : avgLoss[i] === 0 ? 100 : 100 - 100 / (1 + g / avgLoss[i]));
      const emaFast = ema(close, fast), emaSlow = ema(close, slow);
      const dif = close.map((_,i)=> emaFast[i] - emaSlow[i]);
      const dea = ema(dif, signal);
      const macdHist = dif.map((v,i)=> 2 * (v - dea[i]));
      const mid = rolling(close, bollWindow, arr => arr.reduce((a,b)=>a+b,0)/arr.length);
      const std = rolling(close, bollWindow, arr => {{ const m = arr.reduce((a,b)=>a+b,0)/arr.length; return Math.sqrt(arr.reduce((a,b)=>a+(b-m)*(b-m),0)/(arr.length-1)); }});
      const upper = mid.map((v,i)=> v == null ? null : v + bollStd * std[i]);
      const lower = mid.map((v,i)=> v == null ? null : v - bollStd * std[i]);
      const tr = rows.map((r,i)=> Math.max(r.high-r.low, Math.abs(r.high-(i?close[i-1]:r.pre_close)), Math.abs(r.low-(i?close[i-1]:r.pre_close))));
      const atr = rma(tr, atrPeriod);
      return rows.map((r,i)=> ({{...r, rsi:rsi[i], dif:dif[i], dea:dea[i], macdHist:macdHist[i], bollMid:mid[i], bollUpper:upper[i], bollLower:lower[i], atr:atr[i]}}));
    }}
    function scale(values, height, pad=18) {{
      const nums = values.filter(v => Number.isFinite(v));
      let min = Math.min(...nums), max = Math.max(...nums);
      if (!nums.length) {{ min = 0; max = 1; }}
      if (min === max) {{ min -= 1; max += 1; }}
      const extra = (max - min) * 0.08;
      min -= extra; max += extra;
      return v => pad + (max - v) / (max - min) * (height - pad * 2);
    }}
    function xScale(count, width, pad=45) {{
      return i => count <= 1 ? width / 2 : pad + i / (count - 1) * (width - pad * 2);
    }}
    function linePath(rows, x, y, key) {{
      return rows.map((r,i)=> Number.isFinite(r[key]) ? `${{i ? "L" : "M"}} ${{x(i).toFixed(1)}} ${{y(r[key]).toFixed(1)}}` : "").join(" ");
    }}
    function svgFrame(w,h) {{
      return `<svg viewBox="0 0 ${{w}} ${{h}}" role="img"><rect width="100%" height="100%" fill="#fff"/><line x1="45" y1="${{h-26}}" x2="${{w-20}}" y2="${{h-26}}" stroke="#d1d5db"/><line x1="45" y1="16" x2="45" y2="${{h-26}}" stroke="#d1d5db"/>`;
    }}
    function renderLineChart(el, rows, keys) {{
      const w=900,h=220, x=xScale(rows.length,w), y=scale(keys.flatMap(k=>rows.map(r=>r[k])),h);
      let svg = svgFrame(w,h);
      keys.forEach(([key,color,width]) => svg += `<path d="${{linePath(rows,x,y,key)}}" fill="none" stroke="${{color}}" stroke-width="${{width||2.2}}" stroke-linecap="round"/>`);
      el.innerHTML = svg + "</svg>";
    }}
    function renderPrice(rows) {{
      const display = rows.slice(-num("displayCount"));
      const w=900,h=310, x=xScale(display.length,w), all = display.flatMap(r=>[r.high,r.low,r.bollUpper,r.bollLower]).filter(Number.isFinite), y=scale(all,h);
      const step = Math.max(2, (w-90)/display.length * .55);
      let svg = svgFrame(w,h);
      svg += `<path d="${{linePath(display,x,y,"bollUpper")}}" fill="none" stroke="#93c5fd" stroke-width="2"/><path d="${{linePath(display,x,y,"bollMid")}}" fill="none" stroke="#2563eb" stroke-width="2"/><path d="${{linePath(display,x,y,"bollLower")}}" fill="none" stroke="#93c5fd" stroke-width="2"/>`;
      display.forEach((r,i)=> {{
        const c = r.close >= r.open ? colors.red : colors.green, cx=x(i), top=y(Math.max(r.open,r.close)), bot=y(Math.min(r.open,r.close));
        svg += `<line x1="${{cx}}" y1="${{y(r.high)}}" x2="${{cx}}" y2="${{y(r.low)}}" stroke="${{c}}"/><rect x="${{cx-step/2}}" y="${{top}}" width="${{step}}" height="${{Math.max(1,bot-top)}}" fill="${{c}}"/>`;
      }});
      byId("priceChart").innerHTML = svg + "</svg>";
    }}
    function renderVolume(rows) {{
      const display = rows.slice(-num("displayCount"));
      const w=900,h=220, x=xScale(display.length,w), max=Math.max(...display.map(r=>r.vol)), bar=Math.max(1,(w-90)/display.length*.65);
      let svg=svgFrame(w,h);
      display.forEach((r,i)=> {{ const bh=(r.vol/max)*(h-54), cx=x(i); svg += `<rect x="${{cx-bar/2}}" y="${{h-26-bh}}" width="${{bar}}" height="${{bh}}" fill="${{colors.teal}}" opacity=".75"/>`; }});
      byId("volumeChart").innerHTML=svg+"</svg>";
    }}
    function renderMacd(rows) {{
      const display = rows.slice(-num("displayCount"));
      const w=900,h=220, x=xScale(display.length,w), y=scale(display.flatMap(r=>[r.dif,r.dea,r.macdHist]),h), zero=y(0), bar=Math.max(1,(w-90)/display.length*.55);
      let svg=svgFrame(w,h)+`<line x1="45" y1="${{zero}}" x2="${{w-20}}" y2="${{zero}}" stroke="#9ca3af" stroke-dasharray="4 4"/>`;
      display.forEach((r,i)=> {{ const yy=y(r.macdHist), cx=x(i), c=r.macdHist>=0?colors.red:colors.blue; svg += `<rect x="${{cx-bar/2}}" y="${{Math.min(yy,zero)}}" width="${{bar}}" height="${{Math.abs(zero-yy)}}" fill="${{c}}" opacity=".58"/>`; }});
      svg += `<path d="${{linePath(display,x,y,"dif")}}" fill="none" stroke="${{colors.dark}}" stroke-width="2.2"/><path d="${{linePath(display,x,y,"dea")}}" fill="none" stroke="${{colors.orange}}" stroke-width="2.2"/></svg>`;
      byId("macdChart").innerHTML=svg;
    }}
    function renderRsi(rows) {{
      const display = rows.slice(-num("displayCount")), w=900,h=220, x=xScale(display.length,w), y=scale([0,100],h);
      let svg=svgFrame(w,h)+`<line x1="45" y1="${{y(num("rsiUpper"))}}" x2="${{w-20}}" y2="${{y(num("rsiUpper"))}}" stroke="#f59e0b" stroke-dasharray="5 5"/><line x1="45" y1="${{y(num("rsiLower"))}}" x2="${{w-20}}" y2="${{y(num("rsiLower"))}}" stroke="#60a5fa" stroke-dasharray="5 5"/>`;
      svg += `<path d="${{linePath(display,x,y,"rsi")}}" fill="none" stroke="${{colors.purple}}" stroke-width="2.6"/></svg>`;
      byId("rsiChart").innerHTML=svg;
    }}
    function renderDashboard() {{
      const stock = APP_DATA.stocks.find(s => s.ts_code === byId("stockSelect").value) || APP_DATA.stocks[0];
      const rows = indicators(stock.rows);
      const last = rows[rows.length-1];
      byId("stockName").textContent = stock.name; byId("stockCode").textContent = stock.ts_code; byId("rowCount").textContent = rows.length + " 条"; byId("latestDate").textContent = last.trade_date;
      byId("closeKpi").textContent = fmt(last.close); byId("pctKpi").textContent = `${{fmt(last.pct_chg)}}%`;
      byId("rsiKpi").textContent = fmt(last.rsi); byId("rsiView").textContent = last.rsi >= num("rsiUpper") ? "偏热" : last.rsi <= num("rsiLower") ? "偏冷" : "中性";
      byId("macdKpi").textContent = fmt(last.macdHist); byId("macdView").textContent = last.macdHist >= 0 ? "动能偏多" : "动能偏弱";
      byId("atrKpi").textContent = fmt(last.atr); byId("atrView").textContent = `约 ${{fmt(last.atr / last.close * 100)}}%`;
      byId("bollKpi").textContent = last.close > last.bollUpper ? "上轨上方" : last.close < last.bollLower ? "下轨下方" : last.close >= last.bollMid ? "中轨上方" : "中轨下方";
      byId("bollView").textContent = "相对均值位置";
      renderPrice(rows); renderVolume(rows); renderRsi(rows); renderMacd(rows); renderLineChart(byId("atrChart"), rows.slice(-num("displayCount")), [["atr", colors.orange, 2.6]]);
      byId("previewRows").innerHTML = rows.slice(-6).reverse().map(r=>`<tr><td>${{r.trade_date}}</td><td>${{fmt(r.close)}}</td><td>${{fmt(r.pct_chg)}}%</td><td>${{fmt(r.rsi)}}</td><td>${{fmt(r.macdHist)}}</td><td>${{fmt(r.bollMid)}}</td><td>${{fmt(r.atr)}}</td></tr>`).join("");
      byId("summaryList").innerHTML = `<div><b>RSI</b>：${{byId("rsiView").textContent}}，当前值 ${{fmt(last.rsi)}}。</div><div><b>MACD</b>：${{byId("macdView").textContent}}，柱状图 ${{fmt(last.macdHist)}}。</div><div><b>布林带</b>：收盘价位于${{byId("bollKpi").textContent}}。</div><div><b>ATR</b>：ATR 占收盘价约 ${{fmt(last.atr / last.close * 100)}}%，用于衡量波动风险。</div><div>技术指标只描述历史价格和波动特征，不构成投资建议。</div>`;
    }}
    function resetParams() {{ ["bollWindow","bollStd","displayCount","rsiPeriod","rsiUpper","rsiLower","macdFast","macdSlow","macdSignal","atrPeriod"].forEach((id,i)=> byId(id).value = [20,2,180,14,70,30,12,26,9,14][i]); renderDashboard(); }}
    function exportCsv() {{
      const stock = APP_DATA.stocks.find(s => s.ts_code === byId("stockSelect").value);
      const header = Object.keys(stock.rows[0]).join(",");
      const body = stock.rows.map(r => Object.values(r).join(",")).join("\\n");
      const blob = new Blob([header+"\\n"+body], {{type:"text/csv;charset=utf-8"}});
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `${{stock.name}}_${{stock.ts_code}}_daily_2y.csv`; a.click(); URL.revokeObjectURL(a.href);
    }}
    byId("stockSelect").addEventListener("change", renderDashboard);
    byId("recalcBtn").addEventListener("click", renderDashboard);
    byId("resetBtn").addEventListener("click", resetParams);
    byId("exportBtn").addEventListener("click", exportCsv);
    document.querySelectorAll("input[type=number]").forEach(el => el.addEventListener("change", renderDashboard));
    renderDashboard();
  </script>
</body>
</html>"""


def main() -> None:
    start_date, end_date = two_year_window()
    token = read_tushare_token()
    stocks_payload = fetch_stock_data(token, start_date, end_date)
    payload = build_payload(stocks_payload, start_date, end_date)

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(render_multi_stock_html(payload), encoding="utf-8")

    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_HTML}")
    for stock in stocks_payload:
        print(f"{stock['name']} {stock['ts_code']}: {len(stock['rows'])} rows -> {stock['csv']}")


if __name__ == "__main__":
    main()
