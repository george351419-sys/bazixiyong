"""只读事实的喜用仲裁。政策版先并行输出；未审定气候阈值禁止冒充生产结论。"""
from copy import deepcopy
import hashlib
import json
from math import isfinite
from . import metadata as M
from .assessment_identity import assessment_identity
from .route_generation import generate_routes
from .route_admissibility import assess_admissibility
from .conditions import fact_condition
from .needs import build_needs, validate_needs
from .route_effects import assess_effects, verify_replacement

POLICY_VERSION = 'policy_v12_structure_candidates'
POLICIES = tuple('POL-%02d' % i for i in range(1, 8))


def build_facts(ws, geju, tiaohou, fuyi):
    """不调用任何上游计算；注入和生产使用相同契约。"""
    elements = ws.get('climate_energy')
    snapshot_id = hashlib.sha256(json.dumps([ws,geju,tiaohou,fuyi],
        ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':')).encode()).hexdigest()
    return deepcopy(dict(schema_version=1, snapshot_id=snapshot_id, ws=ws, geju=geju, tiaohou=tiaohou,
                         fuyi=fuyi, element_energy=elements,
                         energy_evidence=ws.get('energy_records', [])))


def _number(value, nonnegative=False):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and isfinite(value) and (not nonnegative or value >= 0))


def demand_ledger(statuses):
    """按场景、组合、目标、需求方法合并；缺失证据不会覆盖量化证据。"""
    ledger = {}
    for disease in statuses:
        evidence = [e for e in disease.get('evidence', []) if 'remaining' in e]
        if not evidence:
            evidence = [dict(target_id='structure:' + disease['name'], remaining=None)]
        for e in evidence:
            key = (e.get('scenario_id', 'original'), e.get('route_bundle_id', 'selected'),
                   e['target_id'], e.get('demand_method', 'structural'))
            row = ledger.setdefault(key, dict(scenario_id=key[0], route_bundle_id=key[1],
                target_id=key[2], demand_method=key[3], coverage='unsupported',
                initial_demand=None, remaining=None, evidence_refs=[], observations=[]))
            row['evidence_refs'].append(disease['name'])
            initial, remaining = e.get('initial_demand'), e.get('remaining')
            relief, aggravation = e.get('relief_realized'), e.get('aggravation', 0)
            numeric = _number(initial, True) and _number(remaining, True)
            consistent = (numeric and _number(aggravation, True)
                          and remaining <= initial + aggravation + 1e-9)
            if relief is not None:
                consistent = (consistent and _number(relief, True)
                              and abs(initial + aggravation - relief - remaining) <= 1e-9)
            measured = bool(consistent)
            row['observations'].append(dict(disease_id=disease['name'],
                initial_demand=initial if _number(initial, True) else None,
                relief_realized=relief if _number(relief, True) else None,
                aggravation=aggravation if _number(aggravation, True) else None,
                remaining=e.get('remaining') if _number(e.get('remaining'), True) else None,
                valid=measured, reason_code='valid' if measured else 'inconsistent_quantity' if numeric else 'unquantified',
                treatment_status=disease.get('status')))
            if measured:
                row['coverage'] = 'measured'
                row['initial_demand'] = max(row['initial_demand'] or 0, e['initial_demand'])
                row['remaining'] = max(row['remaining'] or 0, e['remaining'])
            elif row['coverage'] != 'measured' and e.get('remaining') is None:
                row['coverage'] = 'structural_condition'
    for row in ledger.values():
        row['evidence_refs'] = sorted(set(row['evidence_refs']))
        row['observations'].sort(key=lambda x: (x['disease_id'], str(x['initial_demand']), str(x['remaining']),
            str(x['relief_realized']), str(x['aggravation']), str(x['treatment_status'])))
        row['aggregation_kind'] = 'conservative_envelope'
        row['dose'] = None
        row['dose_reason'] = 'paired_observations_only'
        row['coverage_complete'] = all(o['valid'] for o in row['observations'])
    return [ledger[k] for k in sorted(ledger)]


