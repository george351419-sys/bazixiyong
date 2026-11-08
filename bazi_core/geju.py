# -*- coding: utf-8 -*-
"""子平格局派 · 格局判定模块（PRD V1.0，纯月令取格正统子平格局法）。

设计原则：
  - 定格顺序严格写死、不可并行、不可调换：合化 > 外格 > 月令取格 > 禄刃 > 顺逆 > 清浊 > 成破。
    外格（从/专旺/化气/两气成象）优先于八格：命中即归外格并跳过八格 Step2-7
    （yan 2026-11-06：原仅在主格真破格时兜底，现前置为独立第一道关卡）。
  - 月令取格（yan 2026-11-06 古籍调研后拍板，替代 PRD V1.0 的司令口径）：
      ① 月令藏干唯一透出 → 取该透出为格神；
      ② 多透 → 按藏干序位「本气 > 中气 > 余气」取最前者；
      ③ 都不透 → 取本气为格，标为「暗格」；
      ④ 比劫不作八格格神；最终候选为比劫或月临禄刃帝旺时走禄刃分支。
    **人元司令（节气后天数决定的当令之干）不参与取格**，仅作参考字段输出。
  - 优先月令提纲；格神必须溯源到月令之气；禄刃单独分类，不属于八格。
  - 旺衰仅作附加辅助输出，不参与主格局判定（PRD §六.8）。
  - 前置合化以「旺衰模块已校验过的 heju 结果」为唯一口径：从 ws["he_detail"]
    直接复用，不重算；外格（从/化/专旺/两行）筛查复用 wangshuai 真从标签。
    唯一例外：月令「六合不改提纲」是格局派硬规则，详见 DATA_NOTES #3。

本模块只做「格局判定 + 格局维度喜用」，不混入扶抑旺衰派、盲派；不排大运流年；
不做神煞/纳音定格。Step8 喜用层（geju_xiyong.py）依据李厚君师傅
《八字格局核心笔记整理》：「有病治病为先，无病吉神顺用 / 凶神逆用」，是定格之后
的独立附加层，不参与、不推翻 Step1-7，也不与旺衰加权（详见 DATA_NOTES #17-21）。

说明（PRD 内部冲突已在此收敛，详见文件末尾 DATA_NOTES）：
  - 人元司令表 PRD §2.2 对卯/酉列了双段（甲/庚），但新口径下司令不参与取格，
    该冲突已无实义；siling_gan 仅保留作参考字段（卯→乙、酉→辛）。
  - 禄刃触发及细分以Step3的实际判据为准；人元司令不参与取格。
"""
from __future__ import annotations
from .numeric import finite as safe_finite
from .geju_status import State

from . import metadata as M
from .geju_rules import qi_table, verify_rescue, resolve_wuhe, power, record_power, rescue_fraction, clean_level as shared_clean
from .heju import evaluate as heju_evaluate
from .wangshuai import compute_wangshuai
from .geju_xiyong import compute_xiyong_geju, BING_YAO, build_relation_diseases
from .geju_treatment import solve, expands, records


# ============================ 人元司令表（PRD §2.2） ============================
# 每段：(起始天数(含), 司令干)。区间语义 [start, next_start)，末段开放。
# 纯气月令（子/卯/酉）司令恒为本气，忽略表中分段（PRD §2.2 备注 + Step2 分支B.3 双重规定）。
RENYUAN_SILING = {
    "寅": [(0, "戊"), (7, "丙"), (14, "甲")],
    "卯": [(0, "乙")],          # 纯气 override（PRD 表列甲乙，以纯气取本气为准）
    "辰": [(0, "乙"), (9, "癸"), (12, "戊")],
    "巳": [(0, "戊"), (5, "庚"), (14, "丙")],
    "午": [(0, "丙"), (10, "己"), (19, "丁")],
    "未": [(0, "丁"), (9, "乙"), (12, "己")],
    "申": [(0, "戊"), (7, "壬"), (14, "庚")],
    "酉": [(0, "辛")],          # 纯气 override（PRD 表列庚辛，以纯气取本气为准）
    "戌": [(0, "辛"), (9, "丁"), (12, "戊")],
    "亥": [(0, "戊"), (7, "甲"), (14, "壬")],
    "子": [(0, "癸")],
    "丑": [(0, "癸"), (9, "辛"), (12, "己")],
}
PURE_QI = {"子", "卯", "酉"}     # 纯气月令


def siling_gan(month_zhi, solar_term_day):
    """返回月令司令干。

    参数:
        month_zhi       : 月令地支
        solar_term_day  : 节气后第几天（None 时四长生/四库退化为本气或首段）
    """
    segs = RENYUAN_SILING.get(month_zhi)
    if not segs:
        raise ValueError("人元司令表无此月令地支：%r" % month_zhi)
    if month_zhi in PURE_QI:
        return segs[0][1]                      # 纯气恒本气
    d = int(solar_term_day) if solar_term_day is not None else None
    if d is None:
        # 无节气天数兜底：四长生退回本气；四库退回首段（严禁默认取土，PRD §六.4）
        if month_zhi in ("辰", "戌", "丑", "未"):
            return segs[0][1]
        return segs[-1][1]
    chosen = segs[-1][1]
    for i, (start, gan) in enumerate(segs):
        nxt = segs[i + 1][0] if i + 1 < len(segs) else None
        if nxt is None:
            chosen = gan
        elif start <= d < nxt:
            chosen = gan
            break
    return chosen


# ============================ 十神分类 / 善恶 / 路线 ============================
SHISHEN_GROUP = {
    "正官": "官", "七杀": "官",
    "正财": "财", "偏财": "财",
    "正印": "印", "偏印": "印",
    "食神": "食伤", "伤官": "食伤",
    "比肩": "比劫", "劫财": "比劫",
}
SHISHEN_GOOD = {  # 善恶：善=顺用，凶=逆用
    "正官": True, "正财": True, "正印": True, "食神": True,
    "七杀": False, "伤官": False, "偏印": False,
}
GE_TENSHEN = {"正官", "七杀", "正财", "偏财", "正印", "偏印", "食神", "伤官"}  # 八格十神


# 八格路线表（PRD §四 Step4）。xiang/ji 均为「十神组名」（官/财/印/食伤/比劫）。
# 七杀/伤官为双路线，互斥；偏印为凶逆用（财制枭）。
GE_ROUTE = {
    # 正官忌「伤官克官、七杀混官」；食神不克官、官组含格神自身，均不可列为忌。
    "正官": {"good": True, "xiang": ["财", "印"], "ji": ["伤官", "七杀"]},
    # 财格「官护财」指正官，七杀不护财 → 用具体十神名而非官组。
    # 财格忌神仅「比劫」（比劫夺财）。偏印不在此列：财克印（五行上财为克方、
    # 印为被克方），不存在「偏印夺财」；偏印夺食之说仅关乎食神格，与财格无涉。
    "正财": {"good": True, "xiang": ["食伤", "正官"], "ji": ["比劫"]},
    "偏财": {"good": True, "xiang": ["食伤", "正官"], "ji": ["比劫"]},
    "正印": {"good": True, "xiang": ["官", "比劫"], "ji": ["财"]},
    "食神": {"good": True, "xiang": ["财"], "ji": ["偏印"]},   # 仅偏印(枭)夺食为忌；正印不夺食
    "七杀": {"good": False, "routes": {
        "食神制杀": {"xiang": ["食神"], "ji": ["偏印", "正财", "偏财"]},  # 制杀忌枭夺食、忌财党杀
        "杀印相生":   {"xiang": ["正印", "偏印"], "ji": ["正财", "偏财"]},   # 化杀忌财破印
    }},
    "伤官": {"good": False, "routes": {
        "伤官配印": {"xiang": ["正印", "偏印"], "ji": ["正财", "偏财"]},  # 配印忌财破印
        "伤官生财": {"xiang": ["正财", "偏财"], "ji": ["正官"]},          # 生财忌官来见伤
    }},
    # 偏印（枭）凶神逆用：财制枭为相；见食神则「枭旺夺食」为忌（PRD §四 Step4 表）。
    # 早期版本 ji=[] 导致偏印格永不可能破格，属漏实现。
    "偏印": {"good": False, "xiang": ["正财", "偏财"], "ji": ["食神"]},
}

# 救应表（PRD §四 Step6）：键 (格神十神, 忌神十神) -> 救神「组名」
SAVIOUR = {
    ("正官", "伤官"): "印",       # 官格遇伤破，印制伤
    # 官杀混杂不走「救神」：多余七杀只能被五合合去（Step5 合去留清），
    # 不能靠「官自己有根」假救应 —— 旧版 ("正官","七杀"):"官" 已移除。
    ("正财", "比劫"): "食伤",     # 财格比劫夺财，食化劫生财
    ("偏财", "比劫"): "食伤",     # 偏财同论（PRD 财格未分正偏）
    ("正印", "正财"): "比劫",     # 印格财破印，比劫合财护印
    ("正印", "偏财"): "比劫",
    ("七杀", "偏印"): "财",       # 制杀格枭夺食破，财破枭
    ("食神", "偏印"): "比劫",     # 食神格枭夺食，比劫护食（近似）
    ("偏印", "食神"): "财",       # 枭夺食，有财制枭则食神得救（品级下降）
}

# 十干临官(禄) / 帝旺(刃)。按「十干」而非「五行」判定：
# metadata.LU/REN 是五行级映射（金禄在申、水禄在亥），会漏掉阴干禄（辛禄在酉、癸禄在子）。
TEN_GAN_LU = {
    "甲": "寅", "乙": "卯", "丙": "巳", "丁": "午", "戊": "巳", "己": "午",
    "庚": "申", "辛": "酉", "壬": "亥", "癸": "子",
}
YANG_REN = {"甲": "卯", "丙": "午", "戊": "午", "庚": "酉", "壬": "子"}   # 阳干帝旺 → 阳刃
YIN_DIWANG = {"乙": "寅", "丁": "巳", "己": "巳", "辛": "申", "癸": "亥"}  # 阴干帝旺 → 月劫（阴干无阳刃）

