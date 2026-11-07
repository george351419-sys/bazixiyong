# -*- coding: utf-8 -*-
"""调候用神模块（tiaohou v1）｜依据《穷通宝鉴_调候用神表_定本.md》十干逐月详表。

职责边界（**重要，勿越界**）：
  - 本模块只输出「调候维度」的用神喜忌，由 `日干 + 月令` 定，不由身强身弱反推；
  - 调候 ≠ 全局用神。徐乐吾明言「冬令金水，不可缺火，**非定以为用也**」，
    故本模块**不覆盖**旺衰维度 / 格局维度的喜用，engine.final_xiyong V1 仍不加权合并；
    下游若要合并，宜作「门槛 + 权重修正」，而非直接替换方向。

数据结构（对应定本末尾建议）：
  {日干, 月令, 通用序列[], 条件用[{expr,gans,cond}], 忌[], 分段[], 定序原句, 备注, 存疑标记, 另读[]}
  「另读」（丁·亥 庚先）单独存字段，**不覆盖默认通用序列**。

定位规则：
  - 常规格：(日干, 月支) 唯一命中；
  - 节气／上下半月分段：乙·酉（白露／秋分，定本拆两行）、乙·午（夏至）、
    癸·辰（清明／谷雨）、癸·未、壬·丑（后两格定本通用取用列已是全月代表值）；
  - 未给节气信息时，返回 `undetermined` + 全部候选，默认取定本速查矩阵代表值，
    并明确标注「需补节气信息」，不假装确定；
  - 「节气后 15 日」切点是**工程约定**，原书未给日数，所有据此的判定都标 basis。

诚实边界：
  - 底表全部转录自网络整理本，**未核纸本影印**；
  - `ji_gans` / `ji_phrases` 为从备注、原句机械抽取，需人工复核；
  - 条件用的触发判定只覆盖可结构化几类（夜生、节气分段、支成某局、天干多见、透干），
    其余一律 `None`（无法自动判定），不臆断。
"""
from __future__ import annotations

import re

from . import metadata as M
from .tiaohou_data import TIAOHOU_TABLE

GAN_SET = set(M.GAN)
GAN = M.GAN
ZHI_POS = ["年", "月", "日", "时"]

# 定本拍板口径（2026-11-06）：丁·亥 默认甲先，庚先为另读备查
SOURCE_VERSION = "穷通宝鉴_调候用神表_定本.md / 2026-11-06 最终版（丁·亥 默认甲先）"

CAVEAT = (
    "调候维度 ≠ 全局用神：徐乐吾「冬令金水，不可缺火，非定以为用也」。"
    "本结果由日干＋月令定，不覆盖旺衰／格局维度喜用；V1 不做三维加权合并。"
)

# 分段别名 → 归一化标签（便于上层传自然语言）
SEG_ALIAS = {
    "段a": "段A", "段b": "段B", "a": "段A", "b": "段B",
    "白露": "段A", "白露后": "段A", "白露—秋分": "段A", "白露-秋分": "段A",
    "秋分": "段B", "秋分后": "段B", "秋分—寒露": "段B", "秋分-寒露": "段B",
    "上半月": "上半月", "夏至前": "上半月",
    "下半月": "下半月", "夏至后": "下半月", "夏至": "下半月",
    "清明": "清明后", "清明后": "清明后",
    "谷雨": "谷雨后", "谷雨后": "谷雨后",
}

# 夜生判定（工程约定：时支落日入至日出）
NIGHT_ZHI = set("酉戌亥子丑寅")

# 上下半月切点（工程约定，原书未给日数）
DEFAULT_HALF_MONTH_DAY = 15


