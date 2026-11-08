"""构造反例检验输入和验收合同，不作为独立命理金标准。"""
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from bazi_core.paipan import run_paipan,analyze_birth
from bazi_core.arbitration import arbitrate
from bazi_core.engine import analyze
from bazi_core.domain_validation import validate_domain_dataset,REQUIRED_EXPECTATIONS,ACTION_EXPECTATIONS
from bazi_core.release_audit import digest
from tests.test_fusion_completion import prepared

class AuditV25(unittest.TestCase):
    def test_protect_requires_safe_bearing(self):
        for safety in (False,None):
            f,m=prepared();r=f['fusion_evidence']['routes'][0]
            for k,e in r['goal_results'].items():
                e.update(status='protected',execution_status='realized',relief_realized=1,remaining=0,
                    protection_dependency=dict(remaining_without=1,evidence_refs=['p:'+k]))
                r['evidence_registry']['p:'+k]=dict(route_id=r['route_id'],target_id=k,remaining_without=1)
                r['evidence_registry'][e['evidence_refs'][0]]=dict(deepcopy(e),route_id=r['route_id'],target_id=k)
            for a in r['actions']:a['intended_action']='protect'
            r['checks']['bearing_safe']['value']=safety;r['evidence_registry']['bearing_safe']['value']=safety
            self.assertFalse(arbitrate(f,m)['action_release_ready'])

    def test_interval_spanning_day_segment_is_not_single_result(self):
        r=analyze_birth(birth='公历2026年2月11日寅时',truesun=False)
        self.assertFalse(r['ok']);self.assertTrue(r['need_confirm'])
        self.assertEqual([x['day'] for x in r['candidate_solar_term_info']],[6,7])

    def test_precise_clock_narrows_shichen(self):
        r=run_paipan(birth='公历1990年5月15日辰时7点30分')
        self.assertTrue(r['ok'],r);self.assertTrue(r['公历'].endswith('07:30:00'))
        self.assertFalse(r['representative_time'])
        self.assertFalse(run_paipan(birth='公历1990年5月15日辰时10点')['ok'])
        self.assertTrue(run_paipan(birth='公历1990年5月15日子时23点30分')['ok'])

    def test_clock_must_match_full_token(self):
        for clock in ('08:300','123:30','08:30:999','08:30:59.5','08:30:'):
            self.assertFalse(run_paipan(birth='公历1990年5月15日'+clock)['ok'],clock)
        self.assertTrue(run_paipan(birth='公历1990年5月15日08:30:59')['ok'])

    def test_calendar_conflict_precedes_external_backend(self):
        with patch('bazi_core.paipan._run_external_paipan') as external:
            for birth in (None,'公历1990年5月15日8点'):
                args=dict(birth=birth) if birth else dict(y=1990,m=5,d=15,h=8)
                r=run_paipan(**args,lunar=True,calendar='solar',skill_dir='unused')
                self.assertFalse(r['ok'])
            external.assert_not_called()

    def test_direction_fixture_cannot_certify_action_scope(self):
        chart=dict(gans=list('丙庚己丙'),zhis=list('午寅酉寅'),input_kind='real_chart')
        actual=analyze(chart);self.assertEqual(actual['arbitration']['decision_status'],'pending')
        expected={}
        for key in REQUIRED_EXPECTATIONS:
            node=actual
            for part in key.split('.'):node=node[part]
            expected[key]=node
        with tempfile.TemporaryDirectory() as tmp:
            data=dict(review_status='approved',reviewer='contract-only',expected_fixed_at='fixture',
                cases=[dict(id='x',source='constructed-contract-only',chart=chart,expected=expected)])
            Path(tmp,'cases.json').write_text(json.dumps(data))
            spec=dict(path='cases.json',sha256=digest(data))
            self.assertTrue(validate_domain_dataset(spec,tmp)['passed'])
            self.assertFalse(validate_domain_dataset(spec,tmp,required_scope='integrated_action')['passed'])
            data['cases'][0]['scope']='integrated_action'
            Path(tmp,'cases.json').write_text(json.dumps(data));spec['sha256']=digest(data)
            self.assertIn('independent_action_expectations_missing',validate_domain_dataset(spec,tmp)['failures'])

    def test_action_scope_compares_full_release_contract(self):
        expected={k:None for k in REQUIRED_EXPECTATIONS}
        expected.update({'arbitration.decision_status':'decided','arbitration.mode':'integrated',
            'arbitration.release_ready':True,'arbitration.action_release_ready':True,
            'final_xiyong.effective_source':'arbitration_integrated','final_xiyong.release_scope':'integrated_recommendation',
            'final_xiyong.release_ready':True,'final_xiyong.action_release_ready':True,'final_xiyong.actionable':True,
            'final_xiyong.conditional_review_status':'complete','final_xiyong.positions':[{'fixture':'contract-only'}]})
        actual={}
        for key,value in expected.items():
            node=actual;parts=key.split('.')
            for part in parts[:-1]:node=node.setdefault(part,{})
            node[parts[-1]]=value
        with tempfile.TemporaryDirectory() as tmp:
            data=dict(review_status='approved',reviewer='contract-only',expected_fixed_at='fixture',scope='integrated_action',
                cases=[dict(id='x',source='constructed-contract-only',chart={'input_kind':'real_chart'},expected=expected)])
            Path(tmp,'cases.json').write_text(json.dumps(data));spec=dict(path='cases.json',sha256=digest(data))
            evaluate=lambda c,cfg:actual
            self.assertTrue(validate_domain_dataset(spec,tmp,evaluate,required_scope='integrated_action')['passed'])
            actual['final_xiyong']['effective_source']='wangshuai'
            self.assertFalse(validate_domain_dataset(spec,tmp,evaluate,required_scope='integrated_action')['passed'])

if __name__=='__main__':unittest.main()
