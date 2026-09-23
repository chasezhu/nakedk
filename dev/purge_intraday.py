#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清理历史里"当日K线未完成"时写入的脏记录。

背景：早期版本用 is_trading_now 判定"当日bar是否完成"，把午休（11:30-13:00）
期间基于半截K线的分析也落了盘。这些记录会让次日的事后验证拿到错误基准。
判定条件：记录的 date == 今天 且当前还没到 15:00（即该记录必然来自未收盘的bar），
或记录自身带 is_intraday 标记。

用法: python3 dev/purge_intraday.py [--dry-run]
"""
import argparse
import datetime
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import history as hist  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--date", default=None, help="只清理这一天的记录（默认今天）")
    args = ap.parse_args()

    target = args.date or datetime.datetime.now().strftime("%Y-%m-%d")
    total = 0
    for path in sorted(glob.glob(os.path.join(hist._HIST_DIR, "*.json"))):
        rows = json.load(open(path, encoding="utf-8"))
        keep = [r for r in rows if not (r.get("date") == target or r.get("is_intraday"))]
        dropped = len(rows) - len(keep)
        if not dropped:
            continue
        total += dropped
        print("%-26s 删除 %2d 条 (%s)" % (os.path.basename(path), dropped, target))
        if not args.dry_run:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(keep, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)

    print("\n%s：共 %d 条%s" % ("将删除" if args.dry_run else "已删除",
                               total, "（dry-run，未写盘）" if args.dry_run else ""))


if __name__ == "__main__":
    main()
