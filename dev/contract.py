#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""契约回归：对一组标的断言分析输出包含全部必需字段。

存在意义：开发中用整段 patch 串联多个函数时，old_string 跨函数边界会
静默吃掉字段（corrections 就这样丢过一次，前端直接白屏）。这个测试把
"输出契约"钉死，字段缺失立刻失败。

用法: python3 dev/contract.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import analyzer as az  # noqa: E402
from engine import datasource as ds  # noqa: E402
from engine import history as hist  # noqa: E402

REQUIRED = {
    "root": ["id", "engine_version", "symbol", "code", "name", "date", "is_intraday",
             "bar_count", "m1_kline", "m2_context", "levels", "playbook", "intraday",
             "verification", "chart_levels", "warnings"],
    "m1_kline": ["ohcl", "chg_pct", "entity_class", "entity_pct", "shadow", "gap",
                 "close_pos", "narration"],
    "m1_kline.shadow": ["upper_pct", "lower_pct", "upper_meaning", "lower_meaning"],
    "m2_context": ["stage", "p60_pct", "range60", "trend", "trend_ratio",
                   "kline_quality", "is_engulfing", "background_note", "background_kind"],
    "levels": ["ice", "supply", "demand", "in_zone"],
    "levels.ice": ["price", "priority", "source", "detail", "date", "days_ago",
                   "rejected", "deviation_pct", "note", "role"],
    "levels.supply": ["top", "bottom", "strength", "width_pct", "local_peaks",
                      "distance_pct", "in_zone"],
    "levels.demand": ["top", "bottom", "strength", "width_pct", "local_peaks",
                      "distance_pct", "in_zone"],
    "playbook": ["trend_used", "polarized", "tie", "tied", "corrections", "scenarios",
                 "base_prob", "probabilities", "stop_loss", "stop_note",
                 "resistance", "dominant"],
    "playbook.scenarios": ["A", "B", "C"],
    "playbook.scenarios.A": ["prob", "trigger", "label", "tone"],
    "playbook.scenarios.B": ["prob", "low", "high", "label", "tone"],
    "playbook.scenarios.C": ["prob", "trigger", "label", "tone"],
    "intraday": ["available", "note"],
}

WATCH_TARGETS = ["300768", "600030", "002709", "603501", "002415", "600703",
                 "603938", "000001", "399006", "688981"]


def get(d, path):
    cur = d
    for part in path.split("."):
        cur = cur[part]
    return cur


def check(rep) -> list[str]:
    bad = []
    for path, keys in REQUIRED.items():
        try:
            node = rep if path == "root" else get(rep, path)
        except (KeyError, TypeError) as e:
            bad.append("%s: 无法定位 (%s)" % (path, e))
            continue
        for k in keys:
            if k not in node:
                bad.append("%s.%s 缺失" % (path, k))
    if len(rep["chart_levels"]) < 5:
        bad.append("chart_levels 只有 %d 条" % len(rep["chart_levels"]))
    if not (rep["playbook"]["scenarios"]["A"]["prob"]
            + rep["playbook"]["scenarios"]["B"]["prob"]
            + rep["playbook"]["scenarios"]["C"]["prob"] == 100):
        bad.append("A+B+C 概率不等于 100")
    if rep["levels"]["ice"]["price"] <= 0:
        bad.append("冰线价格非正")
    return bad


def main():
    fails = 0
    for q in WATCH_TARGETS:
        try:
            hit = ds.resolve(q)
            bars, src = ds.fetch_daily_auto(hit["symbol"], 250)
            rep = az.analyze(bars, hit["name"], hit["code"], hit["symbol"],
                             quote=None,
                             prev=hist.last_before(hit["symbol"], bars[-1]["date"]))
        except Exception as e:
            print("✗ %-8s %s  取数/分析异常: %s" % (q, "", e))
            fails += 1
            continue
        bad = check(rep)
        if bad:
            fails += 1
            print("✗ %-8s %-8s %s" % (q, hit["name"], " | ".join(bad)))
        else:
            pb = rep["playbook"]
            print("✓ %-8s %-8s 冰线 %7.2f(P%d,%-9s) 主剧本 %s%s  验证 %s"
                  % (q, hit["name"], rep["levels"]["ice"]["price"],
                     rep["levels"]["ice"]["priority"], rep["levels"]["ice"]["role"],
                     pb["dominant"], " [并列]" if pb["tie"] else "",
                     rep["verification"]["verdict"] if rep["verification"] else "—"))
    print("\n%s  %d/%d 通过" % ("全部通过" if not fails else "有失败",
                               len(WATCH_TARGETS) - fails, len(WATCH_TARGETS)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
