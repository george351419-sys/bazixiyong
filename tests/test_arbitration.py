import unittest
from copy import deepcopy
from bazi_core.arbitration import demand_ledger, evaluate_policies as raw_evaluate_policies, build_facts, climate, POLICY_VERSION
from bazi_core.engine import analyze
from bazi_core import metadata as M


def model():
    return dict(version='test-only',review_status='approved',axes={a:dict(
        monthly_demand={z:1 for z in M.ZHI},effect={w:0 for w in M.WUXING_LIST},
        urgent_threshold=2,acceptable_remaining=0) for a in ('cold','heat','dry','wet')})

def need_registry():
    return {'need:1':dict(need_type='climate',scenario_id='original',initial_demand=1,
        baseline_gap=1,baseline_ref='fixture:original:need:1',
        effect_scope='incremental_from_baseline',required=True,severity='urgent',must_handle_now=True,acceptable_remaining=0,
        allowed_deferral_rules=['POL-06'],evidence_refs=['fixture:climate'])}


def evaluate_policies(*args, **kwargs):
    kwargs.setdefault('needs',need_registry())
    return raw_evaluate_policies(*args,**kwargs)

def route(ident, **values):
    deferred = values.pop('_deferred', False)
    values = dict(dict(validated=True,compatible=True,structure_mode='ordinary',
        adds_climate_drug=False,bearing_safe=True,prioritizes_fuyi=False,
        treats_climate=False,alternative=False,preserves_rescue=True), **values)
    registry = {'action':dict(route_id=ident,target_id='need:1',gan='丙',method='protect')}
    checks = {}
    for field,value in values.items():
        registry[field]=dict(route_id=ident,field=field,value=value)
        checks[field]=dict(value=value,evidence_refs=[field])
    relief = 1 if values['treats_climate'] else 0
    item = dict(initial_demand=1,baseline_ref='fixture:original:need:1',effect_scope='incremental_from_baseline',
        relief_realized=relief,remaining=1-relief,
        status='deferred' if deferred else 'treated' if relief else 'unaddressed',
        need_type='climate',scenario_id='original',
        execution_status='not_executed' if deferred else 'realized',
        condition_expr={'op':'eq','path':'bearing.safe','value':True} if deferred else None,
        reason_rule='POL-06' if deferred else None,evidence_refs=['effect'])
    registry['effect']=dict(item,route_id=ident,target_id='need:1')
    return dict(route_id=ident,goals=['need:1'],actions=[dict(gan='丙',target_id='need:1',
        method='protect',evidence_refs=['action'])],checks=checks,evidence_registry=registry,
        goal_results={'need:1':item})

