# -*- coding: utf-8 -*-
"""顶层分析引擎：旺衰 → 旺衰维度喜用映射 + 子平格局 + 调候维度（PRD §7 对接契约）。

三个维度各自独立、互不干预：
  - 旺衰维度（wangshuai）：tag / confidence / 喜忌映射 / effective_ws；
  - 格局维度（geju）：纯月令取格、相神忌神、成破救应（旺衰仅作附加字段，
    **不参与定格、清浊、成破逻辑** —— 格局 PRD §六.8）；
  - 格局维度喜用（geju.xiyong_geju）：李厚君师傅笔记口径「有病治病为先，
    无病吉神顺用/凶神逆用」，独立于定格流程的 Step8，不加权、不推翻定格；
  - 调候维度（tiaohou）：《穷通宝鉴》十干逐月取用，由日干＋月令定，
    输出默认通用序列 / 条件用 / 忌 / 原局透藏 / 另读。

不做三维加权合并：普通方向暂取旺衰；特殊结构由统一仲裁验真。
已审定评估器可以提交跨维度路线，经需求、条件、药效、剂量和资源校验后发布。
默认生产评估依据不足时保持pending。当前规则索引见validation/project_audit_v29.md。
"""
from __future__ import annotations

from . import metadata as M
from .wangshuai import compute_wangshuai
from .geju import compute_geju
from .tiaohou import compute_tiaohou
from .input_contracts import normalize_chart

# 旺衰维度原始满分（PRD §7.2）
BASE_WANGSHUAI_SCORE = 25.0


def _relations_of(day_wx):
    """返回日主五行 day_wx 的十神五行归类。

    印(生我) / 比劫(同我) / 食伤(我生) / 财(我克) / 官杀(克我)。
    """
    yin = None      # 生我（印）
    bijie = day_wx  # 同我（比劫）
    shishen = M.SHENG[day_wx]   # 我生（食伤）
    cai = M.KE[day_wx]          # 我克（财）
    guansha = M.KE_OF[day_wx]   # 克我（官杀）
    for w in M.WUXING_LIST:
        if M.SHENG[w] == day_wx:
            yin = w
    return {
        "印": yin, "比劫": bijie, "食伤": shishen,
        "财": cai, "官杀": guansha,
    }