# ---------------------------------------------------------------- 输入解析
def _coerce_chart(chart):
    """统一输入 -> (gans[4], zhis[4], meta)。

    支持：
      - PRD dict：{year/month/day/hour: {gan,zhi}}
      - 扁平 dict：{gans:[4], zhis:[4]}
      - 字符串四柱："庚午 甲申 庚子 壬午"
    meta 可含 solar_term_day / jie_name / tiaohou_segment / night。
    """
    if isinstance(chart, str):
        parts = chart.split()
        if len(parts) != 4 or any(len(p) != 2 for p in parts):
            raise ValueError("四柱需形如 '庚午 甲申 庚子 壬午'（4 组干支，空格分隔）")
        gans = [p[0] for p in parts]
        zhis = [p[1] for p in parts]
        meta = {}
    elif isinstance(chart, dict):
        if "gans" in chart and "zhis" in chart:
            gans = list(chart["gans"])
            zhis = list(chart["zhis"])
        else:
            gans = [chart[k]["gan"] for k in ("year", "month", "day", "hour")]
            zhis = [chart[k]["zhi"] for k in ("year", "month", "day", "hour")]
        meta = {k: chart.get(k) for k in
                ("solar_term_day", "jie_name", "tiaohou_segment", "night")}
        si = chart.get("solar_term_info")
        if isinstance(si, dict):
            meta.setdefault("solar_term_day", si.get("day"))
            meta.setdefault("jie_name", si.get("jie_name"))
    else:
        raise ValueError("chart 需为 dict 或四柱字符串")

    if len(gans) != 4 or len(zhis) != 4:
        raise ValueError("四柱需各 4 个天干／地支")
    for g in gans:
        if g not in GAN_SET:
            raise ValueError("非法天干：%s" % g)
    for z in zhis:
        if z not in M.ZHI_LIST:
            raise ValueError("非法地支：%s" % z)
    return gans, zhis, meta


# ---------------------------------------------------------------- 底表定位
def _rows(day_gan, month_zhi):
    return [r for r in TIAOHOU_TABLE
            if r["day_gan"] == day_gan and r["month_zhi"] == month_zhi]


def _norm_segment(segment):
    if not segment:
        return None
    s = str(segment).strip()
    return SEG_ALIAS.get(s.lower(), SEG_ALIAS.get(s, s))


def _infer_segment(jie_name, solar_term_day, half_day):
    """由节气名 / 节气后天数推断分段标签。

    返回 (label, basis)；无法推断返回 (None, None)。
    """
    if jie_name:
        j = str(jie_name)
        jie_map = {"白露": "段A", "秋分": "段B", "清明": "清明后",
                   "谷雨": "谷雨后", "夏至": "下半月", "芒种": "上半月",
                   "小暑": "上半月"}
        for key, label in jie_map.items():
            if key in j:
                return label, ("原书节气分段 + 排盘节气名「%s」（原书明文）" % j)
    if solar_term_day is not None:
        try:
            d = int(solar_term_day)
        except (TypeError, ValueError):
            return None, None
        return ("上半月" if d < half_day else "下半月",
                "工程约定：节气后 %d 日切点（原书未给日数）；当前为第 %d 天" % (half_day, d))
    return None, None


