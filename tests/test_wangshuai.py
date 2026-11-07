# -*- coding: utf-8 -*-
"""旺衰模块单元测试 —— 覆盖 PRD 第六节全部 17 个用例（含 ★ 开库用例 10–17）。

运行：
  python3 -m pytest tests/test_wangshuai.py -v
  （或直接：python3 tests/test_wangshuai.py）
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bazi_core import wangshuai as W
from bazi_core import heju as H

GAN_ZHI = "甲乙丙丁戊己庚辛壬癸", "子丑寅卯辰巳午未申酉戌亥"


def mk(gans, zhis):
    """由干支列表构造 PRD 输入 JSON。"""
    assert len(gans) == 4 and len(zhis) == 4
    order = ["year", "month", "day", "hour"]
    return {o: {"gan": gans[i], "zhi": zhis[i]} for i, o in enumerate(order)}


def gz(s):
    """'甲子 乙丑 丙寅 丁卯' -> (['甲','乙','丙','丁'], ['子','丑','寅','卯'])"""
    parts = s.split()
    g = [p[0] for p in parts]
    z = [p[1] for p in parts]
    return g, z


PASS = []


def check(name, cond, detail=""):
    PASS.append((name, cond, detail))
    if not cond:
        print("  ✗ FAIL [%s] %s" % (name, detail))


# ============================ 用例 1：三会成功化，三合作废 ============================
def case1():
    g, z = gz("甲寅 丙卯 甲辰 壬午")   # 月令卯（会木旺支）；三会 寅卯辰
    r = W.compute_wangshuai(mk(g, z))
    check("case1 三会成功", r["he_result"]["he_type"] == "sanhuí" and r["he_result"]["he_hua_success"],
          str(r["he_result"]))
    check("case1 三会分支置换为木", r["debug"]["branch_hua"] == [None, "木", "木", None] or
          set(x for x in r["debug"]["branch_hua"] if x) == {"木"}, str(r["debug"]["branch_hua"]))
    check("case1 无三合成功", not any(h["type"] == "sanhe" and h["hua_success"] for h in r["he_groups"]))


# ============================ 用例 2：三合齐全但月令非中神 → 三合绊 ============================
def case2():
    g, z = gz("壬申 甲子 庚辰 丙午")   # 月令寅？换成午；三合申子辰，月令午≠子
    # 重新构造：月令午，三合成员申子辰齐全
    g, z = gz("壬申 丙子 庚辰 甲午")
    r = W.compute_wangshuai(mk(g, z))
    sanhe = [h for h in r["he_groups"] if h["type"] == "sanhe"]
    check("case2 存在三合判定", len(sanhe) == 1, str(sanhe))
    check("case2 三合绊（不化）", sanhe and sanhe[0]["hua_success"] is False, str(sanhe))


# ============================ 用例 3：天干五合隔位，只绊不化 ============================
def case3():
    # 甲己相邻但月令非土令 → 五合绊（不化）；演示「合而不化」
    g, z = gz("甲子 己寅 丙辰 壬午")
    r = W.compute_wangshuai(mk(g, z))
    wuhe = [h for h in r["he_groups"] if h["type"] == "wuhe"]
    check("case3 存在五合判定", len(wuhe) == 1, str(wuhe))
    check("case3 五合绊（不化）", wuhe and wuhe[0]["hua_success"] is False, str(wuhe))


# ============================ 用例 4：独强根被冲支同时被三合合化，冲失效，不拔根 ============================
def case4():
    g, z = gz("壬申 癸子 甲寅 甲辰")   # 三合申子辰（月令子=中神）成功→申化水；寅(日禄)冲申失效
    r = W.compute_wangshuai(mk(g, z))
    sanhe = [h for h in r["he_groups"] if h["type"] == "sanhe"]
    check("case4 三合成功", sanhe and sanhe[0]["hua_success"], str(sanhe))
    check("case4 申被置换", r["debug"]["branch_hua"][0] == "水", str(r["debug"]["branch_hua"]))
    check("case4 寅不拔根", r["root_status"] in ("独根无伤", "多根稳固") and not any(
        x["is_broken"] for x in r["debug"]["root_list"]), r["root_status"])


# ============================ 用例 5：日主独根被冲，无救 → 拔根清零 ============================
def case5():
    g, z = gz("庚子 丙午 甲寅 戊申")   # 甲日主，独禄寅被申冲（申未被合化）→ 拔根
    r = W.compute_wangshuai(mk(g, z))
    check("case5 拔根", r["root_status"] == "独根被冲拔根", r["root_status"])
    check("case5 根清零", r["root_energy"] == 0.0, str(r["root_energy"]))
    check("case5 进入无根", r["tag"] in ("虚旺", "身弱无根"), r["tag"])


# ============================ 用例 6：地支无根、天干双印紧贴但旺势不足 → 身弱无根 ============================
def case6():
    g, z = gz("庚子 癸午 甲酉 壬申")   # 甲日主，地支无木根；月癸、时壬（印）紧贴 → 虚势 12
    r = W.compute_wangshuai(mk(g, z))
    check("case6 无根", r["root_status"] == "无根" or r["root_energy"] == 0, str(r["root_status"]))
    check("case6 虚势≥10", r["void_momentum"] >= 10, str(r["void_momentum"]))
    # V1.2 起虚旺需「F 占比≥void_wang_min_share_f」，本盘生扶占比约 25%，非虚旺
    check("case6 生扶占比低", r["ratio_share_f"] < 0.5, str(r["ratio_share_f"]))
    check("case6 判身弱无根", r["tag"] == "身弱无根", r["tag"])
    check("case6 提示不判虚旺", any("不判虚旺" in w for w in r["warning"]), str(r["warning"]))
    # 关掉旺势门槛可复现旧口径（兼容开关）
    r2 = W.compute_wangshuai(mk(g, z), {"void_wang_min_share_f": 0.0})
    check("case6 关门槛回退虚旺", r2["tag"] == "虚旺", r2["tag"])


# ============================ 用例 6b：拔根后印星有强根、生扶占比过门槛 → 虚旺 ============================
def case6b():
    g, z = gz("丁酉 癸午 甲子 癸卯")   # 甲日主独根卯被酉冲拔根；双印透干、子水印根 → 虚势 12
    r = W.compute_wangshuai(mk(g, z))
    check("case6b 拔根", r["root_status"] == "独根被冲拔根", r["root_status"])
    check("case6b 生扶占比≥0.5", r["ratio_share_f"] >= 0.5, str(r["ratio_share_f"]))
    check("case6b 判虚旺", r["tag"] == "虚旺", r["tag"])
    check("case6b 不从弱（印有根）", r["cong_info"]["residual_yin_root"] is True,
          str(r["cong_info"]))


# ============================ 用例 6c：日主无根 + 克泄耗压倒 → 从弱（旧版不可达）============================
def case6c():
    g, z = gz("癸申 辛丑 丁申 庚子")   # 丁日主，地支申丑申子无火根；财杀成势
    r = W.compute_wangshuai(mk(g, z))
    check("case6c 无根", r["root_energy"] == 0.0, str(r["root_status"]))
    check("case6c 克泄耗占比≥0.85", r["ratio_share_k"] >= 0.85, str(r["ratio_share_k"]))
    check("case6c 判从弱", r["tag"] == "从弱", r["tag"])
    check("case6c 标记从格", r["cong_info"]["is_cong"] is True, str(r["cong_info"]))
    # 关掉「印比无实根」要求时应回到假从分支（若无印根则为同结果，这里只验证开关可生效）
    r2 = W.compute_wangshuai(mk(g, z), {"cong_yin_root_as_fake": True})
    check("case6c 开关可配", r2["tag"] in ("从弱", "假从弱", "身弱无根"), r2["tag"])


# ============================ 用例 6d：无根从弱门槛可退回旧口径（无根不进从格）============================
def case6d():
    g, z = gz("癸申 辛丑 丁申 庚子")
    r = W.compute_wangshuai(mk(g, z), {"cong_allow_rootless": False})   # 明确关闭无根从格入口
    check("case6d 关从格回退", r["tag"] in ("虚旺", "身弱无根"), r["tag"])


# ============================ 用例 7：生扶占比高但残存七杀有强根 → 假从强 ============================
def case7():
    g, z = gz("甲亥 壬子 甲卯 壬申")   # 木/水极旺（从强），申中庚金本气为七杀强根 → 假从强
    r = W.compute_wangshuai(mk(g, z))
    check("case7 假从强", r["tag"] == "假从强", r["tag"])
    check("case7 标记假从", r["cong_info"]["is_fake_cong"] is True, str(r["cong_info"]))


# ============================ 用例 8：合化成功后禄根五行被置换 → 根失效 ============================
def case8():
    g, z = gz("丙寅 丁午 甲戌 庚申")   # 三合寅午戌火（月令午=中神）成功→寅化火；甲木禄根失效
    r = W.compute_wangshuai(mk(g, z))
    sanhe = [h for h in r["he_groups"] if h["type"] == "sanhe"]
    check("case8 三合成功", sanhe and sanhe[0]["hua_success"], str(sanhe))
    check("case8 寅被置换", r["debug"]["branch_hua"][0] == "火", str(r["debug"]["branch_hua"]))
    # 甲木地支根应全部失效 → 无木根
    wood_roots = [x for x in r["debug"]["root_list"] if x["root_type"] in ("禄", "刃", "长生", "本气根", "微根", "次强根")]
    check("case8 无木根（禄根失效）", len(wood_roots) == 0, str(r["debug"]["root_list"]))


# ============================ 用例 9：中和区间，置信度压低 ============================
def case9():
    g, z = gz("庚亥 壬子 甲午 庚申")   # 月令子（水=木之印，相，得令）；F≈K → 中和偏旺
    r = W.compute_wangshuai(mk(g, z))
    check("case9 中和区间", r["tag"] in ("中和偏旺", "中和偏弱"), r["tag"])
    check("case9 置信度压低(<0.7)", r["confidence"] < 0.7, str(r["confidence"]))


# ============================ ★ 用例 10：甲日主，地支仅未（无丑）→ 微根，不开库，身弱 ============================
def case10():
    g, z = gz("庚酉 戊申 甲未 庚子")   # 甲日主，唯一木根为未中乙木（微根），无丑 → 不开库
    r = W.compute_wangshuai(mk(g, z))
    check("case10 微根", any(x["root_type"] == "微根" for x in r["debug"]["root_list"]), str(r["debug"]["root_list"]))
    check("case10 不开库", r["root_detail"]["store_open"] is False, str(r["root_detail"]))
    check("case10 独根无伤", r["root_status"] == "独根无伤", r["root_status"])


# ============================ ★ 用例 11：甲日主，未+丑，丑未冲开库 → 升级次强根 ============================
def case11():
    g, z = gz("庚酉 戊申 甲未 庚丑")   # 丑冲未（丑未被合化）→ 木库开库，乙木微根→次强根
    r = W.compute_wangshuai(mk(g, z))
    check("case11 开库", r["root_detail"]["store_open"] is True, str(r["root_detail"]))
    check("case11 升级次强根", any(x["root_type"] == "次强根" for x in r["debug"]["root_list"]), str(r["debug"]["root_list"]))
    # 库冲开库豁免拔根：次强根不应被清零
    check("case11 开库不拔根", not any(x["is_broken"] for x in r["debug"]["root_list"]), str(r["debug"]["root_list"]))
    # 对比用例10：开库后单根能量应大于未开库（10 → 30）
    case10_r = W.compute_wangshuai(mk(*gz("庚酉 戊申 甲未 庚子")))
    e11 = max([x["base_energy"] for x in r["debug"]["root_list"] if x["root_type"] == "次强根"] or [0])
    e10 = max([x["base_energy"] for x in case10_r["debug"]["root_list"] if x["root_type"] == "微根"] or [0])
    check("case11 根能量升级(30>10)", e11 > e10, "e11=%s e10=%s" % (e11, e10))


# ============================ ★ 用例 12：甲日主，未+丑，丑(土)参与三合遭局外未(土禄刃)恋根 → 三合绊、库反而开 ============================
# V1.1.1-ext：土特殊扩展至三合/三会后，巳酉丑金中丑(土库)参与化金，局外未(辰戌丑未=土禄刃级)→恋根→三合绊；
#   丑不被置换则仍冲未→库开（与 V1.1 原「三合化则库不开」相反，系扩展决策之必然）。
def case12():
    g, z = gz("庚巳 辛酉 甲未 庚丑")   # 三合巳酉丑金（月令酉=中神）；丑为土库参与合化，局外未(土禄刃级)→恋根→三合绊
    r = W.compute_wangshuai(mk(g, z))
    sanhe = [h for h in r["he_groups"] if h["type"] == "sanhe"]
    check("case12 土恋根→三合绊(不化)", sanhe and sanhe[0]["hua_success"] is False, str(sanhe))
    check("case12 丑未被置换", r["debug"]["branch_hua"][3] is None, str(r["debug"]["branch_hua"]))
    # 三合绊→丑不置换→丑仍冲未→库开（次强根升级）
    check("case12 库开(丑冲力保留)", r["root_detail"]["store_open"] is True, str(r["root_detail"]))
    check("case12 升级次强根", any(x["root_type"] == "次强根" for x in r["debug"]["root_list"]), str(r["debug"]["root_list"]))


# ============================ ★ 用例 13：甲日主，未+丑，丑被六合绊（仍保有冲力）→ 库开 ============================
def case13():
    g, z = gz("壬子 甲寅 甲未 癸丑")   # 子丑六合（月令寅非土令）→ 六合绊，丑冲力保留 → 库开
    r = W.compute_wangshuai(mk(g, z))
    liuhe = [h for h in r["he_groups"] if h["type"] == "liuhe"]
    check("case13 六合绊", liuhe and liuhe[0]["hua_success"] is False, str(liuhe))
    check("case13 库开（冲力有效）", r["root_detail"]["store_open"] is True, str(r["root_detail"]))


# ============================ ★ 用例 14：辰辰自刑开库（config 开关） ============================
def case14():
    g, z = gz("壬辰 甲寅 壬辰 癸子")   # 两辰 → 自刑；水库（辰中癸水）
    # 默认 config：不开库
    r_off = W.compute_wangshuai(mk(g, z))
    check("case14 默认不自查开库", r_off["root_detail"]["store_open"] is False, str(r_off["root_detail"]))
    # 开 self_punish：开库
    r_on = W.compute_wangshuai(mk(g, z), {"store_self_punish_open": True})
    check("case14 开自查开库", r_on["root_detail"]["store_open"] is True, str(r_on["root_detail"]))


# ============================ ★ 用例 15：开库后的次强根被本气冲且无救 → 拔根 ============================
def case15():
    # 默认：库冲开库豁免拔根（取用例11行为：保次强根）
    g, z = gz("庚酉 戊申 甲未 庚丑")
    r_def = W.compute_wangshuai(mk(g, z))
    check("case15 默认开库保根(不豁免拔根关闭)", not any(x["is_broken"] for x in r_def["debug"]["root_list"]), str(r_def["root_status"]))
    # 显式开启豁免拔根（store_root_exempt_from_pull=False）以复现 PRD 字面「开库不豁免拔根」
    r_exempt = W.compute_wangshuai(mk(g, z), {"store_root_exempt_from_pull": False})
    check("case15 开库后次强根仍被拔根(显式)", r_exempt["root_status"] == "独根被冲拔根", r_exempt["root_status"])


# ============================ ★ 用例 16：原局无冲，仅大运冲库 → 静态不开库 ============================
def case16():
    g, z = gz("庚酉 戊申 甲未 庚子")   # 无丑 → 原局无冲 → 不开库（交由上层大运处理）
    r = W.compute_wangshuai(mk(g, z))
    check("case16 无丑不开库", r["root_detail"]["store_open"] is False, str(r["root_detail"]))
    check("case16 仍为微根", any(x["root_type"] == "微根" for x in r["debug"]["root_list"]), str(r["debug"]["root_list"]))


# ============================ ★ 用例 17：开库使残余印比获实根，阻断真从 → 假从 ============================
def case17():
    # 开库（有丑）：未微根→次强，木（比劫）获实根 → 阻断真从弱 → 假从弱
    g, z = gz("庚酉 辛申 甲未 庚丑")
    r_open = W.compute_wangshuai(mk(g, z))
    check("case17 开库", r_open["root_detail"]["store_open"] is True, str(r_open["root_detail"]))
    check("case17 假从弱", r_open["tag"] == "假从弱", r_open["tag"])
    check("case17 假从标记", r_open["cong_info"]["is_fake_cong"] is True, str(r_open["cong_info"]))
    # 不开库（无丑）：未仍为微根（非强实根）→ 从格专项定稿后为「假从弱」
    # （tiered 门槛：日主有微根/余气即降假从，不再判真从；真从须完全无藏干或拔根）
    g2, z2 = gz("庚酉 辛申 甲未 庚巳")
    r_noopen = W.compute_wangshuai(mk(g2, z2))
    check("case17 不开库微根→假从弱", r_noopen["tag"] == "假从弱", r_noopen["tag"])
    check("case17 不开库假从标记", r_noopen["cong_info"]["is_fake_cong"] is True, str(r_noopen["cong_info"]))


# ============================ V1.1.1 恋根校验专项用例（追加） ============================
# 说明：卯戌合火场景下，月令统一设为午（火令）且化神火有根，使「恋根」成为成败关键；
#       经完整合化流水线（heju.evaluate）验证恋根拦截逻辑。天干设置避免产生相邻五合干扰。
def _he(g, z, config=None):
    return H.evaluate(g, z, config)


# 卯戌合火 Case1 ✅ 通过，可合火
def case18():
    g, z = gz("乙卯 丙巳 戊戌 庚子")   # 月令巳(火令)、化神火透干(丙)/有根(巳)；局外子/巳无木、土禄刃 → 恋根不触发
    r = _he(g, z)
    liuhe = [h for h in r["he_groups"] if h["type"] == "liuhe"]
    check("case18 卯戌存在六合判定", len(liuhe) == 1, str(liuhe))
    check("case18 恋根不触发→合火成功", liuhe and liuhe[0]["hua_success"], str(liuhe))


# 卯戌合火 Case2 ❌ 恋根绊局（乙木禄在寅，寅为局外独立根）
def case19():
    g, z = gz("乙卯 丙巳 戊戌 庚寅")   # 剔除局内卯，局外寅(乙木禄)→恋根
    r = _he(g, z)
    liuhe = [h for h in r["he_groups"] if h["type"] == "liuhe"]
    check("case19 恋根触发→合火绊", liuhe and liuhe[0]["hua_success"] is False, str(liuhe))


# 卯戌合火 Case3 ❌ 恋根绊局（戊土禄刃级根据地在丑，丑为局外独立根）
def case20():
    g, z = gz("乙卯 丙巳 戊戌 庚丑")   # 剔除局内戌，局外丑(土禄刃级)→恋根
    r = _he(g, z)
    liuhe = [h for h in r["he_groups"] if h["type"] == "liuhe"]
    check("case20 恋根触发→合火绊", liuhe and liuhe[0]["hua_success"] is False, str(liuhe))


# 卯戌合火 Case4 ✅ 通过，可合火（亥为甲木长生非乙木长生；巳不在局外）
def case21():
    g, z = gz("乙卯 丙巳 戊戌 壬亥")   # 局外亥/巳无木禄刃(寅/卯)、无土禄刃(辰戌丑未)→不触发
    r = _he(g, z)
    liuhe = [h for h in r["he_groups"] if h["type"] == "liuhe"]
    check("case21 恋根不触发→合火成功", liuhe and liuhe[0]["hua_success"], str(liuhe))


# 五合 丙辛合水 ✅ 对照（天干五合同逻辑生效）
def case22():
    g, z = gz("丙亥 辛子 壬亥 癸子")   # 月令子(水令)、化神水透干(壬癸)有根；局外无火(巳午)/金(申酉)禄刃→不触发
    r = _he(g, z)
    wuhe = [h for h in r["he_groups"] if h["type"] == "wuhe"]
    check("case22 丙辛合水成功(恋根不触发)", wuhe and wuhe[0]["hua_success"], str(wuhe))


# 五合 甲己合土 ✅ 对照（天干五合同逻辑生效）
def case23():
    g, z = gz("甲申 己未 丙子 庚酉")   # 月令未(土令)、化神土透干(己)有根；局外无木禄刃(寅/卯)，甲(木)无根不破局→不触发
    r = _he(g, z)
    wuhe = [h for h in r["he_groups"] if h["type"] == "wuhe"]
    check("case23 甲己合土成功(恋根不触发)", wuhe and wuhe[0]["hua_success"], str(wuhe))


# 五合 丙辛合水 ❌ 恋根-block 对照（申为辛金禄，局外独立根）
def case24():
    g, z = gz("丙申 辛子 壬亥 壬子")   # 丙辛合水；局外申(金禄刃)→恋根，合水绊
    r = _he(g, z)
    wuhe = [h for h in r["he_groups"] if h["type"] == "wuhe"]
    check("case24 丙辛恋根触发→合水绊", wuhe and wuhe[0]["hua_success"] is False, str(wuhe))


# 恋根开关关闭时与 V1.1 行为一致（不拦截）
def case25():
    g, z = gz("乙卯 丙巳 戊戌 庚寅")   # 同 case19，开启时恋根绊；关闭时仅看月令/根气/冲破
    r_on = _he(g, z)
    r_off = _he(g, z, {"enable_lian_gen_check": False})
    on_liuhe = [h for h in r_on["he_groups"] if h["type"] == "liuhe"][0]
    off_liuhe = [h for h in r_off["he_groups"] if h["type"] == "liuhe"][0]
    check("case25 开启恋根→绊", on_liuhe["hua_success"] is False, str(on_liuhe))
    check("case25 关闭恋根→不拦截(行为同V1.1)", off_liuhe["hua_success"] is True, str(off_liuhe))


# ============================ V1.1.1-ext 回归守护：三合含土参与者但局外无库支 → 仍可成化 ============================
# 验证「土特殊扩展至三合」并非让所有三合必绊：申子辰水含辰(土)参与，局外寅(木，非辰戌丑未、非金禄刃)→不恋根，三合成功。
def case26():
    g, z = gz("壬申 癸子 庚辰 甲寅")   # 三合申子辰水（月令子=中神）含辰(土)；局外寅(木)非库支 → 不恋根 → 成化
    r = _he(g, z)
    sanhe = [h for h in r["he_groups"] if h["type"] == "sanhe"]
    check("case26 三合成功(局外无库支不恋根)", sanhe and sanhe[0]["hua_success"], str(sanhe))



# ============================ ★ 从格专项用例（case27–31） ============================
# 定稿口径：cong_root_gate=tiered / side=both / 印根 fake / 比劫根用日主根清单
def case27():
    # 乙日主坐辰：辰藏乙为木之中气 → level 3，有实根，不得判真从弱，应降假从弱
    g, z = gz("庚戌 戊未 乙辰 戊申")
    r = W.compute_wangshuai(mk(g, z))
    check("case27 中气根档=3", r["debug"]["root_level"] == 3, str(r["debug"]["root_level"]))
    check("case27 中气根→假从弱", r["tag"] == "假从弱", r["tag"])
    check("case27 假从标记", r["cong_info"]["is_fake_cong"] is True, str(r["cong_info"]))


def case28():
    # 日主无根但印星有强根（巳为金长生/印星…此处印有实根）→ 印根不否掉从格，降假从弱
    g, z = gz("己寅 壬戌 壬卯 甲巳")
    r = W.compute_wangshuai(mk(g, z))
    check("case28 日主无根", r["debug"]["root_level"] == 0, str(r["debug"]["root_level"]))
    check("case28 印根为真", r["cong_info"]["residual_yin_root"] is True, str(r["cong_info"]))
    check("case28 印根→假从弱", r["tag"] == "假从弱", r["tag"])


def case29():
    # 独根（午）被冲拔根＝质变清零 → 视同无根，K 占比 0.92 仍判真从弱
    g, z = gz("庚酉 壬子 丙子 己午")
    r = W.compute_wangshuai(mk(g, z))
    check("case29 拔根状态", r["root_status"] == "独根被冲拔根", r["root_status"])
    check("case29 拔根仍真从弱", r["tag"] == "从弱", r["tag"])


def case30():
    # 库微根（未中乙木为余气 10 分）→ 有微根，判假从弱而非真从
    g, z = gz("壬卯 辛辰 癸未 甲未")
    r = W.compute_wangshuai(mk(g, z))
    check("case30 微根档=1", r["debug"]["root_level"] == 1, str(r["debug"]["root_level"]))
    check("case30 微根→假从弱", r["tag"] == "假从弱", r["tag"])


def case31():
    # 阴干不再被「五行级长生」冒充有根：乙坐亥只是中气(3)，甲坐亥才是十干长生(2)
    check("case31 乙坐亥=中气", W._root_level(["亥"], [None], "木", "乙") == 3,
          str(W._root_level(["亥"], [None], "木", "乙")))
    check("case31 甲坐亥=强根", W._root_level(["亥"], [None], "木", "甲") == 2,
          str(W._root_level(["亥"], [None], "木", "甲")))


def case32():
    # 从强侧残余强根：与从弱同源，按「具体天干」判（子只藏癸 → 只有水算强根，辛长生在子但子不藏金）
    check("case32 子支强根仅水", W._strong_root_gan(["子"], [None], set()) == {"水"},
          str(W._strong_root_gan(["子"], [None], set())))
    check("case32 午支不强加木", "木" not in W._strong_root_gan(["午"], [None], set()),
          str(W._strong_root_gan(["午"], [None], set())))
    check("case32 两入口恒等", W._strong_root_wuxing(["子", "午"], [None, None], set())
          == W._strong_root_gan(["子", "午"], [None, None], set()))
    # 从强实证盘：F 占 90.7%、克泄耗无强根
    g, z = gz("癸辰 己子 壬子 庚申")
    r = W.compute_wangshuai(mk(g, z))
    check("case32 从强", r["tag"] == "从强", r["tag"])
    check("case32 从强 F 占比≈0.91", round(r["ratio_share_f"], 3) == 0.907, str(round(r["ratio_share_f"], 3)))


def case33():
    # P4 证据门槛：假从弱若靠「日主中气根」立论，根必须被冲/被绊/居远位
    from bazi_core import heju
    he_flat = heju.evaluate(["甲", "丙", "甲", "丙"], ["子", "寅", "寅", "子"])
    intact = [{"branch_index": 2, "root_type": "中气根", "is_broken": False}]   # 日支中气、无冲无绊
    check("case33 贴身无损中气根不算证据",
          W._cong_fake_weak_root_evidence(intact, ["子", "寅", "寅", "子"], he_flat, {}) is False)
    far = [{"branch_index": 0, "root_type": "中气根", "is_broken": False}]      # 年支＝远位
    check("case33 远位中气根算证据",
          W._cong_fake_weak_root_evidence(far, ["子", "寅", "寅", "子"], he_flat, {}) is True)
    micro = [{"branch_index": 2, "root_type": "微根", "is_broken": False}]      # 微根本身站不住
    check("case33 微根无需额外证据",
          W._cong_fake_weak_root_evidence(micro, ["子", "寅", "寅", "子"], he_flat, {}) is True)
    # 实证盘：中气根在远位 → 仍判假从弱
    g, z = gz("丙未 戊酉 甲未 己辰")
    r = W.compute_wangshuai(mk(g, z))
    check("case33 远位中气根→假从弱", r["tag"] == "假从弱", r["tag"])


def run_all():
    cases = [case1, case2, case3, case4, case5, case6, case7, case8, case9,
             case10, case11, case12, case13, case14, case15, case16, case17,
             case18, case19, case20, case21, case22, case23, case24, case25, case26,
             case27, case28, case29, case30, case31, case32, case33,
             case6b, case6c, case6d]
    for fn in cases:
        try:
            fn()
        except Exception as e:
            check(fn.__name__, False, "EXCEPTION: %s" % e)
    total = len(PASS)
    failed = [p for p in PASS if not p[1]]
    print("\n========================================")
    print("旺衰模块单元测试：%d 用例，%d 断言，失败 %d" % (len(cases), total, len(failed)))
    for name, cond, detail in failed:
        print("  ✗ [%s] %s" % (name, detail))
    if failed:
        print("结果：FAIL")
        return 1
    print("结果：PASS ✅")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
