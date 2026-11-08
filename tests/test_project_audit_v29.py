"""快照、数值账及维护补证闭环；合成审核不作为领域金标准。"""
import json
import unittest
from copy import deepcopy
from math import fsum
from bazi_core.engine import analyze
from bazi_core.arbitration import build_facts,arbitrate,POLICY_VERSION
from bazi_core.assessment_identity import assessment_identity,snapshot_error
from bazi_core.scenario_evaluation import climate_intervention,climate_removal,prepare_fusion_context
from tests.test_fusion_completion import prepared,bind_intervention_for_test

class AuditV29(unittest.TestCase):
    def test_invalid_baseline_stops_all_scenario_entries(self):
        for mutate in ('ws','energy','records'):
            f,m=prepared()
            if mutate=='ws':f['ws']['tag']='changed'
            elif mutate=='energy':f['element_energy']=dict(f['element_energy'],火=99)
            else:f['energy_evidence']=[dict(id='extra',wuxing='火',power=1)]
            self.assertIsNotNone(snapshot_error(f))
            for result in (climate_intervention(f,m,{'火':1}),climate_removal(f,m,[]),prepare_fusion_context(f,m)):
                self.assertEqual(result['status'],'unknown');self.assertNotIn('effects',result)

    def test_raw_energy_ledger_supports_full_and_partial_removal(self):
        r=analyze('甲子 癸丑 甲午 丙寅',dict(tiangan_base=25.123456123))
        f=build_facts(r['wangshuai'],r['geju'],r['tiaohou'],r['xiyong_wangshuai']);_,m=prepared()
        self.assertIsNone(snapshot_error(f));records=f['energy_evidence']
        for w in f['element_energy']:
            self.assertEqual(f['element_energy'][w],fsum(x['power'] for x in records if x['wuxing']==w))
        all_removed=climate_removal(f,m,[x['id'] for x in records])
        self.assertEqual(all_removed['status'],'evaluated',all_removed)
        self.assertTrue(all(v==0 for v in all_removed['element_energy_after'].values()))
        partial=climate_removal(f,m,[records[0]['id']]);self.assertEqual(partial['status'],'evaluated')
        bad=climate_intervention(f,m,{'火':-f['element_energy']['火']-1})
        self.assertEqual(bad['reason_code'],'negative_energy_intervention')

    def test_model_content_and_delta_change_scenario_identity(self):
        f,m=prepared();a=climate_intervention(f,m,{'火':1})
        b=climate_intervention(f,m,{'火':2});self.assertNotEqual(a['scenario_id'],b['scenario_id'])
        changed=deepcopy(m);changed['axes']['cold']['effect']['火']=.25
        c=climate_intervention(f,changed,{'火':1})
        self.assertEqual(a['model_version'],c['model_version'])
        self.assertNotEqual(a['assessment_snapshot_id'],c['assessment_snapshot_id'])
        self.assertNotEqual(a['model_sha256'],c['model_sha256'])
        self.assertEqual(a['scenario_id'],climate_intervention(f,m,{'火':1,'水':0})['scenario_id'])

    def sync_review(self,bundle,key):
        e=bundle['maintenance_assessments'][key]
        bundle['evidence_registry']['maintenance_review']=dict(target_id=key,
            facts_snapshot_id=bundle['facts_snapshot_id'],assessment_snapshot_id=bundle['assessment_snapshot_id'],
            maintenance_assessment={k:deepcopy(v) for k,v in e.items() if k!='evidence_refs'})

    def reviewed(self,outcome):
        base,_=prepared();source=dict(evidence_id='source:x',drug_id='drug:丙',gan='丙',target_id='x',power=1,method='克掉')
        gj=dict(xiyong_geju=dict(treatment_allocations=[source],treatment_status=[dict(name='已治',status='已治',
            evidence=[dict(target_id='x',initial_demand=1,remaining=0,demand_method='直接处理')])]))
        facts=build_facts(base['ws'],gj,base['tiaohou'],base['fuyi']);f,m=prepared(facts)
        old=f['fusion_evidence']['assessment_snapshot_id']
        for spec in m['axes'].values():spec['monthly_demand']={k:0 for k in spec['monthly_demand']}
        aid=assessment_identity(f,m,POLICY_VERSION)
        f['fusion_evidence']=json.loads(json.dumps(f['fusion_evidence']).replace(old,aid));b=f['fusion_evidence']
        context=prepare_fusion_context(f,m);key,need=next(iter(context['unresolved_maintenance_targets'].items()))
        row=next(r for r in context['demand_ledger'] if r['target_id']=='x')
        review=dict(original_need=deepcopy(need),source_ledger_row=deepcopy(row),baseline_ref=need['baseline_ref'],outcome=outcome,
            withdrawal=dict(scope='original_target',method='reviewed_withdrawal',remaining_with=0,remaining_without=1 if outcome=='protect_required' else 0),
            evidence_refs=['maintenance_review'])
        b['maintenance_assessments']={key:review};self.sync_review(b,key);b['coverage']['geju']['need_ids']=[key]
        if outcome=='no_dependency':b['routes']=[]
        else:
            r=b['routes'][0];r.update(actions=[],resource_usage=[],resources={})
            for k,e in r['goal_results'].items():
                e.update(initial_demand=0,remaining=0,relief_realized=0,execution_status='realized',status='satisfied');e.pop('dose_plan',None)
                r['evidence_registry'][e['evidence_refs'][0]]=dict(deepcopy(e),route_id=r['route_id'],target_id=k)
            r['goals'].append(key)
            action=dict(gan='丙',target_id=key,method='maintain',intended_action='protect',action_id='maintain:x',source_action_id='source:x',protection_ref='protect',evidence_refs=['act'])
            r['actions']=[action];r['evidence_registry']['act']=dict(route_id=r['route_id'],target_id=key,gan='丙',method='maintain')
            effect=dict(initial_demand=0,remaining=0,relief_realized=0,status='protected',execution_status='realized',need_type='geju',scenario_id='original',effect_scope='incremental_from_baseline',baseline_ref=need['baseline_ref'],protection_dependency=dict(remaining_without=1,evidence_refs=['protect']),evidence_refs=['effect'])
            r['goal_results'][key]=effect;r['evidence_registry']['effect']=dict(deepcopy(effect),route_id=r['route_id'],target_id=key)
            r['evidence_registry']['protect']=dict(route_id=r['route_id'],target_id=key,gan='丙',method='maintain',remaining_without=1,action_id='maintain:x',source_action_id='source:x',baseline_ref=need['baseline_ref'],source_record=source)
        if b['routes']: bind_intervention_for_test(r)
        return f,m,key

    def test_valid_maintenance_evidence_completes_both_outcomes(self):
        for outcome in ('protect_required','no_dependency'):
            f,m,key=self.reviewed(outcome);before=deepcopy(f)
            a=arbitrate(f,m);self.assertEqual(a['decision_status'],'decided',a.get('missing_evidence'))
            self.assertEqual(a['needs'][key]['maintenance_status'],'verified')
            self.assertEqual(a['needs'][key]['initial_demand'],0);self.assertEqual(a['needs'][key]['original_demand'],1)
            self.assertEqual(a['action_release_ready'],outcome=='protect_required')
            self.assertEqual(f,before)

    def test_protection_must_agree_with_reviewed_withdrawal(self):
        f,m,key=self.reviewed('protect_required');r=f['fusion_evidence']['routes'][0]
        e=r['goal_results'][key];e['protection_dependency']['remaining_without']=2
        r['evidence_registry']['effect']=dict(deepcopy(e),route_id=r['route_id'],target_id=key)
        r['evidence_registry']['protect']['remaining_without']=2
        self.assertFalse(arbitrate(f,m)['action_release_ready'])

    def test_invalid_maintenance_review_never_clears_unknown(self):
        for mutation in ('stale','quantity','ledger','contradiction','missing_proof'):
            f,m,key=self.reviewed('no_dependency');b=f['fusion_evidence'];e=b['maintenance_assessments'][key]
            if mutation=='quantity':e['original_need']['initial_demand']=99
            elif mutation=='ledger':e['source_ledger_row']['remaining']=99
            elif mutation=='contradiction':e['withdrawal']['remaining_without']=1
            self.sync_review(b,key)
            if mutation=='stale':b['evidence_registry']['maintenance_review']['assessment_snapshot_id']='stale'
            elif mutation=='missing_proof':b['evidence_registry'].pop('maintenance_review')
            a=arbitrate(f,m);self.assertFalse(a['release_ready'],mutation)
            self.assertEqual(a['needs'][key]['maintenance_status'],'unknown')

if __name__=='__main__':unittest.main()
