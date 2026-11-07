# -*- coding: utf-8 -*-
"""前置合局判定流水线（严格化）—— PRD 第三节。

执行顺序：三会 → 三合 → 天干五合 → 地支六合。
核心公理：合化成功 = 五行本质置换；合而不化 = 仅合绊减力，五行不变。

产出（供旺衰 / 未来格局 / 调候复用）：
  - branch_hua[i]  : 第 i 地支成功合化后的五行（None 表示未置换）
  - branch_mag[i]  : 第 i 地支能量倍率（置换成功=倍率；绊局=折扣；否则 1.0）
  - branch_ban[i]  : 第 i 地支是否合而不化（绊局）
  - branch_lock[i] : 第 i 地支是否被任一合局占用（成功或绊，均锁定，遵循「一干支一局」）
  - gan_hua / gan_mag / gan_ban / gan_lock ：天干对应字段
  - he_groups      : 全部匹配到的合局记录（含成功/绊局标记）
  - he_result      : 最高优先级合局摘要（兼容 PRD 输出示例）

设计约束：
  - 同一地支至多参与一个成功合化局；高阶成功则低阶跳过，低阶标记「被裹挟」。
  - 一干支一局：被任一合局（成功或绊）占用的干支，不再参与更低阶合局判定。
  - 合化成功干支五行置换，后续根检索 / F·K 统计一律用置换后五行。
"""
from __future__ import annotations

from . import metadata as M


def _members_present(zhis, members):
    """members 中每个地支是否都在 zhis 里（返回索引列表）。"""
    # 重复成员先选月支，再按距离月支最近、同距日支优先选位。
    # 顺序固定为月、日、年、时，不凭五行得分择优。
    idx = []
    for member in members:
        candidates = [i for i in (1, 2, 0, 3) if zhis[i] == member]
        if not candidates:
            return None
        idx.append(candidates[0])
    return idx


def _has_di_zhi_root(zhis, wx, locked=None, exclude=None, strong_only=False, branch_hua=None):
    """某五行 wx 是否在原地支中得根（合化化神根气 / 克化神强局 判定用）。

    locked: 被成功合化置换的地支不计入（其五行已变）。
    exclude: 这些索引视为「合局自身成员」，不参与「克化神成强局」判定。
    strong_only: True 仅认本气根（用于「克化神成强局」，长生过弱不计入）；
                 False 认本气 + 长生根（用于「化神得根气」）。
    """
    exclude = exclude or set()
    for i, z in enumerate(zhis):
        if i in exclude:
            continue
        if branch_hua and branch_hua[i]:
            if branch_hua[i] == wx:
                return True
            continue
        if locked and locked[i]:
            continue
        if M.WUXING_ZHI[z] == wx:           # 本气根
            return True
        if (not strong_only and z in M.CHANGSHENG_WX.get(wx, set())
                and any(M.WUXING_GAN[g] == wx for g in M.ZHI_HIDE[z])):   # 长生根（十干阴阳长生，V1.1.1 统一体系）
            return True
    return False


# ============================ 恋根校验（V1.1.1 新增） ============================
# 规则（PRD V1.1.1 第三节·定稿）：
#   参与本次合化的干支，以及原五行同气透出天干，在【剔除本次合局参与地支】之后的其余地支中，
#   不存在该原五行的【禄、刃强根（恋根）】；长生、开库次强根、余气微根均不阻断；局外虚浮无根的同五行透干不阻断。
#
# 黑名单：仅 {禄, 刃}。长生不在黑名单（长生嫩气初生，不拦截合化）。
# 土特殊约定：戊己无标准禄刃，辰戌丑未四库本气土统一视为土的禄刃级根据地 ——
#   【对所有四类合化（三会/三合/五合/六合）均生效】。此为用户在 V1.1.1-ext 中拍板决策：
#   扩展土特殊至三合/三会。
#   必然结果：三合/三会中库支(辰戌丑未)参与、且局外另有辰戌丑未时，必然恋根绊（例：巳酉丑金遇局外未）。
#   case12 已据新行为更新（原「三合化则库不开」被恋根改写）。详见 PRD V1.1.1 addendum。
def _lu_ren_branches(wx, soil_special):
    """返回某五行 wx 的禄/刃强根支集合（恋根黑名单）。

    土特殊约定（PRD V1.1.1-ext，用户决策）：戊己无标准禄刃，仅以 辰戌丑未 本气土 为禄刃级根据地，
    且【对所有四类合化（三会/三合/五合/六合）生效】；原 V1.1 reconciled 的「三合/三会收紧」口径已废弃。
    其余五行一律用标准 禄(LU)/刃(REN)。
    """
    if wx == "土":
        return (set(M.STORE_ZHI) if soil_special else set())
    bs = set()
    lu = M.LU.get(wx)
    ren = M.REN.get(wx)
    if lu:
        bs.add(lu)
    if ren:
        bs.add(ren)
    return bs