def xiyong_for_tag(tag, day_wx, ws=None):
    """根据旺衰 tag 与日主五行，给出旺衰维度的喜用映射（PRD §7.3）。

    返回 dict：
      favored   : 喜用五行 list
      disliked  : 忌神五行 list
      neutral   : 中性 / 慎用五行 list
      category  : 喜用类别（克泄耗 / 生扶 / 泄秀生财…）
      principle : 取用原则一句话
      note      : 补充说明（如虚旺、假从的特殊处理）
    """
    rel = _relations_of(day_wx)
    shengfu = [rel["印"], rel["比劫"]]          # 生扶
    kexiehao = [rel["食伤"], rel["财"], rel["官杀"]]  # 克泄耗

    # 默认占位
    out = {
        "favored": [], "disliked": [], "neutral": [],
        "category": "", "principle": "", "note": "",
    }

    if tag in ("身旺", "中和偏旺"):
        out.update(favored=kexiehao, disliked=shengfu, category="克泄耗",
                   principle="身旺（偏旺），喜克、泄、耗以达平衡，忌再加印比生扶。")
    elif tag in ("身弱", "中和偏弱", "身弱无根"):
        # 身弱 / 中和偏弱 / 身弱无根（无根真弱）：均按身弱论，喜印比生扶帮身。
        # 身弱无根额外提示：日主无根，喜生扶但需大运补根或防冲，帮扶宜有根为佳。
        note = ""
        if tag == "身弱无根":
            note = "日主原局无根（独根被拔或本就无根），虽喜印比生扶，但帮扶干支宜有根方实；无根之命逢冲尤需谨慎。"
        out.update(favored=shengfu, disliked=kexiehao, category="生扶",
                   principle="身弱（偏弱），喜印、比劫生扶帮身，忌克泄耗过度。",
                   note=note)
    elif tag == "从强":
        out.update(favored=shengfu, disliked=kexiehao, category="生扶（顺旺势）",
                   principle="从强格，日主极旺不可逆，喜顺其势生扶，忌克泄耗破格。")
    elif tag == "从弱":
        out.update(favored=kexiehao, disliked=shengfu, category="克泄耗（顺弱势）",
                   principle="从弱格，日主极弱不可逆，喜顺其势克泄耗，忌印比帮身。")
    elif tag == "假从强":
        out.update(favored=shengfu, disliked=kexiehao, category="生扶（去病为先）",
                   principle="假从强，表面从旺但残存克泄耗强根，先去病（克泄耗）再顺旺势生扶；置信低，建议结合大运。")
    elif tag == "假从弱":
        out.update(favored=kexiehao, disliked=shengfu, category="克泄耗（去病为先）",
                   principle="假从弱，残存帮扶证据使真从条件不完整；取用需先核对残根或印星干扰，再考虑顺势。")
    elif tag == "虚旺":
        # PRD §7.3：虚旺 ≠ 真旺；忌印比再帮扶，不耐强官杀直克。
        # 实务按「无根假旺」取用：喜食伤、财泄秀生财；印比再帮反成虚浮；
        # 官杀可制但日主无根不耐直克，需有根方可，列为中性慎用。
        out.update(favored=[rel["食伤"], rel["财"]],
                   disliked=[rel["印"], rel["比劫"]],
                   neutral=[rel["官杀"]],
                   category="泄秀生财（无根假旺）",
                   principle="虚旺（无根假旺）：喜食伤、财泄秀生财；忌印比再帮扶（加重虚浮）；官杀可制但日主无根不耐直克，需配他根方可用。")
        out["note"] = "虚旺与真旺相反，不可套用常规身旺喜克泄耗的粗暴结论；原局无根，帮扶印比反而虚浮不实。"
    else:
        out.update(favored=[], disliked=[], category="未定",
                   principle="未识别到明确旺衰标签，建议人工复核。")
    if tag == "假从弱":
        evidence = []
        roots = (ws or {}).get("effective_roots", [])
        for root in roots:
            if root["is_broken"]:
                continue
            rt = root["root_type"]
            category = ("微根残存" if rt in ("微根", "余气根") else
                        "中气残存" if rt == "中气根" else
                        "开库次强根残存" if rt == M.ROOT_MEDIUM else "强根残存")
            evidence.append({"kind": category, "branch_index": root["branch_index"],
                             "root_type": rt, "eff_energy": root["eff_energy"]})
        if (ws or {}).get("cong_info", {}).get("residual_yin_root"):
            evidence.append({"kind": "印星强根干扰", "wuxing": rel["印"]})
        labels = list(dict.fromkeys(e["kind"] for e in evidence))
        out.update(residual_support=evidence, conditional=True, requires_review=True,
                   note="本盘证据：" + ("、".join(labels) if labels else "未提供原局证据，需核实") +
                   "。去病对象须按上述具体证据判断；喜用列表是方向候选，不表示所有克泄耗都宜继续加强。")
    if tag == "假从强":
        evidence = [dict(e, kind="克泄耗强根残存") for e in
                    (ws or {}).get("cong_info", {}).get("residual_k_evidence", [])]
        labels = ["%s%s（%s，有效能量%s）" %
                  (["年支", "月支", "日支", "时支"][e["branch_index"]], e["wuxing"],
                   "受冲绊" if e["damaged"] else "未见冲绊", e.get("eff_energy", "待核"))
                  for e in evidence]
        out.update(residual_opposition=evidence, conditional=True, requires_review=True,
                   principle="假从强，残存克泄耗强根使真从条件不完整；先核对具体干扰，再考虑顺旺势生扶。",
                   note="本盘证据：" + ("、".join(labels) if labels else "未提供原局证据，需核实") +
                   "。去病对象须按上述位置与五行判断；喜用列表是方向候选，不表示所有印比都宜继续加强。")
    return out


