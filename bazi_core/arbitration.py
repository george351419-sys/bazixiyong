"""只读事实的喜用仲裁。政策版先并行输出；未审定气候阈值禁止冒充生产结论。"""
from .numeric import finite as safe_finite
from copy import deepcopy
import hashlib
import json
from math import isfinite
from . import metadata as M
from .assessment_identity import assessment_identity, fact_snapshot_identity, snapshot_error, route_assessment_identity
from .external_arbitration import special_structure_verdict
from .route_generation import generate_routes, generate_structure_route, generate_repair_candidates
from .route_admissibility import assess_admissibility
from .conditions import fact_condition, valid_condition, evaluate_condition
from .dose import assess_dose
from .contracts import action_identity, route_shape_errors
from .route_resources import assess_resources
from .conditional_routes import fake_cong_routes
from .fusion_evidence import apply_evidence, assemble_route
from .needs import build_needs, validate_needs
from .route_effects import assess_effects, verify_replacement, false_execution_conditions

POLICY_VERSION = 'policy_v29_counterfactual_maintenance_resolution'
POLICIES = tuple('POL-%02d' % i for i in range(1, 8))


def build_facts(ws, geju, tiaohou, fuyi):
    """不调用任何上游计算；注入和生产使用相同契约。"""
    elements = ws.get('climate_energy_raw',ws.get('climate_energy'))
    snapshot_id = fact_snapshot_identity(ws,geju,tiaohou,fuyi)
    return deepcopy(dict(schema_version=1, snapshot_id=snapshot_id, ws=ws, geju=geju, tiaohou=tiaohou,
                         fuyi=fuyi, element_energy=elements,
                         energy_evidence=ws.get('energy_records', [])))


