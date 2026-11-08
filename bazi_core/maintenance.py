"""只补充维护依赖的审核结论，不覆盖原局已测量数值。"""
from copy import deepcopy
from .route_effects import number


def resolve_maintenance(assessments, needs, facts, assessment_id, registry):
    from .arbitration import demand_ledger
    merged=deepcopy(needs);errors=[]
    if assessments is None: return merged,errors
    if not isinstance(assessments,dict): return merged,['maintenance_assessments:not_object']
    ledger=demand_ledger(facts.get('geju',{}).get('xiyong_geju',{}).get('treatment_status',[]))
    for key,entry in assessments.items():
        need=needs.get(key) if isinstance(key,str) else None
        error='maintenance_evidence:'+str(key)
        if not isinstance(need,dict) or need.get('maintenance_status')!='unknown' or not isinstance(entry,dict):
            errors.append(error);continue
        row=next((r for r in ledger if all(need.get(field)==r[source] for field,source in
            [('source_target_id','target_id'),('source_demand_method','demand_method'),
             ('source_scenario_id','scenario_id'),('source_bundle_id','route_bundle_id')])),None)
        withdrawal=entry.get('withdrawal');refs=entry.get('evidence_refs');outcome=entry.get('outcome')
        if (row is None or entry.get('source_ledger_row')!=row or entry.get('original_need')!=need
                or entry.get('baseline_ref')!=need.get('baseline_ref') or need.get('initial_demand')!=0
                or not isinstance(withdrawal,dict) or withdrawal.get('scope')!='original_target'
                or withdrawal.get('method')!='reviewed_withdrawal'
                or not number(withdrawal.get('remaining_with')) or not number(withdrawal.get('remaining_without'))
                or withdrawal['remaining_with']!=need['initial_demand']
                or outcome not in ('protect_required','no_dependency')
                or not isinstance(refs,list) or not refs):
            errors.append(error);continue
        gap=withdrawal['remaining_without']-withdrawal['remaining_with']
        if (outcome=='protect_required' and gap<=0) or (outcome=='no_dependency' and gap!=0):
            errors.append(error);continue
        valid=True
        assessment={k:v for k,v in entry.items() if k!='evidence_refs'}
        for ref in refs:
            proof=registry.get(ref) if isinstance(ref,str) else None
            if (not isinstance(proof,dict) or proof.get('target_id')!=key
                    or proof.get('facts_snapshot_id')!=facts['snapshot_id']
                    or proof.get('assessment_snapshot_id')!=assessment_id
                    or proof.get('maintenance_assessment')!=assessment):
                valid=False;break
        if not valid: errors.append(error);continue
        required=outcome=='protect_required'
        merged[key].update(maintenance_status='verified',protection_required=required,required=required,
            handling='maintenance' if required else 'monitor',maintenance_resolution=deepcopy(entry))
    return merged,sorted(set(errors))
