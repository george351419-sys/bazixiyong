# -*- coding: utf-8 -*-
"""格局维度喜用 —— 依据李厚君师傅《八字格局核心笔记整理》。

笔记「感悟总结」原文（本层的唯一取用总纲）：

    先看格局是否有病，有病先治病，有病有药方为贵（尤其以调候之病最优先）；
    然后看格局的用在哪里（无病再看用），顺用逆用要分清，用神只要出现在天干，
    优先取出现在天干的用神；最后考虑身强身弱。

因此本层是「定格之后」的独立一层，不参与、不推翻 PRD 的定格 / 清浊 / 成破：
  1. 扫病：通病（笔记「如果有病」通病段）+ 本格病（笔记表2「病在」），
     按 坏格 / 格局病 / 轻 三级；轻病（非本格正神被克）只提示、不夺用。
  2. 有坏格或格局病 → mode=治病为先：药神按「合去 > 克掉 > 通关 > 隔开」
     （笔记「要么隔开，要么合掉，或克掉，或化掉」及逐病举例）排序，
     原顺逆相神降为辅佐（xi_shen）。
  3. 无病 → mode=吉神顺用 / 凶神逆用：取用候选来自笔记表2「用在」，
     叠加 PRD GE_ROUTE 相神兜底，按「透干有根 > 透干 > 藏干有根 > 原局无」排序。
  4. 旺衰（身强身弱）只在 note / fuyi_hint 里作附加提示，不改格局取用
     （PRD §六.8 明令旺衰不参与定格；笔记亦把身强身弱放在「最后考虑」）。

与 PRD / 现有实现的理论分歧（**本层不改定格，仅记录**）：
  - 笔记「调候之病最优先」：调候模块（bazi_core.tiaohou）**已独立上线**，
    作为 engine.tiaohou 独立维度输出；但**本层 Step8 仍未把调候之病并入病清单**，
    故 tiaohou_pending=True 表示「本层未合并」而非「模块未实现」，
    后续接入时须把调候之病置于病清单最前。
  - 笔记表1「禄劫/羊刃格：天干透财官杀则以财格/官格/杀格论」与 PRD §四
    「禄刃铁则：透干不升格」直接冲突 → 仍按 PRD 定格，仅取用层给提示。
  - 笔记「印格总结：印格一般身强，直接取财、官、食伤为用」与 PRD 正印格
    顺用「官杀生印、比劫护印、忌财破印」冲突 → 以 PRD 顺用为主，
    笔记的「印配食伤」列为辅佐候选，不把财列为印格喜用。
  - 笔记「伤官伤尽」「羊刃驾杀」等需要全局气势判断，V1 只作候选、不自动成立。
  - 「身弱不担财取印」属扶抑派，PRD 明令不混入 → 只放 fuyi_hint。
"""
from __future__ import annotations
from .geju_status import State

from . import metadata as M
from .geju_treatment import solve, expands
from .geju_rules import qi_table, verify_rescue, ke, effective_occ, power, record_power, rescue_fraction

import re
from copy import deepcopy


# 与 geju.SHISHEN_GROUP 保持同步（独立模块避免与 geju 循环引用；如有改动请两处同步）。
SS_GROUP = {
    "正官": "官", "七杀": "官",
    "正财": "财", "偏财": "财",
    "正印": "印", "偏印": "印",
    "食神": "食伤", "伤官": "食伤",
    "比肩": "比劫", "劫财": "比劫",
}
# 吉神（善神）顺用；PRD §2.3 善神表只列正官/正财/正印/食神，偏财未归类，
# 但 GE_ROUTE 明列偏财 good=True（财喜食伤生、官护财，属顺用），故一并纳入。
# 主流程会透传 ge_good（与 Step4 同一口径），此处仅作独立调用时的兜底。
GOOD_SS = {"正官", "正财", "偏财", "正印", "食神"}
ALL_SS = set(SS_GROUP)


def _expand(groups):
    """组名 / 具体十神名 → 具体十神名列表（含比劫，逻辑同 geju._expand_groups）。"""
    out = []
    group_names = set(SS_GROUP.values())
    for g in groups:
        if g in group_names:
            for ss, grp in SS_GROUP.items():
                if grp == g and ss not in out:
                    out.append(ss)
        elif g in ALL_SS and g not in out:
            out.append(g)
    return out


# 笔记表2「用在」：格局 -> [(路线名, 候选十神列表)]，顺序即取用优先级。
# 另补 PRD GE_ROUTE 相神兜底（见 _yong_candidates），保证与成破判定不脱节。
GE_YONG = {
    "正官": [("财生官", ["正财", "偏财"]), ("官印相生", ["正印", "偏印"])],
    "七杀": [("食神制杀", ["食神", "伤官"]), ("杀印相生", ["正印", "偏印"]),
             ("羊刃驾杀", ["劫财"])],
    "正财": [("食伤生财", ["食神", "伤官"]), ("财生官", ["正官"])],
    "偏财": [("食伤生财", ["食神", "伤官"]), ("财生官", ["正官"])],
    "正印": [("官印相生", ["正官"]), ("杀印相生", ["七杀"]),
             ("印配食伤", ["食神", "伤官"])],
    "食神": [("食神生财", ["正财", "偏财"]), ("食神制杀", ["七杀"]),
             ("食神佩印", ["正印"])],
    "伤官": [("伤官生财", ["正财", "偏财"]), ("伤官配印", ["正印", "偏印"]),
             ("伤官制杀", ["七杀"]), ("伤官伤尽", [])],
    "偏印": [("财制枭", ["偏财", "正财"]), ("官印相生", ["正官"]),
             ("枭印配伤官", ["伤官"])],
}

