import unittest
from bazi_core.engine import analyze
from bazi_core.wangshuai import _balance_tag
from bazi_core.direction_fusion import fuse_direction
class DayStemBalance(unittest.TestCase):
 def test_thresholds(self):
  for ratio,label in [(1.5,'身旺'),(1.49,'中和偏旺'),(1.,'中和偏旺'),(.99,'中和偏弱'),(2/3,'中和偏弱'),(.66,'身弱')]:
   self.assertEqual(_balance_tag(ratio,None),label)
 def test_day_stem_once_and_accounts(self):
  c=dict(gans=list('壬戊庚甲'),zhis=list('申申申申'))
  a=analyze(c);b=analyze(c,config={'include_day_stem':False});w=a['wangshuai']
  self.assertAlmostEqual(w['F']-b['wangshuai']['F'],78)
  self.assertEqual(w['K'],b['wangshuai']['K'])
  self.assertEqual(len([x for x in w['debug']['gan_detail'] if x['pos']==2]),1)
  self.assertAlmostEqual(sum(w['relation_energy'].values()),w['F']+w['K'])
  self.assertEqual(w['climate_energy_raw'],b['wangshuai']['climate_energy_raw'])
 def test_balanced_fuyi_is_soft_preference(self):
  r=analyze(dict(gans=list('庚戊己壬'),zhis=list('午寅酉申')))
  w=dict(r['wangshuai'],tag='中和偏弱',ratio_share_f=.45)
  d=fuse_direction(w,r['geju'],r['tiaohou'],r['xiyong_wangshuai'],r['arbitration'])
  self.assertEqual(d['priority'][-1],'fuyi')
  self.assertEqual(d['fuyi_support_weight'],.5)
  self.assertEqual(d['avoid'],[])
  self.assertTrue(all(x['fuyi_caution'] for x in d['candidates'] if x['against']))