# 兼容旧引用保留：主流程已改用上面的十干表，勿再用五行级 LU/REN 判禄刃。
LU = M.LU
REN = M.REN


# ============================ 基础工具 ============================
def _parse_chart(chart):
    if "gans" in chart and "zhis" in chart:
        gans = list(chart["gans"])
        zhis = list(chart["zhis"])
    else:
        gans = [chart["year"]["gan"], chart["month"]["gan"],
                chart["day"]["gan"], chart["hour"]["gan"]]
        zhis = [chart["year"]["zhi"], chart["month"]["zhi"],
                chart["day"]["zhi"], chart["hour"]["zhi"]]
    # 早期版本直接把非法干支透传到 metadata 查表，报 KeyError 难以定位；此处前置校验。
    if len(gans) != 4 or len(zhis) != 4:
        raise ValueError("四柱需 4 个天干 + 4 个地支，实际 %d/%d" % (len(gans), len(zhis)))
    for g in gans:
        if g not in M.WUXING_GAN:
            raise ValueError("非法天干：%r" % g)
    for z in zhis:
        if z not in M.ZHI_HIDE:
            raise ValueError("非法地支：%r" % z)
    return gans, zhis


def _has_root(gan, eff_hide):
    """PRD §2.5 根气判定：天干在地支藏干中出现（本气/中气/余气）即算有根。"""
    for hides in eff_hide:
        if gan in hides:
            return True
    return False


class VirtualHide(list):
    """合化五行均分阴阳，不按天干排列冒充本中气。"""


def _virtual_hide(wx):
    """合化成功后的「虚拟藏干」：该五行对应的两个天干（按天干序）。"""
    return VirtualHide(g for g in M.GAN_LIST if M.WUXING_GAN[g] == wx)


def _build_eff_hide(zhis, he, month_hua=None, keep_month_original=False):
    """构建四柱有效藏干表 —— 置换口径与旺衰模块 heju 的 branch_hua 完全一致。

    PRD 格局 §2.4 / 用户拍板「前置合化以旺衰模块为准」：
      - 凡 heju 判定 branch_hua[i] 非空的支（三会/三合/六合成功），整支五行置换，
        与旺衰模块 F/K 统计「整支按化神五行计入、原藏干作废」保持同一口径；
      - 唯一例外：月令提纲。PRD §2.4 明确规定「六合、半合、遥合不改变月令提纲」，
        故 keep_month_original=True 时，月令只有在三合/三会成功（month_hua 非空）
        才置换；六合成功仅影响月令以外的支，不改提纲。
      - 合而不化（branch_hua[i] 为 None）的支保留原藏干。
    """
    eff = []
    for i, z in enumerate(zhis):
        hua = he["branch_hua"][i]
        if i == 1 and keep_month_original and not month_hua:
            eff.append(list(M.ZHI_HIDE[z]))       # 六合/五合不动提纲（PRD 硬规则）
        elif hua:
            eff.append(_virtual_hide(hua))
        else:
            eff.append(list(M.ZHI_HIDE[z]))
    return eff


def _scan_tenshen(day_gan, gans, eff_hide, zhis=None):
    """扫描全盘十神出现情况。

    返回 dict: 十神名 -> list of {"tou":bool,"root":bool,"idx":int,"gan":str}
      - 天干（年/月/时，排除日主自身）作透干；藏干（含月令有效藏干）作有根。
      - gan 必须记录「实际产生该十神的字」，不能靠 idx 反查藏干首字（会张冠李戴）。
    """
    occ = {}
    for i, g in enumerate(gans):
        if i == 2:
            continue
        ss = M.shishen(day_gan, g)
        rec = {"tou": True, "root": _has_root(g, eff_hide), "idx": i, "gan": g}
        occ.setdefault(ss, []).append(rec)
    for i, hides in enumerate(eff_hide):
        for c in hides:
            ss = M.shishen(day_gan, c)
            rec = {"tou": False, "root": True, "idx": i, "gan": c, "weight": (1.0 / len(hides)) if isinstance(hides, VirtualHide) else (1.0 if c == hides[0] else 0.5)}   # 藏干即根
            occ.setdefault(ss, []).append(rec)
    gan_chong = {"甲": "庚", "庚": "甲", "乙": "辛", "辛": "乙",
                 "丙": "壬", "壬": "丙", "丁": "癸", "癸": "丁"}
    for records in occ.values():
        for r in records:
            base = 1.0 if r["tou"] else r["weight"]
            if r["tou"]:
                hit = gan_chong.get(r["gan"]) in gans
            else:
                hit = bool(zhis and M.CHONG.get(zhis[r["idx"]]) in zhis)
            r.update(base_weight=base, chong=hit, weight=base * (.5 if hit else 1.0))
    return occ


def _group_of(ss):
    return SHISHEN_GROUP.get(ss, "?")


def _tenshen_hunzhuo(ss_iter):
    """判断一组十神是否构成「浊」（不清）。

    真正成浊：
      ① 异类十神并见（如财+官、印+食伤——不同十神组竞争取格）；
      ② 同类混杂：官杀混杂（正官+七杀）、食伤混杂（食神+伤官）、
         正偏印并见（正印+偏印）。
    不算浊：
      财星正偏同透 —— 子平「财不忌偏正」，同类并见主富，不视为浑浊。
    """
    ss_set = set(ss_iter)
    if len(ss_set) < 2:
        return False
    groups = {_group_of(s) for s in ss_set}
    if len(groups) >= 2:
        return True                      # 异类（不同十神组）并见 → 浊
    grp = next(iter(groups))
    if grp == "印" and ("正印" in ss_set and "偏印" in ss_set):
        return True
    if grp == "官" and ("正官" in ss_set and "七杀" in ss_set):
        return True                      # 官杀混杂 → 浊
    if grp == "食伤" and ("食神" in ss_set and "伤官" in ss_set):
        return True                      # 食伤混杂 → 浊
    return False                         # 财财同类并见 → 不算浊


def _is_strong(occ, ss_list):
    """ss_list 中任一十神在局内有力（透干有根 或 藏干）。"""
    for ss in ss_list:
        for rec in occ.get(ss, []):
            if rec["root"]:
                return True
    return False


def _present(occ, ss_list):
    return [ss for ss in ss_list if ss in occ]


def _cong_context(ws, ge_name, ge_category):
    """把旺衰从格标签与格局取格结果的关系显式说清。

    旺衰的「假从」只是气势层判断，不触发外格；格局仍按八格/禄刃取格。
    真从才可被外格筛查消费，因此这里同时给出 is_cong / is_fake_cong。
    """
    info = ws.get("cong_info", {}) if isinstance(ws, dict) else {}
    is_cong = bool(info.get("is_cong"))
    is_fake_cong = bool(info.get("is_fake_cong"))
    tag = ws.get("tag") if isinstance(ws, dict) else None
    if is_fake_cong:
        note = ("旺衰层为%s：这是日主气势的假从判断，不触发外格；"
                "格局层仍按月令八格/禄刃取格，当前取【%s】。" % (tag or "假从", ge_name))
    elif is_cong:
        note = ("旺衰层为%s真从，外格筛查可据此认定从格/专旺；当前格局取【%s】。"
                % (tag or "真从", ge_name))
    elif ge_category == "外格":
        note = ("旺衰层未成立真从/假从；本盘外格由化气/两气成象等独立条件认定，"
                "当前取【%s】。" % ge_name)
    else:
        note = "旺衰层未成立真从/假从；格局按常格流程取【%s】。" % ge_name
    return {
        "source": "wangshuai.cong_info",
        "wangshuai_tag": tag,
        "is_cong": is_cong,
        "is_fake_cong": is_fake_cong,
        "applies_to_geju": bool(is_cong and ge_category == "外格"),
        "ge_category": ge_category,
        "ge_name": ge_name,
        "note": note,
    }


