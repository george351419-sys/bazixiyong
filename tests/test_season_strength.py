import unittest
from bazi_core.season_strength import factors
from bazi_core.engine import analyze
class SeasonStrength(unittest.TestCase):
 def test_four_shen(self):
  c=dict(gans=list('壬戊庚甲'),zhis=list('申申申申'));r=analyze(c);w=r['wangshuai']
  self.assertEqual(w['F'],430.8);self.assertEqual(w['K'],201.6)
  self.assertAlmostEqual(w['seasonal_assessment']['day_stem_diagnostic']['inclusive_share'],.68121442125)
  self.assertEqual(w['debug']['thresholds']['ratio_fk_bands'],[1.5,1.,2/3])
  old=analyze(c,config={'seasonal_strength':False})
  self.assertEqual(old['wangshuai']['F'],288)
 def test_soil_blend(self):
  f=factors('戌');self.assertAlmostEqual(f['金'],1.225);self.assertAlmostEqual(f['土'],1.30)
  self.assertAlmostEqual(f['火'],.925);self.assertAlmostEqual(f['木'],.775)
  self.assertAlmostEqual(f['水'],.925)
 def test_all_months_finite_positive(self):
  for z in '子丑寅卯辰巳午未申酉戌亥':
   self.assertEqual(len(factors(z)),5)
   self.assertTrue(all(.7<=v<=1.3 for v in factors(z).values()))

 def test_soil_always_highest(self):
  for z in '辰未戌丑':
   f=factors(z)
   self.assertEqual(f['土'],1.30)
   self.assertTrue(all(f['土']>=v for v in f.values()))
