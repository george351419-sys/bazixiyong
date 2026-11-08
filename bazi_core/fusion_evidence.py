"""已审定的跨维度评估输入；不内置未经标定的力量兑换或药效系数。

适配器必须绑定同一事实与需求基线。review_status 是内部审核合同，不是外部认证。
"""
from copy import deepcopy
from .needs import validate_needs,assign_method_groups
from .contracts import route_shape_errors, action_identity


def unresolved_geju_rows(facts):
    from .arbitration import demand_ledger
    rows=demand_ledger(facts.get('geju',{}).get('xiyong_geju',{}).get('treatment_status',[]))
    return {'geju:'+str(i)+':'+r['target_id']+':'+r['demand_method']: r
            for i,r in enumerate(rows) if not r['coverage_complete']}


def remaining_need_errors(errors, merged, facts):
    """只能由绑定原始定性目标的审核评估补齐，不能替换已测得的数值。"""
    rows=unresolved_geju_rows(facts)
    unresolved=[e for e in errors if not (e.startswith('geju_need:') and
        all(key in merged and merged[key].get('need_type')=='geju'
            for key,row in rows.items() if row['target_id']==e[len('geju_need:'):]) and
        any(row['target_id']==e[len('geju_need:'):] for row in rows.values()))]
    return [e for e in unresolved if not (e.startswith('maintenance_assessment:')
        and merged.get(e[len('maintenance_assessment:'):],{}).get('maintenance_status')=='verified'
        and merged[e[len('maintenance_assessment:'):]].get('maintenance_resolution'))]

DIMENSIONS=('geju','fuyi','tongguan','special_structure','cross_dimension')
POLICY_FIELDS=('conflict_fuyi','conflict_geju','bear','alternative','rescue_broken','ge_status','repair_feasible')