# ============================ 主入口 ============================
def compute_geju(chart, config=None, ws=None):
    """子平格局判定主入口（PRD V1.0）。

    参数:
        chart : 同旺衰模块输入（year/month/day/hour 各 {gan,zhi}；或扁平 gans/zhis）。
                额外可选字段 solar_term_day（节气后第几天，用于司令取格）。
        config: 超参（复用 metadata.default_config；新增 enable_special_ge 开关）。
        ws    : 可选，已算好的旺衰结果（compute_wangshuai 返回值），避免重复计算。
    返回: 标准化格局 JSON（含 trace_log）。
    """
    if config is not None and not isinstance(config,dict): raise ValueError('格局config必须为字典')
    if config is None:
        config = M.default_config()
    else:
        base = M.default_config()
        base.update(config)
        config = base

    from .input_contracts import boolean
    from math import isfinite
    boolean(config.get('enable_special_ge',True),'enable_special_ge')
    ratio=config.get('blade_control_ratio',1.0)
    if type(ratio) not in (int,float) or not safe_finite(ratio) or ratio<=0:
        raise ValueError('blade_control_ratio必须为正有限数值')

    gans, zhis = _parse_chart(chart)
    day_gan = gans[2]
    day_wx = M.WUXING_GAN[day_gan]
    month_zhi = zhis[1]
    solar_term_day = chart.get("solar_term_day")
    trace = []
    if solar_term_day is None:
        trace.append("Step0：未提供节气后天数（新口径下人元司令不参与取格，"
                     "仅影响 siling_gan 参考字段）")

    # ---------- 旺衰（附加输出）+ 合化结果复用 ----------
    # 用户拍板：前置判断与外格筛查以「旺衰模块已校验过的合化」为准。故先取得旺衰结果，
    # 直接复用其中的 he_detail（heju.evaluate 的完整返回），不再自行重算一次合化。
    # engine.analyze 会把已算好的 ws 传进来，整条链路全局只调一次 heju.evaluate。
    if ws is None:
        ws = compute_wangshuai(chart, config=config)
    from .ws_identity import verify
    verify(ws, chart, config)
    he = ws.get("he_detail")
    if he is None:
        # 兼容外部传入的精简/旧格式 ws（如单测 mock）：退回直算并在链路日志标注来源
        he = heju_evaluate(gans, zhis, config)
        he_source = "heju 直算（ws 未携带 he_detail，兼容兜底）"
    else:
        he_source = "复用旺衰模块 heju 判定（不重算）"

    # 格局层独立记录远隔五合，不改变旺衰的合化结果。
    he = dict(he, he_groups=[dict(g) for g in he["he_groups"]])
    for i in range(4):
        for j in range(i + 1, 4):
            if frozenset((gans[i], gans[j])) in M.WUHE and not any(
                g["type"] == "wuhe" and g.get("idx") == [i, j] for g in he["he_groups"]):
                he["he_groups"].append(dict(type="wuhe", members=[gans[i], gans[j]],
                    idx=[i,j], hua_success=False, hua_wuxing=None, ban=True,
                    geju_only=True, rescue_fraction=1.0 if j-i == 1 else .5))

    strict_he = he
    he = resolve_wuhe(he, gans, _scan_tenshen(day_gan,gans,[M.ZHI_HIDE[z] for z in zhis],zhis))
    trace.append("争合裁决：一字一合，舍弃%s组" % len(he["wuhe_rejected"]))

    # ---------- Step1：合化前置校验（复用 heju 严格合化口径） ----------
    # 仅「三合/三会成功」且月令属于该组成员，才替换提纲（PRD §2.4：六合、半合、遥合不改提纲）
    hg = next((g for g in he["he_groups"]
               if g["hua_success"] and g["type"] in ("sanhe", "sanhuí")
               and month_zhi in g["members"]), None)
    month_hua = hg["hua_wuxing"] if hg else None
    if month_hua:
        eff_month_wx = month_hua
        virtual_hide = _virtual_hide(eff_month_wx)
        trace.append("Step1：前置合化来源=%s；月令%s为%s成员，%s合化成功（化神%s）→ "
                     "提纲五行换为%s，虚拟藏干=%s"
                     % (he_source, month_zhi, "/".join(hg["members"]), hg["type"],
                        eff_month_wx, eff_month_wx, "、".join(virtual_hide)))
    else:
        eff_month_wx = M.WUXING_ZHI[month_zhi]
        virtual_hide = None
        trace.append("Step1：前置合化来源=%s；月令%s无成功三合/三会合化"
                     "（六合/半合/遥合不改提纲），提纲五行=%s"
                     % (he_source, month_zhi, eff_month_wx))

    # 有效藏干：按 heju.branch_hua 全支置换（与旺衰同口径）；月令保留 PRD「六合不改提纲」例外
    eff_hide = _build_eff_hide(zhis, he, month_hua=month_hua, keep_month_original=True)
    if any(he["branch_hua"][i] for i in (0, 2, 3)):
        trace.append("Step1：非月令地支合化置换已按旺衰口径同步（branch_hua=%s）"
                     % he["branch_hua"])
    occ = _scan_tenshen(day_gan,gans,eff_hide,zhis)
    month_hide = eff_hide[1]
    month_benqi = month_hide[0]               # 月令本气（虚拟藏干首干）

    # 新口径：人元司令（节气后天数）全程不参与取格，siling_gan 仅作参考字段输出。
    # PRD V1.0 的「合化后停司令表」因此不再需要单列分支。
    siling = siling_gan(month_zhi, solar_term_day)
    trace.append("Step1：人元司令干=%s（仅供参考，不参与取格）" % siling)
    if month_hua:
        trace.append("Step2：提纲已合化改写，取格改以化神虚拟藏干为准")

    # ---------- Step1.5：外格前置筛查（yan 2026-11-06：外格优先于八格） ----------
    # 流程顺序：旺衰 → 合化 → 【外格】 → 八格。若命中从格 / 专旺 / 化气 / 两气成象，
    # 则直接归外格、跳过八格 Step2-7（仍走 Step8 喜用，mode=外格另论）；否则继续走
    # 传统八格取格。外格门槛复用旺衰模块真从标签 + 日主孤立判据（与旧 Step7 兜底同套）。
    wangshuai_tag = ws["tag"]
    wangshuai_conf = ws["confidence"]
    enable_special = config.get("enable_special_ge", True)
    special_ge = None
    sp_note = ""
    if not enable_special:
        trace.append("Step1.5：外格筛查开关关闭（不启用外格优先判定）")
        sp_note = "外格筛查开关关闭"
    else:
        special_ge, sp_note = _screen_special_ge(
            gans, zhis, day_gan, day_wx, strict_he, ws, config, trace)
    if special_ge:
        occ_sp = _scan_tenshen(day_gan, gans, eff_hide, zhis)
        xy_ctx = {
            "occ": occ_sp, "he": he, "gans": gans, "day_gan": day_gan, "eff_hide": eff_hide, "zhis": zhis,
            "ge_ss": None, "ge_category": "外格", "ge_name": special_ge,
            "ge_status": "成格", "clean_level": "清纯",
            "xiang_shen_list": [], "ji_shen_list": [], "route_label": "",
            "route_xiang": [], "ge_good": True, "wangshuai_tag": wangshuai_tag,
            "special_ge": special_ge,
        }
        xiyong_geju = compute_xiyong_geju(xy_ctx)
        trace.extend(xiyong_geju["trace"])
        cong_context = _cong_context(ws, special_ge, "外格")
        return {
            "main_ge_name": special_ge, "ge_shen": special_ge,
            "xiang_shen_list": [], "ji_shen_list": [],
            "ge_status": "成格", "clean_level": "清纯",
            "ge_category": "外格", "note": sp_note, "lu_ren_flag": False,
            "structure_evidence": dict(source='geju._screen_special_ge',name=special_ge,matched=True,
                kind='hua' if special_ge.startswith('化') else 'zhuanwang' if '专旺' in special_ge else 'two_elements' if '两气成象' in special_ge else 'cong',
                day_hua=strict_he['gan_hua'][2],day_isolated=special_ge.startswith('化'),
                pair=[w for w in M.WUXING_LIST if w in special_ge] if '两气成象' in special_ge else []),
            "special_ge": special_ge, "trace_log": trace,
            "wangshuai_tag": wangshuai_tag, "wangshuai_confidence": wangshuai_conf,
            "is_cong": cong_context["is_cong"],
            "is_fake_cong": cong_context["is_fake_cong"],
            "cong_context": cong_context,
            "siling_gan": siling_gan(month_zhi, solar_term_day),
            "siling_used_for_ge": None, "an_ge_flag": False,
            "ge_variant": "明格",
            "quge_basis": "外格优先（命中从/专旺/化气/两气成象，跳过八格）",
            "bijiao_tou": [], "he_source": he_source, "xiyong_geju": xiyong_geju,
        }

    # ---------- Step2：月令取格（yan 2026-11-06 古籍调研后拍板的新口径） ----------
    # 规则：① 月令藏干唯一透出 → 取该透出；② 多透 → 按藏干序位
    #       「本气 > 中气 > 余气」取最前；③ 都不透 → 取本气并标「暗格」；
    #       ④ 透出字若为日主比劫 → 该字不取（比劫不成格），整盘按建禄/禄刃论（Step3）。
    # 人元司令（节气后天数决定的当令之干）**不参与取格**；PRD V1.0 的
    # 「司令切中气 / 四库严格司令 / 本气与司令二气相争」全部废止。
    pillars_gan = [gans[0], gans[1], gans[3]]  # 年/月/时（日主不算透出）
    visible = []
    for g in month_hide:
        if g in pillars_gan and g not in visible:
            visible.append(g)
    bijiao_visible = [g for g in visible
                      if _group_of(M.shishen(day_gan, g)) == "比劫"]
    valid_visible = [g for g in visible if g not in bijiao_visible]
    trace.append("Step2：月令有效藏干=%s（本气>中气>余气），透出天干=%s%s；"
                 "可定格候选=%s"
                 % ("、".join(month_hide),
                    "、".join(visible) if visible else "无",
                    ("；比劫透出%s不取格神" % "、".join(bijiao_visible))
                    if bijiao_visible else "",
                    "、".join(valid_visible) if valid_visible else "无"))

    lu_ren_flag = False
    special_ge = None
    candidate = None
    candidate_from = ""
    an_ge_flag = False
    ge_variant = "明格"

    def shishen_name(g):
        return M.shishen(day_gan, g)

    if len(valid_visible) == 1:
        candidate = valid_visible[0]
        candidate_from = "单透取格神"
        trace.append("Step2：月令唯一透出%s → 取为格神" % candidate)
    elif len(valid_visible) >= 2:
        order = {g: month_hide.index(g) for g in valid_visible if g in month_hide}
        candidate = min(order, key=order.get) if order else valid_visible[0]
        candidate_from = "多透-藏干序位(本气>中气>余气)"
        za = [g for g in valid_visible if g != candidate]
        trace.append("Step2：月令多透（%s），按本气>中气>余气取%s为格神%s"
                     % ("、".join(valid_visible), candidate,
                        ("，其余%s为杂" % "、".join(za)) if za else ""))
    else:
        candidate = month_benqi
        candidate_from = "不透-取本气(暗格)"
        an_ge_flag = True
        ge_variant = "暗格"
        trace.append("Step2：月令无有效透出%s → 取本气%s为格神，标为【暗格】"
                     % (("（仅透比劫%s，比劫不成格）" % "、".join(bijiao_visible))
                        if bijiao_visible else "", candidate))

    # ---------- Step3：禄刃 vs 八格 ----------
    # 禄刃触发（新口径）：月令藏干透出比劫（该字不取格神），或最终取出的格神
    # 为比劫 → 整盘按建禄/禄刃论；其余透出只作相神，不升格（PRD 禄刃铁则）。
    # 月支是否临官/帝旺只用于细分格名（建禄 / 阳刃 / 月劫），不再单独触发。
    # 提纲被三合/三会改写后，不再按原月支论禄刃。
    month_is_lu = (month_zhi == TEN_GAN_LU.get(day_gan)) and not month_hua
    month_is_yang_ren = (month_zhi == YANG_REN.get(day_gan)) and not month_hua
    month_is_yin_diwang = (month_zhi == YIN_DIWANG.get(day_gan)) and not month_hua
    cand_is_bijiao = (_group_of(shishen_name(candidate)) == "比劫")
    # 「比劫透出」只意味着该字不取格神，并不直接触发禄刃；只有按 ①–③ 最终
    # 取出的格神仍是比劫（多为都不透、本气恰为比劫）才按建禄/禄刃论。
    is_lu_ren_month = cand_is_bijiao or ((not month_hua) and (month_is_lu or month_is_yang_ren or month_is_yin_diwang))

    ge_category = None        # 八格 / 禄刃 / 外格
    ge_name = None
    ge_shen = None
    xiang_shen_list = []
    ji_shen_list = []
    clean_level = "清纯"
    ge_status = None
    note = ""
    route_label = ""          # Step4 选中的顺逆/双路线名（透传给 Step8 喜用层）
    route_xiang = []          # Step4 生效的相神十神名
    ge_ss = None              # 八格格神十神名；禄刃 / 无格为 None

    if is_lu_ren_month:
        lu_ren_flag = True
        ge_category = "禄刃"
        if month_is_lu:
            ge_name = "建禄格"
        elif month_is_yang_ren:
            ge_name = "阳刃格"        # 阳干帝旺
        elif month_is_yin_diwang:
            ge_name = "月劫格"         # 阴干帝旺（阴干无阳刃）
        else:
            ge_name = "建禄格"         # 月令藏比劫透出但月支非禄/刃位 → 按 yan 口径归建禄
        ge_shen = "%s（%s）" % (day_gan, ge_name.replace("格", ""))
        if bijiao_visible:
            lu_why = "月令透出比劫%s（比劫不成格、不取该字）" % "、".join(bijiao_visible)
        elif cand_is_bijiao:
            lu_why = "月令无有效透出，取本气%s为日主比劫" % candidate
        else:
            lu_why = "月令藏比劫"
        if an_ge_flag:
            # 禄刃不是「取本气立八格」，故不标暗格；同步改写取格依据避免字段自相矛盾
            an_ge_flag = False
            ge_variant = "明格"
            candidate_from = "不透-取本气(归禄刃)"
            trace.append("Step2：本盘归禄刃（非八格取本气），不标暗格")
        trace.append("Step3：%s → 按禄刃格（%s）论，非八格；"
                     "Step2 候选%s在此作废，其余透出只作相神、不升格"
                     % (lu_why, ge_name, candidate))
        # 禄刃取相神：官杀 > 财 > 食伤 > 印
        occ = _scan_tenshen(day_gan, gans, eff_hide, zhis)
        priority = [("官", ["正官", "七杀"]), ("财", ["正财", "偏财"]),
                    ("食伤", ["食神", "伤官"]), ("比劫", ["比肩", "劫财"])]
        found = []
        for grp, ss_list in priority:
            hit = [ss for ss in ss_list if any(r["tou"] and record_power(r,he)>0 for r in occ.get(ss, []))]
            if hit:
                found.append((grp, hit))
        month_tou = [g for g in month_hide if g in pillars_gan and M.shishen(day_gan, g) not in ("比肩", "劫财") and any(r["tou"] and record_power(r,he)>0 for r in occ.get(M.shishen(day_gan,g),[]))]
        if ge_name in ("建禄格", "月劫格") and month_tou:
            found.insert(0, ("月支透干", [M.shishen(day_gan, g) for g in month_tou]))
        if found:
            top_grp, top_hit = found[0]
            chosen_rec=max((r for r in records(occ,he) if r['tou'] and r['ss'] in top_hit and r['effective']>0),
                           key=lambda r:(r['effective'],-r['idx']))
            top_hit=[chosen_rec['ss']]
            xiang_shen_list = []
            for ss in top_hit:
                rec = chosen_rec
                xiang_shen_list.append("%s（%s%s）"
                                       % (rec["gan"], ss, "" if rec["tou"] else "·藏"))
            note = "本盘为%s（非八格），按禄刃取相神优先级（官杀>财>食伤>比劫）得%s；相神候选：%s" % (
                ge_name, top_grp, "、".join(xiang_shen_list))
            # PRD Step3 要求：日志必须写明「不是官格，是建禄用官」
            trace.append("Step3：本盘为%s，不是%s格，是%s用%s（透干只作相神，不升格）"
                         % (ge_name, top_grp, ge_name.replace("格", ""), top_grp))
            # 阳刃无官杀制 → 破格；建禄印为忌
            if ge_name == "阳刃格" and not any(r["tou"] for ss in ("正官", "七杀") for r in occ.get(ss, [])):
                ge_status = "真破格"
                note += "；阳刃无官杀制刃 → 破格"
                trace.append("Step3：阳刃无官杀制刃 → 真破格")
            else:
                ge_status = "成格"
                if ge_name == "建禄格" and any(r["tou"] and record_power(r,he)>0 for ss in ("正印", "偏印") for r in occ.get(ss, [])):
                    ji_shen_list = ["%s（%s·印为忌）" % (occ[ss][0]["gan"], ss)
                                    for ss in _present(occ, ["正印", "偏印"]) if any(r["tou"] and record_power(r,he)>0 for r in occ[ss])]
                    note += "；印星透出为建禄之忌"
                trace.append("Step3：禄刃局取相神优先级命中%s，定%s"
                             % (top_grp, ge_status))
        else:
            # 阳刃连相神都无，必然也无官杀制刃，与上面分支保持同一判据（真破格）；
            # 早期版本此处给「成中有败」，与「有财透但无官杀制 → 真破格」倒挂。
            ge_status = "真破格" if ge_name == "阳刃格" else "成格"
            note = "本盘为%s，全局无官杀/财/食伤/印可用，无相神%s" % (
                ge_name, "；阳刃无官杀制刃 → 破格" if ge_name == "阳刃格" else "，待运补足")
            trace.append("Step3：禄刃局无可用相神 → %s" % ge_status)
    else:
        # ---------- 八格分支 ----------
        ge_category = "八格"
        cand_ss = shishen_name(candidate)
        if cand_ss not in GE_TENSHEN:
            # 防御兜底：比劫候选按新口径已在 Step3 归入禄刃，此处理论不可达。
            ge_name = "建禄格"
            ge_category = "禄刃"
            lu_ren_flag = True
            ge_shen = "%s（建禄）" % day_gan
            ge_status = "成格"
            note = "月令候选%s为比劫（%s），按建禄格论（防御兜底）" % (candidate, cand_ss)
            trace.append("Step3：候选%s为比劫十神 → 归建禄格（防御兜底）" % candidate)
        else:
            ge_name = cand_ss + "格"
            ge_shen = "%s%s（%s）" % (candidate, M.WUXING_GAN[candidate], cand_ss)
            ge_ss = cand_ss
            trace.append("Step3：候选格神=%s，十神=%s → 定%s" % (candidate, cand_ss, ge_name))
            (ge_status, clean_level, xiang_shen_list, ji_shen_list, note,
             route_label, route_xiang) =\
                _evaluate_bage(day_gan, gans, eff_hide, he, cand_ss, candidate,
                               valid_visible, month_benqi, solar_term_day, trace, zhis=zhis)

    # ---------- Step5/Step6 清浊与成破已在 _evaluate_bage 内处理；禄刃清浊补充 ----------
    if ge_category == "禄刃":
        clean_level = shared_clean(occ, he)

    if ge_name == "阳刃格":
        from .geju_rules import blade_metrics
        blade_power, control_power = blade_metrics(occ,he)
        ratio = config.get("blade_control_ratio", 1.0)
        controlled = control_power > 0 and control_power >= blade_power * ratio
        ge_status = "成格" if controlled else "真破格"
        note += "；制刃校验：有效官杀%.2f / 阳刃%.2f，门槛比例%.2f → %s" % (control_power, blade_power, ratio, ge_status)
        trace.append(note)

    # ---------- 附加：旺衰维度（标签已在 Step1.5 前置筛查时取好，此处不参与定格） ----------
    # 外格筛查已前置（Step1.5）：命中从/专旺/化气则已提前 return，八格路径下
    # 不再对真破格做外格兜底（同一套门槛，结论必同），故此处不设 Step7 重复筛查。

    if ge_category=='八格' and ge_ss:
        ge_visible=[r for r in occ.get(ge_ss,[]) if r['tou'] and r['gan']==candidate]
        if ge_visible and all(record_power(r,he)<=0 for r in ge_visible):
            an_ge_flag=True
            ge_variant='暗格'
            candidate_from='格神透干完全合去-退依月令藏气'
            note+='；格神透干完全失效，退依月令藏气按暗格论，品级下降，不直接判破格'
            trace.append('Step3复核：格神透干完全合去，退为暗格；成破仍按剩余结构判断')

    # ---------- Step8：格局维度喜用（李厚君师傅笔记口径） ----------
    # 独立一层，不干预 Step1-7 的定格 / 清浊 / 成破。总纲：
    #   有病 → 治病为先（药神优先）；无病 → 吉神顺用 / 凶神逆用取相神。
    # 笔记与 PRD 的理论分歧（禄刃升格、印格取用、调候优先、扶抑）见 DATA_NOTES #17-20。
    xy_ctx = {
        "occ": _scan_tenshen(day_gan, gans, eff_hide, zhis),
        "he": he,
        "gans": gans,
        "day_gan": day_gan,
        "ge_ss": ge_ss,
        "ge_category": ge_category,
        "ge_name": ge_name,
        "ge_status": ge_status,
        "ge_note": note,
        "route_conflict": "双路线" in note and ge_status == "真破格",
        "clean_level": clean_level,
        "xiang_shen_list": xiang_shen_list,
        "ji_shen_list": ji_shen_list,
        "route_label": route_label,
        "route_xiang": route_xiang,
        # 与 Step4 同一善恶判据（SHISHEN_GOOD 优先，GE_ROUTE.good 兜底），
        # 避免喜用层把偏财格标成「凶神逆用」而主流程标「顺用」。
        "ge_good": (SHISHEN_GOOD.get(ge_ss) if ge_ss in SHISHEN_GOOD
                    else GE_ROUTE.get(ge_ss, {}).get("good", True)),
        "wangshuai_tag": wangshuai_tag,
        "blade_control_ratio": config.get("blade_control_ratio", 1.0),
        "special_ge": special_ge,
        "eff_hide": eff_hide, "zhis": zhis,
    }
    xiyong_geju = compute_xiyong_geju(xy_ctx)
    trace.extend(xiyong_geju["trace"])
    cong_context = _cong_context(ws, ge_name, ge_category)

    result = {
        "rescue_summary": he.get("ge_rescue_summary",dict(rescued_strong=[],unresolved_strong=[],weak_risks=[])),
        "main_ge_name": ge_name,
        "ge_shen": ge_shen,
        "xiang_shen_list": xiang_shen_list,
        "ji_shen_list": ji_shen_list,
        "ge_status": ge_status,
        "ge_note": note,
        "route_conflict": "双路线" in note and ge_status == "真破格",
        "clean_level": clean_level,
        "ge_category": ge_category,
        "note": note,
        "lu_ren_flag": lu_ren_flag,
        "special_ge": special_ge,
        "trace_log": trace,
        "wangshuai_tag": wangshuai_tag,
        "wangshuai_confidence": wangshuai_conf,
        "is_cong": cong_context["is_cong"],
        "is_fake_cong": cong_context["is_fake_cong"],
        "cong_context": cong_context,
        "siling_gan": siling_gan(month_zhi, solar_term_day),  # 原月令司令（仅供参考，不参与取格）
        "siling_used_for_ge": None,    # 新口径：人元司令不参与取格，恒为 None
        "an_ge_flag": an_ge_flag,      # 月令无有效透出、取本气为格 → 暗格
        "ge_variant": ge_variant,      # 明格 / 暗格
        "quge_basis": candidate_from,  # 单透 / 多透序位 / 不透取本气(暗格)
        "bijiao_tou": bijiao_visible,  # 月令透出但不取格神的比劫字
        "he_source": he_source,        # 前置合化来源（复用旺衰 / 兼容兜底直算）
        "xiyong_geju": xiyong_geju,    # Step8 格局维度喜用（病/药/顺逆取用，独立层）
    }
    return result


