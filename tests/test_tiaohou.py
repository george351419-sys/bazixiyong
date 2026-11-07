# -*- coding: utf-8 -*-
"""调候用神模块单元测试 —— 以《穷通宝鉴_调候用神表_定本.md》十干逐月详表为准。

运行：
  python3 -m pytest tests/test_tiaohou.py -q
  （或直接：python3 tests/test_tiaohou.py）

覆盖：底表 121 格完整性 / 定本拍板口径 / 前版已删天干 / 无定序格 /
      条件用不并列 / 节气分段 / 原局透藏 / 忌抽取 / engine 集成 / 输入兼容。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bazi_core import metadata as M
from bazi_core.tiaohou import (compute_tiaohou, lookup, format_tiaohou,
                               select_row, SOURCE_VERSION)
from bazi_core.tiaohou_data import TIAOHOU_TABLE as T
from bazi_core.engine import analyze

GAN, ZHI = M.GAN, M.ZHI


def chart(s):
    """'庚午 甲申 庚子 壬午' -> PRD dict。"""
    parts = s.split()
    assert len(parts) == 4
    keys = ("year", "month", "day", "hour")
    return {keys[i]: {"gan": p[0], "zhi": p[1]} for i, p in enumerate(parts)}


def rows(g, z):
    return [r for r in T if r["day_gan"] == g and r["month_zhi"] == z]


# ---------------------------------------------------------------- 底表
def test_table_integrity():
    assert len(T) == 121, "定本详表应 121 行（120 格 + 乙·酉拆一段）"
    for g in GAN:
        for z in ZHI:
            assert rows(g, z), "缺格 %s·%s" % (g, z)
    assert len(rows("乙", "酉")) == 2
    for r in T:
        assert r["quote"] and r["note"], "缺原句／备注：%s" % r["month_label"]
        assert all(x in GAN for x in r["general"])
        assert all(x in GAN for c in r["conditions"] for x in c["gans"])


def test_ding_hai_default_is_jia_first():
    """拍板口径：丁·亥 默认甲先；庚先只在另读，不覆盖默认序列。"""
    r = rows("丁", "亥")[0]
    assert r["general"] == ["甲", "庚"]
    assert r["alt_read"] and r["alt_read"][0]["gans"] == ["庚", "甲"]
    out = compute_tiaohou("庚午 丁亥 丁卯 庚子")
    assert out["yongshen"] == ["甲", "庚"] and out["zhuyong"] == "甲"
    assert out["xiyong"]["favored"] == ["甲", "庚"]
    assert SOURCE_VERSION.find("丁·亥 默认甲先") >= 0


def test_deleted_gans_not_in_general():
    """定本删掉的 3 处提要残留不得回到通用序列。"""
    assert "己" not in rows("甲", "卯")[0]["general"]
    assert "丙" not in rows("甲", "丑")[0]["general"]
    for z in ("子", "丑"):
        assert "戊" not in rows("己", z)[0]["general"]


def test_no_order_cells():
    """原书明言无定序／并用的格：不作首字加权。"""
    for g, z in (("丙", "亥"), ("庚", "巳"), ("丁", "午"), ("丁", "申"),
                 ("丁", "酉"), ("辛", "午"), ("辛", "子")):
        r = rows(g, z)[0]
        assert r["no_order"], "%s·%s 应标无定序" % (g, z)
        assert compute_tiaohou(_chart_for(g, z))["zhuyong"] is None


def _chart_for(day_gan, month_zhi):
    return {"gans": ["甲", "甲", day_gan, "甲"],
            "zhis": ["子", month_zhi, "子", "子"]}


def test_conditions_not_flattened():
    """条件用一律不进默认通用序列（癸·丑 丁、辛·子 戊／甲）。"""
    chou = rows("癸", "丑")[0]
    assert chou["general"] == ["丙", "壬"]
    assert any("丁" in c["gans"] for c in chou["conditions"])
    zi = rows("辛", "子")[0]
    cond_gans = [x for c in zi["conditions"] for x in c["gans"]]
    assert "戊" in cond_gans and "甲" in cond_gans
    assert "戊" not in zi["general"] and "甲" not in zi["general"]


def test_ji_extraction():
    """忌神短语从备注／原句机械抽取，几处定本明言的忌要能命中。"""
    assert "癸" in rows("辛", "申")[0]["ji_gans"]
    assert "戊" in rows("壬", "酉")[0]["ji_gans"]
    assert "戊" in rows("辛", "卯")[0]["ji_gans"]
    assert all(p for p in rows("辛", "申")[0]["ji_phrases"])


# ---------------------------------------------------------------- 分段
def test_yi_you_segment():
    und = compute_tiaohou("辛酉 丁酉 乙丑 丙戌")
    assert und["segment"]["undetermined"] is True
    assert und["yongshen"] == ["癸"]            # 段A 代表值
    assert len(und["segment"]["candidates"]) == 2
    a = compute_tiaohou("辛酉 丁酉 乙丑 丙戌", segment="段A")
    b = compute_tiaohou("辛酉 丁酉 乙丑 丙戌", segment="秋分后")
    assert a["yongshen"] == ["癸"]
    assert b["yongshen"] == ["丙", "癸"]
    assert b["segment"]["status"] == "selected"


def test_half_month_and_jieqi_segments():
    wu = compute_tiaohou("甲午 甲午 乙未 甲申", segment="下半月")
    assert wu["yongshen"] == ["丙", "癸"]
    chen = compute_tiaohou("甲辰 甲辰 癸酉 甲寅", segment="清明后")
    assert chen["yongshen"] == ["丙"]
    chen2 = compute_tiaohou("甲辰 甲辰 癸酉 甲寅", segment="谷雨后")
    assert chen2["yongshen"] == ["丙", "辛", "甲"]
    # 节气后 15 日切点为工程约定，须标 basis
    auto = compute_tiaohou(dict(chart("甲午 甲午 乙未 甲申"), solar_term_day=20))
    assert auto["yongshen"] == ["丙", "癸"]
    assert "工程约定" in (auto["segment"]["basis"] or "")


def test_lookup_without_chart():
    r = lookup("戊", "寅")["row"]
    assert r["general"] == ["丙", "甲", "癸"]
    assert lookup("乙", "酉")["segment"]["status"] == "undetermined"


# ---------------------------------------------------------------- 原局比对
def test_presence():
    out = compute_tiaohou("庚午 丁亥 丁卯 庚子")
    assert out["presence"]["庚"]["state"] == "透干"
    assert "年" in out["presence"]["庚"]["tou_at"]
    assert out["presence"]["甲"]["state"] == "仅藏"
    assert "月" in out["presence"]["甲"]["cang_at"]     # 亥藏甲
    assert "甲" not in out["xiyong"]["missing"]   # 仅藏不算「原局无」


def test_condition_trigger_is_conservative():
    out = compute_tiaohou("丙子 庚子 辛未 壬辰")
    assert out["xiyong"]["pending_conditions"], "条件用应保留在待判／未触发列表"
    for c in out["conditions"]:
        assert c["auto_triggered"] in (True, False, None)
    # 多分支条件不得硬判「未触发」
    assert not any(c["auto_triggered"] is False and any(
        "多分支" in x["kind"] for x in c["checks"]) for c in out["conditions"])


def test_input_forms():
    a = compute_tiaohou("庚午 甲申 庚子 壬午")
    b = compute_tiaohou(chart("庚午 甲申 庚子 壬午"))
    c = compute_tiaohou({"gans": list("庚甲庚壬"), "zhis": list("午申子午")})
    assert a["yongshen"] == b["yongshen"] == c["yongshen"]
    assert isinstance(format_tiaohou(a), str) and "调候维度" in format_tiaohou(a)


# ---------------------------------------------------------------- 引擎集成
def test_engine_integration():
    out = analyze(chart("庚午 甲申 庚子 壬午"))
    assert out["modules"]["tiaohou"] == "done"
    assert out["engine_version"].endswith("tiaohou_v1")
    assert out["tiaohou"]["ok"] is True
    assert out["final_xiyong"]["tiaohou"]["yongshen"] == out["tiaohou"]["yongshen"]
    # V1 不加权：final_xiyong 仍等于旺衰维度，调候不得混入
    assert out["final_xiyong"]["favored"] == out["xiyong_wangshuai"]["favored"]
    assert "不加权" in out["final_xiyong"]["note"]
    assert out["tiaohou"]["caveat"].find("非定以为用也") >= 0


def test_engine_segment_passthrough():
    c = chart("辛酉 丁酉 乙丑 丙戌")
    out = analyze(c, tiaohou_segment="段B")
    assert out["tiaohou"]["yongshen"] == ["丙", "癸"]
    assert out["final_xiyong"]["tiaohou"]["yongshen"] == ["丙", "癸"]


def test_jie_name_segment_inference():
    """排盘给出节气名时，按原书节气分段取用（白露→段A／秋分→段B）。"""
    c = dict(chart("辛酉 丁酉 乙丑 丙戌"), jie_name="白露")
    assert compute_tiaohou(c)["yongshen"] == ["癸"]
    c2 = dict(chart("辛酉 丁酉 乙丑 丙戌"), jie_name="秋分")
    out = compute_tiaohou(c2)
    assert out["yongshen"] == ["丙", "癸"]
    assert "原书节气分段" in (out["segment"]["basis"] or "")


def test_bad_input_raises():
    for bad in ("XXXX 甲申 庚子 壬午", "庚午", 123):
        try:
            compute_tiaohou(bad)
            assert False, "非法输入应抛 ValueError：%r" % (bad,)
        except ValueError:
            pass


def test_all_120_cells_run():
    """全 120 格都能算出结果、格式化不抛异常。"""
    ok = 0
    for g in GAN:
        for z in ZHI:
            c = {"gans": ["甲", "甲", g, "甲"], "zhis": ["子", z, "子", "子"]}
            r = compute_tiaohou(c)
            assert r["ok"] and isinstance(r["yongshen"], list)
            assert "调候维度" in format_tiaohou(r, verbose=False)
            ok += 1
    assert ok == 120


def test_select_row_raises_on_bad_input():
    try:
        select_row("X", "寅")
        assert False, "非法日干应抛错"
    except ValueError:
        pass


def test_all():
    """直接运行入口（不依赖 pytest）。"""
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and k != "test_all"]
    for fn in fns:
        fn()
    print("调候模块单元测试：%d 用例全部通过" % len(fns))
    return 0


if __name__ == "__main__":
    sys.exit(test_all())
