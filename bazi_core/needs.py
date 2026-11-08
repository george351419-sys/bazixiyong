"""需求来自上游事实，候选路线不得创建或修改需求。"""
from .numeric import finite as safe_finite
from math import isfinite
from copy import deepcopy


def validate_needs(needs):
    if not isinstance(needs,dict) or not needs: return ['need_registry']
    errors=[]
    for key,need in needs.items():
        if not isinstance(key,str) or not key or not isinstance(need,dict):
            errors.append('invalid_need');continue
        value=need.get('initial_demand')
        if (type(value) not in (int,float) or not safe_finite(value) or value<0
                or need.get('need_type') not in ('climate','geju','fuyi','tongguan')
                or need.get('scenario_id')!='original' or type(need.get('required')) is not bool
                or not isinstance(need.get('evidence_refs'),list) or not need['evidence_refs']):
            errors.append('need:'+key)
        if 'protection_required' in need and type(need['protection_required']) is not bool:
            errors.append('maintenance_flag:'+key)
        if need.get('protection_required') is True and need.get('required') is not True:
            errors.append('maintenance_optional:'+key)
        if need.get('maintenance_status')=='unknown': errors.append('maintenance_assessment:'+key)
        if need.get('method_relation_conflict'):
            errors.append('method_relation_conflict:'+key)
        if type(value) in (int,float) and value>0 and need.get('required') is not True:
            errors.append('positive_need_optional:'+key)
        if need.get('need_type') == 'climate' and (
                need.get('severity') not in ('none','mild','urgent')
                or type(need.get('must_handle_now')) is not bool
                or type(need.get('acceptable_remaining')) not in (int,float)
                or not safe_finite(need['acceptable_remaining']) or need['acceptable_remaining'] < 0):
            errors.append('need_priority:'+key)
        if need.get('must_handle_now') and (type(need.get('acceptable_remaining')) not in (int,float)
                or not safe_finite(need['acceptable_remaining']) or need['acceptable_remaining'] < 0):
            errors.append('need_acceptance:'+key)
        if 'choice_group' in need and (not isinstance(need['choice_group'],str) or not need['choice_group']):
            errors.append('need_choice_group:'+key)
        relation=need.get('method_relation')
        if relation is not None and (not isinstance(relation,dict)
                or relation.get('kind') not in ('alternative','joint','conflict')
                or not isinstance(relation.get('group_id'),str) or not relation['group_id']
                or not isinstance(relation.get('evidence_refs'),list) or not relation['evidence_refs']
                or any(not isinstance(ref,str) or not ref for ref in relation['evidence_refs'])):
            errors.append('method_relation:'+key)
        tradeoffs=need.get('allowed_tradeoff_rules',[])

        if not isinstance(tradeoffs,list) or any(r not in ('POL-02','POL-06') for r in tradeoffs):
            errors.append('need_tradeoff:'+key)
        if 'baseline_gap' in need and need['baseline_gap'] != value:
            errors.append('need_baseline:'+key)
        rules=need.get('allowed_deferral_rules',[])
        if not isinstance(rules,list) or any(r not in ('POL-03','POL-04','POL-06') for r in rules):
            errors.append('need_deferral:'+key)
    # 互斥治法只能连接同一需求来源的不同方法，不能让调用方用任意标签
    # 把扶抑、通关等彼此独立的正需求隐藏成“二选一”。
    groups={}
    for key,need in needs.items():
        if not isinstance(need,dict): continue
        group=need.get('choice_group')
        if not isinstance(group,str): continue
        if group:
            signature=(need.get('need_type'),need.get('scenario_id'),need.get('source_target_id'),
                       need.get('source_bundle_id'))
            method=need.get('source_demand_method')
            groups.setdefault(group,[]).append((key,signature,method))
    for group,members in groups.items():
        relations=[needs[key].get('method_relation') for key,_,_ in members]
        if any(not isinstance(r,dict) or r.get('kind')!='alternative' or r.get('group_id')!=group or not isinstance(r.get('evidence_refs'),list) or not r['evidence_refs'] for r in relations):
            errors.extend('unverified_method_relation:'+m[0] for m in members)
            errors.extend('invalid_choice_group:'+m[0] for m in members)
            continue
        if any(any(not isinstance(v,str) for v in signature) or not isinstance(method,str) for _,signature,method in members):
            errors.extend('invalid_choice_group:'+m[0] for m in members)
            continue
        signatures={m[1] for m in members}
        methods={m[2] for m in members}
        provenance_complete=all(isinstance(v,str) and bool(v) for _,signature,_ in members
            for v in (signature[2],signature[3]))
        if len(members)<2 or len(signatures)!=1 or not provenance_complete or any(not isinstance(v,str) or not v for v in methods) or len(methods)<2:
            errors.extend('invalid_choice_group:'+m[0] for m in members)
    return sorted(set(errors))


