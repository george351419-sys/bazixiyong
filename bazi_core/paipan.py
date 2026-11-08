# -*- coding: utf-8 -*-
"""排盘接入层：项目内纯历法后端，桥接到旺衰 / 格局 / 调候引擎。

职责：
  - 自然语言、公历、农历、地方时间校正统一经lunar_python排盘；
  - 把排盘结果（四柱干支）转换成 PRD 输入 JSON
    {'year':{'gan','zhi'}, 'month':{...}, 'day':{...}, 'hour':{...}}；
  - 月令起点getPrevJie()用于天数/司令参考；getPrevJieQi()用于含中气的实际调候区间。

依赖：requirements.txt中的lunar_python；兼容旧目录中的纯历法包。不导入绘图库。
时间沿用北京时间口径，校正开关显式记录；缺时辰/子时歧义不生成占位命盘。
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime

# 项目自带依赖目录（lunar_python）
_VENDOR_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".vendor")
if os.path.isdir(_VENDOR_DIR) and _VENDOR_DIR not in sys.path:
    # 只在缺少已安装的纯历法包时兼容旧目录，不覆盖正常环境中的包。
    try:
        import lunar_python
    except ImportError:
        sys.path.append(_VENDOR_DIR)

# 既有排盘 skill 脚本目录（可被子类/环境变量覆盖）
DEFAULT_SKILL_DIR = os.environ.get(
    "BAZI_PAIPAN_SKILL_DIR",
    "",
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


def _run_external_paipan(birth=None, y=None, m=None, d=None, h=None, minute=0, second=0,
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
    if second or (isinstance(birth,str) and re.search(r'(?:\d{1,2}:\d{2}:\d{2}|\d{1,2}[点时]\d{1,2}分\d{1,2}秒)',birth)):
        return {"ok":False,"error":"外部排盘适配器不支持秒精度；请使用项目内默认排盘后端"}
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


def run_paipan(birth=None, y=None, m=None, d=None, h=None, minute=0,
               sex='male', name='', city='', lon=None, calendar=None,
               lunar=False, leap=False, truesun=False, eot=False, sect=None,
               skill_dir=None, second=0, time_basis=None):
    """默认使用项目内纯历法后端；仅显式配置时调用旧外部适配器。

    time_basis 可显式选择 china_civil（历史民用钟表时，独立归一夏令时）或
    china_standard（UTC+8 标准时）。不传时保留既有兼容口径：truesun 为真用
    civil，否则用 standard；输出时间输入口径供复核。sect 不改写出生日期。
    """
    from .input_contracts import integer, boolean, finite_number
    try:
        for key,value in [('lunar',lunar),('leap',leap),('truesun',truesun),('eot',eot)]: boolean(value,key)
        if time_basis not in (None,'china_civil','china_standard'): raise ValueError('time_basis需为china_civil或china_standard')
        if sex not in ('male','female'): raise ValueError('sex需为male或female')
        if sect is not None: sect=integer(sect,'sect',1,2)
        if lon is not None: lon=finite_number(lon,'lon',-180,180)
        if eot and (not truesun or lon is None): raise ValueError('eot需要truesun与经度')
        if calendar not in (None,'solar','lunar'): raise ValueError('calendar需为solar或lunar')
        if lunar and calendar=='solar': raise ValueError('lunar与calendar历法参数矛盾')
        if (skill_dir or DEFAULT_SKILL_DIR) and time_basis is not None: raise ValueError('外部排盘适配器尚不支持显式time_basis，请使用项目内历法后端')
        if skill_dir or DEFAULT_SKILL_DIR:
            return _run_external_paipan(birth,y,m,d,h,minute,second,sex,name,city,lon,calendar,
                                        lunar,leap,truesun,eot,sect,skill_dir)
        from lunar_python import Solar,Lunar
        from .birth_parsing import parse_ymd,parse_hour,detect_calendar,apply_dst,true_solar_time
        warnings=[];trace=[];hour_source='明确钟点'
        if birth:
            if not isinstance(birth,str): raise ValueError('birth需为字符串')
            if any(v is not None for v in (y,m,d,h)): raise ValueError('birth与年月日时参数不可同时提供')
            detected,confidence,reason=detect_calendar(birth)
            if detected=='unknown' and ('公历' in birth or '阳历' in birth or '新历' in birth) and ('农历' in birth or '阴历' in birth or '旧历' in birth):
                raise ValueError(reason)
            explicit_marker=detected in ('solar','lunar') and confidence=='high'
            requested=calendar if calendar is not None else ('lunar' if lunar else 'solar')
            if explicit_marker and (calendar is not None or lunar) and requested!=detected:
                raise ValueError('文本历法标记与历法参数矛盾')
            cal=calendar or ('lunar' if lunar else detected)
            if cal=='unknown' or (calendar is None and not lunar and confidence=='low'):
                return dict(ok=False,error='历法不确定，请明确公历或农历',need_confirm=True)
            y,m,d,parsed_leap,note=parse_ymd(birth)
            leap=leap or parsed_leap
            h,minute,second,hour_source,day_offset,ambiguous=parse_hour(birth)
            if h is None: return dict(ok=False,error='缺少出生时辰，不能用占位时辰分析',need_confirm=True)
            if ambiguous: return dict(ok=False,error='子时跨日不明确，请提供具体日期与钟点',need_confirm=True)
            trace.extend([reason,hour_source])
        else:
            cal=calendar or ('lunar' if lunar else 'solar');day_offset=0
        if leap and cal!='lunar': raise ValueError('闰月仅用于农历')
        y=integer(y,'y',1,9998);m=integer(m,'m',1,12);d=integer(d,'d',1,31)
        h=integer(h,'h',0,23);minute=integer(minute,'minute',0,59);second=integer(second,'second',0,59)
        if cal=='lunar':
            solar=Lunar.fromYmdHms(y,-m if leap else m,d,h,minute,second).getSolar()
            dt=datetime(solar.getYear(),solar.getMonth(),solar.getDay(),h,minute,second)
        else: dt=datetime(y,m,d,h,minute,second)
        if day_offset:
            from datetime import timedelta
            dt+=timedelta(days=day_offset)
        interval_meta=None
        if birth and '取中点' in hour_source:
            from .birth_parsing import SHICHEN
            from datetime import timedelta
            shichen=next(k for k in SHICHEN if k in birth)
            start_hour,end_hour=SHICHEN[shichen]
            start=dt.replace(hour=start_hour,minute=0,second=0)
            end=start+timedelta(hours=2)-timedelta(seconds=1)
            candidates=[]
            for bound in (start,end):
                candidate=run_paipan(y=bound.year,m=bound.month,d=bound.day,h=bound.hour,
                    minute=bound.minute,second=bound.second,sex=sex,lon=lon,truesun=truesun,eot=eot,sect=sect,time_basis=time_basis)
                if not candidate.get('ok'): return candidate
                candidates.append(candidate)
            signatures=[(c['八字'],auto_solar_term_day(c['节气参考公历']),c['夏令时回拨']) for c in candidates]
            # 同柱仍可能跨中气，调候分段也必须一致。
            term=lambda x:((x[1] or {}).get('current_jieqi_time'),(x[1] or {}).get('day'))
            interval_meta=dict(start=start.isoformat(' '),end=end.isoformat(' '),source=shichen)
            if any(x[1] is None for x in signatures) or signatures[0][0]!=signatures[1][0] or term(signatures[0])!=term(signatures[1]) or signatures[0][2]!=signatures[1][2]:
                return dict(ok=False,error='出生时间区间跨命盘、节气或节后天数边界，请补充具体钟点',need_confirm=True,
                    time_interval=interval_meta,candidate_pillars=[c['八字'] for c in candidates],
                    candidate_solar_term_info=[x[1] for x in signatures])
        civil=dt;dst=False;offset=None
        standard_time=dt
        resolved_basis=time_basis or ('china_civil' if truesun else 'china_standard')
        if resolved_basis=='china_civil': standard_time,dst=apply_dst(dt)
        dt=standard_time
        if truesun:
            if lon is not None: dt,offset=true_solar_time(dt,lon,eot)
            else: warnings.append('未提供经度，未做经度时差校正')
        standard_solar=Solar.fromYmdHms(standard_time.year,standard_time.month,standard_time.day,standard_time.hour,standard_time.minute,standard_time.second)
        corrected_solar=Solar.fromYmdHms(dt.year,dt.month,dt.day,dt.hour,dt.minute,dt.second)
        standard_ec=standard_solar.getLunar().getEightChar();standard_ec.setSect(sect or 2)
        corrected_ec=corrected_solar.getLunar().getEightChar();corrected_ec.setSect(sect or 2)
        # 年柱、月柱以北京时间（含历史夏令时归一后）对照节气历表；
        # 真太阳时仅校正日、时柱，避免经度把钟表时刻与固定节气表错位比较。
        pillars=[standard_ec.getYear(),standard_ec.getMonth(),corrected_ec.getDay(),corrected_ec.getTime()]
        return dict(ok=True,八字=pillars,日主=pillars[2][0],性别=sex,姓名=name,出生地=city,
            公历=corrected_solar.toYmdHms(),节气参考公历=standard_solar.toYmdHms(),
            农历=corrected_solar.getLunar().toString(),生肖=corrected_solar.getLunar().getYearShengXiao(),
            时间输入口径=resolved_basis,原始公历=civil.isoformat(' '),历法='农历' if cal=='lunar' else '公历',
            时辰来源=hour_source,真太阳时校正分钟=round(offset,1) if offset is not None else None,
            夏令时回拨=dst,晚子时流派=sect or 2,backend='project_lunar_python',
            hour_stem_day_offset=1 if dt.hour==23 and (sect or 2)==2 else 0,
            time_interval=interval_meta,representative_time=interval_meta is not None,
            time_convention='年/月柱按北京时间节气历表；真太阳时只校正日/时柱；sect不改写物理时刻',warnings=warnings,trace=trace)
    except (ValueError,TypeError,ImportError,OverflowError) as exc:
        return dict(ok=False,error=str(exc),stage='paipan')


def paipan_to_chart(r, solar_term_day=None):
    """把排盘结果转换为 PRD 输入 JSON（PRD 1.1 格式）。

    入参 r：bazi_paipan 返回的 dict（至少含 八字 或 四柱）。
    solar_term_day：节气后第几天，仅供司令参考与调候近似分段，不参与取格。
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
    chart['hour_stem_day_offset']=r.get('hour_stem_day_offset',0)
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
        current = lunar.getPrevJieQi()
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
                "jie_time": jie_solar.toYmdHms(), "exact_days": round(days, 3),
                "current_jieqi_name": current.getName(),
                "current_jieqi_time": current.getSolar().toYmdHms()}
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
        "节气参考公历": r.get("节气参考公历"),
        "农历": r.get("农历"),
        "生肖": r.get("生肖"),
        "真太阳时校正分钟": r.get("真太阳时校正分钟"),
        "夏令时回拨": r.get("夏令时回拨"),
        "历法": r.get("历法"),
        "时辰来源": r.get("时辰来源"),
        "晚子时流派": r.get("晚子时流派"),
        "原始公历": r.get("原始公历"),
        "backend": r.get("backend"),
        "time_interval": r.get("time_interval"),
        "representative_time": r.get("representative_time",False),
        "time_convention": r.get("time_convention"),
    }


