import unittest
from bazi_core.engine import analyze
class SymmetricRoots(unittest.TestCase):
 def test_example_and_legacy(self):
  c=dict(gans=list('壬戊庚甲'),zhis=list('申申申申'))
  a=analyze(c,config={"seasonal_strength":False});b=analyze(c,config={'symmetric_root_discount':False,'seasonal_strength':False})
  self.assertEqual(a['wangshuai']['K'],180)
  self.assertEqual(b['wangshuai']['K'],228)
  self.assertEqual(a['wangshuai']['F'],b['wangshuai']['F'])
  self.assertEqual(a['tag'],'身旺')
 def test_factors_for_both_sides(self):
  r=analyze(dict(gans=list('壬戊庚甲'),zhis=list('申申申申')))
  items=r['wangshuai']['debug']['gan_detail']
  for item in items:
   self.assertAlmostEqual(item['root_factor'],{0:.2,1:.6,3:.8,2:1}[item['root_level']])
