"""F01—F10 回归反例；构造案例不作为领域金标准。"""
import unittest
from copy import deepcopy
from datetime import datetime
from bazi_core.paipan import run_paipan
from bazi_core.birth_parsing import apply_dst
from bazi_core.input_contracts import normalize_chart
from bazi_core.wangshuai import compute_wangshuai
from bazi_core.geju import compute_geju
from bazi_core.numeric import finite
from bazi_core.arbitration import arbitrate
from tests.test_fusion_completion import prepared,bind_intervention_for_test

class AuditV30(unittest.TestCase):
    chart=dict(gans=list('戊庚甲壬'),zhis=list('子子子子'))

    def test_leap_month(self):
        a=run_paipan(birth='农历2033年闰十一月初一日8点')
        b=run_paipan(y=2033,m=11,d=1,h=8,lunar=True,leap=True)
        self.assertTrue(a['ok'],a);self.assertEqual(a['公历'],b['公历'])

    def test_invalid_tokens(self):
        for birth in ('公历1990年5月151日8点','公历1990年5月15日8点和9点','公历1990年5月15日上午下午12点','公历1990年5月15日08:30Z'):
            with self.subTest(birth=birth): self.assertFalse(run_paipan(birth=birth)['ok'])

    def test_dst_transition(self):
        for dt,expected in ((datetime(1990,4,15,0,30),False),(datetime(1990,4,15,3),True),(datetime(1990,9,16,12),False)):
            self.assertEqual(apply_dst(dt)[1],expected)
        for dt in (datetime(1990,4,15,2,30),datetime(1990,9,16,1,30)):
            with self.assertRaises(ValueError): apply_dst(dt)
        r=run_paipan(y=1990,m=5,d=15,h=8,time_basis='china_civil')
        self.assertTrue(r['夏令时回拨']);self.assertIn('07:00:00',r['公历'])

    def test_pillar_agreement(self):
        c=deepcopy(self.chart);c['day']=dict(gan='乙',zhi='子')
        with self.assertRaises(ValueError):normalize_chart(c)

    def test_ws_reuse_identity(self):
        ws=compute_wangshuai(self.chart);compute_geju(self.chart,ws=ws)
        other=deepcopy(self.chart);other['gans'][0]='己'
        with self.assertRaises(ValueError):compute_geju(other,ws=ws)
        with self.assertRaises(ValueError):compute_geju(self.chart,config=dict(tiangan_base=2),ws=ws)
        ws['he_detail']={}
        with self.assertRaises(ValueError):compute_geju(self.chart,ws=ws)

    def test_limit_cannot_borrow_realized_effect(self):
        f,m=prepared();r=f['fusion_evidence']['routes'][0]
        for a in r['actions']:
            a.update(intended_action='limit',action_id='limit:'+a['target_id'])
            a['counterfactual']=dict(action_id=a['action_id'],gan='丙',method=a['method'],remaining_without_limit=1,remaining_with_limit=0)
        bind_intervention_for_test(r)
        self.assertFalse(arbitrate(f,m)['action_release_ready'])
        for a in r['actions']:a['gan']='辛'
        self.assertFalse(arbitrate(f,m)['action_release_ready'])

    def test_valid_limit_and_drug_substitution(self):
        f,m=prepared();r=f['fusion_evidence']['routes'][0]
        for a in r['actions']:
            k=a['target_id'];e=r['goal_results'][k];ref='limit:'+k
            a.update(intended_action='limit',action_id=ref)
            a['counterfactual']=dict(action_id=ref,gan=a['gan'],method=a['method'],remaining_without_limit=1,
                remaining_with_limit=0,baseline_ref=e['baseline_ref'],evidence_refs=[ref])
            r['evidence_registry'][ref]=dict(route_id=r['route_id'],target_id=k,counterfactual=deepcopy(a['counterfactual']))
        bind_intervention_for_test(r)
        self.assertTrue(arbitrate(f,m)['action_release_ready'])
        for a in r['actions']:
            a['gan']='辛'
            for ref in a['evidence_refs']:r['evidence_registry'][ref]['gan']='辛'
        bind_intervention_for_test(r)
        self.assertFalse(arbitrate(f,m)['action_release_ready'])

    def test_disease_recomputed_after_context_change(self):
        from tests.test_geju_revision import ctx
        from bazi_core.geju_xiyong import build_relation_diseases
        c=ctx(list('戊庚甲壬'),list('子子子子'),'七杀')
        before=build_relation_diseases(c)
        c['occ']={}
        after=build_relation_diseases(c)
        fresh=build_relation_diseases(deepcopy(c))
        self.assertEqual(after,fresh);self.assertNotEqual(before,after)

    def test_policy_hit_is_not_conflict_resolution(self):
        from bazi_core.release_audit import summarize
        a=dict(decision_status='pending',policy_inputs=dict(conflict_fuyi=True,conflict_geju=False),policy_evaluation=dict(hits=[dict(rule_id='POL-06')]))
        row=dict(source='constructed',result=dict(tag='身弱',arbitration=a))
        manifest=dict(case_count=1,dataset_sha256='x',thresholds=dict(pending_rate_max=1,conflict_coverage_min=1))
        result=summarize([row],manifest,'x')
        self.assertEqual(result['conflict_coverage'],1)
        self.assertEqual(result['conflict_decided_count'],0)
        self.assertIn('no_resolved_conflict_action_cases',result['failures'])
        self.assertFalse(result['passed'])

    def test_total_numeric_predicate(self):
        for x in (10**400,-10**400,float('inf'),float('nan'),True,None):self.assertFalse(finite(x))
        self.assertFalse(run_paipan(y=2000,m=1,d=1,h=8,lon=10**400)['ok'])

if __name__=='__main__':unittest.main()
