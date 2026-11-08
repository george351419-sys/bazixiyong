"""待审核干预及药效配对快照；不生成或批准药效。"""
from copy import deepcopy
import json


def intervention_recipe(route):
    actions=[{k:deepcopy(v) for k,v in a.items() if k!='evidence_refs'} for a in route.get('actions',[])]
    actions.sort(key=lambda a:json.dumps(a,ensure_ascii=False,sort_keys=True,allow_nan=False))
    usage=[{k:deepcopy(v) for k,v in a.items() if k!='evidence_refs'} for a in route.get('resource_usage',[])]
    usage.sort(key=lambda a:json.dumps(a,ensure_ascii=False,sort_keys=True,allow_nan=False))
    plans={k:deepcopy(e.get('dose_plan')) for k,e in route.get('goal_results',{}).items() if e.get('execution_status')=='planned'}
    plans.update({k:deepcopy(e.get('dose_plan')) for k,e in route.get('monitor_results',{}).items() if e.get('execution_status')=='planned'})
    effects={k:{f:deepcopy(v) for f,v in e.items() if f!='evidence_refs'} for k,e in route.get('goal_results',{}).items()}
    monitors={k:{f:deepcopy(v) for f,v in e.items() if f!='evidence_refs'} for k,e in route.get('monitor_results',{}).items()}
    return dict(assessed_effects=effects,assessed_monitors=monitors,route_id=route.get('route_id'),actions=actions,dose_plans=plans,
                resources=deepcopy(route.get('resources',{})),resource_usage=usage)
