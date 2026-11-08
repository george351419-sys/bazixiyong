"""一次性审计清单的反例与真实引擎消费链；合成药效不是命理金标准。"""
from copy import deepcopy
import unittest
from bazi_core.arbitration import arbitrate,build_facts,demand_ledger
from bazi_core.engine import analyze
from bazi_core.needs import validate_needs,build_needs
from bazi_core.route_effects import assess_effects
from bazi_core.release_audit import summarize
from tests.test_fusion_completion import prepared
from tests.test_arbitration import model


class AuditFixes(unittest.TestCase):
    def test_gan_and_wuxing_must_agree(self):
        f,m=prepared()
        for action in f['fusion_evidence']['routes'][0]['actions']: action['wuxing']='水'
        a=arbitrate(f,m)
        self.assertEqual(a['decision_status'],'pending');self.assertFalse(a['action_release_ready'])
        self.assertNotIn('水',a.get('favored',[]))

    def test_invalid_action_cannot_block_valid_competitor(self):
        import json
        f,m=prepared();bad=json.loads(json.dumps(f['fusion_evidence']['routes'][0]).replace('"reviewed"','"bad"'))
        for item in bad['goal_results'].values():
            item.pop('dose_plan',None)
            bad['evidence_registry'][item['evidence_refs'][0]].pop('dose_plan',None)
            item.update(execution_status='realized',relief_realized=1,remaining=0)
            bad['evidence_registry'][item['evidence_refs'][0]].update(item)
        f['fusion_evidence']['routes'].append(bad)
        a=arbitrate(f,m)
        self.assertEqual(a['policy_evaluation']['choice'],'reviewed')
        self.assertTrue(a['action_release_ready'])

    def test_positive_need_cannot_be_optional(self):
        n=dict(need_type='fuyi',scenario_id='original',initial_demand=10,required=False,evidence_refs=['fixture'])
        self.assertIn('positive_need_optional:x',validate_needs({'x':n}))
        _,errors=assess_effects(dict(route_id='empty',goals=[],actions=[],goal_results={}),{'x':n})
        self.assertIn('uncovered_need:x',errors)

    def test_realized_effect_cannot_be_recommended_as_an_increase(self):
        f,m=prepared();r=f['fusion_evidence']['routes'][0]
        for target,item in r['goal_results'].items():
            item.pop('dose_plan',None)
            r['evidence_registry'][item['evidence_refs'][0]].pop('dose_plan',None)
            item.update(execution_status='realized',relief_realized=1,remaining=0)
            r['evidence_registry'][item['evidence_refs'][0]].update(item)
        a=arbitrate(f,m)
        self.assertEqual(a['reason_code'],'no_feasible_route')
        self.assertTrue(any('increase_effect' in err for errs in a['policy_evaluation']['route_failure_summary'].values() for err in errs))
        self.assertFalse(a['action_release_ready'])
        self.assertNotIn('fuyi_need_assessment',a['missing_evidence'])
        self.assertNotIn('geju_selected_route',a['missing_evidence'])

    def test_assembly_failure_does_not_restore_old_missing_items(self):
        f,m=prepared()
        for action in f['fusion_evidence']['routes'][0]['actions']: action.pop('intended_action')
        from tests.test_fusion_completion import bind_intervention_for_test
        bind_intervention_for_test(f['fusion_evidence']['routes'][0])
        a=arbitrate(f,m)
        self.assertEqual(a['reason_code'],'action_assembly_failed')
        self.assertEqual(a['decision_progress']['final_assembly'],'blocked')
        self.assertFalse(a['action_release_ready'])
        self.assertNotIn('fuyi_need_assessment',a['missing_evidence'])
        self.assertNotIn('geju_selected_route',a['missing_evidence'])

    def test_planned_effect_has_no_realized_dose(self):
        f,m=prepared();a=arbitrate(f,m)
        self.assertTrue(a['action_release_ready'])
        e=a['policy_evaluation']['route_evaluation'][0]['goal_results'][0]
        self.assertEqual(e['current_remaining'],1);self.assertEqual(e['relief_realized'],0)
        self.assertEqual(e['relief_feasible'],1);self.assertEqual(e['projected_remaining'],0)
        self.assertIsNone(e['dose']);self.assertEqual(e['projected_dose'],1)

    def test_malformed_bundle_fields_return_errors(self):
        for mutation in ('need_ids','routes','goals','actions','registry','resources'):
            f,m=prepared();b=f['fusion_evidence']
            if mutation=='need_ids': b['coverage']['fuyi']['need_ids']=[{}]
            elif mutation=='routes': b['routes']=[{}]
            elif mutation=='goals': b['routes'][0]['goals']=[{}]
            elif mutation=='actions': b['routes'][0]['actions']=[None]
            elif mutation=='registry': b['routes'][0]['evidence_registry']={'x':[]}
            else: b['routes'][0]['resources']={'x':None}
            a=arbitrate(f,m)
            self.assertEqual(a['decision_status'],'pending',mutation)
            self.assertFalse(a['action_release_ready'],mutation)

    def test_shared_resource_spent_once_and_capacity_enforced(self):
        f,m=prepared();a=arbitrate(f,m)
        alloc=a['policy_evaluation']['route_evaluation'][0]['resource_allocations']
        self.assertEqual(len(alloc),1);self.assertEqual(len(alloc[0]['target_ids']),4)
        f['fusion_evidence']['routes'][0]['resources']['fire_capacity']['capacity']=.5
        a=arbitrate(f,m)
        self.assertFalse(a['action_release_ready'])
        self.assertTrue(any('resource_capacity' in error for error in a['missing_evidence']))

    def test_method_alternatives_require_one_choice(self):
        ledger=demand_ledger([dict(name='x',evidence=[dict(target_id='same',initial_demand=1,remaining=1,demand_method=method,method_relation=dict(kind='alternative',group_id='reviewed_methods',evidence_refs=['reviewed_relation']))]) for method in ('直接处理','生扶')])
        needs,missing=build_needs(dict(severity='none',axes=[]),ledger,'fixture')
        self.assertFalse(missing);group=next(iter(needs.values()))['choice_group']
        self.assertEqual(len({n['choice_group'] for n in needs.values()}),1)
        _,errors=assess_effects(dict(route_id='r',goals=[],actions=[]),needs)
        self.assertIn('method_choice:'+group,errors)

    def test_unrelated_policy_does_not_cover_conflict(self):
        for hits,covered in [(['POL-07'],0),(['POL-06'],1)]:
            a=dict(decision_status='pending',primary_blocker='evidence_gap',mode='incomplete',
                gap_categories=['evidence_gap'],policy_inputs=dict(conflict_fuyi=True,conflict_geju=False),
                policy_evaluation=dict(hits=[dict(rule_id=k) for k in hits],reason_code='evidence_insufficient'))
            report=summarize([dict(result=dict(tag='假从弱',arbitration=a),source='implementation_snapshot')],
                dict(dataset_sha256='x',case_count=1,thresholds=dict(pending_rate_max=.1,conflict_coverage_min=.95)),'x')
            self.assertEqual(report['covered_conflicts'],covered)
            self.assertEqual(report['conflict_decided_count'],0)
            self.assertEqual(report['conflict_evidence_pending_count'],1)

    def test_real_chart_to_final_output_without_mocking(self):
        chart=dict(gans=list('甲癸甲丙'),zhis=list('子丑午寅'))
        baseline=analyze(chart,config={'climate_model':model()})
        f=build_facts(baseline['wangshuai'],baseline['geju'],baseline['tiaohou'],baseline['arbitration']['dimension_results']['fuyi'])
        f,m=prepared(f)
        r=analyze(chart,config=dict(climate_model=m,fusion_evidence=f['fusion_evidence']))
        self.assertEqual(r['arbitration']['mode'],'integrated',r['arbitration'].get('missing_evidence'))
        self.assertEqual(r['final_xiyong']['effective_source'],'arbitration_integrated')
        self.assertTrue(r['final_xiyong']['action_release_ready'])
        self.assertTrue(all(p['execution_status']=='planned' for p in r['final_xiyong']['positions']))

    def test_single_pass_provider_receives_real_context(self):
        chart=dict(gans=list('甲癸甲丙'),zhis=list('子丑午寅'))
        calls=[]
        def provider(context):
            calls.append(context['facts_snapshot_id'])
            f,_=prepared(context['facts'])
            self.assertEqual(f['fusion_evidence']['assessment_snapshot_id'],context['assessment_snapshot_id'])
            return f['fusion_evidence']
        r=analyze(chart,config={'climate_model':model()},fusion_provider=provider)
        self.assertEqual(len(calls),1)
        self.assertEqual(r['arbitration']['facts_snapshot_id'],calls[0])
        self.assertTrue(r['final_xiyong']['action_release_ready'])

    def test_climate_projection_uses_one_model_and_keeps_adverse_effect(self):
        from bazi_core.scenario_evaluation import climate_intervention,climate_removal
        energies={w:0 for w in '木火土金水'};energies['水']=1
        f=build_facts(dict(climate_energy=energies,energy_records=[dict(id='water',wuxing='水',power=1)]),{},dict(ok=True,month_zhi='子'),{})
        m=model()
        for axis,spec in m['axes'].items():
            spec['monthly_demand']={z:1 if axis=='cold' else 0 for z in spec['monthly_demand']}
        m['axes']['cold']['effect']['火']=1;m['axes']['heat']['effect']['火']=-1
        a=climate_intervention(f,m,{'火':1})
        self.assertEqual(a['effects']['climate:cold']['signed_relief'],1)
        self.assertEqual(a['effects']['climate:heat']['signed_relief'],-1)
        self.assertTrue(a['requires_structure_and_bearing_reassessment'])
        self.assertEqual(a['scope'],'climate_energy_only')
        self.assertEqual(f['element_energy']['火'],0)
        self.assertEqual(climate_removal(f,m,['missing'])['status'],'unknown')
        self.assertEqual(climate_removal(f,m,['water'])['status'],'evaluated')

    def test_hua_and_two_elements_use_unified_external_exit(self):
        for gs,zs,kind in [('甲戊甲己','子辰申丑','hua'),('甲甲丙甲','寅寅午寅','two_elements')]:
            r=analyze(dict(gans=list(gs),zhis=list(zs)))
            self.assertEqual(r['arbitration']['structure_kind'],kind)
            self.assertEqual(r['final_xiyong']['effective_source'],'arbitration_external')
            self.assertFalse(r['final_xiyong']['action_release_ready'])
            self.assertEqual(r['arbitration']['policy_evaluation']['basis'],'confirmed_'+kind)

if __name__=='__main__': unittest.main()