def select_row(day_gan, month_zhi, *, segment=None, solar_term_day=None,
               jie_name=None, half_day=DEFAULT_HALF_MONTH_DAY):
    """定位 (日干, 月支) 的定本行，并处理节气／上下半月分段。

    返回 (row, segment_info)。segment_info 含 status / basis / candidates / applied。
    """
    rows = _rows(day_gan, month_zhi)
    if not rows:
        raise ValueError("底表无此格：%s 日 · %s 月" % (day_gan, month_zhi))

    explicit = _norm_segment(segment)
    inferred, basis = _infer_segment(jie_name, solar_term_day, half_day)
    wanted = explicit or inferred

    info = {
        "status": "single",
        "basis": basis,
        "applied": None,
        "candidates": [],
        "undetermined": False,
        "needs_jieqi": False,
    }

    # 具有 seg_label 的多行格（乙·酉 段A/段B）
    multi = [r for r in rows if r["seg_label"]]
    if multi:
        info["candidates"] = [
            {"label": r["seg_label"], "general": r["general"],
             "raw": r["general_raw"]} for r in multi
        ]
        info["needs_jieqi"] = True
        chosen = None
        if wanted:
            for r in multi:
                lab = r["seg_label"] or ""
                if wanted in lab or (wanted == "上半月" and "段A" in lab) or \
                   (wanted == "下半月" and "段B" in lab):
                    chosen = r
                    break
        if chosen:
            info.update(status="selected", applied=chosen["seg_label"],
                        basis=("显式指定：" + wanted) if explicit else basis)
            return chosen, info
        # 未定：按定本速查矩阵代表值取段A，但明确标注不确定
        info.update(status="undetermined", undetermined=True,
                    applied=multi[0]["seg_label"],
                    basis="未给节气信息，按定本速查矩阵代表值取首段；实际可能属另一段，需补节气信息")
        return multi[0], info

    row = rows[0]
    # 通用取用列内部分段（乙·午、癸·辰）
    if row["general_segments"]:
        info["candidates"] = [
            {"label": s["label"], "general": s["gans"], "raw": s["raw"]}
            for s in row["general_segments"]
        ]
        info["needs_jieqi"] = True
        if wanted:
            for s in row["general_segments"]:
                if wanted in s["label"] or (wanted == "上半月" and "清明后" in s["label"]) or \
                   (wanted == "下半月" and "谷雨后" in s["label"]):
                    info.update(status="selected", applied=s["label"],
                                basis=("显式指定：" + wanted) if explicit else basis)
                    return dict(row, general=s["gans"],
                                general_raw=s["raw"], _segment_applied=s["label"]), info
        info.update(status="undetermined", undetermined=True,
                    applied=row["general_segments"][0]["label"],
                    basis="未给节气信息，按定本速查矩阵代表值取首段；实际可能属另一段，需补节气信息")
        first = row["general_segments"][0]
        return dict(row, general=first["gans"], general_raw=first["raw"],
                    _segment_applied=first["label"]), info

    # 备注里有上下半月分段但通用取用列已是全月代表值（癸·未、壬·丑）
    if any("上下" in k or "节气" in k for k in row["flags"]) and \
       any(k in row["note"] for k in ("上半月", "下半月", "清明", "谷雨")):
        info["status"] = "representative"
        info["needs_jieqi"] = True
        info["basis"] = "定本通用取用列为全月代表值；上下半月差异见备注与原句，未按节气拆列"
        if wanted:
            info["applied"] = wanted
    return row, info


# ---------------------------------------------------------------- 原局比对
def presence_of(gans, zhis, gan):
    """某用神天干在原局的状态：透干 / 仅藏 / 原局无。"""
    tou = [ZHI_POS[i] for i, g in enumerate(gans) if g == gan]
    cang = [ZHI_POS[i] for i, z in enumerate(zhis) if gan in M.ZHI_HIDE.get(z, [])]
    state = "透干" if tou else ("仅藏" if cang else "原局无")
    return {"gan": gan, "state": state, "tou_at": tou, "cang_at": cang,
            "is_day_gan": (gans[2] == gan)}


def _branch_groups(zhis, wx):
    """地支是否构成某五行的三会／三合局（工程近似：只看成员齐备）。"""
    hits = []
    for h in M.SANHUI:
        if h["wx"] == wx and set(h["members"]).issubset(set(zhis)):
            hits.append("三会%s局(%s)" % (wx, "".join(h["members"])))
    for h in M.SANHE:
        if h["wx"] == wx and set(h["members"]).issubset(set(zhis)):
            hits.append("三合%s局(%s)" % (wx, "".join(h["members"])))
    return hits


