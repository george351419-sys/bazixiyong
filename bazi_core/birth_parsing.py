"""项目内的纯生辰解析与时间校正。

从既有 bazi-paipan/birth_parser.py 提取（2026-11-07）；不导入绘图库。
仅保留日期/时辰解析与既有中国北京时间校正规则；输入裁决由paipan接入层负责。
"""
import re
from datetime import datetime, timedelta

try:
    from lunar_python import Lunar, Solar
except ImportError:
    raise ImportError("需要 lunar-python：pip install -r requirements.txt")


# ============================================================ 中文数字
CN_DIGIT = {'零': 0, '〇': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '两': 2,
            '壹': 1, '贰': 2, '叁': 3, '肆': 4, '伍': 5,
            '陆': 6, '柒': 7, '捌': 8, '玖': 9}


def cn2num(s: str):
    """中文数字 → int。支持 五 / 十 / 十五 / 二十 / 廿三 / 三十 / 一百零八"""
    if not s:
        return None
    if s.isdigit():
        return int(s)
    s = s.strip()
    # 廿/卅/卌 前缀
    if s.startswith('廿'):
        return 20 + (cn2num(s[1:]) or 0) if len(s) > 1 else 20
    if s.startswith('卅'):
        return 30 + (cn2num(s[1:]) or 0) if len(s) > 1 else 30
    # 含「十」
    if '十' in s:
        i = s.index('十')
        tens = cn2num(s[:i]) if s[:i] else 1
        rest = cn2num(s[i + 1:]) if s[i + 1:] else 0
        return tens * 10 + rest if rest is not None else tens * 10
    # 纯数字字符
    if all(c in CN_DIGIT for c in s):
        return int(''.join(str(CN_DIGIT[c]) for c in s))
    return None


# ============================================================ 农历信号
LUNAR_MONTH_ALIAS = {'正月': 1, '一月': 1, '二月': 2, '三月': 3, '四月': 4,
                     '五月': 5, '六月': 6, '七月': 7, '八月': 8, '九月': 9,
                     '十月': 10, '冬月': 11, '十一月': 11, '腊月': 12,
                     '十二月': 12}
# 只出现在农历里的说法
LUNAR_ONLY_WORDS = ['农历', '阴历', '旧历', '闰', '正月', '腊月', '冬月',
                    '初一', '初二', '初三', '初四', '初五', '初六', '初七',
                    '初八', '初九', '初十', '十五', '十六', '十七', '十八',
                    '十九', '二十', '廿', '卅', '三十']


def detect_calendar(text: str) -> tuple:
    """返回 (calendar, confidence, reason)
    calendar: 'solar' | 'lunar' | 'unknown'
    """
    solar_markers=any(w in text for w in ('公历','阳历','新历'))
    lunar_markers=any(w in text for w in ('农历','阴历','旧历'))
    if solar_markers and lunar_markers:
        return 'unknown','low','同时出现公历与农历标记'
    if solar_markers:
        return 'solar','high','显式标注「公历/阳历/新历」'
    hits = [w for w in LUNAR_ONLY_WORDS if w in text]
    if any(w in text for w in ('农历', '阴历', '旧历')):
        return 'lunar', 'high', '显式标注「农历/阴历/旧历」'
    if '闰' in text and re.search(r'闰\s*[一二三四五六七八九十]', text):
        return 'lunar', 'high', '出现「闰X月」，闰月只存在于农历'
    if any(w in text for w in ('正月', '腊月', '冬月')):
        return 'lunar', 'high', '出现「正月/腊月/冬月」，农历专属月名'
    if re.search(r'初[一二三四五六七八九十]', text):
        return 'lunar', 'high', '出现「初X」，农历专属日序'
    if re.search(r'[廿卅]', text):
        return 'lunar', 'mid', '出现「廿/卅」，农历日序用法'
    if re.search(r'[一二三四五六七八九十]{1,3}月[一二三四五六七八九十]{1,3}', text):
        return 'lunar', 'mid', '中文数字月日（如「五月十五」），惯用农历'
    # 阿拉伯数字 → 默认阳历（4 位年置信高；2 位年简写给 mid，建议确认）
    if re.search(r'\d{4}\s*[-年./]\s*\d{1,2}\s*[-月./]\s*\d{1,2}', text):
        return 'solar', 'high', '标准公历格式（4位年 + 阿拉伯数字）'
    if re.search(r'\d{2}\s*[-.]\s*\d{1,2}\s*[-.]\s*\d{1,2}', text):
        return 'solar', 'mid', '阿拉伯数字简写（2位年），按公历理解，建议向用户确认'
    if hits:
        return 'lunar', 'low', '命中农历词：' + '、'.join(hits[:3])
    return 'unknown', 'low', '未检测到明确信号'


