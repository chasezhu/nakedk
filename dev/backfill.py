#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""历史回算落盘 —— 让模块六（事后验证）立刻可用。

对每个标的，取最近 N 个交易日，逐日截断K线后跑一遍五模块引擎并落盘到
~/.nakedk/history/<symbol>.json。这样"今天"的分析就能在模块六里看到
上一个交易日的剧本预测 vs 真实走势。

注意：这是**机械回放**，不是前视优化 —— 第 d 日只喂 date <= d 的K线，
与当日真实运行完全等价（冰线优先级、成交量均量窗口都不会看到未来数据）。

用法:
    python3 dev/backfill.py 300768 600030 --days 20
    python3 dev/backfill.py --watchlist --days 20
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import analyzer as az  # noqa: E402
from engine import datasource as ds  # noqa: E402
from engine import history as hist  # noqa: E402


def backfill(query: str, days: int = 20, verbose: bool = True) -> int:
    hit = ds.resolve(query)
    bars, src = ds.fetch_daily_auto(hit["symbol"], 400)
    if len(bars) < 41:
        if verbose:
            print("  %s K线不足，跳过" % hit["name"])
        return 0

    # 最后一天是"今天"，前面 days 天作为历史
    stops = bars[:-days] if days < len(bars) else bars[:1]
    last_full = bars[-1 - days] if days < len(bars) else bars[0]

    n = 0
    for i in range(len(bars) - 1 - days, len(bars) - 1):
        upto = bars[: i + 1]
        if len(upto) < 21:
            continue
        d = upto[-1]["date"]
        try:
            rep = az.analyze(upto, hit["name"], hit["code"], hit["symbol"],
                             quote=None, prev=hist.last_before(hit["symbol"], d),
                             is_intraday=False)
        except ValueError:
            continue
        rep["source"] = src
        rep["kind"] = hit.get("kind")
        hist.save({k: v for k, v in rep.items() if k != "bars"})
        n += 1
        if verbose:
            v = rep["verification"]
            tag = ""
            if v:
                tag = "  ← 验证 %s %s→%s" % (v["prev_date"][5:], v["prev_dominant"],
                                            v["actual_scenario"])
            print("  %s  %s  收 %7.2f  冰线 %6.2f(P%d)  主剧本 %s  验证%s"
                  % (d, hit["name"], rep["m1_kline"]["ohcl"]["close"],
                     rep["levels"]["ice"]["price"], rep["levels"]["ice"]["priority"],
                     rep["playbook"]["dominant"],
                     v["verdict"] if v else "—"))
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("queries", nargs="*", help="股票代码或名称")
    ap.add_argument("--watchlist", action="store_true", help="对自选股列表执行")
    ap.add_argument("--days", type=int, default=20, help="回算多少个交易日（默认 20）")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    queries = list(args.queries)
    if args.watchlist:
        wl = os.path.expanduser(
            "~/.hermes/skills/note-taking/naked-kline-analyst/watchlist.txt")
        if os.path.exists(wl):
            with open(wl, encoding="utf-8") as f:
                queries += [ln.split()[0] for ln in f
                            if ln.strip() and not ln.startswith("#")]
        else:
            print("找不到 watchlist: %s" % wl)

    if not queries:
        ap.error("至少给一个标的，或用 --watchlist")

    total = 0
    for q in queries:
        print("\n▶ %s" % q)
        try:
            total += backfill(q, args.days, verbose=not args.quiet)
        except ds.DataSourceError as e:
            print("  取数失败: %s" % e)
    print("\n完成：共落盘 %d 条历史分析 → %s" % (total, hist._HIST_DIR))


if __name__ == "__main__":
    main()
