import unittest
from bazi_core.engine import analyze
from bazi_core.direction_fusion import fuse_direction,assign_ties,candidate_records
from bazi_core.wangshuai import _balance_tag
class DetailFixes(unittest.TestCase):
 def test_balance_scale_invariance(self):
  for scale in [.1,.3,1.1,100,1e6]:
   for share,label in [(.6,'身旺'),(.5,'中和偏旺'),(.4,'中和偏弱'),(.600001,'身旺'),(.599999,'中和偏旺'),(.500001,'中和偏旺'),(.499999,'中和偏弱'),(.400001,'中和偏弱'),(.399999,'身弱')]:
    f=share*scale;k=(1-share)*scale
    self.assertEqual(_balance_tag(f/k,None,f,k),label)
    self.assertEqual(_balance_tag(f/k,None),label)
 def test_transformed_day_diagnostic_matches_actual(self):
  p='甲子 戊辰 甲申 己丑'.split();c=dict(gans=[x[0] for x in p],zhis=[x[1] for x in p])
  a=analyze(c);b=analyze(c,config={'include_day_stem':False})
  self.assertAlmostEqual(a['wangshuai']['ratio_share_f_exact'],b['wangshuai']['seasonal_assessment']['day_stem_diagnostic']['inclusive_share'])
 def test_complete_season_priority_blocks(self):
  r=analyze(dict(gans=list('庚戊己壬'),zhis=list('午寅酉申')))
  w=dict(r['wangshuai'],tag='身弱',month_zhi='寅',ratio_share_f_exact=.3,F=30.,K=70.)
  g={'ge_category':'八格','xiyong_geju':{'xi_shen_list':['丙（辅助）','丁（辅助）']}}
  t={'ok':True,'zhuyong':'丁','yongshen':['丁','丙']};f={'favored':['火','土'],'disliked':[]}
  d=fuse_direction(w,g,t,f,r['arbitration']);self.assertEqual(d['primary_gan'],'丙')
  w['month_zhi']='子';d=fuse_direction(w,g,t,f,r['arbitration']);self.assertEqual(d['primary_gan'],'丁')
 def test_latent_is_not_current_consensus(self):
  r=analyze(dict(gans=list('庚戊己壬'),zhis=list('午寅酉申')))
  recs,_=candidate_records({'latent_hidden_yong_shen':['丙（潜在）']})
  self.assertFalse(recs[0]['current_support']);self.assertEqual(recs[0]['condition_status'],'waiting_visibility')
 def test_conflicting_disease_is_annotated(self):
  r=analyze(dict(gans=list('庚甲丁丙'),zhis=list('戌申巳午')))
  for row in r['final_xiyong']['stem_ranking']:
   if row['gan']=='丙':self.assertTrue(row['structural_conflicts'])
  self.assertTrue(r['final_xiyong']['structural_conflicts'])
 def test_element_cutoff_ties_are_explicit(self):
  rows=[{'ranking_key':[x]} for x in [3,2,1,1]];assign_ties(rows,3)
  self.assertEqual(rows[2]['rank'],rows[3]['rank']);self.assertTrue(rows[2]['cutoff_tie']);self.assertFalse(rows[3]['selected'])
 def test_balanced_raw_preference_is_soft(self):
  r=analyze(dict(gans=list('庚丁庚丙'),zhis=list('申亥午戌')))
  self.assertEqual(r['xiyong_wangshuai']['strength_of_preference'],'soft');self.assertEqual(r['xiyong_wangshuai']['disliked'],[])

 def test_rootless_middle_reduces_weight(self):
  r=analyze(dict(gans=list('丙丁甲壬'),zhis=list('寅酉子申')))
  self.assertEqual(r['direction_fusion']['fuyi_priority'],'reduced')
  self.assertEqual(r['xiyong_wangshuai']['strength_of_preference'],'soft')
 def test_fake_fallback_preferences_match(self):
  from bazi_core.metadata import WUXING_GAN
  r=analyze(dict(gans=list('辛丁甲己'),zhis=list('未酉申巳')));f=r['final_xiyong']
  self.assertTrue(f['fuyi_stem_preferences']['extreme_weak'])
  self.assertTrue(all(WUXING_GAN[x['gan']] in f['favored'] for x in f['fuyi_stem_preferences']['ranked_gans']))
 def test_luck_shishen_candidates(self):
  r=analyze(dict(gans=list('壬戊庚乙'),zhis=list('午申子酉')))
  plans=[p for p in r['luck_plans'] if p.get('remaining',0)>0]
  self.assertTrue(any(set(p['candidate_gans'])==set('甲乙') for p in plans))

 def test_shared_band_scale_endpoints(self):
  from bazi_core.fuyi_policy import reduced_fuyi, balance_band
  for scale in [.1,.7,1.,13.3,1e6]:
   for p,expected in [(.399999,False),(.4,True),(.5,True),(.599999,True),(.6,False),(.600001,False)]:
    w=dict(F=p*scale,K=(1-p)*scale)
    self.assertEqual(reduced_fuyi(w),expected)
    self.assertEqual(reduced_fuyi(w),balance_band(w['F'],w['K']) in ('中和偏弱','中和偏旺'))
 def test_primary_tie_and_cli(self):
  from cli import _pretty as format_result
  r=analyze(dict(gans=list('丙庚辛癸'),zhis=list('午子亥巳')))
  f=r['final_xiyong'];self.assertEqual(f['primary_gans'],['丙','壬']);self.assertIsNone(f['primary_gan'])
  self.assertIn('方向并列首选：丙≈壬',format_result(r))
 def test_cutoff_cli_only_equal_rank(self):
  from cli import _pretty as format_result
  r=analyze(dict(gans=list('辛壬丙乙'),zhis=list('亥辰寅未')))
  self.assertEqual(r['final_xiyong']['cutoff_tied_gans'],['丁'])
  line=next(x for x in format_result(r).splitlines() if '同分未展示字' in x)
  self.assertTrue(line.endswith('丁'))
