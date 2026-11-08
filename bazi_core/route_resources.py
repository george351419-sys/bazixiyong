"""新路线的共享容量账：一次投用可作用多个需求，但容量只扣一次。"""
from .route_effects import number
from .contracts import action_identity
from .intervention import intervention_recipe


def assess_resources(route,effects):
    projected={e['target_id']:e for e in effects if e.get('execution_status')=='planned'}
    if not projected and not any(a.get('intended_action')=='limit' for a in route.get('actions',[])): return [],[]
    monitors={k:e for k,e in projected.items() if e.get('is_monitor')}
    planned={k:e for k,e in projected.items() if not e.get('is_monitor')}
    resources=route.get('resources',{});usage=route.get('resource_usage',[])
    registry=route.get('evidence_registry',{});errors=[];allocations=[];used={};applications={}
    certification=route.get('intervention_assessment')
    refs=certification.get('evidence_refs') if isinstance(certification,dict) else None
    try: recipe=intervention_recipe(route)
    except (TypeError,ValueError): recipe=None
    if (recipe is None or not isinstance(refs,list) or not refs
            or any(not isinstance(ref,str) or not isinstance(registry.get(ref),dict)
                or registry[ref].get('route_id')!=route['route_id']
                or registry[ref].get('intervention_recipe')!=recipe for ref in refs)):
        errors.append('intervention_effect_binding')
    if not projected:
        return sorted(set(errors)),[]
    if not resources or not usage: return errors+['planned_resource_ledger'],[]
    for item in usage:
        ident=item.get('application_id');rid=item.get('resource_id');targets=item.get('target_ids')
        amount=item.get('amount');refs=item.get('evidence_refs')
        if (not isinstance(ident,str) or not ident or ident in applications or not isinstance(rid,str)
                or rid not in resources or not number(amount) or amount<=0
                or not isinstance(targets,list) or not targets
                or any(not isinstance(t,str) or t not in planned for t in targets)
                or len(set(targets))!=len(targets) or not isinstance(refs,list) or not refs):
            errors.append('invalid_resource_usage');continue
        resource=resources[rid];unit=resource.get('unit')
        if not number(resource.get('capacity')) or not isinstance(unit,str) or not unit:
            errors.append('invalid_resource:'+rid);continue
        valid=all(isinstance(ref,str) and isinstance(registry.get(ref),dict)
            and registry[ref].get('route_id')==route['route_id'] and registry[ref].get('allocation')==item
            and registry[ref].get('resource')==resource for ref in refs)
        actions=[a for a in route['actions'] if a.get('application_id')==ident]
        identities={action_identity(a) for a in actions}
        if (not valid or not actions or None in identities or len(identities)!=1
                or {a['target_id'] for a in actions}!=set(targets)):
            errors.append('resource_evidence:'+ident);continue
        if any(planned[t].get('dose_plan',{}).get('amount')!=amount
               or planned[t]['dose_plan'].get('unit')!=unit for t in targets):
            errors.append('resource_dose:'+ident);continue
        applications[ident]=set(targets);used[rid]=used.get(rid,0)+amount
        allocations.append(dict(application_id=ident,resource_id=rid,amount=amount,target_ids=targets))
    for target,effect in monitors.items():
        refs=effect.get('application_ids',[])
        if not refs or any(a not in applications for a in refs): errors.append('monitor_application:'+target)
    for target in planned:
        # 同一目标的计划剂量不可拆成多次完整用量重复获益。
        if sum(target in ts for ts in applications.values())!=1: errors.append('resource_target:'+target)
    # 反向核账：目标已覆盖不代表同目标下的其他动作也获准投用。
    for action in route.get('actions', []):
        target=action.get('target_id')
        if not isinstance(target,str):
            errors.append('resource_action_target');continue
        if target not in planned: continue
        application=action.get('application_id')
        if (not isinstance(application,str) or application not in applications
                or target not in applications[application]):
            errors.append('unbudgeted_action:'+str(target))
    for rid,total in used.items():
        if total>resources[rid]['capacity']+1e-9: errors.append('resource_capacity:'+rid)
    return sorted(set(errors)),allocations