# ============================================================ 时辰
# 地支时辰 → (起点小时, 终点小时)。子时跨日，单独处理。
SHICHEN = {'子时': (23, 1), '丑时': (1, 3), '寅时': (3, 5), '卯时': (5, 7),
           '辰时': (7, 9), '巳时': (9, 11), '午时': (11, 13), '未时': (13, 15),
           '申时': (15, 17), '酉时': (17, 19), '戌时': (19, 21), '亥时': (21, 23)}
# 单字时辰（如「辰时」写作「辰」+上下文），风险高，仅在有「时」字或明确语境时用
SHICHEN_1 = {k[0]: v for k, v in SHICHEN.items()}


def parse_hour(text: str) -> tuple:
    """返回 (hour, minute, second, how, day_offset, ambiguous)
    - day_offset：子时取次日 00:00，需要 +1 天
    - ambiguous：子时本身有「早子时/晚子时」歧义，必须提示确认

    地支时辰默认取【时辰中点】——这样真太阳时校正时最不容易被推到相邻时辰。
    """
    if re.search(r'(?:\d[:：]\d[^\u4e00-\u9fff]*Z\b|UTC|GMT|[+-]\d{2}:\d{2})',text,re.I): raise ValueError('不支持显式时区标记，请先转换为北京时间')
    periods=[any(w in text for w in words) for words in [('上午','早上','清晨','凌晨'),('下午','晚上','傍晚','夜里'),('中午',)]]
    if sum(periods)>1: raise ValueError('时段标记互相矛盾')
    names=[k for k in SHICHEN if k in text]
    if len(names)>1: raise ValueError('出生时辰标记互相矛盾')
    if names:
        residual=text.replace(names[0],'')
        precise=parse_hour(residual)
        if precise[0] is not None:
            h=precise[0];start,end=SHICHEN[names[0]]
            inside=(start<=h<end) if start<end else (h>=start or h<end)
            if not inside: raise ValueError('具体钟点与时辰范围矛盾')
            return precise
    # 1) 地支时辰：辰时 / 子时 …
    for name, (s, e) in SHICHEN.items():
        if name in text:
            if name == '子时':
                # 🔴 子时跨日：23:00–01:00，中点是【次日 00:00】
                # 曾在此处踩坑：误算 (23+2)%24=1 → 01:00，而 01:00 已属丑时
                return 0, 0, 0, '子时取中点(次日00:00)', 1, True
            mid = (s + e) / 2
            h = int(mid)
            mi = int(round((mid - h) * 60))
            return h, mi, 0, f'{name}取中点', 0, False
    def normalize_hour(h):
        afternoon=any(w in text for w in ('下午','晚上','傍晚','夜里'))
        morning=any(w in text for w in ('上午','早上','清晨','凌晨'))
        noon='中午' in text
        if any(w in text for w in ('晚上','夜里')) and h==12:
            raise ValueError('晚上12点跨日归属不明确，请提供日期与00:00或23:59等具体钟点')
        if afternoon:
            if h>12: raise ValueError('下午/晚上时刻与24小时制小时数矛盾')
            if h<12: h+=12
        if morning:
            if h>12: raise ValueError('上午/凌晨时刻与24小时制小时数矛盾')
            if h==12: h=0
        if noon and h<11: h+=12
        return h
    # 数字和中文数字共用完整的时、分、秒解析。
    token=r'[0-9零〇一二两三四五六七八九十]{1,3}'
    if re.search(r'\d\s*[:：]\s*\d',text) and re.search(r'[0-9零〇一二三四五六七八九十两]+\s*[点时]',text): raise ValueError('请提供唯一出生钟点')
    clock_tokens=re.findall(r'(?<![0-9])[0-9]+\s*[:：][0-9:：.\s]*',text)
    if clock_tokens:
        if len(clock_tokens)!=1: raise ValueError('请提供唯一出生钟点')
        m=re.fullmatch(r'(\d{1,2})\s*[:：]\s*(\d{2})(?:\s*[:：]\s*(\d{2}))?',clock_tokens[0].strip())
        if not m: raise ValueError('时间格式无效，需时:分或时:分:秒')
        return normalize_hour(int(m[1])),int(m[2]),int(m[3] or 0),'明确钟点(时分秒)',0,False
    if len(re.findall(r'('+token+r')\s*[点时]',text))>1: raise ValueError('请提供唯一出生钟点')
    m=re.search(r'('+token+r')\s*[点时](?:\s*(半)|\s*('+token+r')\s*分(?:\s*('+token+r')\s*秒)?)?',text)
    if m:
        tail=text[m.end():]
        if re.match(r'\s*[0-9一二三四五六七八九十半分秒]',tail):
            raise ValueError('时间未完整识别，请使用时:分:秒格式')
        return normalize_hour(cn2num(m[1])),30 if m[2] else cn2num(m[3]) or 0,cn2num(m[4]) or 0,'明确钟点',0,False
    return None, None, None, '未识别', 0, False


