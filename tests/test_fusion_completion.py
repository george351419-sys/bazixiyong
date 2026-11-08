"""融合合同验收：构造用例验证边界与闭环，不充当命理金标准。"""
from copy import deepcopy
import unittest
from bazi_core.arbitration import build_facts,arbitrate,demand_ledger,climate
from bazi_core.assessment_identity import assessment_identity
from bazi_core.needs import build_needs
from bazi_core.dose import assess_dose
from bazi_core.engine import analyze
from bazi_core.fusion_evidence import DIMENSIONS
from bazi_core.release_audit import summarize
from tests.test_arbitration import model,route,evaluate_policies
from bazi_core.arbitration import POLICY_VERSION


def bind_intervention_for_test(route):
    from bazi_core.intervention import intervention_recipe
    route['intervention_assessment']=dict(evidence_refs=['intervention'])
    route['evidence_registry']['intervention']=dict(route_id=route['route_id'],intervention_recipe=intervention_recipe(route))


def prepared(facts=None):
    f=build_facts(dict(tag='身弱',day_wuxing='木',climate_energy={w:1 for w in '木火土金水'},energy_records=[]),
                  {},dict(ok=True,month_zhi='子'),dict(favored=['水','木'],disliked=['火','土','金']))
    if facts is not None: f=deepcopy(facts)
    m=model();aid=assessment_identity(f,m,POLICY_VERSION)
    needs,_=build_needs(climate(f,m),[],aid)
    r=route('reviewed',treats_climate=True)
    r.update(actions=[],goals=list(needs),goal_results={})
    for target,need in needs.items():
        ref='action:'+target;effectref='effect:'+target
        r['actions'].append(dict(gan='丙',target_id=target,method='test_repair',intended_action='increase',evidence_refs=[ref]))
        r['evidence_registry'][ref]=dict(route_id=r['route_id'],gan='丙',target_id=target,method='test_repair')
        effect=dict(initial_demand=1,relief_realized=0,relief_feasible=1,projected_remaining=0,projected_aggravation=0,aggravation=0,remaining=1,status='treated',need_type='climate',
            scenario_id='original',execution_status='planned',effect_scope='incremental_from_baseline',
            baseline_ref=need['baseline_ref'],dose_plan=dict(amount=1,max_amount=1,unit='test_model_power',baseline_ref=need['baseline_ref']),evidence_refs=[effectref])
        r['goal_results'][target]=effect
        r['evidence_registry'][effectref]=dict(effect,route_id=r['route_id'],target_id=target)
    for a in r['actions']: a['application_id']='fire_application'
    resource=dict(capacity=1,unit='test_model_power')
    allocation=dict(application_id='fire_application',resource_id='fire_capacity',amount=1,target_ids=list(needs),evidence_refs=['allocation'])
    r.update(resources={'fire_capacity':resource},resource_usage=[allocation])
    r['evidence_registry']['allocation']=dict(route_id=r['route_id'],resource=resource,allocation=allocation)
    bind_intervention_for_test(r)
    coverage={d:dict(status='complete',need_ids=[],evidence_refs=[d]) for d in DIMENSIONS}
    proof={d:dict(dimension=d,facts_snapshot_id=f['snapshot_id'],assessment_snapshot_id=aid) for d in DIMENSIONS}
    f['fusion_evidence']=dict(review_status='approved',version='synthetic-only',reviewer='contract_fixture',
        facts_snapshot_id=f['snapshot_id'],assessment_snapshot_id=aid,coverage=coverage,
        evidence_registry=proof,needs={},routes=[r],policy_inputs=dict(conflict_fuyi=False,conflict_geju=False))
    f['fusion_evidence']['policy_evidence']={}
    for key,value in f['fusion_evidence']['policy_inputs'].items():
        ref='policy:'+key
        f['fusion_evidence']['policy_evidence'][key]=[ref]
        proof[ref]=dict(field=key,value=value,facts_snapshot_id=f['snapshot_id'],assessment_snapshot_id=aid)
    return f,m