# 病 -> 药规则：(治法, 药十神列表, 说明)，顺序即笔记优先级。
# 「合去」的 ss 列表留空 = 合去病神本身，由 _pick_yao 查天干五合是否已解。
# 优先级依据笔记：合掉最好 > 克掉 > 通关 > 隔开；逐病举例见 BING_NOTE。
BING_YAO = {
    "官杀混杂": [("合去", [], "正官格合杀留官；七杀格合官留杀"),
                 ("克掉", ["食神", "伤官"], "食伤制去多余官杀")],
    "财党七杀": [("制伏", ["食神", "伤官"], "食神制杀（笔记首选）"),
                 ("化掉", ["正印", "偏印"], "杀印相生"),
                 ("合去", [], "合杀留财 / 合财留杀")],
    "七杀无制": [("制伏", ["食神", "伤官"], "食神制杀"),
                 ("化掉", ["正印", "偏印"], "杀印相生"),
                 ("合去", [], "比劫或食神合杀")],
    "伤官见官": [("克掉", ["正印", "偏印"], "印制伤官（首选）"),
                 ("合去", [], "天干合掉伤官"),
                 ("通关", ["正财", "偏财"], "财通关（笔记：其次）")],
    "枭印夺食": [("克掉", ["正财", "偏财"], "财来坏印（笔记：优先）"),
                 ("合去", [], "合掉枭印"),
                 ("通关", ["比肩", "劫财"], "比劫通关（笔记存疑）")],
    "比劫夺财": [("克掉", ["正官", "七杀"], "官杀制比劫（首选）"),
                 ("合去", [], "天干合掉比劫"),
                 ("通关", ["食神", "伤官"], "食伤通关生财")],
    "财来坏印": [("通关", ["正官", "七杀"], "官杀通关，成官印相生"),
                 ("合去", [], "合掉财"),
                 ("克掉", ["比肩", "劫财"], "比劫劫财护印")],
    # 笔记「混杂者，需合掉或克掉？」原文带问号；且「取正神的克制者」对印格
    # 会推出「用财克印」——与本格「财来坏印」之病自相矛盾。故 V1 只给「合去」一法。
    "正神混杂": [("合去", [], "合去多余一字，留单一格神")],
    "食藏伤透": [("合去", [], "喜合伤（笔记）")],
    "财多官埋": [("克掉", ["比肩", "劫财"], "比劫劫财护官"),
                 ("合去", [], "合掉多余之财")],
    "制杀太过": [("生扶", ["正财", "偏财"], "财生杀 / 财坏印以养杀")],
    "财露无官杀": [("护财", ["正官", "七杀"], "需官杀护财")],
    "枭印无制": [("克掉", ["正财", "偏财"], "偏财制枭（笔记：偏印格只需看偏财）")],
    "印过旺": [("克掉", ["正财", "偏财"], "财来坏印以达平衡")],
    "阳刃无制": [("制伏", ["正官", "七杀"], "官杀制刃，有制方成格")],
}

# ============================ 基础工具 ============================
def _recs(ctx, ss):
    return ctx["occ"].get(ss, [])


def _tou(ctx, ss):
    return [r for r in _recs(ctx, ss) if r["tou"]]


def _tou_names(ctx, names):
    return all(_tou(ctx, s) for s in names)


def _present_names(ctx, names):
    """names 中任一十神在传入 ctx 的范围内「透出或藏根」即视为并见。

    注意：_detect_bing() 会把 ctx 过滤成仅天干，再调用本函数；因此当前伤病
    实际只认天干，不应把本函数的通用藏根能力理解为「藏干也触发伤官见官」。
    """
    for s in names:
        recs = _recs(ctx, s)
        if any(r["tou"] or r["root"] for r in recs):
            return True
    return False


def _present_all(ctx, names):
    """names 中每个十神都「透出或藏根」才算并见（以传入 ctx 的记录范围为准）。

    用于「官杀混杂 / 伤官见官」这类必须两神同现的病：只出现其中一方（如仅见正官、
    不见七杀；仅见正官、不见伤官）不构成该病的并见冲突。_detect_bing() 调用前
    已过滤为仅天干，因此伤病实际不认地支藏干。
    """
    for s in names:
        recs = _recs(ctx, s)
        if not any(r["tou"] or r["root"] for r in recs):
            return False
    return True


def _parse_ss(s):
    """从格式化串（如「辛（七杀·藏）」）提取十神名「七杀」；无括号则原样返回。"""
    if not s:
        return ""
    m = re.search(r"（([^·）]+)", s)
    return m.group(1) if m else s


def _fmt(ss, rec=None):
    if rec is None:
        return "%s（原局无，待运取）" % ss
    return "%s（%s·%s%s）" % (
        rec["gan"], ss, "透" if rec["tou"] else "藏",
        "·有根" if rec["root"] else "·虚浮")


def _key(s):
    """跨来源去重键：「丁（伤官·透·有根）」/「丁（伤官）」→ ("丁","伤官")。

    病神由喜用层格式化、忌神来自 Step4（格式略简），两者需归一后再并表。
    """
    gan = s[0] if s else ""
    m = re.search(r"（([^·）]+)", s)
    return (gan, m.group(1) if m else s)


def _dedup(seq):
    seen, out = set(), []
    for s in seq:
        k = _key(s)
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out


def _best_rec(ctx, ss_list):
    """笔记「用神只要出现在天干，优先取出现在天干的用神；天干地支都透出发挥作用才大」。

    排序：透干有根 > 透干虚浮 > 藏干有根 > 其余。返回 (score, ss, rec) 或 None。
    """
    cands = []
    for ss in _expand(ss_list):
        for r in _recs(ctx, ss):
            score = (int(r["tou"]), power(ctx["occ"], ss),
                     int(r["root"]), r.get("weight",1))
            if r.get("weight",1) == 0:
                continue
            cands.append((score, ss, r))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0], reverse=True)
    return cands[0]


def _he_gan_set(ctx):
    """所有参与天干五合（含合绊）的干字 —— 合绊亦「去其杂」，与 Step5 同口径。"""
    out = set()
    for grp in ctx["he"]["he_groups"]:
        if grp["type"] == "wuhe":
            out.update(grp["members"])
    return out


def _pick_yao(bing, ctx, rules=None):
    """按当前病药表优先级取药，返回 (全部药, 局内已有药, 日志列表)。

    笔记「合掉最好」是治法优先级，但「有病有药方为贵」讲的是**局内真有药**：
    故输出按「局内已有药 > 待运取」重排，避免「局内无合，待运取」占住首选用神。
    - 「合去」：病神已被天干五合合去 → 病可解（局内有药）；否则明写待运。
    - 其余治法：在局内找最有力的字（透干优先），找不到则给「应取十神 + 待运取」。
    - rules 由 compute_xiyong_geju 传入动态病药表；独立调用时回退全局 BING_YAO。
    """
    rules = BING_YAO if rules is None else rules
    in_chart, pending, log = [], [], []
    he_gans = _he_gan_set(ctx)
    bing_gans = set()
    for ss in bing["bing_ss"]:
        for r in _tou(ctx, ss):
            bing_gans.add(r["gan"])

    for method, ss_list, note in rules.get(bing["name"], []):
        if method == "合去":
            hit = sorted(bing_gans & he_gans)
            adjacent = any(g["type"] == "wuhe" and
                           any(abs(i-j) == 1 for i in g.get("idx", []) for j in g.get("idx", []))
                           and set(g["members"]) & bing_gans for g in ctx["he"]["he_groups"])
            if hit and not adjacent:
                pending.append("合去%s｜远隔五合，仅救一半" % "".join(hit))
                continue
            if hit:
                in_chart.append("合去%s｜%s｜局内已有五合，病可解"
                                % ("".join(hit), note))
                log.append("  · %s：%s已被五合合去（药已在局内）"
                           % (bing["name"], "".join(hit)))
            else:
                pending.append("合去%s｜%s｜局内无合，待运取"
                               % ("、".join(bing["bing_ss"]), note))
            continue
        candidates = [(ss,r) for ss in _expand(ss_list) for r in _recs(ctx,ss) if r.get("weight",1)>0]
        candidates.sort(key=lambda item:(item[1]["tou"],power(ctx["occ"],item[0]),item[1]["weight"]),reverse=True)
        for ss,r in candidates:
            txt="%s｜%s｜%s" % (_fmt(ss,r),method,note)
            if not r["tou"]:
                pending.append(txt+"｜潜在救应、待透")
            else:
                in_chart.append(txt)
        if not candidates and ss_list:
            pending.append("%s｜%s｜%s｜原局无，待运取" % ("/".join(ss_list),method,note))
    # 同一干字/十神在一病下可能由多个藏干根位重复给出；展示层按 _key 去重。
    in_chart = _dedup(in_chart)
    return _dedup(in_chart + pending), in_chart, log


