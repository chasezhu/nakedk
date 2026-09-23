# NakedK 裸K战法终端

裸K（Price Action）五模块分析的可视化终端。**纯价格行为，不使用任何技术指标**
（无 MACD / KDJ / RSI / 布林带 / 均线 / 资金流），只吃 OHLC + 时间序列位置。

配套技能：[`naked-kline-analyst`](../../.hermes/skills/note-taking/naked-kline-analyst/SKILL.md)
UI 设计系统：[`ui-ux-pro-max`](../../.opencode/skills/ui-ux-pro-max/SKILL.md)

---

## 30 秒跑起来

```bash
cd ~/nakedk
./run.sh bg          # 后台启动 → http://127.0.0.1:8600
./run.sh start       # 或前台启动（Ctrl+C 退出）
./run.sh stop        # 停止
```

不需要 npm install、不需要构建、不需要 API key。前端依赖已 vendored 到
`web/vendor/`（lightweight-charts 163KB + tailwind 451KB），**断网也能打开**。

---

## 架构

```
浏览器
  └─ web/  (零构建单页: index.html + app.js + styles.css + vendor/)
        │  fetch /api/*
        ▼
  server.py   FastAPI · 6 个端点 · 静态资源
        │
        ├── engine/datasource.py   腾讯财经(主) / TickFlow(备) · 符号解析 · 实时快照
        ├── engine/analyzer.py     五模块规则引擎 v2.0.0（确定性，无 LLM）
        └── engine/history.py      分析落盘 ~/.nakedk/history/ → 驱动模块六
```

**为什么规则引擎放 Python 而不是写进 JS**：同一份引擎同时喂这个前端和 17:00 的
cron 报告，改一次两边生效。前端是纯展示层，不做任何判断。

### 数据源

| 源 | 用途 | 说明 |
|----|------|------|
| `smartbox.gtimg.cn` | 名称/代码搜索 | 支持拼音、中文、6位代码 |
| `web.ifzq.gtimg.cn` | 日K（前复权） | 90~400 根，实测 `CORS: *` |
| `qt.gtimg.cn` | 实时快照 | GBK 编码，含今日 OHLC / 涨跌幅 / 换手 |
| TickFlow | 备源 | 免费版滞后 1-2 个自然日，仅腾讯全线失败时启用 |

