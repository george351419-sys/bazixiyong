# -*- coding: utf-8 -*-
"""由《穷通宝鉴_调候用神表_定本.md》「二、十干逐月详表」生成静态数据表。

用法（项目根目录执行）：
    python3 tools/build_tiaohou_data.py

产出：bazi_core/tiaohou_data.py（TIAOHOU_TABLE，121 行）
原则：忠实转录定本四列原文，派生字段（天干序列 / 忌短语 / 标记）只做可追溯的
      机械抽取，不做命理再判断；「默认 / 另读」口径以定本拍板为准。
"""
from __future__ import annotations

import io
import os
import pprint
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "穷通宝鉴_调候用神表_定本.md")
DST = os.path.join(ROOT, "bazi_core", "tiaohou_data.py")

GAN = "甲乙丙丁戊己庚辛壬癸"
GAN_SET = set(GAN)
ZHI = "子丑寅卯辰巳午未申酉戌亥"

FOOTNOTE_FLAGS = {
    "①": "节气／上下半月分段",
    "②": "条件用不并列（非通用次用）",
    "③": "版本窜文／异文",
    "④": "体用视角之别",
    "⑤": "原书明言无定序／并用",
    "⑥": "底本分节差异（定本默认甲先）",
}

NO_ORDER_KEYS = (
    "无定序", "随宜酌用", "两透并取", "非拘执先后",
    "并用，无明定序", "并用，无严格先后", "（并用）",
)

G = "甲乙丙丁戊己庚辛壬癸"
JI_PATTERNS = [
    r"忌见?([" + G + r"]+)",
    r"切忌([" + G + r"]+)",
    r"([" + G + r"]+)(?:水|火|木|金|土)?为病",
    r"([" + G + r"]+)水?不可为用",
    r"不用([" + G + r"]+)",
    r"([" + G + r"]+)为忌",
    r"不可专用([" + G + r"]+)",
    r"([" + G + r"]+)不入取用",
    r"([" + G + r"]+)(?:土|水|火|木|金)?不用",
    r"([" + G + r"]+)反为病",
    r"([" + G + r"]+)在[^，。]*为忌",
]
JI_SENTENCE_KEYS = (
    "忌", "为病", "不可为用", "不用", "不必", "切忌", "反为病",
    "不可专用", "不可离", "为忌", "不入取用",
)


def clean(s: str) -> str:
    return s.replace("**", "").strip()


def gans_in(s: str):
    return [c for c in s if c in GAN_SET]


def uniq(seq):
    out = []
    for x in seq:
        if x not in out:
            out.append(x)
    return out


def split_top(text: str, sep: str = "；"):
    """按分号切分，但保留括号内部的分号（条件用列里很常见）。"""
    parts, buf, depth = [], [], 0
    for ch in text:
        if ch in "（(":
            depth += 1
        elif ch in "）)":
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def parse_conditions(raw: str):
    """条件用列 -> [{expr, gans, cond}]，另返回未识别项。

    括号感知切分，避免把「丁（有丁出、颇吉；或一片癸己会党…）」中的分号切断。
    """
    s = clean(raw)
    if s in ("—", "-", "", "–"):
        return [], []
    items, extra = [], []
    for part in split_top(s):
        m = re.match(r"^(.*?)（(.*)）$", part, re.S)
        if not m:
            m = re.match(r"^(.*?)\((.*)\)$", part, re.S)
        if m:
            expr, cond = m.group(1).strip(), m.group(2).strip()
        else:
            expr, cond = part, ""
        rec = {"expr": expr, "gans": uniq(gans_in(expr)), "cond": cond}
        if rec["gans"] or rec["cond"]:
            items.append(rec)
        else:
            extra.append(part)
    return items, extra