# ============================ 病检测 ============================
def _detect_bing(ctx):
    """返回 (主病列表, 轻病列表, 日志列表)。

    主病 = 坏格 / 格局病（触发「治病为先」）；轻病 = 笔记「非该正神格下，
    天干正神被克其实影响不大…隔开即可，或者合掉其中一个最好」，只提示不夺用。
    """
    main, light, log = [], [], []
    ge = ctx["ge_ss"]
    full_ctx = ctx
    ctx = dict(ctx, occ={ss: [r for r in rs if r["tou"]]
                         for ss, rs in ctx["occ"].items()})

    def count(names):
        return sum(r.get("weight", 1.0 if r["tou"] else 0.5)
                   for ss in names for r in full_ctx["occ"].get(ss, []))

    def add(name, bing_ss, severity, note, target=None):
        bing_ss=[ss for ss in bing_ss if _tou(ctx,ss)]
        item = {"name": name, "bing_ss": list(bing_ss),
                "bing_shen": [_fmt(s, (_tou(ctx, s) or _recs(ctx, s) or [None])[0])
                              for s in bing_ss],
                "severity": severity, "note": note}
        if target:
            item["target"] = target
        (main if severity in ("坏格", "格局病") else light).append(item)
        log.append("Step8：检出%s【%s】，病神=%s" % (
            severity, name, "、".join(bing_ss) or "（结构性失衡，无单一病神）"))

    # ---------- 通病（笔记「如果有病」第一段） ----------
    # 官杀混杂：本格为正官/七杀时坏格，其余格按笔记「非该正神格下影响不大」列轻病。
    # 仅「天干透出」的正官、七杀两神同现才算混杂（yan 2026-11-06：官杀混杂只计天干，
    # 地支藏干不论；故杜月笙丑中辛七杀为藏干，不判官杀混杂）；仅见一方不构成冲突。
    if _tou_names(ctx, ["正官", "七杀"]):
        extra = "七杀" if ge == "正官" else ("正官" if ge == "七杀" else "七杀、正官")
        sev = "坏格" if ge in ("正官", "七杀") else "轻"
        add("官杀混杂", extra.split("、"), sev,
            "笔记：根据格局需要合掉其中一个（正官格合杀留官 / 七杀格合官留杀）")

    # 财党七杀 / 七杀无制：笔记明写「不论在哪里都是病」→ 一律坏格。
    sha_tou = bool(_tou(ctx, "七杀"))
    cai_tou = bool(_tou(ctx, "正财") or _tou(ctx, "偏财"))
    zhi_tou = bool(_tou(ctx, "食神") or _tou(ctx, "伤官"))
    yin_tou = bool(_tou(ctx, "正印") or _tou(ctx, "偏印"))
    if sha_tou and cai_tou and not zhi_tou:
        add("财党七杀", ["七杀"], "坏格",
            "笔记：财党杀（杀旺无制）不论在哪里都是病；宜食神制杀 / 杀印相生 / 合杀留财")
    if sha_tou and not zhi_tou and not yin_tou and ge != "七杀":
        add("七杀无制", ["七杀"], "坏格",
            "笔记：七杀无制，或食神制杀、或杀印相生、或合杀")

    # 伤官见官：笔记「尤其以伤官见官危害最大」→ 一律坏格（调候例外本层 V1 不判，
    # 调候维度另见 engine.tiaohou）。病检测只看天干，故须伤官、正官两神同透；
    # 地支藏干之间的伤官见官不在本层成立。
    if _present_all(ctx, ["伤官", "正官"]):
        add("伤官见官", ["伤官"], "坏格",
            "病在伤官，优先印制，其次合伤，再取财通关"
            "（金水伤官喜见官属调候，本层 V1 未合并调候之病）")

    # 枭印夺食：食神格 / 偏印格坏格；其余轻。
    if _tou(ctx, "偏印") and _tou(ctx, "食神"):
        sev = "坏格" if ge in ("食神", "偏印") else "轻"
        add("枭印夺食", ["偏印"], sev,
            "笔记：优先用财坏印，然后合掉枭印（比劫通关存疑）", target="偏印")

    # 比劫夺财：财格坏格；其余轻。
    bijie_tou = bool(_tou(ctx, "比肩") or _tou(ctx, "劫财"))
    if bijie_tou and cai_tou:
        sev = "坏格" if ge in ("正财", "偏财") else "轻"
        add("比劫夺财", ["比肩", "劫财"], sev,
            "优先官杀制比劫，其次合去，再取食伤通关", target="比劫")

    # 财来坏印：印格坏格；其余轻。
    if cai_tou and bool(_tou(ctx, "正印")):
        sev = "坏格" if ge in ("正印", "偏印") else "轻"
        add("财来坏印", ["正财", "偏财"], sev,
            "笔记：官杀通关成官印相生，或合掉财，或比劫劫财", target="正财")

    # 仅豁免实际构成相隔双路线的具体病神组合。
    def separated(a,b):
        ra=_tou(ctx,a);rb=_tou(ctx,b)
        return ra and rb and all(abs(x["idx"]-y["idx"])!=1 for x in ra for y in rb)
    exempt=set()
    if ge=="七杀" and separated("偏印","食神"): exempt.add("枭印夺食")
    if ge=="伤官" and any(separated(a,b) for a in ("正财","偏财") for b in ("正印","偏印")):
        exempt.add("财来坏印")
    main[:]=[b for b in main if b["name"] not in exempt]
    light[:]=[b for b in light if b["name"] not in exempt]

    # ---------- 本格病（笔记表2「病在」+「格局其他病」） ----------
    # 同类混杂（除财格外，笔记「正神不喜混杂」）。官杀混杂已在通病处理，不重复。
    if ge in ("正官", "七杀", "正印", "偏印", "食神", "伤官"):
        grp = SS_GROUP.get(ge)
        same = [s for s in SS_GROUP if SS_GROUP[s] == grp and s != ge]
        if same and any(_tou(ctx, s) for s in same) and grp != "官":
            add("正神混杂", same, "格局病",
                "笔记：正神不喜混杂（除财格外），需合掉或克掉多余一字", target=same[0])

    # 笔记「正神太多者，则需正神的克制者来克？」原文带问号、作者自己存疑，
    # 且对财格会推出「财多→取比劫克财」这种与「比劫夺财」自相矛盾的药
    # （实战亦无此取法）。故不落为硬规则，只保留有明确举例的「印过旺」：
    # 「正印过多而变枭印，则应用财来坏印」。

    # 食藏伤透
    if ge == "食神" and not _tou(ctx, "食神") and _tou(ctx, "伤官"):
        add("食藏伤透", ["伤官"], "格局病", "笔记：食藏伤透，喜合伤")

    # 财多官埋
    if ge == "正官" and cai_tou and count(["正财", "偏财"]) >= 3:
        # 病在「财过旺埋官」，属结构性失衡：病神不应列为忌神（财本是正官格相神），
        # 药取比劫劫财护官，不取「正官平衡」（格神自身不能作为用药）。
        add("财多官埋", [], "格局病",
            "笔记：财太旺致财多官埋，宜比劫劫财护官以存官")

    # 制杀太过 / 杀弱
    shishang_cnt = count(["食神", "伤官"])
    if ge == "七杀" and _tou(ctx,"七杀") and zhi_tou and shishang_cnt >= 2 and count(["七杀"]) <= 1:
        add("制杀太过", ["食神", "伤官"], "格局病",
            "笔记：七杀太弱（身太旺或食伤太强）可用财生杀；印重克食伤则财坏印")

    # 财露无官杀：笔记「财格中，如果天干透出比劫，要么有官杀克制，要么有食伤通关」。
    # 已有食伤通关即不缺护财之字，不再判病。病在「财露无官杀护财」，并非财本身为忌
    # （财即格神），故病神留空、药取官杀。
    if ge in ("正财", "偏财") and cai_tou\
            and not (_tou(ctx, "正官") or _tou(ctx, "七杀"))\
            and not zhi_tou:
        add("财露无官杀", [], "格局病", "笔记：财露天干而无官杀，需官杀护财")

    # 枭印无制（偏印格无财）
    if ge == "偏印" and not (_recs(ctx, "正财") or _recs(ctx, "偏财")):
        add("枭印无制", ["偏印"], "格局病",
            "笔记：枭印无制（无财）也是废掉；偏印格只需看偏财")

    # 印过旺
    if ge == "正印" and _tou(ctx,"正印") and count(["正印", "偏印"]) >= 3:
        add("印过旺", ["正印"], "格局病",
            "笔记：正印过多而变枭印，应用财来坏印", target="正印")

    # 阳刃无制（禄刃分支由 PRD Step3 判定，这里只补药）
    if ctx["ge_category"] == "禄刃" and ctx["ge_status"] == "真破格"\
            and "阳刃" in (ctx["ge_name"] or ""):
        add("阳刃无制", ["劫财"], "坏格",
            "笔记：羊刃以官杀为制，有制才能成格，否则下等格局")
        main[-1]['blade_control_ratio'] = ctx.get('blade_control_ratio', 1.0)

    # ---------- 路线 / 定格联动 ----------
    # 七杀/伤官双路线互斥：已在定格层判「真破格·浊而无去」，此处补录为坏格病，
    # 使 has_bing 与其对齐；无单一药，喜用层保留「择一取用」。
    if ctx.get("route_label") == "双路线混杂":
        add("双路线互斥", [], "坏格",
            "七杀/伤官双路线（制杀vs化杀 / 生财vs佩印）互斥混杂、浊而无去，格局破败，须择一不可并用")

    # 定格层成破若未被上述具体病覆盖（main 为空），补一条「格局破败」使 has_bing 与成破对齐：
    gs = ctx.get("ge_status")
    if gs and gs != "成格" and not main:
        ji_names = [_parse_ss(s) for s in ctx.get("ji_shen_list", [])]
        ji_names = [n for n in ji_names if n]
        if ji_names:
            sev = "坏格" if gs == "真破格" else "格局病"
            add("忌神破格(%s)" % gs, ji_names, sev,
                "定格层(Step6)判%s，忌神=%s，喜用层对齐补录" % (gs, "、".join(ji_names)))
        elif gs == "真破格":
            add("格局破败", [], "坏格", "定格层判真破格（非单一忌神所致），喜用层对齐补录")

    return main, light, log


