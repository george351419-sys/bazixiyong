# -*- coding: utf-8 -*-
"""旺衰计算模块（有效根状态 V1.3.2，2026-11-07）。

严格按 PRD 流水线：
  Step1  合化置换（由 heju 完成）→ 根检索（含四库开库升级）
  Step2  独根拔根（质变，优先级高于虚旺/从格）
  Step3  全部有效根统一判断真从 / 假从
  Step4  有效无根 → 虚旺或身弱无根
  Step5  常规扶抑打分（月令驱动动态阈值）
  Step6  置信度兜底修正

输入（PRD 1.1）：四柱干支 + config。
输出（规则 V1.3.2）：结构化旺衰判定 JSON。本模块只负责日主旺衰，不处理调候/格局/喜用综合。

注（工程决策，已与 yan 确认方向）：
  - 「一干支一局」：被任一合局（成功或绊）占用的干支不再参与更低阶合局（见 heju）。
  - 四库开库（库冲）视为「开库释放」的质变，是构造性冲，不触发独根拔根（满足 PRD 用例 11）。
    对「开库后的次强根再被本气冲」的极端情形（用例 15）按 PRD 字面会要求拔根，但与用例 11 的
    「库冲开库、旺衰反转」在相同机械条件下矛盾；本实现取「库冲开库优先、不拔根」，并以
    config.store_root_exempt_from_pull（默认 True）显式可配，便于回测调参。
"""
from __future__ import annotations
from .numeric import finite as safe_finite

import math

from . import metadata as M
from .heju import evaluate as heju_evaluate


# ----------------------------- 关系判定 -----------------------------
def _relation(wx, day_wx):
    """wx 相对日主 day_wx 的十神类别（用于 F/K 归属）。

    同我→比劫(F)；生我→印(F)；我生→食伤(K)；克我→官杀(K)；我克→财(K)。
    """
    if wx == day_wx:
        return "bi"            # 比劫（F）
    if M.SHENG[wx] == day_wx:
        return "yin"           # 印（生我，F）
    if M.SHENG[day_wx] == wx:
        return "shishen"       # 食伤（我生，K）
    if M.KE_OF[day_wx] == wx:
        return "guansha"       # 官杀（克我，K）
    if M.KE[day_wx] == wx:
        return "cai"           # 财（我克，K）
    return None


def _sheng_wo(day_wx):
    """生我（印）的五行：满足 SHENG[w] == day_wx。"""
    for w in M.WUXING_LIST:
        if M.SHENG[w] == day_wx:
            return w
    return None


def _root_level(zhis, branch_hua, wx, gan=None, opened_branches=None, broken_branches=None):
    """天干辨根分档（V1.2）。

    返回 0=无根 / 1=微根(余气) / 2=强根 / 3=中气。
    2 = 本气(p0)，或「十干长生且该支确实藏有该五行」；
    3 = 中气(p1，藏干表 30 档)；1 = 余气(p2，10 档)且非十干长生。
    旧实现用五行级 CHANGSHENG_WX 判长生，会把 午/酉/子/卯 当成 木/火/土/金/水
    有根（午藏丁己、酉藏辛、子藏癸、卯藏乙，都不含对应五行），属于假根；
    此处以「藏干含该五行」为前置条件，假根自动排除。
    合化支按化后五行计强根；开库余气升级为中气档；已拔根支不再提供通根资格。
    中气系数由 middle_root_factor 决定（默认0.8）。
    """
    strong = middle = micro = False
    for i, z in enumerate(zhis):
        if i in (broken_branches or set()):
            continue
        if branch_hua[i]:
            strong |= branch_hua[i] == wx
            continue
        for p, h in enumerate(M.ZHI_HIDE[z]):
            if M.WUXING_GAN[h] != wx:
                continue
            if p == 0:
                strong = True
            elif gan and M.WUXING_GAN.get(gan) == wx and z == M.CHANGSHENG_10GAN.get(gan):
                strong = True          # 十干长生（含 庚长生巳 这类余气位）
            elif p == 1 or (i in (opened_branches or set()) and p == 2
                             and z in M.STORE_INFO and M.STORE_INFO[z]["wuxing"] == wx):
                middle = True          # 中气（30 档），系数见 middle_root_factor
            else:
                micro = True           # 余气（10 档）且非长生
    return 2 if strong else (3 if middle else (1 if micro else 0))


def _de_ling(zhis, month_zhi, day_wx, he, config):
    """得令判定：月支五行 = 日主五行（旺）或其生我（相）→ 得令，走 1.1/0.9/0.7 门槛。

    V1.2：月支被本气相冲（且冲支未合化）时，其月令之力已折，可配 `de_ling_month_discount`
    降级为失令口径（1.4/1.1/0.8）。默认 False（维持 V1.1 行为：只看月支原五行）。
    """
    month_wx = M.WUXING_ZHI[month_zhi]
    de = (month_wx == day_wx) or (M.SHENG[month_wx] == day_wx)
    if de and config.get("de_ling_month_discount", False):
        if _chong_factor_at(1, zhis, he, config) < 1.0:
            de = False
    return de


def _chong_factor_at(i, zhis, he, config):
    """第 i 支被冲（且冲支未被合化）时的能量系数，未冲返回 1.0。"""
    z = zhis[i]
    if he["branch_hua"][i]:
        return 1.0
    cz = M.CHONG.get(z)
    if not cz or cz not in zhis:
        return 1.0
    if not any(zz == cz and not he["branch_hua"][j] for j, zz in enumerate(zhis)):
        return 1.0
    return config.get("branch_chong_factor", M.Const.BRANCH_CHONG_FACTOR)


def _strong_root_wuxing(zhis, branch_hua, opened_branches):
    """历史入口，委托给 `_strong_root_gan`（2026-11-06 从格专项复核后收口）。

    旧实现用五行级 CHANGSHENG_WX，新实现用天干级 CHANGSHENG_10GAN；两者在「支必须真藏该干」
    这一前置条件下恒等（每个五行的两个长生支里只有一个真的藏有该行天干，且藏的这个干正是
    长生者）。2000 盘×两档开库状态实测 0 差异，因此保留调用别名，避免两处口径漂移。
    """
    return _strong_root_gan(zhis, branch_hua, opened_branches)

