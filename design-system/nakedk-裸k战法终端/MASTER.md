# Design System Master File — NakedK 裸K战法终端

> **LOGIC:** 构建具体页面时先看 `design-system/nakedk-裸k战法终端/pages/[page].md`。
> 该文件存在则**覆盖**本 Master 文件；否则严格遵循下列规则。

---

**Project:** NakedK 裸K战法终端
**Source:** `ui-ux-pro-max` skill, `--design-system` + `--persist`
**Category:** Financial Dashboard (data-dense trading terminal)
**Updated:** 2026-09-23（人工修订，见文末「生成器输出勘误」）

---

## ⚠️ 生成器输出勘误（必读）

`search.py --design-system` 单次调用只返回**一个**匹配，且不同关键词会命中互相
矛盾的结果。本项目跑了两次查询，两次结论冲突，必须人工裁决：

| 查询 | Style | 配色 | 结论 |
|------|-------|------|------|
| `stock trading dashboard fintech terminal dark` | Dark Mode (OLED) | 底 `#020617`、面 `#0F172A`、CTA `#22C55E`、文字 `#F8FAFC` | ✅ 采纳 |
| `... --persist -p "NakedK"` | Dark Mode (OLED) | 底 `#F8FAFC`、Primary `#1E40AF`、CTA `#F59E0B`、文字 `#1E3A8A` | ❌ 否决 |

第二次输出的配色是**浅色**的，却同时声明 Style = "Dark Mode (OLED)"，自相矛盾。
凡遇此种情况，以 **Style 字段**为准裁决配色（风格是用户诉求，配色是生成器的推断）。

生成器另外两处不可直接采用：

1. **Page Pattern = "Horizontal Scroll Journey"** —— 这是营销落地页模式
   （1. Intro → 2. Horizontal Track → 3. Detail Reveal → 4. Footer），
   对数据看板无意义。本项目用「侧栏 + 主区 + 卡片网格」的终端壳层。
2. **组件规范里 `.btn-primary:hover { transform: translateY(-1px) }`** —— 违反本技能
   自己的 Anti-Pattern 规则「Layout-shifting hovers — Avoid scale transforms」。
   采纳规则，否决样例代码：本项目 hover 只改 color / background-color / border-color。

---

## Global Rules

### Color Palette（实际实现值）

| Role | Hex | Tailwind token | 用途 |
|------|-----|----------------|------|
| Background | `#020617` | `bg-bg` | OLED 深黑底 |
| Surface | `#0F172A` | `bg-surface` | 面板 |
| Surface 2 | `#1E293B` | `bg-surface2` | 输入框 / 次级块 |
| Border | `#334155` | `border-line` | 可见描边 |
| Border (soft) | `#1E293B` | `border-lineSoft` | 面板内分隔 |
| Text | `#F8FAFC` | `text-ink` | 正文 |
| Text (muted) | `#94A3B8` | `text-muted` | 次级文字 |
| Text (dim) | `#64748B` | `text-dim` | 说明 / 元信息 |
| Accent | `#38BDF8` | `text-accent` | 交互态（焦点 / 选中 / 链接） |
| **涨 (up)** | `#F6465D` | `text-up` | 阳线 / 上涨 |
| **跌 (down)** | `#0ECB81` | `text-down` | 阴线 / 下跌 |

**语义色（专供图表标注，不得挪作他用）**

| 标注 | Hex | 线型 |
|------|-----|------|
| 冰线 | `#38BDF8` | dashed |
| 供应区 | `#F6465D` | 10% 填充带 + 上下沿 |
| 需求区 | `#0ECB81` | 10% 填充带 + 上下沿 |
| 剧本A触发 | `#FBBF24` | dotted |
| 剧本C触发 | `#FB923C` | dotted |
| 止损/压力 | `#A78BFA` | large-dashed |

> **偏离 1（已裁决）：CTA 由 `#22C55E` 改为 `#38BDF8`。**
> 理由：A 股语义是**红涨绿跌**，绿色必须专属"下跌"。若 CTA 用绿，页面上
> "确认/主操作"与"跌幅/阴线"会同色，是真实的可读性缺陷。
> 补充裁决：生成器给的西方惯例（Bullish `#26A69A` / Bearish `#EF5350`）
> 对中国股票终端**不可用**，一律红涨绿跌。交互色改用青色，与价格色正交。

### Typography

- **数值 / 代码:** Fira Code（`font-mono`，开 `tabular-nums`，防止数字跳动）
- **正文 / 标题:** Fira Sans（`font-sans`）
- **中文回退:** Noto Sans SC → PingFang SC → Microsoft YaHei
- **Mood:** dashboard, data, analytics, code, technical, precise
- **加载:** Google Fonts，`display=swap`

### Spacing / Radius / Shadow

