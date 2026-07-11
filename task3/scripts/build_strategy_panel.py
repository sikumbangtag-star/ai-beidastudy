from __future__ import annotations

import csv
import json
import re
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TASK3 = ROOT / "task3"
DATA_DIR = TASK3 / "data" / "stocks"
OUTPUT_JSON = TASK3 / "outputs" / "dual_ma_strategy_data.json"
OUTPUT_HTML = TASK3 / "design" / "dual_ma_strategy_panel.html"
TUSHARE_URL = "https://api.tushare.pro"

STOCKS = [
    {"ts_code": "002636.SZ", "name": "金安国纪", "slug": "jinan_guoji"},
    {"ts_code": "300308.SZ", "name": "中际旭创", "slug": "zhongji_xuchuang"},
    {"ts_code": "001309.SZ", "name": "德明利", "slug": "demingli"},
    {"ts_code": "300408.SZ", "name": "三环集团", "slug": "sanhuan_jituan"},
    {"ts_code": "603667.SH", "name": "五洲新春", "slug": "wuzhou_xinchun"},
]
BENCHMARK = {"ts_code": "000300.SH", "name": "沪深300", "slug": "hs300"}
DAILY_FIELDS = ["ts_code", "trade_date", "open", "high", "low", "close", "pre_close", "change", "pct_chg", "vol", "amount"]
NUMERIC_FIELDS = {"open", "high", "low", "close", "pre_close", "change", "pct_chg", "vol", "amount"}


def project_today() -> date:
    return date(2026, 7, 10)


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