def apply_evidence(bundle, facts, assessment_id, needs):
    errors=[]
    if not isinstance(bundle,dict): return {}, {}, {}, ['fusion_evidence_missing']
    if (bundle.get('review_status')!='approved' or not bundle.get('version')
            or not bundle.get('reviewer') or bundle.get('facts_snapshot_id')!=facts.get('snapshot_id')
            or bundle.get('assessment_snapshot_id')!=assessment_id or not assessment_id):
        return {}, {}, {}, ['fusion_evidence_binding']
    registry=bundle.get('evidence_registry',{})
    registry=registry if isinstance(registry,dict) else {}
    coverage=bundle.get('coverage',{})
    normalized={}
    additions=bundle.get('needs',{})
    structural_rows=unresolved_geju_rows(facts)
    if not isinstance(additions,dict): additions={};errors.append('fusion_needs')
    for key,need in additions.items():
        if (not isinstance(key,str) or key in needs or not isinstance(need,dict) or need.get('need_type') not in ('fuyi','tongguan','geju')
                or need.get('baseline_ref')!=assessment_id+':'+str(key)):
            errors.append('fusion_need:'+str(key));continue
        if need.get('need_type')=='geju':
            row=structural_rows.get(key)
            if (row is None or need.get('source_ledger_row')!=row
                    or any(o['initial_demand'] is not None for o in row['observations'])
                    or any(need.get(field)!=row[source] for field,source in
                           [('source_target_id','target_id'),('source_demand_method','demand_method'),
                            ('source_scenario_id','scenario_id'),('source_bundle_id','route_bundle_id')])):
                errors.append('fusion_structural_source:'+key);continue
        normalized[key]=deepcopy(need)
    for key,need in normalized.items():
        refs=need.get('evidence_refs',[])
        if not isinstance(refs,list) or not refs:
            errors.append('fusion_need_evidence:'+key);continue
        for ref in refs:
            proof=registry.get(ref) if isinstance(ref,str) else None
            if (not isinstance(proof,dict) or proof.get('target_id')!=key
                    or proof.get('facts_snapshot_id')!=facts['snapshot_id']
                    or proof.get('assessment_snapshot_id')!=assessment_id
                    or proof.get('need')!={k:v for k,v in need.items() if k!='evidence_refs'}):
                errors.append('fusion_need_evidence:'+key)
    merged=deepcopy(dict(needs,**normalized))
    from .maintenance import resolve_maintenance
    merged,maintenance_errors=resolve_maintenance(bundle.get('maintenance_assessments'),merged,facts,assessment_id,registry)
    errors+=maintenance_errors
    assign_method_groups(merged)
    errors+=validate_needs(merged)
    for key,need in merged.items():
        relation=need.get('method_relation')
        if not isinstance(relation,dict): continue
        refs=relation.get('evidence_refs',[])
        if not isinstance(refs,list): continue
        for ref in refs:
            proof=registry.get(ref) if isinstance(ref,str) else None
            if (not isinstance(proof,dict) or proof.get('relation')!=relation
                    or proof.get('facts_snapshot_id')!=facts['snapshot_id']
                    or proof.get('assessment_snapshot_id')!=assessment_id):
                errors.append('method_relation_evidence:'+key)

    complete={}
    for dimension in DIMENSIONS:
        entry=coverage.get(dimension) if isinstance(coverage,dict) else None
        if not isinstance(entry,dict) or entry.get('status')!='complete':
            errors.append('coverage:'+dimension);continue
        refs=entry.get('evidence_refs');ids=entry.get('need_ids')
        if (not isinstance(ids,list) or any(not isinstance(k,str) or k not in merged or merged[k]['need_type']!=dimension for k in ids)
                or not isinstance(refs,list) or not refs):
            errors.append('coverage:'+dimension);continue
        expected={k for k,n in merged.items() if n['need_type']==dimension}
        if set(ids)!=expected: errors.append('coverage_targets:'+dimension)
        for ref in refs:
            proof=registry.get(ref) if isinstance(ref,str) else None
            if (not isinstance(proof,dict) or proof.get('dimension')!=dimension
                    or proof.get('facts_snapshot_id')!=facts['snapshot_id']
                    or proof.get('assessment_snapshot_id')!=assessment_id):
                errors.append('coverage_evidence:'+dimension)
        complete[dimension]='complete'
    inputs=bundle.get('policy_inputs')
    if not isinstance(inputs,dict): errors.append('policy_inputs');inputs={}
    for key in ('conflict_fuyi','conflict_geju'):
        if type(inputs.get(key)) is not bool: errors.append(key)
    filtered={k:deepcopy(inputs[k]) for k in POLICY_FIELDS if k in inputs}
    policy_refs=bundle.get('policy_evidence',{})
    if not isinstance(policy_refs,dict): policy_refs={}
    for key,value in filtered.items():
        refs=policy_refs.get(key,[])
        if not isinstance(refs,list) or not refs:
            errors.append('policy_evidence:'+key);continue
        for ref in refs:
            proof=registry.get(ref) if isinstance(ref,str) else None
            if (not isinstance(proof,dict) or proof.get('field')!=key or proof.get('value')!=value
                    or proof.get('facts_snapshot_id')!=facts['snapshot_id']
                    or proof.get('assessment_snapshot_id')!=assessment_id):
                errors.append('policy_evidence:'+key)
    routes=bundle.get('routes')
    errors+=route_shape_errors(routes)
    filtered['routes']=deepcopy(routes) if isinstance(routes,list) else []
    return merged,complete,filtered,sorted(set(errors))


