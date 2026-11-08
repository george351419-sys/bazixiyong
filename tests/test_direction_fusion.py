import unittest
from copy import deepcopy
from bazi_core.paipan import analyze_birth
from bazi_core.direction_fusion import fuse_direction

class DirectionFusion(unittest.TestCase):
    def setUp(self):
        self.r=analyze_birth(y=1990,m=2,d=13,h=16,truesun=False,config={"include_day_stem":False})
    def test_example_and_condition_not_promoted(self):
        r=self.r;d=r['direction_fusion']
        self.assertEqual(d['primary_gan'],'丙')
        self.assertEqual(d['secondary'],['水','土'])
        self.assertNotIn('癸',d['dimensions']['tiaohou'])
        self.assertEqual(r['geju']['ge_status'],'真破格')
        self.assertEqual(r['arbitration']['decision_status'],'pending')
        self.assertEqual(r['final_xiyong']['decision_status'],'heuristic')
        self.assertFalse(r['final_xiyong']['action_release_ready'])
    def test_season_and_strict_boundaries(self):
        r=self.r;w=deepcopy(r['wangshuai']);w['month_zhi']='子'
        a=r['arbitration'];f=r['xiyong_wangshuai']
        d=fuse_direction(w,r['geju'],r['tiaohou'],f,a)
        self.assertEqual(d['priority'],['tiaohou','geju','fuyi'])
        for tag in ['从弱','从强','假从弱','假从强']:
            w['tag']=tag
            self.assertIsNone(fuse_direction(w,r['geju'],r['tiaohou'],f,a))
        a=deepcopy(a);a['fact_validation']['status']='invalid'
        self.assertIsNone(fuse_direction(r['wangshuai'],r['geju'],r['tiaohou'],f,a))
    def test_order_determinism(self):
        r=self.r;d=r['direction_fusion'];g=deepcopy(r['geju'])
        for k in ['potential_yong_shen','latent_hidden_yong_shen']:
            g['xiyong_geju'][k]=list(reversed(g['xiyong_geju'].get(k,[])))
        other=fuse_direction(r['wangshuai'],g,r['tiaohou'],r['xiyong_wangshuai'],r['arbitration'])
        self.assertEqual(d['primary_gan'],other['primary_gan'])
    def test_no_intersection_season_priority_and_conflict(self):
        r=self.r;w=deepcopy(r['wangshuai'])
        g={'ge_category':'八格','xiyong_geju':{'selected_records':[{'gan':'庚'}]}}
        th={'ok':True,'yongshen':['丙'],'xiyong':{'favored_effective':['丙']}}
        f={'favored':['土'],'disliked':['金','火']}
        d=fuse_direction(w,g,th,f,r['arbitration'])
        self.assertEqual(d['primary_gan'],'庚')
        self.assertEqual(next(x for x in d['candidates'] if x['wuxing']=='金')['compatibility'],'direction_conflict')
        self.assertGreater(next(x for x in d['candidates'] if x['wuxing']=='金')['conflict_score'],0)
        w['month_zhi']='子'
        d=fuse_direction(w,g,th,f,r['arbitration'])
        self.assertEqual(d['primary_gan'],'丙')
    def test_urgent_and_bearing_proxy(self):
        r=self.r;w=deepcopy(r['wangshuai']);w.update(month_zhi='子',ratio_share_f=.15)
        w['climate_energy_raw']={'火':1,'水':60,'木':10,'金':20,'土':9}
        d=fuse_direction(w,r['geju'],r['tiaohou'],r['xiyong_wangshuai'],r['arbitration'])
        self.assertEqual(d['climate_proxy']['severity'],'urgent')
        self.assertFalse(d['domain_validated'])

    def test_two_layers_and_auxiliary(self):
        d=self.r['direction_fusion']
        self.assertEqual(d['favored_gans'],list('丙壬丁己戊'))
        self.assertLess(d['stem_ranking'][2]['rank'],d['stem_ranking'][3]['rank'])
        r=analyze_birth(y=1994,m=2,d=25,h=2,truesun=False,config={"include_day_stem":False})
        d=r['direction_fusion']
        self.assertEqual(d['favored'],['火','金','土'])
        self.assertEqual(d['favored_gans'],list('丙辛庚丁戊壬'))
        self.assertTrue(any('格局辅助' in e for e in d['stem_ranking'][1]['evidence']))
        self.assertLess(d['stem_ranking'][2]['rank'],d['stem_ranking'][3]['rank'])
        self.assertIn('火',d['caution'])
    def test_dimension_vote_not_doubled_and_limits(self):
        d=self.r['direction_fusion']
        fire=next(x for x in d['candidates'] if x['wuxing']=='火')
        self.assertEqual(len(fire['support']),3)
        self.assertLessEqual(len(d['favored_gans']),6)
        self.assertLessEqual(len(d['favored']),3)
