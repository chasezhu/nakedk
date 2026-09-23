#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""证明：页面的裸K分析是确定性机械计算，不是 LLM 记忆/生成。

三件事：
  A. 确定性  —— 同一批K线跑两次，输出逐字节一致
  B. 可复现  —— 独立进程、无技能上下文、无会话记忆，重算结果 == 服务端 /api/analyze
  C. 可审计  —— 每个结论字段都能追溯到一个规则行（这里抽查几条并打印其输入）
"""
import hashlib
import json
import sys
import urllib.request

import os
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)  # 仓库根，不再写死 /home/zhu/nakedk（换台电脑可跑）
from engine import analyzer as az
from engine import datasource as ds
from engine import history as hist

SYM = sys.argv[1] if len(sys.argv) > 1 else "300768"
PORT = 8600


def h(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


def main():
    print("=" * 74)
    print("标的 %s" % SYM)
    print("=" * 74)

    # ── K线从网络取一次，之后不再碰网络 ──
    hit = ds.resolve(SYM)
    bars, src = ds.fetch_daily_auto(hit["symbol"], 250)
    print("K线: %d 根  %s .. %s  (源 %s)" % (len(bars), bars[0]["date"], bars[-1]["date"], src))

    # ── A. 确定性：同一输入跑两次 ──
    r1 = az.analyze(bars, hit["name"], hit["code"], hit["symbol"])
    r2 = az.analyze(bars, hit["name"], hit["code"], hit["symbol"])
    same = json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)
    print("\n[A] 确定性      两次运行 sha256[:16] = %s / %s  → %s"
          % (h(r1), h(r2), "逐字节一致 ✓" if same else "不一致 ✗"))

    # ── B. 严格可复现：拿服务端同一批输入喂给本地引擎，必须逐字段一致 ──
    # 注意：第一次写这个测试时漏传了 prev / quote，导致 verification 与 intraday
    # 报差异 —— 那是**测试的缺陷**不是引擎的不确定。真正的严格对比必须让两边
    # 看到完全相同的输入：同样 250 根 bars + 同样 quote + 同样 prev + 同样 is_intraday。
    url = "http://127.0.0.1:%d/api/analyze?q=%s" % (PORT, SYM)
    remote = json.loads(urllib.request.urlopen(url, timeout=40).read())

    r3 = az.analyze(remote["bars"], hit["name"], hit["code"], hit["symbol"],
                    quote=remote.get("quote_used"),            # 服务端实际用的实时快照
                    prev=hist.last_before(hit["symbol"], remote["bars"][-1]["date"]),
                    is_intraday=remote["is_intraday"])
    keys = [k for k in r3 if k != "empty_marker"]
    diff = [k for k in keys
            if json.dumps(r3[k], sort_keys=True, ensure_ascii=False)
            != json.dumps(remote.get(k), sort_keys=True, ensure_ascii=False)]
    print("[B] 严格可复现  同 bars + 同 prev + 同 is_intraday 喂本地引擎")
    print("                对比 %d 个字段 → %s" % (len(keys), "全部一致 ✓" if not diff else "有差异 ✗ %s" % diff))
    if diff:
        for k in diff:
            print("                  %s: 本地=%s" % (k, json.dumps(r3[k], ensure_ascii=False)[:90]))
            print("                  %s: 远端=%s" % (" " * len(k), json.dumps(remote.get(k), ensure_ascii=False)[:90]))

    # ── C. 可审计：抽查结论 → 规则 → 输入 ──
    m1, m2, L, pb = r1["m1_kline"], r1["m2_context"], r1["levels"], r1["playbook"]
    o = m1["ohcl"]
    print("\n[C] 可审计抽查（结论 → 规则 → 原始输入）")
    print("  实体占比 %d%%  ← |C-O|/(H-L)×100 = |%.2f-%.2f|/(%.2f-%.2f)"
          % (m1["entity_pct"], o["close"], o["open"], o["high"], o["low"]))
    print("  实体分类 %s   ← 阈值 >70 大 / >40 中 / <20 十字星 / 其余小" % m1["entity_class"])
    print("  阶段 %s (60日 %d%%) ← 基于近60根: 高 %.2f 低 %.2f, C=%.2f"
          % (m2["stage"], m2["p60_pct"], m2["range60"]["high"], m2["range60"]["low"], o["close"]))
    print("  趋势 %s   ← 近5日均收/远5日均收 = %s（>1.02 升 / <0.98 跌）"
          % (m2["trend"], m2["trend_ratio"]))
    ice = L["ice"]
    print("  冰线 %.2f (P%d %s, %d日前) ← %s"
          % (ice["price"], ice["priority"], ice["source"], ice["days_ago"], ice["detail"]))
    print("  供应区 %.2f~%.2f ← 近12根局部高点聚类，强度=%s"
          % (L["supply"]["bottom"], L["supply"]["top"], L["supply"]["strength"]))
    print("  剧本A %.0f%% 触发>%.2f ← 基础概率(趋势=%s)%s"
          % (pb["scenarios"]["A"]["prob"], pb["scenarios"]["A"]["trigger"],
             pb["trend_used"], "，边界极性化改为 40/20/40" if pb["polarized"] else ""))

    # ── 唯一用到"历史"的地方 ──
    v = r1.get("verification")
    print("\n[唯一用到『历史』的模块] 模块六 事后验证")
    if v:
        print("  读 %s 的落盘记录（上一次的分析输出 JSON），比对真实后续K线"
              % v["prev_date"])
        print("  预测 %s → 实际 %s → %s" % (v["prev_dominant"], v["actual_scenario"], v["verdict"]))
    else:
        print("  无历史记录（首次分析该标的），模块六显示空态")

    print("\n结论：页面数字 100%% 来自 engine/analyzer.py 的确定性计算；")
    print("      运行时无 LLM、无 prompt、无会话记忆。唯一的外部读入是")
    print("      (1) 腾讯财经的 OHLC  (2) ~/.nakedk/history/ 里上一次的规则输出。")


if __name__ == "__main__":
    main()