def assemble_route(policy, routes):
    """只组装验证器选中的路线，不从未验证的候选标签推导行动。"""
    choice=policy.get('choice')
    selected=next((r for r in routes if r['route_id']==choice),None)
    evaluation=next((r for r in policy.get('route_evaluation',[]) if r['route_id']==choice),None)
    if policy.get('reason_code')=='no_new_advice':
        return dict(positions=[],favored=[],avoid=[],actionable=False,reason_code='no_new_advice'),[]
    if not selected or not evaluation or evaluation['result']!='eligible': return None,['selected_route']
    positions=[];errors=[]
    effects={e['target_id']:e for e in evaluation['goal_results']}
    seen=set()
    for action in selected['actions']:
        target=action['target_id'];effect=effects.get(target)
        identity=action_identity(action)
        if identity is None: errors.append('action_identity:'+target);continue
        _,wx,_=identity
        intended=action.get('intended_action')
        if intended not in ('increase','protect','limit','wait_condition'):
            errors.append('action_intent:'+target);continue
        if intended=='increase' and (not effect or effect.get('execution_status')!='planned' or effect.get('relief_feasible',0)<=0 or effect['initial_demand']<=0):
            errors.append('increase_effect:'+target);continue
        if intended=='protect' and effect and effect['status']=='protected':
            ref=action.get('protection_ref');proof=selected.get('evidence_registry',{}).get(ref) if isinstance(ref,str) else None
            dependency=selected.get('goal_results',{}).get(target,{}).get('protection_dependency',{})
            if (not isinstance(proof,dict) or ref not in dependency.get('evidence_refs',[])
                    or not isinstance(action.get('action_id'),str) or not action['action_id']
                    or proof.get('action_id')!=action['action_id']
                    or proof.get('method')!=action.get('method')
                    or proof.get('source_action_id')!=action.get('source_action_id')
                    or not isinstance(action.get('source_action_id'),str) or not action['source_action_id']
                    or action_identity(proof)!=identity or proof.get('baseline_ref')!=effect['baseline_ref']):
                errors.append('protection_action_binding:'+target);continue
        if intended=='protect' and not (effect and effect['status']=='protected'):
            guards=[g for g in evaluation.get('structural_results',[]) if g['target_id']==target]
            if (not guards or not all(g['dependency_status']=='verified' for g in guards)
                    or action_identity(selected.get('structure_goals',{}).get(target,{}).get('record',{}))!=identity):
                errors.append('protection_dependency:'+target);continue
        if intended=='wait_condition' and (not effect or effect['status']!='deferred'):
            errors.append('deferred_effect:'+target);continue
        # 限制具体药物需要经验证的反事实，本接口不由忌神标签自动制造。
        if intended=='limit':
            counterfactual=action.get('counterfactual')
            from .route_effects import number
            registry=selected.get('evidence_registry',{})
            refs=counterfactual.get('evidence_refs',[]) if isinstance(counterfactual,dict) else []
            if (not isinstance(counterfactual,dict) or not effect or not isinstance(refs,list) or not refs
                    or effect.get('execution_status')!='planned'
                    or not isinstance(action.get('action_id'),str) or not action['action_id']
                    or counterfactual.get('action_id')!=action['action_id']
                    or action_identity(counterfactual)!=identity
                    or counterfactual.get('method')!=action.get('method')
                    or not number(counterfactual.get('remaining_without_limit'))
                    or counterfactual.get('remaining_with_limit')!=effect['remaining']
                    or counterfactual['remaining_without_limit']<=effect['remaining']
                    or counterfactual.get('baseline_ref')!=effect['baseline_ref']
                    or any(not isinstance(ref,str) or not isinstance(registry.get(ref),dict)
                        or registry[ref].get('route_id')!=selected['route_id']
                        or registry[ref].get('target_id')!=target
                        or registry[ref].get('counterfactual')!=counterfactual for ref in refs)):
                errors.append('limit_counterfactual:'+target);continue
        key=(action.get('gan'),wx,target,intended)
        if key in seen: continue
        seen.add(key)
        positions.append(dict(idx=len(positions)+1,gan=action.get('gan'),wx=wx,
            precision=action.get('precision','gan'),target_id=target,action=intended,
            route_id=selected['route_id'],application_id=action.get('application_id'),
            dose_plan=deepcopy(effect.get('dose_plan')) if effect and effect.get('execution_status')=='planned' and intended in ('increase','limit') else None,
            resource_allocations=deepcopy([a for a in evaluation.get('resource_allocations',[])
                if a['application_id']==action.get('application_id')]),
            baseline_ref=effect.get('baseline_ref') if effect else None,
            condition_expr=(effect.get('condition_expr') if effect and effect.get('condition_expr') is not None
                else action.get('condition_expr')),
            dose=None,observed_relief_ratio=effect.get('dose') if effect and effect.get('execution_status')=='realized' else None,
            projected_dose=effect.get('projected_dose') if effect and effect.get('execution_status')=='planned' else None,
            execution_status=effect.get('execution_status') if effect else None,evidence_refs=deepcopy(action['evidence_refs']),
            roles=[effect['need_type'] if effect else 'geju']))
    favored=list(dict.fromkeys(p['wx'] for p in positions if p['action'] in ('increase','protect')))
    avoided=list(dict.fromkeys(p['wx'] for p in positions if p['action']=='limit'))
    if set(favored)&set(avoided): errors.append('wuxing_action_conflict')
    return dict(positions=positions,favored=favored,avoid=avoided,actionable=bool(positions)
        and policy['decision_status']=='decided',reason_code='selected'),sorted(set(errors))
