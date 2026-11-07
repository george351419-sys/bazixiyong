"""逐目标治疗账；只能从成对证据计算药效，不读取需求汇总包络。"""
from math import isfinite
from .conditions import valid_condition, evaluate_condition, referenced_paths


def number(value):
    return not isinstance(value, bool) and isinstance(value, (int,float)) and isfinite(value) and value >= 0


def assess_effects(route, needs=None, condition_facts=None):
    registry = route.get('evidence_registry', {})
    registry = registry if isinstance(registry, dict) else {}
    effects = route.get('goal_results', {})
    effects = effects if isinstance(effects, dict) else {}
    goals = route.get('goals', [])
    goals = list(goals) if isinstance(goals, list) else []
    monitors=route.get('monitor_results', {})
    monitors=monitors if isinstance(monitors,dict) else {}
    missing, results = [], []
    if len([g for g in goals if isinstance(g,str)]) != len(set(g for g in goals if isinstance(g,str))):
        return [], ['duplicate_goals']
    if needs is None: return [], ['need_registry']
    for goal,need in needs.items():
        if need.get('required') and goal not in goals: missing.append('uncovered_need:'+goal)
        if (not need.get('required') and need.get('initial_demand')==0 and goal not in goals
                and route.get('actions')):
            # 无需用药但必须验证候选动作不会加重此项；监测不是额外处方。
            if goal not in monitors: missing.append('monitor_effect:'+goal)
            else: goals.append(goal)
    effects=dict(effects)
    for goal,item in monitors.items():
        if goal not in needs or needs[goal].get('initial_demand')!=0 or needs[goal].get('required'):
            missing.append('invalid_monitor:'+str(goal));continue
        if goal in effects and effects[goal]!=item: missing.append('conflicting_monitor:'+goal)
        else: effects[goal]=item
    for goal in goals:
        if not isinstance(goal, str):
            missing.append('invalid_goal'); continue
        item = effects.get(goal)
        if not isinstance(item, dict):
            missing.append('goal_result:' + goal); continue
        need=needs.get(goal)
        if not isinstance(need,dict):
            missing.append('unknown_need:'+goal);continue
        state = item.get('status')
        initial, relief, remaining = (item.get(k) for k in ('initial_demand','relief_realized','remaining'))
        aggravation = item.get('aggravation', 0)
        refs = item.get('evidence_refs')
        fields = ('initial_demand', 'relief_realized', 'remaining', 'status', 'need_type',
                  'scenario_id', 'execution_status', 'condition_expr', 'reason_rule', 'aggravation', 'protection_dependency', 'effect_scope', 'baseline_ref')
        valid = isinstance(refs, list) and bool(refs)
        if valid:
            for ref in refs:
                evidence = registry.get(ref) if isinstance(ref, str) else None
                if (not isinstance(evidence, dict) or evidence.get('route_id') != route['route_id']
                        or evidence.get('target_id') != goal
                        or any(evidence.get(k) != item.get(k) for k in fields)):
                    valid = False; break
        valid = (valid and all(number(v) for v in (initial,relief,remaining,aggravation))
                 and abs(initial+aggravation-relief-remaining) <= 1e-9
                 and item.get('scenario_id') == 'original'
                 and initial == need.get('initial_demand')
                 and item.get('effect_scope') == 'incremental_from_baseline'
                 and item.get('baseline_ref') == need.get('baseline_ref')
                 and isinstance(item.get('baseline_ref'),str) and bool(item['baseline_ref'])
                 and item.get('need_type') == need.get('need_type')
                 and item.get('scenario_id') == need.get('scenario_id'))
        if state == 'deferred':
            valid = (valid and relief == 0 and remaining > 0
                     and item.get('execution_status') == 'not_executed'
                     and valid_condition(item.get('condition_expr'))
                     and item.get('reason_rule') in need.get('allowed_deferral_rules', []))
        else:
            valid = (valid and state in ('treated','protected','satisfied','unaddressed','aggravated')
                     and item.get('execution_status') == 'realized')
            if state == 'aggravated': valid = valid and aggravation > 0
            if state == 'unaddressed': valid = valid and relief == 0 and remaining > 0
            if state == 'treated': valid = valid and relief > 0
            if state == 'satisfied': valid = valid and remaining <= 1e-9
            if state == 'protected':
                dependency = item.get('protection_dependency')
                valid = (valid and remaining <= 1e-9 and isinstance(dependency,dict)
                         and number(dependency.get('remaining_without'))
                         and dependency['remaining_without'] > remaining
                         and isinstance(dependency.get('evidence_refs'),list)
                         and bool(dependency['evidence_refs']))
                if valid:
                    valid = all(isinstance(ref,str) and isinstance(registry.get(ref),dict)
                        and registry[ref].get('route_id') == route['route_id']
                        and registry[ref].get('target_id') == goal
                        and registry[ref].get('remaining_without') == dependency['remaining_without']
                        for ref in dependency['evidence_refs'])
            actions = route.get('actions', [])
            no_action_needed=(state=='satisfied' and initial==0 and relief==0 and aggravation==0)
            valid = valid and (no_action_needed or (isinstance(actions,list) and any(
                isinstance(a,dict) and a.get('target_id') == goal for a in actions)))
        if not valid:
            missing.append('goal_evidence:' + goal); continue
        condition_status=evaluate_condition(item['condition_expr'],condition_facts or {}) if state=='deferred' else None
        if condition_status == 'true':
            missing.append('condition_met_revalidate:'+goal)
        results.append(dict(target_id=goal, need_type=item['need_type'], status=state,
            initial_demand=initial, baseline_gap=initial,baseline_ref=item['baseline_ref'],
            relief_realized=relief, relief_incremental=relief,
            aggravation=aggravation, aggravation_incremental=aggravation, remaining=remaining,
            dose=(relief / initial if initial > 0 and state != 'deferred' else None),
            condition_expr=item.get('condition_expr'), reason_rule=item.get('reason_rule'),
            condition_status=condition_status,
            condition_paths=referenced_paths(item['condition_expr']) if state=='deferred' else []))
    return results, missing