def parse_general(raw: str):
    """通用取用列 -> (通用天干序列, 分段列表, 去括号后的原文注记)。

    分段行（乙·午、癸·辰）形如「上半月 癸／下半月 丙、癸」，拆成两段；
    其余行先剥掉括号说明再抽天干，避免把「（庚辛、丙为通例低阶佐用）」
    这类括注里的低阶佐用误当通用主序列。
    """
    s = clean(raw)
    segs = []
    if "／" in s and any(k in s for k in ("上半月", "下半月", "清明后", "谷雨后")):
        for part in s.split("／"):
            part = part.strip()
            idx = next((i for i, c in enumerate(part) if c in GAN_SET), len(part))
            label, body = part[:idx].strip(), part[idx:]
            segs.append({"label": label or "分段", "gans": uniq(gans_in(body)), "raw": part})
        return [], segs, s
    body = re.sub(r"（[^）]*）", "", s)
    body = re.sub(r"\([^)]*\)", "", body)
    note = "；".join(re.findall(r"[（(]([^）)]*)[）)]", s))
    return uniq(gans_in(body)), [], note


def extract_ji(*texts):
    """从备注 / 定序原句里抽取「忌 / 为病 / 不可为用」原文短语与命中的天干。"""
    phrases, gans = [], []
    for t in texts:
        for sent in re.split(r"[；。]", clean(t)):
            sent = sent.strip()
            if sent and any(k in sent for k in JI_SENTENCE_KEYS) and sent not in phrases:
                phrases.append(sent)
    joined = "".join(phrases)
    for pat in JI_PATTERNS:
        for hit in re.findall(pat, joined):
            for g in (hit if isinstance(hit, str) else ""):
                if g in GAN_SET and g not in gans:
                    gans.append(g)
    return phrases, gans


def flags_of(month_label: str, note: str, general_raw: str):
    flags = []
    for mark, name in FOOTNOTE_FLAGS.items():
        if mark in month_label:
            flags.append(name)
    if "推定值" in note:
        flags.append("推定值（该本无逐月专条，非原书明文）")
    if "两读并存" in note or "并列可读" in note:
        flags.append("两读并存／并列可读，不硬判")
    if "条件分支" in note or "非通用并列次用" in note:
        flags.append("条件分支（非通用次用）")
    if "明言" in note and any(k in note for k in ("不可用", "为忌", "为病", "不必", "不可为用")):
        flags.append("原书明言忌／不可用")
    if any(k in general_raw for k in NO_ORDER_KEYS):
        flags.append("原书无定序／并用（不可按首字加权）")
    return uniq(flags)


def parse_table():
    text = io.open(SRC, encoding="utf-8").read()
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("## 二、十干逐月详表"))
    end = next(i for i, l in enumerate(lines[start + 1:], start + 1) if l.startswith("## 三、"))
    rows, day_gan = [], None
    for line in lines[start:end]:
        m = re.match(r"^### ([甲乙丙丁戊己庚辛壬癸])木?$", line.strip()) or \
            re.match(r"^### ([甲乙丙丁戊己庚辛壬癸])(?:木|火|土|金|水)$", line.strip())
        if m:
            day_gan = m.group(1)
            continue
        if not line.startswith("|") or not day_gan:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 5 or cells[0].startswith("---") or cells[0] == "月令":
            continue
        month_label, general_raw, cond_raw, quote, note = cells
        mz = re.search(r"（([子丑寅卯辰巳午未申酉戌亥])）", month_label)
        if not mz:
            raise ValueError("无法解析月令：%s" % month_label)
        month_zhi = mz.group(1)
        sm = re.search(r"·(段[A-Z][^①-⑥]*)", month_label)
        seg_label = sm.group(1).strip() if sm else None
        general, general_segments, general_note = parse_general(general_raw)
        conditions, cond_extra = parse_conditions(cond_raw)
        ji_phrases, ji_gans = extract_ji(note, quote)
        row = {
            "day_gan": day_gan,
            "month_zhi": month_zhi,
            "month_label": month_label,
            "seg_label": seg_label,
            "general_raw": clean(general_raw),
            "general": general,
            "general_segments": general_segments,
            "general_note": general_note,
            "no_order": any(k in clean(general_raw) for k in NO_ORDER_KEYS),
            "condition_raw": clean(cond_raw),
            "conditions": conditions,
            "condition_extra": cond_extra,
            "quote": clean(quote),
            "note": clean(note),
            "ji_phrases": ji_phrases,
            "ji_gans": ji_gans,
            "flags": flags_of(month_label, note, clean(general_raw)),
            "alt_read": [],
        }
        # 定本拍板：丁·亥 默认甲先；古文本「庚先」只作另读备查（不进默认序列）
        if day_gan == "丁" and month_zhi == "亥":
            row["alt_read"] = [{
                "gans": ["庚", "甲"],
                "basis": "古文本（古文岛／gwsj／ctext）标「十月丁火：」专段，首句「三冬丁火微寒，端用庚甲，甲乃庚之良友」",
                "note": "底本分节差异；另读备查，非默认，不进速查矩阵、不作默认编码值",
            }]
        rows.append(row)
    return rows


