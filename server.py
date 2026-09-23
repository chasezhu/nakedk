#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""裸K战法终端 · FastAPI 服务

    GET  /api/health
    GET  /api/search?q=迪普科技
    GET  /api/analyze?q=300768&days=250
    GET  /api/kline?symbol=sz300768&count=250
    GET  /api/watchlist
    POST /api/watchlist   {"action":"add"|"remove","query":"300768"}
    GET  /api/history?symbol=sz300768
    GET  /                -> web/ 静态页
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import analyzer as az  # noqa: E402
from engine import datasource as ds  # noqa: E402
from engine import history as hist  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(BASE, "web")

# 数据根：与 engine/history.py 共用同一个 ~/.nakedk（可用 NAKEDK_HOME 覆盖）。
DATA_ROOT = os.path.expanduser(os.environ.get("NAKEDK_HOME", "~/.nakedk"))

# 自选股 = 本机数据根下的真实文件。
# 历史沿革：早期这份列表放在 hermes 技能目录里（17:00 cron 日报读的就是那个路径）。
# 现在技能目录那份是【指向本文件的软链】，两边始终同一份数据，不会分叉。
WATCHLIST = os.path.expanduser(
    os.environ.get("NAKEDK_WATCHLIST", os.path.join(DATA_ROOT, "watchlist.txt"))
)
# 兼容旧路径：仅用于「首次启动自动迁移」（软链的话会跳过，避免自指）
LEGACY_WATCHLIST = os.path.expanduser(
    "~/.hermes/skills/note-taking/naked-kline-analyst/watchlist.txt"
)
# 仓库自带模板：换台电脑 clone 下来，首次启动自动播种为真实列表
WATCHLIST_EXAMPLE = os.path.join(BASE, "watchlist.example")

WATCH_HEADER = [
    "# 自选股列表",
    "# 每行一只股票，格式：股票代码 股票名称（名称可省略，服务端会联网解析）",
    "# 数据根：%s —— 本文件是唯一真实数据。" % DATA_ROOT,
    "# 技能目录里的同名文件是指向本文件的软链，因此 裸K战法终端(:8600) 与 17:00 cron 日报",
    "# 读到的永远是同一份；网页上的增删 = 直接改写本文件。",
    "",
]

app = FastAPI(title="裸K战法终端", version=az.ENGINE_VERSION)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

_pool = ThreadPoolExecutor(max_workers=8)


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #

def _read_header(path: str) -> list[str] | None:
    """取出文件开头的注释块（用户自己写的说明要保留，不能被前端一次改写就抹掉）。"""
    if not os.path.exists(path):
        return None
    out = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            s = line.rstrip("\n")
            if s.startswith("#"):
                out.append(s)
            elif s.strip():
                break
    return out or None


def ensure_watchlist() -> str:
    """保证 WATCHLIST 存在，返回来源标记（供 /api/health 诊断）。首次启动自动就位。"""
    if os.path.exists(WATCHLIST):
        return "existing"
    os.makedirs(os.path.dirname(WATCHLIST), mode=0o700, exist_ok=True)
    # 1) 旧路径迁移（若旧路径已是软链，说明已迁移过，跳过以免自指）
    if os.path.exists(LEGACY_WATCHLIST) and not os.path.islink(LEGACY_WATCHLIST):
        body = open(LEGACY_WATCHLIST, encoding="utf-8-sig").read()
        with open(WATCHLIST, "w", encoding="utf-8") as f:
            f.write(body)
        return "migrated"
    # 2) 仓库模板播种（换台电脑 clone 后即用）
    if os.path.exists(WATCHLIST_EXAMPLE):
        body = open(WATCHLIST_EXAMPLE, encoding="utf-8-sig").read()
        with open(WATCHLIST, "w", encoding="utf-8") as f:
            f.write(body)
        return "seeded-from-example"
    # 3) 兜底：空表（只有表头）
    with open(WATCHLIST, "w", encoding="utf-8") as f:
        f.write("\n".join(WATCH_HEADER).rstrip("\n") + "\n")
    return "created-empty"