# ============================ 八格评价（Step4/5/6） ============================
def _evaluate_bage(day_gan, gans, eff_hide, he, cand_ss, candidate, visible,
                   month_benqi, solar_term_day, trace, zhis=None):
    occ = _scan_tenshen(day_gan, gans, eff_hide, zhis)
    route_def = GE_ROUTE[cand_ss]

    separated_route_ss = set()
    # 七杀 / 伤官：双路线互斥检测
    if "routes" in route_def:
        r_keys = list(route_def["routes"].keys())
        # 判定哪条路线成立：路线相神组在局内有根
        active = []
        for rk in r_keys:
            rdef = route_def["routes"][rk]
            if any(r["tou"] and record_power(r,he)>0 for ss in rdef["xiang"] for r in occ.get(ss, [])):
                active.append(rk)
        if len(active) >= 2:
            # 双路线互斥是否当真破格：仅当两路线各自「相神（用神）」相互相邻且十神
            # 相克（偏印克食神=枭印夺食、财克印=财破印）才视为相互干扰、浑浊破败；
            # 若两用神相隔（不相邻），各成格局、互不相碍，则择一取用、不破格。
            if _routes_conflict(occ, route_def, active, he):
                clean_level = "浊而无去"
                ge_status = "真破格"
                note = "%s双路线（%s）同时成立且用神相邻相克、相互干扰，"\
                       "格局浑浊破败、浊而无去" % (cand_ss, "、".join(active))
                trace.append("Step4：%s路线混杂（%s），用神相邻相克、互斥破格 → 真破格"
                             % (cand_ss, "、".join(active)))
                rk = _pick_route(occ, route_def, active, he)
                weak = [x for x in active if x != rk][0]
                return (ge_status, clean_level, [], [], note, rk,
                        _expand_groups(route_def["routes"][rk]["xiang"]))
            separated_route_ss = {ss for key in active for ss in route_def["routes"][key]["xiang"]}
            # 不相邻 → 择相神得力者取用，不破格
            rk = _pick_route(occ, route_def, active, he)
            trace.append("Step4：%s双路线（%s）同现，但用神相隔、互不相碍，"
                         "择一取用【%s】（不破格）" % (cand_ss, "、".join(active), rk))
        else:
            rk = active[0] if active else r_keys[0]
        rdef = route_def["routes"][rk]
        xiang_groups = rdef["xiang"]
        ji_groups = rdef["ji"]
        route_label = rk
        trace.append("Step4：%s为凶神逆用，取路线【%s】" % (cand_ss, rk))
    else:
        xiang_groups = route_def["xiang"]
        ji_groups = route_def["ji"]
        # 以十神善恶表为准（早期版本写死「顺用」，导致偏印格这种凶神逆用被标成善神顺用）
        is_good = SHISHEN_GOOD.get(cand_ss, route_def.get("good", True))
        route_label = "顺用" if is_good else "逆用"
        trace.append("Step4：%s为%s，相神组=%s，忌神组=%s"
                     % (cand_ss, ("善神顺用" if is_good else "凶神逆用"),
                        "、".join(xiang_groups) or "无",
                        "、".join(ji_groups) or "无"))

    # 相神 / 忌神（按十神名映射）
    xiang_ss = _expand_groups(xiang_groups)
    ji_ss = [ss for ss in _expand_groups(ji_groups) if ss not in separated_route_ss]
    xiang_present = _present(occ, xiang_ss)

    # 忌神「有力伤格」三级判定（PRD §2.5 + 子平同宫盖头/远隔弱化）：
    #   strong（有力破格）= 透出且确有根；冲后仍保留有效力量也不降级；
    #   weak  （虚浮/隐患 = 成中有败）= 透出但无根；
    #   ignore（忽略）     = 透出后有效力量为 0（如被合化/冲尽）。
    # records() 会给无根透干一个基础有效值，不能单凭 effective>=1 判强；
    # 也不能用 rec["root"]（它只表示该天干在全盘任意处有根）。必须看本柱
    # 实际分配到根的 detail["root_ids"]：同名天干分居两柱时，只有真正得根
    # 的柱位算强，另一柱仍按虚透为弱。
    effective_by_id={r["id"]:r for r in records(occ,he)}
    def _ji_level(rec):
        if not rec["tou"]:
            return "ignore"
        detail=effective_by_id[f"{rec['idx']}:1:{rec['gan']}"]
        if detail['effective']<=0: return "ignore"
        return "strong" if detail.get("root_ids") else "weak"

    for ss in ji_ss:
        for rec in occ.get(ss,[]):
            if rec['tou']:
                detail=effective_by_id[f"{rec['idx']}:1:{rec['gan']}"]
                trace.append("力量参考：%s@%s 冲后%.2f 根数%s 有效%.2f 等级%s" % (rec['gan'],rec['idx'],rec.get('weight',1),len(detail['root_ids']),detail['effective'],_ji_level(rec)))
    ji_strong_ss = []
    ji_weak_ss = []
    for ss in ji_ss:
        levels = [_ji_level(r) for r in occ.get(ss, [])]
        if any(l == "strong" for l in levels):
            ji_strong_ss.append(ss)
        if any(l == "weak" for l in levels):
            ji_weak_ss.append(ss)
    ji_present = list(dict.fromkeys(ji_strong_ss + ji_weak_ss))
    ji_strong = bool(ji_strong_ss)

    # 清浊判定（PRD §2.6，按子平修订）：
    #   浊 = 异类十神并见；官杀混杂、食伤混杂、正偏印并见；
    #   财星正偏同透不算浊（子平「财不忌偏正」）；
    #   浊而能清 = 多余字被天干五合合去（成功化去或合绊留一，两者皆去其杂）。
    grp_ss = {}
    for i, g in enumerate(gans):
        if i == 2:
            continue
        ss = M.shishen(day_gan, g)
        grp = _group_of(ss)
        if grp in ("官", "财", "印", "食伤"):
            grp_ss.setdefault(grp, {}).setdefault(ss, []).append(g)

    # 是否「浊」：
    #   月令多透——异类并见，或官杀/食伤/正偏印混杂 → 浊；财财同类不算浊；
    #   全局——仅官杀混杂、食伤混杂、正偏印并见算浊；财官/印食等异类并见是常格不另计浊。
    visible_ss = [M.shishen(day_gan, g) for g in visible]
    month_zhuo = _tenshen_hunzhuo(visible_ss)
    global_zhuo = any(_tenshen_hunzhuo(m.keys()) for grp, m in grp_ss.items())
    is_zhuo = month_zhuo or global_zhuo

    # 同类并见但不一定浊：财星正偏同透不视为浊，仅作提示
    same_group_multi = [grp for grp, m in grp_ss.items() if len(m) >= 2]
    if same_group_multi and not is_zhuo:
        trace.append("Step5：全局天干同类并见（%s同透），财星正偏并见不视为浊"
                     "（财不忌偏正）" % "、".join(same_group_multi))

    if is_zhuo:
        he_gans = set()
        for grp in he["he_groups"]:
            if grp["type"] == "wuhe":
                he_gans.update(grp["members"])
        extra = [g for g in visible if g != candidate]
        # 同类混杂中，与格神不同十神的那一个字也属于「多余」字
        for ss, gs in grp_ss.get(_group_of(cand_ss), {}).items():
            if ss != cand_ss:
                extra.extend(gs)
        extra = list(dict.fromkeys(extra))     # 去重保序
        extra_records=[r for rs in occ.values() for r in rs if r['tou'] and r['gan'] in extra]
        removed_records=[r for r in extra_records if rescue_fraction(r,he)==1]
        removed=[r['gan'] for r in removed_records]
        trace.append("Step5：逐柱去杂，已去=%s，未去=%s" %
                     ([(r['gan'],r['idx']) for r in removed_records],
                      [(r['gan'],r['idx']) for r in extra_records if rescue_fraction(r,he)<1]))
        if extra_records and len(removed_records)==len(extra_records):
            clean_level = "浊而能清"
            trace.append("Step5：混杂，但多余字%s被天干五合合去留清 → 浊而能清"
                         % "、".join(removed))
        else:
            clean_level = "浊而无去"
            trace.append("Step5：天干同类混杂（%s）且无合去机制 → 浊而无去"
                         % "、".join(same_group_multi or ["异类并见"]))
    else:
        clean_level = "清纯"
        removed = []
        trace.append("Step5：无成浊之同类混杂（财星正偏并见不另计浊） → 清纯")

    # 「合去留清」必须真正作用于成破判定：被五合合去的字，其十神不再算忌神。
    # 早期版本清浊只改 clean_level，Step6 仍拿被合去的七杀当忌神判破格，且配了
    # SAVIOUR ("正官","七杀")->"官" 这种「格神自救」的假救应（现已移除）。
    removed_ss = {M.shishen(day_gan, g) for g in removed}\
        if clean_level == "浊而能清" else set()
    if removed_ss:
        ji_strong_ss = [ss for ss in ji_strong_ss if any(_ji_level(r)=="strong" for r in occ.get(ss, []))]
        ji_weak_ss = [ss for ss in ji_weak_ss if any(_ji_level(r)=="weak" for r in occ.get(ss, []))]
        ji_present = list(dict.fromkeys(ji_strong_ss + ji_weak_ss))
        ji_strong = bool(ji_strong_ss)
        trace.append("Step5→6：合去留清生效，被合去的字对应十神%s不再计入成破判定"
                     % "、".join(sorted(removed_ss)))

    # 相神 / 忌神 列表：用最终生效的 ji_present，且取扫描时记录的真实干字
    xiang_shen_list = []
    for ss in xiang_present:
        rec = occ[ss][0]
        xiang_shen_list.append("%s（%s%s）" % (rec["gan"], ss, "" if rec["tou"] else "·藏"))
    ji_shen_list = []
    for ss in ji_present:
        # 优先挑真正 strong/weak 的记录，别误取年干远隔（ignore）的字
        rec = next((r for r in occ[ss] if _ji_level(r) in ("strong", "weak")),
                   occ[ss][0])
        ji_shen_list.append("%s（%s%s）" % (rec["gan"], ss, "" if rec["tou"] else "·藏"))

    # 成破状态机（Step6）。格神溯月令所出，自带月令之气，视为有力。
    xiang_rooted = _is_strong(occ, xiang_present)

    disease_ctx=dict(occ=occ,he=he,ge_ss=cand_ss,ge_category='八格',ge_name=cand_ss+'格',
                     ge_status='成格',route_label=route_label,route_xiang=_expand_groups(xiang_groups),
                     ji_shen_list=[],xiang_shen_list=[],route_conflict=False)
    build_relation_diseases(disease_ctx,ji_present)

    if ji_strong_ss:
        # 忌神有力 → 找救神。SAVIOUR 的忌神键允许写「组名」（如「比劫」），
        # 而 ji_strong_ss 里是具体十神名，故需同时匹配具体名与其所属组。
        rescued = []
        half_rescued = []
        disease_ctx=dict(occ=occ,he=he,ge_ss=cand_ss,ge_category='八格',ge_name=cand_ss+'格',
                         ge_status='成格',route_label=route_label,route_xiang=_expand_groups(xiang_groups),
                         ji_shen_list=[],xiang_shen_list=[],route_conflict=False)
        diseases,_,_,disease_rules=build_relation_diseases(disease_ctx,ji_strong_ss,only_blockers=True)
        strong_ids={r['id'] for r in effective_by_id.values() if r['tou'] and r['ss'] in ji_strong_ss and _ji_level(r)=='strong'}
        for disease in diseases:
            disease['target_ids']=sorted(strong_ids)
        allowed={ss for disease in diseases for _,names,_ in disease_rules.get(disease["name"],[]) for ss in expands(names)}
        adjudication=solve(dict(occ=occ,he=he,ge_ss=cand_ss),diseases,disease_rules,allowed)
        rescue_evidence=[]
        for disease,status in zip(diseases,adjudication["statuses"]):
            for rec in [r for ss in disease["bing_ss"] for r in occ.get(ss,[])]:
                if not rec["tou"] or _ji_level(rec)!="strong": continue
                ev=next((e for e in status["evidence"] if e.get("target_id")==f"{rec['idx']}:1:{rec['gan']}" and "remaining" in e),{})
                rescue_evidence.append(dict(ss=M.shishen(day_gan,rec["gan"]),idx=rec["idx"],gan=rec["gan"],
                    id=f"{rec['idx']}:1:{rec['gan']}",
                    status=(State.RESCUED if ev and ev['remaining']<=1e-9 else State.PARTIAL if ev and ev['remaining']<effective_by_id[f"{rec['idx']}:1:{rec['gan']}"]['effective'] else State.NO_DRUG),
                    remaining=ev.get("remaining",record_power(rec,he))))
        for item in rescue_evidence:
            trace.append("Step6：逐字救应 %s@%s %s 剩余%.2f" % (item["gan"],item["idx"],item["status"],item["remaining"]))
        for jss in ji_strong_ss:
            items=[e for e in rescue_evidence if e["ss"]==jss]
            if items and all(e["status"] in (State.RESCUED,State.BALANCED) for e in items): rescued.append(jss)
            elif any(e["status"]==State.PARTIAL for e in items): half_rescued.append(jss)
        trace.append("Step6：远隔五合半救=%s（不计完全获救）" % half_rescued)
        trace.append("Step6：逐个验证强忌神，已救=%s，未救=%s" %
                     (rescued, [x for x in ji_strong_ss if x not in rescued]))
        if len(rescued) == len(ji_strong_ss):
            ge_status = "败中有救"
            note = "全部强忌神逐一获救：%s" % "、".join(rescued)
        else:
            ge_status = "真破格"
            note = "%s，忌神%s有力伤格/相，全局无有力救神 → 真破格" % (
                route_label, "、".join(ji_strong_ss))
            trace.append("Step6：忌神有力且无有力救神 → 真破格")
    elif ji_weak_ss:
        ge_status = "成中有败"
        note = "%s，忌神%s已透出但有效力量不足1，隐患待岁运触发" % (
            route_label, "、".join(ji_weak_ss))
        trace.append("Step6：透干忌神有效力量不足1 → 成中有败（带忌）")
    else:
        ge_status = "成格"
        if not xiang_present:
            note = "%s，格神有力、无有力忌神，但相神不显，待运补相" % route_label
        elif not xiang_rooted:
            note = "%s，格神有力、无有力忌神，然相神虚浮无根，相神乏力，待运助根" % route_label
        else:
            note = "%s，格神有力、相神到位、无有力忌神 → 成格" % route_label
        trace.append("Step6：%s → 成格" % ge_status)

    he['ge_rescue_summary']=dict(rescued_strong=rescued if ji_strong_ss else [],
        unresolved_strong=[ss for ss in ji_strong_ss if ss not in rescued] if ji_strong_ss else [],
        weak_risks=list(ji_weak_ss),
        strong_positions=[dict(id=r['id'],ss=r['ss'],idx=r['idx'],effective=r['effective']) for r in effective_by_id.values() if r['tou'] and r['ss'] in ji_ss and _ji_level(r)=='strong'],
        weak_positions=[dict(id=r['id'],ss=r['ss'],idx=r['idx'],effective=r['effective']) for r in effective_by_id.values() if r['tou'] and r['ss'] in ji_ss and _ji_level(r)=='weak'],
        position_evidence=rescue_evidence if ji_strong_ss else [])
    if ge_status=='败中有救' and ji_weak_ss:
        note+='；败中有救但仍带弱忌：%s（隐患未解除）' % '、'.join(ji_weak_ss)
        trace.append('Step6：强忌已救，弱忌仍在：%s' % '、'.join(ji_weak_ss))

    return (ge_status, clean_level, xiang_shen_list, ji_shen_list, note,
            route_label, _expand_groups(xiang_groups))