def _strong_root_gan(zhis, branch_hua, opened_branches):
    """按「具体天干」的十干长生判强根，返回有强根的五行集合（从格残余判定用）。

    与 _strong_root_wuxing 的唯一区别：长生必须「该支确实藏有这个天干」才成立。
    五行级表把 金 的长生记为 {巳, 子}、木 记为 {亥, 午}，于是 子（藏癸）会被算成金有强根、
    午（藏丁己）会被算成木有强根——这属于假根，会让本该真从的盘误降假从。
    """
    out = set()
    for i, z in enumerate(zhis):
        if branch_hua[i]:
            out.add(branch_hua[i])          # 整支置换 = 该五行强根
            continue
        for p, g in enumerate(M.ZHI_HIDE[z]):
            w = M.WUXING_GAN[g]
            if p == 0:
                out.add(w)                  # 本气 → 强根
            elif z == M.CHANGSHENG_10GAN.get(g):
                out.add(w)                  # 十干长生且该支确实藏 g → 强根
            elif p == 2 and z in M.STORE_ZHI and M.STORE_INFO[z]["wuxing"] == w:
                if i in opened_branches:
                    out.add(w)              # 开库升级 → 次强根
    return out


def _cong_fake_weak_root_evidence(roots, zhis, he, config):
    """P4 证据门槛：假从弱用「日主残存中气根」立论时，该根必须真的站不住。

    证据 = 被冲（冲折后能量下降）/ 被绊（合绊锁住）/ 在远位（年支、时支）。
    微根（库余气 10 分）本身就算站不住，无需再加证据。
    """
    for r in roots:
        if r["is_broken"]:
            continue
        i = r["branch_index"]
        if r["root_type"] in ("微根", "余气根"):
            return True
        ban = bool(he.get("branch_ban", [False] * 4)[i]) if he.get("branch_ban") else False
        chonged = _chong_factor_at(i, zhis, he, config) < 1.0
        # 远位只能作为中气根的弱化证据，不能单独否定本气/长生/开库实根。
        far = i in (0, 3) and r["root_type"] == "中气根"
        if ban or chonged or far:
            return True
    return False


def _cong_ruo_verdict(residual_bi_root, residual_yin_root, config, rootless):
    """从弱判定（真从弱 / 假从弱 / 不判），供无根盘与有根盘两分支共用。

    config.cong_yin_root_policy 决定「印星强根」是否破从：
      current（默认）——保持 V1.2 既有口径：无根盘按 cong_requires_yin_no_root 破从，
                       有根盘忽略印根（印远生为虚）。
      ignore —— 两分支都不因印星强根破从（= V1.1 有根盘口径）。
      block  —— 两分支都因印星强根破从：有比劫根→假从弱，否则不判从格。
      fake   —— 印星强根一律降为假从弱（保留「表从实不从」的证据）。
    返回 (tag or None, reason)
    """
    policy = config.get("cong_yin_root_policy", "current")
    if policy == "current":
        if rootless:
            policy = "block" if config.get("cong_requires_yin_no_root", True) else "ignore"
        else:
            policy = "ignore"
    if residual_bi_root:
        if rootless:
            return None, "日主残存比劫强根（按 V1.2 无根盘口径不判假从）"
        return "假从弱", "日主残存比劫强根"
    if residual_yin_root and policy in ("block", "fake"):
        if policy == "fake" or (rootless and config.get("cong_yin_root_as_fake", False)):
            return "假从弱", "印星有强根（表从实不从）"
        return None, "印星有强根"
    return "从弱", ""



# ----------------------------- 根检索（Step1） -----------------------------
def _detect_roots(gans, zhis, day_wx, he, config=None):
    """检索日主全部根清单（含初始微根/强根分类）。返回 root_list。

    config.root_include_mid_micro=True 时，中气(p1, 30档)与非库余气(p2, 10档)也计入日主根，
    用于评估「无根 = 无任何藏干」这一更严格定义的影响面；默认 False（保持 V1.2 口径：
    只有本气/十干长生/开库库根算根）。
    """
    cfg = config or {}
    day_gan = gans[2]   # 日主天干（十干阴阳长生以天干为键）
    roots = []
    for i, z in enumerate(zhis):
        if he["branch_hua"][i]:
            # 整支置换：仅当置换五行==日主五行时才算日主强根（能量=整支 100 × 倍率 × 距离）；
            # 若置换为他五行（如寅化火而日主为木），则该支不再是日主根，不计入 roots。
            if he["branch_hua"][i] == day_wx:
                roots.append({
                    "zhi": z, "branch_index": i, "pos": -1, "gan": None,
                    "root_type": "本气根", "is_broken": False,
                    "base_energy": 100,
                })
            continue
        tiers = M.ZHI_HIDE[z]
        energies = M.zhi_tier_energy(z)
        for p, g in enumerate(tiers):
            w = M.WUXING_GAN[g]
            if w != day_wx:
                continue
            base = energies[p]
            is_cs = (z == M.CHANGSHENG_10GAN.get(day_gan))   # 十干长生（按日主天干）
            if p == 0:                       # 本气根
                if z == M.TEN_GAN_LU.get(day_gan):
                    rt = "禄"
                elif z == M.YANG_REN.get(day_gan):
                    rt = "刃"
                elif z == M.YIN_DIWANG.get(day_gan):
                    rt = "帝旺"
                elif is_cs:
                    rt = "长生"
                else:
                    rt = "本气根"
                roots.append({"zhi": z, "branch_index": i, "pos": p, "gan": g,
                              "root_type": rt, "is_broken": False, "base_energy": base})
            elif is_cs:   # 长生（中气/余气位）。庚长生巳 这类余气位按次强根能量计，不再漏判。
                roots.append({"zhi": z, "branch_index": i, "pos": p, "gan": g,
                              "root_type": "长生", "is_broken": False,
                              "base_energy": base})
            elif cfg.get("root_include_mid_micro", False) and p == 1:
                roots.append({"zhi": z, "branch_index": i, "pos": p, "gan": g,
                              "root_type": "中气根", "is_broken": False, "base_energy": base})
            elif cfg.get("root_include_mid_micro", False) and p == 2:
                roots.append({"zhi": z, "branch_index": i, "pos": p, "gan": g,
                              "root_type": ("微根" if z in M.STORE_INFO and M.STORE_INFO[z]["wuxing"] == day_wx else "余气根"),
                              "is_broken": False, "base_energy": base})
            elif p == 2 and z in M.STORE_ZHI and M.STORE_INFO[z]["wuxing"] == day_wx:
                # 墓库余气根（微根）
                roots.append({"zhi": z, "branch_index": i, "pos": p, "gan": g,
                              "root_type": "微根", "is_broken": False,
                              "base_energy": base})
    return roots