# ============================ 无病取用 ============================
def _yong_candidates(ctx):
    """无病取用候选：笔记表2「用在」优先，PRD GE_ROUTE 相神兜底。

    PRD 双路线（七杀/伤官）已由 Step4 选定 route_label，同名路线提到最前，
    避免喜用层与成破判定各说一套。
    """
    ge = ctx["ge_ss"]
    routes = list(GE_YONG.get(ge, []))
    if ge in ("七杀", "伤官") and ctx.get("route_label") in dict(routes):
        routes = [r for r in routes if r[0] == ctx["route_label"]]
    label = ctx.get("route_label") or ""
    routes.sort(key=lambda r: 0 if (label and (label in r[0] or r[0] in label)) else 1)
    # GE_ROUTE 相神兜底（防止笔记表缺项）
    out = [(name, ss) for name, ss in routes]
    for ss in ctx.get("route_xiang", []):
        if ss and ss not in [s for _, lst in out for s in lst]:
            out.append(("相神护格", [ss]))
    return out


def _pick_yong(ctx):
    """按「透干优先」返回 (首选列表, 辅佐列表, 日志列表)。"""
    log, primary, secondary = [], [], []
    for route, ss_list in _yong_candidates(ctx):
        if not ss_list:
            continue
        best = _best_rec(ctx, ss_list)
        if best is None:
            log.append("Step8：路线【%s】候选%s原局不显，待运补" % (route, "/".join(ss_list)))
            continue
        _, ss, r = best
        txt = "%s｜%s" % (_fmt(ss, r), route)
        (primary if r["tou"] and r["root"] else secondary).append(txt)
        for other_ss in _expand(ss_list):
            for other in _recs(ctx,other_ss):
                candidate="%s｜%s" % (_fmt(other_ss,other),route)
                if candidate!=txt and other.get("weight",1)>0: secondary.append(candidate)
    if not primary and secondary:
        # 笔记「用神强：要在天干上透出，否则格局要降级」；透而虚浮仍属透，
        # 只是不得地根，故记「乏力、待运」而非「未透」。
        primary = [secondary.pop(0)]
        log.append("Step8：无「透干且有根」之相神，退取透干虚浮/藏干者，用神乏力需待运")
    # PRD §六.6：七杀 / 伤官双路线互斥。Step4 已判「双路线混杂、浊而无去」时，
    # 喜用层不得把两条路线并列为用，只留一条首选，其余降为辅佐并注明须择一。
    if ctx.get("route_label") == "双路线混杂" and len(primary) > 1:
        secondary = primary[1:] + secondary
        primary = primary[:1]
        log.append("Step8：Step4 判双路线互斥混杂，喜用层只留一条首选，"
                   "其余降为辅佐（须择一，不可并用）")
    return primary + secondary, [], log