def _expand_groups(groups):
    """把「十神组名」或「具体十神名」统一展开为十神名列表（含比肩/劫财）。

    组名：官/财/印/食伤/比劫；具体名：正官、七杀、…、比肩、劫财。
    两者混用是 GE_ROUTE / SAVIOUR 的常态（如食神忌「偏印」、财格忌「比劫」）。
    历史两处静默 bug：
      ① 早期只认组名 → 具体名条目全被吞（相神/忌神识别失效）；
      ② 后来用 GE_TENSHEN 过滤 → 「比劫」组被整体吞掉，导致财格「比劫夺财」
         无忌神、印格「比劫护印」无相神、以比劫为救神的救应恒为 False。
    比劫虽不成格（不属八格），但作为相神/忌神/救神完全合法，必须保留。
    """
    out = []
    group_names = set(SHISHEN_GROUP.values())     # 组名集合：官/财/印/食伤/比劫
    all_ss = set(SHISHEN_GROUP.keys())           # 十神名集合（含比肩/劫财）
    for grp in groups:
        if grp in group_names:
            for ss, g in SHISHEN_GROUP.items():   # 键=十神名，值=组名
                if g == grp and ss not in out:
                    out.append(ss)
        elif grp in all_ss and grp not in out:
            out.append(grp)
    return out


