from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TASK3_JSON = ROOT / "task3" / "outputs" / "dual_ma_strategy_data.json"
TASK4 = ROOT / "task4"
DATA_DIR = TASK4 / "data" / "stocks"
OUTPUT_JSON = TASK4 / "outputs" / "turtle_strategy_data.json"
OUTPUT_HTML = TASK4 / "design" / "turtle_strategy_panel.html"
INDEX_HTML = TASK4 / "index.html"

DAILY_FIELDS = ["ts_code", "trade_date", "open", "high", "low", "close", "pre_close", "change", "pct_chg", "vol", "amount"]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DAILY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def build_payload_from_task3() -> dict[str, Any]:
    source = json.loads(TASK3_JSON.read_text(encoding="utf-8"))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    stocks = []
    for stock in source["stocks"]:
        csv_name = Path(stock.get("csv", f"{stock['ts_code']}.csv")).name
        csv_path = DATA_DIR / csv_name
        write_csv(csv_path, stock["rows"])
        stocks.append({**stock, "csv": str(csv_path.relative_to(ROOT)).replace("\\", "/")})

    benchmark = source["benchmark"]
    benchmark_path = DATA_DIR / "hs300_000300_SH_daily_2y.csv"
    write_csv(benchmark_path, benchmark["rows"])
    benchmark = {**benchmark, "csv": str(benchmark_path.relative_to(ROOT)).replace("\\", "/")}
    return {
        "generated_at": source.get("generated_at"),
        "start_date": source.get("start_date"),
        "end_date": source.get("end_date"),
        "benchmark": benchmark,
        "stocks": stocks,
    }


HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Task4 海龟策略量化看板</title>
  <style>
    :root { --bg:#f5f7fb; --panel:#fff; --line:#d9e0ea; --text:#172033; --muted:#687387; --red:#d94141; --green:#168567; --blue:#2563eb; --orange:#d97706; --purple:#7c3aed; --teal:#0f9f8f; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--text); font-family:"Microsoft YaHei",Arial,sans-serif; font-size:14px; letter-spacing:0; }
    .topbar { min-height:64px; display:flex; align-items:center; justify-content:space-between; gap:16px; padding:12px 18px; background:#111827; color:#fff; }
    .brand strong { display:block; font-size:18px; }
    .brand span { color:#cbd5e1; font-size:12px; }
    .toolbar { display:flex; align-items:center; justify-content:flex-end; flex-wrap:wrap; gap:10px; }
    select,input,button { height:34px; border:1px solid var(--line); border-radius:6px; background:#fff; color:var(--text); padding:0 10px; font:inherit; }
    .topbar select,.topbar input { min-width:150px; background:#1f2937; border-color:#374151; color:#f9fafb; }
    button { font-weight:700; }
    .primary { background:var(--blue); border-color:var(--blue); color:#fff; }
    .page { width:min(1540px,100%); margin:0 auto; padding:14px; }
    .workbench { display:grid; grid-template-columns:280px minmax(0,1fr); gap:14px; align-items:start; }
    .dashboard-content { min-width:0; display:flex; flex-direction:column; gap:14px; }
    .panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; }
    .overview { display:grid; grid-template-columns:1.4fr repeat(4,minmax(0,1fr)); gap:10px; }
    .data-card,.kpi { min-height:84px; padding:12px; }
    .data-card { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; align-items:end; }
    label,.muted { color:var(--muted); font-size:12px; }
    .value,.kpi strong { display:block; min-height:25px; font-size:20px; line-height:1.15; font-weight:800; color:#111827; }
    .kpi small,.mini small { color:var(--muted); font-size:12px; }
    .right { min-width:0; padding:14px; }
    .chart-head,.section-title { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:10px; }
    .chart-head h3 { margin:0; color:#111827; }
    .section-title span { color:var(--muted); font-size:12px; white-space:nowrap; }
    .legend { display:flex; gap:12px; color:var(--muted); font-size:12px; flex-wrap:wrap; justify-content:flex-end; }
    .dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:5px; vertical-align:1px; }
    .chart { height:230px; border:1px solid #e5e7eb; border-radius:6px; background:#fff; overflow:hidden; }
    .chart.large { height:330px; }
    svg { width:100%; height:100%; display:block; }
    .metric-grid { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:10px; }
    .metric-card { min-height:72px; padding:10px; border:1px solid #e5e7eb; border-radius:6px; background:#f8fafc; }
    .metric-card label { display:block; margin-bottom:5px; }
    .metric-card strong { display:block; font-size:18px; color:#111827; line-height:1.15; }
    .strategy-sidebar { position:sticky; top:14px; padding:14px; display:flex; flex-direction:column; gap:16px; }
    .sidebar-title strong { display:block; font-size:17px; color:#111827; }
    .sidebar-title span { display:block; margin-top:4px; color:var(--muted); font-size:12px; line-height:1.45; }
    .control-stack { display:flex; flex-direction:column; gap:14px; }
    .control-group label { display:block; margin-bottom:7px; }
    .control-group select,.control-group button { width:100%; }
    .parameter-panel { display:grid; grid-template-columns:220px minmax(0,1fr); gap:18px; align-items:center; }
    .parameter-note { color:var(--muted); line-height:1.65; }
    .slider-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; }
    .strategy-sidebar .slider-grid { grid-template-columns:1fr; gap:14px; }
    .slider-head { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:8px; }
    .slider-value { min-width:60px; text-align:right; color:#111827; font-weight:800; }
    .slider-param input[type=range] { width:100%; height:6px; padding:0; border:0; border-radius:999px; accent-color:var(--blue); }
    .trade-panel { padding:14px; overflow:auto; }
    .trade-panel table { min-width:920px; }
    table { width:100%; border-collapse:collapse; font-size:12px; }
    th,td { padding:8px 7px; border-bottom:1px solid #edf0f5; text-align:right; white-space:nowrap; }
    th:first-child,td:first-child { text-align:left; }
    th { background:#f8fafc; color:#4b5563; font-weight:800; }
    @media (max-width:1180px) { .overview,.metric-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } .data-card { grid-column:1/-1; } }
    @media (max-width:960px) { .workbench { grid-template-columns:1fr; } .strategy-sidebar { position:static; } }
    @media (max-width:760px) { .topbar { align-items:flex-start; flex-direction:column; } .toolbar { justify-content:flex-start; } .overview,.data-card,.metric-grid,.parameter-panel,.slider-grid { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <script>const APP_DATA = __APP_DATA__;</script>
  <header class="topbar">
    <div class="brand"><strong>Task4 海龟策略量化看板</strong><span>支持 20/10 与 55/20 两个海龟策略版本切换</span></div>
    <div class="toolbar">
      <select id="stockSelect" aria-label="股票选择">__OPTIONS__</select>
      <input id="dateRange" readonly value="__START_DATE__ 至 __END_DATE__">
      <button id="exportBtn">导出当前CSV</button>
    </div>
  </header>
  <main class="page">
    <div class="workbench">
      <aside class="panel strategy-sidebar">
        <div class="sidebar-title"><strong>策略参数</strong><span>选择预设版本，或拖动周期滑杆观察不同海龟参数下的信号与回测结果。</span></div>
        <div class="control-stack">
          <div class="control-group">
            <label>策略版本</label>
            <select id="variantSelect" aria-label="海龟策略版本">
              <option value="short_20_10">20/10 短周期海龟</option>
              <option value="long_55_20">55/20 长周期海龟</option>
            </select>
          </div>
          <div class="slider-grid">
            <div class="slider-param"><div class="slider-head"><label>入场突破周期</label><span class="slider-value" id="entryWindowValue">20 日</span></div><input id="entryWindow" type="range" value="20" min="5" max="120" step="1"></div>
            <div class="slider-param"><div class="slider-head"><label>出场跌破周期</label><span class="slider-value" id="exitWindowValue">10 日</span></div><input id="exitWindow" type="range" value="10" min="2" max="80" step="1"></div>
          </div>
          <div class="control-group">
            <label>止损模式</label>
            <select id="stopMode" aria-label="止损模式">
              <option value="channel">低价通道止损</option>
              <option value="atr">ATR 止损</option>
              <option value="both">通道或 ATR 先触发</option>
            </select>
          </div>
          <div class="slider-grid">
            <div class="slider-param"><div class="slider-head"><label>ATR 周期</label><span class="slider-value" id="atrWindowValue">20 日</span></div><input id="atrWindow" type="range" value="20" min="5" max="60" step="1"></div>
            <div class="slider-param"><div class="slider-head"><label>ATR 止损倍数</label><span class="slider-value" id="atrMultiplierValue">2.0 倍</span></div><input id="atrMultiplier" type="range" value="2" min="0.5" max="5" step="0.1"></div>
            <div class="slider-param"><div class="slider-head"><label>单笔风险比例</label><span class="slider-value" id="riskPerTradeValue">1.0%</span></div><input id="riskPerTrade" type="range" value="1" min="0.2" max="5" step="0.1"></div>
            <div class="slider-param"><div class="slider-head"><label>最大仓位比例</label><span class="slider-value" id="maxPositionValue">100%</span></div><input id="maxPosition" type="range" value="100" min="5" max="100" step="5"></div>
          </div>
          <div class="control-group"><button class="primary" id="recalcBtn">重新计算</button></div>
        </div>
        <div class="parameter-note">当前口径：T 日收盘判断信号，T+1 开盘成交；买入成本率 0.0005441，卖出成本率 0.0010441。通道模式按收盘价跌破出场低价通道卖出，ATR 仅作为波动指标展示；ATR 模式用买入价减 ATR 倍数止损，并按单笔风险比例控制仓位。默认显示 ATR(20)。</div>
      </aside>
      <div class="dashboard-content">
    <section class="overview">
      <div class="panel data-card">
        <div class="mini"><label>当前股票</label><span class="value" id="stockName">-</span><small id="stockCode">-</small></div>
        <div class="mini"><label>策略版本</label><span class="value" id="variantName">-</span><small>入场 / 出场窗口</small></div>
        <div class="mini"><label>共同交易日</label><span class="value" id="alignedDays">-</span><small>股票与沪深300交集</small></div>
      </div>
      <div class="panel kpi"><label>策略累计收益</label><strong id="strategyReturnKpi">-</strong><small>扣除交易成本</small></div>
      <div class="panel kpi"><label>沪深300收益</label><strong id="benchmarkReturnKpi">-</strong><small>同日期区间</small></div>
      <div class="panel kpi"><label>最大回撤</label><strong id="drawdownKpi">-</strong><small>策略净值</small></div>
      <div class="panel kpi"><label>交易次数</label><strong id="tradeCountKpi">-</strong><small>买入 + 卖出</small></div>
    </section>

    <section class="panel right">
      <div class="section-title">策略指标 <span>Metrics</span></div>
      <div class="metric-grid" id="turtleMetrics"></div>
    </section>

    <section class="panel right">
      <div class="chart-head"><h3>股价、高低价格通道与交易信号</h3><div class="legend"><span>收盘价</span><span><i class="dot" style="background:var(--blue)"></i>入场高价通道</span><span><i class="dot" style="background:var(--orange)"></i>出场低价通道</span><span><i class="dot" style="background:var(--red)"></i>ATR止损线</span><span>买 / 卖</span></div></div>
      <div class="chart large" id="turtlePriceChart"></div>
    </section>

    <section class="panel right">
      <div class="chart-head"><h3>策略净值、沪深300基准与超额收益</h3><div class="legend"><span><i class="dot" style="background:var(--blue)"></i>策略净值</span><span><i class="dot" style="background:var(--teal)"></i>沪深300</span><span><i class="dot" style="background:var(--purple)"></i>超额收益</span></div></div>
      <div class="chart large" id="turtleNavChart"></div>
    </section>

    <section class="panel trade-panel">
      <div class="section-title">交易记录 <span id="tradeTitle">Trades</span></div>
      <table>
        <thead><tr><th>信号日</th><th>成交日</th><th>方向</th><th>触发条件</th><th>成交价</th><th>成本率</th><th>交易后净值</th></tr></thead>
        <tbody id="tradeRows"></tbody>
      </table>
    </section>
      </div>
    </div>
  </main>
  <script>
    const BUY_COST_RATE = 0.0005441;
    const SELL_COST_RATE = 0.0010441;
    const DEFAULT_ATR_WINDOW = 20;
    const VARIANTS = {
      short_20_10: {label:"20/10", entry_window:20, exit_window:10},
      long_55_20: {label:"55/20", entry_window:55, exit_window:20}
    };
    const colors = { red:"#d94141", green:"#168567", blue:"#2563eb", orange:"#d97706", purple:"#7c3aed", teal:"#0f9f8f", dark:"#111827" };
    const byId = id => document.getElementById(id);
    const fmt = (v,d=2) => Number.isFinite(v) ? Number(v).toFixed(d) : "-";
    const fmtPct = v => Number.isFinite(v) ? `${(v * 100).toFixed(2)}%` : "-";
    function alignRows(stockRows) {
      const byDate = new Map((APP_DATA.benchmark.rows || []).map(row => [row.trade_date, row]));
      return stockRows.filter(row => byDate.has(row.trade_date)).map(row => ({stock: row, benchmark: byDate.get(row.trade_date)}));
    }
    function previousHigh(rows, index, window) {
      if (index < window) return null;
      return Math.max(...rows.slice(index - window, index).map(row => row.high));
    }
    function previousLow(rows, index, window) {
      if (index < window) return null;
      return Math.min(...rows.slice(index - window, index).map(row => row.low));
    }
    function trueRange(rows, index) {
      const row = rows[index], previous = rows[index - 1];
      const highLow = row.high - row.low;
      if (!previous) return highLow;
      return Math.max(highLow, Math.abs(row.high - previous.close), Math.abs(row.low - previous.close));
    }
    function calculateAtr(rows, index, window=DEFAULT_ATR_WINDOW) {
      if (index < window - 1) return null;
      const values = rows.slice(index - window + 1, index + 1).map((_, offset) => trueRange(rows, index - window + 1 + offset));
      return values.reduce((sum, value) => sum + value, 0) / values.length;
    }
    function positionSizeByAtr(cash, price, atr, settings) {
      if (settings.stop_mode === "channel") {
        return {shares: cash * (1 - BUY_COST_RATE) / price, cost: cash * BUY_COST_RATE, cash_after: 0, position_value: cash * (1 - BUY_COST_RATE)};
      }
      if (!Number.isFinite(atr) || atr <= 0 || !Number.isFinite(price) || price <= 0) {
        return {shares: 0, cost: 0, cash_after: cash, position_value: 0};
      }
      const riskBudget = cash * settings.risk_per_trade;
      const stopDistance = atr * settings.atr_multiplier;
      const riskShares = riskBudget / stopDistance;
      const maxShares = cash * settings.max_position / price;
      const affordableShares = cash / (price * (1 + BUY_COST_RATE));
      const shares = Math.max(0, Math.min(riskShares, maxShares, affordableShares));
      const positionValue = shares * price;
      const cost = positionValue * BUY_COST_RATE;
      return {shares, cost, cash_after: cash - positionValue - cost, position_value: positionValue};
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
    function computeTurtleStrategy(stockRows) {
      const settings = currentTurtleSettings();
      const variant = settings.variant;
      const aligned = alignRows(stockRows);
      if (aligned.length < Math.max(settings.entry_window, settings.exit_window) + 1) {
        return {rows: [], trades: [], metrics: {error: "共同交易日不足"}};
      }
      const stocks = aligned.map(item => item.stock);
      const benchmarkStart = aligned[0].benchmark.close || 1;
      let cash = 1, shares = 0, holding = false, pending = null, entryNav = 1, entryIndex = null;
      let activeAtrStop = null;
      let totalCost = 0, entryBreakoutCount = 0, effectiveBuyCount = 0, exitBreakoutCount = 0, effectiveSellCount = 0, atrStopCount = 0;
      const rows = [], trades = [], completedReturns = [], holdingDays = [];
      aligned.forEach((item, index) => {
        const stock = item.stock, benchmark = item.benchmark;
        if (pending && pending.execIndex === index) {
          const price = stock.open;
          if (pending.side === "BUY") {
            const sizing = positionSizeByAtr(cash, price, pending.atr, settings);
            if (sizing.shares > 0) {
              const beforeBuyNav = cash + shares * stock.close;
              shares = sizing.shares; entryNav = beforeBuyNav; entryIndex = index; cash = sizing.cash_after; holding = true; totalCost += sizing.cost;
              activeAtrStop = settings.stop_mode !== "channel" && Number.isFinite(pending.atr) ? price - settings.atr_multiplier * pending.atr : null;
              trades.push({...pending, trade_date: stock.trade_date, price, cost_rate: BUY_COST_RATE, cost:sizing.cost, position_value:sizing.position_value, atr_stop_price:activeAtrStop, stop_reason:"入场", nav_after: cash + shares * stock.close});
            }
          } else {
            const grossCash = shares * price, cost = grossCash * SELL_COST_RATE;
            cash += grossCash - cost; shares = 0; holding = false; totalCost += cost; activeAtrStop = null;
            if (entryIndex !== null) { completedReturns.push(cash / entryNav - 1); holdingDays.push(index - entryIndex); }
            trades.push({...pending, trade_date: stock.trade_date, price, cost_rate: SELL_COST_RATE, cost, nav_after: cash});
          }
          pending = null;
        }
        const entry_channel = previousHigh(stocks, index, settings.entry_window);
        const exit_channel = previousLow(stocks, index, settings.exit_window);
        const atr = calculateAtr(stocks, index, settings.atr_window);
        const entry_breakout = entry_channel != null && stock.close > entry_channel;
        const exit_breakout = exit_channel != null && stock.close < exit_channel;
        if (index < aligned.length - 1 && pending === null) {
          if (!holding && entry_breakout) {
            entryBreakoutCount += 1; effectiveBuyCount += 1;
            if (settings.stop_mode === "channel" || Number.isFinite(atr)) {
              pending = {side:"BUY", signal_date:stock.trade_date, signalIndex:index, execIndex:index + 1, entry_channel, exit_channel, atr};
            } else {
              effectiveBuyCount -= 1;
            }
          } else if (holding) {
            const channelExit = settings.stop_mode !== "atr" && exit_breakout;
            const atrExit = settings.stop_mode !== "channel" && activeAtrStop != null && stock.close < activeAtrStop;
            if (channelExit || atrExit) {
              if (channelExit) exitBreakoutCount += 1;
              if (atrExit) atrStopCount += 1;
              effectiveSellCount += 1;
              const stop_reason = channelExit && atrExit ? "通道+ATR止损" : (atrExit ? "ATR止损" : "跌破低价通道");
              pending = {side:"SELL", signal_date:stock.trade_date, signalIndex:index, execIndex:index + 1, entry_channel, exit_channel, atr_stop_price:activeAtrStop, stop_reason};
            }
          }
        }
        const nav = cash + shares * stock.close;
        const benchmark_nav = benchmark.close / benchmarkStart;
        rows.push({...stock, entry_channel, exit_channel, atr, atr_stop_price:holding ? activeAtrStop : null, entry_breakout, exit_breakout, strategy_nav:nav, benchmark_nav, excess_nav: nav - benchmark_nav});
      });
      const navValues = rows.map(row => row.strategy_nav), benchValues = rows.map(row => row.benchmark_nav);
      const dailyReturns = navValues.slice(1).map((value, index) => navValues[index] ? value / navValues[index] - 1 : 0);
      const tradingDays = Math.max(1, dailyReturns.length);
      const strategyReturn = (navValues.at(-1) || 1) - 1, benchmarkReturn = (benchValues.at(-1) || 1) - 1;
      const annualReturn = Math.pow(navValues.at(-1) || 1, 252 / tradingDays) - 1, annualVol = annualVolatility(dailyReturns);
      const latestRow = rows.at(-1) || {};
      const latestAtr = Number.isFinite(latestRow.atr) ? latestRow.atr : null;
      const completed = completedReturns.length;
      return {rows, trades, metrics: {
        variant, entry_window:settings.entry_window, exit_window:settings.exit_window,
        strategy_return:strategyReturn, benchmark_return:benchmarkReturn, excess_return:strategyReturn - benchmarkReturn,
        annual_return:annualReturn, annual_volatility:annualVol, max_drawdown:maxDrawdown(navValues),
        sharpe_ratio: annualVol ? annualReturn / annualVol : 0, trade_count:trades.length,
        win_rate: completed ? completedReturns.filter(value => value > 0).length / completed : 0,
        average_holding_days: holdingDays.length ? holdingDays.reduce((sum, value) => sum + value, 0) / holdingDays.length : 0,
        total_cost:totalCost, entry_breakout_count:entryBreakoutCount, effective_buy_count:effectiveBuyCount,
        exit_breakout_count:exitBreakoutCount, effective_sell_count:effectiveSellCount, aligned_days:rows.length,
        atr_window:settings.atr_window, atr_multiplier:settings.atr_multiplier, stop_mode:settings.stop_mode,
        risk_per_trade:settings.risk_per_trade, max_position:settings.max_position, atr_stop_count:atrStopCount,
        latest_atr:latestAtr, latest_atr_pct:latestAtr && latestRow.close ? latestAtr / latestRow.close : null
      }};
    }
    function currentTurtleSettings() {
      const variant = byId("variantSelect").value;
      return {
        ...VARIANTS[variant],
        variant,
        entry_window: Number(byId("entryWindow").value),
        exit_window: Number(byId("exitWindow").value),
        stop_mode: byId("stopMode").value,
        atr_window: Number(byId("atrWindow").value),
        atr_multiplier: Number(byId("atrMultiplier").value),
        risk_per_trade: Number(byId("riskPerTrade").value) / 100,
        max_position: Number(byId("maxPosition").value) / 100
      };
    }
    function syncTurtleWindows() {
      byId("entryWindowValue").textContent = `${Number(byId("entryWindow").value)} 日`;
      byId("exitWindowValue").textContent = `${Number(byId("exitWindow").value)} 日`;
      byId("atrWindowValue").textContent = `${Number(byId("atrWindow").value)} 日`;
      byId("atrMultiplierValue").textContent = `${Number(byId("atrMultiplier").value).toFixed(1)} 倍`;
      byId("riskPerTradeValue").textContent = `${Number(byId("riskPerTrade").value).toFixed(1)}%`;
      byId("maxPositionValue").textContent = `${Number(byId("maxPosition").value).toFixed(0)}%`;
    }
    function applyVariantPreset() {
      const preset = VARIANTS[byId("variantSelect").value];
      byId("entryWindow").value = preset.entry_window;
      byId("exitWindow").value = preset.exit_window;
      renderDashboard();
    }
    function scale(values, height, pad=18) {
      const nums = values.filter(Number.isFinite);
      let min = nums.length ? Math.min(...nums) : 0, max = nums.length ? Math.max(...nums) : 1;
      if (min === max) { min -= 1; max += 1; }
      const extra = (max - min) * 0.08; min -= extra; max += extra;
      return v => pad + (max - v) / (max - min) * (height - pad * 2);
    }
    function xScale(count, width, pad=46) { return i => count <= 1 ? width / 2 : pad + i / (count - 1) * (width - pad * 2); }
    function linePath(rows, x, y, key) {
      let started = false;
      return rows.map((row, index) => {
        if (!Number.isFinite(row[key])) {
          started = false;
          return "";
        }
        const command = started ? "L" : "M";
        started = true;
        return `${command} ${x(index).toFixed(1)} ${y(row[key]).toFixed(1)}`;
      }).join(" ");
    }
    function svgFrame(w,h) { return `<svg viewBox="0 0 ${w} ${h}" role="img"><rect width="100%" height="100%" fill="#fff"/><line x1="46" y1="${h-28}" x2="${w-20}" y2="${h-28}" stroke="#d1d5db"/><line x1="46" y1="16" x2="46" y2="${h-28}" stroke="#d1d5db"/>`; }
    function renderPriceChart(result) {
      const rows = result.rows;
      const w = 920, h = 330, x = xScale(rows.length, w), y = scale(rows.flatMap(row => [row.close, row.entry_channel, row.exit_channel, row.atr_stop_price]), h);
      let svg = svgFrame(w, h);
      svg += `<path d="${linePath(rows, x, y, "close")}" fill="none" stroke="${colors.dark}" stroke-width="2.1"/>`;
      svg += `<path d="${linePath(rows, x, y, "entry_channel")}" fill="none" stroke="${colors.blue}" stroke-width="2.2"/>`;
      svg += `<path d="${linePath(rows, x, y, "exit_channel")}" fill="none" stroke="${colors.orange}" stroke-width="2.2"/>`;
      svg += `<path d="${linePath(rows, x, y, "atr_stop_price")}" fill="none" stroke="${colors.red}" stroke-width="1.8" stroke-dasharray="4 4"/>`;
      const indexByDate = new Map(rows.map((row, index) => [row.trade_date, index]));
      result.trades.forEach(trade => {
        if (!indexByDate.has(trade.signal_date)) return;
        const index = indexByDate.get(trade.signal_date), row = rows[index], cx = x(index), cy = y(row.close);
        const color = trade.side === "BUY" ? colors.red : colors.green, label = trade.side === "BUY" ? "B" : "S";
        svg += `<circle cx="${cx}" cy="${cy}" r="6" fill="${color}"/><text x="${cx}" y="${cy + 3}" text-anchor="middle" font-size="8" fill="#fff" font-weight="700">${label}</text>`;
      });
      byId("turtlePriceChart").innerHTML = svg + "</svg>";
    }
    function renderNavChart(result) {
      const rows = result.rows;
      const w = 920, h = 330, x = xScale(rows.length, w), y = scale(rows.flatMap(row => [row.strategy_nav, row.benchmark_nav, 1 + row.excess_nav]), h);
      const excessRows = rows.map(row => ({...row, excess_line: 1 + row.excess_nav}));
      let svg = svgFrame(w, h);
      svg += `<path d="${linePath(rows, x, y, "strategy_nav")}" fill="none" stroke="${colors.blue}" stroke-width="2.5"/>`;
      svg += `<path d="${linePath(rows, x, y, "benchmark_nav")}" fill="none" stroke="${colors.teal}" stroke-width="2.3"/>`;
      svg += `<path d="${linePath(excessRows, x, y, "excess_line")}" fill="none" stroke="${colors.purple}" stroke-width="2" stroke-dasharray="5 5"/>`;
      byId("turtleNavChart").innerHTML = svg + "</svg>";
    }
    function renderMetrics(metrics) {
      if (metrics.error) {
        byId("turtleMetrics").innerHTML = `<div class="metric-card"><label>策略状态</label><strong>${metrics.error}</strong></div>`;
        return;
      }
      const items = [
        ["策略累计收益", fmtPct(metrics.strategy_return)], ["沪深300收益", fmtPct(metrics.benchmark_return)],
        ["超额收益", fmtPct(metrics.excess_return)], ["年化收益", fmtPct(metrics.annual_return)],
        ["年化波动", fmtPct(metrics.annual_volatility)], [`ATR(${metrics.atr_window})`, fmt(metrics.latest_atr, 3)],
        ["ATR/收盘价", fmtPct(metrics.latest_atr_pct)], ["最大回撤", fmtPct(metrics.max_drawdown)],
        ["夏普比率", fmt(metrics.sharpe_ratio, 2)], ["交易次数", metrics.trade_count],
        ["胜率", fmtPct(metrics.win_rate)], ["平均持仓天数", fmt(metrics.average_holding_days, 1)],
        ["总交易成本", fmtPct(metrics.total_cost)], ["ATR止损次数", metrics.atr_stop_count],
        ["风险/最大仓位", `${fmtPct(metrics.risk_per_trade)} / ${fmtPct(metrics.max_position)}`], ["突破/买入/跌破/卖出", `${metrics.entry_breakout_count}/${metrics.effective_buy_count}/${metrics.exit_breakout_count}/${metrics.effective_sell_count}`],
      ];
      byId("turtleMetrics").innerHTML = items.map(([label, value]) => `<div class="metric-card"><label>${label}</label><strong>${value}</strong></div>`).join("");
    }
    function renderTrades(trades) {
      byId("tradeTitle").textContent = `${trades.length} records`;
      byId("tradeRows").innerHTML = trades.length
        ? trades.map(trade => `<tr><td>${trade.signal_date}</td><td>${trade.trade_date}</td><td>${trade.side === "BUY" ? "买入" : "卖出"}</td><td>${trade.stop_reason || "-"}</td><td>${fmt(trade.price, 3)}</td><td>${fmt(trade.cost_rate, 7)}</td><td>${fmt(trade.nav_after, 4)}</td></tr>`).join("")
        : `<tr><td colspan="7">当前股票和策略版本下没有完成交易。</td></tr>`;
    }
    function renderDashboard() {
      syncTurtleWindows();
      const stock = APP_DATA.stocks.find(item => item.ts_code === byId("stockSelect").value) || APP_DATA.stocks[0];
      const result = computeTurtleStrategy(stock.rows), metrics = result.metrics;
      const settings = currentTurtleSettings();
      byId("stockName").textContent = stock.name; byId("stockCode").textContent = stock.ts_code;
      byId("variantName").textContent = `${settings.label} (${settings.entry_window}/${settings.exit_window})`; byId("alignedDays").textContent = metrics.aligned_days || result.rows.length || "-";
      byId("strategyReturnKpi").textContent = metrics.error ? "-" : fmtPct(metrics.strategy_return);
      byId("benchmarkReturnKpi").textContent = metrics.error ? "-" : fmtPct(metrics.benchmark_return);
      byId("drawdownKpi").textContent = metrics.error ? "-" : fmtPct(metrics.max_drawdown);
      byId("tradeCountKpi").textContent = metrics.error ? "-" : metrics.trade_count;
      renderMetrics(metrics); renderPriceChart(result); renderNavChart(result); renderTrades(result.trades);
    }
    function exportCsv() {
      const stock = APP_DATA.stocks.find(item => item.ts_code === byId("stockSelect").value) || APP_DATA.stocks[0];
      const header = Object.keys(stock.rows[0]).join(",");
      const body = stock.rows.map(row => Object.values(row).join(",")).join("\n");
      const blob = new Blob([header + "\n" + body], {type:"text/csv;charset=utf-8"});
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `${stock.name}_${stock.ts_code}_daily_2y.csv`; a.click(); URL.revokeObjectURL(a.href);
    }
    byId("stockSelect").addEventListener("change", renderDashboard);
    byId("variantSelect").addEventListener("change", applyVariantPreset);
    byId("entryWindow").addEventListener("input", renderDashboard);
    byId("exitWindow").addEventListener("input", renderDashboard);
    byId("stopMode").addEventListener("change", renderDashboard);
    byId("atrWindow").addEventListener("input", renderDashboard);
    byId("atrMultiplier").addEventListener("input", renderDashboard);
    byId("riskPerTrade").addEventListener("input", renderDashboard);
    byId("maxPosition").addEventListener("input", renderDashboard);
    byId("recalcBtn").addEventListener("click", renderDashboard);
    byId("exportBtn").addEventListener("click", exportCsv);
    renderDashboard();
  </script>
</body>
</html>
"""


INDEX_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="0; url=design/turtle_strategy_panel.html">
  <title>Task4 海龟策略量化看板</title>
</head>
<body>
  <p><a href="design/turtle_strategy_panel.html">打开 Task4 海龟策略量化看板</a></p>
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
    payload = build_payload_from_task3()
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(render_panel_html(payload), encoding="utf-8")
    INDEX_HTML.write_text(INDEX_TEMPLATE, encoding="utf-8")
    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_HTML}")
    print(f"Wrote {INDEX_HTML}")


if __name__ == "__main__":
    main()
