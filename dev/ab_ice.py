#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FIX-1 验证：冰线优先级1 正序搜索 vs 倒序搜索，在历史截面上对比。

用法: python3 dev/ab_ice.py 300768 2026-08-07
"""
import sys

import os
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)  # 仓库根，不再写死 /home/zhu/nakedk（换台电脑可跑）
from engine import datasource as ds
from engine.analyzer import _entity_pct, _vol_ma5_before


def ice_ascending(bars):
    """v3 的原实现：正序（旧->新），第一个命中就返回。"""
    n = len(bars)
    for i in range(max(0, n - 15), n - 1):
        b = bars[i]
        vm = _vol_ma5_before(bars, i)
        if vm <= 0:
            continue
        da = n - 1 - i
        if _entity_pct(b) > 60 and b["vol"] > 1.3 * vm and da <= 10:
            return {"price": round(b["open"], 2), "bar": b["date"], "days_ago": da,
                    "entity": round(_entity_pct(b), 1), "volx": round(b["vol"] / vm, 2),
                    "color": "阳" if b["close"] > b["open"] else "阴"}
    return None


def ice_descending(bars):
    """本版实现：倒序（新->旧），取最近一根。"""
    n = len(bars)
    for i in range(n - 2, max(0, n - 15) - 1, -1):
        b = bars[i]
        vm = _vol_ma5_before(bars, i)
        if vm <= 0:
            continue
        da = n - 1 - i
        if _entity_pct(b) > 60 and b["vol"] > 1.3 * vm and da <= 10:
            return {"price": round(b["open"], 2), "bar": b["date"], "days_ago": da,
                    "entity": round(_entity_pct(b), 1), "volx": round(b["vol"] / vm, 2),
                    "color": "阳" if b["close"] > b["open"] else "阴"}
    return None


def main():
    q = sys.argv[1] if len(sys.argv) > 1 else "300768"
    cutoff = sys.argv[2] if len(sys.argv) > 2 else None

    hit = ds.resolve(q)
    bars, _ = ds.fetch_daily_auto(hit["symbol"], 400)
    if cutoff:
        bars = [b for b in bars if b["date"] <= cutoff]
    if len(bars) < 21:
        print("数据不足")
        return

    C = bars[-1]["close"]
    a = ice_ascending(bars)
    d = ice_descending(bars)

    print("标的 %s(%s)  截面日期 %s  收盘 %.2f" % (hit["name"], hit["symbol"], bars[-1]["date"], C))
    print("-" * 72)
    for tag, r in (("v3 正序(旧->新)", a), ("本版 倒序(新->旧)", d)):
        if not r:
            print("%-18s -> 无候选" % tag)
            continue
        dev = abs(C - r["price"]) / r["price"] * 100
        print("%-18s -> 冰线 %7.2f  %s(%s线, 实体%.1f%%, 量%.2fx, %d日前)  偏离 %.2f%%"
              % (tag, r["price"], r["bar"], r["color"], r["entity"], r["volx"], r["days_ago"], dev))
    print("-" * 72)
    if a and d and a["price"] != d["price"]:
        print(">>> 两者不同：倒序选到了更近的标志性K线（%s vs %s）" % (d["bar"], a["bar"]))
        print(">>> 倒序偏离 %.2f%%  正序偏离 %.2f%%"
              % (abs(C - d["price"]) / d["price"] * 100, abs(C - a["price"]) / a["price"] * 100))
    else:
        print(">>> 该截面两者一致")


if __name__ == "__main__":
    main()
