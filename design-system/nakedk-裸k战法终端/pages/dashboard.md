# Page Override — `dashboard`（NakedK 主界面）

> 本文件**覆盖** `../MASTER.md`。仅记录本页与 Master 的差异与专有约定。

---

## 本页结构

```
┌─ fixed header (top-4 left-4 right-4, z-40) ────────────────────────────┐
│  brand · 搜索框(带联想) · 交易时段指示灯 · 刷新 · 复制报告              │
└────────────────────────────────────────────────────────────────────────┘
main (max-w-shell=1680, pt-28)
  ├─ [错误横幅 / 按需]
  └─ grid lg:grid-cols-[276px_minmax(0,1fr)]
       ├─ aside  lg:sticky lg:top-28
       │    ├─ WATCHLIST 面板（与 cron 共用 watchlist.txt，可增删）
       │    └─ DATA 面板（数据源 / 引擎版本 / 理念声明）
       └─ section#stage
            ├─ #empty   空态（首次进入）
            ├─ #loading 骨架屏
            └─ #report  标头卡 → 图表卡 → [M1 M2] → [M3 M4] → [M6 自检]
```

## 与 Master 的差异

### 1. 图表是本页的核心，不是"配图"

- 库：**lightweight-charts v4.2**（TradingView），本地 vendored 到
  `web/vendor/lightweight-charts.js`（163KB），不依赖 CDN 在线。
- 蜡烛配色：`upColor #F6465D` / `downColor #0ECB81`（红涨绿跌，覆盖 Master 的
  西方惯例色，理由见 Master 「偏离 1」）。
- 成交量画在**同一 pane**（`priceScaleId:'vol'` + `scaleMargins.top:0.82`），
  不用独立 sub-pane，省 30% 纵向空间；透明度 32% —— 符合"成交量仅作背景验证"。
- **默认视野 90 根**，不是 `fitContent()`。踩坑：250 根全塞进视野时价格区间被
  拉到 8 个价位，冰线/供应区/需求区全被压成发丝，标注失去意义。工具栏提供
  60 / 90 / 180 / 全部。

### 2. 价位标注：自绘「价位梯」取代原生轴标签

**踩坑（必须保留的结论）**：lightweight-charts 的 `createPriceLine({axisLabelVisible:true})`
在 A 股这种密集价位下必然叠字 —— 冰线 15.20 与剧本A触发 15.21 只差 0.7px。
因此本项目：

- 所有 priceLine 一律 `axisLabelVisible:false, title:''`；
- 在 `#ladder` 覆盖层里**自己按像素位置做去重叠**（最小间距 15px，被推开的
  条目补一条 `u` 锚线指回真实价位）；
- 区间带（供应区/需求区）用 `priceToCoordinate()` 在 `#bands` 层画
  `position:absolute` 的 div，带 10% 填充 + 上下沿描边；
- 区间带标签贴**左**，价位梯贴**右**，避免同一水平带里抢位。

### 3. 移动端压缩策略

`@media (max-width: 767px)`：价位梯隐藏名称只留色块+价格（113px → 55px，
从占图表 1/3 收到 1/6），区间带标签字号降到 8.5px。名称信息由图例 chips 承担。

### 4. 键盘操作

| 键 | 行为 |
|----|------|
| `/` | 聚焦搜索 |
| `↑` `↓` | 联想列表上下选 |
| `Enter` | 分析选中项 |
| `Esc` | 关闭联想 / 退出「添加自选」模式 |
| `R` | 重新拉取当前标的 |

### 5. 状态与错误

- 所有 fetch 失败走顶部橙色横幅（9s 自动消失），不静默失败。
- `render()` 抛异常会被 `analyze()` 的 catch 兜住并显示横幅 —— 因为
  **图标容器必须先可见再挂载图表**：`display:none` 下容器尺寸 0，
  lightweight-charts 会创建 0×0 canvas 且不会自愈（已踩）。
  现用 `if (!el.clientWidth) requestAnimationFrame(retry)` 加固。

### 6. 本页不做的事（诚实边界）

- 不加任何技术指标（产品定义）。
- 不做浅色模式。
- 不做分时图 / 盘中动态修正的图形化（模块五只出文字结论）。
- 不做多标的并排对比（cron 报告里已有）。