def read_watchlist() -> list[dict]:
    ensure_watchlist()
    out = []
    with open(WATCHLIST, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            out.append({"query": parts[0], "name": " ".join(parts[1:]) if len(parts) > 1 else ""})
    return out


def write_watchlist(rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(WATCHLIST), mode=0o700, exist_ok=True)
    lines = list(_read_header(WATCHLIST) or WATCH_HEADER)
    if lines[-1].strip():
        lines.append("")
    lines += [" ".join(x for x in (r["query"], (r.get("name") or "").strip()) if x) for r in rows]
    with open(WATCHLIST, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def build_report(query: str, days: int = 250, with_quote: bool = True) -> dict:
    hit = ds.resolve(query)
    bars, source = ds.fetch_daily_auto(hit["symbol"], days)
    today = bars[-1]["date"]

    quote = None
    if with_quote:
        try:
            rows = ds.fetch_quote([hit["symbol"]])
            quote = rows[0] if rows else None
        except Exception:
            quote = None

    prev = hist.last_before(hit["symbol"], today)
    # 注意用 bar_is_complete 而不是 is_trading_now：午休/盘前市场不交易，
    # 但当日K线一样是半截的。
    is_intraday = not ds.bar_is_complete(bars[-1]["date"])
    report = az.analyze(
        bars,
        name=hit["name"],
        code=hit["code"],
        symbol=hit["symbol"],
        quote=quote,
        prev=prev,
        is_intraday=is_intraday,
    )
    report["source"] = source
    report["kind"] = hit.get("kind")
    report["alternatives"] = hit.get("alternatives", [])
    # 暴露本次分析实际用到的实时快照，便于审计/复现（也是 /dev/prove_deterministic.py 做
    # 严格可复现对比所必需的：没有它就无法让两边看到完全相同的输入）
    report["quote_used"] = quote
    report["bars"] = [
        {"date": b["date"], "open": b["open"], "high": b["high"],
         "low": b["low"], "close": b["close"], "vol": b["vol"]}
        for b in bars
    ]
    # 盘中快照不落盘：剧本触发价是按未完成的当日K线算的，若存进历史，
    # 次日的"事后验证"就会拿一个半截基准去判定命中，结论不可信。
    # 收盘后重新分析会覆盖同一 date 的记录，所以不落盘也不会丢数据。
    if is_intraday:
        report["history_saved"] = False
        report["warnings"].append("盘中快照不写入历史（收盘后重新分析才进入事后验证链路）")
    else:
        hist.save({k: v for k, v in report.items() if k != "bars"})
        report["history_saved"] = True
    return report


# --------------------------------------------------------------------------- #
# 路由
# --------------------------------------------------------------------------- #

# 启动即就位（缺文件时自动迁移/播种）。失败也不能挡住服务启动。
try:
    WL_ORIGIN = ensure_watchlist()
except Exception as _e:  # noqa: BLE001
    WL_ORIGIN = "error: %s" % _e


@app.get("/api/health")
def health():
    return {"ok": True, "engine": az.ENGINE_VERSION, "watchlist": WATCHLIST,
            "watchlist_origin": WL_ORIGIN, "data_root": DATA_ROOT,
            "trading_now": ds.is_trading_now()}


@app.get("/api/search")
def api_search(q: str = Query(..., min_length=1)):
    return {"results": ds.search(q, limit=10)}


@app.get("/api/analyze")
def api_analyze(q: str = Query(..., min_length=1), days: int = 250):
    try:
        return build_report(q, days=days)
    except ds.DataSourceError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/api/kline")
def api_kline(symbol: str, count: int = 250):
    try:
        bars, source = ds.fetch_daily_auto(symbol, count)
        return {"symbol": symbol, "source": source, "bars": bars}
    except ds.DataSourceError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/watchlist")
def api_watchlist():
    rows = read_watchlist()

    def one(r):
        try:
            hit = ds.resolve(r["query"])
            return {**r, "symbol": hit["symbol"], "name": hit["name"] or r["name"],
                    "code": hit["code"], "kind": hit.get("kind")}
        except Exception as e:
            return {**r, "symbol": None, "error": str(e)}

    items = list(_pool.map(one, rows)) if rows else []
    quotes = {}
    symbols = [i["symbol"] for i in items if i.get("symbol")]
    if symbols:
        try:
            for q_ in ds.fetch_quote(symbols):
                quotes[q_["symbol"]] = q_
        except Exception:
            pass
    for i in items:
        i["quote"] = quotes.get(i.get("symbol") or "")
    return {"items": items, "trading_now": ds.is_trading_now(), "path": WATCHLIST}


class WatchAction(BaseModel):
    action: str
    query: str


@app.post("/api/watchlist")
def api_watchlist_mutate(body: WatchAction):
    rows = read_watchlist()
    if body.action == "add":
        hit = ds.resolve(body.query)
        if any(r["query"] in (hit["code"], hit["symbol"]) for r in rows):
            return {"ok": True, "changed": False, "items": read_watchlist()}
        rows.append({"query": hit["code"], "name": hit["name"]})
    elif body.action == "remove":
        target = body.query.strip()
        before = len(rows)
        rows = [r for r in rows if target not in (r["query"], r.get("name"))]
        if len(rows) == before:
            raise HTTPException(status_code=404, detail="自选股中没有 %s" % target)
    else:
        raise HTTPException(status_code=400, detail="action 必须是 add 或 remove")
    write_watchlist(rows)
    return {"ok": True, "changed": True, "items": read_watchlist()}


@app.get("/api/history")
def api_history(symbol: str):
    return {"symbol": symbol, "rows": hist.recent(symbol, 60)}


# --------------------------------------------------------------------------- #
# 静态资源
# --------------------------------------------------------------------------- #

app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
@app.get("/index.html")
def index():
    return FileResponse(os.path.join(WEB, "index.html"))


@app.exception_handler(ds.DataSourceError)
def _ds_err(_, exc: ds.DataSourceError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("NAKEDK_PORT", "8600"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