def build_needs(assessment, ledger, snapshot_id=None):
    """只转换可确定的成对需求；不同原始量不能以包络值冒充单一需求。"""
    needs,missing={},[]
    if not isinstance(snapshot_id,str) or not snapshot_id:
        return {},['assessment_snapshot_id']
    if assessment['severity']=='unknown': missing.append('climate_needs')
    for axis in assessment.get('axes',[]):
        key='climate:'+axis['axis']
        needs[key]=dict(need_type='climate',scenario_id='original',
            initial_demand=axis['remaining'], baseline_gap=axis['remaining'],
            baseline_ref=snapshot_id+':'+key,effect_scope='incremental_from_baseline',
            original_demand=axis['initial_demand'],original_signed_relief=axis['signed_relief'],
            required=axis['remaining']>0, handling='active' if axis['remaining']>0 else 'monitor',
            severity=axis['severity'], must_handle_now=axis['severity']=='urgent',
            acceptable_remaining=axis['acceptable_remaining'],
            allowed_deferral_rules=['POL-03','POL-04','POL-06'],
            evidence_refs=axis['evidence_refs'])
    for index,row in enumerate(ledger):
        pairs={(o['initial_demand'],o['remaining']) for o in row['observations'] if o['valid']}
        if not row['coverage_complete'] or len(pairs)!=1:
            missing.append('geju_need:'+row['target_id']);continue
        key='geju:'+str(index)+':'+row['target_id']+':'+row['demand_method']
        needs[key]=dict(need_type='geju',scenario_id='original',initial_demand=next(iter(pairs))[1],
            baseline_gap=next(iter(pairs))[1],baseline_ref=snapshot_id+':'+key,
            original_demand=next(iter(pairs))[0],effect_scope='incremental_from_baseline',
            required=next(iter(pairs))[1]>0,handling='active' if next(iter(pairs))[1]>0 else 'monitor',
            source_target_id=row['target_id'],source_demand_method=row['demand_method'],
            source_scenario_id=row['scenario_id'],source_bundle_id=row['route_bundle_id'],
            allowed_deferral_rules=[],evidence_refs=row['evidence_refs'])
    for key,need in needs.items():
        if need['need_type']!='geju': continue
        row=next(r for r in ledger if r['target_id']==need['source_target_id'] and r['demand_method']==need['source_demand_method'] and r['scenario_id']==need['source_scenario_id'] and r['route_bundle_id']==need['source_bundle_id'])
        maintenance=need['initial_demand']==0 and (need['original_demand']>0 or any(o.get('treatment_status') in ('protected','已保护') or o.get('protection_dependency') or (o.get('relief_realized') or 0)>0 for o in row['observations']))
        if maintenance:
            need.update(protection_required=True,required=True,handling='maintenance',maintenance_source=deepcopy(row['observations']))
            if any(o.get('relief_realized') is None for o in row['observations']):
                need['maintenance_status']='unknown'
                missing.append('maintenance_assessment:'+key)
        relations=[o.get('method_relation') for o in row['observations'] if o.get('method_relation') is not None]
        need['method_relation_observations']=deepcopy(row['observations']) if relations else []
        if relations and not all(x==relations[0] for x in relations):
            need['method_relation_conflict']=deepcopy(relations)
            missing.append('method_relation_conflict:'+key)
        elif relations: need['method_relation']=deepcopy(relations[0])
    assign_method_groups(needs)
    return needs,sorted(missing)


def assign_method_groups(needs):
    """不同方法默认均需覆盖；只有明确的替代关系允许互斥选择。"""
    for need in needs.values():
        relation=need.get('method_relation')
        if isinstance(relation,dict) and relation.get('kind')=='alternative' and isinstance(relation.get('group_id'),str):
            need['choice_group']=relation['group_id']
    return needs
