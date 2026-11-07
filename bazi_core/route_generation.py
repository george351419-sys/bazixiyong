"""从已存在的格局治疗作用生成维护候选，不把未知的跨维度证据填成真。"""
from copy import deepcopy
import hashlib
import json


def generate_routes(facts, needs):
    gj=facts['geju'].get('xiyong_geju', {})
    allocations=gj.get('treatment_allocations', [])
    # 同一解算组合共同分配过药力，因此保持为一个候选，禁止拆药后重新拼接。
    valid=[e for e in allocations if isinstance(e,dict) and e.get('evidence_id')
           and e.get('drug_id') and e.get('target_id') and e.get('power',0)>0]
    if not valid:
        return generate_structure_route(facts)
    valid=sorted(valid,key=lambda e:(e['evidence_id'],json.dumps(e,sort_keys=True,ensure_ascii=False)))
    selected_ids={e['drug_id'] for e in valid}
    restrictions=sorted([deepcopy(r) for r in gj.get('conditional_yong_shen', [])
        if isinstance(r,dict) and r.get('id') in selected_ids],
        key=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=False))
    fingerprint=hashlib.sha256(json.dumps(dict(allocations=valid,restrictions=restrictions),ensure_ascii=False,sort_keys=True,
        allow_nan=False,separators=(',',':')).encode()).hexdigest()[:16]
    route_id='geju:maintain:'+fingerprint
    registry={}
    actions=[]
    mappings=[]
    for e in sorted(valid,key=lambda e:e['evidence_id']):
        gan=e['drug_id'].split(':')[-1]
        target=e['target_id']
        demand_method='生扶' if e['method']=='生扶' else '直接处理' if e['method'] in ('克掉','制伏','化掉','通关') else 'structural'
        matching=sorted(key for key,n in needs.items() if n.get('source_target_id')==target
            and n.get('source_demand_method')==demand_method
            and n.get('source_scenario_id','original')==e.get('scenario_id','original')
            and n.get('source_bundle_id','selected')==e.get('route_bundle_id','selected'))
        mappings.append(dict(source_action_id=e['evidence_id'],source_target_id=target,
            original_method=e['method'],demand_method=demand_method,
            status='mapped' if matching else 'unmapped',need_ids=matching,
            power_scope='shared_original_evidence',shared_reference=len(matching)>1))
        registry[e['evidence_id']]=dict(deepcopy(e),route_id=route_id,gan=gan,
            source_target_id=target,source='geju.xiyong_geju.treatment_allocations')
        for need_id in matching:
            # 这里是维护已有药，不是对剩余缺口再次扣减原局药效。
            evidence_id=e['evidence_id']+':need:'+need_id
            registry[evidence_id]=dict(registry[e['evidence_id']],target_id=need_id,method='maintain_existing')
            actions.append(dict(gan=gan,target_id=need_id,method='maintain_existing',
                original_method=e['method'],original_power=e['power'],
                source_action_id=e['evidence_id'],power_scope='shared_original_evidence',
                demand_method=demand_method,intended_action='protect',
                recommendation_status='unverified_intent',
                source_target_id=target,evidence_refs=[evidence_id]))
    route=dict(route_id=route_id,route_kind='maintenance',
        interpretation='维护原局已有效药；不表示继续加强，也不新增药力',origin='original_geju_treatment',
        execution_status='requires_cross_dimension_validation',
        goals=sorted({a['target_id'] for a in actions}),actions=actions,
        source_mappings=mappings,source_restrictions=restrictions,
        restriction_status='requires_review' if restrictions else 'none_declared',
        original_allocations=deepcopy(valid),goal_results={},checks={},evidence_registry=registry,
        missing_evidence=['protection_dependency','climate_effects','bearing_capacity',
                          'cross_dimension_compatibility'])
    route['missing_evidence'] += ['unmapped_source_action:'+m['source_action_id']
        for m in mappings if m['status']=='unmapped']
    route['missing_evidence'] += ['source_restriction:'+str(r['id']) for r in restrictions]
    if not actions:
        route['missing_evidence'].append('geju_need_mapping')
    return [route], list(route['missing_evidence'])


def generate_structure_route(facts):
    geju=facts['geju']
    xy=geju.get('xiyong_geju', {})
    records=sorted(deepcopy(xy.get('selected_records', [])),key=lambda r:r['id'])
    if not records: return [], ['geju_selected_route']
    restrictions=sorted(deepcopy(xy.get('conditional_yong_shen', [])),key=lambda r:r['id'])
    payload=dict(records=records,restrictions=restrictions,ge_status=geju.get('ge_status'),
                 ge_name=geju.get('main_ge_name'))
    digest=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,
        allow_nan=False,separators=(',',':')).encode()).hexdigest()[:16]
    route_id='geju:structure:'+digest
    # 成格维护属于结构条件，不能虚构数值需求或治疗药力。
    actions=[dict(gan=r['gan'],record_id=r['id'],method='maintain_structure',
        intended_action='protect',recommendation_status='unverified_intent',
        evidence_refs=['selection:'+r['id']]) for r in records]
    registry={'selection:'+r['id']:dict(route_id=route_id,record=deepcopy(r),
        source='geju.xiyong_geju.selected_records',ge_status=geju.get('ge_status')) for r in records}
    missing=['structure_guard_verification','climate_effects','bearing_capacity',
             'cross_dimension_compatibility']
    missing += ['source_restriction:'+r['id'] for r in restrictions]
    return [dict(route_id=route_id,route_kind='structure_maintenance',origin='geju_selected_records',
        structure=dict(name=geju.get('main_ge_name'),status=geju.get('ge_status'),
                       ge_shen=geju.get('ge_shen')),
        selected_records=records,source_restrictions=restrictions,actions=actions,
        goals=[],goal_results={},checks={},evidence_registry=registry,
        execution_status='requires_structure_and_cross_dimension_validation',
        missing_evidence=missing)],missing