def climate(facts, model=None):
    """能量来自旺衰；映射和阈值必须显式版本化注入，不暗设系数。"""
    if not isinstance(model, dict) or not model.get('version'):
        return dict(severity='unknown', reason_code='climate_model_unreviewed', axes=[])
    if model.get('review_status') != 'approved':
        return dict(severity='unknown', reason_code='climate_model_unreviewed', axes=[])
    energy = facts.get('element_energy')
    if not isinstance(energy, dict) or not facts.get('tiaohou', {}).get('ok', False):
        return dict(severity='unknown', reason_code='upstream_evidence_missing', axes=[])
    if (set(energy) != set(M.WUXING_LIST) or
            any(not _number(v, True) for v in energy.values()) or
            facts['tiaohou'].get('month_zhi') not in M.ZHI_LIST):
        return dict(severity='unknown', reason_code='energy_evidence_invalid', axes=[])
    try:
        for axis in ('cold', 'heat', 'dry', 'wet'):
            spec = model['axes'][axis]
            values = [spec['monthly_demand'][z] for z in M.ZHI] + [spec['effect'][w] for w in M.WUXING_LIST] + [spec['urgent_threshold'], spec['acceptable_remaining']]
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in values):
                raise ValueError('非有限数值')
            if (spec['urgent_threshold'] <= 0 or spec['acceptable_remaining'] < 0
                    or spec['acceptable_remaining'] >= spec['urgent_threshold']) or any(spec['monthly_demand'][z] < 0 for z in M.ZHI):
                raise ValueError('非法需求或阈值')
    except (KeyError, TypeError, ValueError):
        return dict(severity='unknown', reason_code='climate_model_invalid', axes=[])
    axes = []
    for axis in ('cold', 'heat', 'dry', 'wet'):
        spec = model['axes'][axis]
        demand = spec['monthly_demand'][facts['tiaohou']['month_zhi']]
        signed = sum(energy[w] * spec['effect'][w] for w in M.WUXING_LIST)
        if not _number(signed) or not _number(demand - signed):
            return dict(severity='unknown', reason_code='climate_calculation_invalid', axes=[])
        remaining = max(0, demand - signed)
        axes.append(dict(axis=axis,
                         severity='urgent' if remaining >= spec['urgent_threshold'] else 'mild' if remaining > 0 else 'none',
                         acceptable_remaining=spec['acceptable_remaining'],
                         initial_demand=demand, signed_relief=signed,
                         remaining=remaining, evidence_refs=['wangshuai.energy_records']))
    level = max((2 if a['remaining'] >= model['axes'][a['axis']]['urgent_threshold']
                 else 1 if a['remaining'] > 0 else 0) for a in axes)
    return dict(severity=('none', 'mild', 'urgent')[level], axes=axes, model_version=model['version'])