def _eval_condition(cond, ctx):
    """对一条条件用的触发条件做可结构化子判定。

    返回 checks 列表；auto_triggered 保守判定：
      只有存在 checks 且全部明确 True 才 True；任一明确 False 则 False；否则 None。
    """
    checks = []
    gans, zhis = ctx["gans"], ctx["zhis"]

    if "夜生" in cond or "日生" in cond:
        is_night = ctx.get("night")
        if is_night is None:
            is_night = zhis[3] in NIGHT_ZHI
        need_night = "夜生" in cond
        checks.append({
            "kind": "夜生/日生", "text": "夜生者贵，日生者否" if need_night else "日生",
            "result": bool(is_night) if need_night else (not bool(is_night)),
            "basis": "工程约定：时支属「酉戌亥子丑寅」视为夜生（可由 chart.night 覆盖）",
        })

    for kw, label in (("上半月", "上半月"), ("下半月", "下半月"),
                      ("夏至前", "上半月"), ("夏至后", "下半月"),
                      ("清明后", "清明后"), ("谷雨后", "谷雨后"),
                      ("白露之后", "段A"), ("秋分后", "段B")):
        if kw in cond:
            d = ctx.get("solar_term_day")
            if d is None:
                checks.append({"kind": "节气分段", "text": kw, "result": None,
                               "basis": "缺节气信息，无法判定"})
            else:
                first = ("下半月" not in label and "段B" not in label and "谷雨" not in label)
                ok = (int(d) < ctx["half_day"]) if first else (int(d) >= ctx["half_day"])
                checks.append({"kind": "节气分段", "text": kw, "result": bool(ok),
                               "basis": "工程约定：节气后 %d 日切点（原书未给日数）"
                                        % ctx["half_day"]})

    m = re.search(r"支成([木火土金水])局", cond)
    if m:
        hits = _branch_groups(zhis, m.group(1))
        checks.append({
            "kind": "支成%s局" % m.group(1), "text": m.group(0),
            "result": bool(hits), "detail": hits,
            "basis": "原书条件 + 工程近似（三会／三合成员齐备即算，未验合化真假）",
        })

    for pat, kind in ((r"([甲乙丙丁戊己庚辛壬癸])透重重", "天干重重"),
                      (r"([甲乙丙丁戊己庚辛壬癸])叠叠", "天干叠叠"),
                      (r"一派([甲乙丙丁戊己庚辛壬癸])", "一派某干"),
                      (r"([甲乙丙丁戊己庚辛壬癸])多", "天干多见")):
        for g in re.findall(pat, cond):
            n = gans.count(g)
            checks.append({"kind": kind, "text": "%s 多见" % g, "result": n >= 2,
                           "detail": "原局天干出现 %d 次" % n,
                           "basis": "工程近似：原书「某多／一派／重重」按天干出现 ≥2 次计"})

    for pat in (r"([甲乙丙丁戊己庚辛壬癸])透", r"见([甲乙丙丁戊己庚辛壬癸])",
                r"得([甲乙丙丁戊己庚辛壬癸])", r"([甲乙丙丁戊己庚辛壬癸])出干"):
        for g in re.findall(pat, cond):
            tou = g in gans
            checks.append({"kind": "透干/见干", "text": "%s 透出" % g,
                           "result": tou,
                           "detail": ("透于" + "、".join(
                               ZHI_POS[i] for i, x in enumerate(gans) if x == g)) if tou else "原局天干未见",
                           "basis": "原书条件 + 天干逐字比对（不含地支藏干）"})

    for pat in (r"无([甲乙丙丁戊己庚辛壬癸])", r"不见([甲乙丙丁戊己庚辛壬癸])",
                r"乏([甲乙丙丁戊己庚辛壬癸])"):
        for g in re.findall(pat, cond):
            absent = g not in gans
            checks.append({"kind": "无某干", "text": "天干无 %s" % g,
                           "result": absent,
                           "detail": "原局天干%s%s" % ("无" if absent else "有", g),
                           "basis": "工程近似：原书「无／不见／乏某干」按四柱天干逐字比对（不计藏干）"})

    results = [c["result"] for c in checks]
    if not results:
        auto = None
    elif any(r is False for r in results):
        auto = False
    elif any(r is None for r in results):
        auto = None
    else:
        auto = True
    # 原条件含「或／／不然」等并列分支时，自动子判定否不了整条条件：
    # 只判了其中一个分支就下「未触发」会误导，统一降级为待判。
    if auto is False and any(k in cond for k in ("或", "／", "/", "不然", "否则", "姑用")):
        checks.append({
            "kind": "多分支条件", "text": "原条件含并列分支，自动判定不足以否定整条",
            "result": None,
            "basis": "保守降级：原书「或…／…」需按具体分支人工判读，不硬判未触发",
        })
        auto = None
    return checks, auto