def _apply_store_open(roots, zhis, he, config, warnings):
    """Step1-B：四库开库升级（质变）。返回 (roots, opened_branches, store_opened_roots)。"""
    opened_branches = set()
    store_opened = []
    if not config.get("store_open_enable", True):
        return roots, opened_branches, store_opened
    for i, z in enumerate(zhis):
        if z not in M.STORE_INFO or he["branch_hua"][i]:
            continue
        info = M.STORE_INFO[z]
        chong = info["chong"]
        triggered = any(zz == chong and not he["branch_hua"][j]
                        for j, zz in enumerate(zhis))
        reason = "%s冲%s" % (chong, z)
        if not triggered and config.get("store_self_punish_open", False):
            triggered = z in M.ZI_XING and sum(
                zz == z and not he["branch_hua"][j] for j, zz in enumerate(zhis)) >= 2
            reason = "%s自刑" % z
        if not triggered:
            continue
        opened_branches.add(i)
        store_opened.append({"zhi": z, "branch_index": i,
            "stored_wuxing": info["wuxing"], "root_type_from": "余气微根",
            "root_type_to": "次强根", "energy_from": 10, "energy_to": 30})
        for r in roots:
            if r["branch_index"] == i and r["pos"] == 2:
                r.update(root_type=M.ROOT_MEDIUM, base_energy=30, opened=True)
        warnings.append("%s，%s库开库，余气%s由10升级为30" % (reason, z, info["wuxing"]))
    return roots, opened_branches, store_opened


# ----------------------------- F / K 能量统计 -----------------------------
def _compute_fk(gans, zhis, day_wx, he, root_count, config, store_opened=None, broken_branches=None):
    """统计 F（生扶：印+比劫）与 K（克泄耗：官杀+财+食伤）总有效能量。

    V1.2 口径：
      - 天干印比按 root_level 分三档：强根 1.0 / 微根 micro_root_factor / 无根 void_gan_factor；
      - 克泄耗天干默认使用同一根气折扣；legacy开关可恢复满力，无根另登记诊断；
      - 地支被冲且冲支未合化时整支乘 branch_chong_factor（F、K 同步折，避免单边偏弱）；
      - 四库开库升级同步进 F/K（余气档 10 → 30），与 root_energy 保持同一本账。
    """
    tb = config.get("tiangan_base", M.Const.TIANGAN_BASE)
    vgf = config.get("void_gan_factor", M.Const.VOID_GAN_FACTOR)
    mrf = config.get("micro_root_factor", M.Const.MICRO_ROOT_FACTOR)
    midf = config.get("middle_root_factor", M.Const.MIDDLE_ROOT_FACTOR)
    opened_pairs = {(o["branch_index"], o["stored_wuxing"]) for o in (store_opened or [])}

    F = 0.0
    K = 0.0
    k_elements = set()
    f_elements = set()
    gan_detail = []
    branch_detail = []
    k_dry = []
    climate_energy = {w: 0.0 for w in M.WUXING_LIST}
    energy_records = []
    for i, g in enumerate(gans):
        wx = he["gan_hua"][i] or M.WUXING_GAN[g]
        value = tb * he["gan_mag"][i]
        climate_energy[wx] += value
        energy_records.append(dict(id="stem:%s" % i, wuxing=wx, power=value))
    relation_energy = {key: 0.0 for key in ("bi", "yin", "shishen", "guansha", "cai")}

    # 天干（日主自身不算「生扶/克泄耗」，跳过 index=2）
    for i, g in enumerate(gans):
        if i == 2:
            continue
        eff_wx = he["gan_hua"][i] or M.WUXING_GAN[g]
        base = tb * he["gan_mag"][i]
        rel = _relation(eff_wx, day_wx)
        lv = _root_level(zhis, he["branch_hua"], eff_wx, g,
                         {o["branch_index"] for o in (store_opened or [])},
                         broken_branches if eff_wx == day_wx else None)
        contrib = 0.0
        if rel in ("bi", "yin"):
            bound = (1.0 if lv == 2 else midf if lv == 3
                     else (mrf if lv == 1 else vgf))
            contrib = base * bound
            F += contrib
            f_elements.add(eff_wx)
        elif rel in ("shishen", "guansha", "cai"):
            bound = (1.0 if lv == 2 else midf if lv == 3 else mrf if lv == 1 else vgf)
            contrib = base * bound if config.get("symmetric_root_discount", True) else base
            K += contrib
            k_elements.add(eff_wx)
            if lv == 0:
                k_dry.append({"pos": i, "gan": g, "eff_wx": eff_wx,
                              "relation": rel, "base": round(base, 2)})
        relation_energy[rel] += contrib
        gan_detail.append({"pos": i, "gan": g, "eff_wx": eff_wx, "relation": rel,
                           "root_level": lv, "gan_mag": he["gan_mag"][i],
                           "root_factor": (contrib/base if base else 0),
                           "contribution": round(contrib, 2)})

    # 地支（含藏干分层）
    for i, z in enumerate(zhis):
        dist = M.DISTANCE[i]
        mag = he["branch_mag"][i]
        chong_f = _chong_factor_at(i, zhis, he, config)
        mag_eff = _branch_eff_mag(i, zhis, he, config)
        cF = cK = 0.0
        if he["branch_hua"][i]:
            w = he["branch_hua"][i]
            e = 100.0 * mag_eff * dist
            climate_energy[w] += e
            energy_records.append(dict(id="branch:%s" % i, wuxing=w, power=e))
            relation_energy[_relation(w, day_wx)] += e
            if _relation(w, day_wx) in ("bi", "yin"):
                F += e; f_elements.add(w); cF += e
            else:
                K += e; k_elements.add(w); cK += e
        else:
            for p, g in enumerate(M.ZHI_HIDE[z]):
                w = M.WUXING_GAN[g]
                tier = M.zhi_tier_energy(z)[p]
                if (i, w) in opened_pairs and p == 2:      # 开库升级进 F/K
                    tier = M.Const.STORE_ROOT_ENERGY_TO
                e = tier * mag_eff * dist
                climate_energy[w] += e
                energy_records.append(dict(id="branch:%s:%s" % (i,p), wuxing=w, power=e))
                relation_energy[_relation(w, day_wx)] += e
                if _relation(w, day_wx) in ("bi", "yin"):
                    F += e; f_elements.add(w); cF += e
                elif _relation(w, day_wx) in ("shishen", "guansha", "cai"):
                    K += e; k_elements.add(w); cK += e
        branch_detail.append({"branch_index": i, "zhi": z, "branch_mag": mag,
                              "chong_factor": chong_f, "mag_eff": round(mag_eff, 3),
                              "contribution_F": round(cF, 2), "contribution_K": round(cK, 2)})

    return {"F": F, "K": K, "k_elements": k_elements, "f_elements": f_elements,
            "raw_F": F, "raw_K": K, "relation_energy": relation_energy,
            "climate_energy": climate_energy, "energy_records": energy_records,
            "gan_detail": gan_detail, "branch_detail": branch_detail,
            "k_dry_unrooted": k_dry}