def lian_gen_blocked(zhis, gans, participant_zhi_idx, participant_gan_idx, hua_wx, combo_type, config, branch_hua=None):
    """V1.1.1 恋根校验。返回 (blocked: bool, detail: str)。

    参数:
        zhis / gans      : 原局四柱地支 / 天干
        participant_zhi_idx : 本次合局参与地支下标集合（用于剔除，仅查局外独立根据地）
        participant_gan_idx : 本次合局参与天干下标集合（五合场景；六合/三合/三会为空）
        hua_wx           : 化神五行（参与元素中已是该五行的不计入恋根目标）
        combo_type       : 'sanhuí' | 'sanhe' | 'wuhe' | 'liuhe'
        config           : 超参（enable_lian_gen_check）

    校验目标五行 target = {参与地支原五行} ∪ {参与天干原五行} - {化神五行}
        （即只查「需要改变五行（被合化）的参与元素」在局外是否还恋着禄/刃强根；
          化神自身元素已在该五行，不存在“恋根”问题）。
    局外检查池 check_pool = 全部地支 - 参与地支。
    """
    if not config.get("enable_lian_gen_check", True):
        return False, ""  # 关闭时与 V1.1 完全一致（无恋根拦截）

    soil_special = True   # V1.1.1-ext：土特殊（辰戌丑未为土禄刃级根据地）对所有四类合化生效
    part_zhi_wx = {M.WUXING_ZHI[zhis[i]] for i in participant_zhi_idx}
    part_gan_wx = {M.WUXING_GAN[gans[i]] for i in participant_gan_idx}
    target = (part_zhi_wx | part_gan_wx) - {hua_wx}
    check_pool = [zhis[i] for i in range(len(zhis))
                  if i not in participant_zhi_idx and not (branch_hua and branch_hua[i])]

    for tw in target:
        forbidden = _lu_ren_branches(tw, soil_special)
        for z in check_pool:
            if z in forbidden:
                return True, "恋根：%s在%s得禄/刃强根，合而不化" % (tw, z)
    return False, ""