def analyze_birth(birth=None, y=None, m=None, d=None, h=None, minute=0,
                  sex="male", lon=None, truesun=True, lunar=False, leap=False,
                  calendar=None, config=None, skill_dir=None, solar_term_day=None,
                  tiaohou_segment=None, sect=None, eot=False, second=0, time_basis=None):
    """端到端：生辰 → 排盘 → 旺衰 + 格局 + 调候（含人元司令分段的节气天数）。

    solar_term_day：可手工指定「节气后第几天」；未指定时自动用 lunar_python 推算。
    tiaohou_segment：显式节气分段（调候分段格用），不传则由节气名／天数推断。
    返回 engine.analyze 的结构化结果（含 paipan_meta / solar_term_info）。
    若排盘失败，返回 {'ok': False, 'error': ...}。
    """
    from .engine import analyze
    from .input_contracts import integer

    if solar_term_day is not None:
        try: solar_term_day=integer(solar_term_day,'solar_term_day',0,40)
        except ValueError as exc: return dict(ok=False,error=str(exc),stage='input')

    r = run_paipan(birth=birth, y=y, m=m, d=d, h=h, minute=minute, second=second, sex=sex,
                   lon=lon, lunar=lunar, leap=leap, truesun=truesun,
                   calendar=calendar, skill_dir=skill_dir,sect=sect,eot=eot,time_basis=time_basis)
    if not r.get("ok", True):
        return dict(r,ok=False,stage="paipan")

    # 实际节气事实始终保留；手工天数仅覆盖司令参考输入。
    solar_term_info=auto_solar_term_day(r.get("节气参考公历") or r.get("公历"))
    solar_term_source='auto' if solar_term_info else 'unavailable'
    selected_day=solar_term_day if solar_term_day is not None else (solar_term_info or {}).get('day')
    solar_term_override=None
    if solar_term_day is not None:
        solar_term_override=dict(requested_day=solar_term_day,actual_day=(solar_term_info or {}).get('day'),
            conflict=solar_term_info is not None and solar_term_day!=solar_term_info['day'],scope='siling_reference_only')
        solar_term_source='manual_with_actual' if solar_term_info else 'manual'
    try:
        chart = paipan_to_chart(r, solar_term_day=(
            selected_day))
    except Exception as e:
        return {"ok": False, "error": "排盘桥接失败：%s" % e, "stage": "bridge"}

    # 调候消费实际节气区间；格局仅将节气天数用于司令参考，不据此取格。
    if solar_term_info:
        chart["jie_name"] = solar_term_info.get("jie_name")
        chart["solar_term_info"] = solar_term_info

    chart['input_kind']='real_chart'
    try: out = analyze(chart, config=config, tiaohou_segment=tiaohou_segment)
    except ValueError as exc: return dict(ok=False,error=str(exc),stage='analysis_input')
    out["ok"] = True
    out["paipan_meta"] = paipan_meta(r)
    out["solar_term_info"] = solar_term_info
    out["solar_term_source"] = solar_term_source
    out["solar_term_override"] = solar_term_override
    out["input"] = chart
    out['paipan_warnings']=list(r.get('warnings',[]))
    if solar_term_override and solar_term_override['conflict']:
        out['paipan_warnings'].append('手工节后天数与实际历法不一致；仅覆盖司令参考，调候仍按实际节气')
    return out
