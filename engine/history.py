#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析历史存储 —— 支撑模块六（事后验证）。

每只标的一个 JSON 文件，追加式保存，保留最近 N 次。
存放于 ~/.nakedk/history/<symbol>.json
"""

from __future__ import annotations

import json
import os
import threading

_ROOT = os.path.expanduser(os.environ.get("NAKEDK_HOME", "~/.nakedk"))
_HIST_DIR = os.path.join(_ROOT, "history")
_KEEP = 120
_lock = threading.Lock()


def _path(symbol: str) -> str:
    safe = "".join(c for c in symbol if c.isalnum() or c in "._-")
    return os.path.join(_HIST_DIR, "%s.json" % safe)


def load(symbol: str) -> list[dict]:
    p = _path(symbol)
    if not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def last_before(symbol: str, date: str) -> dict | None:
    """取该日期之前最近一次分析。"""
    rows = [r for r in load(symbol) if r.get("date") and r["date"] < date]
    return rows[-1] if rows else None


def save(record: dict) -> None:
    """保存一次分析。同 date 覆盖（当日可重复分析，只留最新）。"""
    symbol = record.get("symbol")
    if not symbol:
        return
    with _lock:
        os.makedirs(_HIST_DIR, mode=0o700, exist_ok=True)
        rows = load(symbol)
        rows = [r for r in rows if r.get("date") != record.get("date")] + [record]
        rows.sort(key=lambda r: r.get("date") or "")
        rows = rows[-_KEEP:]
        tmp = _path(symbol) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _path(symbol))


def recent(symbol: str, limit: int = 30) -> list[dict]:
    """返回轻量历史（只留验证需要的字段），供前端画时间线。"""
    out = []
    for r in load(symbol)[-limit:]:
        pb = r.get("playbook", {})
        lv = r.get("levels", {})
        out.append(
            {
                "date": r.get("date"),
                "close": r.get("m1_kline", {}).get("ohcl", {}).get("close"),
                "trend": r.get("m2_context", {}).get("trend"),
                "stage": r.get("m2_context", {}).get("stage"),
                "kline_quality": r.get("m2_context", {}).get("kline_quality"),
                "probabilities": {"A": pb.get("scenarios", {}).get("A", {}).get("prob"),
                                  "B": pb.get("scenarios", {}).get("B", {}).get("prob"),
                                  "C": pb.get("scenarios", {}).get("C", {}).get("prob")},
                "dominant": pb.get("dominant"),
                "ice": lv.get("ice", {}).get("price"),
                "ice_priority": lv.get("ice", {}).get("priority"),
                "supply": [lv.get("supply", {}).get("bottom"), lv.get("supply", {}).get("top")],
                "demand": [lv.get("demand", {}).get("bottom"), lv.get("demand", {}).get("top")],
                "verdict": (r.get("verification") or {}).get("verdict"),
            }
        )
    return out
