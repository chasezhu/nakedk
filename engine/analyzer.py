#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""裸K战法 · 六模块规则引擎

严格移植 ~/.hermes/tmp/naked_kline_v3.py，并在移植中修掉 3 个已知缺陷：

[FIX-1] 冰线优先级1 搜索方向
    v3: for i in range(max(0,n-15), n-1)  -> 正序（旧 -> 新），会选到更早的旧标志性K线
    本版: for i in range(n-2, start-1, -1) -> 倒序（新 -> 旧），取最近一根
    依据: naked-kline-analyst 技能「坑1」。迪普科技案例：正序选 7/31 开盘 15.32（偏离 7.5%），
          倒序正确选 8/6 光头大阳开盘 16.51（实体 98.9%，距当前 6 日，偏离 0.2%）。

[FIX-2] 成交量基准错位
    v3: vol_ma5 = mean(bars[-2..-6])，即"今日前5日均量"，却拿去和历史第 i 根比
    本版: _vol_ma5_before(bars, i) = mean(bars[i-5:i])，滚动窗口，逐根对齐

[FIX-3] 冰线优先级3/4 缺失
    v3: 只有 P1/P2，且 P1 失效后有一段"若 C > 冰线*1.03 则改用近5日最低收盘价"的隐式改写，
        会静默覆盖 P1 结果，与技能文档的优先级体系冲突
    本版: 按文档实现 P1 -> P2 -> P3(震荡平台下沿) -> P4(跳空缺口起点)，
          每级都过偏离闸门 (|C-level|/level > 12% 视为不可用，降级到下一级)

新增（v3 没有）:
    - 模块六 事后验证：读取本地历史，用真实后续K线判定上轮剧本是否兑现
    - 结构化 levels 输出，供前端图表直接画线
    - 板块/指数通用（不再假设是股票）

