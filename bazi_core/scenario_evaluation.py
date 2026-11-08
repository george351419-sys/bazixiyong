"""经核验基线上的气候能量干预；不冒充重新排盘或全局结构反事实。"""
from .numeric import finite as safe_finite
from copy import deepcopy
from math import isfinite,fsum,ulp
from . import metadata as M
from .assessment_identity import snapshot_error,assessment_identity
from .release_audit import digest


def _baseline_error(facts):
    if not isinstance(facts,dict): return 'fact_snapshot_missing'
    if facts.get('schema_version')!=1 or any(not isinstance(facts.get(k),dict) for k in ('ws','geju','tiaohou','fuyi')):
        return 'fact_snapshot_invalid_shape'
    return snapshot_error(facts)


def climate_intervention(facts,model,delta):
    from .arbitration import climate,POLICY_VERSION
    error=_baseline_error(facts)
    if error: return dict(status='unknown',reason_code=error)
    before=climate(facts,model)
    if before['severity']=='unknown': return dict(status='unknown',reason_code=before['reason_code'])
    if (not isinstance(delta,dict) or any(w not in M.WUXING_LIST or type(v) not in (int,float)
        or not safe_finite(v) for w,v in delta.items())):
        return dict(status='unknown',reason_code='invalid_energy_intervention')
    normalized={w:delta.get(w,0) for w in M.WUXING_LIST}
    changed=deepcopy(facts);energies={};adjustments={}
    for w,base in facts['element_energy'].items():
        try: value=fsum([base,normalized[w]])
        except OverflowError: return dict(status='unknown',reason_code='nonfinite_energy_intervention')
        tolerance=8*ulp(max(abs(base),abs(normalized[w]),1.0))
        if value<0:
            if value < -tolerance: return dict(status='unknown',reason_code='negative_energy_intervention')
            adjustments[w]=dict(raw_value=value,tolerance=tolerance);value=0.0
        energies[w]=value
    changed['element_energy']=energies
    after=climate(changed,model)
    if after['severity']=='unknown': return dict(status='unknown',reason_code=after['reason_code'])
    assessment_id=assessment_identity(facts,model,POLICY_VERSION)
    if not assessment_id: return dict(status='unknown',reason_code='assessment_identity_invalid')
    effects={}
    for old,new in zip(before['axes'],after['axes']):
        change=old['remaining']-new['remaining']
        effects['climate:'+old['axis']]=dict(current_remaining=old['remaining'],
            relief_feasible=max(0,change),projected_aggravation=max(0,-change),
            signed_relief=change,projected_remaining=new['remaining'])
    return dict(status='evaluated',scope='climate_energy_only',before=before,after=after,
        energy_delta=normalized,element_energy_before=deepcopy(facts['element_energy']),element_energy_after=energies,
        numerical_adjustments=adjustments,effects=effects,model_version=model['version'],model_sha256=digest(model),
        assessment_snapshot_id=assessment_id,
        scenario_id=digest(dict(assessment_id=assessment_id,delta=normalized,scope='climate_energy_only',schema='scenario_v2')),
        facts_snapshot_id=facts['snapshot_id'],requires_structure_and_bearing_reassessment=True)


def climate_removal(facts,model,record_ids):
    error=_baseline_error(facts)
    if error: return dict(status='unknown',reason_code=error)
    if not isinstance(record_ids,list) or any(not isinstance(i,str) for i in record_ids) or len(set(record_ids))!=len(record_ids):
        return dict(status='unknown',reason_code='invalid_removal_ids')
    records={}
    for row in facts.get('energy_evidence',[]):
        if (not isinstance(row,dict) or not isinstance(row.get('id'),str) or not row['id'] or row['id'] in records
                or row.get('wuxing') not in M.WUXING_LIST or type(row.get('power')) not in (int,float)
                or not safe_finite(row['power']) or row['power']<0):
            return dict(status='unknown',reason_code='invalid_energy_record')
        records[row['id']]=row
    if any(i not in records for i in record_ids): return dict(status='unknown',reason_code='missing_removal_record')
    delta={w:-fsum(records[i]['power'] for i in record_ids if records[i]['wuxing']==w) for w in M.WUXING_LIST}
    result=climate_intervention(facts,model,delta)
    result['removed_records']=list(record_ids)
    if result['status']=='evaluated':
        result['removal_id']=digest(dict(scenario_id=result['scenario_id'],record_ids=sorted(record_ids)))
    return result


def prepare_fusion_context(facts,model):
    from .arbitration import climate,demand_ledger,POLICY_VERSION
    from .needs import build_needs
    error=_baseline_error(facts)
    if error: return dict(status='unknown',reason_code=error,missing_evidence=[error],assessment_snapshot_id=None)
    assessment=climate(facts,model)
    ledger=demand_ledger(facts['geju'].get('xiyong_geju',{}).get('treatment_status',[]))
    ident=assessment_identity(facts,model,POLICY_VERSION)
    needs,missing=build_needs(assessment,ledger,ident)
    from .fusion_evidence import unresolved_geju_rows
    return dict(status='prepared',facts=deepcopy(facts),facts_snapshot_id=facts['snapshot_id'],
        assessment_snapshot_id=ident,climate=assessment,needs=needs,demand_ledger=ledger,
        unresolved_geju_targets=unresolved_geju_rows(facts),
        unresolved_maintenance_targets={k:deepcopy(n) for k,n in needs.items() if n.get('maintenance_status')=='unknown'},
        missing_evidence=missing,policy_version=POLICY_VERSION,
        provider_requirements=['bearing_capacity','fuyi','tongguan','structure_guard',
            'projected_effects','dose_limits','shared_resources','counterfactuals','maintenance_assessments'])
