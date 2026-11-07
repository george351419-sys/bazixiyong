# -*- coding: utf-8 -*-
"""排盘接入层：复用既有 bazi-paipan skill，桥接到旺衰 / 格局 / 调候引擎。

职责：
  - 把自然语言 / 公历 / 农历 / 真太阳时生辰，交给 bazi-paipan 排盘；
  - 把排盘结果（四柱干支）转换成 PRD 输入 JSON
    {'year':{'gan','zhi'}, 'month':{...}, 'day':{...}, 'hour':{...}}；
  - 自动推算「节气后第几天」（人元司令取格所需，格局 PRD §2.2 / 模式A），
    用 lunar_python 的 Lunar.getPrevJie() 精确到时刻；算不出时优雅降级为 None。

复用约定（yan 拍板）：排盘用既有 skill，启用真太阳时（truesun=True + 出生地经度）。
依赖：lunar_python 随项目自带于 .vendor/（1MB，不污染全局 Python）。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

# 项目自带依赖目录（lunar_python）
_VENDOR_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".vendor")
if os.path.isdir(_VENDOR_DIR) and _VENDOR_DIR not in sys.path:
    sys.path.insert(0, _VENDOR_DIR)

# 既有排盘 skill 脚本目录（可被子类/环境变量覆盖）
DEFAULT_SKILL_DIR = os.environ.get(
    "BAZI_PAIPAN_SKILL_DIR",
    "/Users/bessie/.workbuddy/skills/bazi-paipan/scripts",
)

# 十二「节」（非中气）：月令由此划分
JIE_BY_ZHI = {
    "寅": "立春", "卯": "惊蛰", "辰": "清明", "巳": "立夏", "午": "芒种", "未": "小暑",
    "申": "立秋", "酉": "白露", "戌": "寒露", "亥": "立冬", "子": "大雪", "丑": "小寒",
}


def _ensure_skill_importable(skill_dir=None):
    """把排盘 skill 脚本目录注入 sys.path；返回目录或 None（不可用时）。"""
    skill_dir = skill_dir or DEFAULT_SKILL_DIR
    if skill_dir and os.path.isdir(skill_dir) and skill_dir not in sys.path:
        sys.path.insert(0, skill_dir)
    return skill_dir if (skill_dir and os.path.isdir(skill_dir)) else None


def run_paipan(birth=None, y=None, m=None, d=None, h=None, minute=0,
               sex="male", name="", city="", lon=None, calendar=None,
               lunar=False, leap=False, truesun=False, eot=False, sect=None,
               skill_dir=None):
    """调用 bazi-paipan 排盘，返回原始排盘 dict。

    参数与 bazi_paipan.quick_paipan 对齐；truesun=True 时建议同时给 lon。
    失败返回 {'ok': False, 'error': ...}。
    """
    skill_dir = _ensure_skill_importable(skill_dir)
    if not skill_dir:
        return {"ok": False, "error": "未找到排盘 skill 目录：%s" % (skill_dir or DEFAULT_SKILL_DIR)}
    try:
        from bazi_paipan import quick_paipan
    except Exception as e:  # 缺 lunar_python 等依赖
        return {"ok": False, "error": "导入排盘模块失败：%s" % e}

    try:
        r = quick_paipan(birth=birth, y=y, m=m, d=d, h=h, minute=minute,
                         sex=sex, name=name, city=city, lon=lon, calendar=calendar,
                         lunar=lunar, leap=leap, truesun=truesun, eot=eot,
                         sect=sect, render=False)
    except Exception as e:
        return {"ok": False, "error": "排盘执行异常：%s" % e}
    return r


def paipan_to_chart(r, solar_term_day=None):
    """把排盘结果转换为 PRD 输入 JSON（PRD 1.1 格式）。

    入参 r：bazi_paipan 返回的 dict（至少含 八字 或 四柱）。
    solar_term_day：节气后第几天，非 None 时写入 chart 供人元司令取格。
    """
    order = ["year", "month", "day", "hour"]
    if "八字" in r and r["八字"]:
        gz_list = r["八字"]
    elif "四柱" in r and r["四柱"]:
        gz_list = [p["干支"] for p in r["四柱"]]
    else:
        raise ValueError("排盘结果缺少 八字 / 四柱 字段，无法桥接")

    chart = {}
    for i, gz in enumerate(gz_list):
        gan, zhi = gz[0], gz[1]
        chart[order[i]] = {"gan": gan, "zhi": zhi}
    if solar_term_day is None:
        solar_term_day = r.get("节气后第几天", r.get("solar_term_day"))
    if solar_term_day is not None:
        chart["solar_term_day"] = int(solar_term_day)
    return chart


def auto_solar_term_day(gregorian_str):
    """由排盘结果中的「公历」时间，推算出生时刻距上一个「节」的天数。

    返回 dict 或 None（依赖缺失 / 格式异常时优雅降级）：
      {'day': int, 'jie_name': str, 'jie_time': str, 'exact_days': float}
    day 为向下取整的整数，与格局 PRD §2.2 分段（0–7、7–14…）语义一致。
    """
    if not gregorian_str:
        return None
    try:
        from lunar_python import Solar
        s = str(gregorian_str).strip().replace("T", " ")
        bdt = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                bdt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        if bdt is None:
            return None
        solar = Solar.fromYmdHms(bdt.year, bdt.month, bdt.day,
                                 bdt.hour, bdt.minute, bdt.second)
        lunar = solar.getLunar()
        jie = lunar.getPrevJie()
        jie_solar = jie.getSolar()
        jdt = datetime.strptime(jie_solar.toYmdHms(), "%Y-%m-%d %H:%M:%S")
        days = (bdt - jdt).total_seconds() / 86400.0
        if days < 0 or days > 40:      # 异常保护：一个节到下一个节约 30 天
            return None
        # 校验：该节确实对应排出的月支（防止跨年表错位）
        expect = JIE_BY_ZHI.get(lunar.getMonthZhiExact())
        if expect and jie.getName() != expect:
            return None
        return {"day": int(days), "jie_name": jie.getName(),
                "jie_time": jie_solar.toYmdHms(), "exact_days": round(days, 3)}
    except Exception:
        return None


def paipan_meta(r):
    """抽取给前端展示用的排盘元信息（不影响旺衰计算）。"""
    if not isinstance(r, dict):
        return {}
    return {
        "八字": " ".join(r.get("八字", [])),
        "日主": r.get("日主"),
        "性别": r.get("性别"),
        "公历": r.get("公历"),
        "农历": r.get("农历"),
        "生肖": r.get("生肖"),
        "真太阳时校正分钟": r.get("真太阳时校正分钟"),
        "夏令时回拨": r.get("夏令时回拨"),
        "历法": r.get("历法"),
        "时辰来源": r.get("时辰来源"),
    }


def analyze_birth(birth=None, y=None, m=None, d=None, h=None, minute=0,
                  sex="male", lon=None, truesun=True, lunar=False, leap=False,
                  calendar=None, config=None, skill_dir=None, solar_term_day=None,
                  tiaohou_segment=None):
    """端到端：生辰 → 排盘 → 旺衰 + 格局 + 调候（含人元司令分段的节气天数）。

    solar_term_day：可手工指定「节气后第几天」；未指定时自动用 lunar_python 推算。
    tiaohou_segment：显式节气分段（调候分段格用），不传则由节气名／天数推断。
    返回 engine.analyze 的结构化结果（含 paipan_meta / solar_term_info）。
    若排盘失败，返回 {'ok': False, 'error': ...}。
    """
    from .engine import analyze

    r = run_paipan(birth=birth, y=y, m=m, d=d, h=h, minute=minute, sex=sex,
                   lon=lon, lunar=lunar, leap=leap, truesun=truesun,
                   calendar=calendar, skill_dir=skill_dir)
    if not r.get("ok", True):
        return {"ok": False, "error": r.get("error"), "stage": "paipan"}

    # 节气后天数：手工指定优先，否则自动推算（失败则降级，司令表按兜底口径取格）
    solar_term_info = None
    if solar_term_day is not None:
        solar_term_source = "manual"
        solar_term_info = {"day": int(solar_term_day), "jie_name": None,
                           "jie_time": None, "exact_days": None}
    else:
        solar_term_info = auto_solar_term_day(r.get("公历"))
        solar_term_source = "auto" if solar_term_info else "unavailable"

    try:
        chart = paipan_to_chart(r, solar_term_day=(
            solar_term_info["day"] if solar_term_info else None))
    except Exception as e:
        return {"ok": False, "error": "排盘桥接失败：%s" % e, "stage": "bridge"}

    # 调候分段需要节气名／节气后天数；这两个是辅助字段，旺衰与格局模块不读取。
    if solar_term_info:
        chart["jie_name"] = solar_term_info.get("jie_name")
        chart["solar_term_info"] = solar_term_info

    out = analyze(chart, config=config, tiaohou_segment=tiaohou_segment)
    out["ok"] = True
    out["paipan_meta"] = paipan_meta(r)
    out["solar_term_info"] = solar_term_info
    out["solar_term_source"] = solar_term_source
    out["input"] = chart
    return out
