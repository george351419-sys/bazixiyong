"""冻结分母的发布验收；主要阻断原因互斥，附加缺口允许重叠。"""
from .numeric import finite as safe_finite
from collections import Counter
import hashlib
import json
from math import isfinite


def digest(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def summarize(results, manifest, actual_hash, domain_validation=None):
    count=len(results);reasons=Counter();groups={};sources=Counter()
    conflicts=covered=unknown_conflicts=conditional=direction_released=action_released=0
    conflict_decided=conflict_evidence_pending=0
    additional=Counter();scenarios={};conflict_groups={}
    for item in results:
        result=item['result'];a=result['arbitration']
        pending=a['decision_status']=='pending'
        unresolved_conditional=(a['decision_status']=='conditional'
            and a.get('conditional_review_status')!='complete')
        conditional+=a['decision_status']=='conditional'
        direction_released+=a.get('release_ready',False)
        action_released+=a.get('action_release_ready',False)
        reason=a.get('primary_blocker') or ('evidence_gap' if pending else 'none')
        if pending or unresolved_conditional:
            reasons['conditional_review_pending' if unresolved_conditional else reason]+=1
        sources[item.get('source','unclassified')]+=1
        tag=result['tag'];groups.setdefault(tag,Counter())
        groups[tag]['total']+=1;groups[tag]['pending']+=pending
        for gap in set(a.get('gap_categories',[])): additional[gap]+=1
        month=result.get('tiaohou',{}).get('month_zhi')
        scenario='winter_summer' if isinstance(month,str) and month in '亥子丑巳午未' else 'other_months' if isinstance(month,str) else 'unknown_month'
        if result.get('geju',{}).get('ge_category')=='外格': scenario+=':external'
        scenarios.setdefault(scenario,Counter());scenarios[scenario]['total']+=1;scenarios[scenario]['pending']+=pending
        policy=a.get('policy_evaluation',{})
        # 冲突类型由评估器明确给出，不用喜忌列表推断药效。
        inputs=a.get('policy_inputs',{})
        if a.get('mode')=='external': continue
        fuyi=inputs.get('conflict_fuyi');geju=inputs.get('conflict_geju')
        if type(fuyi) is not bool or type(geju) is not bool: unknown_conflicts+=1
        if fuyi is True or geju is True:
            conflicts+=1
            group='both' if fuyi is True and geju is True else 'fuyi' if fuyi is True else 'geju'
            bucket=conflict_groups.setdefault(group,dict(total=0,resolved=0))
            bucket['total']+=1
            bucket['resolved']+=a['decision_status']=='decided' and a.get('action_release_ready') is True
            hits={h.get('rule_id') for h in policy.get('hits',[]) if isinstance(h,dict)}
            matched=(fuyi is not True or 'POL-06' in hits) and (geju is not True or bool(hits & {'POL-02','POL-03','POL-04','POL-05'}))
            covered+=matched
            conflict_decided+=a['decision_status']=='decided' and a.get('action_release_ready') is True
            conflict_evidence_pending+=pending and (policy.get('reason_code')=='evidence_insufficient' or 'evidence_gap' in a.get('gap_categories',[]))
    rate=lambda n:n/count if count else 0
    pending=sum(reasons.values())
    pending_limit=manifest['thresholds']['pending_rate_max']
    conflict_limit=manifest['thresholds']['conflict_coverage_min']
    thresholds=manifest.get('thresholds',{})
    direction_min=thresholds.get('direction_release_min_count',1)
    action_min=thresholds.get('action_release_min_count',1)
    failures=[]
    if actual_hash!=manifest['dataset_sha256']: failures.append('frozen_hash_mismatch')
    if count!=manifest['case_count'] or not count: failures.append('frozen_count_mismatch')
    if sources.get('unclassified'): failures.append('baseline_source_unclassified')
    if type(pending_limit) not in (int,float) or not safe_finite(pending_limit) or not 0<=pending_limit<=1:
        failures.append('invalid_release_threshold')
    elif rate(pending)>pending_limit: failures.append('pending_rate_exceeded')
    coverage=covered/conflicts if conflicts else None
    if type(conflict_limit) not in (int,float) or not safe_finite(conflict_limit) or not 0<=conflict_limit<=1:
        failures.append('invalid_release_threshold')
    elif coverage is None or coverage<conflict_limit or unknown_conflicts: failures.append('conflict_coverage_insufficient')
    if type(direction_min) is not int or direction_min<1 or type(action_min) is not int or action_min<1:
        failures.append('invalid_release_threshold')
    if type(direction_min) is int and direction_min>0 and sum(bool(item['result']['arbitration'].get('release_ready')) for item in results) < direction_min:
        failures.append('no_direction_release_cases')
    if type(action_min) is int and action_min>0 and sum(bool(item['result']['arbitration'].get('action_release_ready')) for item in results) < action_min:
        failures.append('no_action_release_cases')
    if not (isinstance(domain_validation,dict) and domain_validation.get('passed') is True
            and domain_validation.get('required_scope')=='integrated_action'
            and domain_validation.get('integrated_action_positive_count',0)>0
            and domain_validation.get('birth_positive_count',0)>0
            and domain_validation.get('case_count',0)>0
            and domain_validation.get('compared_count')==domain_validation.get('case_count')):
        failures.append('independent_comparison_missing_or_failed')
    if not conflict_decided:
        failures.append('no_resolved_conflict_action_cases')
    comparison=domain_validation or {}
    if not all(comparison.get(k,0)>0 for k in ('conflict_positive_count','conflict_negative_count')):
        failures.append('independent_conflict_comparison_missing')
    if any(not v['resolved'] for v in conflict_groups.values()): failures.append('unresolved_conflict_group')
    if any(not all(comparison.get('conflict_groups',{}).get(g,{}).get(k,0)>0 for k in ('positive','negative')) for g in conflict_groups):
        failures.append('independent_conflict_group_missing')
    profile=manifest.get('release_profile_sha256')
    profile_spec=manifest.get('release_profile')
    if (not isinstance(profile,str) or len(profile)!=64 or comparison.get('release_profile_sha256')!=profile
            or not isinstance(profile_spec,dict) or digest(profile_spec)!=profile
            or any(digest(item.get('config',{})) not in profile_spec.get('config_sha256',[]) for item in results)):
        failures.append('release_profile_unverified')
    provenance=manifest.get('provenance',{})
    if (provenance.get('independent_gold_standard') is not True
            or provenance.get('review_status')!='independent_domain_validation_approved'):
        failures.append('independent_validation_missing')
    return dict(case_count=count,frozen_hash=actual_hash,passed=not failures,failures=failures,
        pending_count=pending,pending_rate=rate(pending),conditional_count=conditional,conditional_rate=rate(conditional),
        direction_release_count=direction_released,action_release_count=action_released,
        primary_gap_counts=dict(reasons),primary_gap_rates={k:rate(v) for k,v in reasons.items()},
        conflict_count=conflicts,covered_conflicts=covered,conflict_coverage=coverage,
        conflict_groups=conflict_groups,conflict_decided_count=conflict_decided,conflict_evidence_pending_count=conflict_evidence_pending,
        conflict_unknown_count=unknown_conflicts,additional_gap_counts=dict(additional),scenario_groups={k:dict(v) for k,v in scenarios.items()},baseline_sources=dict(sources),
        groups={k:dict(v) for k,v in groups.items()})
