# -*- coding: utf-8 -*-
"""前置规则0：干支基础元数据字典（开发内置常量表，只读）。

覆盖 PRD 第二节全部要点：
  1. 干支五行、十神表
  2. 地支藏干表（本气/中气/余气）、地支关系表（冲/刑/六合/三合/三会）
  3. 日主根类型表（强根：禄/刃/长生；微根：墓库余气根；次强根：开库升级档）
  4. 地支基础能量（单支总和=100）
  5. 距离衰减系数（日支1.0；月支、时支0.9；年支0.8）

以及派生：十二长生（禄/刃/长生支）、四库开库对照表（2.1）。
"""
from __future__ import annotations

# ============================ 天干 / 地支 ============================
GAN = "甲乙丙丁戊己庚辛壬癸"          # 十天干
ZHI = "子丑寅卯辰巳午未申酉戌亥"       # 十二地支
GAN_LIST = list(GAN)
ZHI_LIST = list(ZHI)

# 天干五行
WUXING_GAN = {}
for _g, _w in {"甲乙": "木", "丙丁": "火", "戊己": "土",
               "庚辛": "金", "壬癸": "水"}.items():
    for _c in _g:
        WUXING_GAN[_c] = _w

# 地支五行（本气五行）
WUXING_ZHI = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
              "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"}

# 五行生克
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}   # 我生
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}       # 我克（KE[X] = X 所克）
KE_OF = {v: k for k, v in KE.items()}                                  # 克 X 者（KE_OF[X] = 克 X 的五行）
WUXING_LIST = ["木", "火", "土", "金", "水"]

# ============================ 十神 ============================
def shishen(day_gan: str, other_gan: str) -> str:
    """以 day_gan 为日主，other_gan 为某干，返回十神名。"""
    if day_gan == other_gan:
        return "比肩"
    dw = WUXING_GAN[day_gan]
    ow = WUXING_GAN[other_gan]
    same_yin = ((GAN_LIST.index(day_gan) % 2) == (GAN_LIST.index(other_gan) % 2))
    if dw == ow:                       # 同五行
        return "比肩" if same_yin else "劫财"
    if SHENG[dw] == ow:                # 我生
        return "食神" if same_yin else "伤官"
    if SHENG[ow] == dw:                # 生我
        return "偏印" if same_yin else "正印"
    if KE[ow] == dw:                   # 克我
        return "七杀" if same_yin else "正官"
    if KE[dw] == ow:                   # 我克
        return "偏财" if same_yin else "正财"
    return "?"

# ============================ 地支藏干（本气/中气/余气） ============================
# 顺序严格为 [本气, 中气, 余气]；不足三项的按实际项数。
ZHI_HIDE = {
    "子": ["癸"],
    "丑": ["己", "癸", "辛"],
    "寅": ["甲", "丙", "戊"],
    "卯": ["乙"],
    "辰": ["戊", "乙", "癸"],
    "巳": ["丙", "戊", "庚"],
    "午": ["丁", "己"],
    "未": ["己", "丁", "乙"],
    "申": ["庚", "壬", "戊"],
    "酉": ["辛"],
    "戌": ["戊", "辛", "丁"],
    "亥": ["壬", "甲"],
}

# 每个藏干对应的五行
def _hide_wuxing(zhi: str):
    return [WUXING_GAN[g] for g in ZHI_HIDE[zhi]]

# 地支基础能量档（单支总和=100），按藏干项数自动判定：
#   独气支（1项：子/卯/酉）：本气 100
#   双藏  （2项：午/亥）：本气 70，余气 30
#   三藏  （3项：丑/寅/辰/巳/未/申/戌）：本气 60，中气 30，余气 10
def zhi_tier_energy(zhi: str):
    n = len(ZHI_HIDE[zhi])
    if n == 1:
        return [100]
    if n == 2:
        return [70, 30]
    return [60, 30, 10]

