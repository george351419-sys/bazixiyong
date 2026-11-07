# -*- coding: utf-8 -*-
"""旺衰模块 V1.2 不变量测试（随机抽样，固定种子以保证可复现）。

运行：python3 tests/test_wangshuai_invariants.py
"""
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bazi_core import metadata as M
from bazi_core.wangshuai import compute_wangshuai, _root_level
from bazi_core import heju
from bazi_core import wangshuai as W

GANS = list("甲乙丙丁戊己庚辛壬癸")
ZHIS = list("子丑寅卯辰巳午未申酉戌亥")
TAGS = {"身旺", "身弱", "中和偏旺", "中和偏弱", "身弱无根", "虚旺",
        "从强", "从弱", "假从强", "假从弱", "独根无伤"}
CONG_TAGS = {"从强", "从弱"}
FAKE_TAGS = {"假从强", "假从弱"}
N = 2000
SEED = 20261106

fails = []


def bad(i, msg):
    fails.append((i, msg))


def run():
    rng = random.Random(SEED)
    for i in range(N):
        gans = [rng.choice(GANS) for _ in range(4)]
        zhis = [rng.choice(ZHIS) for _ in range(4)]
        r = compute_wangshuai({"gans": gans, "zhis": zhis})
        s = " ".join(a + b for a, b in zip(gans, zhis))

        # i1 tag 合法
        if r["tag"] not in TAGS - {"独根无伤"}:
            bad(i, "i1 tag 非法 %s %s" % (s, r["tag"]))
        # i2 从格标签必须带 is_cong
        if r["tag"] in CONG_TAGS and not r["cong_info"]["is_cong"]:
            bad(i, "i2 从格未标记 %s" % s)
        # i3 假从必须 is_fake_cong 且置信度 ≤0.5
        if r["tag"] in FAKE_TAGS:
            if not r["cong_info"]["is_fake_cong"] or r["confidence"] > 0.5:
                bad(i, "i3 假从标记/置信度 %s %s" % (s, r["confidence"]))
        # i4 非从格/非假从时 is_cong 必须为 False
        if r["tag"] not in CONG_TAGS and r["cong_info"]["is_cong"]:
            bad(i, "i4 误标从格 %s %s" % (s, r["tag"]))
        # i5 F+K 恒正、占比互斥且相加为 1
        if r["F"] + r["K"] <= 0:
            bad(i, "i5 F+K 非正 %s" % s)
        if abs(r["ratio_share_f"] + r["ratio_share_k"] - 1.0) > 0.002:
            bad(i, "i5 占比不互补 %s %s/%s" % (s, r["ratio_share_f"], r["ratio_share_k"]))
        # i6 ratio 与 ratio_fk 一致（旧字段兼容）
        if abs(r["ratio"] - r["ratio_fk"]) > 1e-9:
            bad(i, "i6 ratio 不一致 %s" % s)
        # i7 从格必达占比门槛
        ct = M.Const.CONG_THRESHOLD
        if r["tag"] in ("从弱", "假从弱") and r["ratio_share_k"] < ct - 1e-9:
            bad(i, "i7 从弱未达门槛 %s %s" % (s, r["ratio_share_k"]))
        if r["tag"] in ("从强", "假从强") and r["ratio_share_f"] < ct - 1e-9:
            bad(i, "i7 从强未达门槛 %s %s" % (s, r["ratio_share_f"]))
        # i8 根明细能量之和应与 root_energy 一致（计入冲折后不再分叉）
        eff = sum(x["eff_energy"] for x in r["debug"]["root_list"])
        if abs(eff - r["root_energy"]) > 0.06:
            bad(i, "i8 根能量分叉 %s %s vs %s" % (s, eff, r["root_energy"]))
        # i9 无根/拔根结论必须 root_energy == 0
        if r["root_status"] in ("无根", "独根被冲拔根") and r["root_energy"] != 0:
            bad(i, "i9 无根却有根能量 %s %s" % (s, r["root_energy"]))
        # i10 身弱无根/虚旺 只能在无根或拔根盘出现
        if r["tag"] in ("身弱无根", "虚旺") and r["root_status"] not in ("无根", "独根被冲拔根"):
            bad(i, "i10 有根盘判无根档 %s %s/%s" % (s, r["root_status"], r["tag"]))
        # i11 虚旺必须过「虚势 + 生扶占比」双门槛
        if r["tag"] == "虚旺":
            if r["void_momentum"] < M.Const.VOID_WANG_TRIGGER:
                bad(i, "i11 虚旺虚势不足 %s %s" % (s, r["void_momentum"]))
            if r["ratio_share_f"] < M.Const.VOID_WANG_MIN_SHARE_F - 1e-9:
                bad(i, "i11 虚旺占比不足 %s %s" % (s, r["ratio_share_f"]))
        # i12 地支明细必须覆盖 4 支，且冲折系数 ∈ [0.5, 1]
        bd = r["debug"]["branch_detail"]
        if len(bd) != 4:
            bad(i, "i12 地支明细缺失 %s" % s)
        for b in bd:
            if not (0.5 - 1e-9 <= b["chong_factor"] <= 1.0 + 1e-9):
                bad(i, "i12 冲折系数越界 %s %s" % (s, b["chong_factor"]))
        # i13 克泄耗天干满力：k_dry_unrooted 只做标记，对应天干贡献必须等于 base
        gd = {x["pos"]: x for x in r["debug"]["gan_detail"]}
        for k in r["debug"]["k_dry_unrooted"]:
            g = gd.get(k["pos"])
            if g is None or g["root_level"] != 0:
                bad(i, "i13 K 干标记与明细不一致 %s pos=%s" % (s, k["pos"]))
            elif abs(g["contribution"] - k["base"]) > 1e-6:
                bad(i, "i13 K 干被折力 %s pos=%s %.2f/%.2f"
                    % (s, k["pos"], g["contribution"], k["base"]))
        # i14 结果可 JSON 序列化
        try:
            import json
            json.dumps(r, ensure_ascii=False)
        except Exception as e:
            bad(i, "i14 不可序列化 %s %s" % (s, e))

        # ---- 从格专项（定稿口径）守护 ----
        # i15 真从弱 ⇒ 日主「真无根」：四档辨根 level==0，或独根被冲拔根
        if r["tag"] == "从弱":
            lv = r["debug"]["root_level"]
            if not (lv == 0 or r["root_status"] == "独根被冲拔根"):
                bad(i, "i15 真从弱却有根 %s lv=%s/%s" % (s, lv, r["root_status"]))
        # i16 假从弱 ⇒ 必须有「不从」的证据：日主有根(≥微根) / 印根 / 比劫根
        if r["tag"] == "假从弱":
            ci = r["cong_info"]
            has_root = r["debug"]["root_level"] >= 1 or r["root_status"] == "独根被冲拔根"
            if not (has_root or ci.get("residual_yin_root") or ci.get("residual_bi_root")):
                bad(i, "i16 假从弱无证据 %s" % s)
        # i16b 假从弱不得出现在「真无根且印比皆无强根」的盘
        if r["tag"] == "假从弱":
            ci = r["cong_info"]
            if (r["debug"]["root_level"] == 0 and not ci.get("residual_yin_root")
                    and not ci.get("residual_bi_root")
                    and r["root_status"] != "独根被冲拔根"):
                bad(i, "i16b 无证据却判假从 %s" % s)
        # i17 从强须 F 占比达门槛且未落成假从（由 i7/i3 覆盖），此处只校验从强不进假从标记
        if r["tag"] == "从强" and r["cong_info"].get("is_fake_cong"):
            bad(i, "i17 从强误标假从 %s" % s)
        # i19 从强侧残余强根证据：真从强 ⇒ 即使把库全开也挖不出克泄耗强根；假从强 ⇒ 必须挖得出
        if r["tag"] in ("从强", "假从强"):
            day_wx = M.WUXING_GAN[gans[2]]
            all_open = {j for j, zz in enumerate(zhis) if zz in M.STORE_ZHI}
            strong_max = W._strong_root_gan(zhis, r["debug"]["branch_hua"], all_open) - {day_wx}
            k_wx = {M.KE_OF[day_wx], M.KE[day_wx]}
            k_wx |= {w for w in M.WUXING_LIST
                     if M.SHENG[w] in k_wx and w != day_wx and w != W._sheng_wo(day_wx)}
            has_max = bool(strong_max & k_wx)
            if r["cong_info"].get("residual_k_root") is False and has_max:
                bad(i, "i19 标真从强但克泄耗有强根 %s" % s)
            if r["cong_info"].get("residual_k_root") is True and not has_max:
                bad(i, "i19 标假从强却查无强根证据 %s" % s)

        # i20 两套长生口径（五行级 / 天干级）在「支须真藏该干」前提下恒等，防止长生表被改后静默分叉
        wx_set = W._strong_root_wuxing(zhis, r["debug"]["branch_hua"], set())
        gan_set = W._strong_root_gan(zhis, r["debug"]["branch_hua"], set())
        if wx_set != gan_set:
            bad(i, "i20 两套强根口径不一致 %s %s %s" % (s, sorted(wx_set), sorted(gan_set)))

        # i21 假从弱若以「日主中气根」立论，则该根必须被冲/被绊/居远位（P4 证据门槛）
        if r["tag"] == "假从弱" and "中气根" in "".join(r["warning"]):
            he = heju.evaluate(gans, zhis)
            if not W._cong_fake_weak_root_evidence(r["debug"]["root_list"], zhis, he, {}):
                bad(i, "i21 中气根贴身处仍判假从弱 %s" % s)

        # i18 比劫强根来源：真从弱不得同时标 residual_bi_root
        if r["tag"] == "从弱" and r["cong_info"].get("residual_bi_root"):
            bad(i, "i18 真从弱却标比劫强根 %s" % s)

    print("\n========================================")
    print("旺衰不变量测试：%d 盘（seed %d），失败 %d" % (N, SEED, len(fails)))
    for i, m in fails[:20]:
        print("  x #%d %s" % (i, m))
    if fails:
        print("结果：FAIL")
        return 1
    print("结果：PASS")
    return 0


if __name__ == "__main__":
    sys.exit(run())