def evaluate_policies(severity, conflict_fuyi=None, bear='unknown', alternative=None,
                      conflict_geju=None, rescue_broken=None, ge_status=None,
                      repair_feasible=None, fake=False, routes=None, needs=None, condition_facts=None, needs_complete=False):
    hits, missing = [], []
    invalid = []
    if severity not in ('none', 'mild', 'urgent', 'unknown'): invalid.append('severity')
    if bear not in ('can', 'cannot', 'conditional', 'unknown'): invalid.append('bear')
    for key, value in dict(conflict_fuyi=conflict_fuyi, conflict_geju=conflict_geju,
                           alternative=alternative, rescue_broken=rescue_broken,
                           repair_feasible=repair_feasible).items():
        if value is not None and type(value) is not bool: invalid.append(key)
    if type(fake) is not bool: invalid.append('fake')
    if ge_status not in (None, '成格', '成中有败', '败中有救', '真破格'): invalid.append('ge_status')
    if invalid:
        return dict(hits=[], decision_status='pending', reason_code='evidence_insufficient',
                    choice=None, missing_evidence=sorted(invalid), invalid_fields=sorted(invalid),
                    route_evaluation=[])
    need_errors=validate_needs(needs)
    missing += need_errors
    if type(needs_complete) is not bool:
        missing.append('needs_complete')
    # 该出口要求需求评估已完整、候选集合明确为空；不能用未生成路线冒充无需建议。
    if (not need_errors and severity=='none' and conflict_geju is False and conflict_fuyi is False
            and not fake and needs_complete is True and routes == []
            and all(n['initial_demand']==0 and not n.get('protection_required') for n in needs.values())):
        return dict(hits=[],constraints=[],preferences=[],decision_status='decided',
            reason_code='no_new_advice',choice=None,treatment_status='satisfied',
            missing_evidence=[],route_evaluation=[],positions=[])
    if severity == 'unknown': missing.append('climate.severity')
    if conflict_geju is None: missing.append('conflict_geju')
    if conflict_fuyi is None: missing.append('conflict_fuyi')
    if severity == 'urgent' and alternative is True:
        hits.append(('POL-01', 'alternative'))
    if conflict_geju is True:
        if severity == 'urgent':
            if rescue_broken is True: hits.append(('POL-03', 'guard'))
            elif rescue_broken is False and ge_status == '成格': hits.append(('POL-02', 'climate'))
            else: missing.append('validated_geju_policy')
        elif severity == 'mild':
            if ge_status == '真破格' and repair_feasible is False: hits.append(('POL-05', 'climate'))
            elif ge_status in ('成格', '成中有败', '败中有救'): hits.append(('POL-04', 'guard'))
            else: missing.append('repair_feasibility')
    if conflict_fuyi is True:
        if severity == 'urgent':
            if bear == 'can': hits.append(('POL-06', 'climate'))
            elif bear in ('cannot', 'conditional'): hits.append(('POL-06', 'ordinary'))
            else: missing.append('bearing_capacity')
        elif severity in ('none', 'mild'): hits.append(('POL-06', 'ordinary'))
    if fake: hits.append(('POL-07', 'ordinary'))
    # 结构门和安全边界为硬约束；治疗目标的次序是偏好，不能互相否决。
    constraints, preferences = [], []
    for rule, choice in hits:
        if rule == 'POL-07':
            constraints.append(dict(rule_id=rule, field='structure_mode', expected='ordinary'))
        elif choice == 'guard':
            constraints.append(dict(rule_id=rule, field='preserves_rescue', expected=True))
        elif rule == 'POL-06' and bear in ('cannot', 'conditional'):
            constraints.append(dict(rule_id=rule, field='bearing_safe', expected=True))
            preferences.append(dict(rule_id=rule, field='prioritizes_fuyi'))
        else:
            field = dict(alternative='alternative', climate='treats_climate', ordinary='prioritizes_fuyi')[choice]
            preferences.append(dict(rule_id=rule, field=field))
    if severity == 'none':
        constraints.append(dict(rule_id='NO-CLIMATE-NEED', field='adds_climate_drug', expected=False))
    if routes is None:
        missing.append('validated_routes')
        evaluated = []
    else:
        evaluated = validate_routes(routes, constraints, preferences, needs if not need_errors else None, condition_facts,
            active_deferral_rules={rule for rule,_ in hits if rule in ('POL-03','POL-04','POL-06')},
            active_rules={rule for rule,_ in hits})
    eligible = [r for r in evaluated if r['result'] == 'eligible']
    # Pareto次序：不引入未经约定的政策兑换率；优于所有竞争路线才唯一选中。
    def dominates(left, right):
        return (all(a >= b for a,b in zip(left, right))
                and any(a > b for a,b in zip(left, right)))
    frontier = [r for r in eligible if not any(
        dominates(other['preference_lower'], r['preference_upper'])
        for other in eligible if other is not r)]
    unresolved = []
    for r in evaluated:
        if r['result'] != 'unknown': continue
        if any(dominates(v['preference_lower'], r['preference_upper']) for v in eligible):
            r['blocking'] = False
        else:
            r['blocking'] = True
            unresolved.append(r)
    if unresolved:
        missing += ['route:' + r['route_id'] + ':' + key
                    for r in unresolved for key in r['missing_evidence']]
    constraint_values = {}
    for c in constraints:
        constraint_values.setdefault(c['field'], set()).add((type(c['expected']).__name__,str(c['expected'])))
    contradictory = sorted(k for k,v in constraint_values.items() if len(v)>1)
    if contradictory:
        reason = 'policy_conflict'
    elif missing:
        reason = 'evidence_insufficient'
    elif len(frontier) == 1:
        reason = 'selected'
    elif not evaluated or eligible:
        reason = 'policy_gap'
    else:
        reason = 'no_feasible_route'
    failure_summary = {r['route_id']: r['failed_rules'] for r in evaluated if r['result']=='rejected'}
    return dict(constraint_conflicts=contradictory, route_failure_summary=failure_summary, hits=[dict(rule_id=r, choice=c) for r,c in hits], constraints=constraints,
                preferences=preferences,
                decision_status=('conditional' if frontier[0]['treatment_status']=='deferred' else 'decided') if reason == 'selected' else 'pending',
                treatment_status=frontier[0]['treatment_status'] if reason == 'selected' else 'unknown',
                reason_code=reason, choice=frontier[0]['route_id'] if reason == 'selected' else None,
                missing_evidence=sorted(set(missing)), route_evaluation=evaluated)


