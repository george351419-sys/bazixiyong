import unittest
from bazi_core.fuyi_order import fuyi_order
from bazi_core.paipan import analyze_birth
from bazi_core.luck_plans import build_luck_plans

class FuyiLuckPlans(unittest.TestCase):
    def test_priorities_and_boundary(self):
        w=dict(tag='身弱',day_gan='丙',root_state={'effective_count':1},ratio_share_f=.3)
        def order():return [r['gan'] for r in fuyi_order(w,['木','火'])['ranked_gans']]
        self.assertEqual(order(),list('乙甲丙丁'))
        w['ratio_share_f']=.20
        self.assertEqual(order(),list('乙甲丁丙'))
        w['ratio_share_f']=.20001
        self.assertEqual(order(),list('乙甲丙丁'))
        w['root_state']['effective_count']=0
        self.assertFalse(fuyi_order(w,['木','火'])['rooted'])
        w['tag']='从弱'
        self.assertFalse(fuyi_order(w,['木','火'])['extreme_weak'])
    def test_luck_targets_and_not_realized(self):
        r=analyze_birth(y=1992,m=10,d=17,h=22,minute=30,truesun=False)
        self.assertEqual(r['final_xiyong']['favored_gans'],list('壬甲庚乙丙丁'))
        self.assertEqual([x['rank'] for x in r['final_xiyong']['stem_ranking']],[1,2,3,4,5,6])
        p=next(x for x in r['final_xiyong']['luck_plans'] if x['name']=='食藏伤透')
        self.assertEqual(p['target_gans'],['己'])
        self.assertEqual(p['candidate_gans'],['甲'])
        self.assertFalse(p['realized'])
        self.assertFalse(p['current_favored'])
    def test_empty_and_unknown_targets(self):
        self.assertEqual(build_luck_plans({}),[])
        plans=build_luck_plans({'xiyong_geju':{'bing_list':[{'name':'x','treatment_status':'待运方案','yao':['合去']}]}})
        self.assertEqual(plans[0]['candidate_gans'],[])

    def test_jianlu_structure_and_wealth_sequence(self):
        r=analyze_birth(y=1992,m=8,d=12,h=16,truesun=False)
        self.assertEqual(r['geju']['main_ge_name'],'建禄格')
        self.assertEqual(r['final_xiyong']['structure_primary'][0]['gan'],'壬')
        self.assertEqual(r['final_xiyong']['structure_secondary'][0]['gan'],'甲')
        self.assertEqual(r['final_xiyong']['favored_gans'][:3],list('壬甲丁'))
        self.assertEqual(r['wangshuai']['F'],430.8)
        self.assertEqual(r['wangshuai']['K'],201.6)
        self.assertAlmostEqual(r['wangshuai']['ratio_share_f'],.681)
        self.assertFalse(r['geju']['xiyong_geju']['used_original_drug'])