class FusionCompletion(unittest.TestCase):
    def test_missing_conditions_differ_from_explicit_empty(self):
        r=analyze(dict(gans=list('癸丁甲乙'),zhis=list('巳巳戌巳')))
        f=build_facts(r['wangshuai'],r['geju'],r['tiaohou'],r['xiyong_wangshuai'])
        del f['geju']['xiyong_geju']['conditional_ji_shen']
        f=build_facts(f['ws'],f['geju'],f['tiaohou'],f['fuyi'])
        a=arbitrate(f)
        self.assertEqual(a['reason_code'],'true_cong_invalid_selection')
        self.assertFalse(a['release_ready'])
        f['geju']['xiyong_geju']['conditional_ji_shen']=[]
        f=build_facts(f['ws'],f['geju'],f['tiaohou'],f['fuyi'])
        a=arbitrate(f)
        self.assertTrue(a['release_ready'])
        self.assertEqual(a['release_scope'],'direction_conclusion')
        self.assertFalse(a['action_release_ready'])

    def test_gap_does_not_certify_relief_or_dose(self):
        row=demand_ledger([dict(name='fixture',evidence=[dict(target_id='x',initial_demand=10,remaining=3)])])[0]
        self.assertTrue(row['gap_complete']);self.assertFalse(row['relief_complete'])
        self.assertIsNone(row['dose'])
        self.assertEqual(row['dose_assessments'][0]['state'],'evidence_insufficient')
        d=assess_dose(dict(initial_demand=1,relief_realized=0,remaining=1,execution_status='not_executed',relief_feasible=1))
        self.assertEqual(d['state'],'not_executed');self.assertIsNone(d['dose'])
        d=assess_dose(dict(initial_demand=1,relief_realized=1,remaining=0,execution_status='realized'))
        self.assertEqual(d['dose'],1);self.assertEqual(d['action'],'no_increase')
        d=assess_dose(dict(initial_demand=1,relief_realized=0,aggravation=1,remaining=2,execution_status='realized'))
        self.assertLess(d['signed_relief'],0);self.assertEqual(d['state'],'adverse_effect')

    def test_fake_route_has_concrete_obstacles_and_recheck(self):
        a=analyze(dict(gans=list('乙丁壬乙'),zhis=list('巳亥辰巳')),config={'seasonal_strength':False})['arbitration']
        r=a['conditional_routes'][0]
        self.assertTrue(r['prerequisites']);self.assertTrue(r['requires_reassessment']);self.assertFalse(r['actionable'])
        self.assertTrue(all(p['evidence_ref'] and p['resolution'] for p in r['prerequisites']))

    def test_reviewed_ordinary_route_is_assembled(self):
        f,m=prepared();a=arbitrate(f,m)
        self.assertEqual(a['mode'],'integrated',a)
        self.assertEqual(a['decision_status'],'decided')
        self.assertTrue(a['release_ready']);self.assertTrue(a['action_release_ready'])
        self.assertEqual(a['favored'],['火']);self.assertTrue(a['positions'])
        self.assertTrue(all(p['dose'] is None and p['projected_dose']==1 for p in a['positions']))

    def test_bundle_cannot_clear_missing_evidence(self):
        for path in ('binding','coverage','effect','intent','policy_proof'):
            f,m=prepared()
            if path=='binding': f['fusion_evidence']['assessment_snapshot_id']='old'
            elif path=='coverage': del f['fusion_evidence']['coverage']['fuyi']
            elif path=='effect': del f['fusion_evidence']['routes'][0]['goal_results']['climate:cold']
            elif path=='intent': f['fusion_evidence']['routes'][0]['actions'][0]['intended_action']='protect'
            else: f['fusion_evidence']['policy_evidence']={}
            a=arbitrate(f,m)
            self.assertEqual(a['decision_status'],'pending',path)
            self.assertFalse(a['release_ready'],path)

    def test_engine_consumes_integrated_output(self):
        from unittest.mock import patch
        f,m=prepared()
        # 入口与路线验证在上面的用例完成；此处独立验证引擎消费协议。
        with patch('bazi_core.arbitration.arbitrate',return_value=arbitrate(f,m)):
            r=analyze(dict(gans=list('甲癸甲丙'),zhis=list('子丑午寅')))
        self.assertEqual(r['final_xiyong']['effective_source'],'arbitration_integrated')
        self.assertTrue(r['final_xiyong']['actionable'])
        self.assertEqual(r['final_xiyong']['recommendation_scope'],'validated_route')

    def test_six_policy_groups(self):
        cases=[('alternative',dict(severity='urgent',alternative=True),'POL-01'),
            ('urgent_geju',dict(severity='urgent',conflict_geju=True,ge_status='成格',rescue_broken=False),'POL-02'),
            ('rescue_guard',dict(severity='urgent',conflict_geju=True,rescue_broken=True),'POL-03'),
            ('mild_geju',dict(severity='mild',conflict_geju=True,ge_status='成格'),'POL-04'),
            ('urgent_fuyi',dict(severity='urgent',conflict_fuyi=True,bear='can'),'POL-06'),
            ('fake_default',dict(severity='mild',fake=True),'POL-07')]
        for name,extra,expected in cases:
            inputs=dict(conflict_geju=False,conflict_fuyi=False,routes=[route('r',treats_climate=True)])
            inputs.update(extra);p=evaluate_policies(**inputs)
            self.assertIn(expected,[h['rule_id'] for h in p['hits']],name)
            if name!='alternative':
                self.assertEqual(p['choice'],'r',name)
                self.assertEqual(p['decision_status'],'decided',name)
        before=route('original',treats_climate=True,preserves_rescue=False)
        after=route('replacement',treats_climate=True,alternative=True,preserves_rescue=True)
        costs={d:dict(before=1 if d=='geju' else 0,after=0) for d in ('geju','self','other_routes')}
        after['replacement']=dict(replaces_route_id='original',cost_comparison=costs,evidence_refs=['comparison'])
        after['evidence_registry']['comparison']=dict(route_id='replacement',replaces_route_id='original',cost_comparison=costs)
        p=evaluate_policies('urgent',conflict_geju=True,conflict_fuyi=False,rescue_broken=True,alternative=True,routes=[before,after])
        self.assertEqual(p['choice'],'replacement')
        p=evaluate_policies('mild',conflict_geju=True,conflict_fuyi=False,ge_status='真破格',repair_feasible=False,routes=[])
        self.assertIn('POL-05',[h['rule_id'] for h in p['hits']])

    def test_route_identity_is_separate_from_baseline(self):
        f,m=prepared();a=arbitrate(f,m)
        f['fusion_evidence']['version']='synthetic-revised'
        b=arbitrate(f,m)
        self.assertEqual(a['assessment_snapshot_id'],b['assessment_snapshot_id'])
        self.assertNotEqual(a['route_assessment_id'],b['route_assessment_id'])

    def test_release_gate_freezes_denominator_and_rates(self):
        r=analyze(dict(gans=list('乙丁壬乙'),zhis=list('巳亥辰巳')),config={'seasonal_strength':False})
        manifest=dict(dataset_sha256='fixed',case_count=1,thresholds=dict(pending_rate_max=.1,conflict_coverage_min=.95))
        report=summarize([dict(result=r,source='implementation_snapshot')],manifest,'changed')
        self.assertFalse(report['passed']);self.assertIn('frozen_hash_mismatch',report['failures'])
        self.assertEqual(sum(report['primary_gap_rates'].values()),report['pending_rate'])
        self.assertIn('pending_rate_exceeded',report['failures'])

if __name__=='__main__': unittest.main()
