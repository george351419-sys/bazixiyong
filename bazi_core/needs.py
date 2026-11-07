"""需求来自上游事实，候选路线不得创建或修改需求。"""
from math import isfinite


def validate_needs(needs):
    if not isinstance(needs,dict) or not needs: return ['need_registry']
    errors=[]
    for key,need in needs.items():
        if not isinstance(key,str) or not key or not isinstance(need,dict):
            errors.append('invalid_need');continue
        value=need.get('initial_demand')
        if (type(value) not in (int,float) or not isfinite(value) or value<0
                or need.get('need_type') not in ('climate','geju','fuyi','tongguan')
                or need.get('scenario_id')!='original' or type(need.get('required')) is not bool
                or not isinstance(need.get('evidence_refs'),list) or not need['evidence_refs']):
            errors.append('need:'+key)
        if need.get('need_type') == 'climate' and (
                need.get('severity') not in ('none','mild','urgent')
                or type(need.get('must_handle_now')) is not bool
                or type(need.get('acceptable_remaining')) not in (int,float)
                or not isfinite(need['acceptable_remaining']) or need['acceptable_remaining'] < 0):
            errors.append('need_priority:'+key)
        if need.get('must_handle_now') and (type(need.get('acceptable_remaining')) not in (int,float)
                or not isfinite(need['acceptable_remaining']) or need['acceptable_remaining'] < 0):
            errors.append('need_acceptance:'+key)
        tradeoffs=need.get('allowed_tradeoff_rules',[])
        if not isinstance(tradeoffs,list) or any(r not in ('POL-02','POL-06') for r in tradeoffs):
            errors.append('need_tradeoff:'+key)
        if 'baseline_gap' in need and need['baseline_gap'] != value:
            errors.append('need_baseline:'+key)
        rules=need.get('allowed_deferral_rules',[])
        if not isinstance(rules,list) or any(r not in ('POL-03','POL-04','POL-06') for r in rules):
            errors.append('need_deferral:'+key)
    return sorted(errors)


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
    return needs,sorted(missing)