# ============================ 主入口 ============================
def compute_xiyong_geju(ctx):
    """格局维度喜用主入口。ctx 由 geju.compute_geju 在主流程末尾组装。

    ctx 必填：occ / he / gans / day_gan / ge_ss / ge_category / ge_name /
              ge_status / clean_level / xiang_shen_list / ji_shen_list /
              route_label / route_xiang / wangshuai_tag / special_ge
    返回：结构化 dict（含 trace，供并入主 trace_log）。
    """
    trace = ["Step8：格局喜用取用原则 = 有病治病为先 / 无病吉神顺用·凶神逆用"
             "（李厚君师傅《八字格局核心笔记整理》）"]
    treatment_rules = dict(BING_YAO)
    original_ctx = ctx
    if ctx.get("special_ge"):
        main, light, det_log = [], [], []
    else:
        ctx = dict(ctx, occ=effective_occ(ctx["occ"],ctx["he"]), he=dict(ctx["he"],he_groups=[]), _effective_occ=True)
        main, light, det_log, treatment_rules = build_relation_diseases(ctx,[_parse_ss(x) for x in ctx.get("ji_shen_list",[])])
        ctx["he"] = original_ctx["he"]
    trace.extend(det_log)

    # 逐病配药：局内已有药优先于「待运取」（笔记「有病有药方为贵」）
    yao_in_chart_all, yao_pending_all = [], []
    for b in main:
        yao, in_chart_yao, log = _pick_yao(b, ctx, treatment_rules)
        b["yao"] = yao
        b["yao_in_chart"] = in_chart_yao
        yao_in_chart_all.extend(in_chart_yao)
        yao_pending_all.extend([y for y in yao if y not in in_chart_yao])
        trace.extend(log)
    yao_all = _dedup(yao_in_chart_all + yao_pending_all)
    yao_in_chart = bool(yao_in_chart_all)
    for b in light:
        b["yao"] = ["隔开即可，或合掉其中一个（笔记：影响不大）"]

    tiaohou_note = ("笔记：调候之病最优先（金水伤官喜见官、木火伤官需见印等）；"
                    "调候模块已独立上线（见 engine.tiaohou），但本层 Step8 尚未把"
                    "调候之病并入病清单，后续接入时须置于病清单最前")

    # 扶抑只作附加提示（PRD 不混入扶抑派）；区分「身弱无根」与「身弱（有根）」，
    # 不再一律写成「身弱有根」（旧版硬编码 bug）。
    fuyi_hint = ""
    tag = ctx.get("wangshuai_tag") or ""
    if tag in ("身弱", "中和偏弱", "身弱无根"):
        if ctx["ge_ss"] in ("正财", "偏财"):
            base = "扶抑方向喜印比；比劫可能夺财，须在格局冲突与承受能力评估中另行裁决"
        elif tag == "身弱无根":
            base = "身弱无根，扶抑维度更需印比生扶"
        else:
            base = "身弱（有根），扶抑维度优先用印"
        fuyi_hint = "旺衰标签=%s：%s；仅作参考，不参与格局取用" % (tag, base)

    # 双路线相邻相克：定格仍记破格，取强路线，明确冲去弱路线。
    route_resolution = []
    if "双路线" in ctx.get("ge_note", "") and ctx.get("ge_status") == "真破格":
        from .geju_treatment import records as route_records
        available=[r for r in route_records(original_ctx['occ'],original_ctx['he']) if r['tou'] and r['effective']>0]
        strong_names=set(ctx.get('route_xiang',[]))
        route_names={ss for _,names in GE_YONG.get(ctx['ge_ss'],[])[:2] for ss in names}
        strong=[r for r in available if r['ss'] in strong_names]
        weak=[r for r in available if r['ss'] in route_names and r['ss'] not in strong_names]
        describe=lambda r: '%s（%s·%s柱·力量%.2f）' % (r['gan'],r['ss'],('年','月','日','时')[r['idx']],r['effective'])
        route_resolution=['保留%s；冲去较弱的%s（待运解决）' % ('、'.join(describe(r) for r in strong),'、'.join(describe(r) for r in weak))] if strong and weak else []

    # ---------- mode 判定 ----------
    if ctx.get("special_ge"):
        mode = "外格另论"
    elif main and (ctx["ge_ss"] is not None or ctx["ge_category"] == "禄刃"):
        # 阳刃无制虽属禄刃局，仍是「有病治病为先」（笔记：官杀制刃，有制才成格）
        mode = "治病为先"
    elif ctx["ge_category"] == "禄刃":
        mode = "禄刃取相"
    elif ctx["ge_ss"] is None:
        mode = "无格可取"
    elif ctx.get("ge_good", ctx["ge_ss"] in GOOD_SS):
        mode = "吉神顺用"
    else:
        mode = "凶神逆用"

    yong, xi, ylog = _pick_yong(ctx)
    trace.extend(ylog)

    if route_resolution:
        yong = [_fmt(ss, _best_rec(ctx, [ss])[2]) + "｜保留强路线"
                for ss in ctx.get("route_xiang", []) if _best_rec(ctx, [ss])]
        yao_all = []

    # 病神 / 忌神（跨来源按「干字+十神」去重）
    ji = _dedup([s for b in main for s in b["bing_shen"]]
                + list(ctx.get("ji_shen_list", [])))
    # 格神与其护格相神不可同时列为忌神（如正官格之财/印、伤官格之财印）；
    # 结构性病（财多官埋 / 财露无官杀）已不写病神，此处兜底再过滤一次。
    ge_ss = ctx.get("ge_ss")
    xiang_ss_set = set()
    for s in ctx.get("xiang_shen_list", []):
        xiang_ss_set.add(_parse_ss(s))
    xiang_ss_set.update(ctx.get("route_xiang", []))
    if ge_ss:
        xiang_ss_set.add(ge_ss)
    ji = [s for s in ji if _parse_ss(s) not in xiang_ss_set]

    if mode == "治病为先":
        principle = ("有病先治病，有病有药方为贵：药神优先于顺逆相神"
                     "（治法按各病规则表；原局有效药优先于待透与待运建议）")
        if yao_all and not route_resolution:
            # 有病时：药为用，原顺逆相神降为辅佐
            yong = yao_all
            yong_keys = {_key(s) for s in yong}
            combined_xi = _dedup(
                [s for s in yong] + [s for s in xi]
                + list(ctx.get("xiang_shen_list", [])))
            xi = [s for s in combined_xi if _key(s) not in yong_keys][:4]
            trace.append("Step8：治病为先，原顺逆相神降为辅佐；%s"
                         % ("药已在原局" if yao_in_chart else "原局无药，待运取药"))
        else:
            # 结构性破格（如双路线互斥）无单一药可施，保留「择一取用」，不空用神。
            trace.append("Step8：治病为先但无单一药可施（结构性破格），保留择一取用")
    elif mode in ("吉神顺用", "凶神逆用"):
        principle = ("无病再看用：格神为%s，%s；用神优先取透干有根者"
                     % ("吉神（善神）" if mode == "吉神顺用" else "凶神",
                        "顺用——保护生扶" if mode == "吉神顺用" else "逆用——制伏化泄"))
        trace.append("Step8：无病，按%s取用，首选=%s"
                     % (mode, "、".join(yong) or "原局不显，待运补"))
    else:
        principle = "%s：V1 不做独立取用，沿用格局相神作参考" % mode
        # 禄刃 / 无格 / 外格：GE_YONG 无对应条目，仍把 Step3/4 已判相神摆出来，
        # 避免这一层输出空白（笔记禄劫/羊刃另有「透干升格」说，见模块头分歧声明）。
        ref = [s for s in ctx.get("xiang_shen_list", []) if s]
        if not yong:
            yong = ref[:2]
        xi = [s for s in ref if s not in yong] or xi
        trace.append("Step8：%s，沿用格局相神作参考" % mode)

    # 同一十神既作「辅佐用神」又列「病神/忌神」属自相矛盾，统一剔除：
    # 忌神（main 病神 + 定格忌神）与轻病病神均不得进入辅佐列表。
    ji_key_set = {_key(s) for s in ji}
    bing_key_set = {_key(s) for b in main for s in b["bing_shen"]}\
        | {_key(s) for b in light for s in b["bing_shen"]}
    xi = [s for s in xi if _key(s) not in ji_key_set and _key(s) not in bing_key_set]

    note_parts = [
        tiaohou_note,
        "笔记：用神只要出现在天干，优先取透干者；天干地支都透出发挥作用才大",
    ]
    if light:
        note_parts.append("轻病（不夺用）：%s；笔记「非该正神格下，天干正神被克影响不大，"
                          "隔开即可或合掉其中一个」" % "、".join(b["name"] for b in light))
    if fuyi_hint:
        note_parts.append(fuyi_hint)
    if ctx.get("route_label"):
        note_parts.append("Step4 已选路线：%s（七杀/伤官双路线互斥，喜用层沿用）"
                          % ctx["route_label"])
    if ctx.get("route_label") == "双路线混杂":
        note_parts.append("Step4 判双路线互斥混杂、浊而无去；喜用须择一不可并用，品级受限")

    # 所有首选均由具体柱位组合求解；旧文本仅作为说明，不参与身份判定。
    allowed = {ss for disease in main for _,names,_ in treatment_rules.get(disease["name"],[]) for ss in _expand(names)}
    if not main or route_resolution:
        allowed.update(ss for _,names in _yong_candidates(ctx) for ss in _expand(names))
        if ctx["ge_category"]=="禄刃":
            allowed.update(_parse_ss(x) for x in ctx.get("xiang_shen_list",[]))
    rank={}
    for index,(_,names) in enumerate(_yong_candidates(ctx)):
        for ss in _expand(names): rank.setdefault(ss,index)
    auxiliary_ss={ss for _,names in _yong_candidates(ctx) for ss in _expand(names)}
    auxiliary_ss.update(_parse_ss(x) for x in ctx.get('xiang_shen_list',[]))
    resolved=solve(dict(original_ctx,route_priority=rank,auxiliary_ss=auxiliary_ss),main,treatment_rules,allowed)
    def format_rec(r):
        position=('年','月','日','时')[r['idx']]+('干' if r['tou'] else '支藏干')
        actions=[e for e in resolved['allocations'] if e['drug_id']==r['id']]
        targets=sorted({e['target_id'] for e in actions})
        describe=lambda ident: (('年','月','日','时')[int(ident.split(':')[0])]+'干'+ident.split(':')[-1]) if ident[0].isdigit() else ident.replace('structure:','')
        reason='；作用于'+ '、'.join(describe(t) for t in targets) if targets else ''
        return _fmt(r['ss'],r)+'｜%s·力量%.2f%s' % (position,r['effective'],reason)
    yong=[format_rec(r) for r in resolved["selected"]]
    potential=[format_rec(r)+"｜潜在救应、待透" for r in resolved["candidates"] if not r["tou"] and not r.get("root_owner_id")]
    pending=[item for item in yao_all if "待运" in item or "仅救一半" in item]
    treatment_status=resolved["statuses"]
    for status,disease in zip(treatment_status,main):
        if status["status"]==State.NO_DRUG:
            if any(r['tou'] and r['ss'] in expands(names) for _,names,_ in treatment_rules.get(disease['name'],[]) for r in resolved['candidates']):
                status['status']=State.CORRESPONDING
                status['reason']='原局有效药候选已透出，未选用或作用、药力检查未通过'
            elif any(r["ss"] in expands(names) for _,names,_ in treatment_rules.get(disease["name"],[]) for r in resolved["candidates"] if not r["tou"] and not r.get("root_owner_id")):
                status["status"]=State.POTENTIAL
            elif disease.get("yao"): status["status"]=State.PENDING
        disease["treatment_status"]=status["status"]
        disease["rescue_evidence"]=status["evidence"]
    unresolved=[x["name"] for x in treatment_status if x["status"] not in (State.RESCUED,State.BALANCED)]
    yao_in_chart=bool(main) and not unresolved
    validation=["全盘按柱位枚举兼容组合；治疗作用和药力统一分配"]
    if unresolved: validation.append("尚未完全解决：%s" % "、".join(unresolved))
    # 辅佐只保留有效原局透干，不把待透、待运混入原局首选。
    xi=[format_rec(r) for r in resolved["auxiliary"]]
    external_presence = []
    conditional_ji = []
    third_element_roles = []
    special_yong_wuxing = []
    special_xi_wuxing = []
    special_ji_wuxing = []
    if ctx.get("special_ge"):
        special = ctx["special_ge"]
        day_wx = M.WUXING_GAN[ctx["day_gan"]]
        if "化" in special:
            target = special[1]
            fav = [target, M.SHENG[target]]
        elif "专旺" in special:
            fav = [day_wx, M.SHENG[day_wx], next(w for w in M.WUXING_LIST if M.SHENG[w] == day_wx)]
        elif "从强" in special:
            fav = [day_wx, next(w for w in M.WUXING_LIST if M.SHENG[w] == day_wx)]
        elif "从财" in special:
            fav = [M.KE[day_wx], M.SHENG[day_wx]]
        elif "从杀" in special:
            fav = [M.KE_OF[day_wx], M.KE[day_wx]]
        elif "从儿" in special:
            fav = [M.SHENG[day_wx], M.KE[day_wx]]
        elif "两气成象" in special:
            pair = [w for w in M.WUXING_LIST if w in special]
            downstream = next((w for w in pair if any(M.SHENG[a] == w for a in pair)), None)
            fav = ([downstream] + [w for w in pair if w != downstream]) if downstream else pair
        else:
            fav = list(dict.fromkeys(M.WUXING_GAN[r["gan"]]
                       for rs in ctx["occ"].values() for r in rs if r["tou"]))
            fav = [w for w in fav if w != day_wx]
        yong = [w + "（外格顺势用神）" for w in fav[:1]]
        xi = [w + "（外格顺势喜神）" for w in fav[1:]]
        ji = [w + "（逆势忌神）" for w in M.WUXING_GAN.values()
              if w not in fav and M.KE.get(w) == fav[0]] if fav else []
        # 逐外格定义破势之神，避免一律套克用者为忌。
        core = []
        conditional = []
        if "从财" in special:
            core = [day_wx, next(w for w in M.WUXING_LIST if M.SHENG[w]==day_wx)]
            conditional = [(M.KE_OF[day_wx], "官杀过强泄财时为忌")]
        elif "从杀" in special:
            core = [M.SHENG[day_wx], next(w for w in M.WUXING_LIST if M.SHENG[w]==day_wx)]
            conditional = [(day_wx, "印比有根成势、扶身抗杀时为忌")]
        elif "从儿" in special:
            core = [next(w for w in M.WUXING_LIST if M.SHENG[w]==day_wx)]
            conditional = [(M.KE_OF[day_wx], "与食伤交战且无财通关时为忌")]
        elif "从弱" in special:
            core = [day_wx, next(w for w in M.WUXING_LIST if M.SHENG[w] == day_wx)]
        elif "从强" in special:
            core = [M.SHENG[day_wx], M.KE[day_wx], M.KE_OF[day_wx]]
        if core:
            ji = [w+"（破势忌神）" for w in core]
        for w,condition in conditional:
            conditional_ji.append(dict(wuxing=w,kind="条件忌",condition=condition))
        ji = list(dict.fromkeys(ji))
        if "专旺" in special:
            conditional_ji.append({"wuxing": M.KE[day_wx], "role": "财星",
                "condition": "耗损旺气或生助官杀时为忌", "kind": "条件忌"})
        if "两气成象" in special and len(pair) == 2 and downstream:
            # 保留两行原有喜用；第三行按作用分类，不因出现就判破格。
            for w in M.WUXING_LIST:
                if w in pair:
                    continue
                drain = M.SHENG[downstream] == w
                bridge = any(M.KE[a] == w and M.SHENG[a] == b and M.SHENG[b] == w
                             for a in pair for b in pair if a != b)
                if drain or bridge:
                    third_element_roles.append({"wuxing": w,
                        "role": "泄秀" if drain else "通关",
                        "roles": (["泄秀", "主体下游通关"] if drain and bridge else ["泄秀" if drain else "通关"]),
                        "bridge_structure": "主体上游→主体下游→第三行，主体下游通关" if bridge else "",
                        "condition": "适量顺势可用；过量耗损两行或使气势转向时为条件忌"})
                    conditional_ji.append({"wuxing": w, "kind": "条件忌",
                        "condition": "过量耗损两行或使气势转向时为忌"})
                    ji = [item for item in ji if not item.startswith(w)]
                elif M.KE[w] == downstream:
                    # 核心忌仍保留：第三行许可不代表无条件放行。
                    continue
                else:
                    conditional_ji.append({"wuxing": w, "kind": "条件忌",
                        "condition": "实际克耗两行、截断相生或使气势转向时为忌"})
            note_parts.append("两气成象允许第三行泄秀；相生链中由主体下游通关，尚不包含相克主体借第三行通关的入格类型")
        special_yong_wuxing = list(dict.fromkeys(fav[:1]))
        special_xi_wuxing = list(dict.fromkeys(fav[1:]))
        special_ji_wuxing = list(dict.fromkeys(item[0] for item in ji if item))
        visible_wx={M.WUXING_GAN[r["gan"]] for rs in ctx["occ"].values() for r in rs if r["tou"]}
        external_presence = [{"wuxing": item[0], "present": item[0] in visible_wx,
                              "status": "原局天干已见，需核查作用" if item[0] in visible_wx else "原局天干未见，规则提示"}
                             for item in ji]
        principle = "外格按气势取用：化气顺化神，专旺顺旺神，从财从杀从儿顺所从之神"
    # 条件忌明确区分规则、天干存在与可量化触发，未定义者不强行判定。
    from .geju_treatment import records as treatment_records
    powers={w:0.0 for w in M.WUXING_LIST}
    for rec in treatment_records(original_ctx["occ"],original_ctx["he"]):
        powers[M.WUXING_GAN[rec["gan"]]]+=rec.get("atom_effective",rec["effective"])
    if original_ctx.get("zhis"):
        powers=qi_table(original_ctx["gans"],original_ctx["zhis"],original_ctx["he"],original_ctx.get("eff_hide"))
    for item in conditional_ji:
        w=item["wuxing"]
        item["present"]=any(r["tou"] and M.WUXING_GAN[r["gan"]]==w and record_power(r,original_ctx["he"])>0 for rs in original_ctx["occ"].values() for r in rs)
        item["triggered"]=None if item["present"] else False
        item["status"]="原局未见有效透干" if not item["present"] else "原局已见，条件待核查"
        if ctx.get("special_ge") and "两气成象" in ctx["special_ge"] and w not in pair:
            threshold=min(powers[x] for x in pair)
            item["threshold"]=threshold
            item["triggered"]=powers[w]>threshold and powers[w]>0
            item["status"]="已触发：第三行强过较弱主体" if item["triggered"] else "未触发过量门槛"
    conditional_yong=[]
    unresolved_targets={ss for b,status in zip(main,treatment_status) if status['status'] not in (State.RESCUED,State.BALANCED) for ss in b['bing_ss']}
    for rec in resolved['selected']:
        if rec['ss'] in unresolved_targets:
            text=format_rec(rec)
            conditional_yong.append(dict(id=rec['id'],shen=text,
                reason='可改善部分病，但自身仍是其他未解决病的病神，不作无条件首选'))
            yong=[x for x in yong if x!=text]
    conditional_ids={x['id'] for x in conditional_yong}
    ji=[x for x in ji if _key(x) not in {_key(c['shen']) for c in conditional_yong}]
    # 条件取用保留在独立字段，病清单和治疗分配继续完整展示其副作用。
    has_unresolved = bool(unresolved)
    used_original_drug = bool(resolved['allocations'])
    self_balanced = bool(treatment_status) and all(x['status']==State.BALANCED for x in treatment_status)
    primary_visible_yong_shen = list(yong)
    latent_hidden_yong_shen = list(potential)
    if primary_visible_yong_shen and latent_hidden_yong_shen:
        yong_visibility = "visible_primary_with_latent_hidden"
    elif primary_visible_yong_shen:
        yong_visibility = "visible_primary"
    elif latent_hidden_yong_shen:
        yong_visibility = "latent_hidden_only"
    else:
        yong_visibility = "none"
    yong_selection_note = (
        "yong_shen_list 只收原局透干且实际入选的用神；藏干候选仅列入 "
        "latent_hidden_yong_shen，不冒充首选透干用神。"
    )
    if yong_visibility == "latent_hidden_only":
        yong_selection_note += " 本盘原局无透干首选，藏干候选待透或待运方用。"
    trace = [trace[0]] + det_log
    trace.append('Step8：最终模式=%s；原局首选=%s；辅佐=%s' % (mode,'、'.join(yong) or '无','、'.join(xi) or '无'))
    trace.extend('Step8：最终病状态 %s=%s' % (x['name'],x['status']) for x in treatment_status)
    trace.append('Step8：最终汇总 未解决=%s；实际使用原局药=%s；全部原局自有平衡=%s' % (has_unresolved,used_original_drug,self_balanced))
    trace.extend(validation + route_resolution)

    # 结构取用与治病药分开：有药未治愈不等于结构没有用神。
    structure_primary=[]
    structure_secondary=[]
    if ctx.get('ge_category')=='禄刃':
        structure_primary=[dict(gan=t[0],shishen=_parse_ss(t),role='结构主用',source='Step3禄刃取相')
                           for t in ctx.get('xiang_shen_list',[]) if t and t[0] in M.GAN_LIST]
        if any(r['shishen']=='食神' for r in structure_primary):
            structure_secondary=[dict(gan=r['gan'],shishen=r['ss'],role='结构第二用',source='食神生财',
                                      visibility='透' if r['tou'] else '藏')
                                 for r in treatment_records(original_ctx['occ'],original_ctx['he']) if r['ss'] in ('正财','偏财') and r['effective']>0]
    return {
        "structure_primary": structure_primary,
        "structure_secondary": structure_secondary,
        "conditional_yong_shen": conditional_yong,
        "unconditional_selected_records": [r for r in resolved["selected"] if r["id"] not in conditional_ids],
        "has_unresolved_bing": has_unresolved,
        "used_original_drug": used_original_drug,
        "self_balanced": self_balanced,
        "drug_budget_detail": resolved['drug_budget'],
        "flow_budget_detail": resolved['flow_budget'],
        "evidence_registry": {e['evidence_id']:e for e in resolved['allocations']},
        "potential_yong_shen": potential,
        "primary_visible_yong_shen": primary_visible_yong_shen,
        "latent_hidden_yong_shen": latent_hidden_yong_shen,
        "yong_visibility": yong_visibility,
        "yong_selection_note": yong_selection_note,
        "pending_yong_shen": pending,
        "selected_records": resolved["selected"],
        "alternative_yong_shen": [format_rec(r) for r in resolved["alternatives"]],
        "treatment_allocations": resolved["allocations"],
        "remaining_drug_capacity": resolved["remaining_capacity"],
        "treatment_status": treatment_status,
        "candidate_pool": yao_all if main else _pick_yong(ctx)[0],
        "external_ji_presence": external_presence,
        "unresolved_bing": unresolved,
        "conditional_ji_shen": conditional_ji,
        "third_element_roles": third_element_roles,
        "special_yong_wuxing": special_yong_wuxing,
        "special_xi_wuxing": special_xi_wuxing,
        "special_ji_wuxing": special_ji_wuxing,
        "route_resolution": route_resolution,
        "combination_validation": validation,
        "supporting_roots": [r for r in treatment_records(original_ctx["occ"],original_ctx["he"]) if not r["tou"] and r.get("root_owner_id")],
        "root_ownership": [{"id":r["id"],"root_ids":r["root_ids"],"effective":r["effective"]} for r in treatment_records(original_ctx["occ"],original_ctx["he"]) if r["tou"]],
        "power_detail": [{"ss":ss,"gan":r["gan"],"idx":r["idx"],"tou":r["tou"],
                          "base":r.get("base_weight",1 if r["tou"] else .5),
                          "after_chong":r.get("weight",1),"effective":record_power(r,original_ctx["he"])}
                         for ss,rs in original_ctx["occ"].items() for r in rs],
        "strength_counts": {ss: sum(r.get("weight", 1.0 if r["tou"] else .5) for r in rs) for ss, rs in ctx["occ"].items()},
        "source": "李厚君师傅《八字格局核心笔记整理》",
        "has_bing": bool(main),
        "mode": mode,
        "bing_list": main,
        "bing_light": [{"name": b["name"], "bing_shen": b["bing_shen"],
                        "note": b["note"]} for b in light],
        "yong_shen_list": yong,
        "xi_shen_list": xi,
        "ji_shen_list": ji,
        "yao_shen_list": yao_all,
        "yao_in_chart": yao_in_chart if main else None,
        "principle": principle,
        "note": "；".join(note_parts),
        "fuyi_hint": fuyi_hint,
        "tiaohou_pending": True,   # 本层 Step8 未合并调候之病；调候模块本身已上线（engine.tiaohou）
        "trace": trace,
    }