# ============================================================ 年月日
def parse_ymd(text: str) -> tuple:
    """返回 (year, month, day, is_leap, note)"""
    is_leap = False
    note = []

    # 闰月
    lm = re.search(r'闰\s*(正|冬|腊|[一二三四五六七八九十]{1,3}|\d{1,2})\s*月', text)
    if lm:
        is_leap = True
        note.append('闰月')

    # ---- 先定位年份，并把年份从文本中移除，避免干扰月日匹配 ----
    # 典型坑：'90.5.15' 中的 '90.5' 会被月日正则误当成「90月5日」
    year = None
    ym = re.search(r'(?<!\d)\d{4}(?!\d)', text)
    if ym:
        year = int(ym.group(0))
        text_md = text[:ym.start()] + ' ' + text[ym.end():]
    else:
        ym = re.search(r'[一二三四五六七八九〇零]{2,4}\s*年', text)
        if ym:
            digits = ''.join(str(CN_DIGIT.get(c, '')) for c in ym.group(0) if c in CN_DIGIT)
            if len(digits) == 4:
                year = int(digits)
            elif len(digits) == 2:
                year = 1900 + int(digits)
            text_md = text[:ym.start()] + ' ' + text[ym.end():]
        else:
            # ⚠️ 不能用 \b：中文字符两侧 \b 行为不可靠（"我是90年" 中 \b 不匹配）
            ym = re.search(r'(?<!\d)(\d{2})\s*年', text)
            if ym:
                y2 = int(ym.group(1))
                year = 1900 + y2 if y2 >= 30 else 2000 + y2
                text_md = text[:ym.start()] + ' ' + text[ym.end():]
            else:
                text_md = text

    # ---- 月日（在已剔除年份的文本上匹配）----
    month = day = None
    # A) 阿拉伯数字 5-15 / 5.15 / 5月15
    m = re.search(r'(?<!\d)(\d+)\s*[-月./]\s*(\d+)(?!\d)', text_md)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        month, day = a, b
    else:
        # B) 中文月名：五月/腊月/闰五月
        m = re.search(r'(闰)?(正月|腊月|冬月|[一二三四五六七八九十]{1,2}月)\s*'
                      r'(初?[一二三四五六七八九十廿卅]{1,4})(?![一二三四五六七八九十廿卅])', text_md)
        if m:
            mon_s, day_s = m.group(2), m.group(3)
            is_leap=is_leap or bool(m.group(1))
            month = LUNAR_MONTH_ALIAS.get(mon_s)
            if month is None:
                month = cn2num(mon_s.replace('月', ''))
            if day_s.startswith('初'):
                day = cn2num(day_s[1:])
            elif day_s.startswith('廿'):
                day = 20 + (cn2num(day_s[1:]) or 0)
            elif day_s.startswith('卅'):
                day = 30 + (cn2num(day_s[1:]) or 0)
            else:
                day = cn2num(day_s)
        else:
            # C) 中文数字月+日：五月十五
            m = re.search(r'([一二三四五六七八九十]{1,2})月\s*'
                          r'([一二三四五六七八九十]{1,3})', text_md)
            if m:
                month = cn2num(m.group(1))
                day = cn2num(m.group(2))

    return year, month, day, is_leap, note


