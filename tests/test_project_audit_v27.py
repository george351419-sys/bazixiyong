"""v27反例；合成审核记录只验证合同。"""
import unittest
from copy import deepcopy
from bazi_core.arbitration import arbitrate,demand_ledger,evaluate_policies
from bazi_core.needs import build_needs,validate_needs
from bazi_core.route_effects import assess_effects
from tests.test_fusion_completion import prepared,bind_intervention_for_test

class AuditV27(unittest.TestCase):
    def test_drug_swap_invalidates_effect_assessment(self):
        f,m=prepared();self.assertTrue(arbitrate(f,m)['action_release_ready'])
        r=f['fusion_evidence']['routes'][0]
        for a in r['actions']:
            a['gan']='辛'
            for ref in a['evidence_refs']:r['evidence_registry'][ref]['gan']='辛'
        x=arbitrate(f,m)
        self.assertFalse(x['action_release_ready']);self.assertTrue(any('intervention_effect_binding' in e for e in x['missing_evidence']))
        bind_intervention_for_test(r)
        self.assertTrue(arbitrate(f,m)['action_release_ready'])

    def test_method_dose_application_and_resource_changes_need_review(self):
        for kind in ('method','dose','application','resource','effect'):
            f,m=prepared();r=f['fusion_evidence']['routes'][0]
            if kind=='method':
                for a in r['actions']:
                    a['method']='different'
                    for ref in a['evidence_refs']:r['evidence_registry'][ref]['method']='different'
            elif kind=='dose':
                for e in r['goal_results'].values():
                    e['dose_plan']['max_amount']=2
                    r['evidence_registry'][e['evidence_refs'][0]]=dict(deepcopy(e),route_id=r['route_id'],target_id=next(k for k,v in r['goal_results'].items() if v is e))
            elif kind=='application':
                for a in r['actions']:a['application_id']='new'
                r['resource_usage'][0]['application_id']='new'
                r['evidence_registry']['allocation']['allocation']=deepcopy(r['resource_usage'][0])
            elif kind=='resource':
                r['resources']['fire_capacity']['capacity']=2
                r['evidence_registry']['allocation']['resource']=deepcopy(r['resources']['fire_capacity'])
            else:
                for key,e in r['goal_results'].items():
                    e.update(relief_feasible=.5,projected_remaining=.5)
                    r['evidence_registry'][e['evidence_refs'][0]]=dict(deepcopy(e),route_id=r['route_id'],target_id=key)
            x=arbitrate(f,m);self.assertFalse(x['action_release_ready'],kind)
            self.assertTrue(any('intervention_effect_binding' in e for e in x['missing_evidence']),(kind,x['missing_evidence']))

    def test_unquantified_zero_gap_stays_pending(self):
        ledger=demand_ledger([dict(name='已治',status='已治',evidence=[dict(target_id='x',initial_demand=1,remaining=0)])])
        needs,missing=build_needs(dict(severity='none',axes=[]),ledger,'base')
        n=next(iter(needs.values()));self.assertTrue(n['required']);self.assertTrue(n['protection_required'])
        self.assertEqual(n['maintenance_status'],'unknown');self.assertTrue(missing)
        x=evaluate_policies('none',needs=needs,needs_complete=True,routes=[],conflict_fuyi=False,conflict_geju=False)
        self.assertEqual(x['decision_status'],'pending');self.assertNotEqual(x['reason_code'],'no_new_advice')

    def test_maintenance_cannot_be_optional_or_omitted(self):
        n=dict(need_type='geju',scenario_id='original',initial_demand=0,required=False,evidence_refs=['r'],protection_required=True)
        self.assertIn('maintenance_optional:x',validate_needs({'x':n}))
        _,errors=assess_effects(dict(route_id='r',goals=[],actions=[]),{'x':n})
        self.assertIn('uncovered_need:x',errors)
        n['protection_required']='yes'
        self.assertIn('maintenance_flag:x',validate_needs({'x':n}))

    def test_conflicting_method_observations_are_retained_and_blocked(self):
        data=[dict(name=kind,evidence=[dict(target_id='x',initial_demand=1,remaining=1,method_relation=dict(kind=kind,group_id='g',evidence_refs=['review']))]) for kind in ('joint','conflict')]
        needs,missing=build_needs(dict(severity='none',axes=[]),demand_ledger(data),'base')
        n=next(iter(needs.values()));self.assertEqual(len(n['method_relation_conflict']),2)
        self.assertEqual(len(n['method_relation_observations']),2)
        self.assertTrue(any(e.startswith('method_relation_conflict:') for e in missing))
        self.assertTrue(validate_needs(needs))

if __name__=='__main__':unittest.main()