def _number(value, nonnegative=False):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and safe_finite(value) and (not nonnegative or value >= 0))


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
                execution_status=e.get('execution_status','realized' if relief is not None else 'unknown'),
                relief_feasible=e.get('relief_feasible'),
                aggravation=aggravation if _number(aggravation, True) else None,
                remaining=e.get('remaining') if _number(e.get('remaining'), True) else None,
                valid=measured, reason_code='valid' if measured else 'inconsistent_quantity' if numeric else 'unquantified',
                protection_dependency=deepcopy(e.get('protection_dependency')),
                method_relation=deepcopy(e.get('method_relation')),
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
        row['gap_complete'] = row['coverage_complete']
        row['relief_complete'] = row['gap_complete'] and all(o['relief_realized'] is not None for o in row['observations'])
        row['dose_assessments'] = [assess_dose(o) for o in row['observations']]
        doses={d['dose'] for d in row['dose_assessments']}
        if row['relief_complete'] and len(doses)==1:
            row['dose']=next(iter(doses))
            row['dose_reason']='paired_realized_relief'
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
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not safe_finite(v) for v in values):
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
        shape_errors=route_shape_errors(routes)
        if shape_errors:
            return dict(hits=[dict(rule_id=r,choice=c) for r,c in hits],decision_status='pending',reason_code='invalid_route_input',choice=None,missing_evidence=shape_errors,route_evaluation=[])
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
    exclusions={r['route_id']:false_execution_conditions(r,condition_facts) for r in routes}
    summaries = {r['route_id']: ([],[]) if exclusions[r['route_id']] else assess_effects(r, needs, condition_facts) for r in routes}
    candidates = {r['route_id']:r for r in routes}
    output = []
    for route in sorted(routes, key=lambda r:r['route_id']):
        if exclusions[route['route_id']]:
            output.append(dict(route_id=route['route_id'],result='rejected',applicability='not_applicable',
                failed_rules=exclusions[route['route_id']],missing_evidence=[],evaluation_skipped=True,
                goal_results=[],resource_allocations=[],structural_results=[],tradeoff_approvals=[],
                treatment_status='not_applicable',preference_lower=[0]*len(preferences),preference_upper=[0]*len(preferences)))
            continue
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
                if (action_identity(action) is None
                        or action.get('target_id') not in (goals or [])
                        or not isinstance(action.get('method'), str) or not action.get('method')
                        or not isinstance(action.get('evidence_refs'), list) or not action['evidence_refs']
                        or any(not isinstance(ref,str) or not isinstance(registry.get(ref),dict)
                               or registry[ref].get('route_id') != route['route_id']
                               or registry[ref].get('target_id') != action['target_id']
                               or registry[ref].get('gan') != action.get('gan')
                               or (action.get('precision')=='wuxing' and registry[ref].get('wuxing')!=action.get('wuxing'))
                               or registry[ref].get('method') != action['method']
                               for ref in action.get('evidence_refs', []))):
                    unknown.append('action_evidence')
        structural_results=[]
        for target,goal in route.get('structure_goals', {}).items():
            upstream=(condition_facts or {}).get('geju',{}).get('xiyong_geju',{})
            record=goal.get('record',{})
            if goal.get('precision')=='wuxing':
                source_ok=(record.get('wuxing') in upstream.get('special_yong_wuxing',[])
                           and (condition_facts or {}).get('geju',{}).get('ge_category')=='外格')
            else:
                source_ok=any(r==record for r in upstream.get('selected_records',[]))
            if not source_ok: unknown.append('structure_source:'+target)
            guard=supported('structure_guard:'+target)
            if guard is False: failed.append('structure_guard_failed:'+target)
            elif guard is not True: unknown.append('structure_dependency:'+target)
            structural_results.append(dict(target_id=target,source_verified=source_ok,
                dependency_status='verified' if guard is True and source_ok else 'unknown'))
        for mapping in route.get('source_mappings', []):
            if mapping.get('status') != 'mapped':
                unknown.append('source_mapping:'+str(mapping.get('source_action_id')))
        for restriction in route.get('source_restrictions', []):
            key='source_restriction:'+str(restriction.get('id'))
            result=supported(key)
            if result is False: failed.append('restriction_still_active:'+str(restriction.get('id')))
            elif result is not True: unknown.append(key)
        if actions and supported('bearing_safe') is False:
            failed.append('bearing_safety')
        requirements = [('validated', 'validated', True), ('compatible', 'compatible', True)]
        requirements += [(c['rule_id'], c['field'], c['expected']) for c in constraints]
        if any(isinstance(a,dict) and a.get('intended_action') in ('increase','protect','limit') for a in actions or []):
            requirements.append(('bearing_safety','bearing_safe',True))
        for source, field, expected in requirements:
            value = supported(field)
            if value is None: unknown.append(field)
            elif type(value) is not type(expected) or value != expected: failed.append(source)
        effects, effect_missing = summaries[route['route_id']]
        unknown += effect_missing
        for action in actions if isinstance(actions,list) else []:
            if not isinstance(action,dict) or 'condition_expr' not in action: continue
            expr=action.get('condition_expr')
            if not valid_condition(expr):
                unknown.append('action_condition_invalid:'+str(action.get('target_id')));continue
            status=evaluate_condition(expr,condition_facts or {})
            if status=='false': failed.append('action_condition_false:'+str(action.get('target_id')))
            elif status=='unknown': unknown.append('action_condition_unknown:'+str(action.get('target_id')))
            effect=next((e for e in effects if e['target_id']==action.get('target_id')),None)
            if effect and effect.get('condition_expr')!=expr:
                unknown.append('action_effect_condition_mismatch:'+str(action.get('target_id')))
        for effect in effects:
            if effect['status']=='deferred' and effect['reason_rule'] not in active_deferral_rules:
                unknown.append('unauthorized_deferral:'+effect['target_id'])
        inadmissible, admissibility_missing, approvals = assess_admissibility(route,effects,needs or {},active_rules,POLICY_VERSION)
        resource_errors,resource_allocations=assess_resources(route,effects)
        unknown+=resource_errors
        failed += inadmissible
        unknown += admissibility_missing
        lower, upper = [], []
        for pref in preferences:
            value = supported(pref['field'])
            if pref['field'] == 'treats_climate' and value is True:
                if not any(e['need_type']=='climate' and e['comparison_relief']>0 for e in effects):
                    value = None
            if pref['field'] == 'alternative' and value is True:
                if not verify_replacement(route, candidates, summaries, needs): value = None
            lower.append(1 if value is True else 0)
            upper.append(0 if value is False else 1)
            if type(value) is not bool: unknown.append(pref['field'])
        output.append(dict(route_id=route['route_id'],
            result='rejected' if failed else 'unknown' if unknown else 'eligible',
            failed_rules=sorted(set(failed)), missing_evidence=sorted(set(unknown)),
            goal_results=effects,resource_allocations=resource_allocations,structural_results=structural_results,tradeoff_approvals=approvals,
            treatment_status=('deferred' if any(e['status']=='deferred' for e in effects) else
                'partial' if any(e['remaining']>0 for e in effects) else 'satisfied') if not effect_missing and all(g['dependency_status']=='verified' for g in structural_results) else 'unknown',
            preference_lower=lower, preference_upper=upper))
        # 行动不成立的路线不得先靠药效排序胜出，再阻塞其他可执行路线。
        if output[-1]['result']=='eligible' and any(a.get('intended_action') is not None for a in route.get('actions',[])):
            _,action_errors=assemble_route(dict(choice=route['route_id'],reason_code='selected',decision_status='decided',route_evaluation=[output[-1]]),[route])
            if action_errors:
                output[-1]['result']='rejected'
                output[-1]['failed_rules']=sorted(set(output[-1]['failed_rules']+action_errors))

    return output


