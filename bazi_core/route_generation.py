"""从已存在的格局治疗作用生成维护候选，不把未知的跨维度证据填成真。"""
from copy import deepcopy
import hashlib
import json
from . import metadata as M


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
    if not records and geju.get('ge_category')=='外格':
        records=[dict(id='wuxing:'+w,wuxing=w,precision='wuxing')
                 for w in xy.get('special_yong_wuxing',[]) if w in M.WUXING_LIST]
    if not records: return [], ['geju_selected_route']
    restrictions=sorted(deepcopy(xy.get('conditional_yong_shen', [])),key=lambda r:r['id'])
    payload=dict(records=records,restrictions=restrictions,ge_status=geju.get('ge_status'),
                 ge_name=geju.get('main_ge_name'))
    digest=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,
        allow_nan=False,separators=(',',':')).encode()).hexdigest()[:16]
    route_id='geju:structure:'+digest
    # 成格维护属于结构条件，不能虚构数值需求或治疗药力。
    actions=[]
    registry={}
    structure_goals={}
    for record in records:
        target='structure:'+str(geju.get('main_ge_name'))+':'+record['id']
        ref='selection:'+record['id']
        precision=record.get('precision','gan')
        action=dict(gan=record.get('gan'),wuxing=record.get('wuxing'),precision=precision,
            target_id=target,record_id=record['id'],method='maintain_structure',
            intended_action='protect',recommendation_status='unverified_intent',evidence_refs=[ref])
        actions.append(action)
        registry[ref]=dict(route_id=route_id,target_id=target,gan=record.get('gan'),
            wuxing=record.get('wuxing'),precision=precision,method='maintain_structure',
            record=deepcopy(record),source='geju.xiyong_geju.selected_records' if precision=='gan'
            else 'geju.xiyong_geju.special_yong_wuxing',ge_status=geju.get('ge_status'))
        structure_goals[target]=dict(record_id=record['id'],precision=precision,
            record=deepcopy(record),evidence_refs=[ref],dependency_status='unknown')
    missing=['structure_guard_verification','climate_effects','bearing_capacity',
             'cross_dimension_compatibility']
    missing += ['source_restriction:'+r['id'] for r in restrictions]
    return [dict(route_id=route_id,route_kind='structure_maintenance',origin='geju_external_wuxing' if all(r.get('precision')=='wuxing' for r in records) else 'geju_selected_records',
        structure=dict(name=geju.get('main_ge_name'),status=geju.get('ge_status'),
                       ge_shen=geju.get('ge_shen')),
        selected_records=records,source_restrictions=restrictions,actions=actions,
        goals=sorted(structure_goals),structure_goals=structure_goals,goal_results={},checks={},evidence_registry=registry,
        execution_status='requires_structure_and_cross_dimension_validation',
        missing_evidence=missing)],missing


def generate_repair_candidates(facts, needs, climate_model=None):
    """枚举来源有据的补缺意图；药效未知时不填零，不成为可执行处方。"""
    candidates=[]
    sources=[]
    for gan in facts.get('tiaohou',{}).get('yongshen',[]):
        if gan in M.GAN_LIST: sources.append((gan,M.WUXING_GAN[gan],'tiaohou.yongshen'))
    for wx in facts.get('fuyi',{}).get('favored',[]):
        if wx in M.WUXING_LIST: sources.append((None,wx,'fuyi.favored'))
    for gan,wx,source in sources:
        targets=sorted(k for k,n in needs.items() if n['initial_demand']>0)
        if not targets: continue
        route_id='repair:'+str(gan or wx)+':'+source
        presence=facts.get('tiaohou',{}).get('presence',{}).get(gan,{}) if gan else {}
        absent=presence.get('state')=='原局无'
        registry={};actions=[]
        for target in targets:
            ref=route_id+':'+target
            method='conditional_supply' if absent else 'evaluate_increment'
            registry[ref]=dict(route_id=route_id,target_id=target,gan=gan,wuxing=wx,
                               method=method,source=source)
            actions.append(dict(gan=gan,wuxing=wx,precision='gan' if gan else 'wuxing',
                target_id=target,method=method,intended_action='wait_condition' if absent else 'increase',
                evidence_refs=[ref],recommendation_status='unverified_intent'))
        candidates.append(dict(route_id=route_id,route_kind='conditional_repair' if absent else 'deficit_repair',
            origin=source,goals=targets,actions=actions,checks={},goal_results={},
            evidence_registry=registry,execution_status='not_executed',
            relief_realized=0,relief_feasible=None,
            missing_evidence=['relief_feasible','bearing_capacity','cross_dimension_compatibility',
                              'supply_condition' if absent else 'dose_limit'],
            interpretation='仅为待评估修复意图，不因列入候选就建议加强'))
    if isinstance(climate_model,dict) and climate_model.get('review_status')=='approved':
        from .scenario_evaluation import climate_intervention
        for route in candidates:
            wx=route['actions'][0]['wuxing']
            amounts=[]
            for key,need in needs.items():
                if need['need_type']!='climate' or need['initial_demand']<=0: continue
                coefficient=climate_model.get('axes',{}).get(key.split(':')[-1],{}).get('effect',{}).get(wx)
                if type(coefficient) in (int,float) and coefficient>0:
                    amounts.append(need['initial_demand']/coefficient)
            if amounts:
                amount=min(amounts)
                projection=climate_intervention(facts,climate_model,{wx:amount})
                route['climate_projection']=projection
                route['proposed_energy_increment']=amount
                # 能量投影不证明该字原局可用，也不证明格局与日主能承受。
                route['execution_status']='not_executed'
    return candidates
