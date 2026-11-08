# -*- coding: utf-8 -*-
"""八字喜用判断 · 命令行入口（旺衰 + 子平格局 + 调候维度）。

用法：
  # 自然语言生辰（公历/农历自动识别），真太阳时 + 经度
  python cli.py --birth "1990年五月初五辰时" --sex male --lon 117.2 --truesun
  # 显式公历
  python cli.py --y 1990 --m 5 --d 5 --h 8 --minute 0 --sex male --lon 117.2 --truesun
  # 直接给四柱（跳过排盘）
  python cli.py --chart "庚午 甲申 庚子 壬午" --solar-term-day 5 --trace
  # 输出纯 JSON
  python cli.py --birth "..." --json

输出：旺衰判定 + 旺衰维度喜用 + 独立格局维度 + 格局维度喜用 + 调候维度
      （《穷通宝鉴》十干逐月取用；调候已上线，作为独立维度输出，V1 不做三维加权）。
  分段格（乙·酉 白露／秋分、乙·午 夏至、癸·辰 清明／谷雨）可用
  --tiaohou-segment 指定，如 --tiaohou-segment 段B；排盘模式会自动按节气推断。
排盘模式仍自动推算「节气后第几天」，但新口径下人元司令不参与取格，
仅作 siling_gan 参考字段；取格按「唯一透出 / 多透按本气>中气>余气 / 都不透取本气标暗格」。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bazi_core.paipan import analyze_birth
from bazi_core.engine import analyze
from bazi_core.tiaohou import format_tiaohou
from bazi_core.input_contracts import normalize_chart


def _parse_chart(s):
    parts = s.split()
    if len(parts) != 4:
        raise ValueError("--chart 需形如 '庚午 辛巳 癸巳 乙卯'（四柱干支，空格分隔）")
    order = ["year", "month", "day", "hour"]
    chart = {}
    for i, p in enumerate(parts):
        if len(p) != 2:
            raise ValueError("干支格式应为 2 字：%s" % p)
        chart[order[i]] = {"gan": p[0], "zhi": p[1]}
    return chart


def _pretty(out, show_trace=False):
    if not out.get("ok"):
        return "分析失败：%s（阶段：%s）" % (out.get("error"), out.get("stage"))
    meta = out.get("paipan_meta", {})
    ws = out["wangshuai"]
    xy = out["xiyong_wangshuai"]
    lines = []
    if meta.get("八字"):
        lines.append("八字：%s  日主：%s（%s）" % (meta["八字"], meta["日主"], out["day_wuxing"]))
        if meta.get("公历"):
            lines.append("公历：%s   农历：%s   生肖：%s" % (meta["公历"], meta.get("农历"), meta.get("生肖")))
        sti = out.get("solar_term_info")
        if sti and sti.get("jie_name"):
            lines.append("节气：%s %s 后第 %s 天（%.2f 天，来源：%s）"
                         % (sti["jie_name"], sti.get("jie_time"), sti["day"],
                            sti.get("exact_days") or 0, out.get("solar_term_source")))
        elif sti:
            lines.append("节气：手工指定第 %s 天（来源：manual）" % sti["day"])
        elif out.get("solar_term_source") == "unavailable":
            lines.append("节气：自动推算不可用，司令表按兜底口径取格")
        if meta.get("真太阳时校正分钟") is not None:
            lines.append("真太阳时校正：%s 分钟%s" % (meta["真太阳时校正分钟"],
                      "（夏令时回拨）" if meta.get("夏令时回拨") else ""))
    lines.append("-" * 40)
    lines.append("旺衰判定：%s   置信度：%s" % (out["tag"], out["confidence"]))
    profile=ws.get("calculation_profile",{})
    if profile.get("include_day_stem_requested") and not profile.get("include_day_stem_effective"):
        lines.append("兼容配置：关闭季节层时回放旧计分，日干计分开关不独立生效。")
    season=ws.get("seasonal_assessment")
    if season:
        lines.append("月令系数："+json.dumps(season["factors"],ensure_ascii=False))
        lines.append("含日干生扶占比：%.1f%%" % (100*season["day_stem_diagnostic"]["inclusive_share"]))
        lines.append("日干贡献：%.2f；原七字占比：%.1f%%" % (season["day_stem_diagnostic"]["contribution"],100*season["external_share"]))
    lines.append("兼容结构根记录：%s   F(生扶)=%s   K(克泄耗)=%s%s"
                 % (ws.get("root_status"), ws.get("F"), ws.get("K"),
                    ("   ratio=%.2f" % ws["ratio"]) if ws.get("ratio") is not None else ""))
    if ws.get("warning"):
        lines.append("备注：" + "；".join(ws["warning"]))
    lines.append("-" * 40)
    final=out.get('final_xiyong',{})
    lines.append('当前取用方向：%s；忌：%s' % (' '.join(final.get('favored',[])) or '待判',' '.join(final.get('disliked',[])) or '未定'))
    lines.append('裁决：%s；范围：%s；方向发布：%s；行动发布：%s' %
        (final.get('decision_status'),final.get('decision_scope'),final.get('release_ready'),final.get('action_release_ready')))
    if final.get('structure_primary'):
        lines.append('格局结构主用：'+' '.join(x['gan']+'（'+x['shishen']+'）' for x in final['structure_primary']))
        lines.append('格局结构第二用：'+' '.join(x['gan']+'（'+x['shishen']+'）' for x in final.get('structure_secondary',[])))
    if final.get('stem_ranking'):
        groups={}
        for item in final['stem_ranking']: groups.setdefault(item['rank'],[]).append(item['gan'])
        lines.append('喜用字：'+' > '.join('≈'.join(v) for v in groups.values()))
    element_groups={}
    for row in final.get('element_ranking',[]):
        if row.get('selected'): element_groups.setdefault(row['rank'],[]).append(row['wuxing'])
    if element_groups: lines.append('喜用五行层级：'+' > '.join('≈'.join(v) for v in element_groups.values()))
    if any(row.get('cutoff_tie') for row in final.get('stem_ranking',[])): lines.append('喜用字截断处存在并列；同分未展示字：'+ '、'.join(final.get('cutoff_tied_gans',[])))
    if any(row.get('cutoff_tie') for row in final.get('element_ranking',[])): lines.append('五行数量截断处存在并列：未展示同分项不表示更差或为忌。')
    for row in final.get('stem_ranking',[]):
        if row.get('conditions'): lines.append('候选条件 '+row['gan']+'：'+'；'.join(row['conditions']))
    for conflict in final.get('structural_conflicts',[]):
        lines.append('结构冲突 '+conflict['gan']+'：'+str(conflict['name'])+'；'+conflict['condition'])
    for plan in final.get('luck_plans',[]):
        lines.append('待运方案：'+str(plan['name'])+'；处理字：'+(' '.join(plan['target_gans']) or '未指明')+'；候选字：'+(' '.join(plan['candidate_gans']) or '未指明'))
        lines.append('  治法：'+'；'.join(plan['methods']))
    if final.get('primary_status')=='tied': lines.append('方向并列首选：'+'≈'.join(final['primary_gans']))
    if final.get('primary_gan'): lines.append('方向首用：'+final['primary_gan']+'；辅助五行：'+' '.join(final.get('secondary',[])))
    if final.get("caution"): lines.append("慎用/条件使用："+" ".join(final["caution"]))
    if final.get("unselected"): lines.append("未入选："+" ".join(final["unselected"]))
    if not final.get("stem_ranking"): lines.append(final.get("stem_ranking_note",""))
    if final.get("tiaohou_avoid_pending_review"): lines.append("调候待核忌字："+" ".join(final["tiaohou_avoid_pending_review"]))
    lines.append('当前依据：'+final.get('principle',''))
    lines.append(final.get('note',''))
    if out.get('input_validation',{}).get('input_kind')=='rule_case': lines.append('输入为规则构造案例，不表示存在对应出生日期。')
    for p in final.get('positions',[]):
        lines.append('路线作用：%s %s；目标：%s' % (p.get('gan') or p.get('wx'),p.get('action'),p.get('target_id','方向')))
        if p.get('dose_plan'):
            plan=p['dose_plan'];lines.append('  投用：%s %s；上限：%s；投用ID：%s' %
                (plan['amount'],plan['unit'],plan['max_amount'],p.get('application_id')))
        if p.get('condition_expr'): lines.append('  条件：'+json.dumps(p['condition_expr'],ensure_ascii=False))
    lines.append("-" * 40)
    lines.append("喜用维度（旺衰）：%s" % xy["category"])
    lines.append("  喜用五行：%s" % " ".join(xy["favored"]))
    lines.append("  忌神五行：%s" % " ".join(xy["disliked"]))
    fp=xy.get("stem_preferences",{})
    if fp.get("weak"):
        groups={}
        for item in fp.get("ranked_gans",[]): groups.setdefault(item["rank"],[]).append(item["gan"]+"（"+item["shishen"]+"）")
        lines.append("  扶抑字序："+" > ".join("≈".join(v) for v in groups.values()))
        lines.append("  扶抑分型："+("极弱" if fp.get("extreme_weak") else "一般弱/中和偏弱")+"；有效根："+str(fp.get("rooted")))
    if xy.get("neutral"):
        lines.append("  中性/慎用：%s" % " ".join(xy["neutral"]))
    lines.append("  取用原则：%s" % xy["principle"])
    if xy.get("note"):
        lines.append("  说明：%s" % xy["note"])
    lines.append("-" * 40)

    gj = out.get("geju")
    if gj:
        lines.append("子平格局：%s（%s）   状态：%s   清浊：%s"
                     % (gj["main_ge_name"], gj["ge_category"],
                        gj["ge_status"], gj["clean_level"]))
        lines.append("  格神：%s" % gj["ge_shen"])
        if gj.get("an_ge_flag"):
            lines.append("  ※ 暗格：月令无有效透出，取本气为格（依据：%s）"
                         % gj.get("quge_basis", ""))
        if gj.get("bijiao_tou"):
            lines.append("  ※ 月令透出比劫%s：该字不取格神" % "、".join(gj["bijiao_tou"]))
        lines.append("  相神：%s" % ("、".join(gj["xiang_shen_list"]) or "不显"))
        lines.append("  忌神：%s" % ("、".join(gj["ji_shen_list"]) or "无"))
        if gj.get("lu_ren_flag"):
            lines.append("  ※ 禄刃月令，非八格；透干只作相神，不升格")
        if gj.get("special_ge"):
            lines.append("  外格：%s" % gj["special_ge"])
        lines.append("  司令：%s（仅供参考，不参与取格）   旺衰（附加）：%s / %.2f"
                     % (gj.get("siling_gan"), gj.get("wangshuai_tag"),
                        gj.get("wangshuai_confidence") or 0))
        lines.append("  备注：%s" % gj["note"])
        # Step8 格局维度喜用（李师傅笔记口径，独立层、不与旺衰加权）
        xyj = gj.get("xiyong_geju")
        if xyj:
            lines.append("  格局喜用：%s（%s）"
                         % (xyj["mode"], "有病·治病为先" if xyj["has_bing"]
                            else "无病·顺逆取用"))
            for b in xyj["bing_list"]:
                lines.append("    病：%s【%s】→ 药：%s"
                             % (b["name"], b["severity"],
                                "；".join(b["yao"][:2]) or "待运"))
            lines.append("    用神：%s" % ("；".join(xyj["yong_shen_list"]) or "不显"))
            if xyj["xi_shen_list"]:
                lines.append("    辅佐：%s" % "；".join(xyj["xi_shen_list"]))
            lines.append("    原则：%s" % xyj["principle"])
            if xyj.get("fuyi_hint"):
                lines.append("    扶抑（附加）：%s" % xyj["fuyi_hint"])
            if xyj.get("tiaohou_pending"):
                lines.append("    ※ 调候维度已独立上线（见下方），但本层格局喜用尚未把「调候之病」并入病清单；笔记以调候之病最优先")
        lines.append("-" * 40)
        if show_trace:
            lines.append("格局判定链路：")
            for i, t in enumerate(gj["trace_log"], 1):
                lines.append("  %2d. %s" % (i, t))
            lines.append("-" * 40)

    th = out.get("tiaohou")
    if th and th.get("ok"):
        lines.append(format_tiaohou(th, verbose=True))
    elif th:
        lines.append("调候维度：计算失败（%s）" % th.get("error"))

    mods = out.get("modules", {})
    lines.append("-" * 40)
    lines.append("三维计算：旺衰=%s，格局=%s，调候=%s（方向融合与严格仲裁分层输出）"
                 % (mods.get("wangshuai"), mods.get("geju"), mods.get("tiaohou")))
    lines.append("旺衰兼容展示分（不作融合权重） effective_ws = 25 × %.2f = %.2f"
                 % (out["confidence"], out["score_wangshuai"]["effective_ws"]))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="八字喜用判断（旺衰 + 子平格局，代码确定性引擎）")
    ap.add_argument("--birth", help="自然语言生辰，如 '1990年五月初五辰时'")
    ap.add_argument("--y", type=int, help="公历/农历年")
    ap.add_argument("--m", type=int, help="月")
    ap.add_argument("--d", type=int, help="日")
    ap.add_argument("--h", type=int, help="时（24 小时制）")
    ap.add_argument("--minute", type=int, default=0, help="分钟")
    ap.add_argument("--second", type=int, default=0, help="秒")
    ap.add_argument("--sex", default="male", choices=["male", "female"], help="性别")
    ap.add_argument("--lon", type=float, default=None, help="出生地经度（度），配合 --truesun")
    ap.add_argument("--truesun", action="store_true", help="启用真太阳时 + 夏令时回拨")
    ap.add_argument("--lunar", action="store_true", help="--y/--m/--d/--h 为农历")
    ap.add_argument("--leap", action="store_true", help="农历闰月")
    ap.add_argument("--chart", help="直接给四柱，如 '庚午 辛巳 癸巳 乙卯'（跳过排盘）")
    ap.add_argument('--rule-case',action='store_true',help='显式允许不满足历法一致性的规则构造案例')
    ap.add_argument('--sect',type=int,choices=[1,2],default=2,help='晚子时日柱约定，默认2')
    ap.add_argument('--eot',action='store_true',help='经度校正另加均时差，需--truesun及--lon')
    ap.add_argument("--solar-term-day", type=int, default=None,
                    help="节气后第几天（司令参考/调候近似分段；不参与取格）")
    ap.add_argument("--trace", action="store_true", help="打印格局判定链路日志")
    ap.add_argument("--no-special-ge", action="store_true", help="关闭外格前置筛查")
    ap.add_argument("--tiaohou-segment", default=None,
                    help="调候节气分段，如 段A/段B/上半月/下半月/清明后/谷雨后；不传自动推断")
    ap.add_argument("--json", action="store_true", help="输出原始 JSON")
    args = ap.parse_args()

    config = {"enable_special_ge": not args.no_special_ge} if args.no_special_ge else None

    if args.chart:
        try:
            chart = _parse_chart(args.chart)
            chart['input_kind']='rule_case' if args.rule_case else 'real_chart'
            chart,_=normalize_chart(chart,default_kind='real_chart')
        except ValueError as e:
            print("参数错误：%s" % e); sys.exit(2)
        if args.solar_term_day is not None:
            chart["solar_term_day"] = args.solar_term_day
        try: out = analyze(chart, config=config, tiaohou_segment=args.tiaohou_segment)
        except ValueError as exc: print('参数错误：'+str(exc));sys.exit(2)
        out["input"] = chart
    elif args.birth or (None not in (args.y, args.m, args.d, args.h)):
        out = analyze_birth(birth=args.birth, y=args.y, m=args.m, d=args.d, h=args.h,
                            minute=args.minute, second=args.second, sex=args.sex, lon=args.lon,
                            truesun=args.truesun, lunar=args.lunar, leap=args.leap,
                            config=config, solar_term_day=args.solar_term_day,
                            tiaohou_segment=args.tiaohou_segment,sect=args.sect,eot=args.eot)
    else:
        ap.print_help()
        print("\n需提供 --birth / --y --m --d --h / --chart 之一。")
        sys.exit(2)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(_pretty(out, show_trace=args.trace))


if __name__ == "__main__":
    main()