def verify_replacement(route, candidates, summaries, needs=None):
    """替代需同需求、药效不低且逐项代价不高；至少一项代价严格改善。"""
    link = route.get('replacement')
    if not isinstance(link,dict): return False
    original = candidates.get(link.get('replaces_route_id'))
    if original is None or original is route: return False
    before = summaries.get(original['route_id'])
    after = summaries.get(route['route_id'])
    if not before or not after or before[1] or after[1]: return False
    def result_map(summary):
        return {r['target_id']:r for r in summary[0]}
    a,b = result_map(before),result_map(after)
    if not needs or not a or set(a)!=set(b) or any(k not in a for k,v in needs.items() if v.get('required')): return False
    if not any(r['need_type']=='climate' and r['relief_realized']>0 for r in b.values()): return False
    if any(a[k]['initial_demand'] != b[k]['initial_demand'] or
           b[k]['remaining'] > a[k]['remaining'] or b[k]['relief_realized'] < a[k]['relief_realized'] for k in a): return False
    # 比较值需要同一次验证器的显式证据；不从喜忌标签推导代价。
    costs = link.get('cost_comparison')
    refs = link.get('evidence_refs')
    registry=route.get('evidence_registry', {})
    if not isinstance(costs,dict) or set(costs)!={'geju','self','other_routes'} or not isinstance(refs,list) or not refs: return False
    for ref in refs:
        e=registry.get(ref) if isinstance(ref,str) else None
        if (not isinstance(e,dict) or e.get('route_id')!=route['route_id']
                or e.get('replaces_route_id')!=original['route_id'] or e.get('cost_comparison')!=costs): return False
    strict=False
    for pair in costs.values():
        if (not isinstance(pair,dict) or not number(pair.get('before')) or not number(pair.get('after'))
                or pair['after']>pair['before']): return False
        strict = strict or pair['after']<pair['before']
    return strict