# ============================ 双路线互斥（yan 2026-11-06 修订） ============================
def _shishen_ke(a, b):
    """十神相克：印克食伤；财克印；食伤克官杀；官杀克比劫；比劫克财。"""
    ke_map = {
        "正印": {"食神", "伤官"}, "偏印": {"食神", "伤官"},
        "正财": {"正印", "偏印"}, "偏财": {"正印", "偏印"},
        "食神": {"正官", "七杀"}, "伤官": {"正官", "七杀"},
        "正官": {"比肩", "劫财"}, "七杀": {"比肩", "劫财"},
        "比肩": {"正财", "偏财"}, "劫财": {"正财", "偏财"},
    }
    return b in ke_map.get(a, set())


def _routes_conflict(occ, route_def, active, he=None):
    """双路线互斥是否当真破格：两路线的「相神（用神）」相互相邻且十神相克才破格。

    相邻 = 两用神所在柱下标相差 1（年-月 / 月-日 / 日-时）；同柱（差 0）不算相邻。
    仅当相邻且存在十神相克（偏印克食神=枭印夺食、财克印=财破印）才视为相互干扰、
    浑浊破败；否则两用神相隔、互不相碍，择一取用即可（yan 2026-11-06：互斥用神
    离得远、不相互干扰 → 不算破格，如阎锡山可用枭印也可用食神）。
    """
    route_recs = {}
    for rk in active:
        xiang_ss = _expand_groups(route_def["routes"][rk]["xiang"])
        recs = []
        for ss in xiang_ss:
            for rec in occ.get(ss, []):
                if rec["tou"] and record_power(rec,he)>0:
                    recs.append((ss, rec))
        route_recs[rk] = recs
    rk_list = list(route_recs)
    for i in range(len(rk_list)):
        for j in range(i + 1, len(rk_list)):
            for ssa, ra in route_recs[rk_list[i]]:
                for ssb, rb in route_recs[rk_list[j]]:
                    if abs(ra["idx"] - rb["idx"]) == 1 and\
                       (_shishen_ke(ssa, ssb) or _shishen_ke(ssb, ssa)):
                        return True
    return False