| Token | Value | 用途 |
|-------|-------|------|
| `--space-xs` | 4px | 紧贴间距 |
| `--space-sm` | 8px | 图标间距 |
| `--space-md` | 16px | 标准内边距 |
| `--space-lg` | 24px | 区块间距 |
| radius 面板 | 16px (`rounded-2xl`) | 面板 |
| radius 控件 | 8–10px | 按钮 / 输入框 |
| shadow | `0 22px 48px -14px rgba(0,0,0,.85)` | 下拉浮层 |

深色底上**不用**浅色阴影做层级，改用描边（`border-line`）+ 背景明度差
（`#020617` → `#0F172A` → `#1E293B`）。

### Key Effects

低强度环境光辉光（`radial-gradient`，透明度 5–10%）、150–250ms 颜色过渡、
`backdrop-blur` 仅用于顶栏与下拉、**不做大面积白、不做 glow 动画**。

---

## Component Specs（实际值，非生成器样例）

```css
/* 面板 */
.panel { border-radius: 1rem; border: 1px solid #1E293B;
         background: rgba(15,23,42,.70); backdrop-filter: blur(6px); }

/* 图标按钮：hover 只改色，不位移 */
.icon-btn { height: 2.25rem; width: 2.25rem; border-radius: .625rem;
            border: 1px solid rgba(51,65,85,.75); background: rgba(30,41,59,.55);
            color: #94A3B8; cursor: pointer;
            transition: color .18s ease, border-color .18s ease, background-color .18s ease; }
.icon-btn:hover { color: #38BDF8; border-color: rgba(56,189,248,.5); background: rgba(56,189,248,.10); }

/* 自选股行 */
.wl-item { padding: .6rem .85rem; border-left: 2px solid transparent; cursor: pointer;
           transition: background-color .16s ease, border-color .16s ease; }
.wl-item[data-active="1"] { background: rgba(56,189,248,.11); border-left-color: #38BDF8; }

/* 焦点可见（键盘导航） */
a:focus-visible, button:focus-visible, input:focus-visible, [tabindex]:focus-visible {
  outline: 2px solid #38BDF8; outline-offset: 2px;
}

/* 骨架屏（加载反馈，禁止空白冻结） */
.skeleton { background: linear-gradient(90deg,#1E293B8C 0%,#334155BF 50%,#1E293B8C 100%);
            background-size: 200% 100%; animation: sk 1.5s ease-in-out infinite; }
```

---

## Style Guidelines

**Style:** Dark Mode (OLED)
**Keywords:** dark theme, low light, high contrast, deep black, midnight blue,
eye-friendly, OLED, night mode, power efficient
**Key Effects:** minimal glow, low white emission, high readability, visible focus

### Page Pattern（替换生成器的落地页模式）

数据终端壳层：**浮动顶栏（top-4 / left-4 / right-4） → 侧栏（自选股，sticky）
→ 主区（标的标头 → K线图 → 六模块卡片网格）→ 页脚免责**

- 导航常驻可见 ✅
- 信息密度优先，但用卡片分组 + 留白防止拥挤 ✅
- 移动端：侧栏下移、模块网格单列 ✅

---

## Anti-Patterns (Do NOT Use)

- ❌ Light mode default
- ❌ Slow rendering
- ❌ Emojis as icons — 一律 Lucide SVG
- ❌ Missing `cursor:pointer`
- ❌ Layout-shifting hovers（含生成器自己样例里的 `translateY(-1px)`）
- ❌ Low contrast text（正文 ≥ 4.5:1）
- ❌ Instant state changes（必须 150–300ms 过渡）
- ❌ Invisible focus states
- ❌ **A股终端里用绿色表示上涨**（语义冲突）
- ❌ **把技术指标画进裸K图**（KDJ/MACD/均线一律不加，这是产品定义不是审美）

---

## Pre-Delivery Checklist

- [x] 无 emoji 图标，全部 Lucide SVG（24×24 固定 viewBox）
- [x] 图标集一致
- [x] 所有可点击元素 `cursor:pointer`
- [x] Hover 150–250ms 过渡且不引起布局位移
- [x] 深色模式文字对比度 ≥ 4.5:1（正文 `#F8FAFC` / 次级 `#94A3B8` / 说明 `#64748B`）
- [x] 焦点态可见（2px accent outline）
- [x] `prefers-reduced-motion` 已降级动画
- [x] 响应式：375 / 768 / 1024 / 1440 实测通过（375px 与 768px 零横向溢出）
- [x] 无内容被固定顶栏遮挡（`pt-28`，顶栏包裹后实测高 64–112px）
- [x] 移动端无横向滚动
- [x] 加载态有骨架屏（`animate-pulse` 等价物）
- [ ] **浅色模式未实现** —— 本项目只做暗色（终端场景），若日后要浅色需重新取
      配色并单独验证玻璃卡不透明度（生成器已提示 `bg-white/80` 起）
