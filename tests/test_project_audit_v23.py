"""v23复核：发布条件、需求互斥、历法时间基准和汇总门槛。"""
import unittest
from copy import deepcopy
from datetime import datetime

from bazi_core.arbitration import arbitrate
from bazi_core.needs import validate_needs
from bazi_core.paipan import run_paipan
from bazi_core.release_audit import summarize
from tests.test_fusion_completion import prepared


class ProjectAuditV23(unittest.TestCase):
    def test_planned_action_condition_false_unknown_and_invalid_block(self):
        for expr, expected in [
            ({'op':'eq','path':'ws.tag','value':'从强'}, 'condition_false'),
            ({'op':'eq','path':'missing.value','value':1}, 'condition_unknown'),
            ('unparsed', 'condition_invalid'),
        ]:
            f,m=prepared();route=f['fusion_evidence']['routes'][0]
            effect=route['goal_results']['climate:cold']
            effect['condition_expr']=expr
            route['evidence_registry'][effect['evidence_refs'][0]]['condition_expr']=deepcopy(expr)
            result=arbitrate(f,m)
            self.assertFalse(result['action_release_ready'],expr)
            self.assertEqual(result['decision_status'],'pending')
            errors=result['missing_evidence'] if expected!='condition_false' else [e for row in result['policy_evaluation']['route_evaluation'] for e in row['failed_rules']]
            self.assertTrue(any(expected in e for e in errors),errors)

    def test_increase_requires_explicit_safe_bearing_evidence(self):
        f,m=prepared();route=f['fusion_evidence']['routes'][0]
        route['checks']['bearing_safe']['value']=False
        route['evidence_registry']['bearing_safe']['value']=False
        result=arbitrate(f,m)
        self.assertFalse(result['action_release_ready'])
        self.assertEqual(result['decision_status'],'pending')

    def test_choice_group_cannot_merge_independent_dimensions(self):
        needs={}
        for kind in ('fuyi','tongguan'):
            needs[kind]=dict(need_type=kind,scenario_id='original',initial_demand=1,required=True,
                evidence_refs=['proof'],choice_group='arbitrary',source_target_id=kind,
                source_bundle_id='same',source_demand_method=kind)
        self.assertTrue(any(e.startswith('invalid_choice_group:') for e in validate_needs(needs)))
        unbound={key:dict(need,need_type='geju',source_target_id=None,source_bundle_id=None,
            source_demand_method=key) for key,need in needs.items()}
        self.assertTrue(any(e.startswith('invalid_choice_group:') for e in validate_needs(unbound)))

    def test_explicit_solar_marker_wins_chinese_month_day(self):
        r=run_paipan(birth='公历1990年五月十五日8点',truesun=False)
        self.assertTrue(r['ok'],r)
        self.assertEqual(r['历法'],'公历')
        self.assertEqual(r['公历'],'1990-05-15 08:00:00')
        self.assertFalse(run_paipan(birth='公历农历1990年五月十五日8点',truesun=False)['ok'])

    def test_afternoon_modifier_applies_across_time_formats(self):
        cases=[('公历1990年5月15日下午8:30', '20:30:00'),
               ('公历1990年5月15日下午8点半','20:30:00'),
               ('公历1990年5月15日下午八点','20:00:00')]
        for birth,expected in cases:
            r=run_paipan(birth=birth,truesun=False)
            self.assertTrue(r['ok'],(birth,r));self.assertTrue(r['公历'].endswith(expected),r)
        self.assertFalse(run_paipan(birth='公历1990年5月15日下午20:30',truesun=False)['ok'])

    def test_seconds_preserved_at_exact_solar_term_boundary(self):
        from lunar_python import Solar
        term=Solar.fromYmdHms(2026,2,1,12,0,0).getLunar().getJieQiTable()['立春']
        dt=datetime.strptime(term.toYmdHms(),'%Y-%m-%d %H:%M:%S')
        before=run_paipan(y=dt.year,m=dt.month,d=dt.day,h=dt.hour,minute=dt.minute,second=dt.second-1,truesun=False)
        after=run_paipan(y=dt.year,m=dt.month,d=dt.day,h=dt.hour,minute=dt.minute,second=dt.second,truesun=False)
        self.assertTrue(before['ok'] and after['ok'])
        self.assertNotEqual(before['八字'][:2],after['八字'][:2])
        text=run_paipan(birth=f'公历{dt.year}年{dt.month}月{dt.day}日{dt.hour}点{dt.minute}分{dt.second}秒',truesun=False)
        self.assertTrue(text['ok'],text)
        self.assertEqual(text['公历'],dt.isoformat(' '))

    def test_true_solar_longitude_does_not_shift_year_month_term_basis(self):
        a=run_paipan(birth='公历2026年2月4日4点12分',lon=120,truesun=True)
        b=run_paipan(birth='公历2026年2月4日4点12分',lon=90,truesun=True)
        self.assertTrue(a['ok'] and b['ok'])
        self.assertEqual(a['八字'][:2],b['八字'][:2])
        self.assertEqual(a['节气参考公历'],b['节气参考公历'])

    def test_release_gate_blocks_zero_release_and_missing_gold(self):
        manifest=dict(case_count=1,dataset_sha256='fixed',
            thresholds=dict(pending_rate_max=.1,conflict_coverage_min=.95))
        arb=dict(decision_status='conditional',release_ready=False,action_release_ready=False,
            conditional_review_status='pending',mode='integrated',policy_inputs=dict(conflict_fuyi=True,conflict_geju=False),
            policy_evaluation=dict(hits=[dict(rule_id='POL-06')]),gap_categories=[])
        result=summarize([dict(result=dict(tag='身弱',arbitration=arb),source='reviewed')],manifest,'fixed')
        self.assertFalse(result['passed'])
        self.assertIn('no_direction_release_cases',result['failures'])
        self.assertIn('no_action_release_cases',result['failures'])
        self.assertIn('independent_validation_missing',result['failures'])
        self.assertEqual(result['pending_count'],1)


if __name__=='__main__': unittest.main()