def evaluate(gans, zhis, config=None):
    """对四柱干支做合局判定。

    参数:
        gans : 4 个天干字符列表 [年,月,日,时]
        zhis : 4 个地支字符列表 [年,月,日,时]
        config: 超参（仅 hehua_strict 等；本版固定严格）
    返回: dict（见模块 docstring）
    """
    if config is not None and not isinstance(config, dict):
        raise ValueError("合化配置必须为字典")
    if (config or {}).get("hehua_strict", True) is not True:
        raise ValueError("合化固定采用严格规则，hehua_strict必须为true")
    n = 4
    branch_hua = [None] * n
    branch_mag = [1.0] * n
    branch_ban = [False] * n
    branch_lock = [False] * n
    gan_hua = [None] * n
    gan_mag = [1.0] * n
    gan_ban = [False] * n
    gan_lock = [False] * n
    he_groups = []

    month_zhi = zhis[1]

    # ---------------------- 1) 三会局（最高优先级） ----------------------
    for sh in M.SANHUI:
        idx = _members_present(zhis, sh["members"])
        if not idx:
            continue
        ok = True
        reasons = []
        # 条件2：月令必须是会局的本气旺支
        if month_zhi not in sh["wang"]:
            ok = False
            reasons.append("月令非会局本气旺支")
        # 条件3：会局本气地支不被本气相冲（本气化神分支若存在冲支则破）
        for z in sh["members"]:
            if M.WUXING_ZHI[z] == sh["wx"] and M.CHONG.get(z) in zhis:
                ok = False
                reasons.append("%s被%s冲，会而不化" % (z, M.CHONG[z]))
                break
        # 条件4：克制化神的强根干支透干成局（排除会局自身成员，仅认本气强根）
        ke_wx = M.KE_OF[sh["wx"]]
        for g in gans:
            if M.WUXING_GAN[g] == ke_wx and _has_di_zhi_root(zhis, ke_wx, exclude=set(idx), strong_only=True):
                ok = False
                reasons.append("%s透干成局克化神%s" % (g, sh["wx"]))
                break
        # 恋根校验（V1.1.1）：参与地支原五行在局外不得有禄/刃强根
        blocked, lgreason = lian_gen_blocked(zhis, gans, set(idx), set(), sh["wx"], "sanhuí", config or {})
        if blocked:
            ok = False
            reasons.append(lgreason)
        for i in idx:
            branch_lock[i] = True
        if ok:
            for i in idx:
                branch_hua[i] = sh["wx"]
                branch_mag[i] = M.Const.SANHUI_MAG
            he_groups.append({"type": "sanhuí", "members": sh["members"], "idx": idx,
                              "hua_success": True, "hua_wuxing": sh["wx"],
                              "ban": False, "reason": "三会成功"})
        else:
            for i in idx:
                branch_ban[i] = True
                branch_mag[i] = M.Const.BAN_DECAY
            he_groups.append({"type": "sanhuí", "members": sh["members"], "idx": idx,
                              "hua_success": False, "hua_wuxing": None,
                              "ban": True, "reason": "; ".join(reasons) or "会而不化"})
        break  # 三会至多一组

    # ---------------------- 2) 三合局（次高优先级） ----------------------
    for sh in M.SANHE:
        idx = _members_present(zhis, sh["members"])
        if not idx:
            continue
        if any(branch_lock[i] for i in idx):
            continue  # 已被三会占用
        ok = True
        reasons = []
        # 条件2：月令必须为中神
        if month_zhi != sh["zhong"]:
            ok = False
            reasons.append("月令非中神(%s)" % sh["zhong"])
        # 条件3：中神不被本气相冲
        if M.CHONG.get(sh["zhong"]) in zhis:
            ok = False
            reasons.append("中神%s被%s冲" % (sh["zhong"], M.CHONG[sh["zhong"]]))
        # 条件4：化神透出天干
        hua_gan_present = any(M.WUXING_GAN[g] == sh["wx"] for g in gans)
        if not hua_gan_present:
            ok = False
            reasons.append("化神%s不透干" % sh["wx"])
        # 条件5：不能有克制化神的五行成强局（排除合局自身成员，仅认本气强根）
        ke_wx = M.KE_OF[sh["wx"]]
        if _has_di_zhi_root(zhis, ke_wx, exclude=set(idx), strong_only=True):
            ok = False
            reasons.append("克化神%s成强局" % sh["wx"])
        # 恋根校验（V1.1.1）：参与地支原五行在局外不得有禄/刃强根
        blocked, lgreason = lian_gen_blocked(zhis, gans, set(idx), set(), sh["wx"], "sanhe", config or {})
        if blocked:
            ok = False
            reasons.append(lgreason)
        for i in idx:
            branch_lock[i] = True
        if ok:
            for i in idx:
                branch_hua[i] = sh["wx"]
                branch_mag[i] = M.Const.SANHE_MAG
            he_groups.append({"type": "sanhe", "members": sh["members"], "idx": idx,
                              "hua_success": True, "hua_wuxing": sh["wx"],
                              "ban": False, "reason": "三合成功"})
        else:
            for i in idx:
                branch_ban[i] = True
                branch_mag[i] = M.Const.BAN_DECAY
            he_groups.append({"type": "sanhe", "members": sh["members"], "idx": idx,
                              "hua_success": False, "hua_wuxing": None,
                              "ban": True, "reason": "; ".join(reasons) or "三合绊"})
        break

    # ---------------------- 3) 天干五合（紧贴相邻） ----------------------
    for a, b in ((0, 1), (1, 2), (2, 3)):
        key = frozenset((gans[a], gans[b]))
        if key not in M.WUHE:
            continue
        if gan_lock[a] or gan_lock[b]:
            continue
        hua_wx = M.WUHE[key]
        ok = True
        reasons = []
        # 条件2：月令为化神旺地
        if month_zhi not in M.HE_HUA_WANG_MONTH[hua_wx]:
            ok = False
            reasons.append("月令非化神%s旺地" % hua_wx)
        # 条件3：化神得地支根气（本气/长生），不是虚透无根
        if not _has_di_zhi_root(zhis, hua_wx, branch_hua=branch_hua):
            ok = False
            reasons.append("化神%s无根虚透" % hua_wx)
        # 条件4：没有克化神的干支强力透干破局
        ke_wx = M.KE_OF[hua_wx]
        for g in (gans[0], gans[1], gans[2], gans[3]):
            if M.WUXING_GAN[g] == ke_wx and _has_di_zhi_root(zhis, ke_wx, branch_hua=branch_hua):
                ok = False
                reasons.append("%s透干克化神%s" % (g, hua_wx))
                break
        # 恋根校验（V1.1.1）：参与天干原五行在局外不得有禄/刃强根（五合无参与地支）
        blocked, lgreason = lian_gen_blocked(zhis, gans, set(), {a, b}, hua_wx, "wuhe", config or {}, branch_hua=branch_hua)
        if blocked:
            ok = False
            reasons.append(lgreason)
        gan_lock[a] = gan_lock[b] = True
        if ok:
            gan_hua[a] = gan_hua[b] = hua_wx
            gan_mag[a] = gan_mag[b] = M.Const.WUHE_MAG
            he_groups.append({"type": "wuhe", "members": [gans[a], gans[b]],
                              "idx": [a, b],
                              "hua_success": True, "hua_wuxing": hua_wx,
                              "ban": False, "reason": "五合成功"})
        else:
            gan_ban[a] = gan_ban[b] = True
            gan_mag[a] = gan_mag[b] = M.Const.WUHE_BAN_DECAY
            he_groups.append({"type": "wuhe", "members": [gans[a], gans[b]],
                              "idx": [a, b],
                              "hua_success": False, "hua_wuxing": None,
                              "ban": True, "reason": "; ".join(reasons) or "五合绊"})

    # ---------------------- 4) 地支六合（最低优先级） ----------------------
    for z1, z2 in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)):
        key = frozenset((zhis[z1], zhis[z2]))
        if key not in M.LIUHE:
            continue
        if branch_lock[z1] or branch_lock[z2]:
            continue
        hua_wx = M.LIUHE[key]
        ok = True
        reasons = []
        # 条件2：月令为化神旺地
        if month_zhi not in M.HE_HUA_WANG_MONTH[hua_wx]:
            ok = False
            reasons.append("月令非化神%s旺地" % hua_wx)
        # 条件3：化神有根（透干或地支本气/长生）
        if not (any(M.WUXING_GAN[g] == hua_wx for g in gans)
                or _has_di_zhi_root(zhis, hua_wx, branch_hua=branch_hua)):
            ok = False
            reasons.append("化神%s无根" % hua_wx)
        # 条件4：六合两支不被本气冲破（冲支存在且未被置换则破）
        for zi in (z1, z2):
            cz = M.CHONG.get(zhis[zi])
            if cz in zhis:
                if any(z == cz and not branch_hua[j] for j, z in enumerate(zhis)):    # 冲支未置换（保留冲力）则破
                    ok = False
                    reasons.append("%s被%s冲" % (zhis[zi], cz))
                    break
        # 恋根校验（V1.1.1）：参与地支原五行在局外不得有禄/刃强根
        blocked, lgreason = lian_gen_blocked(zhis, gans, {z1, z2}, set(), hua_wx, "liuhe", config or {}, branch_hua=branch_hua)
        if blocked:
            ok = False
            reasons.append(lgreason)
        branch_lock[z1] = branch_lock[z2] = True
        if ok:
            branch_hua[z1] = branch_hua[z2] = hua_wx
            branch_mag[z1] = branch_mag[z2] = M.Const.LIUHE_MAG
            he_groups.append({"type": "liuhe", "members": [zhis[z1], zhis[z2]], "idx": [z1, z2],
                              "hua_success": True, "hua_wuxing": hua_wx,
                              "ban": False, "reason": "六合成功"})
        else:
            branch_ban[z1] = branch_ban[z2] = True
            branch_mag[z1] = branch_mag[z2] = M.Const.LIUHE_BAN_DECAY
            he_groups.append({"type": "liuhe", "members": [zhis[z1], zhis[z2]], "idx": [z1, z2],
                              "hua_success": False, "hua_wuxing": None,
                              "ban": True, "reason": "; ".join(reasons) or "六合绊"})

    # ---------------------- 摘要 he_result（最高优先级合局） ----------------------
    he_result = {
        "has_he": len(he_groups) > 0,
        "he_type": None, "he_group": None, "he_hua_success": False,
        "hua_wuxing": None, "he_ban": False,
    }
    if he_groups:
        order = {"sanhuí": 0, "sanhe": 1, "wuhe": 2, "liuhe": 3}
        # 成功优先，其次按阶序
        best = sorted(he_groups, key=lambda g: (not g["hua_success"], order[g["type"]]))[0]
        he_result.update({
            "he_type": best["type"],
            "he_group": best["members"],
            "he_hua_success": best["hua_success"],
            "hua_wuxing": best["hua_wuxing"],
            "he_ban": best["ban"],
        })

    return {
        "branch_hua": branch_hua,
        "branch_mag": branch_mag,
        "branch_ban": branch_ban,
        "branch_lock": branch_lock,
        "gan_hua": gan_hua,
        "gan_mag": gan_mag,
        "gan_ban": gan_ban,
        "gan_lock": gan_lock,
        "he_groups": he_groups,
        "he_result": he_result,
    }
