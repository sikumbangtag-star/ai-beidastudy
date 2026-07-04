# Task2 Spec: 金安国纪价格指标 Notebook

## 1. 任务目标

本任务使用 task1 已经获取过的金安国纪日线行情数据，计算并展示四类技术指标：

- RSI: 相对强弱指标
- MACD: 指数平滑异同移动平均线
- Bollinger Bands: 布林带
- ATR: 平均真实波幅

最终成果以 Jupyter Notebook 的形式呈现，要求能清楚展示数据读取、字段清洗、指标计算、图表展示和结果解释过程。

## 2. 文件归属规则

本项目按日期分为两个任务目录：

- `task1/`: 今天以前已经形成的全部项目文件和成果，包括 Tushare MCP、金安国纪 HTML 面板、历史 CSV 数据、GitHub Pages 配置等。
- `task2/`: 今天开始形成的全部新文件，包括本 spec、后续 notebook、指标计算代码、衍生数据和图表输出。

根目录保留 `.git/` 版本库目录，不移动到任务目录中。

## 3. 数据来源

本任务不重新调用 Tushare，也不重新拉取行情数据。

复用 task1 已有数据：

```text
task1/outputs/jinan_guoji/daily_prices.csv
```

该文件作为 task2 的只读原始数据源。后续如果需要保存清洗后的数据或指标结果，统一输出到：

```text
task2/data/
task2/outputs/
```

## 4. 目录规划

```text
task2/
  SPEC.md
  notebooks/
    jinan_guoji_indicators.ipynb
  src/
    indicators.py
  data/
    jinan_guoji_indicators.csv
  outputs/
    jinan_guoji_indicator_summary.md
    figures/
```

职责说明：

- `task2/SPEC.md`: 本任务规划文件。
- `task2/notebooks/jinan_guoji_indicators.ipynb`: 展示完整计算过程、图表和解释。
- `task2/src/indicators.py`: 封装 RSI、MACD、布林带、ATR 的计算函数，便于 notebook 调用和复核。
- `task2/data/jinan_guoji_indicators.csv`: 保存带指标列的日线数据。
- `task2/outputs/`: 保存图表、摘要和可交付结果。

## 5. 指标算法

### 5.1 RSI

默认参数：`period = 14`

计算步骤：

1. 计算收盘价变化量：

```text
delta = close_t - close_(t-1)
```

2. 拆分上涨和下跌：

```text
gain = max(delta, 0)
loss = max(-delta, 0)
```

3. 计算平均上涨和平均下跌。默认采用 Wilder 平滑方式：

```text
avg_gain = RMA(gain, 14)
avg_loss = RMA(loss, 14)
```

4. 计算 RSI：

```text
RS = avg_gain / avg_loss
RSI = 100 - 100 / (1 + RS)
```

输出列：

```text
rsi_14
```

主要作用：判断价格短期强弱和超买超卖状态。常见参考区间为 `RSI > 70` 偏热，`RSI < 30` 偏冷。

### 5.2 MACD

默认参数：`fast = 12`, `slow = 26`, `signal = 9`

计算步骤：

```text
ema_fast = EMA(close, 12)
ema_slow = EMA(close, 26)
dif = ema_fast - ema_slow
dea = EMA(dif, 9)
macd_hist = 2 * (dif - dea)
```

输出列：

```text
macd_dif
macd_dea
macd_hist
```

主要作用：判断趋势方向和动能变化。DIF 上穿 DEA 常被称为金叉，下穿称为死叉；柱状图放大通常表示动能增强。

### 5.3 布林带

默认参数：`window = 20`, `num_std = 2`

计算步骤：

```text
boll_mid = MA(close, 20)
boll_std = STD(close, 20)
boll_upper = boll_mid + 2 * boll_std
boll_lower = boll_mid - 2 * boll_std
boll_width = (boll_upper - boll_lower) / boll_mid
```

输出列：

```text
boll_mid
boll_upper
boll_lower
boll_width
```

主要作用：判断价格相对均值的位置、波动区间和波动率收缩或扩张。

### 5.4 ATR

默认参数：`period = 14`

计算步骤：

1. 计算真实波幅：

```text
tr = max(
  high - low,
  abs(high - previous_close),
  abs(low - previous_close)
)
```

2. 默认采用 Wilder 平滑：

```text
atr_14 = RMA(tr, 14)
```

输出列：

```text
tr
atr_14
```

主要作用：衡量波动幅度，不判断涨跌方向。可用于观察风险变化、设置止损距离和辅助仓位控制。

## 6. Notebook 展示结构

Notebook 采用教学型结构，读者可以顺着单元格理解每一步：

1. 任务说明和数据路径
2. 导入依赖
3. 读取 `task1/outputs/jinan_guoji/daily_prices.csv`
4. 标准化字段类型和交易日期排序
5. 检查缺失值、重复交易日和价格字段合理性
6. 计算 RSI、MACD、布林带、ATR
7. 保存带指标的数据到 `task2/data/jinan_guoji_indicators.csv`
8. 绘制价格与布林带图
9. 绘制成交量图
10. 绘制 RSI 图
11. 绘制 MACD 图
12. 绘制 ATR 图
13. 输出最近交易日的指标摘要
14. 写出简短结论和风险提示

## 7. 图表要求

Notebook 至少包含以下图表：

- 收盘价 + 布林带上轨/中轨/下轨
- 成交量柱状图
- RSI 折线图，并标出 70 和 30 参考线
- MACD DIF/DEA 折线图 + MACD 柱状图
- ATR 折线图

图表应统一使用中文标题和清晰坐标轴。若本地 matplotlib 中文字体不可用，允许在 notebook 中加入字体降级设置，保证代码能运行。

## 8. 数据质量和边界处理

实现时需要处理以下情况：

- 交易日期按升序排列后再计算指标。
- 数值字段转为浮点数，无法转换的值记为缺失。
- 指标计算前期窗口不足时允许出现空值。
- 如果缺少 `trade_date`、`open`、`high`、`low`、`close`、`vol` 中任意核心字段，notebook 应明确报错。
- 不修改 task1 的原始 CSV。

## 9. 验收标准

完成 task2 后，应满足：

- `task2/notebooks/jinan_guoji_indicators.ipynb` 可以从头运行到尾。
- 指标结果保存到 `task2/data/jinan_guoji_indicators.csv`。
- 图表能在 notebook 中正常显示。
- 最近交易日的 RSI、MACD、布林带、ATR 指标有摘要解释。
- task1 旧文件保持完整，仅作为历史数据和旧成果归档。

## 10. 风险提示

技术指标只能描述历史价格和波动特征，不能单独作为投资建议。Notebook 中的结论应使用“可能”“显示”“提示”等审慎表述，避免给出确定性买卖建议。