def analyze(chart, config=None, tiaohou_segment=None, fusion_provider=None):
    """顶层分析入口（旺衰 + 格局 + 调候）。

    参数:
        chart : PRD 输入 JSON（year/month/day/hour 各 {gan,zhi} 或扁平 gans/zhis）；
                可带 solar_term_day、jie_name（节气后天数与节气名，供调候分段）、
                tiaohou_segment、night 等辅助字段。
        config: 超参（可选；enable_special_ge 控制格局外格兜底；
                tiaohou 子 dict 传给调候模块，如 {half_month_day:15}）
        tiaohou_segment: 显式节气分段（如「段B」「下半月」「谷雨后」），
                         用于乙·酉／乙·午／癸·辰等原书分段格；不传则自动推断。
    返回: 结构化结果 dict（旺衰 + 旺衰维度喜用 + 格局 + 独立调候维度）
    """
    chart,input_validation=normalize_chart(chart)
    ws = compute_wangshuai(chart, config=config)
    day_wx = ws["day_wuxing"]
    tag = ws["tag"]
    confidence = ws["confidence"]

    # 格局模块复用已算好的旺衰结果（仅作附加字段与外格门槛，不参与定格）
    geju_out = compute_geju(chart, config=config, ws=ws)

    # 调候维度：独立计算，不参与旺衰／格局，也不改写 final_xiyong
    th_cfg = (config or {}).get("tiaohou") if isinstance(config, dict) else None
    try:
        tiaohou_out = compute_tiaohou(chart, segment=tiaohou_segment, config=th_cfg)
    except (ValueError, KeyError) as e:
        tiaohou_out = {"ok": False, "error": str(e), "module": "tiaohou_v1"}

    xiyong = xiyong_for_tag(tag, day_wx, ws=ws)
    effective_xiyong = dict(xiyong)
    effective_source = "wangshuai"
    wangshuai_applicable = True
    special_ge = geju_out.get("special_ge")
    geju_overrides_wangshuai = bool(special_ge and "化" in special_ge)
    if tag in ("假从弱", "假从强") and not geju_overrides_wangshuai:
        ordinary_tag = "身弱" if tag == "假从弱" else "身旺"
        effective_xiyong = xiyong_for_tag(ordinary_tag, day_wx, ws=ws)
        effective_source = "ordinary_structure_fallback"

    effective_ws = round(BASE_WANGSHUAI_SCORE * confidence, 3)

    final_note = (
        "V1 不加权合并：final_xiyong 默认仍等于旺衰维度；格局喜用见 "
        "geju_xiyong（李厚君师傅笔记口径：有病治病为先 / 无病顺逆取用）。"
        "调候模块已上线，作为独立维度见 tiaohou（由日干＋月令定，《穷通宝鉴》"
        "逐月取用）——调候 ≠ 全局用神，不覆盖旺衰／格局维度，此处只附摘要；"
        "格局喜用 Step8 的「调候之病最优先」尚未合并。普通融合须具备经审定的需求、药效与承受证据；不以加权代替裁决。"
    )

    if tag in ("假从弱", "假从强") and not geju_overrides_wangshuai:
        final_note = "假从转真条件未满足，普通身弱／身旺方向仅作暂定；顺从方向仅为条件候选，尚未完成跨维度裁决。"

    from .arbitration import build_facts, arbitrate
    facts=build_facts(ws,geju_out,tiaohou_out,effective_xiyong)
    if (config or {}).get('fusion_evidence') is not None:
        from copy import deepcopy
        facts['fusion_evidence']=deepcopy(config['fusion_evidence'])
    if fusion_provider is not None:
        if not callable(fusion_provider): raise ValueError('fusion_provider必须为内部评估函数')
        if 'fusion_evidence' in facts: raise ValueError('不可同时提供fusion_provider与fusion_evidence')
        from .scenario_evaluation import prepare_fusion_context
        facts['fusion_evidence']=fusion_provider(prepare_fusion_context(facts,(config or {}).get('climate_model')))
    arbitration=arbitrate(facts,(config or {}).get('climate_model'))
    if (arbitration.get('mode')=='external' and arbitration.get('decision_status')=='pending') or arbitration.get('fact_validation',{}).get('status')=='invalid':
        effective_xiyong.update(favored=[], disliked=[], neutral=[])
        effective_source='unresolved_external_conflict' if 'conflict' in arbitration.get('reason_code','') else 'invalid_external_facts'
        wangshuai_applicable=False
        final_note=arbitration.get('priority_reason','事实校验未通过，暂停最终裁决。')
    if arbitration.get('mode') in ('external','integrated') and arbitration.get('decision_status') in ('decided','conditional'):
        effective_xiyong.update(favored=arbitration['favored'],disliked=arbitration['avoid'],neutral=[])
        effective_source='arbitration_integrated' if arbitration['mode']=='integrated' else 'arbitration_external'
        wangshuai_applicable=False
        final_note=arbitration['priority_reason']
    geju_overrides_wangshuai=arbitration.get('structure_kind')=='hua' and arbitration['decision_status']=='decided'
    return {
        "arbitration": arbitration,
        "ok": True,
        "input_validation": input_validation,
        "input": chart,
        "rule_versions": dict(project='project_audit_v29',wangshuai=ws.get('rules_version'),
            fusion=arbitration['policy_version'],geju='geju_v2_cong_separation',
            tiaohou='tiaohou_v2_complete_conditions'),
        "engine_version": "wangshuai_v1.3.2+geju_v1+tiaohou_v1",
        "tag": tag,
        "confidence": confidence,
        "day_gan": ws["day_gan"],
        "day_wuxing": day_wx,
        "day_root_level": ws.get("day_root_level"),
        "effective_root_level": ws.get("effective_root_level"),
        "boundary_hints": ws.get("boundary_hints", []),
        "phase_marks": ws.get("phase_marks", []),
        "confidence_semantics": ws.get("confidence_semantics"),
        "root_semantics": ws.get("root_semantics"),
        "wangshuai": ws,
        "xiyong_wangshuai": xiyong,
        "geju": geju_out,
        "tiaohou": tiaohou_out,
        "score_wangshuai": {
            "display_only": True,
            "used_by_arbitration": False,
            "base_ws": BASE_WANGSHUAI_SCORE,
            "confidence": confidence,
            "effective_ws": effective_ws,
        },
        "modules": {
            "wangshuai": "done",
            "tiaohou": "done" if tiaohou_out.get("ok") else "error",
            "geju": "done",         # 子平格局模块（PRD V1.0）
        },
        "final_xiyong": {
            "note": final_note,
            "effective_source": effective_source,
            "wangshuai_applicable": wangshuai_applicable,
            "geju_overrides_wangshuai": geju_overrides_wangshuai,
            "special_ge": special_ge,
            "raw_xiyong_source": "xiyong_wangshuai",
            "favored": effective_xiyong["favored"],
            "disliked": effective_xiyong["disliked"],
            "neutral": effective_xiyong["neutral"],
            "decision_status": arbitration["decision_status"],
            "decision_scope": arbitration.get('decision_scope','普通方向暂定，融合未完成'),
            "release_ready": arbitration['release_ready'],
            "release_scope": arbitration['release_scope'],
            "action_release_ready": arbitration['action_release_ready'],
            "recommendation_scope": "validated_route" if arbitration.get('mode')=='integrated' else "direction_only",
            "actionable": arbitration.get('actionable',False),
            "positions": arbitration.get('positions',[]),
            "action_limitations": [] if arbitration.get('mode')=='integrated' else ['dose_assessment','bearing_capacity','repair_route_generation'],
            "conditional_review_status": arbitration.get('conditional_review_status','not_assessed'),
            "principle": arbitration['priority_reason'] if effective_source in ('arbitration_external','arbitration_integrated','unresolved_external_conflict','invalid_external_facts') and arbitration.get('priority_reason') else effective_xiyong['principle'],
            "assessment_level": 'integrated_route' if arbitration.get('mode')=='integrated' else 'confirmed_external_structure' if arbitration['decision_status'] == 'decided' else 'unresolved_conflict' if effective_source == 'unresolved_external_conflict' else 'unresolved_evidence' if effective_source == 'invalid_external_facts' else 'provisional_direction',
            "conditional_route": dict(favored=xiyong['favored'], requires_reassessment=True, requirements=arbitration.get('conditional_routes',[]))
                if tag in ('假从弱','假从强') else None,
            "conditional_favored": xiyong["favored"] if tag in ("假从弱", "假从强") else [],
            "conditional_disliked": arbitration.get("conditional_avoid", []),
            "disliked_source": arbitration.get("avoid_source", effective_source),
            "disliked_scope": arbitration.get("avoid_scope", "dimension_default"),
            "tiaohou": {
                "dimension": "调候独立原始维度；最终裁决以arbitration为准",
                "yongshen": tiaohou_out.get("yongshen", []),
                "zhuyong": tiaohou_out.get("zhuyong"),
                "no_order": tiaohou_out.get("no_order", False),
                "favored_wuxing": (tiaohou_out.get("xiyong") or {}).get("favored_wuxing", []),
                "summary": tiaohou_out.get("summary", ""),
                "caveat": tiaohou_out.get("caveat", ""),
            },
            "geju_xiyong": geju_out["xiyong_geju"],
            "geju_summary": {
                "main_ge_name": geju_out["main_ge_name"],
                "ge_status": geju_out["ge_status"],
                "xiang_shen_list": geju_out["xiang_shen_list"],
                "ji_shen_list": geju_out["ji_shen_list"],
                "xiyong_mode": geju_out["xiyong_geju"]["mode"],
                "has_bing": geju_out["xiyong_geju"]["has_bing"],
                "an_ge_flag": geju_out.get("an_ge_flag", False),
                "ge_variant": geju_out.get("ge_variant", "明格"),
            },
        },
    }