### API

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/health` | 引擎版本 / watchlist 路径 / 是否盘中 |
| GET | `/api/search?q=` | 联想搜索 |
| GET | `/api/analyze?q=&days=` | 完整分析（含 250 根 bars + 图表标注 + 六模块） |
| GET | `/api/kline?symbol=&count=` | 只要K线 |
| GET | `/api/watchlist` | 自选股 + 实时行情 |
| POST | `/api/watchlist` | `{action:add\|remove, query}`，直接写回 watchlist.txt |
| GET | `/api/history?symbol=` | 轻量历史（供时间线） |

---

## 五模块 + 事后验证

| 模块 | 内容 |
|------|------|
| 一 K线解剖 | 实体占比 / 上下影线含义 / 跳空 / 收盘位置 / 一句话定性 |
| 二 背景定位 | 60日阶段位置（极高位~极低位）/ 趋势判定 / K线定性 / 背景修正 |
| 三 关键价位 | **冰线**（四级优先级）/ 供应区 / 需求区（12根局部极值聚类） |
| 四 次日验证剧本 | A/B/C 三剧本触发价 + 概率（含边界极性化与阴线修正）+ 止损反推 |
| 五 盘中动态修正 | 仅盘中可用：现价相对三个触发价，判定当前活跃剧本 |
| 六 **事后验证** | 用真实后续K线回测上轮主剧本是否兑现 + 冰线是否被破 |

### 模块六怎么用

每次**收盘后**分析都会自动落盘。想立刻看到效果，用回算工具把历史补上：

```bash
./run.sh backfill 300768 --days 20      # 单只，回算 20 个交易日
./run.sh backfill --watchlist --days 15 # 全部自选股
```

它是**机械回放**：第 d 日只喂 `date <= d` 的K线，与当日真实运行完全等价，
冰线优先级和成交量均量窗口都看不到未来数据 —— 不是前视优化。

---

## ⚠️ 相对 v3 的 3 个 bug 修复（有证据）

移植自 `~/.hermes/tmp/naked_kline_v3.py` 时的三处修正。**用 `./run.sh ab` 可复现**：

### FIX-1 冰线优先级1 搜索方向（严重）

v3 用**正序**（旧→新）扫描，会选到更早的旧标志性K线，与技能文档「坑1」冲突。

```
$ ./run.sh ab 300768 2026-08-14
标的 迪普科技(sz300768)  截面日期 2026-08-14  收盘 16.47
v3 正序(旧->新)   -> 冰线 15.32  2026-07-31(阳线, 实体76.2%, 量1.53x)  偏离 7.51%
本版 倒序(新->旧) -> 冰线 16.51  2026-08-06(阳线, 实体98.9%, 量1.36x)  偏离 0.24%
```

v3 用一段"若 C > 冰线×1.03 则改用近5日最低收盘价"的隐式改写掩盖了这个问题，
所以线上没暴雷。本版按文档倒序搜索，并删掉隐式改写。

### FIX-2 成交量基准错位（中等）

v3 用固定的「今日前5日均量」去比较任意历史第 i 根，越往前越失真。
本版改为滚动窗口 `mean(bars[i-5:i])`，逐根对齐。

### FIX-3 冰线优先级 3/4 缺失（中等）

v3 只有 P1/P2。本版补全 P3（震荡平台下沿）/ P4（跳空缺口起点），
并加 12% 偏离闸门 —— 候选超闸门则降级到下一优先级，被拒原因写进 `warnings`。

---

## 开发

```bash
./run.sh smoke 300768              # 引擎自检，打印全部字段
./run.sh ab 300768 2026-08-14      # 冰线正序/倒序 A/B
./run.sh backfill --watchlist      # 历史回算落盘
python3 dev/contract.py            # 输出契约回归（10 标的 × 全字段断言）
python3 dev/purge_intraday.py --dry-run   # 查脏历史快照
```

`dev/contract.py` 的存在理由：开发中曾用整段 patch 串联函数，一处 `old_string`
跨了函数边界，把 `playbook.corrections` 静默吃掉，前端直接白屏。这个测试把
输出契约钉死。

---

## 已知边界（诚实声明）

1. **不含节假日日历**。`is_trading_now()` 只看星期与时段，法定假日会误判为盘中。
2. **盘中不落盘**。当日K线未收盘定格时（含午休、盘前）分析不写入历史，
   否则次日事后验证会拿半截K线当基准。收盘后重新分析才进入验证链路。
3. **6 位代码有歧义**。`000001` 同时是深市平安银行和沪市上证指数，默认取股票，
   界面上给出切换 chip。注意技能文档写的是"000001 → 上证指数"，与此不同。
4. **冰线是阻力时不做止损反推**。文档写"看涨→止损=冰线×1.01"，但若冰线来自
   大阴线开盘且高于现价，它是阻力不是支撑，此时 ×1.01 无意义。本版只标注
   `role`，不改写数值 —— 这条规则要不要成文，待定。
5. **单进程、无鉴权、只监听 127.0.0.1**。要暴露到局域网需自行加反向代理与认证。
6. **不含 TradingView 归属移除**。`lightweight-charts` 为 Apache-2.0，
   图表左下角的 TradingView 标识保留以符合许可要求。

---

## 目录

```
nakedk/
├── run.sh                    启动/停止/自检/回算
├── server.py                 FastAPI 服务
├── engine/
│   ├── datasource.py         取数 + 符号解析
│   ├── analyzer.py           五模块规则引擎 v2.0.0
│   └── history.py            分析落盘
├── web/
│   ├── index.html  app.js  styles.css
│   └── vendor/               lightweight-charts.js + tailwind.js（本地化）
├── dev/
│   ├── smoke.py              引擎自检
│   ├── ab_ice.py             冰线 A/B
│   ├── backfill.py           历史回算
│   ├── contract.py           输出契约回归
│   └── purge_intraday.py     清理脏历史
└── design-system/
    └── nakedk-裸k战法终端/
        ├── MASTER.md         设计系统（含生成器输出勘误）
        └── pages/dashboard.md 本页覆盖 + 踩坑记录
```

数据落盘位置：`~/.nakedk/history/<symbol>.json`（可用 `NAKEDK_HOME` 覆盖）
自选股文件：`~/.nakedk/watchlist.txt` ← **唯一真实数据**（同属数据根，可用 `NAKEDK_WATCHLIST` 指向别处）

- 前端增删会直接写回该文件；仓库自带 `watchlist.example`，换台电脑 clone 后
  首次启动会自动播种（迁移旧路径 → 播种 example → 建空表，三级兜底）。
- 与 17:00 cron 日报共用同一份：`~/.hermes/skills/note-taking/naked-kline-analyst/watchlist.txt`
  现在是指向 `~/.nakedk/watchlist.txt` 的**软链**，两边永远一致、不会分叉。
