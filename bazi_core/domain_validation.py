"""独立审定案例加载及逐字段比对；预期由审定文件提供，不从当前输出生成。"""
import json
from pathlib import Path
from .release_audit import digest

REQUIRED_EXPECTATIONS=('tag','geju.main_ge_name','geju.ge_status','tiaohou.yongshen',
                       'final_xiyong.favored','final_xiyong.disliked')


ACTION_EXPECTATIONS=('arbitration.decision_status','arbitration.mode','arbitration.release_ready',
    'arbitration.action_release_ready','final_xiyong.effective_source','final_xiyong.release_scope',
    'final_xiyong.release_ready','final_xiyong.action_release_ready','final_xiyong.actionable',
    'final_xiyong.conditional_review_status','final_xiyong.positions')


def validate_domain_dataset(spec, root, evaluator=None, required_scope='direction', require_birth=False):
    report=dict(passed=False,case_count=0,compared_count=0,failures=[],
        required_scope=required_scope,conflict_positive_count=0,conflict_negative_count=0,birth_positive_count=0,scope_counts={},integrated_action_positive_count=0)
    if not isinstance(spec,dict):
        report['failures']=['independent_dataset_missing'];return report
    try:
        path=(Path(root)/spec['path']).resolve()
        path.relative_to(Path(root).resolve())
        data=json.loads(path.read_text())
        if not isinstance(data,dict): raise ValueError('independent_dataset_not_object')
        if digest(data)!=spec['sha256']: raise ValueError('independent_dataset_hash_mismatch')
        if data.get('review_status')!='approved' or not data.get('reviewer') or not data.get('expected_fixed_at'):
            raise ValueError('independent_dataset_review_missing')
        profile=data.get('release_profile_sha256')
        profile_spec=data.get('release_profile')
        if profile is not None and (not isinstance(profile_spec,dict) or digest(profile_spec)!=profile): raise ValueError('independent_release_profile_invalid')
        report['release_profile_sha256']=profile
        report['conflict_groups']={}
        cases=data.get('cases')
        if not isinstance(cases,list) or not cases: raise ValueError('independent_dataset_empty')
        report['case_count']=len(cases);report['dataset_sha256']=digest(data)
        if required_scope not in ('direction','integrated_action'): raise ValueError('independent_scope_invalid')
        ids=set()
        for case in cases:
            if (not isinstance(case,dict) or not isinstance(case.get('id'),str) or case['id'] in ids
                    or not case.get('source') or case['source']=='implementation_snapshot'):
                raise ValueError('independent_case_provenance_invalid')
            ids.add(case['id']);expected=case.get('expected',{})
            birth_input=case.get('birth_input')
            birth_negative=isinstance(birth_input,dict) and isinstance(expected,dict) and expected.get('ok') is False
            required=('ok','stage') if birth_negative else REQUIRED_EXPECTATIONS
            if not isinstance(expected,dict) or not all(k in expected for k in required):
                raise ValueError('independent_expected_layers_missing')
            scope=case.get('scope',data.get('scope','direction'))
            if scope not in ('direction','integrated_action'): raise ValueError('independent_scope_invalid')
            report['scope_counts'][scope]=report['scope_counts'].get(scope,0)+1
            if scope=='integrated_action':
                if not all(k in expected for k in ACTION_EXPECTATIONS):
                    raise ValueError('independent_action_expectations_missing')
                if expected['arbitration.action_release_ready'] is True:
                    fixed={'arbitration.decision_status':'decided','arbitration.mode':'integrated',
                        'arbitration.release_ready':True,'final_xiyong.effective_source':'arbitration_integrated',
                        'final_xiyong.release_scope':'integrated_recommendation','final_xiyong.release_ready':True,
                        'final_xiyong.action_release_ready':True,'final_xiyong.actionable':True,
                        'final_xiyong.conditional_review_status':'complete'}
                    if any(digest(expected[k])!=digest(v) for k,v in fixed.items()) or not expected['final_xiyong.positions']:
                        raise ValueError('independent_action_scope_conflict')
                    report['integrated_action_positive_count']+=1
            config=case.get('config')
            if profile is not None and digest(config or {}) not in profile_spec.get('config_sha256',[]): raise ValueError('independent_release_profile_mismatch')
            if config is not None and not isinstance(config,dict): raise ValueError('independent_config_invalid')
            if birth_input is not None:
                from .paipan import analyze_birth
                allowed={'birth','y','m','d','h','minute','second','sex','lon','truesun','lunar','leap','calendar','solar_term_day','tiaohou_segment','sect','eot','time_basis'}
                if not isinstance(birth_input,dict) or set(birth_input)-allowed or 'chart' in case:
                    raise ValueError('independent_birth_input_invalid')
                if 'truesun' not in birth_input or 'sect' not in birth_input:
                    raise ValueError('independent_time_convention_missing')
                if not birth_negative:
                    fields=('paipan_meta.八字','paipan_meta.原始公历','paipan_meta.公历',
                        'paipan_meta.节气参考公历','paipan_meta.time_convention','solar_term_info.current_jieqi_name')
                    if not all(k in expected for k in fields): raise ValueError('independent_birth_expectations_missing')
                actual=analyze_birth(**birth_input,config=config)
                if not birth_negative and actual.get('ok') is True: report['birth_positive_count']+=1
            else:
                chart=case.get('chart')
                if not isinstance(chart,dict) or chart.get('input_kind')!='real_chart':
                    raise ValueError('independent_real_chart_required')
                if evaluator is None:
                    from .engine import analyze
                    actual=analyze(chart,config=config)
                else: actual=evaluator(chart,config)
            for key,value in expected.items():
                result=actual
                for part in key.split('.'):
                    if not isinstance(result,dict) or part not in result:
                        raise ValueError('independent_expected_path_invalid:'+key)
                    result=result[part]
                if digest(result)!=digest(value):
                    report['failures'].append('independent_mismatch:'+case['id']+':'+key)
            conflict_keys=('arbitration.policy_inputs.conflict_fuyi','arbitration.policy_inputs.conflict_geju')
            if all(type(expected.get(k)) is bool for k in conflict_keys) and any(expected[k] for k in conflict_keys):
                if 'arbitration.action_release_ready' in expected:
                    key='conflict_positive_count' if expected['arbitration.action_release_ready'] else 'conflict_negative_count'
                    report[key]+=1
                    f,g=(expected[k] for k in conflict_keys)
                    group='both' if f and g else 'fuyi' if f else 'geju'
                    bucket=report['conflict_groups'].setdefault(group,dict(positive=0,negative=0))
                    bucket['positive' if expected['arbitration.action_release_ready'] else 'negative']+=1
            report['compared_count']+=1
        if required_scope=='integrated_action' and report['integrated_action_positive_count']==0:
            report['failures'].append('independent_action_positive_cases_missing')
        if require_birth and report['birth_positive_count']==0:
            report['failures'].append('independent_birth_positive_cases_missing')
        report['passed']=not report['failures']
    except (OSError,KeyError,ValueError,TypeError) as exc:
        report['failures'].append(str(exc))
    return report