def _pick_route(occ, route_def, active, he=None):
    """双路线同现但不相邻、互不相碍时，择相神得力者取用（透干有根优先）。"""
    available=[r for r in records(occ,he or {'he_groups':[]}) if r['tou'] and r['effective']>0]
    best_rk,best_score=None,-1
    for rk in active:
        names=_expand_groups(route_def['routes'][rk]['xiang'])
        score=max((r['effective'] for r in available if r['ss'] in names),default=0)
        if score>best_score: best_rk,best_score=rk,score
    return best_rk or active[0]


# ============================ Step7：外格筛查（复用旺衰模块） ============================
def _day_is_isolated(gans, zhis, day_gan, day_wx, he):
    """PRD Step7 门槛：日主孤立无有力根气。

    以下任一成立即判「不孤立」：
      - 地支有日主禄 / 刃 / 帝旺 / 长生强根，且该支未被合化置换；
      - 年/月/时干有比劫或印星透出且有根。
    """
    strong_branches = {TEN_GAN_LU.get(day_gan), YANG_REN.get(day_gan),
                       YIN_DIWANG.get(day_gan), M.CHANGSHENG_10GAN.get(day_gan)}
    for i, z in enumerate(zhis):
        if he["branch_hua"][i]:
            continue
        if z in strong_branches:
            return False
    eff_hide = _build_eff_hide(zhis, he)   # 与旺衰同口径：branch_hua 全支置换
    for i, g in enumerate(gans):
        if i == 2:
            continue
        if M.shishen(day_gan, g) in ("比肩", "劫财", "正印", "偏印")\
                and _has_root(g, eff_hide):
            return False
    return True


def _screen_special_ge(gans, zhis, day_gan, day_wx, he, ws, config, trace):
    """八格之前优先调用。复用 wangshuai 真从标签 + heju 化气 + 两气成象。

    门槛（PRD §四 Step7「门槛极高」）：
      - 从格/专旺：旺衰模块必须给出「真从」(cong_info.is_cong=True)；
        假从 / 虚旺 / 身弱无根一律排除；
      - 化气格：额外要求日主孤立无有力根气；
      - 两气成象：以全局两行成象为准，不再叠加日主孤立门槛。
    返回 (special_ge_name_or_None, note)。
    """
    tag = ws["tag"]
    is_cong = bool(ws.get("cong_info", {}).get("is_cong"))
    isolated = _day_is_isolated(gans, zhis, day_gan, day_wx, he)
    trace.append("Step1.5：外格前置筛查（旺衰标签=%s / 真从=%s / 日主孤立=%s）"
                 % (tag, is_cong, isolated))

    # 1) 化气格：天干五合「严格成功」、且【日主必须参与该合】、且日主孤立。
    #    正统化气格是「日主与相邻干相合而化」，他柱两干相合不能把日主带走；
    #    早期版本只查「全局有无成功五合」，导致年干+月干合也被判成化气格（真 bug）。
    def _day_joins_wuhe(hgrp):
        # heju 已把参与柱下标写进 idx（V1.1.1 后）；只按干字匹配会在
        # 「日主与他柱同干字」时误判，故优先用下标。兼容旧格式 / mock 时回退字符匹配。
        if hgrp.get("idx"):
            return 2 in hgrp["idx"]
        ms = set(hgrp["members"])
        return any(2 in (i, i + 1) and {gans[i], gans[i + 1]} == ms
                   for i in (0, 1, 2))

    hua = next((g for g in he["he_groups"]
                if g["type"] == "wuhe" and g["hua_success"]
                and _day_joins_wuhe(g)), None)
    if hua is None and any(g["type"] == "wuhe" and g["hua_success"]
                           for g in he["he_groups"]):
        trace.append("Step7：存在成功五合，但日主未参与该合（他柱之合）→ 不合化气格门槛")
    if hua:
        wx = hua["hua_wuxing"]
        if isolated:
            hua_name = {
                "土": "化土格（甲己）", "金": "化金格（乙庚）", "水": "化水格（丙辛）",
                "木": "化木格（丁壬）", "火": "化火格（戊癸）",
            }.get(wx, "化气格")
            trace.append("Step7：天干%s五合化%s成功且日主孤立 → 化气格"
                         % ("".join(hua["members"]), wx))
            return hua_name, "外格前置筛查：天干五合化气成功 → 外格：%s" % hua_name
        trace.append("Step7：五合化%s成功，但日主有强根/印比有根，不合化气格门槛" % wx)

    # 2) 从格 / 专旺：复用旺衰模块的真从判定（气势专一由 cong_threshold 严格把关）
    if is_cong and tag == "从弱":
        dom = _dominant_k_wx(gans, zhis, day_wx, he)
        sub = {"财": "从财格", "官杀": "从杀格", "食伤": "从儿格"}.get(dom, "从弱格")
        trace.append("Step7：旺衰真从弱，克泄耗主导=%s → 从格：%s" % (dom, sub))
        return sub, "外格前置筛查：旺衰真从弱、%s主导 → 外格：%s" % (dom, sub)
    if is_cong and tag == "从强":
        trace.append("Step7：旺衰真从强 → 从强格；专旺细分需要独立审定条件，不由F占比推定")
        return "从强格", "外格前置筛查：真从强，按印比顺势；专旺细分尚未审定，不直接命名五类专旺格"

    # 3) 两气成象（两行）：全局仅两五行且相生成象；不以日主孤立为门槛。
    two = _two_line_check(gans, zhis, he, day_wx)
    if two:
        trace.append("Step7：主体两行及允许的第三行满足成象条件 → 两气成象格")
        return two, "外格前置筛查：全局两行成象 → 外格：%s" % two

    trace.append("Step7：旺衰标签=%s，无合格外格条件（门槛未达）" % tag)
    return None, "外格前置筛查：未入真从/专旺，亦无合格化气/两行 → 无格，原局驳杂"


def _dominant_k_wx(gans, zhis, day_wx, he):
    """粗略返回克泄耗主导的十神组（财/官杀/食伤）。合化支按置换后五行计入。"""
    counts=qi_table(gans,zhis,he)
    scores={"食伤":counts[M.SHENG[day_wx]],"财":counts[M.KE[day_wx]],"官杀":counts[M.KE_OF[day_wx]]}
    winners=[k for k,v in scores.items() if abs(v-max(scores.values()))<1e-9]
    return winners[0] if len(winners)==1 else "并列："+"、".join(winners)


def _two_line_check(gans, zhis, he, day_wx):
    """两气成象：全局（天干+地支有效五行）仅出现两个五行，且二者相生或比和成象。"""
    counts = {w:v for w,v in qi_table(gans,zhis,he,_build_eff_hide(zhis,he,month_hua=next((g["hua_wuxing"] for g in he.get("he_groups",[]) if g["type"] in ("sanhe","sanhuí") and g["hua_success"] and zhis[1] in g["members"]),None),keep_month_original=True)).items() if v>0}
    ordered=sorted(counts,key=lambda w:-counts[w])
    if len(ordered) not in (2,3): return None
    for a in ordered:
        b=M.SHENG[a]
        if b not in counts or min(counts[a],counts[b])<2: continue
        other=[w for w in ordered if w not in (a,b)]
        # 主体两行各至少2分；第三行不得压过较弱主体，只允许下游泄秀。
        if other and not (counts[a]>=2 and counts[b]>=2 and
                          other[0]==M.SHENG[b] and counts[other[0]]<=min(counts[a],counts[b])):
            continue
        return "两气成象格（%s·%s相生）" % (a,b)
    return None