禁止使用任何技术指标（MACD/KDJ/RSI/均线/资金流）。仅使用 OHLC + 时间位置。
"""

from __future__ import annotations

from datetime import date, datetime

ENGINE_VERSION = "2.0.2"
ICE_MAX_DEV = 12.0  # 冰线偏离闸门(%)，超过则降级到下一优先级

# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #


def _pct(x: float, base: float) -> float:
    return (x - base) / base * 100 if base else 0.0


def _local_peaks(series: list[float], higher: bool = True) -> list[float]:
    out = []
    for i in range(1, len(series) - 1):
        if higher and series[i] > series[i - 1] and series[i] > series[i + 1]:
            out.append(series[i])
        elif not higher and series[i] < series[i - 1] and series[i] < series[i + 1]:
            out.append(series[i])
    return out


def _vol_ma5_before(bars: list[dict], i: int) -> float:
    """第 i 根K线之前 5 根的平均量。FIX-2：滚动窗口，不再用固定的"今日前5日"。"""
    win = bars[max(0, i - 5): i]
    if not win:
        return 0.0
    return sum(b["vol"] for b in win) / len(win)


def _entity_pct(bar: dict) -> float:
    span = bar["high"] - bar["low"]
    return abs(bar["close"] - bar["open"]) / span * 100 if span > 0 else 0.0


def _date_key(d) -> date | None:
    """把日期解析成 datetime.date 用于可靠比较；失败返回 None 以便回退字符串比较。"""
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    s = str(d)
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------- #
# 模块一：K线解剖
# --------------------------------------------------------------------------- #

def _module1(bars: list[dict]) -> dict:
    t, prev = bars[-1], bars[-2]
    O, H, L, C = t["open"], t["high"], t["low"], t["close"]
    span = H - L
    chg = _pct(C, prev["close"])

    ep = _entity_pct(t)
    if ep > 70:
        ec = "大阳线" if C > O else "大阴线"
    elif ep > 40:
        ec = "中阳线" if C > O else "中阴线"
    elif ep < 20:
        ec = "十字星/小实体"
    else:
        ec = "小阳线" if C > O else "小阴线"

    upper, lower = H - max(O, C), min(O, C) - L
    up = upper / span * 100 if span > 0 else 0.0
    lp = lower / span * 100 if span > 0 else 0.0

    if up > 40:
        um = "上方供应强劲"
    elif up > 30 and C > O:
        um = "多头遇阻"
    elif span > 0 and upper / span < 0.01:
        um = "光头无压力"
    else:
        um = "正常"

    if lp > 40:
        lm = "下方承接强劲"
    elif lp > 30 and C < O:
        lm = "空头有抵抗"
    elif span > 0 and lower / span < 0.01:
        lm = "光脚无承接"
    else:
        lm = "正常"

    gp = _pct(O, prev["close"])
    if gp > 1:
        gc = "跳空高开"
    elif gp < -1:
        gc = "跳空低开"
    elif abs(gp) < 0.3:
        gc = "平开"
    elif gp > 0:
        gc = "小幅高开"
    else:
        gc = "小幅低开"

    cpp = (C - L) / span * 100 if span > 0 else 50.0
    if cpp > 70:
        cpc, cpe = "顶部收盘", "good"
    elif cpp < 30:
        cpc, cpe = "底部收盘", "bad"
    else:
        cpc, cpe = "中部收盘", "warn"

    if C > O and lp > 40:
        nt = "低开高走收阳，长下影显示承接强劲，多头占优"
    elif C > O and up > 30:
        nt = "收阳但上影线明显，多头遇阻"
    elif C > O:
        nt = "光头阳线收盘，多头控盘力度较强"
    elif C < O and lp > 40:
        nt = "收阴但长下影显示有承接，空头未能完全掌控"
    elif C < O and up > 30:
        nt = "收阴且上影线较长，多空均未占优"
    else:
        nt = "阴线收盘，空头占优"

    return {
        "ohcl": {"open": O, "high": H, "low": L, "close": C},
        "chg_pct": round(chg, 2),
        "entity_class": ec,
        "entity_pct": round(ep),
        "shadow": {
            "upper_pct": round(up),
            "lower_pct": round(lp),
            "upper_meaning": um,
            "lower_meaning": lm,
        },
        "gap": {"pct": round(gp, 2), "class": gc},
        "close_pos": {"pct": round(cpp), "class": cpc, "tone": cpe},
        "narration": nt,
    }


# --------------------------------------------------------------------------- #
# 模块二：背景定位
# --------------------------------------------------------------------------- #

def _module2(bars: list[dict]) -> dict:
    C = bars[-1]["close"]
    win = bars[-60:]
    h60 = max(b["high"] for b in win)
    l60 = min(b["low"] for b in win)
    p60 = (C - l60) / (h60 - l60) * 100 if h60 > l60 else 50.0

    if C >= h60 * 0.95:
        stage = "极高位"
    elif C >= h60 * 0.90:
        stage = "高位"
    elif C <= l60 * 1.05:
        stage = "极低位"
    elif C <= l60 * 1.10:
        stage = "低位"
    else:
        stage = "中位"

    r20 = bars[-21:-1]
    near5 = r20[-5:]
    far5 = r20[-10:-5]
    # P1-10: 趋势用结构判断（近5/前5高低点），不再用收盘均值（本质是均线）
    near_high = max(b["high"] for b in near5)
    near_low = min(b["low"] for b in near5)
    far_high = max(b["high"] for b in far5)
    far_low = min(b["low"] for b in far5)
    if near_high > far_high and near_low > far_low:
        trend = "上升趋势"
    elif near_high < far_high and near_low < far_low:
        trend = "下跌趋势"
    else:
        trend = "横盘震荡"
    # 保留 trend_ratio 语义：近5/前5区间中点之比（结构化的“位置比”，非均线）
    near_mid = (near_high + near_low) / 2
    far_mid = (far_high + far_low) / 2
    ratio = near_mid / far_mid if far_mid else 1.0

    p20h = max(b["high"] for b in r20)
    p20l = min(b["low"] for b in r20)
    t, prev = bars[-1], bars[-2]
    chg = _pct(t["close"], prev["close"])
    # P0-1: 标准阴包阳——前阳后阴，且当前实体吞没前阳线实体
    is_engulf = (
        prev["close"] > prev["open"]
        and t["close"] < t["open"]
        and t["open"] >= prev["close"]
        and t["close"] <= prev["open"]
    )

    if t["close"] > p20h:
        kq = "向上突破"
    elif is_engulf:
        kq = "阴包阳（结构破位）"
    elif t["close"] < p20l:
        kq = "向下突破"
    elif trend == "上升趋势" and t["close"] < t["open"]:
        r10l = min(b["low"] for b in bars[-11:-1])
        kq = "上涨回调" if t["low"] >= r10l * 0.99 else "破位下跌"
    elif trend == "下跌趋势" and t["close"] > t["open"] and chg > 3:
        kq = "超跌反弹"
    elif trend == "下跌趋势" and t["close"] < t["open"]:
        kq = "下跌延续"
    else:
        kq = "普通日"

    if stage in ("高位", "极高位") and (is_engulf or t["close"] < t["open"]):
        bg = "高位%s阴线，警惕性提高 100%%" % ("(阴包阳)" if is_engulf else "")
        bg_kind = "alert"
    elif trend == "上升趋势" and t["close"] < t["open"]:
        bg = "上涨趋势中回调，对阴线容忍度提高 50%"
        bg_kind = "tolerant"
    else:
        bg = "无特殊修正"
        bg_kind = "neutral"

    return {
        "stage": stage,
        "p60_pct": round(p60),
        "range60": {"high": round(h60, 2), "low": round(l60, 2)},
        "trend": trend,
        "trend_ratio": round(ratio, 4),
        "kline_quality": kq,
        "is_engulfing": is_engulf,
        "background_note": bg,
        "background_kind": bg_kind,
        "prev20": {"high": round(p20h, 2), "low": round(p20l, 2)},
    }


# --------------------------------------------------------------------------- #
# 模块三：关键价位（冰线 / 供应区 / 需求区）
# --------------------------------------------------------------------------- #

def _ice_line(bars: list[dict]) -> dict:
    n = len(bars)
    last = n - 1
    C = bars[-1]["close"]
    rejected = []

    def ok(price: float) -> bool:
        return price > 0 and abs(C - price) / price * 100 <= ICE_MAX_DEV

    # ---- 优先级 1: 最近标志性K线开盘价（15根内、距当前≤10日、实体>60%、量>前5日均量×1.3）
    # FIX-1: 倒序搜索，取最近一根
    for i in range(n - 2, max(0, n - 15) - 1, -1):
        b = bars[i]
        days_ago = last - i
        vm = _vol_ma5_before(bars, i)
        if vm <= 0:
            continue
        ep = _entity_pct(b)
        if ep > 60 and b["vol"] > 1.3 * vm and days_ago <= 10:
            price = b["open"]
            if ok(price):
                kind = "阳" if b["close"] > b["open"] else "阴"
                return {
                    "price": round(price, 2),
                    "priority": 1,
                    "source": "标志性%s线开盘价" % kind,
                    "detail": "%s，实体 %.1f%%，量 %.2f 倍均量，%d 日前"
                    % (b["date"], ep, b["vol"] / vm, days_ago),
                    "date": b["date"],
                    "days_ago": days_ago,
                    "rejected": rejected,
                }
            rejected.append({"priority": 1, "date": b["date"], "price": round(price, 2),
                             "reason": "偏离 %.1f%% 超闸门" % (abs(C - price) / price * 100)})
            break

    # ---- 优先级 2: 近 3 日最低价（bars[-4:-1]）
    recent = bars[-4:-1]
    if recent:
        lows = [b["low"] for b in recent]
        i_min = lows.index(min(lows))
        price = min(lows)
        if ok(price):
            return {
                "price": round(price, 2),
                "priority": 2,
                "source": "近3日最低价",
                "detail": "%s 最低 %.2f（近3日低点 %.2f~%.2f，最低收盘 %.2f）"
                % (recent[i_min]["date"], price, min(lows), max(lows),
                   min(b["close"] for b in recent)),
                "date": recent[i_min]["date"],
                "days_ago": last - (n - 4 + i_min),
                "rejected": rejected,
            }
        rejected.append({"priority": 2, "price": round(price, 2),
                         "reason": "偏离 %.1f%% 超闸门" % (abs(C - price) / price * 100)})

    # ---- 优先级 3: 震荡平台下沿（连续≥5根在 3% 区间内）
    for end in range(n - 2, max(0, n - 22), -1):
        run = []
        for j in range(end, max(0, end - 10) - 1, -1):
            run.append(j)
            if len(run) >= 5:
                hi = max(bars[k]["high"] for k in run)
                lo = min(bars[k]["low"] for k in run)
                if (hi - lo) / lo * 100 < 3.0:
                    if ok(lo):
                        return {
                            "price": round(lo, 2),
                            "priority": 3,
                            "source": "震荡平台下沿",
                            "detail": "%s~%s 共 %d 根在 %.2f%% 区间内盘整，下沿 %.2f"
                            % (bars[min(run)]["date"], bars[max(run)]["date"],
                               len(run), (hi - lo) / lo * 100, lo),
                            "date": bars[min(run)]["date"],
                            "days_ago": last - max(run),
                            "rejected": rejected,
                        }
                    rejected.append({"priority": 3, "date": bars[min(run)]["date"],
                                     "price": round(lo, 2),
                                     "reason": "偏离 %.1f%% 超闸门" % (abs(C - lo) / lo * 100)})
                    break

    # ---- 优先级 4: 跳空缺口起点
    for i in range(n - 2, max(0, n - 21), -1):
        if bars[i]["low"] > bars[i - 1]["high"] * 1.005:
            price = bars[i - 1]["high"]
            if ok(price):
                return {
                    "price": round(price, 2),
                    "priority": 4,
                    "source": "跳空缺口起点",
                    "detail": "%s 缺口（前一日最高 %.2f -> 当日最低 %.2f）"
                    % (bars[i]["date"], price, bars[i]["low"]),
                    "date": bars[i - 1]["date"],
                    "days_ago": last - (i - 1),
                    "rejected": rejected,
                }
            rejected.append({"priority": 4, "date": bars[i - 1]["date"],
                             "price": round(price, 2),
                             "reason": "偏离 %.1f%% 超闸门" % (abs(C - price) / price * 100)})
            break

    # ---- 全失效：退化到近 20 日最低收盘
    window = bars[-21:-1]
    fallback_bar = min(window, key=lambda b: b["close"])
    price = fallback_bar["close"]
    return {
        "price": round(price, 2),
        "priority": 0,
        "source": "近20日最低收盘价（降级兜底）",
        "detail": "四级优先级全部失效，使用降级兜底值",
        "date": fallback_bar["date"],
        "days_ago": None,
        "rejected": rejected,
    }


def _zones(bars: list[dict], n: int = 12) -> tuple[dict, dict]:
    w = bars[-(n + 1):-1]

    hvals = [b["high"] for b in w]
    lvals = [b["low"] for b in w]

    lh = _local_peaks(hvals, True)
    if len(lh) >= 2:
        s_top, s_bot = max(lh), min(lh)
        sr = (s_top - s_bot) / s_bot * 100
        strength = "强" if sr < 2.0 else "中"
        # P1-13: 供应区触碰需“冲高回落/收阴”才算有效，避免 close<high 恒真导致强度虚高。
        # 强度“+”只在出现 ≥2 根明显冲高收阴时生效，窄幅横盘不会误加“+”。
        touches = sum(1 for b in w if s_bot <= b["high"] <= s_top and b["close"] < b["open"])
        if touches >= 2:
            strength += "+"
    else:
        s_top = max(hvals)
        s_bot = s_top - (s_top - min(lvals)) * 0.2
        strength = "弱"

    ll = _local_peaks(lvals, False)
    if len(ll) >= 2:
        d_bot, d_top = min(ll), max(ll)
        dr = (d_top - d_bot) / d_bot * 100
        dstrength = "强" if dr < 2.0 else "中"
        # P1-13: 需求区触碰需“下探回收/收阳”才算有效，强度“+”只在明显下探回收时生效
        touches = sum(1 for b in w if d_bot <= b["low"] <= d_top and b["close"] > b["open"])
        if touches >= 2:
            dstrength += "+"
    else:
        d_bot = min(lvals)
        d_top = d_bot + (max(hvals) - d_bot) * 0.15
        dstrength = "弱"

    span_days = len(w)
    supply = {
        "top": round(s_top, 2), "bottom": round(s_bot, 2), "strength": strength,
        "width_pct": round((s_top - s_bot) / s_bot * 100, 2),
        "local_peaks": len(lh), "window": span_days,
    }
    demand = {
        "top": round(d_top, 2), "bottom": round(d_bot, 2), "strength": dstrength,
        "width_pct": round((d_top - d_bot) / d_bot * 100, 2),
        "local_peaks": len(ll), "window": span_days,
    }
    return supply, demand


def _module3(bars: list[dict]) -> dict:
    C = bars[-1]["close"]
    ice = _ice_line(bars)
    supply, demand = _zones(bars, 12)

    dev = abs(C - ice["price"]) / ice["price"] * 100
    ice["deviation_pct"] = round(dev, 2)
    if dev > 5:
        if ice["price"] > C:
            ice["note"] = "偏离 %.1f%%，冰线（%.2f）高于现价（%.2f），已转为阻力位" % (
                dev, ice["price"], C)
            ice["role"] = "resistance"
        else:
            ice["note"] = "偏离 %.1f%%，冰线（%.2f）低于现价（%.2f），短期指导意义有限" % (
                dev, ice["price"], C)
            ice["role"] = "far_support"
    else:
        ice["note"] = ""
        ice["role"] = "support" if ice["price"] < C else "resistance"

    # FIX-3: 大阴线场景显式标注（v3 是隐式改写，本版只标注不改写）
    if ice["priority"] == 1:
        for b in bars[-11:-1]:
            if abs(b["open"] - ice["price"]) < 0.005 and b["close"] < b["open"] and ice["price"] > C:
                ice["note"] = (ice["note"] + "；" if ice["note"] else "") + \
                    "冰线来自大阴线开盘，处于现价上方，性质为阻力"
                ice["role"] = "resistance"
                break

    near_supply = supply["bottom"] * 0.98 <= C <= supply["top"] * 1.02
    near_demand = demand["bottom"] * 0.98 <= C <= demand["top"] * 1.02

    # P1-14: distance_pct 语义统一——正数=价位在现价上方，负数=下方；side 字段显式标注
    supply_distance = round(_pct(supply["bottom"], C), 2)
    demand_distance = round(_pct(demand["top"], C), 2)

    return {
        "ice": ice,
        "supply": {**supply, "distance_pct": supply_distance,
                   "side": "above" if supply_distance >= 0 else "below",
                   "in_zone": near_supply},
        "demand": {**demand, "distance_pct": demand_distance,
                   "side": "above" if demand_distance >= 0 else "below",
                   "in_zone": near_demand},
        "in_zone": near_supply or near_demand,
    }


# --------------------------------------------------------------------------- #
# 模块四：次日验证剧本
# --------------------------------------------------------------------------- #

_BUILD_LABEL = {
    ("上升趋势", "up"): ("看涨反转", "多头陷阱"),
    ("上升趋势", "down"): ("震仓洗盘", "趋势转弱"),
    ("上升趋势", "doji"): ("趋势暂歇", "多头陷阱"),
    ("下跌趋势", "up"): ("超跌反弹", "下跌中继"),
    ("下跌趋势", "down"): ("下跌延续", "真出货"),
    ("下跌趋势", "doji"): ("跌势暂歇", "下跌中继"),
    ("横盘震荡", "up"): ("多头试探", "假突破"),
    ("横盘震荡", "down"): ("空头试探", "真破位"),
    ("横盘震荡", "doji"): ("方向待定", "假突破"),
}

# 剧本 A 标签的三态归属：中性标签既不进 bullish，也不进 bearish
_BULLISH_QA = {"看涨反转", "震仓洗盘", "超跌反弹", "多头试探"}
_BEARISH_QA = {"下跌延续", "真出货", "空头试探", "趋势转弱"}

# chart_levels 里止损线的标签（按方向）
_STOP_LABEL = {"bull": "多头止损", "bear": "空头止损", "neutral": "参考止损"}


def _module4(bars: list[dict], m1: dict, m2: dict, m3: dict) -> dict:
    t = bars[-1]
    O, H, L, C = t["open"], t["high"], t["low"], t["close"]
    trend = m2["trend"]

    ta0 = (O + C) / 2
    tbl0 = L + (H - L) * 0.30
    tc = L * 0.997

    # B 区间：以实体中点和低点 30% 位为边界，始终有序
    tbl = min(ta0, tbl0)
    tbh = max(ta0, tbl0)
    # A 触发价必须严格高于 B 上沿，避免 O==C==L 等极端 bar 下 A 触发塌缩进 B 区间
    ta = tbh + 0.01

    if trend == "上升趋势":
        ba, bb, bc = 50, 30, 20
    elif trend == "下跌趋势":
        ba, bb, bc = 20, 30, 50
    else:
        ba, bb, bc = 30, 40, 30

    # P0-7: 供应/需求区方向性概率调整（总和归一化到 100）
    polarized = False
    if m3["supply"]["in_zone"]:
        ba, bb, bc = 35, 20, 45
        polarized = True
    elif m3["demand"]["in_zone"]:
        ba, bb, bc = 45, 20, 35
        polarized = True

    up = C > O
    down = C < O
    state = "up" if up else ("down" if down else "doji")
    corrections = []
    if down:
        decl = (C - O) / O * 100
        if abs(decl) > 5 and m1["entity_pct"] > 60:
            ba -= 10
            bc += 10
            corrections.append("大阴线跌幅 %.1f%%>5%%：A-10%%，C+10%%" % abs(decl))
        elif abs(decl) < 2 and m1["shadow"]["lower_pct"] > m1["entity_pct"]:
            ba += 10
            bc -= 10
            corrections.append("阴线跌幅 <2% 且下影>实体：A+10%，C-10%")
        else:
            corrections.append("阴线幅度适中，无需修正")
    elif up:
        corrections.append("今日收阳，不适用阴线修正")
    else:
        corrections.append("十字星收盘，不适用阴线修正")

    total = ba + bb + bc
    pa = round(ba / total * 100)
    pb = round(bb / total * 100)
    pc = 100 - pa - pb

    key = (trend, state)
    if key in _BUILD_LABEL:
        qa, qc = _BUILD_LABEL[key]
    elif up:
        qa, qc = ("多头试探", "假突破")
    elif down:
        qa, qc = ("空头试探", "真破位")
    else:
        qa, qc = ("方向待定", "假突破")

    if state == "doji":
        qb = "整固观察"
    elif up:
        qb = "高位整固"
        if trend == "下跌趋势":
            qb = "反弹中继"
    else:
        qb = "中继/整固"
        if trend == "横盘震荡":
            qb = "箱体内回踩"

    # 方向三态：中性标签既不进 bullish，也不进 bearish
    if qa in _BULLISH_QA:
        direction = "bull"
    elif qa in _BEARISH_QA:
        direction = "bear"
    else:
        direction = "neutral"

    # P0-3: 止损方向——做多止损在冰线下方，做空止损在供应区上方，中性仅作参考。
    # resistance 始终表示“上方压力位”，与止损位（stop_loss）分离。
    resistance = m3["supply"]["top"]
    if direction == "bull":
        stop = m3["ice"]["price"] * 0.99
        stop_note = "看涨 → 止损设在冰线（%.2f）下方 1%% = %.2f" % (m3["ice"]["price"], stop)
    elif direction == "bear":
        stop = m3["supply"]["top"] * 1.01
        stop_note = "看跌 → 止损设在供应区上沿（%.2f）上方 1%% = %.2f" % (m3["supply"]["top"], stop)
    else:
        stop = m3["supply"]["top"] * 1.01
        stop_note = "方向未定 → 止损仅作参考（供应区上沿 %.2f 上方 1%% = %.2f）" % (m3["supply"]["top"], stop)

    probs = {"A": pa, "B": pb, "C": pc}
    top = max(probs.values())
    tied = sorted(k for k, v in probs.items() if v == top)

    return {
        "trend_used": trend,
        "polarized": polarized,
        "direction": direction,
        "tie": len(tied) > 1,
        "tied": tied,
        "corrections": corrections,
        "scenarios": {
            "A": {"prob": pa, "trigger": round(ta, 2), "label": qa, "tone": "bull"},
            "B": {"prob": pb, "low": round(tbl, 2), "high": round(tbh, 2), "label": qb, "tone": "range"},
            "C": {"prob": pc, "trigger": round(tc, 2), "label": qc, "tone": "bear"},
        },
        "base_prob": {"A": ba, "B": bb, "C": bc},
        "probabilities": probs,
        "stop_loss": round(stop, 2),
        "stop_note": stop_note,
        "resistance": round(resistance, 2) if resistance else None,
        "dominant": tied[0],
    }


# --------------------------------------------------------------------------- #
# 模块五：盘中动态修正
# --------------------------------------------------------------------------- #

def _module5(bars: list[dict], m1: dict, m4: dict, quote: dict | None) -> dict:
    if not quote:
        return {"available": False, "note": "非交易时段，跳过盘中动态修正"}

    last = quote.get("last")
    if last is None:
        return {"available": False, "note": "快照缺少现价，跳过盘中动态修正"}

    sc = m4["scenarios"]
    if last >= sc["A"]["trigger"]:
        live, tone = "A", "bull"
        note = "现价 %.2f 已站上剧本A触发价 %.2f，看涨剧本进行中" % (last, sc["A"]["trigger"])
    elif last <= sc["C"]["trigger"]:
        live, tone = "C", "bear"
        note = "现价 %.2f 已跌破剧本C触发价 %.2f，看跌剧本进行中" % (last, sc["C"]["trigger"])
    else:
        live, tone = "B", "range"
        note = "现价 %.2f 位于 %.2f~%.2f 之间，区间震荡剧本中" % (last, sc["B"]["low"], sc["B"]["high"])

    return {
        "available": True,
        "live_scenario": live,
        "tone": tone,
        "note": note + "（盘中未收盘，触发未确认）",
        "confirmed": False,
        "intraday": {
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "last": last,
            "chg_pct": quote.get("chg_pct"),
            "time": quote.get("time", ""),
        },
    }


# --------------------------------------------------------------------------- #
# 模块六：事后验证
# --------------------------------------------------------------------------- #

def verify_previous(prev: dict | None, bars: list[dict], today: str) -> dict | None:
    """用真实后续K线判定上一轮分析的剧本是否兑现。

    剧本语义（技能模块四）:
        A 触发: 收盘 > (O+C)/2  -> 看涨剧本成立
        C 触发: 收盘 < L*0.997   -> 看跌剧本成立
        B     : 收盘落入 B.low~B.high 区间 -> 区间剧本成立
        三者皆未触发 -> 记为“未触发”，不再把“长期横盘”简单算作 B
    """
    if not prev or prev.get("date") == today:
        return None

    # P0-3(2.0.2): 日期严格解析——任一无法解析的日期直接跳过该 bar，不做字符串回退，
    # 避免 date/str 类型混用比较抛 TypeError。无法解析的 bar 计数后合并为一条 warning。
    parse_warnings: list[str] = []
    prev_key = _date_key(prev["date"])
    if prev_key is None:
        parse_warnings.append("上轮日期 %r 无法解析" % prev["date"])
    after = []
    bad_bar_count = 0
    for b in bars:
        bkey = _date_key(b["date"])
        if bkey is None:
            bad_bar_count += 1
            continue
        if prev_key is not None and bkey > prev_key:
            after.append(b)
    if bad_bar_count:
        parse_warnings.append("K线中有 %d 根日期无法解析，已跳过" % bad_bar_count)
    if not after:
        return None

    sc = prev.get("playbook", {}).get("scenarios")
    if not sc:
        return None

    # P0-8: B 判定贴近剧本语义——A/C 触发优先；B 需收盘实际落入区间；否则“未触发”
    hits = {"A": None, "B": None, "C": None}
    b_low, b_high = sc["B"]["low"], sc["B"]["high"]
    for b in after:
        if b["close"] > sc["A"]["trigger"]:
            hits["A"] = b["date"]
            break
        if b["close"] < sc["C"]["trigger"]:
            hits["C"] = b["date"]
            break
        if hits["B"] is None and b_low <= b["close"] <= b_high:
            hits["B"] = b["date"]

    if hits["A"]:
        actual = "A"
    elif hits["C"]:
        actual = "C"
    elif hits["B"]:
        actual = "B"
    else:
        actual = "未触发"

    predicted = prev.get("playbook", {}).get("dominant")
    if actual == "未触发":
        verdict = "未触发"
    else:
        verdict = "命中" if actual == predicted else "未命中"

    # 冰线/区间漂移：按角色区分突破方向
    drift = {}
    ice_node = prev.get("levels", {}).get("ice", {})
    old_ice = ice_node.get("price")
    if old_ice:
        role = ice_node.get("role")
        drift["ice_old"] = old_ice
        drift["ice_role"] = role
        if role == "resistance":
            # 阻力在上方：收盘站上冰线才算突破
            broke = any(b["close"] > old_ice for b in after)
            drift["ice_broken"] = broke
            drift["ice_break_date"] = next((b["date"] for b in after if b["close"] > old_ice), None)
            drift["ice_label"] = "站上冰线（阻力突破）" if broke else "未突破（阻力仍有效）"
        elif role == "far_support":
            # 远支撑：区分是否回落跌破
            broke = any(b["close"] < old_ice for b in after)
            drift["ice_broken"] = broke
            drift["ice_break_date"] = next((b["date"] for b in after if b["close"] < old_ice), None)
            drift["ice_label"] = "回落跌破冰线" if broke else "未回落至其下方"
        else:
            # support 及其他默认：跌破冰线才算支撑失效
            broke = any(b["close"] < old_ice for b in after)
            drift["ice_broken"] = broke
            drift["ice_break_date"] = next((b["date"] for b in after if b["close"] < old_ice), None)
            drift["ice_label"] = "跌破冰线（支撑失效）" if broke else "守稳"

    old_sup = prev.get("levels", {}).get("supply", {})
    if old_sup.get("top"):
        touched = any(b["high"] >= old_sup["bottom"] * 0.99 for b in after)
        drift["supply_touched"] = touched
        drift["supply_upgraded"] = any(b["close"] > old_sup["top"] for b in after)

    return {
        "prev_date": prev["date"],
        "prev_dominant": predicted,
        "prev_probs": prev.get("playbook", {}).get("probabilities"),
        "days_elapsed": len(after),
        "actual_scenario": actual,
        "first_hit_dates": hits,
        "verdict": verdict,
        "drift": drift,
        "warnings": parse_warnings,
        "bar_after": after[0] if after else None,
    }


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #

def analyze(bars: list[dict], name: str, code: str, symbol: str,
            quote: dict | None = None, prev: dict | None = None,
            is_intraday: bool = False) -> dict:
    if len(bars) < 21:
        raise ValueError("K线不足 21 根，无法执行六模块分析（当前 %d 根）" % len(bars))

    m1 = _module1(bars)
    m2 = _module2(bars)
    m3 = _module3(bars)
    m4 = _module4(bars, m1, m2, m3)
    m5 = _module5(bars, m1, m4, quote)

    today = bars[-1]["date"]
    m6 = verify_previous(prev, bars, today)

    # 图表标注用价位清单
    levels = [
        {"key": "ice", "label": "冰线", "price": m3["ice"]["price"], "kind": "line",
         "color": "#38BDF8", "style": "dashed", "note": m3["ice"]["source"]},
        {"key": "supply", "label": "供应区", "kind": "band", "color": "#F6465D",
         "top": m3["supply"]["top"], "bottom": m3["supply"]["bottom"],
         "note": "强度%s" % m3["supply"]["strength"]},
        {"key": "demand", "label": "需求区", "kind": "band", "color": "#0ECB81",
         "top": m3["demand"]["top"], "bottom": m3["demand"]["bottom"],
         "note": "强度%s" % m3["demand"]["strength"]},
        {"key": "playA", "label": "剧本A触发", "price": m4["scenarios"]["A"]["trigger"],
         "kind": "line", "color": "#FBBF24", "style": "dotted",
         "note": m4["scenarios"]["A"]["label"]},
        {"key": "playC", "label": "剧本C触发", "price": m4["scenarios"]["C"]["trigger"],
         "kind": "line", "color": "#FB923C", "style": "dotted",
         "note": m4["scenarios"]["C"]["label"]},
        {"key": "stop", "label": _STOP_LABEL.get(m4.get("direction"), "止损"),
         "price": m4["stop_loss"], "kind": "line",
         "color": "#A78BFA", "style": "large_dashed", "note": m4["stop_note"]},
        {"key": "resistance", "label": "压力位", "price": m4["resistance"], "kind": "line",
         "color": "#F87171", "style": "dashed",
         "note": "上方压力位（供应区上沿，与止损位分离）"},
    ]

    warnings = []
    if m4["tie"]:
        warnings.append("剧本 %s 概率持平（%d%%），无单一主剧本，勿按单一方向布局"
                        % ("/".join(m4["tied"]), m4["scenarios"][m4["dominant"]]["prob"]))
    if m3["ice"]["priority"] == 0:
        warnings.append("冰线四级优先级全部失效，已降级为近20日最低收盘价，参考价值低")
    if m3["ice"]["deviation_pct"] > ICE_MAX_DEV:
        warnings.append("冰线偏离 %.1f%% 过大" % m3["ice"]["deviation_pct"])
    for r in m3["ice"].get("rejected", []):
        warnings.append("冰线候选被拒(P%d): %s" % (r["priority"], r["reason"]))
    if m3["supply"]["width_pct"] > 15:
        warnings.append("供应区跨度 %.1f%%，过大，有效性下降" % m3["supply"]["width_pct"])
    if m3["demand"]["width_pct"] > 15:
        warnings.append("需求区跨度 %.1f%%，过大，有效性下降" % m3["demand"]["width_pct"])
    if len(bars) < 60:
        warnings.append("K线仅 %d 根（<60），阶段定位降级" % len(bars))
    if is_intraday:
        warnings.append("含当日未完成K线（盘中），结论为临时值")

    return {
        "id": "%s@%s" % (symbol, today),
        "engine_version": ENGINE_VERSION,
        "symbol": symbol,
        "code": code,
        "name": name,
        "date": today,
        "is_intraday": is_intraday,
        "bar_count": len(bars),
        "m1_kline": m1,
        "m2_context": m2,
        "levels": m3,
        "playbook": m4,
        "intraday": m5,
        "verification": m6,
        "chart_levels": levels,
        "warnings": warnings,
    }