# ---------------------------------------------------------------- 主入口
def compute_tiaohou(chart, *, segment=None, config=None):
    """输入八字 → 调候维度用神喜忌（结构化结果）。

    参数:
        chart  : PRD dict / 扁平 dict / 四柱字符串；可带 solar_term_day、jie_name、
                 tiaohou_segment、night（夜生标记）等辅助字段。
        segment: 显式分段，如「段B」「下半月」「谷雨后」；不传则自动推断。
        config : 可选 {half_month_day:15, auto_condition_eval:True, night:None}

    返回 dict：默认通用序列 / 主用 / 条件用（含触发判定）/ 忌 / 原局透藏 /
             调候维度喜用 / 标记 / 另读 / 定序原句 / 备注 / 一句话结论。
    """
    cfg = {"half_month_day": DEFAULT_HALF_MONTH_DAY,
           "auto_condition_eval": True, "night": None}
    if config:
        cfg.update(config)

    gans, zhis, meta = _coerce_chart(chart)
    day_gan, month_zhi = gans[2], zhis[1]
    half_day = int(cfg["half_month_day"])
    seg = segment or meta.get("tiaohou_segment")
    solar_term_day = meta.get("solar_term_day")
    jie_name = meta.get("jie_name")

    row, seg_info = select_row(day_gan, month_zhi, segment=seg,
                               solar_term_day=solar_term_day,
                               jie_name=jie_name, half_day=half_day)

    night = cfg.get("night")
    if night is None:
        night = meta.get("night")
    ctx = {"gans": gans, "zhis": zhis, "day_gan": day_gan,
           "month_zhi": month_zhi, "solar_term_day": solar_term_day,
           "jie_name": jie_name, "night": night, "half_day": half_day}

    general = list(row["general"])
    no_order = bool(row["no_order"])
    zhuyong = None if (no_order or not general) else general[0]

    # 条件用触发判定
    conditions, active_gans = [], []
    for c in row["conditions"]:
        item = {"expr": c["expr"], "gans": c["gans"], "cond": c["cond"],
                "checks": [], "auto_triggered": None, "evaluated": False}
        if cfg["auto_condition_eval"] and c["cond"]:
            checks, auto = _eval_condition(c["cond"], ctx)
            item["checks"] = checks
            item["auto_triggered"] = auto
            item["evaluated"] = bool(checks)
            if auto is True:
                active_gans.extend(c["gans"])
        conditions.append(item)

    favored_effective = general + [g for g in active_gans if g not in general]
    presence = {g: presence_of(gans, zhis, g) for g in favored_effective}
    ji_gans = [g for g in row["ji_gans"] if g not in favored_effective]

    flags = list(row["flags"])
    if seg_info["undetermined"]:
        flags.append("节气分段未定：当前取代表值，需补节气信息")
    if no_order:
        flags.append("原书无定序：不可按首字加权")
    if row["alt_read"]:
        flags.append("存在另读（备查，非默认）")

    favored_wx = []
    for g in favored_effective:
        w = M.WUXING_GAN[g]
        if w not in favored_wx:
            favored_wx.append(w)
    missing = [g for g, p in presence.items()
               if p["state"] == "原局无"]

    # 一句话结论
    if general:
        seq = "、".join(general)
        head = "%s 日 %s 月：调候用神 %s" % (day_gan, month_zhi, seq)
        if no_order:
            head += "（原书并用／无定序，不作首用加权）"
        else:
            head += "，首用 %s" % zhuyong
    else:
        head = "%s 日 %s 月：原书明言随宜酌用，无固定通用序列" % (day_gan, month_zhi)
    if seg_info["undetermined"]:
        head += "；节气分段未定，此为代表值"
    tou = [g for g in favored_effective if presence[g]["state"] == "透干"]
    cang = [g for g in favored_effective if presence[g]["state"] == "仅藏"]
    if tou:
        head += "；已透：%s" % "、".join(tou)
    if cang:
        head += "；仅藏：%s" % "、".join(cang)
    if missing:
        head += "；原局缺：%s" % "、".join(missing)
    if ji_gans:
        head += "；忌：%s（自动抽取，需复核）" % "、".join(ji_gans)

    return {
        "ok": True,
        "module": "tiaohou_v1",
        "source": SOURCE_VERSION,
        "caveat": CAVEAT,
        "day_gan": day_gan,
        "month_zhi": month_zhi,
        "month_label": row["month_label"],
        "segment": seg_info,
        "general_raw": row["general_raw"],
        "yongshen": general,                 # 默认通用取用序列（首字为主）
        "zhuyong": zhuyong,                  # 首用；无定序时为 None
        "no_order": no_order,
        "conditions": conditions,
        "conditions_raw": row["condition_raw"],
        "condition_extra": row["condition_extra"],
        "ji": {"gans": ji_gans, "phrases": row["ji_phrases"],
               "auto_extracted": True,
               "note": "忌神短语为从备注／原句机械抽取，需人工复核，不代替原书判读"},
        "quote": row["quote"],
        "note": row["note"],
        "flags": flags,
        "alt_read": row["alt_read"],
        "presence": presence,
        "xiyong": {
            "dimension": "调候",
            "favored": general,
            "favored_effective": favored_effective,
            "favored_wuxing": favored_wx,
            "disliked": ji_gans,
            "missing": missing,
            "pending_conditions": [
                {"expr": c["expr"], "gans": c["gans"], "cond": c["cond"]}
                for c in conditions if c["auto_triggered"] is not True
            ],
            "active_conditions": [
                {"expr": c["expr"], "gans": c["gans"], "cond": c["cond"]}
                for c in conditions if c["auto_triggered"] is True
            ],
            "note": "favored 为定本默认通用序列；favored_effective 追加了自动判定为已触发的条件用。"
                    "条件触发是保守的工程近似，未触发／待判的条件用一律留在 pending_conditions，"
                    "不得当作固定次用加权。",
        },
        "summary": head,
        "cell": {
            "general_raw": row["general_raw"], "general_segments": row["general_segments"],
            "condition_raw": row["condition_raw"], "quote": row["quote"],
            "note": row["note"],
        },
    }


