"""审计反例，构造预期仅验证合同，不作为独立领域金标准。"""
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from bazi_core.paipan import run_paipan,analyze_birth
from bazi_core.needs import validate_needs
from bazi_core.arbitration import arbitrate
from bazi_core.domain_validation import validate_domain_dataset,REQUIRED_EXPECTATIONS
from bazi_core.release_audit import digest,summarize
from tests.test_fusion_completion import prepared

class AuditV24(unittest.TestCase):
    def test_protection_cannot_publish_false_condition(self):
        f,m=prepared();r=f['fusion_evidence']['routes'][0]
        for k,e in r['goal_results'].items():
            e.update(status='protected',execution_status='realized',relief_realized=1,remaining=0,
                condition_expr={'op':'eq','path':'ws.tag','value':'从强'},
                protection_dependency=dict(remaining_without=1,evidence_refs=['protect:'+k]))
            r['evidence_registry']['protect:'+k]=dict(route_id=r['route_id'],target_id=k,remaining_without=1)
            r['evidence_registry'][e['evidence_refs'][0]]=dict(deepcopy(e),route_id=r['route_id'],target_id=k)
        for a in r['actions']: a['intended_action']='protect'
        self.assertFalse(arbitrate(f,m)['action_release_ready'])

    def test_dates_do_not_truncate_or_swap(self):
        r=run_paipan(birth='公历1990年五月三十一日8点')
        self.assertTrue(r['ok'],r);self.assertTrue(r['公历'].startswith('1990-05-31'))
        self.assertFalse(run_paipan(birth='公历1990-13-05 08:00')['ok'])

    def test_chinese_time_and_midnight(self):
        r=run_paipan(birth='公历1990年5月15日下午八点半')
        self.assertTrue(r['ok'],r);self.assertTrue(r['公历'].endswith('20:30:00'))
        self.assertFalse(run_paipan(birth='公历1990年5月15日晚上12点')['ok'])
        r=run_paipan(birth='公历1990年5月16日00:00')
        self.assertTrue(r['ok'],r);self.assertTrue(r['公历'].endswith('00:00:00'))

    def test_malformed_groups_return_errors(self):
        self.assertTrue(validate_needs({'x':None}))
        for group in ([1],{'x':1}):
            self.assertTrue(validate_needs({'x':dict(choice_group=group)}))

    def test_time_interval_conflict_survives_public_entry(self):
        r=analyze_birth(birth='公历1990年5月15日辰时',lon=117.2,truesun=True)
        self.assertFalse(r['ok']);self.assertTrue(r['need_confirm'])
        self.assertEqual(len(r['candidate_pillars']),2)
        r=run_paipan(birth='公历1990年5月15日辰时',truesun=False)
        self.assertTrue(r['ok'],r);self.assertTrue(r['representative_time']);self.assertTrue(r['time_interval'])

    def test_approved_flags_without_comparison_cannot_pass_gate(self):
        manifest=dict(case_count=1,dataset_sha256='fixed',thresholds=dict(pending_rate_max=.1,conflict_coverage_min=.95),
            provenance=dict(independent_gold_standard=True,review_status='independent_domain_validation_approved'))
        a=dict(decision_status='decided',release_ready=True,action_release_ready=True,
            policy_inputs=dict(conflict_fuyi=True,conflict_geju=False),policy_evaluation=dict(hits=[dict(rule_id='POL-06')]))
        report=summarize([dict(result=dict(tag='身弱',arbitration=a),source='implementation_snapshot')],manifest,'fixed')
        self.assertFalse(report['passed']);self.assertIn('independent_comparison_missing_or_failed',report['failures'])

    def test_independent_dataset_requires_real_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            expected={k:None for k in REQUIRED_EXPECTATIONS}
            data=dict(review_status='approved',reviewer='contract-fixture',expected_fixed_at='fixture',cases=[
                dict(id='one',source='synthetic-contract-only',chart=dict(input_kind='real_chart'),expected=expected)])
            path=Path(tmp)/'cases.json';path.write_text(json.dumps(data))
            spec=dict(path='cases.json',sha256=digest(data))
            actual={}
            for key in expected:
                node=actual
                parts=key.split('.')
                for part in parts[:-1]:node=node.setdefault(part,{})
                node[parts[-1]]=None
            self.assertTrue(validate_domain_dataset(spec,tmp,lambda c,cfg:actual)['passed'])
            actual['tag']='wrong'
            self.assertFalse(validate_domain_dataset(spec,tmp,lambda c,cfg:actual)['passed'])
            spec['sha256']='wrong'
            self.assertFalse(validate_domain_dataset(spec,tmp,lambda c,cfg:actual)['passed'])
            self.assertFalse(validate_domain_dataset(None,tmp)['passed'])

if __name__=='__main__':unittest.main()
