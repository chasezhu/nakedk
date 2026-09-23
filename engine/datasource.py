#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""裸K终端 · 数据层

主源: 腾讯财经 (smartbox / fqkline / qt)
    - 实测返回 access-control-allow-origin: * ，浏览器可直连
    - 无需注册、无需 key、前复权、90+ 根日K
备源: TickFlow (免费版滞后 1-2 自然日，见 naked-kline-analyst 技能坑7)

对外只暴露 4 个函数:
    search(q)                -> 名称/代码模糊搜索
    resolve(q)               -> 唯一化 {symbol, code, name, market, kind}
    fetch_daily(symbol, ...) -> 日K bars
    fetch_quote(symbols)     -> 实时快照
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
import urllib.parse
import urllib.request

__all__ = [
    "DataSourceError",
    "search",
    "resolve",
    "fetch_daily",
    "fetch_quote",
    "PROBE_MARKETS",
]


class DataSourceError(RuntimeError):
    """所有数据源都失败时抛出。"""


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://gu.qq.com/",
}

PROBE_MARKETS = ("sh", "sz", "bj")

# smartbox 的类型后缀 -> 人话
_KIND_MAP = {
    "GP-A": "A股",
    "GP-B": "B股",
    "ZS": "指数",
    "QZ": "权证",
    "JJ": "基金",
    "ZQ": "债券",
}


