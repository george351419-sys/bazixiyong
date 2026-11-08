import unittest
from bazi_core.wangshuai import _cong_ranges
from bazi_core.engine import analyze
from bazi_core.fuyi_order import fuyi_order
class CongRangeReview(unittest.TestCase):
 def test_inclusive_boundaries(self):
  for f,k,expected in [(85,15,(True,False)),(15,85,(False,True)),(84.999,15.001,(False,False)),(15.001,84.999,(False,False)),(0,0,(False,False))]:
   self.assertEqual(_cong_ranges(f,k),expected)
  self.assertEqual(_cong_ranges(90,10,.9),(True,False))
 def test_contains_day_and_does_not_certify_cong(self):
  r=analyze(dict(gans=list('壬戊庚甲'),zhis=list('申申申申')));w=r['wangshuai']
  self.assertEqual(w['cong_range']['weak_max'],.15)
  self.assertEqual(w['cong_range']['strong_min'],.85)
  self.assertFalse(w['cong_range']['enters_strong'])
  self.assertIn('含日干',w['cong_range']['uses'])
  self.assertEqual(w['tag'],'身旺')
 def test_extreme_uses_unrounded_share(self):
  w=dict(day_gan='丙',tag='身弱',ratio_share_f=.2,ratio_share_f_exact=.2004,root_state={'effective_count':1})
  self.assertFalse(fuyi_order(w,['木','火'])['extreme_weak'])