def main():
    rows = parse_table()
    # 完整性校验：10 干 × 12 月 = 120，乙·酉拆两段 → 121
    assert len(rows) == 121, "详表行数应为 121，实际 %d" % len(rows)
    pairs = [(r["day_gan"], r["month_zhi"]) for r in rows]
    for g in GAN:
        for z in ZHI:
            assert (g, z) in pairs, "缺格：%s·%s" % (g, z)
    assert len([r for r in rows if r["seg_label"]]) == 2, "乙·酉 应有段A/段B 两行"
    for r in rows:
        assert r["quote"] and r["note"], "缺原句或备注：%s" % r["month_label"]

    body = pprint.pformat(rows, width=110, sort_dicts=False)
    header = '''# -*- coding: utf-8 -*-
"""《穷通宝鉴》调候用神静态底表（自动生成，**请勿手改**）。

来源：穷通宝鉴_调候用神表_定本.md →「二、十干逐月详表」（121 行）。
生成器：tools/build_tiaohou_data.py（每次定本修订后重跑本脚本即可同步）。

字段说明：
  day_gan/month_zhi/month_label/seg_label : 定位键；乙·酉拆「段A 白露—秋分」「段B 秋分—寒露」两行
  general_raw                             : 定本「通用取用」列原文（已去粗体标记）
  general                                 : 从 general_raw 机械抽取的默认通用天干序列（首字为主）
  general_segments                        : 内部分段（乙·午 上半月/下半月、癸·辰 清明后/谷雨后）
  general_note                            : general_raw 括注内容（如「并用，无明定序」）
  no_order                                : 原书明言无定序／并用，禁止按首字加权
  condition_raw/conditions/condition_extra: 「条件用」列原文 / 结构化 [{expr,gans,cond}] / 未识别项
  quote/note                              : 「原书定序原句」「备注」列原文
  ji_phrases/ji_gans                      : 从 note+quote 自动抽取的忌／为病原文短语与命中天干（需人工复核）
  flags                                   : 分段、条件分支、异文、体用、无定序、推定值等标记
  alt_read                                : 另读（丁·亥 庚先），**不覆盖默认 general**

诚实边界：全部依据网络整理本转录，未核纸本影印；ji_* 为机械抽取，不代替原书判读。
"""
from __future__ import annotations

'''
    io.open(DST, "w", encoding="utf-8").write(header + "TIAOHOU_TABLE = " + body + "\n")
    print("生成 %s：%d 行" % (DST, len(rows)))
    for key in [("丁", "亥"), ("辛", "子"), ("癸", "丑"), ("乙", "酉"), ("戊", "寅")]:
        rs = [r for r in rows if (r["day_gan"], r["month_zhi"]) == key]
        for r in rs:
            print("  %s·%s [%s] general=%s no_order=%s cond=%d flags=%s" % (
                r["day_gan"], r["month_zhi"], r["seg_label"] or "-",
                "".join(r["general"]) or "/".join(
                    s["label"] + ":" + "".join(s["gans"]) for s in r["general_segments"]),
                r["no_order"], len(r["conditions"]), ",".join(r["flags"]) or "-"))


if __name__ == "__main__":
    main()