def _branch_eff_mag(i, zhis, he, config):
    """第 i 支的有效倍率（合绊折扣 × 冲折 的合成口径）。

    「既冲又绊」三种可选口径（config.chong_ban_combine）：
      - ban_priority（默认）= V1.1 原系数：只取绊局折扣（0.7 / 0.6），冲不再叠加；
        依据：V1.1 根本没有冲折这一项，一支被冲照常计分，冲的损伤已体现在「根被拔/结构受损」上。
      - multiply = 两者叠乘（0.5×0.7=0.35）
      - max       = 取较轻者
    只有冲（无绊）时一律乘 branch_chong_factor；只有绊（无冲）时取绊局折扣。
    """
    mag = he["branch_mag"][i]
    cf = _chong_factor_at(i, zhis, he, config)
    if cf >= 1.0 or mag >= 1.0:
        return mag * cf                     # 只冲 / 只绊 / 都没有
    mode = config.get("chong_ban_combine", "ban_priority")
    if mode == "multiply":
        return mag * cf
    if mode == "max":
        return max(mag, cf)
    return mag                              # ban_priority：保持原绊局系数


def _root_energy(roots, zhis, he, config):
    """汇总日主实根能量（置换后五行、开库升级后、乘距离系数与倍率/绊/冲折扣）。"""
    total = 0.0
    for r in roots:
        i = r["branch_index"]
        dist = M.DISTANCE[i]
        total += r["base_energy"] * _branch_eff_mag(i, zhis, he, config) * dist
    return round(total, 2)


def _validate_config(config):
    if 'blade_control_ratio' in config:
        value=config['blade_control_ratio']
        if type(value) not in (int,float) or not safe_finite(value) or value<=0:
            raise ValueError('blade_control_ratio必须是正有限数值')
    enums = {
        "cong_root_gate": {"off", "strict", "tiered"},
        "cong_root_gate_side": {"rootless", "both"},
        "cong_yin_root_policy": {"current", "ignore", "block", "fake"},
        "cong_bi_root_source": {"current", "gan_level"},
        "chong_ban_combine": {"ban_priority", "multiply", "max"},
    }
    for key, allowed in enums.items():
        if not isinstance(config[key], str) or config[key] not in allowed:
            raise ValueError("%s无效，可选：%s" % (key, sorted(allowed)))
    bounds = {"cong_threshold": (0.5, 1), "tiangan_base": (0, 1000000),
              "void_gan_factor": (0, 1), "micro_root_factor": (0, 1),
              "middle_root_factor": (0, 1), "branch_chong_factor": (0, 1),
              "void_wang_min_share_f": (0, 1)}
    for key, (low, high) in bounds.items():
        value = config[key]
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or value < low or (high is not None and value > high)
                or not safe_finite(value)
                or (key in ("cong_threshold", "tiangan_base", "branch_chong_factor") and value == low)):
            raise ValueError("%s超出允许范围" % key)
    if not (config["void_gan_factor"] <= config["micro_root_factor"]
            <= config["middle_root_factor"]):
        raise ValueError("辨根系数应满足无根≤余气≤中气≤本气")
    if config["hehua_strict"] is not True:
        raise ValueError("合化固定采用严格规则，hehua_strict必须为true")
    for key, default in M.default_config().items():
        if isinstance(default, bool) and not isinstance(config[key], bool):
            raise ValueError("%s必须是布尔值" % key)


def _weak_cong_decision(level, roots, residual_bi, residual_yin, zhis, he, config):
    """唯一从弱入口：有效根档和逐根证据先于印根真假从分类。"""
    gate = config["cong_root_gate"]
    active = [r for r in roots if not r["is_broken"]]
    if gate == "strict" and level != 0:
        return None, "严格模式：仍有有效根"
    if gate == "tiered" and level in (2, 3):
        if config["cong_fake_need_weak_root"] and not all(
                _cong_fake_weak_root_evidence([r], zhis, he, config) for r in active):
            return None, "残存实根缺少受冲绊或中气远位证据"
    verdict, why = _cong_ruo_verdict(residual_bi, residual_yin, config, level == 0)
    if verdict and gate != "off" and level != 0:
        return "假从弱", "日主残根微弱或逐根通过弱化证据检查" + ("；" + why if why else "")
    return verdict, why or "有效无根且无印比强根"


def _phase_label(day_gan, zhi):
    """禄刃帝旺是独立标记，不改变根档、能量或从格资格。"""
    if zhi == M.TEN_GAN_LU.get(day_gan):
        return "禄"
    if zhi == M.YANG_REN.get(day_gan):
        return "阳刃"
    if zhi == M.YIN_DIWANG.get(day_gan):
        return "帝旺"
    return None


def _at_least(left,right):
    from math import ulp
    return left>=right or right-left<=8*max(ulp(left),ulp(right))

def _cong_ranges(F,K,threshold=.85):
    total=F+K
    if total<=0:return False,False
    return _at_least(F,threshold*total),_at_least((1-threshold)*total,F)

def _bands(de_ling):
    from .fuyi_policy import BALANCE_SHARES
    from fractions import Fraction
    return [float(Fraction(str(p))/(1-Fraction(str(p)))) for p in BALANCE_SHARES] if de_ling is None else [1.1,.9,.7] if de_ling else [1.4,1.1,.8]