def _http(url: str, gbk: bool = False, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    raw = urllib.request.urlopen(req, timeout=timeout).read()
    return raw.decode("gbk", errors="replace") if gbk else raw.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- #
# 符号解析
# --------------------------------------------------------------------------- #

def search(q: str, limit: int = 10) -> list[dict]:
    """用腾讯 smartbox 搜名称或代码，返回候选列表。"""
    q = (q or "").strip()
    if not q:
        return []
    url = "https://smartbox.gtimg.cn/s3/?q=%s&t=all" % urllib.parse.quote(q)
    try:
        txt = _http(url, gbk=True)
    except Exception:
        return []

    m = re.search(r'"(.*)"', txt, re.S)
    if not m or not m.group(1):
        return []

    out: list[dict] = []
    for item in m.group(1).split("^"):
        parts = item.split("~")
        if len(parts) < 4:
            continue
        market, code, name_esc, pinyin = parts[0], parts[1], parts[2], parts[3]
        kind_raw = parts[4] if len(parts) > 4 else ""
        try:
            name = json.loads('"%s"' % name_esc)
        except Exception:
            name = name_esc
        out.append(
            {
                "symbol": "%s%s" % (market, code),
                "code": code,
                "name": name,
                "market": market,
                "kind": _KIND_MAP.get(kind_raw.upper(), kind_raw or "其他"),
                "pinyin": pinyin.lower(),
            }
        )
        if len(out) >= limit * 3:
            break

    # A股优先，再指数，其余靠后
    order = {"A股": 0, "指数": 1, "B股": 2, "基金": 3, "债券": 4}
    out.sort(key=lambda x: order.get(x["kind"], 9))
    return out[:limit]


def _guess_prefixes(code: str) -> list[str]:
    """按 naked-kline-analyst 技能里的规则猜市场前缀（顺序即优先级）。"""
    if code.startswith("399") or code.startswith("159") or code.startswith("159"):
        return ["sz"]
    if code.startswith("000") and len(code) == 6 and code[3:] in {"001", "300", "905", "016", "688", "903", "852"}:
        return ["sh"]
    if code[0] in "69":
        return ["sh"]
    if code[0] in "03":
        return ["sz"]
    if code[0] == "8" or code[:2] in {"43", "87"}:
        return ["bj"]
    return list(PROBE_MARKETS)


def resolve(q: str) -> dict:
    """把用户输入（代码或名称）唯一化成一个标的。"""
    q = (q or "").strip()
    if not q:
        raise DataSourceError("请输入股票代码或名称")

    # 已经带市场前缀的完整符号（前端歧义切换会直接传 sz000001 / sh000001）
    m = re.fullmatch(r"(sh|sz|bj)(\d{6})", q.lower())
    if m:
        quote = fetch_quote([q.lower()])
        if quote:
            row = quote[0]
            mkt, code = m.group(1), m.group(2)
            # 指数只能靠前缀判定：沪市 000xxx/950xxx/880xxx、深市 399xxx 才是指数。
            # 只看"以 000 开头"会把深市主板股票 sz000001 平安银行误判成指数。
            is_index = (mkt == "sh" and code.startswith(("000", "950", "880"))) or \
                       (mkt == "sz" and code.startswith(("399", "1599")))
            chosen = {"symbol": row["symbol"], "code": row["code"], "name": row["name"],
                      "market": mkt, "kind": "指数" if is_index else "A股"}
            alts = [h for h in search(code, limit=10)
                    if h["symbol"] != chosen["symbol"] and h["code"] == code
                    and h["kind"] in ("A股", "指数", "B股")]
            if alts:
                chosen["alternatives"] = alts[:4]
            return chosen

    hits = search(q, limit=10)
    if not hits:
        # smartbox 挂了也要能干活：纯数字走规则猜前缀
        if re.fullmatch(r"\d{6}", q):
            for pre in _guess_prefixes(q):
                quote = fetch_quote(["%s%s" % (pre, q)])
                if quote:
                    row = quote[0]
                    return {
                        "symbol": row["symbol"],
                        "code": q,
                        "name": row["name"],
                        "market": pre,
                        "kind": "A股" if pre != "sh" or not q.startswith(("000", "88", "95")) else "指数",
                    }
        raise DataSourceError("找不到标的: %s" % q)

    def with_alts(chosen: dict) -> dict:
        # 6 位代码会撞车：000001 既是深市平安银行也是沪市上证指数。
        # 这里保留其它同名/同码候选，让前端给出切换入口，而不是猜死一个。
        # 只提示同类歧义（股票/指数）。smartbox 会用 6 位数字撞上基金代码，
        # 002709 就同时是一只货币基金，对交易者没有意义。
        alts = [h for h in hits
                if h["symbol"] != chosen["symbol"]
                and h["kind"] in ("A股", "指数", "B股")
                and (h["code"] == chosen["code"] or h["name"] == chosen["name"])]
        if alts:
            chosen = {**chosen, "alternatives": alts[:4]}
        return chosen

    # 名称精确命中优先，其次代码精确命中，再次第一个 A 股
    exact = [h for h in hits if h["name"] == q or h["code"] == q]
    if exact:
        return with_alts(exact[0])
    a_share = [h for h in hits if h["kind"] in ("A股", "指数")]
    return with_alts((a_share or hits)[0])


# --------------------------------------------------------------------------- #
# 日K
# --------------------------------------------------------------------------- #

def fetch_daily(symbol: str, count: int = 250, adjust: str = "qfq") -> list[dict]:
    """腾讯前复权日K。bars 升序，字段 date/open/high/low/close/vol。

    注意: 盘中调用时最后一根是当日未完成K线。
    """
    fmt = {"qfq": "qfq", "hfq": "hfq", "none": ""}[adjust]
    url = (
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        "?param=%s,day,,,%d,%s" % (symbol, count + 1, fmt)
    )
    payload = json.loads(_http(url, timeout=25))
    if payload.get("code") != 0:
        raise DataSourceError("腾讯接口返回 code=%s msg=%s" % (payload.get("code"), payload.get("msg")))

    node = (payload.get("data") or {}).get(symbol)
    if not node:
        raise DataSourceError("腾讯接口无 %s 数据" % symbol)

    # 前复权 key 名不固定（无复权时叫 day）
    key = next((k for k in (fmt + "day", "day", "qfqday", "hfqday") if node.get(k)), None)
    if not key:
        raise DataSourceError("%s 无日K字段: %s" % (symbol, list(node.keys())))

    bars: list[dict] = []
    for row in node[key]:
        if len(row) < 6:
            continue
        d = str(row[0])
        if len(d) == 8 and d.isdigit():  # 偶尔返回 YYYYMMDD
            d = "%s-%s-%s" % (d[:4], d[4:6], d[6:])
        bars.append(
            {
                "date": d,
                "open": float(row[1]),
                "close": float(row[2]),
                "high": float(row[3]),
                "low": float(row[4]),
                "vol": float(row[5]),
            }
        )
    if len(bars) < 2:
        raise DataSourceError("%s 日K数据不足 (%d 根)" % (symbol, len(bars)))
    return bars[-count:]


def fetch_daily_tickflow(symbol: str, count: int = 90) -> list[dict]:
    """TickFlow 备源。需要 os.chdir 到无 numpy 的目录，故用子进程隔离。

    路径全部不写死（换台电脑 clone 下来也能跑）：
      解释器   NAKEDK_PYTHON > ~/.local/bin/python3 > 当前 sys.executable
      临时目录 NAKEDK_TMP    > ~/.hermes/tmp（不存在则自动建）
      TickFlow 的 site-packages 只有真的存在才注入 sys.path
    """
    import subprocess

    code = symbol[2:] if symbol[:2] in PROBE_MARKETS else symbol
    tf_symbol = "%s.SZ" % code if symbol.startswith("sz") else "%s.SH" % code

    extra_path = os.path.expanduser("~/.local/lib/python3.10/site-packages")
    scratch = os.path.expanduser(os.environ.get("NAKEDK_TMP", "~/.hermes/tmp"))
    os.makedirs(scratch, exist_ok=True)
    py = os.environ.get("NAKEDK_PYTHON")
    if not py:
        cand = os.path.expanduser("~/.local/bin/python3")
        py = cand if os.path.exists(cand) else sys.executable

    script = r"""
import sys, os, datetime, json
_extra = %r
if os.path.isdir(_extra):
    sys.path.insert(0, _extra)
os.chdir(%r)
from tickflow import TickFlow
tf = TickFlow.free()
raw = tf.klines.get(%r, period="1d", count=%d, as_dataframe=False)
out = []
for i in range(len(raw['timestamp'])):
    ts = raw['timestamp'][i] / 1000
    out.append({
        'date': datetime.datetime.fromtimestamp(ts).strftime('%%Y-%%m-%%d'),
        'open': float(raw['open'][i]), 'close': float(raw['close'][i]),
        'high': float(raw['high'][i]), 'low': float(raw['low'][i]),
        'vol': float(raw['volume'][i]),
    })
print(json.dumps(out))
""" % (extra_path, scratch, tf_symbol, count)

    res = subprocess.run(
        [py, "-c", script],
        capture_output=True, text=True, timeout=90,
    )
    if res.returncode != 0:
        raise DataSourceError("TickFlow 失败: %s" % (res.stderr or "")[-300:])
    return json.loads(res.stdout.strip().splitlines()[-1])


def fetch_daily_auto(symbol: str, count: int = 250, adjust: str = "qfq") -> tuple[list[dict], str]:
    """带兜底的取数，返回 (bars, 数据源名)。"""
    try:
        return fetch_daily(symbol, count, adjust), "tencent"
    except Exception as primary_err:
        try:
            return fetch_daily_tickflow(symbol, min(count, 90)), "tickflow"
        except Exception as backup_err:
            raise DataSourceError(
                "腾讯与 TickFlow 均失败\n  腾讯: %s\n  TickFlow: %s" % (primary_err, backup_err)
            ) from primary_err


# --------------------------------------------------------------------------- #
# 实时快照
# --------------------------------------------------------------------------- #

def fetch_quote(symbols: list[str]) -> list[dict]:
    """腾讯实时快照。字段含义见 腾讯 qt.gtimg.cn 协议。"""
    if not symbols:
        return []
    txt = _http("https://qt.gtimg.cn/q=%s" % ",".join(symbols), gbk=True, timeout=15)
    out: list[dict] = []
    for line in txt.strip().split(";"):
        line = line.strip()
        if "=" not in line:
            continue
        lhs, _, rhs = line.partition("=")
        symbol = lhs.replace("v_", "").strip()
        fields = rhs.strip().strip('"').split("~")
        if len(fields) < 40:
            continue

        def num(i, default=0.0):
            try:
                return float(fields[i])
            except (ValueError, IndexError):
                return default

        out.append(
            {
                "symbol": symbol,
                "name": fields[1],
                "code": fields[2],
                "last": num(3),
                "prev_close": num(4),
                "open": num(5),
                "vol_hand": num(6),
                "time": fields[30],
                "chg": num(31),
                "chg_pct": num(32),
                "high": num(33),
                "low": num(34),
                "amount_wan": num(37),
                "turnover_pct": num(38),
                "pe": num(39),
                "amplitude_pct": num(43),
                "float_mktcap_yi": num(44),
                "total_mktcap_yi": num(45),
            }
        )
    return out


def is_trading_now(now: datetime.datetime | None = None) -> bool:
    """市场**此刻**是否在连续竞价（用于顶栏指示灯，不含节假日日历）。"""
    now = now or datetime.datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return (9 * 60 + 30 <= t <= 11 * 60 + 30) or (13 * 60 <= t <= 15 * 60)


def bar_is_complete(last_bar_date: str, now: datetime.datetime | None = None) -> bool:
    """当日K线是否已收盘定格。

    与 is_trading_now 是**两个不同问题**：午休（11:30-13:00）和盘前市场都不
    在交易，但当日 bar 同样未完成。只有 15:00 后才算定格。

    踩坑：曾用 is_trading_now 当"bar 是否完成"用，12:5x 午休期间把半截
    K线的分析当收盘结论写进了历史，事后验证的基准就不可信了。
    """
    now = now or datetime.datetime.now()
    if last_bar_date != now.strftime("%Y-%m-%d"):
        return True
    return now.hour * 60 + now.minute >= 15 * 60


if __name__ == "__main__":  # 自检
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "300768"
    hit = resolve(q)
    print("resolve:", hit)
    bars, src = fetch_daily_auto(hit["symbol"], 90)
    print("source: %s  bars: %d  %s -> %s" % (src, len(bars), bars[0]["date"], bars[-1]["date"]))
    for b in bars[-5:]:
        print("  ", b)
    print("quote:", fetch_quote([hit["symbol"]]))