def select_policy(severity, **kwargs):
    """兼容旧调用方；正式消费多规则结果使用 evaluate_policies。"""
    result = evaluate_policies(severity, **kwargs)
    if result['decision_status'] != 'decided': return None, 'pending'
    return (result['hits'][0]['rule_id'] if result['hits'] else None,
            result['choice'])


def _arbitrate(facts, climate_model=None):
    if facts.get('schema_version') != 1: raise ValueError('不支持的事实快照版本')
    ws, gj, th = (facts[k] for k in ('ws', 'geju', 'tiaohou'))
    reason=snapshot_error(facts)
    if reason:
        return dict(mode='incomplete',decision_status='pending',reason_code=reason,
            policy_version=POLICY_VERSION,release_ready=False,positions=[],favored=[],avoid=[],
            decision_scope='未裁决',conditional_review_status='not_assessed',
            missing_evidence=[reason],implementation_gaps=[],
            decision_progress=dict(special_structure='not_assessed',policy_selection='blocked',final_assembly='blocked'),
            policy_evaluation=dict(decision_status='pending',reason_code=reason,
                blocking_missing_evidence=[reason],route_evaluation=[]),routes=[],
            facts_snapshot_id=facts.get('snapshot_id'),assessment_snapshot_id=None)
    external=special_structure_verdict(facts)
    if external is not None and external['decision_status'] != 'decided':
        external.update(policy_version=POLICY_VERSION,
            missing_evidence=external['blocking_missing_evidence'],
            implementation_gaps=[],gap_categories=['evidence_conflict' if external['reason_code'].endswith('conflict') else 'evidence_gap'],
            climate=climate(facts,climate_model),routes=[],
            decision_scope='顺势主方向',
            conditional_review_status='conflict' if external['reason_code'] in ('triggered_avoid_conflict','unconditional_avoid_conflict') else 'not_assessed',
            policy_evaluation=dict(decision_status='pending',reason_code=external['reason_code'],
                route_evaluation=[],blocking_missing_evidence=external['blocking_missing_evidence']),
            decision_progress=dict(special_structure='evidence_insufficient' if external['reason_code'] in ('true_cong_evidence_missing','true_cong_invalid_selection','special_invalid_selection','special_structure_evidence_missing') else 'conflict',policy_selection='pending',final_assembly='blocked'),
            facts_snapshot_id=facts.get('snapshot_id'),
            assessment_snapshot_id=assessment_identity(facts,climate_model,POLICY_VERSION))
        return external
    if external is not None:
        provenance_routes,_=generate_structure_route(facts)
        provenance=validate_routes(provenance_routes,[],needs={},condition_facts=facts)
        external.update(policy_version=POLICY_VERSION,
            climate=climate(facts,climate_model),routes=provenance_routes,missing_evidence=[],
            policy_evaluation=dict(decision_status='decided',basis=external['reason_code'],
                route_evaluation=provenance,route_evaluation_scope='source_provenance',
                blocking_missing_evidence=[],
                diagnostic_missing_evidence=sorted({m for route in provenance
                    for m in route.get('missing_evidence',[])}),
                diagnostic_affects_decision=False),
            decision_progress=dict(special_structure='confirmed',policy_selection='decided',final_assembly='complete'),
            facts_snapshot_id=facts.get('snapshot_id'),
            assessment_snapshot_id=assessment_identity(facts,climate_model,POLICY_VERSION))
        return external
    assessment = climate(facts, climate_model)
    statuses = gj.get('xiyong_geju', {}).get('treatment_status', [])
    ledger = demand_ledger(statuses)
    assessment_id = assessment_identity(facts, climate_model, POLICY_VERSION)
    needs, need_missing = build_needs(assessment, ledger, assessment_id)
    policy_inputs = deepcopy(facts.get('policy_inputs', {}))
    policy_inputs['fake'] = ws.get('cong_info', {}).get('is_fake_cong') is True
    policy_inputs['needs'] = needs
    policy_inputs['condition_facts'] = facts
    generated, generation_missing=generate_routes(facts,needs)
    generated += generate_repair_candidates(facts,needs,climate_model)
    if 'candidate_routes' in facts:
        policy_inputs['routes'] = facts['candidate_routes']
    elif 'routes' not in policy_inputs:
        policy_inputs['routes'] = generated
    # 承受、扶抑与通关尚未完成全量评估，不得宣称全局无新增建议。
    coverage = dict(climate='complete' if assessment['severity']!='unknown' else 'evidence_insufficient',
        geju='evidence_insufficient' if any(k.startswith('geju_need:') for k in need_missing) else 'assessed_current_treatment',
        fuyi='not_implemented',tongguan='not_implemented',
        special_structure='not_implemented',cross_dimension='not_implemented')
    fusion_errors=[]
    if 'fusion_evidence' in facts:
        merged,completed,inputs,fusion_errors=apply_evidence(facts['fusion_evidence'],facts,assessment_id,needs)
        from .fusion_evidence import remaining_need_errors
        unresolved=remaining_need_errors(need_missing,merged,facts) if not fusion_errors else need_missing
        if not fusion_errors and not unresolved:
            need_missing=[]
            needs=merged
            coverage.update(completed)
            policy_inputs.update(inputs,needs=needs)
        else:
            fusion_errors+=unresolved
    policy_inputs['needs_complete'] = all(v=='complete' for v in coverage.values())
    policy = evaluate_policies(assessment['severity'], **policy_inputs)
    assembly_errors=[]
    if policy_inputs['needs_complete'] and policy['decision_status'] in ('decided','conditional'):
        assembled,assembly_errors=assemble_route(policy,policy_inputs.get('routes',[]))
        if not assembly_errors:
            return dict(assembled,mode='integrated',decision_status=policy['decision_status'],
                policy_version=POLICY_VERSION,policy_evaluation=policy,policy_inputs={k:v for k,v in policy_inputs.items() if k in ('conflict_fuyi','conflict_geju','bear')},routes=deepcopy(policy_inputs.get('routes',[])),
                needs=needs,assessment_coverage=coverage,climate=assessment,demand_ledger=ledger,
                facts_snapshot_id=facts.get('snapshot_id'),assessment_snapshot_id=assessment_id,
                decision_scope='已审定证据支持的跨维度路线',conditional_review_status='complete' if policy['decision_status']=='decided' else 'pending',
                release_ready=policy['decision_status']=='decided',implementation_gaps=[],missing_evidence=[],
                conditional_routes=fake_cong_routes(facts),
                decision_progress=dict(policy_selection=policy['decision_status'],final_assembly='complete'),
                priority_reason='需求已覆盖，按政策与逐目标药效验证选择路线。')
        fusion_errors+=assembly_errors
    progress=dict(candidate_generation='generated' if policy_inputs.get('routes') else 'empty',
        evidence_validation='complete' if policy.get('route_evaluation') and all(r['result']!='unknown' for r in policy['route_evaluation']) else 'incomplete',
        policy_selection=policy['decision_status'],final_assembly='blocked' if assembly_errors else 'waiting_for_validated_route')
    # 病状态是路线生成的输入，不能冒充已经生成的治疗路线。
    disease_states = deepcopy(statuses)
    routes = deepcopy(policy_inputs.get('routes') or [])
    full_coverage=all(v=='complete' for v in coverage.values())
    missing=list(policy['missing_evidence'])+need_missing+fusion_errors
    if not full_coverage:
        missing+=generation_missing
        missing += [key for dimension,key in [('fuyi','fuyi_need_assessment'),('tongguan','tongguan_need_assessment'),('cross_dimension','validated_cross_dimension_routes')] if coverage.get(dimension)!='complete']
    if assessment['severity'] == 'unknown': missing.append(assessment['reason_code'])
    # 尚缺经审核的药效、路线兼容或气候前置时，只并行展示，不接管最终喜用。
    implementation_gaps=[] if all(v=='complete' for v in coverage.values()) else ['production_fuyi_assessment','production_tongguan_assessment','production_cross_dimension_effects']
    return dict(mode='incomplete', policy_evaluation=policy, policy_inputs={k:v for k,v in policy_inputs.items() if k in ('conflict_fuyi','conflict_geju','bear')},routes=routes,
                disease_states=disease_states, needs=needs,assessment_coverage=coverage,decision_progress=progress,
                route_generation_coverage=dict(maintenance='implemented',
                    deficit_repair='intent_generated_effects_pending',conditional='intent_generated_effects_pending'),
                facts_snapshot_id=facts.get('snapshot_id'), assessment_snapshot_id=assessment_id,
                decision_status='pending',
                reason_code='action_assembly_failed' if assembly_errors else policy['reason_code'] if full_coverage and policy['decision_status']=='pending' else 'evidence_insufficient',
                implementation_gaps=implementation_gaps, policy_version=POLICY_VERSION,
                release_ready=False, positions=[], climate=assessment, demand_ledger=ledger,
                conditional_routes=fake_cong_routes(facts),
        gap_categories=(['implementation_gap'] if implementation_gaps else []) + (['evidence_gap'] if assessment['severity']=='unknown' or need_missing or fusion_errors or policy.get('reason_code')=='evidence_insufficient' else []) + (['policy_gap'] if policy.get('reason_code')=='policy_gap' else []),
        assembly_errors=sorted(set(assembly_errors)),missing_evidence=sorted(set(missing)),
                dimension_results=dict(fuyi=facts['fuyi'], geju=gj.get('xiyong_geju', {}), tiaohou=th))