def build_relation_diseases(ctx, blockers=(), only_blockers=False):
    """定格和喜用共同从实际格局、路线及透干关系生成病与治法。"""
    detect_ctx=ctx if ctx.get('_effective_occ') else dict(ctx,occ=effective_occ(ctx['occ'],ctx['he']))
    main,light,log=_detect_bing(detect_ctx)
    rules=dict(BING_YAO)
    main=[b for b in main if b['name'] in rules or not b['name'].startswith('忌神破格')]
    covered={ss for b in main for ss in b['bing_ss']}
    for blocker in blockers:
        if not any(r['tou'] and record_power(r,ctx['he'])>0 for r in ctx['occ'].get(blocker,[])): continue
        if blocker in covered: continue
        name='路线受损：%s·%s·%s' % (ctx.get('ge_ss') or ctx.get('ge_name') or '禄刃',ctx.get('route_label') or '取相',blocker)
        medicines=[ss for ss in ALL_SS if ke(ss,blocker)]
        rules[name]=[('克掉',medicines,'制去实际破坏所选路线的字')]
        main.append(dict(name=name,bing_ss=[blocker],bing_shen=[_fmt(blocker,(_tou(ctx,blocker) or [None])[0])],
                         severity='坏格',note='具体路线破坏关系，不能只按忌神名称套病名'))
    for disease in main:
        disease['affects_ge']=disease['name']=='阳刃无制' or bool(set(disease['bing_ss']) & set(blockers))
        disease['scope']='本格成破病' if disease['affects_ge'] else '全局附加病'
    if only_blockers: main=[b for b in main if set(b['bing_ss']) & set(blockers)]
    return main,light,log,rules
