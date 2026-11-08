"""构造反例只验证代码合同，不是领域金标准。"""
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from bazi_core.arbitration import build_facts,arbitrate,demand_ledger,evaluate_policies
from bazi_core.needs import build_needs,assign_method_groups,validate_needs
from bazi_core.paipan import analyze_birth
from bazi_core.domain_validation import validate_domain_dataset,REQUIRED_EXPECTATIONS
from bazi_core.release_audit import digest
from tests.test_fusion_completion import prepared,bind_intervention_for_test

class AuditV26(unittest.TestCase):
    def protected_route(self):
        base,_=prepared()
        records=[dict(evidence_id='source:'+k,drug_id='drug:丙',gan='丙',target_id=k,power=1,method='克掉') for k in ('climate:cold','climate:heat','climate:dry','climate:wet')]
        facts=build_facts(base['ws'],dict(xiyong_geju=dict(treatment_allocations=records)),base['tiaohou'],base['fuyi'])
        f,m=prepared(facts);r=f['fusion_evidence']['routes'][0]
        for a in r['actions']:
            k=a['target_id'];e=r['goal_results'][k];ref='p:'+k
            a.update(intended_action='protect',action_id='action:'+k,source_action_id='source:'+k,protection_ref=ref)
            e.update(status='protected',execution_status='realized',relief_realized=1,remaining=0,protection_dependency=dict(remaining_without=1,evidence_refs=[ref]))
            e.pop('dose_plan',None)
            r['evidence_registry'][e['evidence_refs'][0]]=dict(deepcopy(e),route_id=r['route_id'],target_id=k)
            r['evidence_registry'][ref]=dict(route_id=r['route_id'],target_id=k,remaining_without=1,gan='丙',
                action_id=a['action_id'],method=a['method'],source_action_id=a['source_action_id'],baseline_ref=e['baseline_ref'],
                source_record=next(x for x in records if x['target_id']==k))
        bind_intervention_for_test(r)
        return f,m

    def test_protection_binding_positive_and_extra_drug_rejected(self):
        f,m=self.protected_route();self.assertTrue(arbitrate(f,m)['action_release_ready'])
        r=f['fusion_evidence']['routes'][0];a=deepcopy(r['actions'][0]);a.update(gan='辛',evidence_refs=['extra']);r['actions'].append(a)
        r['evidence_registry']['extra']=dict(route_id=r['route_id'],target_id=a['target_id'],gan='辛',method=a['method'])
        self.assertFalse(arbitrate(f,m)['action_release_ready'])

    def test_zero_gap_keeps_maintenance(self):
        ledger=demand_ledger([dict(name='protected',status='protected',evidence=[dict(target_id='x',initial_demand=1,relief_realized=1,remaining=0,demand_method='protect')])])
        needs,errors=build_needs(dict(severity='none',axes=[]),ledger,'base')
        self.assertFalse(errors);n=next(iter(needs.values()));self.assertTrue(n['protection_required']);self.assertTrue(n['required'])
        result=evaluate_policies('none',needs=needs,needs_complete=True,routes=[],conflict_geju=False,conflict_fuyi=False)
        self.assertNotEqual(result['reason_code'],'no_new_advice')

    def test_methods_not_alternative_without_evidence(self):
        needs={k:dict(need_type='geju',scenario_id='original',source_target_id='x',source_scenario_id='original',source_bundle_id='same',source_demand_method=k,initial_demand=1,required=True,evidence_refs=['source']) for k in ('a','b')}
        assign_method_groups(needs);self.assertTrue(all('choice_group' not in n for n in needs.values()))
        for n in needs.values():n['method_relation']=dict(kind='alternative',group_id='reviewed',evidence_refs=['relation'])
        assign_method_groups(needs);self.assertFalse(validate_needs(needs))
        for n in needs.values():n.pop('method_relation')
        self.assertTrue(validate_needs(needs))

    def test_manual_reference_preserves_actual_term(self):
        a=analyze_birth(y=2026,m=9,d=28,h=12,truesun=False)
        b=analyze_birth(y=2026,m=9,d=28,h=12,truesun=False,solar_term_day=1)
        self.assertTrue(b['ok'],b);self.assertEqual(a['tiaohou']['yongshen'],b['tiaohou']['yongshen'])
        self.assertEqual(b['solar_term_info']['current_jieqi_name'],'秋分')
        self.assertTrue(b['solar_term_override']['conflict']);self.assertEqual(b['input']['solar_term_day'],1)

    def test_malformed_dataset_reports_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            for data in ([],None,'text',{'cases':[]}):
                Path(tmp,'cases.json').write_text(json.dumps(data))
                result=validate_domain_dataset(dict(path='cases.json',sha256=digest(data)),tmp)
                self.assertFalse(result['passed']);self.assertTrue(result['failures'])

    def test_birth_dataset_checks_real_pipeline(self):
        birth=dict(y=2026,m=9,d=28,h=12,truesun=False,sect=2)
        actual=analyze_birth(**birth)
        paths=REQUIRED_EXPECTATIONS+('paipan_meta.八字','paipan_meta.原始公历','paipan_meta.公历','paipan_meta.节气参考公历','paipan_meta.time_convention','solar_term_info.current_jieqi_name')
        expected={}
        for key in paths:
            value=actual
            for part in key.split('.'):value=value[part]
            expected[key]=value
        with tempfile.TemporaryDirectory() as tmp:
            data=dict(review_status='approved',reviewer='contract-fixture',expected_fixed_at='fixture',cases=[dict(id='birth',source='constructed-contract-only',birth_input=birth,expected=expected)])
            path=Path(tmp,'cases.json');path.write_text(json.dumps(data));spec=dict(path='cases.json',sha256=digest(data))
            self.assertTrue(validate_domain_dataset(spec,tmp,require_birth=True)['passed'])
            expected['paipan_meta.八字']='wrong';path.write_text(json.dumps(data));spec['sha256']=digest(data)
            self.assertFalse(validate_domain_dataset(spec,tmp,require_birth=True)['passed'])

if __name__=='__main__':unittest.main()
