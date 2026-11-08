"""执行前提、监测关联和发布字段反例；不作为命理金标准。"""
import json
import unittest
from copy import deepcopy
from bazi_core.arbitration import arbitrate,POLICY_VERSION
from bazi_core.assessment_identity import assessment_identity
from bazi_core.route_effects import false_execution_conditions
from tests.test_fusion_completion import prepared,bind_intervention_for_test
import tests.test_project_audit_v26 as v26

class AuditV28(unittest.TestCase):
    def competitor(self,value):
        f,m=prepared();b=f['fusion_evidence'];bad=deepcopy(b['routes'][0]);bad['route_id']='other'
        for proof in bad['evidence_registry'].values():
            if proof.get('route_id')=='reviewed':proof['route_id']='other'
        e=bad['goal_results']['climate:cold'];e['condition_expr']=dict(op='eq',path='ws.tag' if value is False else 'missing.value',value='从强')
        bad['evidence_registry'][e['evidence_refs'][0]]['condition_expr']=deepcopy(e['condition_expr'])
        bind_intervention_for_test(bad);b['routes'].append(bad)
        return f,m

    def test_false_route_is_excluded_without_cascading_errors(self):
        f,m=self.competitor(False);x=arbitrate(f,m)
        self.assertTrue(x['action_release_ready']);self.assertEqual(x['policy_evaluation']['choice'],'reviewed')
        bad=next(r for r in x['policy_evaluation']['route_evaluation'] if r['route_id']=='other')
        self.assertEqual(bad['applicability'],'not_applicable');self.assertTrue(bad['evaluation_skipped'])
        self.assertEqual(bad['missing_evidence'],[]);self.assertEqual(bad['resource_allocations'],[])

    def test_unknown_route_still_blocks_and_deferral_is_not_excluded(self):
        f,m=self.competitor(None);self.assertFalse(arbitrate(f,m)['action_release_ready'])
        r=f['fusion_evidence']['routes'][1];r['goal_results']['climate:cold']['status']='deferred'
        self.assertFalse(false_execution_conditions(r,f))

    def monitored(self):
        f,m=prepared();old=f['fusion_evidence']['assessment_snapshot_id']
        m['axes']['heat']['monthly_demand']={k:0 for k in m['axes']['heat']['monthly_demand']}
        new=assessment_identity(f,m,POLICY_VERSION)
        f['fusion_evidence']=json.loads(json.dumps(f['fusion_evidence']).replace(old,new))
        r=f['fusion_evidence']['routes'][0];k='climate:heat'
        r['goals'].remove(k);r['actions']=[a for a in r['actions'] if a['target_id']!=k]
        e=r['goal_results'].pop(k);e.update(initial_demand=0,remaining=0,relief_feasible=0,projected_remaining=0,status='satisfied',application_ids=['fire_application'])
        e.pop('dose_plan');r['monitor_results']={k:e}
        r['evidence_registry'][e['evidence_refs'][0]]=dict(deepcopy(e),route_id=r['route_id'],target_id=k)
        r['resource_usage'][0]['target_ids'].remove(k)
        r['evidence_registry']['allocation']['allocation']=deepcopy(r['resource_usage'][0])
        bind_intervention_for_test(r)
        return f,m

    def test_monitor_links_one_real_application_without_new_action(self):
        f,m=self.monitored();x=arbitrate(f,m)
        self.assertTrue(x['action_release_ready'],x['missing_evidence'])
        self.assertEqual(len(x['positions']),3)
        row=x['policy_evaluation']['route_evaluation'][0]
        self.assertEqual(len(row['resource_allocations']),1);self.assertEqual(row['resource_allocations'][0]['amount'],1)
        monitor=next(e for e in row['goal_results'] if e['target_id']=='climate:heat')
        self.assertTrue(monitor['is_monitor']);self.assertIsNone(monitor['dose_plan'])
        r=f['fusion_evidence']['routes'][0];e=r['monitor_results']['climate:heat'];e['application_ids']=['missing']
        r['evidence_registry'][e['evidence_refs'][0]]=dict(deepcopy(e),route_id=r['route_id'],target_id='climate:heat')
        bind_intervention_for_test(r)
        self.assertFalse(arbitrate(f,m)['action_release_ready'])

    def test_realized_protection_rejects_new_dose_and_output_omits_it(self):
        f,m=v26.AuditV26().protected_route();x=arbitrate(f,m)
        self.assertTrue(x['action_release_ready'])
        self.assertTrue(all(p['dose_plan'] is None and p['dose'] is None and p['projected_dose'] is None for p in x['positions']))
        r=f['fusion_evidence']['routes'][0]
        for key,e in r['goal_results'].items():
            e['dose_plan']=dict(amount=999,max_amount=1,unit='unchecked',baseline_ref='wrong')
            r['evidence_registry'][e['evidence_refs'][0]]=dict(deepcopy(e),route_id=r['route_id'],target_id=key)
        x=arbitrate(f,m);self.assertFalse(x['action_release_ready'])
        self.assertTrue(any('unexpected_dose_plan' in error for error in x['missing_evidence']))

if __name__=='__main__':unittest.main()