class ArbitrationTests(unittest.TestCase):
    def test_dedup_keeps_method_and_bundle(self):
        rows=[dict(name='病',evidence=[dict(target_id='x',demand_method=m,initial_demand=n,remaining=n)]) for m,n in [('生扶',1),('直接处理',2.5),('生扶',0.5)]]
        result=demand_ledger(rows)
        self.assertEqual(sorted(r['initial_demand'] for r in result),[1,2.5])
        rows[2]['evidence'][0]['route_bundle_id']='alternative'
        self.assertEqual(len(demand_ledger(rows)),3)
    def test_structural_not_silently_lost(self):
        rows=[dict(name='阳刃无制',evidence=[dict(target_id='structure:blade',remaining=1)])]
        self.assertEqual(demand_ledger(rows)[0]['coverage'],'unsupported')
    def test_policies(self):
        for kwargs,expected in [({'alternative':True},'POL-01'),({'conflict_geju':True,'ge_status':'成格','rescue_broken':False},'POL-02'),({'conflict_geju':True,'rescue_broken':True},'POL-03'),({'severity':'mild','conflict_geju':True,'ge_status':'成格'},'POL-04'),({'severity':'mild','conflict_geju':True,'ge_status':'真破格','repair_feasible':False},'POL-05'),({'conflict_fuyi':True,'bear':'can'},'POL-06'),({'fake':True},'POL-07')]:
            args=dict(severity='urgent',conflict_geju=False,conflict_fuyi=False);args.update(kwargs)
            self.assertIn(expected,[x['rule_id'] for x in evaluate_policies(**args)['hits']])
    def test_double_conflict_cannot_bear(self):
        result=evaluate_policies('urgent',conflict_geju=True,rescue_broken=False,
            ge_status='成格',conflict_fuyi=True,bear='cannot', routes=[
                route('climate',bearing_safe=False,treats_climate=True),
                route('ordinary',prioritizes_fuyi=True,_deferred=True)])
        self.assertEqual(result['reason_code'],'selected')
        self.assertEqual(result['choice'],'ordinary')
        self.assertEqual(result['decision_status'],'conditional')
        self.assertEqual(len(result['hits']),2)
    def test_unknown_never_defaults(self):
        self.assertEqual(evaluate_policies('unknown')['decision_status'],'pending')
        self.assertEqual(evaluate_policies('urgent',conflict_geju=True,
            conflict_fuyi=False)['reason_code'],'evidence_insufficient')
    def test_alternative_preserves_rescue(self):
        before=route('original',treats_climate=True,preserves_rescue=False)
        after=route('replacement',treats_climate=True,alternative=True,preserves_rescue=True)
        comparison={'geju':dict(before=2,after=0),'self':dict(before=0,after=0),'other_routes':dict(before=0,after=0)}
        after['replacement']=dict(replaces_route_id='original',cost_comparison=comparison,
                                  evidence_refs=['replacement-proof'])
        after['evidence_registry']['replacement-proof']=dict(route_id='replacement',
            replaces_route_id='original',cost_comparison=comparison)
        result=evaluate_policies('urgent',conflict_geju=True,conflict_fuyi=False,
            rescue_broken=True,alternative=True,routes=[before,after])
        self.assertEqual(result['decision_status'],'decided')
        self.assertEqual(result['choice'],'replacement')
    def test_no_route_no_decision(self):
        result=evaluate_policies('none',conflict_geju=True,conflict_fuyi=False)
        self.assertEqual(result['decision_status'],'pending')
        self.assertIn('validated_routes',result['missing_evidence'])
    def test_invalid_policy_inputs(self):
        for args in (dict(severity='garbage'),dict(severity='urgent',bear='yes'),
                     dict(severity='urgent',conflict_fuyi=1)):
            self.assertEqual(evaluate_policies(**args)['decision_status'],'pending')
    def test_ledger_mixed_coverage_order_independent(self):
        rows=[dict(name='a',evidence=[dict(target_id='x',remaining=1)]),
              dict(name='b',evidence=[dict(target_id='x',remaining=1,initial_demand=2,demand_method='structural')])]
        result=demand_ledger(rows)
        self.assertEqual(result,demand_ledger(list(reversed(rows))))
        self.assertEqual(result[0]['initial_demand'],2)
        self.assertFalse(result[0]['coverage_complete'])
    def test_bad_energy_never_becomes_none(self):
        for value in (float('nan'),float('inf'),-1,True):
            energy={w:1 for w in M.WUXING_LIST};energy['火']=value
            self.assertEqual(climate(dict(element_energy=energy,
                tiaohou=dict(ok=True,month_zhi='子')),model())['severity'],'unknown')
    def test_route_unknown_and_duplicates(self):
        args=dict(severity='none',conflict_fuyi=False,conflict_geju=False)
        self.assertEqual(evaluate_policies(**args,routes=[dict(route_id='x')])['decision_status'],'pending')
        self.assertEqual(evaluate_policies(**args,routes=[dict(route_id='x'),dict(route_id='x')])['reason_code'],'invalid_route_input')

    def test_fake_structure_can_treat_climate(self):
        result=evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=True,
            bear='can',fake=True,routes=[route('ordinary-climate',treats_climate=True)])
        self.assertEqual(result['choice'],'ordinary-climate')
    def test_empty_self_declared_route_rejected(self):
        result=evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=False,
            routes=[dict(route_id='empty',validated=True,compatible=True)])
        self.assertEqual(result['decision_status'],'pending')
        self.assertIn('route:empty:goals',result['missing_evidence'])
    def test_dominated_unknown_does_not_block(self):
        weak=route('weak',treats_climate=False)
        del weak['checks']['compatible']
        result=evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=True,bear='can',
            routes=[weak,route('good',treats_climate=True)])
        self.assertEqual(result['choice'],'good')
        self.assertEqual(next(r for r in result['route_evaluation'] if r['route_id']=='weak')['result'],'rejected')
    def test_competitive_unknown_blocks(self):
        candidate=route('maybe',treats_climate=True)
        del candidate['checks']['compatible']
        result=evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=True,bear='can',
            routes=[candidate,route('good',treats_climate=True)])
        self.assertEqual(result['decision_status'],'pending')
        self.assertIn('route:maybe:compatible',result['missing_evidence'])
    def test_ledger_arithmetic(self):
        for e in [dict(initial_demand=1,remaining=2),
                  dict(initial_demand=2,remaining=1,relief_realized=2)]:
            row=demand_ledger([dict(name='病',evidence=[dict(target_id='x',**e)])])[0]
            self.assertFalse(row['coverage_complete'])
            self.assertEqual(row['observations'][0]['reason_code'],'inconsistent_quantity')
        row=demand_ledger([dict(name='病',evidence=[dict(target_id='x',initial_demand=1,
            remaining=2,relief_realized=0,aggravation=1)])])[0]
        self.assertTrue(row['coverage_complete'])
    def test_forged_check_reference(self):
        r=route('x');r['evidence_registry']['compatible']['route_id']='other'
        result=evaluate_policies('none',conflict_geju=False,conflict_fuyi=False,routes=[r])
        self.assertEqual(result['decision_status'],'pending')
    def test_route_selection_order_independent(self):
        args=dict(severity='urgent',conflict_geju=False,conflict_fuyi=True,bear='can')
        routes=[route('good',treats_climate=True),route('weak',treats_climate=False)]
        self.assertEqual(evaluate_policies(**args,routes=routes),
                         evaluate_policies(**args,routes=list(reversed(routes))))

    def test_urgent_untreated_single_candidate(self):
        result=evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=True,bear='can',
            routes=[route('untreated')])
        self.assertEqual(result['decision_status'],'pending')
        self.assertIn('urgent_need_unresolved:need:1',result['route_evaluation'][0]['failed_rules'])
    def test_uncovered_goal(self):
        candidate=route('x',treats_climate=True);candidate['goals'].append('orphan')
        result=evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=False,routes=[candidate])
        self.assertEqual(result['decision_status'],'pending')
    def test_alternative_requires_comparison(self):
        result=evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=False,alternative=True,
            routes=[route('alt',alternative=True,treats_climate=True)])
        self.assertEqual(result['decision_status'],'pending')
    def test_envelope_cannot_be_used_as_dose(self):
        rows=[dict(name='a',evidence=[dict(target_id='x',initial_demand=10,remaining=0,relief_realized=10)]),
              dict(name='b',evidence=[dict(target_id='x',initial_demand=2,remaining=2,relief_realized=0)])]
        row=demand_ledger(rows)[0]
        self.assertEqual(row['aggregation_kind'],'conservative_envelope')
        self.assertIsNone(row['dose'])
        self.assertEqual(len(row['observations']),2)
    def test_goal_effect_evidence_mismatch(self):
        candidate=route('x',treats_climate=True)
        candidate['goal_results']['need:1']['relief_realized']=0
        result=evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=False,routes=[candidate])
        self.assertEqual(result['decision_status'],'pending')

    def test_need_registry_required(self):
        result=raw_evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=False,
            routes=[route('x',treats_climate=True)])
        self.assertEqual(result['decision_status'],'pending')
    def test_route_cannot_shrink_need(self):
        r=route('x',treats_climate=True)
        for obj in (r['goal_results']['need:1'],r['evidence_registry']['effect']):
            obj.update(initial_demand=0.000001,relief_realized=0.000001,remaining=0)
        result=evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=False,routes=[r])
        self.assertEqual(result['decision_status'],'pending')
    def test_required_need_cannot_be_omitted(self):
        needs=need_registry();needs['geju:critical']=dict(need_type='geju',scenario_id='original',
            initial_demand=10,required=True,allowed_deferral_rules=[],evidence_refs=['fixture:geju'])
        result=evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=False,
            needs=needs,routes=[route('x',treats_climate=True)])
        self.assertEqual(result['decision_status'],'pending')
    def test_duplicate_goal_rejected(self):
        r=route('x',treats_climate=True);r['goals'].append('need:1')
        result=evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=False,routes=[r])
        self.assertEqual(result['decision_status'],'pending')
    def test_invalid_condition_and_deferral_policy(self):
        for expression in ({'nonsense':123},{'op':'eq','path':'_secret','value':True}):
            r=route('x',_deferred=True,prioritizes_fuyi=True)
            for obj in (r['goal_results']['need:1'],r['evidence_registry']['effect']):
                obj['condition_expr']=expression
            result=evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=True,
                bear='cannot',routes=[r])
            self.assertEqual(result['decision_status'],'pending')
    def test_condition_three_states(self):
        from bazi_core.conditions import evaluate_condition
        expr={'op':'eq','path':'bearing.safe','value':True}
        self.assertEqual(evaluate_condition(expr,{}),'unknown')
        self.assertEqual(evaluate_condition(expr,{'bearing':{'safe':False}}),'false')
        self.assertEqual(evaluate_condition(expr,{'bearing':{'safe':True}}),'true')
        self.assertEqual(evaluate_condition({'op':'all','args':[expr]},{}),'unknown')
    def test_replacement_cannot_damage_other_need(self):
        from bazi_core.route_effects import assess_effects, verify_replacement
        needs=need_registry();needs['geju:critical']=dict(need_type='geju',scenario_id='original',
            initial_demand=10,required=True,allowed_deferral_rules=[],evidence_refs=['fixture:geju'])
        before=route('before',treats_climate=True);after=route('after',treats_climate=True,alternative=True)
        for candidate,remaining in ((before,0),(after,9)):
            goal='geju:critical';candidate['goals'].append(goal)
            item=dict(initial_demand=10,relief_realized=10-remaining,remaining=remaining,
                status='treated',need_type='geju',scenario_id='original',execution_status='realized',
                condition_expr=None,reason_rule=None,evidence_refs=['geju-proof'])
            candidate['goal_results'][goal]=item
            candidate['evidence_registry']['geju-proof']=dict(item,route_id=candidate['route_id'],target_id=goal)
            candidate['actions'].append(dict(gan='甲',target_id=goal,method='repair',evidence_refs=['repair']))
            candidate['evidence_registry']['repair']=dict(route_id=candidate['route_id'],target_id=goal,gan='甲',method='repair')
        costs={key:dict(before=1,after=0) for key in ('geju','self','other_routes')}
        after['replacement']=dict(replaces_route_id='before',cost_comparison=costs,evidence_refs=['cmp'])
        after['evidence_registry']['cmp']=dict(route_id='after',replaces_route_id='before',cost_comparison=costs)
        candidates={'before':before,'after':after}
        summaries={k:assess_effects(v,needs) for k,v in candidates.items()}
        self.assertFalse(verify_replacement(after,candidates,summaries,needs))

    def test_condition_met_requires_revalidation(self):
        args=dict(severity='urgent',conflict_geju=False,conflict_fuyi=True,bear='cannot',
                  routes=[route('x',_deferred=True,prioritizes_fuyi=True)])
        waiting=evaluate_policies(**args,condition_facts={'bearing':{'safe':False}})
        ready=evaluate_policies(**args,condition_facts={'bearing':{'safe':True}})
        self.assertEqual(waiting['decision_status'],'conditional')
        self.assertEqual(ready['decision_status'],'pending')
        self.assertTrue(any('condition_met_revalidate' in m for m in ready['missing_evidence']))
    def test_pol03_deferral_uses_same_authorization(self):
        candidate=route('x',_deferred=True)
        needs=need_registry();needs['need:1']['allowed_deferral_rules']=['POL-03']
        for obj in (candidate['goal_results']['need:1'],candidate['evidence_registry']['effect']):
            obj['reason_rule']='POL-03'
        result=evaluate_policies('urgent',conflict_geju=True,conflict_fuyi=False,
            rescue_broken=True,needs=needs,routes=[candidate])
        self.assertEqual(result['decision_status'],'conditional')
        unauthorized=evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=False,
            needs=needs,routes=[candidate])
        self.assertEqual(unauthorized['decision_status'],'pending')
    def test_each_urgent_need_must_be_handled(self):
        r=route('x',treats_climate=True);needs=need_registry()
        needs['climate:second']=dict(needs['need:1'])
        r['goals'].append('climate:second')
        other=route('other')['goal_results']['need:1']
        r['goal_results']['climate:second']=other
        r['evidence_registry']['second-effect']=dict(other,route_id='x',target_id='climate:second')
        other['evidence_refs']=['second-effect']
        r['actions'].append(dict(gan='甲',target_id='climate:second',method='observe',evidence_refs=['second-action']))
        r['evidence_registry']['second-action']=dict(route_id='x',target_id='climate:second',gan='甲',method='observe')
        result=evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=False,needs=needs,routes=[r])
        self.assertEqual(result['decision_status'],'pending')
        self.assertTrue(any('urgent_need_unresolved:climate:second' in r['failed_rules'] for r in result['route_evaluation']))
    def test_route_can_record_aggravation(self):
        from bazi_core.route_effects import assess_effects
        r=route('x')
        for obj in (r['goal_results']['need:1'],r['evidence_registry']['effect']):
            obj.update(status='aggravated',aggravation=1,remaining=2)
        goals,missing=assess_effects(r,need_registry())
        self.assertEqual(missing,[])
        self.assertEqual(goals[0]['aggravation'],1)
        self.assertEqual(goals[0]['remaining'],2)
    def test_protection_requires_dependency(self):
        from bazi_core.route_effects import assess_effects
        r=route('x',treats_climate=True)
        for obj in (r['goal_results']['need:1'],r['evidence_registry']['effect']):
            obj['status']='protected'
        self.assertTrue(assess_effects(r,need_registry())[1])
        dependency=dict(remaining_without=1,evidence_refs=['dependency'])
        for obj in (r['goal_results']['need:1'],r['evidence_registry']['effect']):
            obj['protection_dependency']=dependency
        r['evidence_registry']['dependency']=dict(route_id='x',target_id='need:1',remaining_without=1)
        self.assertEqual(assess_effects(r,need_registry())[1],[])
    def test_internal_fake_condition_matches_schema(self):
        from bazi_core.arbitration import arbitrate
        from bazi_core.conditions import valid_condition,evaluate_condition
        ws=dict(climate_energy={w:0 for w in M.WUXING_LIST},cong_info=dict(is_fake_cong=True,is_cong=False))
        facts=build_facts(ws,{}, {}, {})
        expr=arbitrate(facts)['conditional_routes'][0]['condition_expr']
        self.assertTrue(valid_condition(expr))
        self.assertEqual(evaluate_condition(expr,facts),'false')

    def test_inadmissible_candidate_does_not_block(self):
        full=route('full',treats_climate=True);partial=route('partial',treats_climate=True)
        for obj in (partial['goal_results']['need:1'],partial['evidence_registry']['effect']):
            obj.update(relief_realized=.5,remaining=.5)
        args=dict(severity='urgent',conflict_geju=False,conflict_fuyi=True,bear='can')
        self.assertEqual(evaluate_policies(**args,routes=[full])['choice'],'full')
        result=evaluate_policies(**args,routes=[full,partial])
        self.assertEqual(result['choice'],'full')
        self.assertEqual(next(r for r in result['route_evaluation'] if r['route_id']=='partial')['result'],'rejected')
    def test_aggravation_requires_targeted_authorization(self):
        needs=need_registry()
        needs['geju:x']=dict(need_type='geju',scenario_id='original',initial_demand=0,
            baseline_gap=0,baseline_ref='fixture:geju:x',required=True,
            allowed_deferral_rules=[],allowed_tradeoff_rules=['POL-06'],evidence_refs=['baseline'])
        candidate=route('x',treats_climate=True);candidate['goals'].append('geju:x')
        item=dict(initial_demand=0,relief_realized=0,remaining=1,aggravation=1,
            baseline_ref='fixture:geju:x',effect_scope='incremental_from_baseline',status='aggravated',
            need_type='geju',scenario_id='original',execution_status='realized',condition_expr=None,
            reason_rule=None,evidence_refs=['harm-effect'])
        candidate['goal_results']['geju:x']=item
        candidate['evidence_registry']['harm-effect']=dict(item,route_id='x',target_id='geju:x')
        candidate['actions'].append(dict(gan='甲',target_id='geju:x',method='harm',evidence_refs=['harm-action']))
        candidate['evidence_registry']['harm-action']=dict(route_id='x',target_id='geju:x',gan='甲',method='harm')
        args=dict(severity='urgent',conflict_geju=False,conflict_fuyi=True,bear='can',needs=needs,routes=[candidate])
        denied=evaluate_policies(**args)
        self.assertEqual(denied['decision_status'],'pending')
        self.assertIn('unauthorized_aggravation:geju:x',denied['route_evaluation'][0]['failed_rules'])
        auth=dict(target_id='geju:x',rule_id='POL-06',baseline_ref='fixture:geju:x',policy_version=POLICY_VERSION,max_aggravation=1,evidence_refs=['tradeoff'])
        candidate['tradeoff_authorizations']=[auth]
        candidate['evidence_registry']['tradeoff']=dict(route_id='x',target_id='geju:x',rule_id='POL-06',baseline_ref='fixture:geju:x',policy_version=POLICY_VERSION,max_aggravation=1,aggravation=1)
        approved=evaluate_policies(**args)
        self.assertEqual(approved['choice'],'x')
        self.assertEqual(len(approved['route_evaluation'][0]['tradeoff_approvals']),1)
        candidate['tradeoff_authorizations'][0]['max_aggravation']=.5
        self.assertEqual(evaluate_policies(**args)['decision_status'],'pending')
    def test_old_effect_cannot_be_deducted_twice(self):
        candidate=route('x',treats_climate=True)
        candidate['goal_results']['need:1']['effect_scope']='total_original_relief'
        candidate['evidence_registry']['effect']['effect_scope']='total_original_relief'
        self.assertEqual(evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=False,
            routes=[candidate])['decision_status'],'pending')
    def test_baseline_reference_cannot_be_changed(self):
        candidate=route('x',treats_climate=True)
        for obj in (candidate['goal_results']['need:1'],candidate['evidence_registry']['effect']):
            obj['baseline_ref']='some-other-chart'
        self.assertEqual(evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=False,
            routes=[candidate])['decision_status'],'pending')

    def test_assessment_identity_covers_model_content_and_policy(self):
        from bazi_core.assessment_identity import assessment_identity
        from bazi_core.needs import build_needs
        facts=build_facts(dict(climate_energy={w:1 for w in M.WUXING_LIST}),{},dict(ok=True,month_zhi='子'),{})
        a=model();b=deepcopy(a);b['axes']['cold']['urgent_threshold']=.5
        # 同名版本、不同内容也必须失效。
        aid=assessment_identity(facts,a,POLICY_VERSION);bid=assessment_identity(facts,b,POLICY_VERSION)
        self.assertNotEqual(aid,bid)
        self.assertNotEqual(aid,assessment_identity(facts,a,'other-policy'))
        self.assertEqual(aid,assessment_identity(facts,deepcopy(a),POLICY_VERSION))
        na,_=build_needs(climate(facts,a),[],aid);nb,_=build_needs(climate(facts,b),[],bid)
        self.assertNotEqual(na['climate:cold']['baseline_ref'],nb['climate:cold']['baseline_ref'])
    def test_authorization_requires_current_baseline_and_policy(self):
        from bazi_core.route_admissibility import assess_admissibility
        need={'n':dict(allowed_tradeoff_rules=['POL-06'],baseline_ref='NEW')}
        effect=[dict(target_id='n',aggravation=1,remaining=1,status='aggravated',baseline_ref='NEW')]
        auth=dict(target_id='n',rule_id='POL-06',max_aggravation=1,baseline_ref='NEW',
                  policy_version=POLICY_VERSION,evidence_refs=['proof'])
        proof=dict(auth,route_id='x',aggravation=1)
        candidate=dict(route_id='x',tradeoff_authorizations=[auth],evidence_registry={'proof':proof})
        self.assertFalse(assess_admissibility(candidate,effect,need,{'POL-06'},POLICY_VERSION)[0])
        for field,old in [('baseline_ref','OLD'),('policy_version','old-policy')]:
            original=proof[field];proof[field]=old
            self.assertTrue(assess_admissibility(candidate,effect,need,{'POL-06'},POLICY_VERSION)[0])
            proof[field]=original
    def test_treatment_target_explicit_and_reviewed(self):
        from bazi_core.needs import build_needs
        facts=build_facts(dict(climate_energy={w:1 for w in M.WUXING_LIST}),{},dict(ok=True,month_zhi='子'),{})
        m=model();m['axes']['cold']['acceptable_remaining']=.4
        assessed=climate(facts,m)
        needs,_=build_needs(assessed,[], 'test-assessment')
        self.assertEqual(needs['climate:cold']['acceptable_remaining'],.4)
        del m['axes']['cold']['acceptable_remaining']
        self.assertEqual(climate(facts,m)['reason_code'],'climate_model_invalid')
    def test_no_feasible_route_is_not_policy_conflict(self):
        result=evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=True,bear='can',
            routes=[route('untreated')])
        self.assertEqual(result['reason_code'],'no_feasible_route')
        self.assertIn('urgent_need_unresolved:need:1',result['route_failure_summary']['untreated'])

    def test_complete_zero_needs_no_new_advice(self):
        needs=need_registry()
        needs['need:1'].update(initial_demand=0,baseline_gap=0,severity='none',must_handle_now=False,required=False)
        result=evaluate_policies('none',conflict_geju=False,conflict_fuyi=False,needs=needs,
            needs_complete=True,routes=[])
        self.assertEqual(result['decision_status'],'decided')
        self.assertEqual(result['reason_code'],'no_new_advice')
        self.assertIsNone(result['choice'])
        self.assertEqual(result['positions'],[])
        incomplete=evaluate_policies('none',conflict_geju=False,conflict_fuyi=False,needs=needs,routes=[])
        self.assertNotEqual(incomplete['decision_status'],'decided')
    def test_zero_need_monitoring_requires_no_drug(self):
        needs=need_registry();needs['zero']=dict(needs['need:1'],initial_demand=0,baseline_gap=0,
            required=False,severity='none',must_handle_now=False,baseline_ref='fixture:zero')
        r=route('x',treats_climate=True)
        args=dict(severity='urgent',conflict_geju=False,conflict_fuyi=False,needs=needs,routes=[r])
        self.assertEqual(evaluate_policies(**args)['decision_status'],'pending')
        item=dict(initial_demand=0,relief_realized=0,remaining=0,status='satisfied',need_type='climate',
            scenario_id='original',execution_status='realized',condition_expr=None,reason_rule=None,
            baseline_ref='fixture:zero',effect_scope='incremental_from_baseline',evidence_refs=['monitor'])
        r['monitor_results']={'zero':item}
        r['evidence_registry']['monitor']=dict(item,route_id='x',target_id='zero')
        result=evaluate_policies(**args)
        self.assertEqual(result['choice'],'x')
        self.assertEqual(len(r['actions']),1)
        self.assertEqual(len(result['route_evaluation'][0]['goal_results']),2)
    def test_zero_satisfied_goal_does_not_require_action(self):
        needs=need_registry();needs['need:1'].update(initial_demand=0,baseline_gap=0,severity='none',must_handle_now=False,required=False)
        r=route('nothing');r['actions']=[]
        for item in (r['goal_results']['need:1'],r['evidence_registry']['effect']):
            item.update(initial_demand=0,remaining=0,status='satisfied')
        result=evaluate_policies('none',conflict_geju=False,conflict_fuyi=False,needs=needs,routes=[r])
        self.assertEqual(result['decision_status'],'decided')
    def test_actual_entry_generates_original_treatment_candidate(self):
        from bazi_core.route_generation import generate_routes
        from bazi_core.arbitration import arbitrate
        allocation=dict(evidence_id='action:1',drug_id='3:1:甲',target_id='0:1:戊',
            method='克掉',power=1,chain=['0:1:戊','3:1:甲'])
        gj=dict(xiyong_geju=dict(treatment_allocations=[allocation],treatment_status=[]))
        facts=build_facts(dict(climate_energy={w:1 for w in M.WUXING_LIST}),gj,dict(ok=True,month_zhi='子'),{})
        output=arbitrate(facts,model())
        self.assertTrue(output['routes'])
        self.assertEqual(output['routes'][0]['origin'],'original_geju_treatment')
        self.assertFalse(output['release_ready'])
        self.assertIn('bearing_capacity',output['missing_evidence'])
        needs={'geju:a':dict(source_target_id='0:1:戊',source_demand_method='直接处理'),'geju:b':dict(source_target_id='0:1:戊',source_demand_method='直接处理')}
        candidates,_=generate_routes(facts,needs)
        actions=candidates[0]['actions']
        self.assertEqual(len(actions),2)
        self.assertNotEqual(actions[0]['evidence_refs'],actions[1]['evidence_refs'])
        for a in actions:
            self.assertEqual(candidates[0]['evidence_registry'][a['evidence_refs'][0]]['target_id'],a['target_id'])

    def test_source_method_and_order(self):
        from bazi_core.route_generation import generate_routes
        a=dict(evidence_id='a',drug_id='3:1:甲',target_id='x',method='克掉',power=1)
        b=dict(a,evidence_id='b',drug_id='2:1:乙')
        f=dict(geju=dict(xiyong_geju=dict(treatment_allocations=[a,b])))
        needs={'direct':dict(source_target_id='x',source_demand_method='直接处理'),
               'support':dict(source_target_id='x',source_demand_method='生扶')}
        first,_=generate_routes(f,needs)
        self.assertEqual({a['target_id'] for a in first[0]['actions']},{'direct'})
        f['geju']['xiyong_geju']['treatment_allocations']=[b,a]
        second,_=generate_routes(f,needs)
        self.assertEqual(first,second)
        self.assertEqual(first[0]['route_kind'],'maintenance')
        self.assertTrue(all(a['intended_action']=='protect' for a in first[0]['actions']))
    def test_coverage_does_not_claim_complete(self):
        r=analyze(dict(gans=list('甲癸甲丙'),zhis=list('子丑午寅')))['arbitration']
        self.assertEqual(r['assessment_coverage']['fuyi'],'not_implemented')
        self.assertEqual(r['route_generation_coverage']['deficit_repair'],'intent_generated_effects_pending')
        self.assertFalse(r['release_ready'])

    def test_every_source_action_has_mapping_result(self):
        from bazi_core.route_generation import generate_routes
        a=dict(evidence_id='a',drug_id='3:1:甲',target_id='x',method='克掉',power=1)
        b=dict(a,evidence_id='b',target_id='missing')
        facts=dict(geju=dict(xiyong_geju=dict(treatment_allocations=[a,b])))
        needs={'n':dict(source_target_id='x',source_demand_method='直接处理')}
        routes,missing=generate_routes(facts,needs)
        self.assertEqual({m['source_action_id'] for m in routes[0]['source_mappings']},{'a','b'})
        self.assertIn('unmapped_source_action:b',missing)
        self.assertEqual(routes[0]['actions'][0]['recommendation_status'],'unverified_intent')
    def test_upstream_conditional_restriction_preserved(self):
        from bazi_core.route_generation import generate_routes
        a=dict(evidence_id='a',drug_id='3:1:甲',target_id='x',method='克掉',power=1)
        restriction=dict(id='3:1:甲',reason='自身仍为其他病的病神')
        xy=dict(treatment_allocations=[a],conditional_yong_shen=[restriction])
        facts=dict(geju=dict(xiyong_geju=xy));needs={'n':dict(source_target_id='x',source_demand_method='直接处理')}
        routes,missing=generate_routes(facts,needs)
        self.assertEqual(routes[0]['source_restrictions'],[restriction])
        self.assertIn('source_restriction:3:1:甲',missing)
        before=routes[0]['route_id'];restriction['reason']='其他限制'
        self.assertNotEqual(before,generate_routes(facts,needs)[0][0]['route_id'])

    def test_actual_structure_candidate_is_preserved(self):
        result=analyze(dict(gans=list('甲戊丁戊'),zhis=list('子辰亥申')))
        routes=result['arbitration']['routes']
        self.assertTrue(routes)
        self.assertEqual(routes[0]['origin'],'geju_selected_records')
        self.assertIn('甲',[a['gan'] for a in routes[0]['actions']])
        self.assertEqual(result['arbitration']['decision_progress']['candidate_generation'],'generated')
    def test_restriction_false_is_known_rejection(self):
        r=route('x',treats_climate=True);r['source_restrictions']=[dict(id='a',reason='限制')]
        field='source_restriction:a'
        r['checks'][field]=dict(value=False,evidence_refs=['restriction'])
        r['evidence_registry']['restriction']=dict(route_id='x',field=field,value=False)
        result=evaluate_policies('urgent',conflict_geju=False,conflict_fuyi=False,routes=[r])
        self.assertEqual(result['route_evaluation'][0]['result'],'rejected')
        self.assertIn('restriction_still_active:a',result['route_evaluation'][0]['failed_rules'])

    def test_structure_candidate_matches_validator_contract(self):
        output=analyze(dict(gans=list('甲戊丁戊'),zhis=list('子辰亥申')))['arbitration']
        evaluation=output['policy_evaluation']['route_evaluation'][0]
        self.assertNotIn('action_evidence',evaluation['missing_evidence'])
        self.assertTrue(evaluation['structural_results'])
        self.assertTrue(all(g['source_verified'] for g in evaluation['structural_results']))
        self.assertTrue(any(m.startswith('structure_dependency:') for m in evaluation['missing_evidence']))
        self.assertEqual(evaluation['treatment_status'],'unknown')
    def test_external_wuxing_candidate_keeps_precision(self):
        output=analyze(dict(gans=list('丙庚辛癸'),zhis=list('午子亥巳')),config={'include_day_stem':False})['arbitration']
        candidate=output['routes'][0]
        self.assertEqual(candidate['origin'],'geju_external_wuxing')
        self.assertTrue(all(a['gan'] is None and a['precision']=='wuxing' for a in candidate['actions']))
        evaluation=output['policy_evaluation']['route_evaluation'][0]
        self.assertNotIn('action_evidence',evaluation['missing_evidence'])
        self.assertTrue(all(g['source_verified'] for g in evaluation['structural_results']))

    def test_true_cong_final_entry_uses_unified_verdict(self):
        r=analyze(dict(gans=list('丙庚辛癸'),zhis=list('午子亥巳')),config={'include_day_stem':False})
        self.assertEqual(r['arbitration']['mode'],'external')
        self.assertEqual(r['arbitration']['decision_status'],'decided')
        self.assertEqual(r['final_xiyong']['effective_source'],'arbitration_external')
        self.assertEqual(r['final_xiyong']['favored'],['火','水'])
        self.assertTrue(all(p['gan'] is None for p in r['arbitration']['positions']))

    def test_cong_er_avoid_uses_subtype_and_preserves_conditions(self):
        # 构造接口输入，验证分支合同，不作为历法金标准。
        r=analyze(dict(gans=list('癸丁甲乙'),zhis=list('巳巳戌巳')))
        final=r['final_xiyong']
        self.assertEqual(final['favored'],['火','土'])
        self.assertEqual(final['disliked'],['水'])
        self.assertEqual(final['disliked_scope'],'unconditional')
        conditional=final['conditional_disliked'][0]
        self.assertEqual(conditional['wuxing'],'金')
        self.assertEqual(conditional['decision_status'],'not_triggered')
        self.assertTrue(conditional['condition'])
        self.assertNotIn('金',final['disliked'])

    def test_true_cong_rejects_missing_or_inconsistent_root_contract(self):
        from copy import deepcopy
        from bazi_core.external_arbitration import true_cong_verdict
        r=analyze(dict(gans=list('丙庚辛癸'),zhis=list('午子亥巳')),config={'include_day_stem':False})
        facts=build_facts(r['wangshuai'],r['geju'],{}, {})
        self.assertIsNotNone(true_cong_verdict(facts))
        missing=deepcopy(facts)
        del missing['ws']['cong_info']['root_evidence']
        self.assertEqual(true_cong_verdict(missing)['reason_code'],'true_cong_evidence_missing')
        inconsistent=deepcopy(facts)
        inconsistent['ws']['cong_info']['root_evidence'].append(
            dict(branch_index=0,root_type='本气',broken=False))
        self.assertEqual(true_cong_verdict(inconsistent)['reason_code'],'true_cong_evidence_conflict')
        self.assertFalse(r['arbitration']['policy_evaluation']['diagnostic_affects_decision'])
        conditional=deepcopy(facts)
        conditional['geju']['xiyong_geju']['conditional_ji_shen']=[
            dict(wuxing='木',condition='印比有根成势时',triggered=None)]
        verdict=true_cong_verdict(conditional)
        self.assertEqual(verdict['conditional_avoid'][0]['decision_status'],'pending')
        self.assertNotIn('decision_status',conditional['geju']['xiyong_geju']['conditional_ji_shen'][0])
        conditional['geju']['xiyong_geju']['conditional_ji_shen'][0]['triggered']=True
        verdict=true_cong_verdict(conditional)
        self.assertEqual(verdict['conditional_avoid'][0]['decision_status'],'triggered')
        self.assertNotIn('木',verdict['avoid'])


    def test_fake_cong_uses_ordinary_main_direction(self):
        r=analyze(dict(gans=list('乙丁壬乙'),zhis=list('巳亥辰巳')),config={'seasonal_strength':False})
        self.assertEqual(r['tag'],'假从弱')
        self.assertEqual(r['final_xiyong']['effective_source'],'ordinary_structure_fallback')
        self.assertEqual(r['final_xiyong']['favored'],['金','水'])
        self.assertEqual(r['final_xiyong']['conditional_favored'],['木','火','土'])
        self.assertEqual(r['final_xiyong']['decision_status'],'pending')
        self.assertEqual(r['final_xiyong']['favored'],r['arbitration']['dimension_results']['fuyi']['favored'])
        self.assertEqual(r['final_xiyong']['assessment_level'],'provisional_direction')
        self.assertIn('身弱',r['final_xiyong']['principle'])
        self.assertTrue(r['arbitration']['conditional_routes'][0]['requires_reassessment'])

    def test_triggered_avoid_conflict_blocks_external_release(self):
        from bazi_core.arbitration import arbitrate
        r=analyze(dict(gans=list('癸丁甲乙'),zhis=list('巳巳戌巳')))
        facts=build_facts(r['wangshuai'],r['geju'],r['tiaohou'],r['xiyong_wangshuai'])
        facts['geju']['xiyong_geju']['conditional_ji_shen']=[
            dict(wuxing='火',condition='构造已触发冲突',triggered=True)]
        facts=build_facts(facts['ws'],facts['geju'],facts['tiaohou'],facts['fuyi'])
        a=arbitrate(facts)
        self.assertEqual(a['reason_code'],'triggered_avoid_conflict')
        self.assertEqual(a['decision_status'],'pending')
        self.assertFalse(a['release_ready'])
        self.assertEqual(a['favored'],[])
        self.assertIn('resolve_triggered_avoid:火',a['missing_evidence'])

    def test_identity_tracks_mutated_facts_and_conditional_completion(self):
        from bazi_core.assessment_identity import assessment_identity
        from bazi_core.external_arbitration import true_cong_verdict
        r=analyze(dict(gans=list('癸丁甲乙'),zhis=list('巳巳戌巳')))
        f=build_facts(r['wangshuai'],r['geju'],r['tiaohou'],r['xiyong_wangshuai'])
        before=assessment_identity(f,None,'test')
        f['geju']['xiyong_geju']['conditional_ji_shen']=[dict(wuxing='金',condition='条件待核',triggered=None)]
        self.assertIsNone(assessment_identity(f,None,'test'))
        f=build_facts(f['ws'],f['geju'],f['tiaohou'],f['fuyi'])
        self.assertNotEqual(before,assessment_identity(f,None,'test'))
        v=true_cong_verdict(f)
        self.assertEqual(v['decision_status'],'decided')
        self.assertEqual(v['conditional_review_status'],'pending')
        self.assertFalse(v['release_ready'])

    def test_release_contract_and_missing_root_classification(self):
        from bazi_core.arbitration import arbitrate
        from bazi_core.assessment_identity import assessment_identity
        r=analyze(dict(gans=list('癸丁甲乙'),zhis=list('巳巳戌巳')))
        f=build_facts(r['wangshuai'],r['geju'],r['tiaohou'],r['xiyong_wangshuai'])
        original=assessment_identity(f,None,'test')
        f['candidate_routes']=[]
        self.assertEqual(original,assessment_identity(f,None,'test'))
        del f['ws']['cong_info']['root_evidence']
        self.assertEqual(arbitrate(f)['reason_code'],'fact_snapshot_stale_or_invalid')
        f=build_facts(f['ws'],f['geju'],f['tiaohou'],f['fuyi'])
        a=arbitrate(f)
        self.assertEqual(a['decision_progress']['special_structure'],'evidence_insufficient')
        self.assertEqual(a['conditional_review_status'],'not_assessed')
        self.assertFalse(a['release_ready'])
        r=analyze(dict(gans=list('癸丁甲乙'),zhis=list('巳巳戌巳')))
        f=build_facts(r['wangshuai'],r['geju'],r['tiaohou'],r['xiyong_wangshuai'])
        a=arbitrate(f,dict(nonserializable=object()))
        self.assertEqual(a['reason_code'],'assessment_identity_invalid')
        self.assertEqual(a['decision_status'],'pending')
        self.assertFalse(a['release_ready'])
        self.assertEqual(a['favored'],[])

    def test_fact_consistency_and_invalid_external_selection(self):
        from bazi_core.arbitration import arbitrate
        r=analyze(dict(gans=list('癸丁甲乙'),zhis=list('巳巳戌巳')))
        f=build_facts(r['wangshuai'],r['geju'],r['tiaohou'],r['xiyong_wangshuai'])
        f['element_energy']={w:0 for w in f['element_energy']}
        a=arbitrate(f)
        self.assertEqual(a['reason_code'],'energy_source_mismatch')
        self.assertFalse(a['release_ready'])
        self.assertEqual(a['fact_validation']['status'],'invalid')
        f['geju']['xiyong_geju']['special_ji_wuxing']=None
        f=build_facts(f['ws'],f['geju'],f['tiaohou'],f['fuyi'])
        a=arbitrate(f)
        self.assertEqual(a['mode'],'external')
        self.assertEqual(a['reason_code'],'true_cong_invalid_selection')
        self.assertFalse(a['release_ready'])
        self.assertFalse(r['final_xiyong']['actionable'])

    def test_energy_mapping_and_no_mutation(self):
        ws=dict(day_wuxing='木',climate_energy=dict(木=1,水=2,火=3,土=4,金=5))
        f=build_facts(ws,{}, {}, {})
        self.assertEqual(f['element_energy'],ws['climate_energy'])
        f['element_energy']['木']=9
        self.assertEqual(ws['climate_energy']['木'],1)
    def test_model_validation(self):
        f=dict(element_energy={w:1 for w in M.WUXING_LIST},tiaohou=dict(ok=True,month_zhi='子'))
        self.assertEqual(climate(f,model())['severity'],'mild')
        for mutate in (lambda m:m.update(review_status='draft'),
                       lambda m:m['axes']['cold'].update(urgent_threshold=0),
                       lambda m:m['axes']['cold']['effect'].update(火=float('nan'))):
            m=model();mutate(m)
            self.assertEqual(climate(f,m)['severity'],'unknown')
        self.assertEqual(climate(dict(f,tiaohou=dict(ok=False)),model())['severity'],'unknown')
    def test_engine_end_to_end(self):
        result=analyze(dict(gans=list('甲癸甲丙'),zhis=list('子丑午寅')))
        ws=result['wangshuai']
        self.assertAlmostEqual(sum(ws['climate_energy'].values()),sum(r['power'] for r in ws['energy_records']),places=4)
        self.assertTrue(any(r['id']=='stem:2' for r in ws['energy_records']))
        self.assertEqual(result['arbitration']['mode'],'incomplete')
        self.assertFalse(result['arbitration']['release_ready'])
        self.assertEqual(result['final_xiyong']['effective_source'],'direction_fusion_heuristic')
        self.assertEqual(result,analyze(dict(gans=list('甲癸甲丙'),zhis=list('子丑午寅'))))

if __name__=='__main__': unittest.main()