# ============================ 地支关系 ============================
# 六冲（本气相冲）
CHONG = {
    "子": "午", "午": "子", "丑": "未", "未": "丑",
    "寅": "申", "申": "寅", "卯": "酉", "酉": "卯",
    "辰": "戌", "戌": "辰", "巳": "亥", "亥": "巳",
}

# 三会局：会局五行，成员地支，本气旺支（月令必须在此集合内才成会）
SANHUI = [
    {"wx": "木", "members": ["寅", "卯", "辰"], "wang": ["寅", "卯"]},
    {"wx": "火", "members": ["巳", "午", "未"], "wang": ["巳", "午"]},
    {"wx": "金", "members": ["申", "酉", "戌"], "wang": ["申", "酉"]},
    {"wx": "水", "members": ["亥", "子", "丑"], "wang": ["亥", "子"]},
]

# 三合局：化神五行，成员地支，中神（月令必须=中神才成合）
SANHE = [
    {"wx": "水", "members": ["申", "子", "辰"], "zhong": "子"},
    {"wx": "木", "members": ["亥", "卯", "未"], "zhong": "卯"},
    {"wx": "火", "members": ["寅", "午", "戌"], "zhong": "午"},
    {"wx": "金", "members": ["巳", "酉", "丑"], "zhong": "酉"},
]

# 天干五合：(干1, 干2) -> 化神五行
WUHE = {
    frozenset(("甲", "己")): "土",
    frozenset(("乙", "庚")): "金",
    frozenset(("丙", "辛")): "水",
    frozenset(("丁", "壬")): "木",
    frozenset(("戊", "癸")): "火",
}

# 地支六合：(支1, 支2) -> 化神五行
LIUHE = {
    frozenset(("子", "丑")): "土",
    frozenset(("寅", "亥")): "木",
    frozenset(("卯", "戌")): "火",
    frozenset(("辰", "酉")): "金",
    frozenset(("巳", "申")): "水",
    frozenset(("午", "未")): "土",
}

# 自刑（四库自刑）；地支相刑（寅巳申无恩、丑戌未恃势、子卯无礼）—— 用于可选开库开关
ZI_XING = {"辰", "未", "戌", "丑"}   # 辰辰/未未/戌戌/丑丑
XING = [
    {"members": ["寅", "巳", "申"]},   # 无恩之刑
    {"members": ["丑", "戌", "未"]},   # 恃势之刑
    {"members": ["子", "卯"]},         # 无礼之刑
]

# 月令化神旺地（五合/六合化神得令的月支五行）。化神需落在「当旺」月令。
#   甲己化土 -> 土令（辰戌丑未）
#   乙庚合金 -> 金令（申酉）
#   丙辛合水 -> 水令（亥子）
#   丁壬合木 -> 木令（寅卯）
#   戊癸合火 -> 火令（巳午）
#   六合同理（子丑合土、午未合土 -> 土令；寅亥合木 -> 木令；卯戌合火 -> 火令；
#            辰酉合金 -> 金令；巳申合水 -> 水令）
HE_HUA_WANG_MONTH = {
    "土": {"辰", "戌", "丑", "未"},
    "金": {"申", "酉"},
    "水": {"亥", "子"},
    "木": {"寅", "卯"},
    "火": {"巳", "午"},
}

# ============================ 十二长生（禄/刃/长生支） ============================
# 土随火。返回各五行对应的地支。
LU = {"木": "寅", "火": "巳", "土": "巳", "金": "申", "水": "亥"}          # 临官（禄）
REN = {"木": "卯", "火": "午", "土": "午", "金": "酉", "水": "子"}         # 帝旺（刃）
CHANGSHENG = {"木": "亥", "火": "寅", "土": "寅", "金": "巳", "水": "申"}  # 长生（五行长生，旧体系，仅合化化神得根气兼容保留）