def lookup(day_gan, month_zhi, *, segment=None, solar_term_day=None, jie_name=None):
    """只按「日干 + 月支」查定本格（不接八字原局），返回底表行 + 分段信息。

    适合只想查表、不排盘的场合；要判断用神透藏请用 compute_tiaohou。
    """
    if day_gan not in GAN_SET or month_zhi not in M.ZHI_LIST:
        raise ValueError("日干／月支非法：%s / %s" % (day_gan, month_zhi))
    row, info = select_row(day_gan, month_zhi, segment=segment,
                           solar_term_day=solar_term_day, jie_name=jie_name)
    return {"day_gan": day_gan, "month_zhi": month_zhi,
            "row": row, "segment": info, "source": SOURCE_VERSION}


def _clip(s, n=160):
    s = str(s or "")
    return s if len(s) <= n else s[:n] + "…（完整见 --json／定本）"


def format_tiaohou(out, *, verbose=True):
    """结构化结果 → 中文可读文本（CLI 用；Web 用自身渲染）。"""
    if not out.get("ok"):
        return "调候分析失败：%s" % out.get("error")
    L = []
    L.append("调候维度（《穷通宝鉴》逐月取用｜独立维度，不覆盖旺衰／格局）")
    L.append("  %s" % out["summary"])
    if out["conditions_raw"] and out["conditions_raw"] != "—":
        L.append("  条件用（须带触发条件，非通用次用）：")
        for c in out["conditions"]:
            mark = {True: "✔ 已触发", False: "✘ 未触发", None: "? 待判"}[c["auto_triggered"]]
            L.append("    [%s] %s（%s）%s" % (
                mark, c["expr"] or "—", c["cond"] or "无条件文字",
                ("｜" + "；".join(x["text"] + "=" + str(x["result"])
                              for x in c["checks"])) if verbose and c["checks"] else ""))
    if out["ji"]["phrases"]:
        L.append("  忌／不可用（原文抽取，需复核）：%s"
                 % "；".join(_clip(p, 44) for p in out["ji"]["phrases"][:3]))
    if out["alt_read"]:
        for a in out["alt_read"]:
            L.append("  另读备查（非默认）：%s — %s" % ("、".join(a["gans"]), a["basis"]))
    if verbose:
        L.append("  原书定序：%s" % _clip(out["quote"], 200))
        L.append("  备注：%s" % _clip(out["note"], 180))
        if out["flags"]:
            L.append("  标记：%s" % "；".join(out["flags"]))
    L.append("  ※ %s" % out["caveat"])
    return "\n".join(L)