def _classification_ling(zhis,month_zhi,day_wx,he,config):
    return None if config.get("seasonal_strength",True) else _de_ling(zhis,month_zhi,day_wx,he,config)

def _balance_tag(ratio_fk,de_ling,F=None,K=None):
    if de_ling is None and F is not None and K is not None:
        from .fuyi_policy import balance_band
        return balance_band(F,K)
    bands=_bands(de_ling)
    for boundary,name in zip(bands,['身旺','中和偏旺','中和偏弱']):
        left,right=(F,boundary*K) if F is not None and K is not None else (ratio_fk,boundary)
        # 仅容忍浮点运算舍入；不把展示百分比作为判定输入。
        if _at_least(left,right):
            return name
    return '身弱'


def _boundary_hints(F, K, tag, de_ling, cong_threshold, weak_candidate=None,
                    strong_candidate=None, rootless=False, void_momentum=0,
                    void_min_share=.5):
    """固定结构下的邻近判定提示；提示半径不是评分阈值或准确率。"""
    total = F + K
    share_f, share_k = F / total, K / total
    ratio_fk = F / K if K > 0 else 99.0
    fallback = ("虚旺" if void_momentum >= M.Const.VOID_WANG_TRIGGER and share_f >= void_min_share
                else "身弱无根") if rootless else _balance_tag(ratio_fk, de_ling,F,K)
    hints = []
    def add(kind, value, threshold, radius, low, high):
        distance = abs(value - threshold)
        if distance <= radius + 1e-12 and tag in (low, high):
            neighbor = low if tag == high else high
            if neighbor == tag:
                return
            hints.append({"kind": kind, "value": round(value, 6), "threshold": threshold,
                          "distance": round(distance, 6), "review_radius": radius,
                          "current_tag": tag, "adjacent_tag": neighbor,
                          "note": "仅提示固定结构下的邻近规则结论，不改判、不直接切换喜用。"})
    if tag in ("身旺", "中和偏旺", "中和偏弱", "身弱"):
        thresholds = _bands(de_ling)
        for boundary, low, high in zip(thresholds, ["中和偏旺", "中和偏弱", "身弱"],
                                      ["身旺", "中和偏旺", "中和偏弱"]):
            add("balance", ratio_fk, boundary, .05, low, high)
    if weak_candidate:
        add("cong_weak", share_k, cong_threshold, .02, fallback, weak_candidate)
    if strong_candidate:
        add("cong_strong", share_f, cong_threshold, .02, fallback, strong_candidate)
    if rootless and void_momentum >= M.Const.VOID_WANG_TRIGGER and tag in ("虚旺", "身弱无根"):
        add("void_wang", share_f, void_min_share, .02, "身弱无根", "虚旺")
    return hints