def arbitrate(facts, climate_model=None):
    """统一返回合同，并在所有分支完成后检查发布条件。"""
    result=_arbitrate(facts,climate_model)
    result.setdefault('implementation_gaps',[])
    result.setdefault('gap_categories',[])
    result.setdefault('conditional_review_status','not_assessed')
    result['route_assessment_id']=route_assessment_identity(result.get('assessment_snapshot_id'),result.get('routes',[]),result.get('policy_inputs',{}),facts.get('fusion_evidence'))
    errors=[]
    if result.get('decision_status')=='decided':
        if not result.get('assessment_snapshot_id'): errors.append('assessment_identity_invalid')
        if not result.get('facts_snapshot_id'): errors.append('fact_snapshot_missing')
        if not result['route_assessment_id']: errors.append('route_assessment_identity_invalid')
        if errors:
            result.update(decision_status='pending',reason_code=errors[0],release_ready=False,
                          positions=[],favored=[],avoid=[])
            result['missing_evidence']=sorted(set(result.get('missing_evidence',[])+errors))
            result['decision_progress'].update(policy_selection='blocked',final_assembly='blocked')
            result['policy_evaluation'].update(decision_status='pending',reason_code=errors[0])
            result['priority_reason']='评估身份无效，暂停最终裁决。'
    result['release_ready']=bool(result.get('release_ready') and
        result['decision_status']=='decided' and result.get('assessment_snapshot_id') and
        not result.get('missing_evidence') and not result['implementation_gaps'] and
        result['conditional_review_status']=='complete')
    validation_error=snapshot_error(facts)
    result['fact_validation']=dict(status='invalid' if validation_error else 'valid',reason_code=validation_error)
    if validation_error: result['release_ready']=False
    if errors or validation_error:
        result['gap_categories']=sorted(set(result['gap_categories']+['evidence_gap']))
    result['comparison_mode']='policy_default' if result.get('mode')=='integrated' else 'structure_rule' if result.get('mode')=='external' else 'not_decided'
    result['release_scope']='direction_conclusion' if result.get('mode')=='external' else 'integrated_recommendation'
    result['action_release_ready']=bool(result['release_ready'] and result.get('actionable') is True)
    result['primary_blocker']=('implementation_gap' if result['implementation_gaps'] else
        'evidence_gap' if 'evidence_gap' in result['gap_categories'] else
        'evidence_conflict' if 'evidence_conflict' in result['gap_categories'] else
        'policy_gap' if 'policy_gap' in result['gap_categories'] else
        'conditional_review' if result['conditional_review_status']=='pending' else None)
    return result
