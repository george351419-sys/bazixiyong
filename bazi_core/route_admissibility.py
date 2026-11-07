"""排序前的逐需求可接受性检查；不能用排序胜出来替代政策授权。"""
from .route_effects import number


def assess_admissibility(route, effects, needs, active_rules, policy_version=None):
    rejected, missing, approvals = [], [], []
    registry=route.get('evidence_registry', {})
    registry=registry if isinstance(registry,dict) else {}
    for effect in effects:
        target=effect['target_id'];need=needs[target]
        if (need.get('must_handle_now') and effect['remaining'] > need['acceptable_remaining']
                and effect['status']!='deferred'):
            rejected.append('urgent_need_unresolved:'+target)
        if effect['aggravation'] <= 0: continue
        auths=route.get('tradeoff_authorizations', [])
        auths=auths if isinstance(auths,list) else []
        approved=False
        for auth in auths:
            if not isinstance(auth,dict) or auth.get('target_id')!=target: continue
            baseline_ref=need.get('baseline_ref')
            if (not isinstance(baseline_ref,str) or not baseline_ref
                    or effect.get('baseline_ref')!=baseline_ref
                    or auth.get('baseline_ref')!=baseline_ref
                    or not policy_version or auth.get('policy_version')!=policy_version): continue
            rule=auth.get('rule_id')
            if rule not in active_rules or rule not in need.get('allowed_tradeoff_rules', []): continue
            cap=auth.get('max_aggravation');refs=auth.get('evidence_refs')
            if not number(cap) or effect['aggravation']>cap or not isinstance(refs,list) or not refs: continue
            valid=True
            for ref in refs:
                evidence=registry.get(ref) if isinstance(ref,str) else None
                if (not isinstance(evidence,dict) or evidence.get('route_id')!=route['route_id']
                        or evidence.get('target_id')!=target or evidence.get('rule_id')!=rule
                        or evidence.get('baseline_ref')!=baseline_ref
                        or evidence.get('policy_version')!=policy_version
                        or evidence.get('max_aggravation')!=cap
                        or evidence.get('aggravation')!=effect['aggravation']):
                    valid=False;break
            if valid:
                approved=True
                approvals.append(dict(target_id=target,rule_id=rule,baseline_ref=baseline_ref,
                                      policy_version=policy_version,aggravation=effect['aggravation'],
                                      max_aggravation=cap,evidence_refs=refs))
                break
        if not approved: rejected.append('unauthorized_aggravation:'+target)
    return sorted(set(rejected)), missing, approvals