# ============================================================ 农历 → 公历
def lunar_to_solar(y: int, m: int, d: int, is_leap: bool = False,
                   hour: int = 0, minute: int = 0):
    """农历 → 公历。闰月用负数月份（lunar-python 约定）。"""
    lm = -m if is_leap else m
    lunar = Lunar.fromYmdHms(y, lm, d, hour, minute, 0)
    solar = lunar.getSolar()
    return solar


# ============================================================ 真太阳时
def true_solar_time(dt: datetime, lon: float, with_eot: bool = False) -> tuple:
    """真太阳时校正。
    公式：真太阳时 = 北京时间 + (出生地经度 − 120°) × 4 分钟 [+ 均时差]

    关于均时差（Equation of Time）：
      实测对照 bazi-engine（2026-09-12）：天津 6:00→5:48、乌鲁木齐 6:00→3:50，
      与「只算经度差」完全吻合，说明主流排盘软件**不含均时差**。
      所以默认 with_eot=False（与主流一致、可对账）；需要天文精度时再开。
    """
    offset_min = (lon - 120.0) * 4.0
    if with_eot:
        # 均时差近似（精度约 ±0.5 分钟）
        import math
        n = dt.timetuple().tm_yday
        b = 2 * math.pi * (n - 81) / 364.0
        eot = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    else:
        eot = 0.0
    total = offset_min + eot
    return dt + timedelta(minutes=total), total


# 中国 1986-1991 夏令时区间（用于回拨）
# 参考：1986-05-04 至 1991-09-15 期间每年 4 月中旬至 9 月中旬实行
DST_RANGES = [
    ('1986-05-04', '1986-09-14'), ('1987-04-12', '1987-09-13'),
    ('1988-04-10', '1988-09-11'), ('1989-04-16', '1989-09-17'),
    ('1990-04-15', '1990-09-16'), ('1991-04-14', '1991-09-15'),
]


def apply_dst(dt: datetime) -> tuple:
    """夏令时回拨 1 小时。返回 (new_dt, applied)"""
    if not 1986<=dt.year<=1991: return dt,False
    from zoneinfo import ZoneInfo
    zone=ZoneInfo('Asia/Shanghai')
    options=[]
    for fold in (0,1):
        aware=dt.replace(tzinfo=zone,fold=fold)
        from datetime import timezone
        back=aware.astimezone(timezone.utc).astimezone(zone)
        if back.replace(tzinfo=None)==dt:
            offset=aware.utcoffset()
            if offset not in options: options.append(offset)
    if not options: raise ValueError('该钟点处于夏令时跳时空档')
    if len(options)>1: raise ValueError('该钟点在夏令时转换时重复，请明确标准时刻')
    correction=options[0]-timedelta(hours=8)
    return dt-correction,correction!=timedelta(0)