def tushare_post(api_name: str, params: dict[str, Any], token: str, fields: list[str] | None = None) -> list[dict[str, Any]]:
    body = json.dumps(
        {
            "api_name": api_name,
            "token": token,
            "params": params,
            "fields": ",".join(fields or DAILY_FIELDS),
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
        raise RuntimeError(f"Tushare {api_name} failed: {payload.get('msg')}")
    fields = payload["data"]["fields"]
    return [dict(zip(fields, row)) for row in payload["data"]["items"]]


def normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        item = {}
        for field in DAILY_FIELDS:
            value = row.get(field)
            if field in NUMERIC_FIELDS:
                value = None if value in ("", None) else float(value)
            item[field] = value
        normalized.append(item)
    return sorted(normalized, key=lambda item: item["trade_date"])


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DAILY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def fetch_stock_data(token: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    payload = []
    for stock in STOCKS:
        rows = normalize_rows(
            tushare_post("daily", {"ts_code": stock["ts_code"], "start_date": start_date, "end_date": end_date}, token)
        )
        csv_path = DATA_DIR / f"{stock['slug']}_{stock['ts_code'].replace('.', '_')}_daily_2y.csv"
        write_csv(csv_path, rows)
        payload.append(
            {
                "ts_code": stock["ts_code"],
                "name": stock["name"],
                "slug": stock["slug"],
                "csv": str(csv_path.relative_to(ROOT)).replace("\\", "/"),
                "rows": rows,
            }
        )
    return payload


def fetch_benchmark_data(token: str, start_date: str, end_date: str) -> dict[str, Any]:
    rows = normalize_rows(
        tushare_post("index_daily", {"ts_code": BENCHMARK["ts_code"], "start_date": start_date, "end_date": end_date}, token)
    )
    csv_path = DATA_DIR / "hs300_000300_SH_daily_2y.csv"
    write_csv(csv_path, rows)
    return {
        "ts_code": BENCHMARK["ts_code"],
        "name": BENCHMARK["name"],
        "slug": BENCHMARK["slug"],
        "csv": str(csv_path.relative_to(ROOT)).replace("\\", "/"),
        "rows": rows,
    }


def build_payload(stocks: list[dict[str, Any]], benchmark: dict[str, Any], start_date: str, end_date: str) -> dict[str, Any]:
    return {
        "generated_at": date.today().isoformat(),
        "start_date": start_date,
        "end_date": end_date,
        "benchmark": benchmark,
        "stocks": stocks,
    }


HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Task3 双均线策略回测看板</title>
  <style>
    :root { --bg:#f5f7fb; --panel:#fff; --line:#d9e0ea; --text:#172033; --muted:#687387; --red:#d94141; --green:#168567; --blue:#2563eb; --orange:#d97706; --purple:#7c3aed; --teal:#0f9f8f; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--text); font-family:"Microsoft YaHei",Arial,sans-serif; font-size:14px; letter-spacing:0; }
    .topbar { min-height:64px; display:flex; align-items:center; justify-content:space-between; gap:16px; padding:12px 18px; background:#111827; color:#fff; }
    .brand strong { display:block; font-size:18px; }
    .brand span { color:#cbd5e1; font-size:12px; }
    .toolbar { display:flex; align-items:center; justify-content:flex-end; flex-wrap:wrap; gap:10px; }
    select,input,button { height:34px; border:1px solid var(--line); border-radius:6px; background:#fff; color:var(--text); padding:0 10px; font:inherit; }
    input[type=checkbox] { width:18px; height:18px; padding:0; }
    .topbar select,.topbar input { min-width:150px; background:#1f2937; border-color:#374151; color:#f9fafb; }
    button { font-weight:700; }
    .primary { background:var(--blue); border-color:var(--blue); color:#fff; }
    .page { width:min(1540px,100%); margin:0 auto; padding:14px; display:flex; flex-direction:column; gap:14px; }
    .panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; }
    .overview { display:grid; grid-template-columns:1.4fr repeat(4,minmax(0,1fr)); gap:10px; }
    .data-card,.kpi { min-height:84px; padding:12px; }
    .data-card { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; align-items:end; }
    label,.muted { color:var(--muted); font-size:12px; }
    .value,.kpi strong { display:block; min-height:25px; font-size:20px; line-height:1.15; font-weight:800; color:#111827; }
    .kpi small,.mini small { color:var(--muted); font-size:12px; }
    .module { display:grid; grid-template-columns:340px minmax(0,1fr); overflow:hidden; }
    .left { padding:16px; border-right:1px solid var(--line); background:#fbfcfe; }
    .right { min-width:0; padding:14px; }
    .title,.chart-head,.section-title { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:10px; }
    .title h2,.chart-head h3 { margin:0; color:#111827; }
    .title h2 { font-size:17px; }
    .title span,.section-title span { color:var(--muted); font-size:12px; white-space:nowrap; }
    .param { display:grid; grid-template-columns:1fr 90px; align-items:center; gap:10px; margin:9px 0; }
    .param input { width:90px; text-align:right; }
    .slider-param { margin:13px 0; }
    .slider-head { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:7px; }
    .slider-value { min-width:58px; text-align:right; color:#111827; font-weight:800; }
    .slider-param input[type=range] { width:100%; height:6px; padding:0; border:0; border-radius:999px; accent-color:var(--blue); }
    .check-param { display:flex; align-items:center; justify-content:space-between; gap:10px; margin:10px 0; color:#374151; }
    .note,.cost-box { margin:14px 0 0; padding-top:12px; border-top:1px solid #e9edf4; color:#4b5563; line-height:1.65; font-size:13px; }
    .cost-box { padding:10px; border:1px solid #e5e7eb; border-radius:6px; background:#fff; }
    .legend { display:flex; gap:12px; color:var(--muted); font-size:12px; flex-wrap:wrap; justify-content:flex-end; }
    .dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:5px; vertical-align:1px; }
    .chart { height:230px; border:1px solid #e5e7eb; border-radius:6px; background:#fff; overflow:hidden; }
    .chart.large { height:330px; }
    svg { width:100%; height:100%; display:block; }
    .metric-grid { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:10px; }
    .metric-card { min-height:72px; padding:10px; border:1px solid #e5e7eb; border-radius:6px; background:#f8fafc; }
    .metric-card label { display:block; margin-bottom:5px; }
    .metric-card strong { display:block; font-size:18px; color:#111827; line-height:1.15; }
    .trade-panel { padding:14px; overflow:auto; }
    .trade-panel table { min-width:920px; }
    table { width:100%; border-collapse:collapse; font-size:12px; }
    th,td { padding:8px 7px; border-bottom:1px solid #edf0f5; text-align:right; white-space:nowrap; }
    th:first-child,td:first-child { text-align:left; }
    th { background:#f8fafc; color:#4b5563; font-weight:800; }
    @media (max-width:1180px) { .overview,.metric-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } .data-card { grid-column:1/-1; } .module { grid-template-columns:300px minmax(0,1fr); } }
    @media (max-width:760px) { .topbar { align-items:flex-start; flex-direction:column; } .toolbar { justify-content:flex-start; } .overview,.data-card,.module,.metric-grid { grid-template-columns:1fr; } .left { border-right:0; border-bottom:1px solid var(--line); } }
  </style>
</head>
<body>
  <script>const APP_DATA = __APP_DATA__;</script>
  <header class="topbar">
    <div class="brand"><strong>Task3 双均线策略回测看板</strong><span>5 只股票近两年日线，沪深300作为基准与大盘过滤条件</span></div>
    <div class="toolbar">
      <select id="stockSelect" aria-label="股票选择">__OPTIONS__</select>
      <input id="dateRange" readonly value="__START_DATE__ 至 __END_DATE__">
      <button class="primary" id="recalcBtn">重新计算</button>
      <button id="resetBtn">恢复默认</button>
      <button id="exportBtn">导出当前CSV</button>
    </div>
  </header>
  <main class="page">
    <section class="overview">
      <div class="panel data-card">
        <div class="mini"><label>当前股票</label><span class="value" id="stockName">-</span><small id="stockCode">-</small></div>
        <div class="mini"><label>共同交易日</label><span class="value" id="alignedDays">-</span><small>股票与沪深300交集</small></div>
        <div class="mini"><label>最新交易日</label><span class="value" id="latestDate">-</span><small>来自 Tushare</small></div>
      </div>
      <div class="panel kpi"><label>策略累计收益</label><strong id="strategyReturnKpi">-</strong><small>扣除交易成本</small></div>
      <div class="panel kpi"><label>沪深300收益</label><strong id="benchmarkReturnKpi">-</strong><small>同日期区间</small></div>
      <div class="panel kpi"><label>最大回撤</label><strong id="drawdownKpi">-</strong><small>策略净值</small></div>
      <div class="panel kpi"><label>交易次数</label><strong id="tradeCountKpi">-</strong><small>买入 + 卖出</small></div>
    </section>

    <section class="panel right">
      <div class="section-title">策略指标 <span>Metrics</span></div>
      <div class="metric-grid" id="strategyMetrics"></div>
    </section>

    <section class="panel module">
      <div class="left">
        <div class="title"><h2>策略参数</h2><span>双均线</span></div>
        <div class="slider-param"><div class="slider-head"><label>快均线周期</label><span class="slider-value" id="fastMaValue">5 日</span></div><input id="fastMaWindow" type="range" value="5" min="2" max="60" step="1"></div>
        <div class="slider-param"><div class="slider-head"><label>慢均线周期</label><span class="slider-value" id="slowMaValue">20 日</span></div><input id="slowMaWindow" type="range" value="20" min="3" max="120" step="1"></div>
        <label class="check-param"><span>连续三日阳线过滤</span><input id="requireThreeBullish" type="checkbox" checked></label>
        <label class="check-param"><span>判断日沪深300上涨过滤</span><input id="requireMarketUp" type="checkbox" checked></label>
        <div class="slider-param"><div class="slider-head"><label>显示最近 N 日</label><span class="slider-value" id="displayCountValue">180 日</span></div><input id="displayCount" type="range" value="180" min="60" max="520" step="10"></div>
        <div class="cost-box">
          <div><b>买入成本率</b> 0.0005441：佣金万三 + 滑点万一 + 冲击万一 + 经手费 + 过户费</div>
          <div><b>卖出成本率</b> 0.0010441：买入侧成本 + 印花税万五</div>
          <div>信号按 T 日收盘判断，成交按 T+1 开盘价执行。</div>
        </div>
      </div>
      <div class="right">
        <div class="chart-head"><h3>股价、长短均线与买卖信号</h3><div class="legend"><span>收盘价</span><span><i class="dot" style="background:var(--blue)"></i>快均线</span><span><i class="dot" style="background:var(--orange)"></i>慢均线</span><span>买 / 卖 / 过滤</span></div></div>
        <div class="chart large" id="strategyPriceChart"></div>
      </div>
    </section>

    <section class="panel">
      <div class="right">
        <div class="chart-head"><h3>策略净值、沪深300基准与超额收益</h3><div class="legend"><span><i class="dot" style="background:var(--blue)"></i>策略净值</span><span><i class="dot" style="background:var(--teal)"></i>沪深300</span><span><i class="dot" style="background:var(--purple)"></i>超额收益</span></div></div>
        <div class="chart large" id="strategyNavChart"></div>
      </div>
    </section>

    <section class="panel trade-panel">
      <div class="section-title">交易记录 <span id="strategyTradeTitle">Trades</span></div>
      <table>
        <thead><tr><th>信号日</th><th>成交日</th><th>方向</th><th>成交价</th><th>成本率</th><th>三日阳线</th><th>大盘上涨</th><th>交易后净值</th></tr></thead>
        <tbody id="tradeRows"></tbody>
      </table>
    </section>
  </main>
  <script>
    const BUY_COST_RATE = 0.0005441;
    const SELL_COST_RATE = 0.0010441;
    const colors = { red:"#d94141", green:"#168567", blue:"#2563eb", orange:"#d97706", purple:"#7c3aed", teal:"#0f9f8f", dark:"#111827" };
    const byId = id => document.getElementById(id);
    const num = id => Number(byId(id).value);
    const fmt = (v,d=2) => Number.isFinite(v) ? Number(v).toFixed(d) : "-";
    const fmtPct = v => Number.isFinite(v) ? `${(v * 100).toFixed(2)}%` : "-";
    function simpleMa(values, period) {
      let sum = 0;
      return values.map((value, index) => {
        sum += value;
        if (index >= period) sum -= values[index - period];
        return index >= period - 1 ? sum / period : null;
      });
    }
    function alignStrategyRows(stockRows) {
      const benchmark = (APP_DATA.benchmark && APP_DATA.benchmark.rows) || [];
      const byDate = new Map(benchmark.map(row => [row.trade_date, row]));
      return stockRows.filter(row => byDate.has(row.trade_date)).map(row => ({stock: row, benchmark: byDate.get(row.trade_date)}));
    }
    function annualVolatility(returns) {
      if (returns.length < 2) return 0;
      const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length;
      const variance = returns.reduce((sum, value) => sum + Math.pow(value - mean, 2), 0) / (returns.length - 1);
      return Math.sqrt(variance) * Math.sqrt(252);
    }
    function maxDrawdown(values) {
      let peak = values[0] || 1, drawdown = 0;
      values.forEach(value => { peak = Math.max(peak, value); drawdown = Math.min(drawdown, value / peak - 1); });
      return drawdown;
    }
    function computeDualMaStrategy(stockRows) {
      const fastWindow = Math.floor(num("fastMaWindow"));
      const slowWindow = Math.floor(num("slowMaWindow"));
      if (fastWindow <= 0 || slowWindow <= 0 || fastWindow >= slowWindow) {
        return { rows: [], trades: [], metrics: { error: "快均线周期必须小于慢均线周期" } };
      }
      const aligned = alignStrategyRows(stockRows);
      if (aligned.length < slowWindow + 1) {
        return { rows: [], trades: [], metrics: { error: "股票与沪深300共同交易日不足" } };
      }
      const close = aligned.map(item => item.stock.close);
      const fastMa = simpleMa(close, fastWindow), slowMa = simpleMa(close, slowWindow);
      const requireThree = byId("requireThreeBullish").checked, requireMarket = byId("requireMarketUp").checked;
      const benchmarkStart = aligned[0].benchmark.close || 1;
      let cash = 1, shares = 0, holding = false, pending = null, entryNav = 1, entryIndex = null;
      let totalCost = 0, goldenCrossCount = 0, effectiveBuyCount = 0, filteredBuyCount = 0;
      const rows = [], trades = [], completedReturns = [], holdingDays = [];
      const threeBullish = index => index >= 2 && [index - 2, index - 1, index].every(item => aligned[item].stock.close > aligned[item].stock.open);
      const marketUp = index => index >= 1 && aligned[index].benchmark.close > aligned[index - 1].benchmark.close;
      aligned.forEach((item, index) => {
        const stock = item.stock, benchmark = item.benchmark;
        if (pending && pending.execIndex === index) {
          const price = stock.open;
          if (pending.side === "BUY") {
            const cost = cash * BUY_COST_RATE;
            shares = (cash - cost) / price; entryNav = cash; entryIndex = index; cash = 0; holding = true; totalCost += cost;
            trades.push({...pending, trade_date: stock.trade_date, price, cost_rate: BUY_COST_RATE, cost, nav_after: shares * stock.close});
          } else {
            const grossCash = shares * price, cost = grossCash * SELL_COST_RATE;
            cash = grossCash - cost; shares = 0; holding = false; totalCost += cost;
            if (entryIndex !== null) { completedReturns.push(cash / entryNav - 1); holdingDays.push(index - entryIndex); }
            trades.push({...pending, trade_date: stock.trade_date, price, cost_rate: SELL_COST_RATE, cost, nav_after: cash});
          }
          pending = null;
        }
        const nav = holding ? shares * stock.close : cash;
        const benchmarkNav = benchmark.close / benchmarkStart;
        const prevFast = index ? fastMa[index - 1] : null, prevSlow = index ? slowMa[index - 1] : null;
        const currFast = fastMa[index], currSlow = slowMa[index];
        const goldenCross = prevFast != null && prevSlow != null && currFast != null && currSlow != null && prevFast <= prevSlow && currFast > currSlow;
        const deathCross = prevFast != null && prevSlow != null && currFast != null && currSlow != null && prevFast >= prevSlow && currFast < currSlow;
        const threeOk = threeBullish(index), marketOk = marketUp(index);
        let filteredBuy = false;
        if (index < aligned.length - 1 && pending === null) {
          if (!holding && goldenCross) {
            goldenCrossCount += 1;
            if ((threeOk || !requireThree) && (marketOk || !requireMarket)) {
              effectiveBuyCount += 1;
              pending = { side:"BUY", signal_date:stock.trade_date, signalIndex:index, execIndex:index + 1, three_bullish:threeOk, market_up:marketOk };
            } else {
              filteredBuyCount += 1; filteredBuy = true;
            }
          } else if (holding && deathCross) {
            pending = { side:"SELL", signal_date:stock.trade_date, signalIndex:index, execIndex:index + 1, three_bullish:threeOk, market_up:marketOk };
          }
        }
        rows.push({...stock, fast_ma:currFast, slow_ma:currSlow, golden_cross:goldenCross, death_cross:deathCross, filtered_buy:filteredBuy, three_bullish:threeOk, market_up:marketOk, strategy_nav:nav, benchmark_nav:benchmarkNav, excess_nav:nav - benchmarkNav});
      });
      const navValues = rows.map(row => row.strategy_nav), benchValues = rows.map(row => row.benchmark_nav);
      const dailyReturns = navValues.slice(1).map((value, index) => navValues[index] ? value / navValues[index] - 1 : 0);
      const tradingDays = Math.max(1, dailyReturns.length);
      const strategyReturn = (navValues.at(-1) || 1) - 1, benchmarkReturn = (benchValues.at(-1) || 1) - 1;
      const annualReturn = Math.pow(navValues.at(-1) || 1, 252 / tradingDays) - 1, annualVol = annualVolatility(dailyReturns);
      const completed = completedReturns.length;
      return {
        rows, trades,
        metrics: {
          strategy_return: strategyReturn, benchmark_return: benchmarkReturn, excess_return: strategyReturn - benchmarkReturn,
          annual_return: annualReturn, annual_volatility: annualVol, max_drawdown: maxDrawdown(navValues),
          sharpe_ratio: annualVol ? annualReturn / annualVol : 0, trade_count: trades.length,
          win_rate: completed ? completedReturns.filter(value => value > 0).length / completed : 0,
          average_holding_days: holdingDays.length ? holdingDays.reduce((sum, value) => sum + value, 0) / holdingDays.length : 0,
          total_cost: totalCost, golden_cross_count: goldenCrossCount, effective_buy_count: effectiveBuyCount,
          filtered_buy_count: filteredBuyCount, aligned_days: rows.length
        }
      };
    }
    function scale(values, height, pad=18) {
      const nums = values.filter(Number.isFinite);
      let min = nums.length ? Math.min(...nums) : 0, max = nums.length ? Math.max(...nums) : 1;
      if (min === max) { min -= 1; max += 1; }
      const extra = (max - min) * 0.08; min -= extra; max += extra;
      return v => pad + (max - v) / (max - min) * (height - pad * 2);
    }
    function xScale(count, width, pad=46) { return i => count <= 1 ? width / 2 : pad + i / (count - 1) * (width - pad * 2); }
    function linePath(rows, x, y, key) { return rows.map((row, index) => Number.isFinite(row[key]) ? `${index ? "L" : "M"} ${x(index).toFixed(1)} ${y(row[key]).toFixed(1)}` : "").join(" "); }
    function svgFrame(w,h) { return `<svg viewBox="0 0 ${w} ${h}" role="img"><rect width="100%" height="100%" fill="#fff"/><line x1="46" y1="${h-28}" x2="${w-20}" y2="${h-28}" stroke="#d1d5db"/><line x1="46" y1="16" x2="46" y2="${h-28}" stroke="#d1d5db"/>`; }
    function renderStrategyPriceChart(result) {
      const rows = result.rows.slice(-num("displayCount"));
      const w = 920, h = 330, x = xScale(rows.length, w), y = scale(rows.flatMap(row => [row.close, row.fast_ma, row.slow_ma]), h);
      let svg = svgFrame(w, h);
      svg += `<path d="${linePath(rows, x, y, "close")}" fill="none" stroke="${colors.dark}" stroke-width="2.1"/>`;
      svg += `<path d="${linePath(rows, x, y, "fast_ma")}" fill="none" stroke="${colors.blue}" stroke-width="2.2"/>`;
      svg += `<path d="${linePath(rows, x, y, "slow_ma")}" fill="none" stroke="${colors.orange}" stroke-width="2.2"/>`;
      const indexByDate = new Map(rows.map((row, index) => [row.trade_date, index]));
      result.trades.forEach(trade => {
        if (!indexByDate.has(trade.signal_date)) return;
        const index = indexByDate.get(trade.signal_date), row = rows[index], cx = x(index), cy = y(row.close);
        const color = trade.side === "BUY" ? colors.red : colors.green, label = trade.side === "BUY" ? "B" : "S";
        svg += `<circle cx="${cx}" cy="${cy}" r="6" fill="${color}"/><text x="${cx}" y="${cy + 3}" text-anchor="middle" font-size="8" fill="#fff" font-weight="700">${label}</text>`;
      });
      rows.forEach((row, index) => {
        if (!row.filtered_buy) return;
        const cx = x(index), cy = y(row.close);
        svg += `<path d="M ${cx - 6} ${cy - 6} L ${cx + 6} ${cy + 6} M ${cx + 6} ${cy - 6} L ${cx - 6} ${cy + 6}" stroke="${colors.purple}" stroke-width="2.2"/>`;
      });
      byId("strategyPriceChart").innerHTML = svg + "</svg>";
    }
    function renderStrategyNavChart(result) {
      const rows = result.rows.slice(-num("displayCount"));
      const w = 920, h = 330, x = xScale(rows.length, w), y = scale(rows.flatMap(row => [row.strategy_nav, row.benchmark_nav, 1 + row.excess_nav]), h);
      let svg = svgFrame(w, h);
      svg += `<path d="${linePath(rows, x, y, "strategy_nav")}" fill="none" stroke="${colors.blue}" stroke-width="2.5"/>`;
      svg += `<path d="${linePath(rows, x, y, "benchmark_nav")}" fill="none" stroke="${colors.teal}" stroke-width="2.3"/>`;
      const excessRows = rows.map(row => ({...row, excess_line: 1 + row.excess_nav}));
      svg += `<path d="${linePath(excessRows, x, y, "excess_line")}" fill="none" stroke="${colors.purple}" stroke-width="2" stroke-dasharray="5 5"/>`;
      byId("strategyNavChart").innerHTML = svg + "</svg>";
    }
    function renderStrategyMetrics(metrics) {
      if (metrics.error) {
        byId("strategyMetrics").innerHTML = `<div class="metric-card"><label>策略状态</label><strong>${metrics.error}</strong></div>`;
        return;
      }
      const items = [
        ["策略累计收益", fmtPct(metrics.strategy_return)], ["沪深300收益", fmtPct(metrics.benchmark_return)],
        ["超额收益", fmtPct(metrics.excess_return)], ["年化收益", fmtPct(metrics.annual_return)],
        ["年化波动", fmtPct(metrics.annual_volatility)], ["最大回撤", fmtPct(metrics.max_drawdown)],
        ["夏普比率", fmt(metrics.sharpe_ratio, 2)], ["交易次数", metrics.trade_count],
        ["胜率", fmtPct(metrics.win_rate)], ["平均持仓天数", fmt(metrics.average_holding_days, 1)],
        ["总交易成本", fmtPct(metrics.total_cost)], ["金叉/有效/过滤", `${metrics.golden_cross_count}/${metrics.effective_buy_count}/${metrics.filtered_buy_count}`],
      ];
      byId("strategyMetrics").innerHTML = items.map(([label, value]) => `<div class="metric-card"><label>${label}</label><strong>${value}</strong></div>`).join("");
    }
    function renderTradeRows(trades) {
      byId("strategyTradeTitle").textContent = `${trades.length} records`;
      byId("tradeRows").innerHTML = trades.length
        ? trades.map(trade => `<tr><td>${trade.signal_date}</td><td>${trade.trade_date}</td><td>${trade.side === "BUY" ? "买入" : "卖出"}</td><td>${fmt(trade.price, 3)}</td><td>${fmt(trade.cost_rate, 7)}</td><td>${trade.three_bullish ? "是" : "否"}</td><td>${trade.market_up ? "是" : "否"}</td><td>${fmt(trade.nav_after, 4)}</td></tr>`).join("")
        : `<tr><td colspan="8">当前参数下没有完成交易。</td></tr>`;
    }
    function renderDashboard() {
      syncSliderValues();
      const stock = APP_DATA.stocks.find(item => item.ts_code === byId("stockSelect").value) || APP_DATA.stocks[0];
      const result = computeDualMaStrategy(stock.rows), metrics = result.metrics;
      const lastRow = result.rows.at(-1) || stock.rows.at(-1);
      byId("stockName").textContent = stock.name; byId("stockCode").textContent = stock.ts_code;
      byId("alignedDays").textContent = metrics.aligned_days || result.rows.length || "-";
      byId("latestDate").textContent = lastRow ? lastRow.trade_date : "-";
      byId("strategyReturnKpi").textContent = metrics.error ? "-" : fmtPct(metrics.strategy_return);
      byId("benchmarkReturnKpi").textContent = metrics.error ? "-" : fmtPct(metrics.benchmark_return);
      byId("drawdownKpi").textContent = metrics.error ? "-" : fmtPct(metrics.max_drawdown);
      byId("tradeCountKpi").textContent = metrics.error ? "-" : metrics.trade_count;
      renderStrategyPriceChart(result); renderStrategyNavChart(result); renderStrategyMetrics(metrics); renderTradeRows(result.trades);
    }
    function syncSliderValues() {
      byId("fastMaValue").textContent = `${num("fastMaWindow")} 日`;
      byId("slowMaValue").textContent = `${num("slowMaWindow")} 日`;
      byId("displayCountValue").textContent = `${num("displayCount")} 日`;
    }
    function resetParams() {
      byId("fastMaWindow").value = 5; byId("slowMaWindow").value = 20; byId("displayCount").value = 180;
      byId("requireThreeBullish").checked = true; byId("requireMarketUp").checked = true;
      renderDashboard();
    }
    function exportCsv() {
      const stock = APP_DATA.stocks.find(item => item.ts_code === byId("stockSelect").value) || APP_DATA.stocks[0];
      const header = Object.keys(stock.rows[0]).join(",");
      const body = stock.rows.map(row => Object.values(row).join(",")).join("\n");
      const blob = new Blob([header + "\n" + body], {type:"text/csv;charset=utf-8"});
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `${stock.name}_${stock.ts_code}_daily_2y.csv`; a.click(); URL.revokeObjectURL(a.href);
    }
    byId("stockSelect").addEventListener("change", renderDashboard);
    byId("recalcBtn").addEventListener("click", renderDashboard);
    byId("resetBtn").addEventListener("click", resetParams);
    byId("exportBtn").addEventListener("click", exportCsv);
    document.querySelectorAll("input[type=range]").forEach(item => item.addEventListener("input", renderDashboard));
    document.querySelectorAll("input[type=checkbox]").forEach(item => item.addEventListener("change", renderDashboard));
    renderDashboard();
  </script>
</body>
</html>
"""


def render_panel_html(payload: dict[str, Any]) -> str:
    options = "\n".join(
        f'<option value="{stock["ts_code"]}">{stock["name"]} {stock["ts_code"]}</option>'
        for stock in payload["stocks"]
    )
    return (
        HTML_TEMPLATE.replace("__APP_DATA__", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        .replace("__OPTIONS__", options)
        .replace("__START_DATE__", payload.get("start_date", ""))
        .replace("__END_DATE__", payload.get("end_date", ""))
    )


def main() -> None:
    start_date, end_date = two_year_window()
    token = read_tushare_token()
    stocks = fetch_stock_data(token, start_date, end_date)
    benchmark = fetch_benchmark_data(token, start_date, end_date)
    payload = build_payload(stocks, benchmark, start_date, end_date)

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(render_panel_html(payload), encoding="utf-8")

    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_HTML}")
    print(f"{benchmark['name']} {benchmark['ts_code']}: {len(benchmark['rows'])} rows -> {benchmark['csv']}")
    for stock in stocks:
        print(f"{stock['name']} {stock['ts_code']}: {len(stock['rows'])} rows -> {stock['csv']}")


if __name__ == "__main__":
    main()
