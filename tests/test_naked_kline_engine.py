#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""裸K战法 · 六模块规则引擎 单元测试。

覆盖 P0/P1 修复项与输出契约，全部离线（不碰网络/历史落盘）。
"""

import os
import sys
from datetime import date as _date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from engine import analyzer as az


# --------------------------------------------------------------------------- #
# 构造工具
# --------------------------------------------------------------------------- #

def make_bar(date_str, o, h, l, c, vol=1000):
    return {"date": date_str, "open": o, "high": h, "low": l, "close": c, "vol": vol}


def baseline(n, o=10.0, c=10.0, h=10.1, l=9.9, vol=1000, start="2026-01-01"):
    """生成 n 根日期连续的普通K线。"""
    d = datetime.strptime(start, "%Y-%m-%d")
    bars = []
    for i in range(n):
        bars.append(make_bar((d + timedelta(days=i)).strftime("%Y-%m-%d"),
                             o, h, l, c, vol))
    return bars


def _m1(entity_pct=0.0, lower_pct=0.0, upper_pct=100.0):
    return {"entity_pct": entity_pct,
            "shadow": {"lower_pct": lower_pct, "upper_pct": upper_pct}}


def _m2(trend="横盘震荡"):
    return {"trend": trend}


def _m3(ice_price=9.5, supply_top=13.0, supply_bottom=12.0,
        supply_in_zone=False, demand_in_zone=False):
    return {
        "ice": {"price": ice_price},
        "supply": {"top": supply_top, "bottom": supply_bottom,
                   "in_zone": supply_in_zone},
        "demand": {"top": 8.0, "bottom": 6.0, "in_zone": demand_in_zone},
        "in_zone": supply_in_zone or demand_in_zone,
    }


# --------------------------------------------------------------------------- #
# P0-1 阴包阳
# --------------------------------------------------------------------------- #

def test_engulfing_true():
    bars = baseline(38)
    bars.append(make_bar("2026-03-01", 10.0, 10.6, 9.9, 10.5))   # 前阳
    bars.append(make_bar("2026-03-02", 10.6, 10.8, 9.7, 9.8))     # 后阴吞没
    m2 = az._module2(bars)
    assert m2["is_engulfing"] is True


def test_engulfing_false_for_plain_down_bar():
    # 普通阴线：开盘落在前阳实体内部，不吞没 —— 旧逻辑会误判为阴包阳
    bars = baseline(38)
    bars.append(make_bar("2026-03-01", 10.0, 10.6, 9.9, 10.5))   # 前阳
    bars.append(make_bar("2026-03-02", 10.3, 10.5, 9.8, 9.9))     # 普通阴线
    m2 = az._module2(bars)
    assert m2["is_engulfing"] is False


# --------------------------------------------------------------------------- #
# P0-2 B 区间始终有序
# --------------------------------------------------------------------------- #

def test_module4_b_range_ordered_extreme_doji():
    # O == C == L 的极端 bar（十字星且无下影），旧逻辑会出现 low > high
    bars = [make_bar("2026-01-01", 10.0, 12.0, 10.0, 10.0)]
    m4 = az._module4(bars, _m1(), _m2(), _m3())
    b = m4["scenarios"]["B"]
    assert b["low"] <= b["high"]
    assert b["low"] == pytest.approx(10.0)
    assert b["high"] == pytest.approx(10.6)


# --------------------------------------------------------------------------- #
# P0-3 止损方向
# --------------------------------------------------------------------------- #

def test_stop_loss_bullish_below_ice():
    # 上升趋势 + 收阳 -> 看涨反转，止损应在冰线下方
    bars = [make_bar("2026-01-01", 10.0, 12.0, 9.0, 11.0)]
    m4 = az._module4(bars, _m1(), _m2("上升趋势"), _m3(ice_price=9.0))
    assert m4["stop_loss"] < 9.0
    assert "下方" in m4["stop_note"]
    assert m4["resistance"] == pytest.approx(13.0)  # 压力位 = 供应区上沿，与止损分离


def test_stop_loss_bearish_above_supply():
    # 下跌趋势 + 收阴 -> 下跌延续，止损应在供应区上方
    bars = [make_bar("2026-01-01", 11.0, 12.0, 9.0, 10.0)]
    m4 = az._module4(bars, _m1(), _m2("下跌趋势"), _m3(supply_top=13.0))
    assert m4["stop_loss"] > 13.0
    assert "上方" in m4["stop_note"]


# --------------------------------------------------------------------------- #
# P0-5b / 冰线优先级1 倒序搜索
# --------------------------------------------------------------------------- #

def test_ice_priority1_reverse_search_picks_recent():
    n = 25
    bars = baseline(n)
    bars[-1] = make_bar(bars[-1]["date"], 10.9, 11.2, 10.8, 11.0, 1000)
    # 较旧候选（i=15）：光头大阳 open=10.0
    bars[15] = make_bar(bars[15]["date"], 10.0, 10.5, 10.0, 10.5, 5000)
    # 较新候选（i=21）：光头大阳 open=10.8
    bars[21] = make_bar(bars[21]["date"], 10.8, 11.3, 10.8, 11.3, 5000)
    ice = az._ice_line(bars)
    assert ice["priority"] == 1
    assert ice["price"] == pytest.approx(10.8)


# --------------------------------------------------------------------------- #
# P0-5c / P3、P4 被偏离闸门拒绝时记录进 rejected
# --------------------------------------------------------------------------- #

def test_ice_p3_p4_rejected_recorded():
    n = 30
    bars = baseline(n, o=10.0, c=10.0, h=10.05, l=9.95, vol=1000)
    # 跳空缺口：i=10 当日最低高于前一日最高 * 1.005
    bars[10] = make_bar(bars[10]["date"], 10.3, 10.4, 10.2, 10.3, 1000)
    # 今日远离平台/缺口，迫使各优先级被偏离闸门拒绝
    bars[-1] = make_bar(bars[-1]["date"], 12.0, 12.3, 11.9, 12.0, 1000)
    ice = az._ice_line(bars)
    priorities = {r["priority"] for r in ice["rejected"]}
    assert 3 in priorities
    assert 4 in priorities


# --------------------------------------------------------------------------- #
# P0-4 verify_previous 冰线漂移按角色区分
# --------------------------------------------------------------------------- #

def _prev(role):
    return {
        "date": "2026-01-10",
        "playbook": {
            "scenarios": {
                "A": {"trigger": 11.0},
                "B": {"low": 9.8, "high": 10.2},
                "C": {"trigger": 9.0},
            },
            "dominant": "B",
            "probabilities": {"A": 30, "B": 40, "C": 30},
        },
        "levels": {
            "ice": {"price": 10.0, "role": role},
            "supply": {"top": 12.0, "bottom": 11.0},
        },
    }


def test_verify_support_broken_on_close_below():
    after = [make_bar("2026-01-11", 10.1, 10.3, 9.6, 9.7)]
    v = az.verify_previous(_prev("support"), after, "2026-01-12")
    assert v["drift"]["ice_broken"] is True
    assert v["drift"]["ice_label"] == "跌破冰线（支撑失效）"
    assert v["drift"]["ice_break_date"] == "2026-01-11"


def test_verify_resistance_break_on_close_above():
    after = [make_bar("2026-01-11", 9.9, 10.4, 9.8, 10.3)]
    v = az.verify_previous(_prev("resistance"), after, "2026-01-12")
    assert v["drift"]["ice_broken"] is True
    assert v["drift"]["ice_label"] == "站上冰线（阻力突破）"
    assert v["drift"]["ice_break_date"] == "2026-01-11"


def test_verify_resistance_not_broken_on_close_below():
    # 阻力位上方，收盘在其下方不叫“突破”
    after = [make_bar("2026-01-11", 10.1, 10.2, 9.7, 9.8)]
    v = az.verify_previous(_prev("resistance"), after, "2026-01-12")
    assert v["drift"]["ice_broken"] is False
    assert v["drift"]["ice_label"] == "未突破（阻力仍有效）"


# --------------------------------------------------------------------------- #
# P0-6 十字星不进入阴线修正
# --------------------------------------------------------------------------- #

def test_doji_not_in_down_correction():
    bars = [make_bar("2026-01-01", 10.0, 11.0, 9.0, 10.0)]  # C == O 十字星
    m4 = az._module4(bars, _m1(entity_pct=0.0), _m2("横盘震荡"), _m3())
    joined = "".join(m4["corrections"])
    assert "十字星" in joined
    assert "大阴线跌幅" not in joined
    assert "阴线幅度" not in joined


# --------------------------------------------------------------------------- #
# P0-8 B 剧本判定：不再把“从未触发”算作 B
# --------------------------------------------------------------------------- #

def test_verify_b_scenario_requires_close_in_range():
    prev = _prev("support")
    # 后续收盘既不在 A/C 触发、也不落在 B 区间内 -> 未触发，而非 B
    after = [make_bar("2026-01-11", 10.9, 11.1, 10.8, 10.9)]  # 高于 B 区间且未破 A(11.0)
    v = az.verify_previous(prev, after, "2026-01-12")
    assert v["actual_scenario"] == "未触发"
    assert v["verdict"] == "未触发"


def test_verify_b_scenario_hit_when_close_in_range():
    prev = _prev("support")
    after = [make_bar("2026-01-11", 10.0, 10.3, 9.9, 10.0)]  # 收盘落在 9.8~10.2 区间
    v = az.verify_previous(prev, after, "2026-01-12")
    assert v["actual_scenario"] == "B"
    assert v["verdict"] == "命中"


# --------------------------------------------------------------------------- #
# 输出契约：analyze 21+ 根 bars 全字段
# --------------------------------------------------------------------------- #

def test_analyze_full_structure():
    bars = baseline(60, o=10.0, c=10.3, h=10.4, l=9.95, vol=1200)
    rep = az.analyze(bars, "测试标的", "TEST", "TEST")
    for k in ("m1_kline", "m2_context", "levels", "playbook", "intraday",
              "verification", "chart_levels", "warnings"):
        assert k in rep
    pb = rep["playbook"]
    assert pb["scenarios"]["A"]["prob"] + pb["scenarios"]["B"]["prob"] \
        + pb["scenarios"]["C"]["prob"] == 100
    assert rep["levels"]["ice"]["price"] > 0
    assert rep["engine_version"] == "2.0.2"


def test_analyze_rejects_insufficient_bars():
    with pytest.raises(ValueError):
        az.analyze(baseline(20), "x", "x", "x")


# --------------------------------------------------------------------------- #
# 2.0.2：十字星三态贯穿剧本逻辑
# --------------------------------------------------------------------------- #

def test_doji_sideways_not_bearish_labels():
    # 横盘 + 十字星：不应返回“空头试探/真破位”
    bars = [make_bar("2026-01-01", 10.0, 11.0, 9.0, 10.0)]
    m4 = az._module4(bars, _m1(), _m2("横盘震荡"), _m3())
    assert m4["scenarios"]["A"]["label"] == "方向待定"
    assert m4["scenarios"]["A"]["label"] != "空头试探"
    assert m4["scenarios"]["C"]["label"] != "真破位"


def test_doji_uptrend_not_shakeout():
    # 上升趋势 + 十字星：不应返回“震仓洗盘”
    bars = [make_bar("2026-01-01", 10.0, 11.0, 9.0, 10.0)]
    m4 = az._module4(bars, _m1(), _m2("上升趋势"), _m3())
    assert m4["scenarios"]["A"]["label"] == "趋势暂歇"
    assert m4["scenarios"]["A"]["label"] != "震仓洗盘"


def test_doji_direction_neutral_not_bullish():
    # 十字星不应进入 bullish 止损分支
    bars = [make_bar("2026-01-01", 10.0, 11.0, 9.0, 10.0)]
    m4 = az._module4(bars, _m1(), _m2("横盘震荡"),
                     _m3(ice_price=9.0, supply_top=13.0))
    assert m4["direction"] == "neutral"
    assert "方向未定" in m4["stop_note"]
    # 中性 stop 取供应区上沿上方 1%，不是 bullish 的冰线下方
    assert m4["stop_loss"] > m4["resistance"]


# --------------------------------------------------------------------------- #
# 2.0.2：B 区间 / A / C 触发互不包含
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("o,h,l,c", [
    (10.0, 12.0, 10.0, 10.0),  # O == C == L（光脚平开十字星）
    (12.0, 12.0, 10.0, 12.0),  # O == C == H（光头平开十字星）
    (10.0, 11.0, 9.0, 10.0),   # O == C（普通十字星）
])
def test_module4_playbook_invariants(o, h, l, c):
    bars = [make_bar("2026-01-01", o, h, l, c)]
    m4 = az._module4(bars, _m1(), _m2("横盘震荡"), _m3())
    b = m4["scenarios"]["B"]
    a_trigger = m4["scenarios"]["A"]["trigger"]
    c_trigger = m4["scenarios"]["C"]["trigger"]
    assert b["low"] <= b["high"]
    assert a_trigger > b["high"]
    assert c_trigger < b["low"]


# --------------------------------------------------------------------------- #
# 2.0.2：verify_previous 日期类型混用不抛异常
# --------------------------------------------------------------------------- #

def test_verify_prev_date_object_bar_string():
    prev = _prev("support")
    prev["date"] = _date(2026, 1, 10)              # date 对象
    after = [make_bar("2026-01-11", 10.0, 10.3, 9.9, 10.0)]  # 字符串
    v = az.verify_previous(prev, after, "2026-01-12")
    assert v is not None


def test_verify_prev_string_bar_date_object():
    prev = _prev("support")
    prev["date"] = "2026-01-10"                    # 字符串
    after = [make_bar(_date(2026, 1, 11), 10.0, 10.3, 9.9, 10.0)]  # date 对象
    v = az.verify_previous(prev, after, "2026-01-12")
    assert v is not None


def test_verify_bad_date_warning_no_exception():
    prev = _prev("support")
    after = [
        make_bar("2026-01-11", 10.0, 10.3, 9.9, 10.0),
        make_bar("not-a-date", 10.0, 10.3, 9.9, 10.0),   # 坏日期
        make_bar("2026-01-12", 10.1, 10.4, 10.0, 10.1),
    ]
    v = az.verify_previous(prev, after, "2026-01-13")
    assert v is not None
    assert any("无法解析" in w for w in v["warnings"])


# --------------------------------------------------------------------------- #
# 2.0.2：parse_warnings 去重
# --------------------------------------------------------------------------- #

def test_parse_warnings_deduplicated():
    prev = _prev("support")
    after = [
        make_bar("2026-01-11", 10.0, 10.3, 9.9, 10.0),
        make_bar("bad-1", 10.0, 10.3, 9.9, 10.0),
        make_bar("bad-2", 10.0, 10.3, 9.9, 10.0),
        make_bar("bad-3", 10.0, 10.3, 9.9, 10.0),
    ]
    v = az.verify_previous(prev, after, "2026-01-13")
    assert v is not None
    parse_msgs = [w for w in v["warnings"] if "无法解析" in w]
    assert len(parse_msgs) == 1          # 多根坏日期合并为一条
    assert "3" in parse_msgs[0]          # 计数 3 根


# --------------------------------------------------------------------------- #
# 2.0.2：chart_levels 结构
# --------------------------------------------------------------------------- #

def test_chart_levels_stop_and_resistance():
    bars = baseline(60, o=10.0, c=10.3, h=10.4, l=9.95, vol=1200)
    rep = az.analyze(bars, "测试标的", "TEST", "TEST")
    cl = {item["key"]: item for item in rep["chart_levels"]}
    assert "stop" in cl
    assert "压力" not in cl["stop"]["label"]
    assert "resistance" in cl
    assert cl["resistance"]["price"] == rep["playbook"]["resistance"]


# --------------------------------------------------------------------------- #
# 2.0.2：文档与版本
# --------------------------------------------------------------------------- #

def test_engine_version_and_error_message():
    assert az.ENGINE_VERSION == "2.0.2"
    with pytest.raises(ValueError) as exc:
        az.analyze(baseline(20), "x", "x", "x")
    assert "六模块" in str(exc.value)
    assert "五模块" not in str(exc.value)