def validate_routes(routes, constraints, preferences=(), needs=None, condition_facts=None, active_deferral_rules=(), active_rules=()):
    """路线携带目标、动作和逐项检查证据；布尔自声明不足以进入可行集合。

    evidence_registry 由事实/验证器提供；这是内部证据契约，不是外部认证。
    """
    if not isinstance(routes, list) or any(not isinstance(r, dict) for r in routes):
        raise ValueError('路线必须为对象列表')
    ids = [r.get('route_id') for r in routes]
    if any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('路线ID必须非空且唯一')
    summaries = {r['route_id']: assess_effects(r, needs, condition_facts) for r in routes}
    candidates = {r['route_id']:r for r in routes}
    output = []
    for route in sorted(routes, key=lambda r:r['route_id']):
        failed, unknown = [], []
        registry = route.get('evidence_registry', {})
        if not isinstance(registry, dict): registry = {}
        def supported(field):
            check = route.get('checks', {}).get(field) if isinstance(route.get('checks'), dict) else None
            if not isinstance(check, dict): return None
            refs = check.get('evidence_refs')
            if not isinstance(refs, list) or not refs: return None
            for ref in refs:
                entry = registry.get(ref) if isinstance(ref, str) else None
                if (not isinstance(entry, dict) or entry.get('route_id') != route['route_id']
                        or entry.get('field') != field or entry.get('value') != check.get('value')):
                    return None
            return check.get('value')
        goals = route.get('goals')
        actions = route.get('actions')
        if not isinstance(goals, list) or not goals or any(not isinstance(g,str) or not g for g in goals):
            unknown.append('goals')
        if not isinstance(actions,list):
            unknown.append('actions')
        elif not actions and any(n.get('initial_demand',0)>0 for n in (needs or {}).values()):
            unknown.append('actions')
        else:
            for action in actions:
                if (not isinstance(action, dict) or action.get('gan') not in M.GAN_LIST
                        or action.get('target_id') not in (goals or [])
                        or not isinstance(action.get('method'), str) or not action.get('method')
                        or not isinstance(action.get('evidence_refs'), list) or not action['evidence_refs']
                        or any(not isinstance(ref,str) or not isinstance(registry.get(ref),dict)
                               or registry[ref].get('route_id') != route['route_id']
                               or registry[ref].get('target_id') != action['target_id']
                               or registry[ref].get('gan') != action['gan']
                               or registry[ref].get('method') != action['method']
                               for ref in action.get('evidence_refs', []))):
                    unknown.append('action_evidence')
        for mapping in route.get('source_mappings', []):
            if mapping.get('status') != 'mapped':
                unknown.append('source_mapping:'+str(mapping.get('source_action_id')))
        for restriction in route.get('source_restrictions', []):
            key='source_restriction:'+str(restriction.get('id'))
            result=supported(key)
            if result is False: failed.append('restriction_still_active:'+str(restriction.get('id')))
            elif result is not True: unknown.append(key)
        requirements = [('validated', 'validated', True), ('compatible', 'compatible', True)]
        requirements += [(c['rule_id'], c['field'], c['expected']) for c in constraints]
        for source, field, expected in requirements:
            value = supported(field)
            if value is None: unknown.append(field)
            elif type(value) is not type(expected) or value != expected: failed.append(source)
        effects, effect_missing = summaries[route['route_id']]
        unknown += effect_missing
        for effect in effects:
            if effect['status']=='deferred' and effect['reason_rule'] not in active_deferral_rules:
                unknown.append('unauthorized_deferral:'+effect['target_id'])
        inadmissible, admissibility_missing, approvals = assess_admissibility(route,effects,needs or {},active_rules,POLICY_VERSION)
        failed += inadmissible
        unknown += admissibility_missing
        lower, upper = [], []
        for pref in preferences:
            value = supported(pref['field'])
            if pref['field'] == 'treats_climate' and value is True:
                if not any(e['need_type']=='climate' and e['relief_realized']>0 for e in effects):
                    value = None
            if pref['field'] == 'alternative' and value is True:
                if not verify_replacement(route, candidates, summaries, needs): value = None
            lower.append(1 if value is True else 0)
            upper.append(0 if value is False else 1)
            if type(value) is not bool: unknown.append(pref['field'])
        output.append(dict(route_id=route['route_id'],
            result='rejected' if failed else 'unknown' if unknown else 'eligible',
            failed_rules=sorted(set(failed)), missing_evidence=sorted(set(unknown)),
            goal_results=effects, tradeoff_approvals=approvals,
            treatment_status=('deferred' if any(e['status']=='deferred' for e in effects) else
                'partial' if any(e['remaining']>0 for e in effects) else 'satisfied') if not effect_missing else 'unknown',
            preference_lower=lower, preference_upper=upper))
    return output


