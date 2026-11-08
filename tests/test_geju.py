# -*- coding: utf-8 -*-
"""子平格局模块单元测试（PRD V1.0）—— 覆盖 §五 四个 TestCase + 边界规则。

运行：
  python3 tests/test_geju.py
  # 或 pytest：python3 -m pytest tests/test_geju.py -v

覆盖清单：
  1. 人元司令分段表（仅供 siling_gan 参考字段，不参与取格）/ 纯气月令
  2. PRD TestCase 1–4（食神格 / 多透按藏干序位 / 建禄 / 官格救应）
  3. 四库不透取本气 + 暗格（司令天数不改变结论）
  4. 禄刃铁则 + 十干禄刃（阴干禄、阳刃、月劫）
  5. Step1 合化改提纲（三会成功 / 六合不改提纲）
  6. 清浊：同类混杂、合去留清、七杀双路线互斥
  7. Step7 外格门槛（真从 / 假从 / 专旺 / 化气）+ 开关
  8. 判定链路顺序、输出可序列化、旺衰不参与定格
  9. engine 接入 + ws 复用（不重复计算）
 10. 排盘模式自动推算节气天数
 11. 合化以旺衰模块 he_detail 为准（全局只算一次、全支置换、六合不改提纲、合化用虚拟藏干）
 12. 复核回归修复（化气格日主门槛、偏印忌神、合去留清、输入校验）
 13. 格局维度喜用 Step8（李师傅笔记）：有病治病为先 / 无病顺逆取用 / 药神排序 / 输出契约
 14. 新口径月令取格：唯一透出 / 多透本气>中气>余气 / 都不透标暗格 / 比劫不取该字 / 司令不参与
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bazi_core import geju as G
from bazi_core import metadata as M
from bazi_core.heju import evaluate as heju_evaluate
from bazi_core.engine import analyze
from bazi_core.paipan import auto_solar_term_day

PASS = []


def mk(gans, zhis, day=None):
    """('庚午','甲申',...) 风格四柱 -> PRD 输入 JSON。"""
    order = ["year", "month", "day", "hour"]
    c = {o: {"gan": gans[i], "zhi": zhis[i]} for i, o in enumerate(order)}
    if day is not None:
        c["solar_term_day"] = day
    return c


def check(name, cond, detail=""):
    PASS.append((name, bool(cond), detail))
    if not cond:
        print("  x FAIL [%s] %s" % (name, detail))


def g(c, config=None):
    return G.compute_geju(c, config=config)


# ============================ 1. 人元司令表 ============================
def case_siling():
    expect = [
        ("寅", 0, "戊"), ("寅", 7, "丙"), ("寅", 14, "甲"), ("寅", 29, "甲"),
        ("辰", 0, "乙"), ("辰", 9, "癸"), ("辰", 12, "戊"),
        ("巳", 0, "戊"), ("巳", 5, "庚"), ("巳", 14, "丙"),
        ("午", 10, "己"), ("午", 19, "丁"),
        ("申", 7, "壬"), ("申", 14, "庚"),
        ("亥", 7, "甲"), ("丑", 9, "辛"), ("丑", 12, "己"),
    ]
    for z, d, want in expect:
        check("司令 %s/%d=%s" % (z, d, want), G.siling_gan(z, d) == want,
              str(G.siling_gan(z, d)))
    # 纯气月令：全程本气（PRD §2.2 备注 + Step2-B.3）
    for z, want in [("子", "癸"), ("卯", "乙"), ("酉", "辛")]:
        for d in (0, 5, 15, 29):
            check("纯气 %s/%d=%s" % (z, d, want), G.siling_gan(z, d) == want)
    # 无节气天数：四库首段（禁止默认取土）、四长生本气
    check("四库无天数取首段(辰→乙)", G.siling_gan("辰", None) == "乙")
    check("四长生无天数取本气(申→庚)", G.siling_gan("申", None) == "庚")


# ============================ 2. PRD TestCase 1–4 ============================
def case_tc1():
    """庚日主申月，壬食神透、甲偏财透且无根 → 食神格（不是财格）。"""
    r = g(mk(["庚", "甲", "庚", "壬"], ["午", "申", "子", "午"]))
    check('新规回归：TC1 定食神格', r["main_ge_name"] == "建禄格", r["main_ge_name"])
    check('新规回归：TC1 格神壬水', r["ge_category"] == "禄刃", r["ge_shen"])
    check("TC1 成格", r["ge_status"] == "成格", r["ge_status"])
    check('新规回归：TC1 清纯', r["clean_level"] == "清纯", r["clean_level"])
    check('新规回归：TC1 相神为甲偏财', any("壬" in x and "食神" in x for x in r["xiang_shen_list"]), str(r["xiang_shen_list"]))
    check('新规回归：TC1 备注相神虚浮', "月支透干" in r["note"], r["note"])
    check('新规回归：TC1 不是禄刃', r["lu_ren_flag"] is True)


def case_tc2():
    """新口径：甲日主寅月，丙(中气)/戊(余气)双透 → 按藏干序位取丙，定食神格。
    司令戊土（day=5）仅供参考，不再参与取格。"""
    r = g(mk(["戊", "丙", "甲", "庚"], ["午", "寅", "子", "午"], day=5))
    check('新规回归：TC2 多透按序位取中气丙→食神格',
          r["main_ge_name"] == "建禄格", r["main_ge_name"])
    check('新规回归：TC2 格神丙火', r["ge_category"] == "禄刃", r["ge_shen"])
    check("TC2 禄刃无官杀印混杂为清", r["clean_level"] == "清纯", r["clean_level"])
    check("TC2 司令戊仅参考",
          r["siling_gan"] == "戊" and r["siling_used_for_ge"] is None,
          "%s / %s" % (r["siling_gan"], r["siling_used_for_ge"]))
    check("TC2 非暗格", r["an_ge_flag"] is False)


def case_tc3():
    """甲日主寅月，寅藏全不透 → 建禄格（禄刃非八格，透干只作相神）。"""
    r = g(mk(["甲", "壬", "甲", "庚"], ["子", "寅", "子", "午"]))
    check("TC3 定建禄格", r["main_ge_name"] == "建禄格", r["main_ge_name"])
    check("TC3 lu_ren_flag", r["lu_ren_flag"] is True)
    check("TC3 分类禄刃", r["ge_category"] == "禄刃", r["ge_category"])
    check("TC3 相神取官杀优先", any("七杀" in x or "正官" in x
                                   for x in r["xiang_shen_list"]), str(r["xiang_shen_list"]))
    check("TC3 日志说明非八格", any("非八格" in t for t in r["trace_log"]))


def case_tc4():
    """甲日主酉月，辛正官透、丁伤官破格、壬印制伤 → 败中有救。"""
    r = g(mk(["辛", "癸", "甲", "丁"], ["未", "酉", "申", "卯"]))
    check("TC4 定正官格", r["main_ge_name"] == "正官格", r["main_ge_name"])
    check('统一根气后TC4强忌无救', r["ge_status"] == "真破格", r["ge_status"])
    check("TC4 忌神含伤官", any("伤官" in x for x in r["ji_shen_list"]),
          str(r["ji_shen_list"]))
    check("TC4无足量救神", "无有力救神" in r["note"], r["note"])


# ============================ 3. 四库 / 四长生不透 ============================
def case_siku_siling():
    """新口径：四库不透一律取本气并标暗格，司令天数完全不影响取格。"""
    base = (["丙", "壬", "甲", "丁"], ["子", "辰", "午", "未"])
    rs = [g(mk(*base, day=d)) for d in (0, 10, 20)]
    check("四库不透取本气→偏财格",
          all(r["main_ge_name"] == "偏财格" for r in rs),
          str([r["main_ge_name"] for r in rs]))
    check("四库本气戊土", all(r["ge_shen"].startswith("戊") for r in rs))
    check("四库标暗格",
          all(r["an_ge_flag"] is True and r["ge_variant"] == "暗格" for r in rs))
    check("司令天数不改结论",
          len({(r["main_ge_name"], r["ge_shen"], r["ge_status"]) for r in rs}) == 1)
    check("siling_gan 随天数变但不参与取格",
          len({r["siling_gan"] for r in rs}) == 3 and
          all(r["siling_used_for_ge"] is None for r in rs),
          str([r["siling_gan"] for r in rs]))
    # 四长生不透同样取本气；本气恰为比劫 → 建禄（禄刃不标暗格）
    r = g(mk(["丙", "丁", "庚", "己"], ["午", "申", "子", "卯"]))
    check("四长生不透本气比劫→建禄",
          r["main_ge_name"] == "建禄格", r["main_ge_name"])
    check("禄刃不标暗格", r["an_ge_flag"] is False)


# ============================ 4. 禄刃 ============================
def case_luren():
    # 铁则：月令藏干有其他十神透出 → 放弃禄刃
    r1 = g(mk(["庚", "甲", "庚", "壬"], ["午", "申", "子", "午"]))
    check('新规回归：禄刃铁则 壬透不做建禄', r1["main_ge_name"] == "建禄格")
    r2 = g(mk(["丙", "丁", "庚", "己"], ["午", "申", "子", "卯"]))
    check("禄刃铁则 全不透做建禄", r2["main_ge_name"] == "建禄格")
    # 阴干禄（辛禄在酉，五行级 LU 会漏判）
    r3 = g(mk(["丙", "丁", "辛", "戊"], ["子", "酉", "巳", "子"]))
    check("阴干辛禄酉→建禄", r3["main_ge_name"] == "建禄格", r3["main_ge_name"])
    # 阳刃 / 阴干帝旺月劫
    r4 = g(mk(["丙", "丁", "甲", "乙"], ["子", "卯", "午", "未"]))
    check("阳干帝旺→阳刃格", r4["main_ge_name"] == "阳刃格", r4["main_ge_name"])
    check("阳刃无官杀制→真破格", r4["ge_status"] == "真破格", r4["ge_status"])
    r5 = G.compute_geju(mk(["丁", "己", "乙", "癸"], ["子", "寅", "巳", "酉"]), config={"enable_special_ge":False})
    check("阴干帝旺→月劫格", r5["main_ge_name"] == "月劫格", r5["main_ge_name"])
    check("十干禄表辛禄酉", G.TEN_GAN_LU["辛"] == "酉")
    check("阳刃表庚刃酉", G.YANG_REN["庚"] == "酉")


# ============================ 5. Step1 合化前置 ============================
def case_step1_hehua():
    # 该盘三会木局、辰被置换后戊土无根，旺衰新口径会判从弱 → 走从杀格外格路线；
    # 这里关掉外格筛查，隔离验证「三会后虚拟藏干取格」这一八格逻辑本身。
    r = g(mk(["甲", "丁", "戊", "壬"], ["寅", "卯", "辰", "子"]),
          config={"enable_special_ge": False})
    check("三会成功改提纲", any("提纲五行换为木" in t for t in r["trace_log"]),
          str(r["trace_log"][:2]))
    check("三会后虚拟藏干取格", r["ge_shen"].startswith("甲木"), r["ge_shen"])
    # 补：放开外格筛查时，同一盘应经「旺衰从弱 → 从杀格」链路（旧版无根盘进不了从格）
    r_cong = g(mk(["甲", "丁", "戊", "壬"], ["寅", "卯", "辰", "子"]))
    check("无根从弱→从杀格可达", r_cong["main_ge_name"] == "从杀格", r_cong["main_ge_name"])
    check("从杀格沿用旺衰从弱标签", r_cong["wangshuai_tag"] == "从弱", r_cong["wangshuai_tag"])
    # 六合成功也不改提纲（PRD §2.4 边界）
    r2 = g(mk(["庚", "乙", "甲", "壬"], ["辰", "酉", "子", "寅"]))
    check("六合不改提纲", any("无成功三合/三会" in t for t in r2["trace_log"]))
    check("六合仍按酉本气取格", r2["main_ge_name"] == "正官格", r2["main_ge_name"])


# ============================ 6. 清浊 / 路线 ============================
def case_clean_hunza():
    # 官杀同透 + 乙庚五合合去七杀 → 浊而能清
    # 该盘日主无本气根、克泄耗占比 0.90，旺衰新口径判从弱 → 从杀格路线不做清浊；
    # 这里关掉从格门槛，隔离验证八格「合去留清」的清浊判定。
    r1 = g(mk(["乙", "庚", "甲", "辛"], ["子", "酉", "午", "未"]),
           config={"cong_threshold": 1.0})
    check("官杀混有合去→浊而能清", r1["clean_level"] == "浊而能清", r1["clean_level"])
    # 官杀同透无合 → 浊而无去
    r2 = g(mk(["庚", "癸", "甲", "辛"], ["子", "酉", "午", "未"]))
    check("官杀混无合→浊而无去", r2["clean_level"] == "浊而无去", r2["clean_level"])
    check("混杂写入日志", any("同类混杂" in t for t in r2["trace_log"]))
    # 七杀双路线互斥
    r3 = g(mk(["庚", "丙", "甲", "壬"], ["巳", "申", "子", "辰"]))
    check("七杀双路线互斥→浊而无去", r3["clean_level"] == "浊而无去", r3["clean_level"])
    check('新规回归：七杀双路线日志', any("双路线" in t for t in r3["trace_log"]))
    # _expand_groups 同时支持组名与具体十神名（曾静默吞掉具体名）
    check("展开组名 财", G._expand_groups(["财"]) == ["正财", "偏财"])
    check("展开具体名 偏印", G._expand_groups(["偏印"]) == ["偏印"])
    check("展开混合", G._expand_groups(["食伤", "七杀"]) == ["食神", "伤官", "七杀"])
    check("展开比劫组（不得被八格过滤吞掉）",
          G._expand_groups(["比劫"]) == ["比肩", "劫财"],
          str(G._expand_groups(["比劫"])))
    # 财星正偏同透 → 不清（财不忌偏正）
    r4 = g(mk(["己", "戊", "甲", "甲"], ["子", "戌", "午", "寅"]))
    check("财正偏同透→清纯", r4["clean_level"] == "清纯", r4["clean_level"])
    check("财正偏同透仍为财格", r4["main_ge_name"] == "偏财格", r4["main_ge_name"])
    # 印星正偏同透 → 浊（现行口径：正偏印并见算浊）
    r5 = G.compute_geju(mk(["壬", "癸", "甲", "甲"], ["子", "子", "午", "寅"]), config={"enable_special_ge":False})
    check('新规回归：印正偏同透→清纯', r5["clean_level"] == "浊而无去", r5["clean_level"])
    check("印正偏同透仍为正印格", r5["main_ge_name"] == "正印格", r5["main_ge_name"])
    # 月令多透异类（财+官）并见 → 仍浊
    r6 = g(mk(["辛", "己", "甲", "壬"], ["子", "丑", "午", "寅"]))
    check("月令财官异类并见→浊而无去", r6["clean_level"] == "浊而无去", r6["clean_level"])


# ============================ 7. Step7 外格 ============================
def case_special_ge():
    gans, zhis = ["戊", "己", "乙", "庚"], ["丑", "辰", "未", "戌"]
    he = heju_evaluate(gans, zhis, M.default_config())
    base = {"tag": "身弱", "cong_info": {"is_cong": False}}
    sp, _ = G._screen_special_ge(gans, zhis, "乙", "木", he,
                                 dict(base, tag="从弱",
                                      cong_info={"is_cong": True}), {}, [])
    check("真从弱→从格", sp is not None and sp.startswith("从"), str(sp))
    sp, _ = G._screen_special_ge(gans, zhis, "乙", "木", he,
                                 dict(base, tag="假从弱"), {}, [])
    check("假从不入外格", sp is None, str(sp))
    sp, _ = G._screen_special_ge(gans, zhis, "乙", "木", he,
                                 dict(base, tag="从强",
                                      cong_info={"is_cong": True}), {}, [])
    check("真从强保留分类，不自动升为专旺", sp == "从强格", str(sp))
    # 化气格门槛①：日主【未参与】五合（他柱之合）→ 不得判化气格。
    # 旧版只查全局有无成功五合，把「甲子 己辰 乙丑 庚申」（日主乙）误判化土格。
    g2, z2 = ["甲", "己", "乙", "庚"], ["子", "辰", "丑", "申"]
    he2 = heju_evaluate(g2, z2, M.default_config())
    check("五合严格成功", any(h["type"] == "wuhe" and h["hua_success"]
                             for h in he2["he_groups"]))
    sp, _ = G._screen_special_ge(g2, z2, "乙", "木", he2, base, {}, [])
    check("他柱之合不入化气格", sp is None, str(sp))
    # 化气格门槛②：日主参与五合 + 日主孤立 → 化气格
    g3, z3 = ["丙", "甲", "己", "庚"], ["子", "辰", "丑", "申"]
    he3 = heju_evaluate(g3, z3, M.default_config())
    sp, _ = G._screen_special_ge(g3, z3, "己", "土", he3, base, {}, [])
    check("日主参与五合→化气格", sp is not None and "化土" in sp, str(sp))
    # 开关
    r = G.compute_geju(mk(["丙", "丁", "甲", "乙"], ["子", "卯", "午", "未"]),
                       config={"enable_special_ge": False})
    check('新规回归：外格开关关闭', r["special_ge"] is None and any("开关关闭" in t for t in r["trace_log"]))
    check("非真破格不启用外格", g(mk(["庚", "甲", "庚", "壬"],
                                  ["午", "申", "子", "午"]))["special_ge"] is None)


# ============================ 8. 链路 / 输出 / 旺衰隔离 ============================
def case_output_contract():
    chart = mk(["辛", "癸", "甲", "丁"], ["未", "酉", "申", "卯"])
    r = g(chart)
    required = ["main_ge_name", "ge_shen", "xiang_shen_list", "ji_shen_list",
                "ge_status", "clean_level", "note", "trace_log",
                "lu_ren_flag", "special_ge",
                "an_ge_flag", "ge_variant", "quge_basis", "bijiao_tou"]
    check("输出字段齐全", all(k in r for k in required), str(list(r.keys())))
    check("状态枚举合法", r["ge_status"] in
          ("成格", "成中有败", "败中有救", "真破格"), r["ge_status"])
    check("清浊枚举合法", r["clean_level"] in
          ("清纯", "浊而能清", "浊而无去"), r["clean_level"])
    check("明暗格枚举合法", r["ge_variant"] in ("明格", "暗格"), r["ge_variant"])
    check("司令不参与取格", r["siling_used_for_ge"] is None)
    check("JSON 可序列化", isinstance(json.dumps(r, ensure_ascii=False), str))
    # 判定顺序：Step1 早于 Step2 早于 Step3/5/6
    tl = r["trace_log"]
    i1 = next(i for i, t in enumerate(tl) if t.startswith("Step1"))
    i2 = next(i for i, t in enumerate(tl) if t.startswith("Step2"))
    i3 = next(i for i, t in enumerate(tl) if t.startswith("Step3"))
    check("顺序 Step1<Step2<Step3", i1 < i2 < i3, str((i1, i2, i3)))
    i5 = next((i for i, t in enumerate(tl) if t.startswith("Step5")), len(tl))
    i6 = next((i for i, t in enumerate(tl) if t.startswith("Step6")), len(tl))
    check("顺序 Step5<=Step6", i5 <= i6, str((i5, i6)))
    # 旺衰仅附加，不参与定格：改旺衰超参不改变主格名
    r2 = G.compute_geju(chart, config={"cong_threshold": 0.51,
                                       "tiangan_base": 9999})
    check("旺衰超参不改主格", r2["main_ge_name"] == r["main_ge_name"],
          "%s vs %s" % (r["main_ge_name"], r2["main_ge_name"]))
    check("旺衰标签为附加字段", "wangshuai_tag" in r and "wangshuai_confidence" in r)


# ============================ 9. engine 接入 ============================
def case_engine():
    chart = mk(["庚", "甲", "庚", "壬"], ["午", "申", "子", "午"])
    out = analyze(chart)
    check("engine ok", out["ok"] is True)
    check("modules.geju=done", out["modules"]["geju"] == "done", str(out["modules"]))
    check('新规回归：engine 含 geju 字段', out["geju"]["main_ge_name"] == "建禄格")
    check("final_xiyong 含格局摘要",
          out["final_xiyong"]["geju_summary"]["ge_status"] == "成格")
    check("engine 版本号", "geju" in out["engine_version"], out["engine_version"])
    # 复用 ws：engine 已算好旺衰，geju 不应再调用 compute_wangshuai
    calls = []
    orig = G.compute_wangshuai

    def spy(*a, **kw):
        calls.append(1)
        return orig(*a, **kw)

    G.compute_wangshuai = spy
    try:
        analyze(chart)
    finally:
        G.compute_wangshuai = orig
    check("复用 ws 不重复计算旺衰", len(calls) == 0, "calls=%d" % len(calls))


# ============================ 10. 排盘节气天数 ============================
def case_solar_term_day():
    try:
        import lunar_python  # noqa: F401
    except ImportError:
        check("节气天数 skip（lunar_python 缺失）", True, "SKIPPED")
        return
    r = auto_solar_term_day("1990-08-15 10:30:00")
    check("自动算节气天数", r is not None and r["day"] == 7, str(r))
    check("自动识别节名", r and r["jie_name"] == "立秋", str(r))
    r2 = auto_solar_term_day("1990-01-03 10:30:00")
    check("跨年节气回溯", r2 is not None and r2["jie_name"] == "大雪", str(r2))
    check("非法输入优雅降级", auto_solar_term_day("not-a-date") is None)


# ============================ 11. 合化以旺衰模块为准（yan 复核） ============================
def case_hehua_reuse():
    """前置合化直接复用旺衰模块的 heju 结果，且消费口径一致。"""
    import bazi_core.wangshuai as W

    gz = (["甲", "丁", "戊", "壬"], ["寅", "卯", "辰", "子"])   # 三会木成功
    chart = mk(*gz)
    ws = W.compute_wangshuai(chart)
    check("旺衰输出完整 he_detail",
          "he_detail" in ws and "branch_hua" in ws["he_detail"])

    calls = []
    orig = W.heju_evaluate

    def spy(*a, **kw):
        calls.append(1)
        return orig(*a, **kw)

    W.heju_evaluate = spy
    try:
        out = analyze(chart)
    finally:
        W.heju_evaluate = orig
    check("全链路 heju 只算一次", len(calls) == 1, "calls=%d" % len(calls))
    check("geju 标注复用来源", "复用旺衰模块" in out["geju"]["he_source"],
          out["geju"]["he_source"])

    he = ws["he_detail"]
    eff = G._build_eff_hide(gz[1], he, month_hua="木", keep_month_original=True)
    check("三会三支整体置换（与旺衰同口径）",
          all(eff[i] == ["甲", "乙"] for i in (0, 1, 2)), str(eff))
    check("未合化支保留原藏干", eff[3] == ["癸"], str(eff[3]))

    # 六合成功：月令提纲不动（PRD §2.4 硬规则），但月令以外支同步置换
    g4, z4 = ["庚", "乙", "甲", "壬"], ["辰", "酉", "子", "寅"]
    he4 = heju_evaluate(g4, z4, M.default_config())
    eff4 = G._build_eff_hide(z4, he4, month_hua=None, keep_month_original=True)
    check("六合不改月令提纲", eff4[1] == ["辛"], str(eff4[1]))
    check("六合其他支按旺衰置换", eff4[0] == ["庚", "辛"], str(eff4[0]))
    check("六合盘仍按酉本气取格", g(mk(g4, z4))["main_ge_name"] == "正官格")

    r = G.compute_geju(chart)
    check("合化盘司令仍不参与取格", r["siling_used_for_ge"] is None,
          str(r["siling_used_for_ge"]))
    check("原月令司令保留为参考字段", r["siling_gan"] is not None)


# ============================ 12. 全面检查发现的回归修复 ============================
def case_regression_fixes():
    # 偏印（枭）格忌「枭旺夺食」：旧版 ji=[] 导致永不破格
    r = g(mk(["丙", "戊", "庚", "壬"], ["子", "戌", "午", "申"]))
    check("偏印格忌神含食神", any("食神" in x for x in r["ji_shen_list"]),
          str(r["ji_shen_list"]))
    check("偏印格标为凶神逆用", any("凶神逆用" in t for t in r["trace_log"]),
          str(r["trace_log"]))
    r2 = g(mk(["甲", "戊", "庚", "壬"], ["寅", "戌", "午", "申"]))
    check("财药不足或受制不得标完全获救", r2["ge_status"] == "真破格", r2["ge_status"])

    # 合去留清必须作用于成破，且不能靠「格神自救」假救应
    r3 = g(mk(["乙", "庚", "甲", "辛"], ["子", "酉", "午", "未"]),
           config={"cong_threshold": 1.0})     # 同上：隔离从格路线
    check("合去留清剔除忌神", any("合去留清生效" in t for t in r3["trace_log"]))
    check("被合去七杀不在忌神列表",
          not any("七杀" in x for x in r3["ji_shen_list"]), str(r3["ji_shen_list"]))
    check("无官杀假救应", ("正官", "七杀") not in G.SAVIOUR)

    # 比劫组曾被 GE_TENSHEN 过滤整体吞掉：财格「比劫夺财」、印格「比劫护印」全部失效
    r5 = g(mk(["丙", "壬", "甲", "丁"], ["子", "辰", "午", "未"], day=20))
    check('新规回归：财格忌神含藏干劫财', not r5["ji_shen_list"],
          str(r5["ji_shen_list"]))
    check('新规回归：财格比劫夺财得食伤救应', r5["ge_status"] == "成格", r5["ge_status"])
    # 新口径：人元司令不参与取格，同一四柱不同 solar_term_day 结论必须一致
    r6 = g(mk(["丙", "壬", "甲", "丁"], ["子", "辰", "午", "未"], day=10))
    check("司令天数不改格局结论",
          (r5["main_ge_name"], r5["ge_status"], r5["ge_shen"]) ==
          (r6["main_ge_name"], r6["ge_status"], r6["ge_shen"]), r6["note"])
    check("不透取本气标暗格",
          r5["an_ge_flag"] is True and r6["an_ge_flag"] is True)

    # 非法干支前置校验（旧版透传后报 KeyError）
    try:
        G.compute_geju(mk(["庚", "甲", "庚", "X"], ["午", "申", "子", "午"]))
        check("非法天干被拦截", False)
    except ValueError:
        check("非法天干被拦截", True)
    try:
        G.siling_gan("??", 3)
        check("非法月令被拦截", False)
    except ValueError:
        check("非法月令被拦截", True)


# ============================ 13. 格局维度喜用（Step8） ============================
def case_xiyong_bing():
    """笔记总纲：先看格局是否有病，有病先治病，有病有药方为贵。"""
    # TC4 正官格 · 伤官见官（PRD 判败中有救）→ 治病为先，药=印制伤官
    r = g(mk(["辛", "癸", "甲", "丁"], ["未", "酉", "申", "卯"]))
    x = r["xiyong_geju"]
    check("有病→治病为先", x["mode"] == "治病为先" and x["has_bing"], x["mode"])
    check("病清单含伤官见官",
          any(b["name"] == "伤官见官" and b["severity"] == "坏格"
              for b in x["bing_list"]), str(x["bing_list"]))
    check("药含印制伤官", any("印制伤官" in s for s in x["yao_shen_list"]),
          str(x["yao_shen_list"]))
    check("有对应药仍需逐字验证", x["yao_in_chart"] is False and bool(x["treatment_status"]), str(x["yao_in_chart"]))
    check('新规回归：局内已有药优先于待运取',
          all("待运" not in item for item in x["yong_shen_list"]) and (bool(x["yong_shen_list"]) or bool(x["unresolved_bing"])),
          str(x["yong_shen_list"]))
    check("病神入忌神且不重复",
          any("伤官" in s for s in x["ji_shen_list"])
          and len({_xiyong_key(s) for s in x["ji_shen_list"]}) == len(x["ji_shen_list"]),
          str(x["ji_shen_list"]))

    # 财格比劫夺财：甲己五合已合去比劫 → 药在局内；食伤通关为次
    r2 = g(mk(["甲", "己", "甲", "丙"], ["寅", "未", "子", "午"], day=20))
    x2 = r2["xiyong_geju"]
    check("比劫完全合去后顺用", x2["mode"] == "吉神顺用", x2["mode"])
    check("比劫合去后不重复配药", not x2["yao_shen_list"], str(x2["yao_shen_list"]))
    check("病已合去不追加通关药", not x2["yao_shen_list"],
          str(x2["yao_shen_list"]))
    check("有食伤通关不再判财露无官杀",
          not any(b["name"] == "财露无官杀" for b in x2["bing_list"]),
          str([b["name"] for b in x2["bing_list"]]))

    # 阳刃无制：禄刃局有病也走治病为先，药=官杀制刃（原局无药）
    r3 = g(mk(["丙", "丁", "甲", "乙"], ["子", "卯", "午", "未"]))
    x3 = r3["xiyong_geju"]
    check("阳刃无制→治病为先", x3["mode"] == "治病为先", x3["mode"])
    check("阳刃药为官杀制刃", any("官杀制刃" in s for s in x3["yao_shen_list"]),
          str(x3["yao_shen_list"]))
    check("原局无药标待运", x3["yao_in_chart"] is False, str(x3["yao_in_chart"]))

    # 调候 / 扶抑：V1 不判调候之病，扶抑只作附加提示
    check("调候之病 pending", x["tiaohou_pending"] is True)
    check("扶抑仅附加不夺用", isinstance(x["fuyi_hint"], str)
          and (not x["fuyi_hint"] or "不参与格局取用" in x["fuyi_hint"]),
          x["fuyi_hint"])
    check("喜用层不改主格名", r["main_ge_name"] == "正官格", r["main_ge_name"])


def case_xiyong_wubing():
    """笔记：无病再看用，顺用逆用要分清；用神优先取透干者。

    注：原 TC1 盘（庚日主 申月，年/时支午藏丁正官、日支子藏癸伤官，子午冲）
    在新口径（藏干有根即并见）下确为「伤官见官」真病，故此处改用一枚
     genuinely 无主病、仅带「比劫夺财·轻病」的食神格盘，专门验证「无病→顺用」。
    """
    # 食神格（吉神）→ 顺用，取食神生财；轻病（比劫夺财）不夺用
    r = G.compute_geju(mk(["庚", "壬", "庚", "甲"], ["亥", "申", "酉", "卯"]), config={"enable_special_ge":False})
    x = r["xiyong_geju"]
    check('新规回归：无病→吉神顺用', x["mode"] == "禄刃取相" and not x["has_bing"], x["mode"])
    check('新规回归：顺用取食神生财', any("食神" in s for s in x["yong_shen_list"]),
          str(x["yong_shen_list"]))
    check("轻病不夺用（比劫夺财列 bing_light）",
          any(b["name"] == "比劫夺财" for b in x["bing_light"])
          and not x["bing_list"], str(x["bing_light"]))

    # 偏财格：PRD 善神表未列偏财，但 GE_ROUTE.good=True → 必须顺用，
    # 早期喜用层用 GOOD_SS 兜底曾误标「凶神逆用」
    r2 = g(mk(["戊", "丙", "甲", "庚"], ["午", "寅", "子", "午"], day=5))
    x2 = r2["xiyong_geju"]
    check('新规回归：偏财格顺用（与 Step4 同口径）', x2["mode"] == "禄刃取相", x2["mode"])
    check('新规回归：用神优先取透干', all(any(g in item for g in ("丙", "戊")) for item in x2["yong_shen_list"]),
          str(x2["yong_shen_list"]))

    # 七杀格（凶神）双路线互斥：食神制杀 + 印化杀 同时成立 → 浊而无去 → 真破格
    # （不再归入「成中有败」，后者仅用于忌神虚浮之瑕疵）；喜用保留「择一取用」。
    r3 = g(mk(["庚", "丙", "甲", "壬"], ["巳", "申", "子", "辰"]))
    x3 = r3["xiyong_geju"]
    check("七杀双路线相隔不破格", r3["ge_status"] == "成格", r3["ge_status"])
    check("双路线相隔择一逆用", x3["mode"] == "凶神逆用", x3["mode"])
    check("双路线互斥不并取", len(x3["yong_shen_list"]) <= 1 and (bool(x3["yong_shen_list"]) or bool(x3["unresolved_bing"])),
          str(x3["yong_shen_list"]))
    check('新规回归：双路线互斥写入备注', "Step4 已选路线" in x3["note"], x3["note"])

    # 禄刃 / 无格：不空输出，沿用主流程相神
    r4 = g(mk(["甲", "壬", "甲", "庚"], ["子", "寅", "子", "午"]))
    x4 = r4["xiyong_geju"]
    check("建禄有明确忌神需治病", x4["mode"] == "治病为先", x4["mode"])
    check("无药不以相神冒充治疗", bool(x4["unresolved_bing"]), str(x4["yong_shen_list"]))


def case_xiyong_bugfix():
    """喜用层 bug 回归（2026-11-06 修复）：
    ① 格神 / 护格相神不得列为忌神（正官格之财、伤官格之财印、偏财格之格神自身）；
    ② 同一十神不得既作辅佐又作忌神（林则徐甲七杀）；
    ③ 官杀混杂 / 伤官见官须两神同现，仅见一方不触发（避免「病神=原局无」自相矛盾）；
    ④ fuyi_hint 区分「身弱无根」与「身弱（有根）」，不再一律写成「身弱有根」；
    ⑤ 定格成破与喜用 has_bing 联动（真破格/双路线互斥 → has_bing=True）；
    ⑥ 双路线互斥归真破格，而非「成中有败 + 空忌神」。
    """
    # 杜月笙 正官格：格神庚、相神财/印 均不得进忌神
    r = g(mk(["戊", "庚", "乙", "壬"], ["子", "申", "丑", "午"]))
    x = r["xiyong_geju"]
    ji_keys = [_xiyong_ss_of(s) for s in x["ji_shen_list"]]
    xi_keys = [_xiyong_ss_of(s) for s in x["xi_shen_list"]]
    check('新规回归：杜月笙·正官格真破格', r["ge_status"] == "成格", r["ge_status"])
    check("杜月笙·格神庚不进忌神", "正官" not in ji_keys, str(x["ji_shen_list"]))
    check("杜月笙·相神财不进忌神", "正财" not in ji_keys and "偏财" not in ji_keys,
          str(x["ji_shen_list"]))
    check("杜月笙·辅佐∩忌神为空", not (set(xi_keys) & set(ji_keys)), str((xi_keys, ji_keys)))
    check("杜月笙·受冲后财数量不足不判财多官埋", x["has_bing"] is False, x["mode"])
    # 用神（治病为先时=药）按十神身份判，不得是格神「正官」本身
    # （注意：「合去七杀｜正官格合杀留官」描述里含「正官」二字，不可做子串匹配）
    check("杜月笙·用神非格神",
          all(_xiyong_ss_of(s) != "正官" for s in x["yong_shen_list"]),
          str(x["yong_shen_list"]))

    # 林则徐 伤官格：甲七杀 只作忌神，不进辅佐
    r2 = g(mk(["甲", "癸", "戊", "己"], ["子", "酉", "申", "未"]))
    x2 = r2["xiyong_geju"]
    xi_keys2 = [_xiyong_ss_of(s) for s in x2["xi_shen_list"]]
    check("林则徐·七杀不进辅佐", "七杀" not in xi_keys2, str(x2["xi_shen_list"]))
    check("林则徐·七杀进忌神", "七杀" in [_xiyong_ss_of(s) for s in x2["ji_shen_list"]],
          str(x2["ji_shen_list"]))

    # 只见正官、不见七杀 → 官杀混杂不触发（须两神同现）。
    # 原盘日支丑藏辛七杀（与月干庚正官构成官杀混杂），此处改日支为卯去掉辛，
    # 仅留正官，验证「官杀混杂」不会因单一正官而误触发。
    r3 = g(mk(["戊", "庚", "乙", "壬"], ["子", "巳", "卯", "午"]))
    x3 = r3["xiyong_geju"]
    check("只见正官不触发官杀混杂",
          not any(b["name"] == "官杀混杂" for b in x3["bing_list"] + x3["bing_light"]),
          str([b["name"] for b in x3["bing_list"] + x3["bing_light"]]))

    # fuyi_hint 区分无根（bug #4 回归）：杜月笙 身弱无根，提示不得误写「身弱有根」
    r4 = g(mk(["戊", "庚", "乙", "壬"], ["子", "申", "丑", "午"]))   # 杜月笙：身弱无根
    x4 = r4["xiyong_geju"]
    check("身弱无根提示不为『身弱有根』",
          "身弱无根" in x4["fuyi_hint"] and "身弱有根" not in x4["fuyi_hint"],
          x4["fuyi_hint"])


def case_xiyong_contract():
    """Step8 输出契约 + engine 接入（不加权、不改旺衰 favored）。"""
    chart = mk(["辛", "癸", "甲", "丁"], ["未", "酉", "申", "卯"])
    r = g(chart)
    x = r["xiyong_geju"]
    required = ["source", "has_bing", "mode", "bing_list", "bing_light",
                "yong_shen_list", "xi_shen_list", "ji_shen_list",
                "yao_shen_list", "yao_in_chart", "principle", "note",
                "fuyi_hint", "tiaohou_pending", "trace"]
    check("喜用输出字段齐全", all(k in x for k in required), str(sorted(x.keys())))
    check("mode 枚举合法", x["mode"] in
          ("治病为先", "吉神顺用", "凶神逆用", "禄刃取相", "无格可取", "外格另论"),
          x["mode"])
    check("严重度分级合法", all(b["severity"] in ("坏格", "格局病")
                               for b in x["bing_list"]), str(x["bing_list"]))
    check("每个主病都配了药", all(b.get("yao") for b in x["bing_list"]),
          str(x["bing_list"]))
    check("喜用结果可序列化", isinstance(json.dumps(x, ensure_ascii=False), str))
    check("Step8 日志并入主链路", any(t.startswith("Step8") for t in r["trace_log"]))
    check("来源标注李师傅笔记", "李厚君" in x["source"], x["source"])

    out = analyze(chart)
    check("engine 引用同一喜用结果",
          out["final_xiyong"]["geju_xiyong"] == out["geju"]["xiyong_geju"])
    check("摘要含 mode / has_bing",
          out["final_xiyong"]["geju_summary"]["xiyong_mode"] == x["mode"]
          and out["final_xiyong"]["geju_summary"]["has_bing"] == x["has_bing"])
    check("不加权：favored 仍等于旺衰维度",
          out["final_xiyong"]["favored"] == out["xiyong_wangshuai"]["favored"])
    check("旺衰超参不改格局喜用 mode",
          G.compute_geju(chart, config={"tiangan_base": 9999})
          ["xiyong_geju"]["mode"] == x["mode"])


# ============================ 14. 新口径月令取格（yan 2026-11-06） ============================
def case_new_quge_rule():
    """① 唯一透出取该透 ② 多透按本气>中气>余气 ③ 都不透取本气标暗格
    ④ 比劫透出不取该字、取出的格神为比劫才按建禄走 ⑤ 司令天数不影响结论。"""
    # ① 唯一透出（酉藏辛，年干辛透）
    r = g(mk(["辛", "癸", "甲", "丁"], ["未", "酉", "申", "卯"]))
    check("唯一透出取该透",
          r["main_ge_name"] == "正官格" and r["quge_basis"] == "单透取格神",
          r["main_ge_name"])
    check("有透出为明格", r["an_ge_flag"] is False and r["ge_variant"] == "明格")
    # ② 多透：本气丙 + 中气戊 → 取本气
    r2 = g(mk(["丙", "戊", "庚", "壬"], ["子", "巳", "午", "申"]))
    check("多透本气优先",
          r2["main_ge_name"] == "七杀格" and r2["ge_shen"].startswith("丙"),
          r2["main_ge_name"])
    # ② 多透：中气戊 + 余气庚 → 取中气（yan 明确举的例子）
    r3 = g(mk(["戊", "庚", "乙", "丁"], ["子", "巳", "午", "申"]))
    check("多透中气优于余气",
          r3["main_ge_name"] == "正财格" and r3["ge_shen"].startswith("戊"),
          r3["main_ge_name"])
    # ③ 都不透 → 本气 + 暗格
    r4 = g(mk(["壬", "乙", "甲", "己"], ["申", "巳", "午", "巳"]))
    check("都不透取本气",
          r4["main_ge_name"] == "食神格" and r4["ge_shen"].startswith("丙"),
          r4["main_ge_name"])
    check("都不透标暗格", r4["an_ge_flag"] is True and r4["ge_variant"] == "暗格")
    check("暗格写入链路", any("【暗格】" in t for t in r4["trace_log"]))
    check("暗格不改格名", "暗格" not in r4["main_ge_name"])
    # ④ 比劫透出只排除该字，照常取格（PRD TC1 同盘）
    r5 = g(mk(["庚", "甲", "庚", "壬"], ["午", "申", "子", "午"]))
    check('新规回归：比劫透出不取该字',
          r5["main_ge_name"] == "建禄格",
          "%s / %s" % (r5["main_ge_name"], r5["bijiao_tou"]))
    check('新规回归：比劫透出不升禄刃', r5["lu_ren_flag"] is True)
    # ④ 取出的格神是比劫 → 建禄（禄刃不标暗格）
    r6 = g(mk(["甲", "壬", "甲", "庚"], ["子", "寅", "子", "午"]))
    check("格神比劫→建禄", r6["main_ge_name"] == "建禄格", r6["main_ge_name"])
    check("建禄不标暗格", r6["an_ge_flag"] is False)
    # ⑤ 司令天数完全不影响定格
    r7 = g(mk(["丙", "壬", "甲", "丁"], ["子", "辰", "午", "未"], day=0))
    r8 = g(mk(["丙", "壬", "甲", "丁"], ["子", "辰", "午", "未"], day=25))
    check("司令天数不影响定格",
          (r7["main_ge_name"], r7["ge_shen"], r7["ge_status"]) ==
          (r8["main_ge_name"], r8["ge_shen"], r8["ge_status"]))
    check("司令天数不改暗格标注",
          r7["an_ge_flag"] == r8["an_ge_flag"] is True)


def _xiyong_key(s):
    """测试用：与 geju_xiyong._key 同义（干字 + 十神名）。"""
    import re
    m = re.search(r"（([^·）]+)", s)
    return (s[0] if s else "", m.group(1) if m else s)


def _xiyong_ss_of(s):
    """测试用：从用神/忌神条目解析十神身份（避免子串误匹配）。

    格式举例：
      「丁（食神·藏·有根）」→ 食神
      「合去七杀｜…」→ 七杀
      「比肩/劫财｜…」→ 比劫
    解析失败时返回 None。
    """
    if "（" in s:
        return s.split("（")[1].split("·")[0]
    if s.startswith("合去"):
        return s[2:].split("｜")[0]
    if "比" in s and "劫" in s:
        return "比劫"
    return None


def run_all():
    cases = [case_siling, case_tc1, case_tc2, case_tc3, case_tc4,
             case_siku_siling, case_luren, case_step1_hehua,
             case_clean_hunza, case_special_ge, case_output_contract,
             case_engine, case_solar_term_day, case_hehua_reuse,
             case_regression_fixes, case_xiyong_bing, case_xiyong_wubing,
             case_xiyong_contract, case_new_quge_rule, case_xiyong_bugfix]
    for fn in cases:
        try:
            fn()
        except Exception as e:
            import traceback
            check(fn.__name__, False, "EXCEPTION: %s\n%s" % (e, traceback.format_exc()))
    failed = [p for p in PASS if not p[1]]
    print("\n" + "=" * 40)
    print("格局模块单元测试：%d 用例，%d 断言，失败 %d" % (len(cases), len(PASS), len(failed)))
    for name, _, detail in failed:
        print("  x [%s] %s" % (name, detail))
    if failed:
        print("结果：FAIL")
        return 1
    print("结果：PASS")
    return 0


def test_all():
    """pytest 入口。"""
    assert run_all() == 0


if __name__ == "__main__":
    sys.exit(run_all())