# ----------------------------- 主入口 -----------------------------
def compute_wangshuai(chart, config=None):
    """计算日主旺衰。

    参数:
        chart : PRD 1.1 输入 JSON，含 year/month/day/hour 各 {gan,zhi}；
                也接受扁平 {'gans':[4], 'zhis':[4]}。
        config: 超参（cong_threshold / store_self_punish_open / tiangan_base / ...）。
    返回: PRD 1.2 结构化结果 dict。
    """
    if config is not None and not isinstance(config, dict):
        raise ValueError("config必须为字典")
    if config is None:
        config = M.default_config()
    else:
        base = M.default_config()
        base.update(config)
        config = base

    _validate_config(config)
    if not isinstance(chart, dict):
        raise ValueError("chart必须为四柱字典")
    try:
        if "gans" in chart or "zhis" in chart:
            if not all(isinstance(chart.get(k), (list, tuple, str)) for k in ("gans", "zhis")):
                raise ValueError("gans和zhis必须同时提供四项序列")
            gans, zhis = list(chart["gans"]), list(chart["zhis"])
        else:
            pillars = [chart[k] for k in ("year", "month", "day", "hour")]
            if not all(isinstance(p, dict) for p in pillars):
                raise ValueError("四柱必须为包含gan和zhi的字典")
            gans = [p["gan"] for p in pillars]
            zhis = [p["zhi"] for p in pillars]
        if (len(gans) != 4 or len(zhis) != 4
                or any(not isinstance(g, str) or g not in M.GAN_LIST for g in gans)
                or any(not isinstance(z, str) or z not in M.ZHI_LIST for z in zhis)):
            raise ValueError("需要四个有效天干和四个有效地支")
    except (KeyError, TypeError) as exc:
        raise ValueError("四柱输入不完整，需要gans/zhis或year/month/day/hour的gan/zhi") from exc

    day_gan = gans[2]
    day_wx = M.WUXING_GAN[day_gan]
    month_zhi = zhis[1]
    warnings = []
    if config["cong_root_gate_side"] != "both":
        warnings.append("cong_root_gate_side已弃用，统一有效根入口始终适用于全部分支")

    # ---- 前置合局判定 ----
    he = heju_evaluate(gans, zhis, config)

    # 所有质变只处理一份完整根清单；结构清单仅用于兼容展示。
    evidence_roots = _detect_roots(gans, zhis, day_wx, he,
                                  dict(config, root_include_mid_micro=True))
    evidence_roots, opened_branches, store_opened = _apply_store_open(
        evidence_roots, zhis, he, config, warnings)
    pull_event = {"scope": "all_effective_roots", "pre_count": len(evidence_roots),
                  "triggered": False, "branch_index": None, "store_exempt": False}
    pulled = False
    if len(evidence_roots) == 1:
        root = evidence_roots[0]
        i = root["branch_index"]
        opposite = M.CHONG.get(root["zhi"])
        has_chong = not he["branch_hua"][i] and any(
            z == opposite and not he["branch_hua"][j] for j, z in enumerate(zhis))
        exempt = (i in opened_branches and root["root_type"] == M.ROOT_MEDIUM
                  and config["store_root_exempt_from_pull"])
        pull_event["store_exempt"] = bool(has_chong and exempt)
        if has_chong and not exempt:
            root["original_base_energy"] = root["base_energy"]
            root.update(base_energy=0, is_broken=True)
            pulled = True
            pull_event.update(triggered=True, branch_index=i)
            warnings.append("%s被%s冲，唯一有效根拔根清零" % (root["zhi"], opposite))
    broken_branches = {r["branch_index"] for r in evidence_roots if r["is_broken"]}
    roots = _detect_roots(gans, zhis, day_wx, he, config)
    by_branch = {r["branch_index"]: r for r in evidence_roots}
    for root in roots:
        root.update(by_branch[root["branch_index"]])
    root_count = sum(not r["is_broken"] for r in roots)
    root_detail = {"store_open": bool(store_opened), "store_opened_roots": store_opened,
                   "pull_event": pull_event}
    root_status = ("独根被冲拔根" if pulled else "多根稳固" if root_count > 1
                   else "独根无伤" if root_count == 1 else "无根")
    reng = _root_energy(roots, zhis, he, config)
    fk = _compute_fk(gans, zhis, day_wx, he, root_count, config, store_opened, broken_branches)
    from .season_strength import adjust
    fk=adjust(fk,gans,zhis,day_wx,he,config,_relation,_root_level,{o["branch_index"] for o in store_opened},broken_branches)
    total = fk["F"] + fk["K"]
    ratio_share_f = (fk["F"] / total) if total > 0 else 1.0
    ratio_share_k = (fk["K"] / total) if total > 0 else 1.0
    ratio_fk = (fk["F"] / fk["K"]) if fk["K"] > 0 else 99.0
    cong_threshold = config.get("cong_threshold", M.Const.CONG_THRESHOLD)
    strong_wx = _strong_root_wuxing(zhis, he["branch_hua"], opened_branches)
    # 从强侧残余克泄耗强根：与从弱同源，一律按「具体天干」的十干长生 + 藏干前置条件
    residual_strong_wx = _strong_root_gan(zhis, he["branch_hua"], opened_branches)
    # 独根被冲拔根后，该支在结构上虽还「藏」日主五行，但根已断（质变清零），
    # 不能再算作从格的残余强根。
    # 比劫（日主自身）强根：两套口径
    #   current —— 五行级 _strong_root_wuxing（会把「甲长生亥」算作乙日主有强根，阴干假阳性）
    #   gan_level —— 直接用日主根清单里的强根档（禄/刃/帝旺/长生/本气根），与四档辨根一致
    if config.get("cong_bi_root_source", "current") == "gan_level":
        strong_types = {"禄", "刃", "帝旺", "长生", "本气根"}
        residual_bi_root = any(r["root_type"] in strong_types and not r["is_broken"] for r in evidence_roots)
    else:
        residual_bi_root = (day_wx in strong_wx) and not pulled
    yin_wx = _sheng_wo(day_wx)
    # 日主四档辨根档（0 无根 / 1 微根·余气 / 2 强根 / 3 中气），从格门槛与输出共用
    day_root_level = _root_level(zhis, he["branch_hua"], day_wx, gans[2])
    effective_root_level = _root_level(zhis, he["branch_hua"], day_wx, gans[2],
                                       opened_branches, broken_branches)
    residual_yin_root = yin_wx in strong_wx

    # 从格及扶抑只消费有效根，不按兼容结构清单分流。
    active_roots = [r for r in evidence_roots if not r["is_broken"]]
    void_momentum = 0
    if effective_root_level == 0:
        for i, g in enumerate(gans):
            if i != 2 and (he["gan_hua"][i] or M.WUXING_GAN[g]) in (day_wx, yin_wx):
                void_momentum += 6 if i in (1, 3) else 3
        void_momentum = min(void_momentum, M.Const.VOID_MOMENTUM_MAX)
    tag = None
    trace = []
    cong_info = {"is_cong": False, "is_fake_cong": False,
                 "residual_bi_root": residual_bi_root,
                 "residual_yin_root": residual_yin_root}
    enters_strong,enters_weak=_cong_ranges(fk["F"],fk["K"],cong_threshold)
    if enters_weak:
        if effective_root_level == 0 and not config["cong_allow_rootless"]:
            why = "配置禁用无根从格"
        else:
            tag, why = _weak_cong_decision(effective_root_level, evidence_roots,
                residual_bi_root, residual_yin_root, zhis, he, config)
        trace.append({"rule": "cong_weak", "passed": tag is not None, "reason": why})
    else:
        trace.append({"rule": "cong_weak", "passed": False, "reason": "克泄耗占比未达门槛"})
    if tag is None and enters_strong:
        # 印旺不等于日主从强：至少需要中气或强根承接生扶。
        supported = effective_root_level in (2, 3)
        residual_k_root = bool(fk["k_elements"] & residual_strong_wx)
        cong_info.update(residual_k_root=residual_k_root,
                         strong_support="实根承扶" if supported else "印比旺但日主缺乏实根",
                         residual_k_elements=sorted(fk["k_elements"] & residual_strong_wx))
        potential_k = fk["k_elements"] & _strong_root_gan(zhis, he["branch_hua"], {i for i,z in enumerate(zhis) if z in M.STORE_ZHI})
        if supported and (residual_k_root or not potential_k):
            tag = "假从强" if residual_k_root else "从强"
        elif supported:
            warnings.append("库中存在潜在克泄耗强根，保守不升真从强")
        trace.append({"rule": "cong_strong", "passed": tag in ("从强","假从强"),
                      "reason": "实根承扶；残余克泄耗强根决定真假" if tag in ("从强","假从强") else "潜在库根阻止升格" if supported else "日主仅微根或无根，不判从强"})
    if tag is None and effective_root_level == 0:
        tag = "虚旺" if (void_momentum >= M.Const.VOID_WANG_TRIGGER and
             ratio_share_f >= config["void_wang_min_share_f"]) else "身弱无根"
        trace.append({"rule": "rootless", "passed": True, "reason": tag})
        if void_momentum >= M.Const.VOID_WANG_TRIGGER and tag != "虚旺":
            warnings.append("天干虚势达标但生扶占比不足，不判虚旺")
    if tag is None:
        tag = _balance_tag(ratio_fk, _classification_ling(zhis, month_zhi, day_wx, he, config),fk["F"],fk["K"])
        trace.append({"rule": "balance", "passed": True, "reason": tag})
    is_cong = tag in ("从强", "从弱")
    is_fake_cong = tag in ("假从强", "假从弱")
    cong_info.update(is_cong=is_cong, is_fake_cong=is_fake_cong)
    warnings.extend(t["reason"] for t in trace if t["passed"])

    # ---- Step6 置信度 ----
    if tag in ("身旺", "身弱"):
        confidence = 0.85
    elif tag in ("中和偏旺", "中和偏弱"):
        confidence = 0.6
    elif tag in ("从强", "从弱"):
        confidence = 0.82
    elif tag in ("假从强", "假从弱"):
        confidence = 0.45
    elif tag in ("虚旺", "身弱无根"):
        confidence = 0.5
    else:
        confidence = 0.7

    # 全局修正
    if is_fake_cong:
        confidence = min(confidence, 0.5)
    if len(he["he_groups"]) > 1 or any(he["branch_ban"]) or any(he["gan_ban"]):
        confidence *= 0.8
    if len(active_roots) == 1:
        confidence *= 0.85
    if root_detail["store_open"]:
        confidence *= M.Const.STORE_OPEN_CONFIDENCE_FACTOR

    result = _assemble(
        chart, config, zhis, he, day_gan, day_wx, month_zhi, tag, round(confidence, 3),
        root_status, roots, root_detail, void_momentum, reng, fk, warnings,
        is_cong=is_cong, is_fake_cong=is_fake_cong, cong_info=cong_info,
        ratio_fk=ratio_fk, ratio_share_f=ratio_share_f, ratio_share_k=ratio_share_k,
        day_root_level=day_root_level,
        thresholds={"cong_threshold": cong_threshold,
                    "de_ling": _de_ling(zhis, month_zhi, day_wx, he, config),
                    "ratio_fk_bands": _bands(_classification_ling(zhis, month_zhi, day_wx, he, config)),
                    "void_wang_min_share_f": config.get("void_wang_min_share_f"),
                    "micro_root_factor": config.get("micro_root_factor"),
                    "middle_root_factor": config.get("middle_root_factor"),
                    "branch_chong_factor": config.get("branch_chong_factor")})
    from math import fsum
    result["climate_energy_raw"] = {w:fsum(e['power'] for e in fk['energy_records'] if e['wuxing']==w) for w in M.WUXING_LIST}
    result["climate_energy"] = {w: round(v, 6) for w,v in result['climate_energy_raw'].items()}
    result["energy_records"] = fk["energy_records"]
    result["relation_energy"] = {key: round(value, 2) for key, value in fk["relation_energy"].items()}
    result["cong_info"]["support_profile"] = (
        "印主导" if fk["relation_energy"]["yin"] > fk["relation_energy"]["bi"] else "比劫主导")
    result["effective_root_level"] = effective_root_level
    result["root_state"] = {
        "count": sum(not r["is_broken"] for r in roots),
        "energy_level": effective_root_level,
        "damaged_branches": [i for i in range(4) if
            _chong_factor_at(i, zhis, he, config) < 1 or he["branch_ban"][i]],
        "effective_count": len(active_roots),
        "effective_energy": _root_energy(active_roots, zhis, he, config),
        "damaged_root_branches": sorted({r["branch_index"] for r in evidence_roots
            if r["is_broken"] or he["branch_ban"][r["branch_index"]]
            or _chong_factor_at(r["branch_index"], zhis, he, config) < 1}),
        "pulled_branches": sorted(broken_branches),
        "note": "root_status是兼容结构事件；effective_count为剩余全部有效根数量。",
    }
    result["root_semantics"]["effective_root_scope"] = (
        "effective_root_level计入合化与全局开库，并排除已拔根支；"
        "day_root_level保留未应用开库/拔根的扫描档位以兼容旧接口。"
        "拔根清除通根资格，地支F/K仍按冲折保留余力。")
    result["root_semantics"]["usage_note"] = (
        "独根判定、拔根、从格和扶抑统一读取全部有效根；结构清单与root_status仅保留兼容展示。"
        "长生提升根资格，不增加藏干能量；开库才将库余气10升级为30。")
    result["root_semantics"]["energy_root_scope"] = (
        "effective_root_level及effective_roots计入合化、开库和拔根，档位0无根/1余气/2强根/3中气。"
        "root_state.effective_energy统计全部有效根，root_energy保留兼容结构根统计。")
    result["decision_trace"] = trace
    result["cong_info"]["root_evidence"] = [
        {"branch_index": r["branch_index"], "root_type": r["root_type"],
         "broken": r["is_broken"],
         "weak_evidence": _cong_fake_weak_root_evidence([r], zhis, he, config)}
        for r in evidence_roots]
    result["cong_info"]["residual_k_evidence"] = [
        {"branch_index": i, "wuxing": wx,
         "damaged": bool(he["branch_ban"][i]) or _chong_factor_at(i, zhis, he, config) < 1}
        for i in range(4)
        for wx in sorted(_strong_root_gan([zhis[i]], [he["branch_hua"][i]],
                                           {0} if i in opened_branches else set()) & fk["k_elements"])]
    for evidence in result["cong_info"]["residual_k_evidence"]:
        i, wx = evidence["branch_index"], evidence["wuxing"]
        if he["branch_hua"][i]:
            base = 100.0
        else:
            base = sum((M.Const.STORE_ROOT_ENERGY_TO if i in opened_branches and p == 2
                        and M.STORE_INFO[zhis[i]]["wuxing"] == wx else M.zhi_tier_energy(zhis[i])[p])
                       for p, gan in enumerate(M.ZHI_HIDE[zhis[i]]) if M.WUXING_GAN[gan] == wx)
        evidence["eff_energy"] = round(base * _branch_eff_mag(i, zhis, he, config) * M.DISTANCE[i], 2)
    result["effective_roots"] = [dict(r, eff_energy=round(r["base_energy"] *
        _branch_eff_mag(r["branch_index"], zhis, he, config) * M.DISTANCE[r["branch_index"]], 2))
        for r in evidence_roots]
    result["confidence_semantics"] = {
        "kind": "heuristic", "calibrated_probability": False,
        "note": "规则经验系数，非准确率或概率，不宜直接作为融合权重。",
        "cong_margin": round(max(ratio_share_f, ratio_share_k) - cong_threshold, 6),
        "balance_boundary_distance": round(min(abs(ratio_fk - x) for x in
            _bands(_classification_ling(zhis, month_zhi, day_wx, he, config))), 6),
    }
    result["phase_marks"] = [
        {"branch_index": i, "zhi": z, "label": _phase_label(day_gan, z),
         "active": not bool(he["branch_hua"][i]) and i not in broken_branches,
         "inactive_reason": "合化置换" if he["branch_hua"][i] else "根已被拔" if i in broken_branches else None}
        for i, z in enumerate(zhis) if _phase_label(day_gan, z)]
    for root in result["effective_roots"]:
        i = root["branch_index"]
        root["phase_label"] = (_phase_label(day_gan, zhis[i])
                               if not he["branch_hua"][i] and not root["is_broken"] else None)
    weak_candidate, _ = _weak_cong_decision(effective_root_level, evidence_roots,
        residual_bi_root, residual_yin_root, zhis, he, config)
    if effective_root_level == 0 and not config["cong_allow_rootless"]:
        weak_candidate = None
    potential_k = fk["k_elements"] & _strong_root_gan(zhis,he["branch_hua"],{i for i,z in enumerate(zhis) if z in M.STORE_ZHI})
    strong_candidate = (("假从强" if fk["k_elements"] & residual_strong_wx else "从强")
                        if effective_root_level in (2, 3) else None)
    result["boundary_hints"] = _boundary_hints(fk["F"], fk["K"], tag,
        _classification_ling(zhis, month_zhi, day_wx, he, config), cong_threshold,
        weak_candidate, strong_candidate, effective_root_level == 0,
        void_momentum, config["void_wang_min_share_f"])
    if strong_candidate=="从强" and potential_k:
        result["boundary_hints"]=[h for h in result["boundary_hints"] if h.get("kind")!="cong_strong"]
    result["cong_range"]=dict(strong_min=cong_threshold,weak_max=round(1-cong_threshold,12),enters_strong=enters_strong,enters_weak=enters_weak,uses="含日干有效力量" if (fk.get("seasonal_assessment") or {}).get("day_stem_policy")=="included_effective" else "旧版配置口径")
    result["ratio_share_f_exact"]=ratio_share_f
    from .fuyi_policy import VERSION as fuyi_policy_version
    result["fuyi_policy_version"]=fuyi_policy_version
    result["calculation_profile"]=dict(seasonal_strength=config["seasonal_strength"],include_day_stem_requested=config["include_day_stem"],include_day_stem_effective=config["include_day_stem"] and config["seasonal_strength"],note="关闭季节层即回放旧计分行为，日干计分开关仅在季节版生效")
    result["seasonal_assessment"]=fk.get("seasonal_assessment")
    result["rules_version"] = "wangshuai_season_v3_day_included" if config.get("seasonal_strength",True) else "wangshuai_effective_roots_v1.3.2"
    def ensure_finite(value):
        if isinstance(value, float) and not safe_finite(value):
            raise ValueError("旺衰计算产生非有限数值，请检查参数")
        if isinstance(value, dict):
            for item in value.values():
                ensure_finite(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                ensure_finite(item)
    ensure_finite(result)
    from .ws_identity import seal
    seal(result, chart, config)
    return result


def _assemble(chart, config, zhis, he, day_gan, day_wx, month_zhi, tag, confidence,
              root_status, roots, root_detail, void_momentum, root_energy, fk,
              warnings, is_cong, is_fake_cong, cong_info=None,
              ratio_fk=None, ratio_share_f=None, ratio_share_k=None, thresholds=None,
              day_root_level=None):
    # 根明细列表（供前端/上层展示）
    root_list = []
    for r in roots:
        i = r["branch_index"]
        cf = _chong_factor_at(i, zhis, he, config)
        root_list.append({
            "zhi": r["zhi"], "root_type": r["root_type"],
            "is_broken": r["is_broken"], "pos": r["pos"],
            "base_energy": r["base_energy"],
            "eff_energy": round(r["base_energy"]
                                * _branch_eff_mag(i, zhis, he, config)
                                * M.DISTANCE[i], 2),
            "branch_index": i,
        })

    he_result = he["he_result"]
    return {
        "tag": tag,
        "confidence": confidence,
        "root_status": root_status,
        "void_momentum": void_momentum,
        "root_energy": root_energy,
        "F": round(fk["F"], 2),
        "K": round(fk["K"], 2),
        # ratio 保留 = 扶抑倍数（旧字段，兼容）；从格占比请看 ratio_share_*
        "ratio": round(ratio_fk, 3) if ratio_fk is not None else None,
        "ratio_fk": round(ratio_fk, 3) if ratio_fk is not None else None,
        "ratio_share_f": round(ratio_share_f, 3) if ratio_share_f is not None else None,
        # 取整口径：share_k 由 share_f 反推，保证两者相加恒为 1.000（避免各自四舍五入后和为 0.999）
        "ratio_share_k": (round(1.0 - round(ratio_share_f, 3), 3)
                          if ratio_share_f is not None else None),
        "day_root_level": day_root_level,
        # 两套根口径必须同时展示，避免把「结构根清单=无根」误读成 F/K 也无根气。
        "root_semantics": {
            "structural_root_scope": ("root_status / debug.root_list 的质变根清单："
                                      "默认只收本气、十干长生、四库库根与合化整支；"
                                      "普通中气和非库余气不进清单。"),
            "energy_root_scope": ("day_root_level / F / K 的能量辨根：扫描全部藏干，"
                                  "0=无根，1=微根/余气，2=强根/本气/十干长生，"
                                  "3=中气。"),
            "usage_note": ("结构根用于无根、拔根、从格质变判断；能量根用于 F/K 与"
                           "天干辨根系数。两者同时输出，不可互相替代。"),
        },
        "day_gan": day_gan,
        "day_wuxing": day_wx,
        "month_zhi": month_zhi,
        "he_result": he_result,
        "he_groups": he["he_groups"],
        # 完整合化明细：供格局模块直接复用（PRD 格局「前置判断以旺衰模块合化为准」）。
        "he_detail": he,
        "root_detail": root_detail,
        "cong_info": cong_info or {"is_cong": is_cong, "is_fake_cong": is_fake_cong},
        "warning": warnings,
        "debug": {
            "root_list": root_list,
            "raw_F": round(fk["raw_F"], 2),
            "raw_K": round(fk["raw_K"], 2),
            "gan_detail": fk.get("gan_detail", []),
            "branch_detail": fk.get("branch_detail", []),
            "k_dry_unrooted": fk.get("k_dry_unrooted", []),
            "branch_hua": he["branch_hua"],
            "branch_mag": he["branch_mag"],
            "gan_hua": he["gan_hua"],
            "thresholds": thresholds or {},
            "root_level": day_root_level,
        },
    }