def select_policy(severity, **kwargs):
    """兼容旧调用方；正式消费多规则结果使用 evaluate_policies。"""
    result = evaluate_policies(severity, **kwargs)
    if result['decision_status'] != 'decided': return None, 'pending'
    return (result['hits'][0]['rule_id'] if result['hits'] else None,
            result['choice'])


def arbitrate(facts, climate_model=None):
    if facts.get('schema_version') != 1: raise ValueError('不支持的事实快照版本')
    ws, gj, th = (facts[k] for k in ('ws', 'geju', 'tiaohou'))
    assessment = climate(facts, climate_model)
    statuses = gj.get('xiyong_geju', {}).get('treatment_status', [])
    ledger = demand_ledger(statuses)
    assessment_id = assessment_identity(facts, climate_model, POLICY_VERSION)
    needs, need_missing = build_needs(assessment, ledger, assessment_id)
    policy_inputs = deepcopy(facts.get('policy_inputs', {}))
    policy_inputs['needs'] = needs
    policy_inputs['condition_facts'] = facts
    generated, generation_missing=generate_routes(facts,needs)
    if 'candidate_routes' in facts:
        policy_inputs['routes'] = facts['candidate_routes']
    elif 'routes' not in policy_inputs:
        policy_inputs['routes'] = generated
    # 承受、扶抑与通关尚未完成全量评估，不得宣称全局无新增建议。
    coverage = dict(climate='complete' if assessment['severity']!='unknown' else 'evidence_insufficient',
        geju='evidence_insufficient' if any(k.startswith('geju_need:') for k in need_missing) else 'assessed_current_treatment',
        fuyi='not_implemented',tongguan='not_implemented',
        special_structure='not_implemented',cross_dimension='not_implemented')
    policy_inputs['needs_complete'] = all(v=='complete' for v in coverage.values())
    policy = evaluate_policies(assessment['severity'], **policy_inputs)
    progress=dict(candidate_generation='generated' if policy_inputs.get('routes') else 'empty',
        evidence_validation='complete' if policy.get('route_evaluation') and all(r['result']!='unknown' for r in policy['route_evaluation']) else 'incomplete',
        policy_selection=policy['decision_status'],final_assembly='not_implemented')
    # 病状态是路线生成的输入，不能冒充已经生成的治疗路线。
    disease_states = deepcopy(statuses)
    routes = deepcopy(policy_inputs.get('routes') or [])
    missing = list(policy['missing_evidence']) + need_missing + generation_missing + [
        'validated_cross_dimension_routes','fuyi_need_assessment','tongguan_need_assessment']
    if assessment['severity'] == 'unknown': missing.append(assessment['reason_code'])
    # 尚缺经审核的药效、路线兼容或气候前置时，只并行展示，不接管最终喜用。
    return dict(mode='incomplete', policy_evaluation=policy, routes=routes,
                disease_states=disease_states, needs=needs,assessment_coverage=coverage,decision_progress=progress,
                route_generation_coverage=dict(maintenance='implemented',
                    deficit_repair='not_implemented',conditional='not_implemented'),
                facts_snapshot_id=facts.get('snapshot_id'), assessment_snapshot_id=assessment_id,
                decision_status='pending',
                reason_code='evidence_insufficient', policy_version=POLICY_VERSION,
                release_ready=False, positions=[], climate=assessment, demand_ledger=ledger,
                conditional_routes=[dict(kind='fake_cong', condition_expr=fact_condition('ws.cong_info.is_cong'))]
                    if ws.get('cong_info', {}).get('is_fake_cong') else [],
                missing_evidence=sorted(set(missing)),
                dimension_results=dict(fuyi=facts['fuyi'], geju=gj.get('xiyong_geju', {}), tiaohou=th))
