#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""引擎自检：跑一遍五模块并打印全部字段。"""
import json
import sys

import os
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)  # 仓库根，不再写死 /home/zhu/nakedk（换台电脑可跑）
from engine import datasource as ds
from engine import analyzer as az

q = sys.argv[1] if len(sys.argv) > 1 else "300768"
hit = ds.resolve(q)
print("resolve:", hit)
bars, src = ds.fetch_daily_auto(hit["symbol"], 250)
print("src=%s bars=%d %s..%s" % (src, len(bars), bars[0]["date"], bars[-1]["date"]))

r = az.analyze(bars, hit["name"], hit["code"], hit["symbol"])
for k in ("m1_kline", "m2_context", "playbook", "intraday"):
    print("\n=== %s ===" % k)
    print(json.dumps(r[k], ensure_ascii=False, indent=1))
print("\n=== levels.ice ===")
print(json.dumps(r["levels"]["ice"], ensure_ascii=False, indent=1))
print("\n=== levels.supply/demand ===")
print(json.dumps({k: v for k, v in r["levels"].items() if k != "ice"}, ensure_ascii=False, indent=1))
print("\n=== chart_levels ===")
print(json.dumps(r["chart_levels"], ensure_ascii=False, indent=1))
print("\n=== warnings ===", r["warnings"])
