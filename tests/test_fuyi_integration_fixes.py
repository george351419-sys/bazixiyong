import unittest
from copy import deepcopy
from bazi_core.engine import analyze
from bazi_core.direction_fusion import fuse_direction,candidate_records
from bazi_core.luck_plans import build_luck_plans

class IntegrationFixes(unittest.TestCase):
 def setUp(self):
  self.r=analyze(dict(gans=list('庚戊己壬'),zhis=list('午寅酉申')))
 def test_winter_policy_not_vetoed_by_fuyi(self):
  w=dict(self.r['wangshuai'],month_zhi='亥',tag='身弱')
  d=fuse_direction(w,{'ge_category':'八格','xiyong_geju':{}},{'ok':True,'zhuyong':'丙','yongshen':['丙']},{'favored':['金','水'],'disliked':['火','土','木']},self.r['arbitration'])
  self.assertEqual(d['primary_gan'],'丙');self.assertIn('火',d['favored']);self.assertIn('火',d['caution'])
 def test_conditional_identity_covers_all_geju_entries(self):
  gx={'conditional_yong_shen':[{'id':'0:1:丙','shen':'丙（有条件）'}], 'selected_records':[{'id':'0:1:丙','gan':'丙'}], 'xi_shen_list':['丙（辅助）'],'structure_primary':[{'gan':'丙'}],'latent_hidden_yong_shen':['丙（藏）']}
  records,blocked=candidate_records(gx)
  self.assertEqual(records,[]);self.assertEqual(blocked,['丙'])
 def test_structure_is_not_realized_drug(self):
  d=self.r['direction_fusion']
  self.assertTrue(all(not x['repair']['realized'] for x in d['candidates']))
 def test_insufficient_drug_is_plan_even_when_present(self):
  p=build_luck_plans({'xiyong_geju':{'bing_list':[dict(name='药力不足',treatment_status='原局有对应药',bing_shen=['戊（病）'],yao=['甲｜克掉'],rescue_evidence=[{'remaining':3}])]}})
  self.assertEqual(p[0]['target_gans'],['戊']);self.assertEqual(p[0]['candidate_gans'],['甲']);self.assertEqual(p[0]['remaining'],3)
 def test_balanced_final_is_caution(self):
  r=analyze(dict(gans=list('庚丁庚丙'),zhis=list('申亥午戌')))
  self.assertIn(r['tag'],['中和偏弱','中和偏旺'])
  self.assertEqual(r['final_xiyong']['disliked'],[])
  self.assertTrue(r['final_xiyong']['caution'])
 def test_full_candidates_and_limits(self):
  d=self.r['direction_fusion']
  self.assertLessEqual(len(d['favored']),3);self.assertLessEqual(len(d['favored_gans']),6)
  self.assertTrue(all('source_records' in r for r in d['stem_ranking']))
 def test_special_output_explains_precision(self):
  r=analyze(dict(gans=list('甲戊甲己'),zhis=list('子辰申丑')))
  self.assertIsNotNone(r['final_xiyong']['stem_ranking_status'])
  self.assertTrue(r['final_xiyong']['stem_ranking_note'])