# 十干级禄/刃/帝旺（V1.2）。五行级 LU/REN 会把「辛酉」标成刃（实为禄）、
# 「癸子」标成刃（实为禄），故根类型标注一律走下面这套。
TEN_GAN_LU = {
    "甲": "寅", "乙": "卯", "丙": "巳", "丁": "午", "戊": "巳", "己": "午",
    "庚": "申", "辛": "酉", "壬": "亥", "癸": "子",
}
YANG_REN = {"甲": "卯", "丙": "午", "戊": "午", "庚": "酉", "壬": "子"}   # 阳干帝旺 → 阳刃
YIN_DIWANG = {"乙": "寅", "丁": "巳", "己": "巳", "辛": "申", "癸": "亥"}  # 阴干帝旺（阴干无阳刃）

# ------------------- V1.1.1 统一长生体系：十干分阴阳长生 -------------------
# 取代「五行长生」，消除两套体系混用。旺衰强根标记（禄/刃/长生）一律以此为准。
#   甲长生亥 / 乙长生午 / 丙长生寅 / 丁长生酉 / 戊长生寅 / 己长生酉
#   庚长生巳 / 辛长生子 / 壬长生申 / 癸长生卯
CHANGSHENG_10GAN = {
    "甲": "亥", "乙": "午", "丙": "寅", "丁": "酉", "戊": "寅",
    "己": "酉", "庚": "巳", "辛": "子", "壬": "申", "癸": "卯",
}
# 五行 -> 长生支集合（阴阳两干均计）。例：木长生在 亥(甲)/午(乙)。
CHANGSHENG_WX = {}
for _g, _z in CHANGSHENG_10GAN.items():
    CHANGSHENG_WX.setdefault(WUXING_GAN[_g], set()).add(_z)

# ============================ 四库开库对照表（2.1） ============================
# 库支 -> 所藏五行（余气）、对冲库支。余气位置恒为 position2（见 ZHI_HIDE）。
STORE_INFO = {
    "未": {"wuxing": "木", "chong": "丑"},   # 未中乙木
    "丑": {"wuxing": "金", "chong": "未"},   # 丑中辛金
    "辰": {"wuxing": "水", "chong": "戌"},   # 辰中癸水
    "戌": {"wuxing": "火", "chong": "辰"},   # 戌中丁火
}
STORE_ZHI = set(STORE_INFO.keys())

# ============================ 根类型常量 ============================
ROOT_STRONG = "强根"          # 禄 / 刃 / 长生 / 本气根
ROOT_WEAK = "微根"            # 墓库余气根
ROOT_MEDIUM = "次强根"        # 开库升级后（余气 -> 中气档）

# ============================ 距离系数 ============================
# 顺序：年支, 月支, 日支, 时支
DISTANCE = [0.8, 0.9, 1.0, 0.9]

# ============================ 能量 / 倍率 常量（PRD 第五节） ============================
class Const:
    HEHUA_STRICT = True            # 固定开启严格合化规则
    CONG_THRESHOLD = 0.85          # 从格能量占比阈值（邵伟华严格）
    VOID_MOMENTUM_MAX = 15         # 虚势分上限
    VOID_WANG_TRIGGER = 10         # 虚旺触发阈值
    SANHUI_MAG = 1.8               # 三会成功倍率
    SANHE_MAG = 1.6                # 三合成功倍率
    WUHE_MAG = 1.4                 # 五合成功倍率
    LIUHE_MAG = 1.3                # 六合成功倍率
    BAN_DECAY = 0.6                # 三会/三合绊局折扣
    WUHE_BAN_DECAY = 0.7           # 五合绊折扣
    LIUHE_BAN_DECAY = 0.7          # 六合绊折扣
    VOID_GAN_FACTOR = 0.2          # 天干无根帮扶系数
    MICRO_ROOT_FACTOR = 0.6        # 余气（10 档）天干辨关系数
    MIDDLE_ROOT_FACTOR = 0.8       # 中气（30 档）天干辨关系数（本气1.0 > 中气0.8 > 余气0.6）
    BRANCH_CHONG_FACTOR = 0.5      # 地支被冲（冲支未合化）时的整支能量系数
    VOID_WANG_MIN_SHARE_F = 0.5    # 虚旺要求的最低 F 占比（旺势约束）
    STORE_OPEN_ENABLE = True       # 开库升级总开关
    STORE_SELF_PUNISH_OPEN = False # 四库自刑视为开库
    STORE_ROOT_ENERGY_FROM = 10    # 开库前：余气档能量
    STORE_ROOT_ENERGY_TO = 30      # 开库后：中气档能量（次强根）
    STORE_OPEN_CONFIDENCE_FACTOR = 0.9  # 开库对置信度下调系数
    TIANGAN_BASE = 60              # 天干基准能量（可用于回测调参）