# ============================ DATA_NOTES：PRD 内部冲突与收敛口径 ============================
# 以下为 PRD 文本自相矛盾处，实现按「正统子平 + 输出字段定义」收敛，供复核与后续调参。
#
# 1) 纯气月令：§2.2 司令表给卯/酉列双段，与「纯气取本气」备注冲突。
#    新口径（#22）下人元司令不参与取格，此冲突已无实义；siling_gan 仍按
#    「卯→乙、酉→辛」输出，仅作参考字段。
#
# 2) 禄刃：Step3 把「庚申」同时列进建禄表与阳刃表，且祇按五行给禄（金禄在申）
#    会漏掉阴干禄（辛禄在酉、癸禄在子）。实现按十干十二长生：
#      禄 = 甲寅/乙卯/丙巳/丁午/戊巳/己午/庚申/辛酉/壬亥/癸子
#      阳刃（阳干帝旺）= 甲卯/丙午/戊午/庚酉/壬子；阴干帝旺月归「月劫格」，无阳刃。
#
# 3) 合化改提纲 / 口径统一（yan 复核后确认「以旺衰模块校验过的合化为准」）：
#    ① 判定层：compute_geju 不再自行调用 heju.evaluate，而是从旺衰结果 ws["he_detail"]
#       直接取用（wangshuai._assemble 输出完整 he）。engine 链路全局只算一次合化，
#       两模块对同一盘、同一 config 的合化结论必然一致；仅传精简 mock ws 时才兜底直算。
#    ② 消费层：有效藏干按 he["branch_hua"] 对【所有】成功置换的支整体置换，
#       与旺衰模块「整支按化神五行计入、原藏干作废」同口径；外格统计的天干五行
#       同样用 he["gan_hua"] 置换（与旺衰 F/K 统计一致）。
#    ③ 唯一例外：月令提纲。§2.4 明确「六合、半合、遥合不改变月令提纲」，故
#       月令只在三合/三会成功（month_hua 非空）时置换；六合成功只影响月令以外
#       的支。这是格局派硬规则，与旺衰模块「六合成功则整支置换」在此一支上刻意不同。
#    ④ 八格主流程的十神仍按【原天干】论：天干五合化气成功属外格（化气格）范畴，
#       不继续用八格十神置换，真破格时由 Step7 兜底。故不做 gan_hua 的十神级替换。
#    ⑤ 合化成功后重新生成该五行「虚拟藏干」（该五行两个天干，按天干序），再走透干/定格。
#
# 4) 忌神有力：§2.5 只给「有根/无根」二分。实现按子平贴身原则三级化：
#      strong = 月/时干贴身透出且有根，或非月令地支藏干有根；
#      weak   = 月/时干透出无根（虚浮隐患 → 成中有败）；
#      ignore = 年干远隔虚浮、或月令藏而不透被格神盖头（不计入）。
#    否则月令余气杂神会把绝大多数格局误判为真破格。
#
# 5) 比劫不成格：月令本气为日主同气（比劫）透出，不立格、也不阻断禄刃分支
#    （Step3 铁则「有其他十神透出才放弃禄刃」中的「其他」指八格十神，不含比劫）。
#
# 6) 状态名：§1.4 输出枚举为「败中有救」，§四 Step6 正文写「败中有成」→ 取输出枚举。
#
# 7) 旺衰：仅作附加字段（wangshuai_tag / confidence），不参与定格、成破、清浊
#    （§六.8）；作为外格前置筛查（Step1.5）的门槛依据（真从标签 + 日主孤立），
#    命中从/专旺/化气/两气成象即归外格、跳过八格（yan 2026-11-06 由旧 Step7 兜底前置）。
#
# 8) 顺逆路线精确化：正官忌「伤官克官」而非整个食伤组（食神不克官）；财格
#    「官护财」指**正官**（七杀不护财），故这两处用具体十神名而非组名。
#    GE_ROUTE 的 xiang/ji 允许组名与具体名混用，由 _expand_groups 统一展开。
#
# 9) 同类混杂（§2.6）指「全局天干」官杀/财/食伤/印同透，并非只看月令透干
#    （同一地支的藏干几乎不可能构成同类十神）。实现同时扫描全局天干；
#    「合去留清」按天干五合成员（成功化去或合绊留一，两者皆去其杂）判定。
#
# 10) 外格门槛（§四 Step7「门槛极高」）：复用旺衰模块「真从」标签
#     (cong_info.is_cong) 作为气势专一判据，叠加「日主孤立」判据（无禄/刃/
#     长生强根、无印比有根透干）；假从 / 虚旺 / 身弱无根一律排除。
#
# 11) 化气格必须由【日主参与】五合：正统化气格是日主与相邻柱之干相合而化，
#     年干+月干之类「他柱之合」不能把日主带走。旧版只查全局有无成功五合，
#     曾把「甲子 己辰 乙丑 庚申」（日主乙，甲己合在年月）误判为化土格。
#
# 12) 偏印（枭）格忌「枭旺夺食」：PRD §四 Step4 表列有忌神，旧版误写成 ji=[]
#     并自注「PRD 未列忌神」，导致偏印格永不可能破格。现补 ji=[食神]，
#     救应为「财制枭」(SAVIOUR)，品级判为败中有救。
#
# 13) 合去留清必须作用于成破：旧版 Step5 只改 clean_level，Step6 仍拿被五合
#     合去的七杀当忌神判破格，并配了 ("正官","七杀")->"官" 的「格神自救」假救应。
#     现删除该条，改为把被合去字对应的十神从忌神集合中剔除后再判状态。
#
# 14) 提纲合化改写后停用司令表：原实现在 month_hua 时把 siling 置 None。
#     新口径（#22）下司令全程不参与取格，该分叉已并入统一逻辑；合化后
#     取格仍以化神「虚拟藏干」按藏干序位走，siling_gan 仅作参考字段。
#
# 15) 午月（四正）的司令口径：PRD 曾令午月 10–19 天切己土司令取格。
#     新口径（#22）废止司令参与，午月不透一律取本气丙（标暗格）；
#     PRD 该分支的注释范围争议（四长生 vs 四正）随之失效。
#
# 16) 比劫不是八格十神，但作为相神 / 忌神 / 救神完全合法。_expand_groups 早期
#     用 GE_TENSHEN 过滤展开结果，把整个「比劫」组静默吞掉，导致：财格
#     「比劫夺财」永远无忌神、印格「比劫护印」无相神、以比劫为救神的救应恒 False；
#     且 SAVIOUR 的忌神键写组名（如 ("正财","比劫")）时与具体十神名对不上。
#     现放开过滤，并让救应匹配同时支持「具体名 / 所属组名」，补偏财同论条目。
#
# 17) 格局维度喜用（Step8）：依据李厚君师傅《八字格局核心笔记整理》新增独立一层，
#     实现在 geju_xiyong.py，输出 geju["xiyong_geju"]（engine.final_xiyong 亦引用，
#     但不加权）。总纲：「先看格局是否有病，有病先治病，有病有药方为贵；然后看
#     格局的用在哪里（无病再看用），顺用逆用要分清，用神只要出现在天干优先取
#     透干者；最后考虑身强身弱」。PRD 原本只有相神/忌神字段、无独立喜用层，
#     这是按 yan 拍板新增，不参与 Step1-7 定格 / 清浊 / 成破（§六.8）。
#
# 18) 分歧（未改定格）：笔记表1「禄劫/羊刃格，天干透财官杀则以财格/官格/杀格论」
#     与 PRD §四 Step3「禄刃铁则：透干不升格，只是相神」直接冲突。V1 仍按 PRD
#     定格（不升格）；喜用层对禄刃给 mode=禄刃取相，阳刃无制则治病为先（药=官杀
#     制刃），不改写 main_ge_name。若采用笔记口径须改 Step3，属理论路线变更。
#
# 19) 分歧（未改定格）：笔记「印格总结：印格一般身强，直接取财、官、食伤为用」
#     与 PRD 正印格顺用「官杀生印、比劫护印、忌财来破印」冲突。喜用层以 PRD
#     顺用为主（GE_YONG 正印 = 官印相生 / 杀印相生 / 印配食伤），不把财列为
#     印格喜用；财仅在「财来坏印」成病时作忌神、「印过旺」时作药。
#
# 20) 分歧（未实现）：笔记「尤其以调候之病最优先」「金水伤官喜见官、木火伤官
#     需见印」，但 PRD §1.2 明确 V1 不做调候优先级、调候仅附加信息。故喜用层
#     固定 tiaohou_pending=True、不判调候之病；调候模块上线后须把调候病置于
#     bing_list 最前。另笔记「身弱不担财取印」「最后考虑身强身弱」属扶抑，
#     PRD 禁止混入 → 只写进 fuyi_hint / note，不改 mode、不改取用。
#
# 21) 病清单口径：合并笔记「通病」段与表2「病在」，按「坏格 / 格局病 / 轻」分级
#     （笔记「非该正神格下，天干正神被克影响不大」→ 轻病只提示不夺用）。
#     笔记原文带问号的存疑条目（「正神太多者，则需正神的克制者来克？」、
#     「或取比劫通关？」）不落硬规则，避免推出「财多取比劫」「印混杂用财克印」
#     这类自相矛盾的药。药按「合去 > 克掉 > 通关 > 隔开」排序，但局内已有药
#     一律优先于「待运取」（笔记「有病有药方为贵」）；七杀/伤官双路线互斥
#     （§六.6）在喜用层同样生效，不并列两条为用。
#
# 22) 【yan 2026-11-06 古籍调研后拍板】月令取格口径重写，替代 PRD V1.0 的
#     「透干 > 司令 > 本气」：
#       ① 月令藏干唯一透出 → 取该透出为格神；
#       ② 多透 → 按藏干序位「本气 > 中气 > 余气」取最前
#          （如中气、余气同透则取中气）；
#       ③ 都不透 → 取本气为格，标「暗格」（an_ge_flag / ge_variant；格名不变、
#          不改成破/清浊/喜用判定）；
#       ④ 透出字为日主比劫 → 该字不取（比劫不成格），照常在剩余透出中取格；
#          只有按 ①–③ 最终取出的格神仍是比劫（多为都不透、本气恰为比劫）
#          才按建禄/禄刃论。月支临官/帝旺只用于细分格名（建禄/阳刃/月劫），
#          不再单独触发禄刃；禄刃不标暗格。
#     **人元司令（节气后天数决定的当令之干）不参与取格**：siling_gan 仅作参考
#     字段，siling_used_for_ge 恒 None。连带废止：司令切中气、四库严格司令、
#     本气与司令二气相争、同类多透司令优先、合化后停司令表的分叉。
#     solar_term_day 仍自动推算并输出（排盘信息 / 历史契约），但同一四柱给不同
#     solar_term_day 必须得到完全相同的格局结论（已写进 tests/test_geju.py）。
#     注意：PRD §2.2 人元司令分段表本身保留，siling_gan() 仍可独立调用。

# 2026-11-06 审核修订：以执行代码和《格局规则审核修订.md》为准，早期 DATA_NOTES 为历史记录。
