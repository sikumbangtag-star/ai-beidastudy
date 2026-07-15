from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
TASK5 = ROOT / "task5"
OUTPUT_DIR = TASK5 / "outputs"
DESIGN_DIR = TASK5 / "design"
HTML_PATH = DESIGN_DIR / "ml_classification_panel.html"
INDEX_PATH = TASK5 / "index.html"


def build_payload() -> dict:
    payload = json.loads((OUTPUT_DIR / "eda_model_payload.json").read_text(encoding="utf-8"))
    predictions = pd.read_csv(OUTPUT_DIR / "model_predictions.csv")
    payload["roc_points"] = {}
    for model, group in predictions[predictions["split"] == "test"].groupby("model"):
        payload["roc_points"][model] = roc_points(group["Y"].to_numpy(), group["score"].to_numpy())
    payload["prediction_scores"] = {}
    for (model, split), group in predictions.groupby(["model", "split"]):
        payload["prediction_scores"].setdefault(model, {})[split] = [
            {"y": int(y), "score": round(float(score), 6)}
            for y, score in zip(group["Y"].to_numpy(), group["score"].to_numpy())
        ]
    return payload


def roc_points(y_true, score):
    pairs = sorted(zip(score, y_true), reverse=True)
    positives = max(1, sum(1 for _, y in pairs if y == 1))
    negatives = max(1, sum(1 for _, y in pairs if y == 0))
    tp = fp = 0
    points = [{"fpr": 0, "tpr": 0}]
    for _, y in pairs:
        if y == 1:
            tp += 1
        else:
            fp += 1
        points.append({"fpr": fp / negatives, "tpr": tp / positives})
    points.append({"fpr": 1, "tpr": 1})
    return points


HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Task5 机器学习分类模型面板</title>
  <style>
    * { box-sizing:border-box; }
    body { margin:0; background:#f5f7fb; color:#172033; font-family:"Microsoft YaHei",Arial,sans-serif; font-size:14px; letter-spacing:0; }
    header { min-height:64px; padding:14px 18px; background:#111827; color:#fff; display:flex; align-items:center; justify-content:space-between; gap:14px; }
    h1 { margin:0; font-size:19px; }
    header span { color:#cbd5e1; font-size:12px; }
    select { height:34px; border:1px solid #374151; border-radius:6px; background:#1f2937; color:#fff; padding:0 10px; font:inherit; }
    input[type="number"] { height:34px; width:88px; border:1px solid #cbd5e1; border-radius:6px; padding:0 8px; font:inherit; }
    input[type="range"] { width:min(520px,100%); accent-color:#2563eb; }
    main { width:min(1500px,100%); margin:0 auto; padding:14px; display:grid; gap:14px; }
    .grid { display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:14px; }
    .panel { min-width:0; background:#fff; border:1px solid #d9e0ea; border-radius:8px; padding:14px; }
    .span-3 { grid-column:span 3; } .span-4 { grid-column:span 4; } .span-5 { grid-column:span 5; } .span-6 { grid-column:span 6; } .span-7 { grid-column:span 7; } .span-8 { grid-column:span 8; } .span-12 { grid-column:span 12; }
    .title { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:10px; }
    .title h2 { margin:0; font-size:16px; color:#111827; }
    .muted { color:#687387; font-size:12px; }
    .kpi { display:grid; gap:6px; min-height:92px; }
    .kpi strong { font-size:25px; color:#111827; }
    .chart { height:300px; border:1px solid #edf0f5; border-radius:6px; overflow:hidden; }
    .chart.small { height:230px; }
    svg { width:100%; height:100%; display:block; background:#fff; }
    table { width:100%; border-collapse:collapse; font-size:12px; }
    th,td { padding:8px 7px; border-bottom:1px solid #edf0f5; text-align:right; white-space:nowrap; }
    th:first-child,td:first-child { text-align:left; }
    th { color:#4b5563; background:#f8fafc; }
    .heatmap { overflow:auto; }
    .heat-grid { display:grid; gap:2px; width:max-content; }
    .cell { width:32px; height:28px; display:grid; place-items:center; font-size:10px; color:#111827; border-radius:3px; }
    .control-row { display:flex; align-items:center; gap:14px; flex-wrap:wrap; }
    .control-row label { display:flex; align-items:center; gap:8px; }
    @media (max-width:980px) { .span-3,.span-4,.span-5,.span-6,.span-7,.span-8 { grid-column:span 12; } }
  </style>
</head>
<body>
  <script>const APP_DATA = __APP_DATA__;</script>
  <header>
    <div><h1>Task5 机器学习分类模型面板</h1><span>EDA、AUC、ROC、混淆矩阵、特征重要性</span></div>
    <label>选择模型 <select id="modelSelect"></select></label>
  </header>
  <main>
    <section class="grid">
      <div class="panel span-3 kpi"><span class="muted">当前模型</span><strong id="modelName">-</strong><span id="modelNote" class="muted">-</span></div>
      <div class="panel span-3 kpi"><span class="muted">测试集 AUC</span><strong id="testAuc">-</strong><span class="muted">越高表示排序能力越强</span></div>
      <div class="panel span-3 kpi"><span class="muted">验证集 AUC</span><strong id="validAuc">-</strong><span class="muted">用于模型比较</span></div>
      <div class="panel span-3 kpi"><span class="muted">测试集 F1</span><strong id="testF1">-</strong><span class="muted" id="thresholdHint">阈值 0.50</span></div>
    </section>

    <section class="panel">
      <div class="title"><h2>分类阈值</h2><span class="muted">AUC/ROC 不随阈值变化；混淆矩阵、准确率、精确率、召回率、F1 会实时更新</span></div>
      <div class="control-row">
        <label><span class="muted">阈值</span><input id="thresholdRange" type="range" min="0" max="1" step="0.01" value="0.50"></label>
        <label><input id="thresholdInput" type="number" min="0" max="1" step="0.01" value="0.50"></label>
        <span class="muted">score >= 阈值 判为 Y=1</span>
      </div>
    </section>

    <section class="grid">
      <div class="panel span-4"><div class="title"><h2>目标变量分布</h2><span class="muted">Y=0/1</span></div><div class="chart small" id="targetChart"></div></div>
      <div class="panel span-8"><div class="title"><h2>数据切分</h2><span class="muted">70% / 20% / 10%</span></div><div id="splitTable"></div></div>
    </section>

    <section class="grid">
      <div class="panel span-7"><div class="title"><h2 id="rocTitle">ROC 曲线</h2><span class="muted">测试集</span></div><div class="chart" id="rocChart"></div></div>
      <div class="panel span-5"><div class="title"><h2>混淆矩阵</h2><span class="muted" id="confusionSubTitle">测试集, 阈值 0.50</span></div><div class="chart" id="confusionChart"></div></div>
    </section>

    <section class="grid">
      <div class="panel span-6"><div class="title"><h2>特征重要性 / 系数贡献</h2><span class="muted">Top 12</span></div><div class="chart" id="importanceChart"></div></div>
      <div class="panel span-6"><div class="title"><h2>模型指标</h2><span class="muted">验证集与测试集</span></div><div id="metricsTable"></div></div>
    </section>

    <section class="panel">
      <div class="title"><h2>特征相关性矩阵</h2><span class="muted">全部特征</span></div>
      <div class="heatmap" id="corrHeatmap"></div>
    </section>
  </main>
  <script>
    const modelLabels = {
      linear_regression: "线性回归",
      logistic_regression: "逻辑回归",
      decision_tree: "决策树",
      random_forest: "随机森林"
    };
    const modelNotes = {
      linear_regression: "连续预测值裁剪到 0-1 后计算 AUC/ROC",
      logistic_regression: "线性分类模型, 输出正类概率",
      decision_tree: "单棵树模型, 非线性且可解释",
      random_forest: "集成树模型, 当前测试集 AUC 最高"
    };
    const byId = id => document.getElementById(id);
    const fmt = (v,d=4) => Number.isFinite(Number(v)) ? Number(v).toFixed(d) : "-";

    function setup() {
      byId("modelSelect").innerHTML = Object.keys(modelLabels).map(key => `<option value="${key}">${modelLabels[key]}</option>`).join("");
      byId("modelSelect").value = "random_forest";
      byId("modelSelect").addEventListener("change", renderModel);
      byId("thresholdRange").addEventListener("input", event => setThreshold(event.target.value));
      byId("thresholdInput").addEventListener("input", event => setThreshold(event.target.value));
      renderTarget();
      renderSplitTable();
      renderCorr();
      renderModel();
    }

    function currentThreshold() {
      const value = Number(byId("thresholdRange").value);
      return Math.min(1, Math.max(0, Number.isFinite(value) ? value : 0.5));
    }

    function setThreshold(value) {
      const threshold = Math.min(1, Math.max(0, Number(value)));
      if (!Number.isFinite(threshold)) return;
      const text = threshold.toFixed(2);
      byId("thresholdRange").value = text;
      byId("thresholdInput").value = text;
      renderModel();
    }

    function renderTarget() {
      const rows = APP_DATA.target_distribution;
      const max = Math.max(...rows.map(row => row.count));
      const bars = rows.map((row, i) => {
        const h = row.count / max * 170;
        const x = 130 + i * 170;
        return `<rect x="${x}" y="${210-h}" width="90" height="${h}" fill="${i ? "#2563eb" : "#94a3b8"}"/><text x="${x+45}" y="232" text-anchor="middle">Y=${row.label}</text><text x="${x+45}" y="${200-h}" text-anchor="middle">${row.count}</text>`;
      }).join("");
      byId("targetChart").innerHTML = `<svg viewBox="0 0 460 250"><line x1="58" y1="210" x2="430" y2="210" stroke="#d1d5db"/>${bars}</svg>`;
    }

    function renderSplitTable() {
      byId("splitTable").innerHTML = `<table><thead><tr><th>数据集</th><th>样本数</th><th>正样本比例</th><th>开始日期</th><th>结束日期</th></tr></thead><tbody>${APP_DATA.split_summary.map(row => `<tr><td>${row.split}</td><td>${row.n_samples}</td><td>${fmt(row.positive_rate, 4)}</td><td>${row.start_date}</td><td>${row.end_date}</td></tr>`).join("")}</tbody></table>`;
    }

    function metric(model, split) {
      return APP_DATA.metrics.find(row => row.model === model && row.split === split);
    }

    function renderModel() {
      const model = byId("modelSelect").value;
      const threshold = currentThreshold();
      const test = computeThresholdMetrics(model, "test", threshold);
      const valid = computeThresholdMetrics(model, "valid", threshold);
      const testBase = metric(model, "test"), validBase = metric(model, "valid");
      byId("modelName").textContent = modelLabels[model];
      byId("modelNote").textContent = modelNotes[model];
      byId("testAuc").textContent = fmt(testBase.auc);
      byId("validAuc").textContent = fmt(validBase.auc);
      byId("testF1").textContent = fmt(test.f1);
      byId("thresholdHint").textContent = `阈值 ${threshold.toFixed(2)}`;
      byId("confusionSubTitle").textContent = `测试集, 阈值 ${threshold.toFixed(2)}`;
      byId("rocTitle").textContent = `${modelLabels[model]} ROC 曲线`;
      renderRoc(model);
      renderConfusion(test);
      renderImportance(model);
      renderMetrics(model, valid, test);
    }

    function computeThresholdMetrics(model, split, threshold) {
      const rows = (((APP_DATA.prediction_scores || {})[model] || {})[split] || []);
      let tp = 0, fp = 0, tn = 0, fn = 0;
      rows.forEach(row => {
        const pred = Number(row.score) >= threshold ? 1 : 0;
        const actual = Number(row.y);
        if (pred === 1 && actual === 1) tp += 1;
        else if (pred === 1 && actual === 0) fp += 1;
        else if (pred === 0 && actual === 0) tn += 1;
        else fn += 1;
      });
      const n = rows.length || 1;
      const precision = tp + fp ? tp / (tp + fp) : 0;
      const recall = tp + fn ? tp / (tp + fn) : 0;
      const f1 = precision + recall ? 2 * precision * recall / (precision + recall) : 0;
      return {
        split,
        auc: metric(model, split).auc,
        accuracy: (tp + tn) / n,
        precision,
        recall,
        f1,
        tp,
        fp,
        tn,
        fn
      };
    }

    function renderRoc(model) {
      const points = APP_DATA.roc_points[model] || [];
      const mapPoint = p => [58 + p.fpr * 380, 238 - p.tpr * 190];
      const path = points.map((p, i) => `${i ? "L" : "M"} ${mapPoint(p)[0].toFixed(1)} ${mapPoint(p)[1].toFixed(1)}`).join(" ");
      byId("rocChart").innerHTML = `<svg viewBox="0 0 480 300"><line x1="58" y1="238" x2="438" y2="238" stroke="#d1d5db"/><line x1="58" y1="48" x2="58" y2="238" stroke="#d1d5db"/><line x1="58" y1="238" x2="438" y2="48" stroke="#cbd5e1" stroke-dasharray="5 5"/><path d="${path}" fill="none" stroke="#2563eb" stroke-width="3"/><text x="250" y="278" text-anchor="middle">FPR</text><text x="18" y="150" transform="rotate(-90 18 150)" text-anchor="middle">TPR</text></svg>`;
    }

    function renderConfusion(m) {
      const cells = [
        ["TN", m.tn, "#dbeafe"], ["FP", m.fp, "#fee2e2"],
        ["FN", m.fn, "#ffedd5"], ["TP", m.tp, "#dcfce7"],
      ];
      byId("confusionChart").innerHTML = `<svg viewBox="0 0 420 300">${cells.map((c,i) => { const x = 80 + (i%2)*140, y = 60 + Math.floor(i/2)*100; return `<rect x="${x}" y="${y}" width="120" height="80" rx="6" fill="${c[2]}" stroke="#e5e7eb"/><text x="${x+60}" y="${y+32}" text-anchor="middle" font-weight="700">${c[0]}</text><text x="${x+60}" y="${y+58}" text-anchor="middle" font-size="20">${c[1]}</text>`; }).join("")}<text x="210" y="30" text-anchor="middle">预测类别</text><text x="34" y="155" transform="rotate(-90 34 155)" text-anchor="middle">真实类别</text></svg>`;
    }

    function renderImportance(model) {
      const rows = APP_DATA.feature_importance.filter(row => row.model === model).sort((a,b) => b.importance - a.importance).slice(0, 12);
      const max = Math.max(...rows.map(row => row.importance), 0.0001);
      byId("importanceChart").innerHTML = `<svg viewBox="0 0 720 320">${rows.map((row, i) => { const y = 20 + i*24, w = row.importance / max * 390; return `<text x="8" y="${y+14}" font-size="11">${row.feature.slice(0,22)}</text><rect x="230" y="${y}" width="${w}" height="16" fill="#2563eb"/><text x="${240+w}" y="${y+13}" font-size="11">${fmt(row.importance,3)}</text>`; }).join("")}</svg>`;
    }

    function renderMetrics(model, valid, test) {
      const rows = [valid, test];
      byId("metricsTable").innerHTML = `<table><thead><tr><th>数据集</th><th>AUC</th><th>准确率</th><th>精确率</th><th>召回率</th><th>F1</th></tr></thead><tbody>${rows.map(row => `<tr><td>${row.split}</td><td>${fmt(row.auc)}</td><td>${fmt(row.accuracy)}</td><td>${fmt(row.precision)}</td><td>${fmt(row.recall)}</td><td>${fmt(row.f1)}</td></tr>`).join("")}</tbody></table>`;
    }

    function renderCorr() {
      const cols = APP_DATA.correlation_matrix.columns;
      const vals = APP_DATA.correlation_matrix.values;
      const grid = [`<div class="heat-grid" style="grid-template-columns:120px repeat(${cols.length},32px)">`];
      grid.push(`<div></div>${cols.map(c => `<div class="cell" title="${c}">${c.slice(0,2)}</div>`).join("")}`);
      vals.forEach((row, i) => {
        grid.push(`<div class="cell" style="width:120px;justify-content:start" title="${cols[i]}">${cols[i].slice(0,12)}</div>`);
        row.forEach(v => {
          const red = v > 0 ? 255 : Math.round(255 * (1 + v));
          const blue = v < 0 ? 255 : Math.round(255 * (1 - v));
          const green = Math.round(245 * (1 - Math.abs(v)));
          grid.push(`<div class="cell" title="${v}" style="background:rgb(${red},${green},${blue})">${Math.abs(v) > .65 ? v.toFixed(1) : ""}</div>`);
        });
      });
      grid.push("</div>");
      byId("corrHeatmap").innerHTML = grid.join("");
    }

    setup();
  </script>
</body>
</html>
"""


INDEX_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="0; url=design/ml_classification_panel.html">
  <title>Task5 机器学习分类模型面板</title>
</head>
<body>
  <p><a href="design/ml_classification_panel.html">打开 Task5 机器学习分类模型面板</a></p>
</body>
</html>
"""


def main() -> None:
    DESIGN_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_payload()
    HTML_PATH.write_text(
        HTML_TEMPLATE.replace("__APP_DATA__", json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
        encoding="utf-8",
    )
    INDEX_PATH.write_text(INDEX_TEMPLATE, encoding="utf-8")
    print(HTML_PATH)
    print(INDEX_PATH)


if __name__ == "__main__":
    main()
