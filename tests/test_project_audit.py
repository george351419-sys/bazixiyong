"""全项目审查反例：输入→真实排盘→模块衔接→发布。构造药效不作命理金标准。"""
import json
import subprocess
import sys
import unittest
from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path

from bazi_core.engine import analyze
from bazi_core.paipan import analyze_birth,auto_solar_term_day,run_paipan
from bazi_core.tiaohou import compute_tiaohou,_eval_condition
from bazi_core.arbitration import arbitrate,build_facts,climate,demand_ledger,POLICY_VERSION
from bazi_core.needs import build_needs
from bazi_core.assessment_identity import assessment_identity
from bazi_core.fusion_evidence import unresolved_geju_rows
from bazi_core.input_contracts import normalize_chart
from tests.test_fusion_completion import prepared
from tests.test_arbitration import model
from web.server import do_analyze
from cli import _pretty

ROOT=Path(__file__).resolve().parents[1]


class ProjectAudit(unittest.TestCase):
    def test_malformed_action_target_returns_pending_without_exception(self):
        for invalid in ([],{},None,False):
            f,m=prepared();r=f['fusion_evidence']['routes'][0]
            action=deepcopy(r['actions'][0]);action['target_id']=invalid;r['actions'].append(action)
            a=arbitrate(f,m)
            self.assertFalse(a['action_release_ready'])
            self.assertEqual(a['decision_status'],'pending')

    def test_extra_action_cannot_borrow_other_drugs_effect(self):
        for application in (None,'not_allocated','fire_application'):
            f,m=prepared();r=f['fusion_evidence']['routes'][0];target=r['goals'][0]
            r['actions'].append(dict(gan='甲',target_id=target,method='extra',intended_action='increase',
                                     application_id=application,evidence_refs=['extra']))
            r['evidence_registry']['extra']=dict(route_id=r['route_id'],gan='甲',target_id=target,method='extra')
            a=arbitrate(f,m)
            self.assertFalse(a['action_release_ready'],application)
            self.assertNotIn('木',a.get('favored',[]))

    def test_published_action_retains_exact_plan_and_resource(self):
        f,m=prepared();a=arbitrate(f,m)
        self.assertTrue(a['action_release_ready'])
        for position in a['positions']:
            self.assertEqual(position['dose_plan']['amount'],1)
            self.assertEqual(position['dose_plan']['max_amount'],1)
            self.assertEqual(position['dose_plan']['baseline_ref'],position['baseline_ref'])
            self.assertEqual(position['resource_allocations'][0]['application_id'],position['application_id'])

    def test_actual_zhongqi_boundaries_select_both_sides(self):
        from lunar_python import Solar
        table=Solar.fromYmdHms(2026,6,1,12,0,0).getLunar().getJieQiTable()
        for term,g,z,before,after in [('秋分','乙','酉',['癸'],['丙','癸']),
                                    ('夏至','乙','午',['癸'],['丙','癸']),
                                    ('谷雨','癸','辰',['丙'],['丙','辛','甲'])]:
            dt=datetime.fromisoformat(table[term].toYmdHms())
            for offset,expected in [(-1,before),(0,after),(1,after)]:
                info=auto_solar_term_day((dt+timedelta(seconds=offset)).isoformat(' '))
                c=dict(gans=['甲','丁',g,'丙'],zhis=['子',z,'丑','戌'],solar_term_info=info)
                result=compute_tiaohou(c)
                self.assertEqual(result['yongshen'],expected,(term,offset,result['segment']))
                self.assertEqual(result['segment']['status'],'selected')

    def test_legacy_jie_and_day_use_explicit_approximation(self):
        c=dict(gans=list('甲丁乙丙'),zhis=list('子酉丑戌'),jie_name='白露',solar_term_day=20)
        r=compute_tiaohou(c)
        self.assertEqual(r['yongshen'],['丙','癸'])
        self.assertIn('工程约定',r['segment']['basis'])

    def test_negation_is_not_both_presence_and_absence(self):
        ctx=dict(gans=list('甲丁乙丙'),zhis=list('子酉丑戌'),half_day=15)
        checks,result=_eval_condition('不见戊',ctx)
        self.assertTrue(result)
        self.assertFalse(any(c['kind']=='透干/见干' for c in checks))
        ctx['gans'][3]='戊'
        self.assertFalse(_eval_condition('不见戊',ctx)[1])

    def test_unparsed_qualifier_cannot_trigger_whole_condition(self):
        ctx=dict(gans=list('甲丁乙丙'),zhis=list('申酉丑午'),half_day=15)
        self.assertFalse(_eval_condition('见甲申时，名藤萝系甲',ctx)[1])
        self.assertIsNone(_eval_condition('见甲且身旺',ctx)[1])
        ctx['gans'][3]='甲';ctx['zhis'][3]='申'
        self.assertTrue(_eval_condition('见甲申时，名藤萝系甲',ctx)[1])

    def test_whole_boolean_condition_and_quantity(self):
        ctx=dict(gans=list('甲丁乙丙'),zhis=list('申酉丑午'),half_day=15)
        self.assertTrue(_eval_condition('见甲或见戊',ctx)[1])
        self.assertFalse(_eval_condition('见甲且见戊',ctx)[1])
        self.assertFalse(_eval_condition('四柱多壬，不见戊制为病',ctx)[1])
        ctx['gans']=['壬','壬','丙','庚']
        self.assertTrue(_eval_condition('四柱多壬，不见戊制为病',ctx)[1])

    def test_blade_shortfall_enters_need_registry_without_fake_relief(self):
        c=dict(gans=list('乙壬丙己'),zhis=list('未午寅丑'))
        for ratio in (1,2):
            r=analyze(c,dict(blade_control_ratio=ratio))
            f=build_facts(r['wangshuai'],r['geju'],r['tiaohou'],r['xiyong_wangshuai']);m=model()
            needs,missing=build_needs(climate(f,m),demand_ledger(r['geju']['xiyong_geju']['treatment_status']),
                assessment_identity(f,m,POLICY_VERSION))
            self.assertFalse(missing)
            n=next(n for n in needs.values() if n['need_type']=='geju')
            self.assertAlmostEqual(n['initial_demand'],1.25*ratio-.5)
        for invalid in (0,-1,float('nan'),float('inf'),True):
            with self.assertRaises(ValueError): analyze(c,dict(blade_control_ratio=invalid))

    def structural_bundle(self):
        original,_=prepared()
        gj=dict(xiyong_geju=dict(treatment_status=[dict(name='定性结构',evidence=[])]))
        base=build_facts(original['ws'],gj,original['tiaohou'],original['fuyi'])
        f,m=prepared(base);b=f['fusion_evidence'];aid=b['assessment_snapshot_id']
        key,row=next(iter(unresolved_geju_rows(f).items()))
        need=dict(need_type='geju',scenario_id='original',initial_demand=1,baseline_gap=1,
            baseline_ref=aid+':'+key,required=True,effect_scope='incremental_from_baseline',
            source_ledger_row=row,source_target_id=row['target_id'],source_demand_method=row['demand_method'],
            source_scenario_id=row['scenario_id'],source_bundle_id=row['route_bundle_id'],evidence_refs=['structural'])
        b['needs'][key]=need
        b['evidence_registry']['structural']=dict(target_id=key,facts_snapshot_id=f['snapshot_id'],
            assessment_snapshot_id=aid,need={k:v for k,v in need.items() if k!='evidence_refs'})
        b['coverage']['geju']['need_ids']=[key]
        route=b['routes'][0];route['goals'].append(key)
        effect=deepcopy(route['goal_results']['climate:cold'])
        effect.update(need_type='geju',baseline_ref=need['baseline_ref'],evidence_refs=['structural_effect'])
        effect['dose_plan']['baseline_ref']=need['baseline_ref']
        route['goal_results'][key]=effect
        route['evidence_registry']['structural_effect']=dict(effect,route_id=route['route_id'],target_id=key)
        action=deepcopy(route['actions'][0]);action.update(target_id=key,evidence_refs=['structural_action'])
        route['actions'].append(action)
        route['evidence_registry']['structural_action']=dict(route_id=route['route_id'],target_id=key,gan='丙',method=action['method'])
        route['resource_usage'][0]['target_ids'].append(key)
        route['evidence_registry']['allocation']['allocation']=deepcopy(route['resource_usage'][0])
        from tests.test_fusion_completion import bind_intervention_for_test
        bind_intervention_for_test(route)
        return f,m,key

    def test_reviewed_structural_gap_can_complete_real_arbitration(self):
        f,m,key=self.structural_bundle();a=arbitrate(f,m)
        self.assertTrue(a['action_release_ready'],a.get('missing_evidence'))
        self.assertIn(key,a['needs'])

    def test_reviewed_structural_gap_cannot_change_source(self):
        f,m,key=self.structural_bundle();need=f['fusion_evidence']['needs'][key]
        need['source_ledger_row']['target_id']='invented'
        a=arbitrate(f,m)
        self.assertFalse(a['action_release_ready'])
        self.assertTrue(any('fusion_structural_source:' in e for e in a['missing_evidence']))

    def test_independent_structural_assessment_cannot_erase_inconsistent_quantities(self):
        f,m,key=self.structural_bundle()
        gj=deepcopy(f['geju']);gj['xiyong_geju']['treatment_status'][0]['evidence']=[
            dict(target_id='structure:定性结构',initial_demand=1,remaining=3)]
        changed=build_facts(f['ws'],gj,f['tiaohou'],f['fuyi'])
        # 旧审核包必须因事实变化失效，不能拿来抹平新矛盾。
        changed['fusion_evidence']=f['fusion_evidence']
        self.assertFalse(arbitrate(changed,m)['release_ready'])

    def test_from_strong_is_not_automatically_specialized(self):
        r=analyze('壬辰 己酉 癸酉 壬子')
        self.assertEqual(r['tag'],'从强')
        self.assertEqual(r['wangshuai']['cong_info']['support_profile'],'印主导')
        self.assertEqual(r['geju']['main_ge_name'],'从强格')
        self.assertEqual(set(r['final_xiyong']['favored']),{'水','金'})
        self.assertNotIn('木',r['final_xiyong']['favored'])

    def test_fuyi_hint_does_not_contradict_own_dimension(self):
        r=analyze('庚戌 甲申 丁巳 丙午')
        hint=r['geju']['xiyong_geju']['fuyi_hint']
        self.assertNotIn('不可取比劫',hint)
        self.assertIn('格局冲突',hint)

    def test_birth_entry_without_pillow_or_external_skill(self):
        script="""import sys
sys.modules['PIL']=None
from bazi_core.paipan import analyze_birth
r=analyze_birth(y=2026,m=9,d=30,h=12,truesun=False)
assert r['ok'],r
assert r['paipan_meta']['backend']=='project_lunar_python'
assert r['paipan_meta']['八字']=='丙午 丁酉 丁未 丙午'
"""
        result=subprocess.run([sys.executable,'-c',script],cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_text_lunar_and_numeric_lunar_agree(self):
        a=analyze_birth(birth='1990年五月初五辰时',truesun=False)
        b=analyze_birth(y=1990,m=5,d=5,h=8,lunar=True,truesun=False)
        self.assertTrue(a['ok'],a);self.assertTrue(b['ok'],b)
        self.assertEqual(a['paipan_meta']['八字'],b['paipan_meta']['八字'])

    def test_late_zi_uses_library_sect_without_changing_datetime(self):
        for sect in (1,2):
            r=analyze_birth(y=2026,m=11,d=6,h=23,minute=30,truesun=False,sect=sect)
            self.assertTrue(r['ok'],r)
            self.assertEqual(r['paipan_meta']['公历'],'2026-11-06 23:30:00')
            self.assertEqual(r['input']['hour_stem_day_offset'],1 if sect==2 else 0)
        chinese=analyze_birth(birth='2026年11月6日23点30分',truesun=False)
        self.assertTrue(chinese['ok'],chinese)
        self.assertEqual(chinese['paipan_meta']['公历'],'2026-11-06 23:30:00')

    def test_dst_and_longitude_consistent_for_text_and_numeric(self):
        for correction in (False,True):
            a=run_paipan(birth='1990-05-28 08:00',lon=117.2,truesun=correction)
            b=run_paipan(y=1990,m=5,d=28,h=8,lon=117.2,truesun=correction)
            self.assertTrue(a['ok'],a);self.assertTrue(b['ok'],b)
            self.assertEqual(a['八字'],b['八字'])
            self.assertEqual(a['公历'],b['公历'])
            self.assertEqual(a['夏令时回拨'],correction)

    def test_missing_or_ambiguous_time_never_becomes_noon(self):
        for birth in ('1990年五月初五','1990年五月初五子时'):
            self.assertFalse(analyze_birth(birth=birth)['ok'])

    def test_public_input_types_and_calendar_contract(self):
        valid='丙午 丁酉 丁未 丙午'
        for payload in [[],dict(chart='甲丑 乙寅 丙卯 丁辰'),
                        dict(chart=valid,enable_special_ge='false'),dict(chart=valid,truesun='false'),
                        dict(chart=valid,solar_term_day=2.9),dict(chart=valid,solar_term_day=True),
                        dict(chart=valid,solar_term_day=-1),dict(chart=42)]:
            r=do_analyze(payload);self.assertFalse(r['ok'],payload);self.assertEqual(r['stage'],'input')
        self.assertTrue(do_analyze(dict(chart=valid))['ok'])
        r=do_analyze(dict(chart='甲丑 乙寅 丙卯 丁辰',input_kind='rule_case'))
        self.assertTrue(r['ok']);self.assertEqual(r['input_validation']['calendar_consistency'],'inconsistent')

    def test_cli_reports_final_arbitration_and_actual_dose(self):
        r=analyze('壬辰 己酉 癸酉 壬子');text=_pretty(r)
        self.assertIn('当前取用方向',text);self.assertIn(r['final_xiyong']['principle'],text)
        f,m=prepared();a=arbitrate(f,m)
        r['final_xiyong'].update(positions=a['positions'])
        self.assertIn('投用：1 test_model_power',_pretty(r))


if __name__=='__main__': unittest.main()