def default_config() -> dict:
    """返回默认超参数（与 PRD 一致）。"""
    return {
        "cong_threshold": Const.CONG_THRESHOLD,
        "hehua_strict": Const.HEHUA_STRICT,
        "store_self_punish_open": Const.STORE_SELF_PUNISH_OPEN,
        "store_open_enable": Const.STORE_OPEN_ENABLE,
        "tiangan_base": Const.TIANGAN_BASE,
        "void_gan_factor": Const.VOID_GAN_FACTOR,
        # V1.2 旺衰专项：微根折扣 / 支冲折半 / 虚旺旺势门槛 / 从格印根开关
        "micro_root_factor": Const.MICRO_ROOT_FACTOR,
        "middle_root_factor": Const.MIDDLE_ROOT_FACTOR,
        "branch_chong_factor": Const.BRANCH_CHONG_FACTOR,
        "void_wang_min_share_f": Const.VOID_WANG_MIN_SHARE_F,
        # 无根从弱门槛：要求印星/比劫均无本气·长生实根（True=决策 1(a) 口径）
        "cong_requires_yin_no_root": True,
        # 印星有强根时是否降级为「假从弱」（False=不认印根，落回虚旺/身弱无根）
        "cong_yin_root_as_fake": False,
        # 印星强根是否破从：current=保持V1.2(无根盘破/有根盘忽略)；ignore=两分支都忽略；block=两分支都破；fake=一律降假从弱
        # 从格专项定稿（2026-11-06）：fake —— 印有强根不否掉从格，降为假从弱（两分支统一）
        "cong_yin_root_policy": "fake",
        # 无根盘是否允许判从格（True=V1.2 新口径；False=回到「无根只出虚旺/身弱无根」）
        "cong_allow_rootless": True,
        # 从格根门槛（从格专项定稿 = tiered）：
        #   off=关闭根档护栏；strict=有效无根才从；tiered=0真从/1假从/实根逐根检查弱化证据
        "cong_root_gate": "tiered",
        "cong_root_gate_side": "both",   # 已弃用；兼容接收rootless并告警，实际统一入口
        # 比劫（日主自身）强根来源：current=五行级(阴干假阳性)；gan_level=日主根清单（定稿）
        "cong_bi_root_source": "gan_level",
        "cong_fake_need_weak_root": True,   # 假从弱用中气根立论时，根须有冲/绊/远位证据（P4）
        "root_include_mid_micro": False,  # 仅影响兼容根清单展示；不改变独根/从格/扶抑与能量
        "store_root_exempt_from_pull": True,  # 库冲开库的根豁免独根拔根
        # V1.2 复核新增（默认保持现行口径，便于 A/B 回测）
        # 冲×绊：ban_priority=保持绊局原系数(默认,等价V1.1)；multiply=叠乘0.35；max=取较轻
        "chong_ban_combine": "ban_priority",
        "de_ling_month_discount": False,      # 月支被冲坏时是否降级为失令门槛
        # V1.1.1：恋根校验总开关（复用，不新增顶层开关）。默认开启。
        # 关闭时与 V1.1 行为完全一致（无恋根拦截）。
        "enable_lian_gen_check": True,
    }
