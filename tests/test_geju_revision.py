"""2026-11-06 用户审核口径回归；独立于旧版预期。"""
import unittest
from bazi_core import geju as G, geju_xiyong as X, metadata as M


def ctx(gans, zhis, ge='正官'):
    return dict(occ=G._scan_tenshen(gans[2], gans, [M.ZHI_HIDE[z] for z in zhis]),
                gans=gans, day_gan=gans[2], he={'he_groups': []}, ge_ss=ge,
                ge_category='八格', ge_name=ge+'格', ge_status='成格', clean_level='清纯',
                xiang_shen_list=[], ji_shen_list=[], route_label='', route_xiang=[],
                special_ge=None, wangshuai_tag='中和')

class Revision(unittest.TestCase):
    def test_hidden_diseases(self):
        c=ctx(['甲','壬','甲','癸'], ['午','酉','巳','丑'])
        main,light,_=X._detect_bing(c)
        self.assertNotIn('伤官见官', [x['name'] for x in main+light])
        self.assertNotIn('枭印夺食', [x['name'] for x in main+light])
    def test_chong_halves_each_position(self):
        occ=G._scan_tenshen('甲',['丙','壬','甲','戊'],
                              [M.ZHI_HIDE[z] for z in ['寅','申','辰','戌']],
                              ['寅','申','辰','戌'])
        for rs in occ.values():
            for r in rs:
                if not r['tou'] or r['gan'] in ('丙','壬'):
                    self.assertTrue(r['chong'])
                    self.assertEqual(r['weight'], r['base_weight']*.5)
        self.assertTrue(any(r['weight']==.25 for rs in occ.values() for r in rs))

    def test_priority(self):
        self.assertEqual(X.BING_YAO['伤官见官'][0][1], ['正印','偏印'])
        self.assertEqual(X.BING_YAO['比劫夺财'][0][1], ['正官','七杀'])
    def test_fixed_luren(self):
        for day,month,name in [('丙','午','阳刃格'),('庚','申','建禄格'),('乙','寅','月劫格')]:
            r=G.compute_geju(dict(gans=['戊','壬',day,'辛'],zhis=['辰',month,'辰','丑']), {'enable_special_ge':False})
            self.assertEqual(r['main_ge_name'],name)
    def test_yin_mixed(self):
        self.assertTrue(G._tenshen_hunzhuo(['正印','偏印']))
    def test_weights(self):
        c=ctx(['壬','癸','甲','丙'], ['亥','子','辰','申'])
        r=X.compute_xiyong_geju(c)
        self.assertEqual(r['strength_counts']['偏印'], 2.0)
    def test_route_only_visible(self):
        c=ctx(['丙','壬','甲','庚'], ['子','子','子','子'],'七杀')
        routes=G.GE_ROUTE['七杀']
        self.assertTrue(G._routes_conflict(c['occ'],routes,['食神制杀','杀印相生']))
        c=ctx(['丙','庚','甲','壬'], ['子','子','子','子'],'七杀')
        self.assertFalse(G._routes_conflict(c['occ'],routes,['食神制杀','杀印相生']))
    def test_external(self):
        for special in ['从财格','从杀格','从儿格','曲直格（专旺木）','化土格（甲己）','两气成象格（木·火相生）']:
            c=ctx(['丙','戊','甲','丁'], ['寅','午','寅','午'])
            c.update(special_ge=special,ge_category='外格',ge_ss=None)
            self.assertTrue(X.compute_xiyong_geju(c)['yong_shen_list'])
    def test_special_wealth_is_conditional(self):
        for day in M.GAN_LIST:
            c=ctx(['丙','戊',day,'丁'], ['寅','午','寅','午'])
            c.update(special_ge='专旺格', ge_category='外格', ge_ss=None)
            r=X.compute_xiyong_geju(c)
            wealth=M.KE[M.WUXING_GAN[day]]
            self.assertTrue(any(x['wuxing']==wealth for x in r['conditional_ji_shen']))
            self.assertFalse(any(x.startswith(wealth) for x in r['ji_shen_list']))
    def test_two_elements_allow_downstream_drain(self):
        for upstream in M.WUXING_LIST:
            downstream=M.SHENG[upstream]
            drain=M.SHENG[downstream]
            c=ctx(['丙','戊','甲','丁'], ['寅','午','寅','午'])
            c.update(special_ge=f'两气成象格（{upstream}·{downstream}相生）',ge_category='外格',ge_ss=None)
            r=X.compute_xiyong_geju(c)
            self.assertTrue(any(x['wuxing']==drain and x['role']=='泄秀' for x in r['third_element_roles']))
            self.assertFalse(any(x.startswith(drain) for x in r['ji_shen_list']))
            self.assertTrue(r['yong_shen_list'][0].startswith(downstream))
            self.assertTrue(any(x.startswith(M.KE_OF[downstream]) for x in r['ji_shen_list']))

    def test_hidden_bijian_counted(self):
        occ=G._scan_tenshen('甲',['乙','丙','甲','丁'],[M.ZHI_HIDE['寅']]*4)
        self.assertEqual(sum(r['weight'] for r in occ['比肩']),4)
    def test_external_has_no_ordinary_diseases(self):
        c=ctx(['戊','庚','甲','壬'],['寅','申','子','午'])
        c.update(special_ge='从杀格',ge_ss=None,ge_category='外格')
        r=X.compute_xiyong_geju(c)
        self.assertFalse(r['has_bing'])
        self.assertFalse(r['yao_shen_list'])
        self.assertEqual({x[0] for x in r['ji_shen_list']},{'火','水'})
    def test_clean_rules_shared(self):
        from bazi_core.geju_rules import clean_level
        c=ctx(['壬','癸','甲','丙'],['子']*4)
        self.assertEqual(clean_level(c['occ'],c['he']),'浊而无去')
    def test_rescue_by_position(self):
        from bazi_core.geju_rules import rescue_fraction
        he={'he_groups':[dict(type='wuhe',idx=[0,1],members=['丁','壬'])]}
        self.assertEqual(rescue_fraction(dict(tou=True,idx=0),he),1)
        self.assertEqual(rescue_fraction(dict(tou=True,idx=3),he),0)
    def test_two_lines_accept_small_drain(self):
        he=dict(gan_hua=[None]*4,branch_hua=[None]*4)
        self.assertIsNotNone(G._two_line_check(['甲','丙','甲','戊'],['寅','午','寅','午'],he,'木'))
        self.assertIsNone(G._two_line_check(['戊']*4,['辰','午','寅','辰'],he,'土'))
    def test_luren_month_tou_selects_one(self):
        r=G.compute_geju(dict(gans=['丙','戊','甲','庚'],zhis=['午','寅','辰','申']),{'enable_special_ge':False})
        self.assertEqual(len(r['xiang_shen_list']),1)
        self.assertNotIn('比肩',r['xiang_shen_list'][0])
    def test_blade_control_evidence(self):
        r=G.compute_geju(dict(gans=['癸','壬','丙','戊'],zhis=['子','午','午','辰']),{'enable_special_ge':False})
        self.assertIn('制刃校验',r['note'])

    def test_directed_ke(self):
        from bazi_core.geju_rules import ke
        self.assertTrue(ke('正印','伤官'))
        self.assertFalse(ke('伤官','正印'))
        c=ctx(['己','癸','庚','壬'],['巳','午','酉','子'],'正印')
        self.assertTrue(X.compute_xiyong_geju(c)['yong_shen_list'])
    def test_contested_wuhe_one_partner(self):
        from bazi_core.geju_rules import resolve_wuhe
        he={'he_groups':[dict(type='wuhe',idx=[0,1]),dict(type='wuhe',idx=[1,2])]}
        result=resolve_wuhe(he,['甲','己','甲','丁'],{})
        self.assertEqual(len(result['he_groups']),1)
        self.assertEqual(len(result['wuhe_rejected']),1)
    def test_hidden_only_cannot_trigger_excess(self):
        c=ctx(['甲','辛','甲','壬'],['辰','戌','丑','未'])
        names=[b['name'] for b in X.compute_xiyong_geju(c)['bing_list']]
        self.assertNotIn('财多官埋',names)
    def test_pending_is_not_cure(self):
        c=ctx(['丙','丁','甲','乙'],['子','卯','午','未'])
        c.update(ge_ss=None,ge_name='阳刃格',ge_category='禄刃',ge_status='真破格')
        r=X.compute_xiyong_geju(c)
        self.assertIn('阳刃无制',r['unresolved_bing'])
        self.assertFalse(r['yao_in_chart'])
    def test_two_lines_entry_does_not_require_isolation(self):
        r=G.compute_geju(dict(gans=['甲','丙','甲','戊'],zhis=['寅','午','寅','午']))
        self.assertIn('两气成象',r['main_ge_name'])
    def test_route_uses_effective_power(self):
        c=ctx(['丙','壬','甲','庚'],['寅','子','子','申'],'七杀')
        he={'he_groups':[dict(type='wuhe',idx=[0,1],members=['丙','壬'])]}
        # helper has deterministic tie policy and discounts fully unavailable stems
        label=G._pick_route(c['occ'],G.GE_ROUTE['七杀'],['食神制杀','杀印相生'],he)
        self.assertIn(label,('食神制杀','杀印相生'))

    def test_hidden_drug_pending_only(self):
        c=ctx(['丁','辛','甲','乙'],['子','酉','子','子'],'正官')
        r=X.compute_xiyong_geju(c)
        self.assertTrue(any(t['status']=='潜在救应、待透' for t in r['treatment_status']))
        self.assertFalse(r['yao_in_chart'])
        self.assertTrue(any('待透' in x for x in r['candidate_pool']))
    def test_nonexistent_officer_not_protected(self):
        c=ctx(['甲','甲','壬','戊'],['午','午','午','寅'],'正财')
        c.update(route_xiang=['食神','伤官','正官'])
        r=X.compute_xiyong_geju(c)
        self.assertTrue(any('食神' in x for x in r['yong_shen_list']))
    def test_tiny_second_element_rejected(self):
        he=dict(gan_hua=[None]*4,branch_hua=[None]*4)
        self.assertIsNone(G._two_line_check(['甲']*4,['卯','卯','卯','午'],he,'木'))
    def test_virtual_yinyang_equal(self):
        occ=G._scan_tenshen('丙',['丙']*4,[G._virtual_hide('木')])
        self.assertEqual(occ['正印'][0]['weight'],.5)
        self.assertEqual(occ['偏印'][0]['weight'],.5)
    def test_med_capacity_not_reused(self):
        from bazi_core.geju_rules import verify_rescue
        occ={'伤官':[dict(tou=True,idx=0,gan='丁',weight=1),dict(tou=True,idx=2,gan='丁',weight=1)],
             '正印':[dict(tou=True,idx=1,gan='癸',weight=1)]}
        result=verify_rescue(occ,{'he_groups':[]},['伤官'],['正印'])
        self.assertEqual(sum(x['status']=='完全获救' for x in result),1)
    def test_all_candidates_retained(self):
        c=ctx(['癸','壬','甲','丁'],['子','亥','寅','午'],'正官')
        _,inside,_=X._pick_yao(dict(name='伤官见官',bing_ss=['伤官']),c)
        self.assertTrue(any('正印' in s for s in inside))
        self.assertTrue(any('偏印' in s for s in inside))

    def test_wrong_method_rejected(self):
        from bazi_core.geju_rules import verify_rescue
        occ={'伤官':[dict(tou=True,idx=0,gan='丁',weight=1)],'比肩':[dict(tou=True,idx=1,gan='甲',weight=1)]}
        self.assertEqual(verify_rescue(occ,{'he_groups':[]},['伤官'],['比肩'])[0]['status'],'未获救')
    def test_global_capacity_across_diseases(self):
        from bazi_core.geju_treatment import allocate,records
        occ={'伤官':[dict(tou=True,idx=0,gan='丁',weight=1)],'食神':[dict(tou=True,idx=2,gan='丙',weight=1)],'正印':[dict(tou=True,idx=1,gan='癸',weight=1)]}
        he={'he_groups':[]};selected=[r for r in records(occ,he) if r['ss']=='正印']
        statuses,allocations,_=allocate(occ,he,[dict(name='A',bing_ss=['伤官']),dict(name='B',bing_ss=['食神'])],selected,
            {'A':[('克掉',['正印'],'')],'B':[('克掉',['正印'],'')]})
        self.assertEqual(sum(x['status']=='完全获救' for x in statuses),1)
        self.assertEqual(sum(x['power'] for x in allocations),1)
    def test_no_borrowing_unselected_position(self):
        from bazi_core.geju_treatment import allocate,records
        occ={'伤官':[dict(tou=True,idx=0,gan='丁',weight=1)],'正印':[dict(tou=True,idx=1,gan='癸',weight=1),dict(tou=True,idx=3,gan='癸',weight=1)]}
        he={'he_groups':[]};selected=[r for r in records(occ,he) if r['idx']==3]
        statuses,_,_=allocate(occ,he,[dict(name='A',bing_ss=['伤官'])],selected,{'A':[('克掉',['正印'],'')]})
        self.assertNotEqual(statuses[0]['status'],'完全获救')
    def test_pending_fields_separated(self):
        c=ctx(['丁','辛','甲','乙'],['子','酉','子','子'],'正官')
        r=X.compute_xiyong_geju(c)
        self.assertTrue(r['potential_yong_shen'])
        self.assertTrue(all('待透' not in x and '待运' not in x and '·藏' not in x for x in r['yong_shen_list']))
    def test_structural_guard_can_resolve(self):
        from bazi_core.geju_treatment import allocate,records
        occ={'正财':[dict(tou=True,idx=0,gan='己',weight=1)],'正官':[dict(tou=True,idx=1,gan='辛',weight=1)]}
        he={'he_groups':[]};selected=[r for r in records(occ,he) if r['ss']=='正官']
        statuses,allocations,_=allocate(occ,he,[dict(name='财露无官杀',bing_ss=[])],selected,X.BING_YAO)
        self.assertEqual(statuses[0]['status'],'完全获救')
        self.assertEqual(allocations[0]['drug_id'],'1:1:辛')

    def test_disease_order_invariance(self):
        from bazi_core.geju_treatment import allocate,records
        occ={'伤官':[dict(tou=True,idx=0,gan='丁',weight=1)],'食神':[dict(tou=True,idx=2,gan='丙',weight=1)],'正印':[dict(tou=True,idx=1,gan='癸',weight=1),dict(tou=True,idx=3,gan='癸',weight=1)]}
        he={'he_groups':[]};drugs=[r for r in records(occ,he) if r['ss']=='正印']
        diseases=[dict(name='A',bing_ss=['伤官']),dict(name='B',bing_ss=['食神'])]
        rules={x:[('克掉',['正印'],'')] for x in ('A','B')}
        a=allocate(occ,he,diseases,drugs,rules)[0]
        b=allocate(occ,he,diseases[::-1],drugs[::-1],rules)[0]
        self.assertEqual({x['name']:x['status'] for x in a},{x['name']:x['status'] for x in b})
        self.assertTrue(all(x['status']=='完全获救' for x in a))
    def test_structural_cannot_bypass_threshold(self):
        from bazi_core.geju_treatment import allocate,records
        occ={'正印':[dict(tou=True,idx=0,gan='癸',weight=1),dict(tou=False,idx=0,gan='癸',weight=3)],'正财':[dict(tou=True,idx=1,gan='己',weight=1)]}
        he={'he_groups':[]};drugs=[r for r in records(occ,he) if r['ss']=='正财']
        result=allocate(occ,he,[dict(name='印过旺',bing_ss=['正印'])],drugs,X.BING_YAO)[0]
        self.assertNotEqual(result[0]['status'],'完全获救')
    def test_no_disease_route_priority_and_auxiliary(self):
        from bazi_core.geju_treatment import solve
        c=ctx(['戊','庚','甲','壬'],['子']*4)
        c['route_priority']={'偏财':0,'偏印':1}
        result=solve(c,[],{}, {'偏财','偏印'})
        self.assertEqual(len(result['selected']),1)
        self.assertEqual(result['selected'][0]['ss'],'偏财')
        self.assertTrue(result['auxiliary'] or result['alternatives'])
    def test_bridge_has_concrete_endpoint(self):
        from bazi_core.geju_treatment import allocate,records
        occ={'伤官':[dict(tou=True,idx=0,gan='丁',weight=1)],'正财':[dict(tou=True,idx=1,gan='己',weight=1)],'正官':[dict(tou=True,idx=2,gan='辛',weight=1)]}
        he={'he_groups':[]};drugs=[r for r in records(occ,he) if r['ss']=='正财']
        _,actions,_=allocate(occ,he,[dict(name='伤官见官',bing_ss=['伤官'])],drugs,X.BING_YAO)
        self.assertEqual(actions[0]['chain'],['0:1:丁','1:1:己','2:1:辛'])

    def test_auxiliary_is_a_compatible_set(self):
        from bazi_core.geju_treatment import solve
        occ={'比肩':[dict(tou=True,idx=3,gan='甲',weight=2)],'正印':[dict(tou=True,idx=0,gan='癸',weight=1)],'食神':[dict(tou=True,idx=1,gan='丙',weight=1)]}
        result=solve(dict(occ=occ,he={'he_groups':[]},ge_ss=None,route_priority={'比肩':0,'正印':1,'食神':1}),[],{},set(occ))
        self.assertEqual(len(result['selected']),1)
        self.assertEqual(len(result['auxiliary']),1)
        self.assertEqual(len(result['alternatives']),1)
    def test_primary_never_borrows_second_route_score(self):
        from bazi_core.geju_treatment import solve
        occ={'正财':[dict(tou=True,idx=0,gan='己',weight=.5)],'正印':[dict(tou=True,idx=3,gan='癸',weight=2)]}
        result=solve(dict(occ=occ,he={'he_groups':[]},ge_ss=None,route_priority={'正财':0,'正印':1}),[],{},set(occ))
        self.assertEqual([r['ss'] for r in result['selected']],['正财'])
    def test_root_single_owner(self):
        from bazi_core.geju_treatment import records
        occ={'正印':[dict(tou=True,idx=0,gan='癸',weight=1),dict(tou=True,idx=3,gan='癸',weight=1),dict(tou=False,idx=1,gan='癸',weight=1)]}
        rs=records(occ,{'he_groups':[]})
        self.assertEqual(sum(r['effective'] for r in rs if r['tou']),3)
        self.assertEqual(sum(len(r['root_ids']) for r in rs if r['tou']),1)
    def test_shengfu_preserves_disease_power(self):
        from bazi_core.geju_treatment import allocate,records
        occ={'食神':[dict(tou=True,idx=0,gan='丙',weight=2)],'正财':[dict(tou=True,idx=1,gan='戊',weight=1)],'七杀':[dict(tou=True,idx=2,gan='庚',weight=1)]}
        he={'he_groups':[]};drugs=[r for r in records(occ,he) if r['ss']=='正财']
        statuses,actions,_=allocate(occ,he,[dict(name='制杀太过',bing_ss=['食神'])],drugs,X.BING_YAO,'七杀')
        self.assertEqual(actions[0]['effect'],'增加保护对象力量')
        endpoint=next(e for e in statuses[0]['evidence'] if 'disease_power' in e)
        self.assertEqual(endpoint['disease_power'],2)
        self.assertEqual(endpoint['protected_gain'],1)

    def test_real_chart_bridge_across_day(self):
        from bazi_core.geju_treatment import records,route_chain
        occ=G._scan_tenshen('甲',['丁','己','甲','辛'],[M.ZHI_HIDE[z] for z in ['午','丑','寅','酉']])
        stems=[r for r in records(occ,{'he_groups':[]}) if r['tou']]
        chain=route_chain('通关',next(r for r in stems if r['ss']=='正财'),next(r for r in stems if r['ss']=='伤官'),[r for r in stems if r['ss']=='正官'],stems)
        self.assertEqual([r['idx'] for r in chain],[0,1,3])
    def test_no_drug_not_called_cure(self):
        from bazi_core.geju_treatment import allocate
        occ={'食神':[dict(tou=True,idx=0,gan='丙',weight=1)],'七杀':[dict(tou=True,idx=3,gan='庚',weight=2)]}
        result=allocate(occ,{'he_groups':[]},[dict(name='制杀太过',bing_ss=['食神'])],[],X.BING_YAO,'七杀')[0]
        self.assertEqual(result[0]['status'],'原局自有平衡')

    def test_qi_respects_effective_month(self):
        from bazi_core.geju_rules import qi_table
        he=dict(he_groups=[],gan_hua=[None]*4,branch_hua=[None,'土',None,None])
        zs=['子','午','酉','亥'];gs=['甲','乙','丙','丁']
        eff=G._build_eff_hide(zs,he,keep_month_original=True)
        actual=qi_table(gs,zs,he,eff)
        self.assertGreater(actual['火'],qi_table(gs,zs,he)['火'])
    def test_path_prefers_available_capacity(self):
        from bazi_core.geju_treatment import sheng_path
        a=dict(id='a',idx=0,ss='食神',effective=1)
        b=dict(id='b',idx=1,ss='正财',effective=.01)
        c=dict(id='c',idx=1,ss='偏财',effective=1)
        d=dict(id='d',idx=3,ss='正官',effective=1)
        self.assertEqual([r['id'] for r in sheng_path(a,d,[a,b,c,d])],['a','c','d'])

    def test_reused_evidence_keeps_complete_reference(self):
        from bazi_core.geju_treatment import allocate,records
        occ={'伤官':[dict(tou=True,idx=0,gan='丁',weight=1)],'正印':[dict(tou=True,idx=1,gan='癸',weight=1)]}
        he={'he_groups':[]};drugs=[r for r in records(occ,he) if r['ss']=='正印']
        statuses,actions,_=allocate(occ,he,[dict(name='A',bing_ss=['伤官']),dict(name='B',bing_ss=['伤官'])],drugs,{'A':[('克掉',['正印'],'')],'B':[('克掉',['正印'],'')]})
        reused=next(e for state in statuses for e in state['evidence'] if e.get('reused_evidence'))
        self.assertEqual(reused['evidence_ref'],actions[0]['evidence_id'])
        self.assertEqual(reused['chain'],actions[0]['chain'])
        self.assertEqual(reused['effect'],actions[0]['effect'])
    def test_remaining_balance_reports_actual_availability(self):
        from bazi_core.geju_treatment import ResourceBalances
        result=ResourceBalances({'x':2},{'x':.5})
        self.assertEqual(result['x'],.5)
        self.assertEqual(result.drug_budget['x'],2)
        self.assertEqual(result.flow_budget['x'],.5)
    def test_final_log_matches_final_selection(self):
        c=ctx(['丁','辛','甲','乙'],['子','酉','子','子'],'正官')
        r=X.compute_xiyong_geju(c)
        line=next(x for x in r['trace'] if '最终模式=' in x)
        self.assertIn('原局首选='+('、'.join(r['yong_shen_list']) or '无'),line)
        self.assertEqual(r['has_unresolved_bing'],bool(r['unresolved_bing']))
        self.assertEqual(r['used_original_drug'],bool(r['treatment_allocations']))
        self.assertFalse(any('无病，按' in x or '药已在原局' in x for x in r['trace']))
    def test_status_partial_canonical(self):
        from bazi_core.geju_status import State
        self.assertEqual(State.PARTIAL,'部分解决')
        from bazi_core import geju_rules
        occ={'伤官':[dict(tou=True,idx=0,gan='丁',weight=2)],'正印':[dict(tou=True,idx=1,gan='癸',weight=1)]}
        self.assertEqual(geju_rules.verify_rescue(occ,{'he_groups':[]},['伤官'],['正印'])[0]['status'],State.PARTIAL)

    def test_rooted_chong_blocker_remains_strong(self):
        result=G.compute_geju(dict(gans=['丁','癸','甲','辛'],zhis=['未','酉','午','未']),{'enable_special_ge':False})
        self.assertEqual(result['ge_status'],'真破格')
        self.assertTrue(any('丁@0' in line and '等级strong' in line for line in result['trace_log']))
    def test_owned_root_not_pending(self):
        c=ctx(['辛','癸','甲','丁'],['酉','子','寅','午'],'正官')
        result=X.compute_xiyong_geju(c)
        self.assertFalse(any(x.startswith('癸') for x in result['potential_yong_shen']))
        self.assertTrue(any(x['gan']=='癸' for x in result['supporting_roots']))
    def test_auxiliary_pool_separate_from_medicine(self):
        from bazi_core.geju_treatment import solve
        c=ctx(['癸','辛','甲','戊'],['子','酉','寅','辰'],'正官')
        c.update(auxiliary_ss={'正印'},route_priority={'偏财':0})
        result=solve(c,[],{}, {'偏财'})
        self.assertTrue(any(x['ss']=='正印' for x in result['auxiliary']))
        self.assertTrue(all(x['ss']=='偏财' for x in result['selected']))

    def test_transformed_luren_fallback_has_occurrences(self):
        r=G.compute_geju(dict(gans=['辛','戊','庚','庚'],zhis=['酉','申','申','戌']),{'enable_special_ge':False})
        self.assertEqual(r['ge_category'],'禄刃')
        self.assertTrue(r['clean_level'])
    def test_identical_stems_clear_by_position(self):
        r=G.compute_geju(dict(gans=['庚','辛','乙','庚'],zhis=['申','酉','卯','辰']),{'enable_special_ge':False})
        self.assertEqual(r['clean_level'],'浊而无去')
        self.assertTrue(any('逐柱去杂' in line and "('庚', 0)" in line for line in r['trace_log']))
    def test_empty_pending_list_cannot_claim_owned_roots_pending(self):
        r=G.compute_geju(dict(gans=['丙','庚','壬','戊'],zhis=['申','申','午','午']),{'enable_special_ge':False})['xiyong_geju']
        self.assertFalse(r['potential_yong_shen'])
        self.assertFalse(any(s['status']=='潜在救应、待透' for s in r['treatment_status']))

    def test_conflicting_drug_is_conditional(self):
        r=G.compute_geju(dict(gans=['甲','戊','辛','丁'],zhis=['午','辰','丑','丑']))['xiyong_geju']
        self.assertTrue(any(x['shen'].startswith('甲') for x in r['conditional_yong_shen']))
        self.assertFalse(any(x.startswith('甲') for x in r['yong_shen_list']))
        self.assertTrue(any('甲' in text for b in r['bing_list'] for text in b['bing_shen']))
    def test_nonexistent_disease_god_not_listed(self):
        r=G.compute_geju(dict(gans=['甲','戊','辛','丁'],zhis=['午','辰','丑','丑']))['xiyong_geju']
        self.assertFalse(any('原局无' in text for b in r['bing_list'] for text in b['bing_shen']))
        self.assertFalse(any('偏财' in text for text in r['ji_shen_list']))
    def test_removed_god_downgrades_to_hidden(self):
        r=G.compute_geju(dict(gans=['乙','庚','戊','壬'],zhis=['亥','辰','午','午']))
        self.assertEqual(r['main_ge_name'],'正官格')
        self.assertTrue(r['an_ge_flag'])
        self.assertEqual(r['ge_variant'],'暗格')
        self.assertIn('格神透干完全失效',r['note'])

    def test_removed_luren_print_not_reintroduced(self):
        r=G.compute_geju(dict(gans=['丙','辛','己','己'],zhis=['子','未','未','丑']))
        self.assertFalse(r['ji_shen_list'])
        self.assertFalse(any('正印' in b['bing_ss'] for b in r['xiyong_geju']['bing_list']))
        self.assertFalse(any('None' in b['name'] for b in r['xiyong_geju']['bing_list']))
    def test_transformed_luren_uses_normal_selection(self):
        r=G.compute_geju(dict(gans=['辛','戊','庚','庚'],zhis=['酉','申','申','戌']),{'enable_special_ge':False})
        self.assertTrue(r['xiang_shen_list'])
        self.assertTrue(r['xiyong_geju']['xi_shen_list'])
        self.assertTrue(r['xiyong_geju']['unresolved_bing'])
    def test_unrooted_ji_remains_weak(self):
        # 比劫透干但四支无根：只能按虚浮隐患记为成中有败，不能冒充强忌求救。
        r=G.compute_geju(dict(gans=['戊','壬','癸','癸'],zhis=['戌','午','酉','巳']))
        self.assertEqual(r['ge_status'],'成中有败')
        self.assertEqual(r['rescue_summary']['rescued_strong'],[])
        self.assertEqual(r['rescue_summary']['weak_risks'],['比肩','劫财'])
        self.assertIn('有效力量不足1',r['note'])

    def test_same_tenshen_strong_and_weak_kept_separate(self):
        r=G.compute_geju(dict(gans=['丁','癸','甲','丁'],zhis=['午','酉','子','子']),{'enable_special_ge':False})
        self.assertEqual(r['ge_status'],'败中有救')
        summary=r['rescue_summary']
        self.assertEqual([x['id'] for x in summary['strong_positions']],['0:1:丁'])
        self.assertEqual([x['id'] for x in summary['weak_positions']],['3:1:丁'])
        self.assertIn('伤官',summary['rescued_strong'])
        self.assertIn('伤官',summary['weak_risks'])
        self.assertEqual(summary['position_evidence'][0]['status'],'完全获救')
    def test_luren_compares_individual_stems(self):
        r=G.compute_geju(dict(gans=['丁','丙','庚','丁'],zhis=['亥','申','寅','丑']),{'enable_special_ge':False})
        self.assertEqual(r['main_ge_name'],'建禄格')
        self.assertEqual(r['xiang_shen_list'],['丙（七杀）'])

    def test_removed_candidate_cannot_activate_route_conflict(self):
        r=G.compute_geju(dict(gans=['癸','己','甲','丁'],zhis=['丑','午','寅','卯']),{'enable_special_ge':False})
        self.assertFalse(any('路线混杂' in line for line in r['trace_log']))
        self.assertFalse(r['xiyong_geju']['route_resolution'])
    def test_dual_route_compares_single_records(self):
        r=G.compute_geju(dict(gans=['癸','丙','甲','丙'],zhis=['丑','申','寅','午']),{'enable_special_ge':False})
        note=r['xiyong_geju']['route_resolution'][0]
        self.assertIn('保留癸',note)
        self.assertIn('力量1.50',note)
    def test_resolution_lists_only_actual_stems(self):
        r=G.compute_geju(dict(gans=['癸','丙','甲','丙'],zhis=['丑','申','寅','午']),{'enable_special_ge':False})
        note=r['xiyong_geju']['route_resolution'][0]
        self.assertNotIn('伤官',note)
        self.assertNotIn('偏印',note)
        self.assertIn('年柱',note)
        self.assertIn('月柱',note)
        self.assertIn('时柱',note)

    def test_no_contribution_moves_to_auxiliary(self):
        r=G.compute_geju(dict(gans=['丁','癸','甲','癸'],zhis=['午','酉','子','子']),{'enable_special_ge':False})['xiyong_geju']
        self.assertEqual([x['id'] for x in r['selected_records']],['1:1:癸'])
        self.assertEqual(len(r['yong_shen_list']),1)
        self.assertTrue(any('时干' in x for x in r['xi_shen_list']))
        self.assertIn('月干',r['yong_shen_list'][0])
        self.assertIn('年干丁',r['yong_shen_list'][0])
    def test_same_character_different_positions_labeled(self):
        c=ctx(['丁','癸','甲','癸'],['午','酉','子','子'],'正官')
        r=X.compute_xiyong_geju(c)
        labels=r['yong_shen_list']+r['xi_shen_list']
        self.assertEqual(len(labels),len(set(labels)))
        self.assertTrue(any('月干' in x for x in labels))
        self.assertTrue(any('时干' in x for x in labels))

    def test_combination(self):
        c=ctx(['丙','壬','甲','庚'], ['寅','子','寅','申'],'七杀')
        r=X.compute_xiyong_geju(c)
        self.assertIn('combination_validation',r)
    def test_half_rescue(self):
        c=ctx(['丁','辛','甲','壬'], ['午','酉','辰','子'])
        c['he']['he_groups']=[dict(type='wuhe',members=['丁','壬'],idx=[0,3])]
        b=dict(name='伤官见官',bing_ss=['伤官'])
        _,inside,_=X._pick_yao(b,c)
        self.assertFalse(any('局内已有五合' in y for y in inside))
        all_yao,_,_=X._pick_yao(b,c)
        self.assertTrue(any('仅救一半' in y for y in all_yao))
    def test_adjacent_rescue(self):
        c=ctx(['丁','壬','甲','辛'], ['午','子','辰','酉'])
        c['he']['he_groups']=[dict(type='wuhe',members=['丁','壬'],idx=[0,1])]
        _,inside,_=X._pick_yao(dict(name='伤官见官',bing_ss=['伤官']),c)
        self.assertTrue(any('局内已有五合' in y for y in inside))
    def test_multiple_ji_not_all_rescued(self):
        trace=[]
        out=G._evaluate_bage('甲',['丁','庚','甲','辛'],
            [['丁'],['庚'],['壬'],['辛']],{'he_groups':[]},
            '正官','辛',['辛'],'辛',None,trace)
        self.assertEqual(out[0],'真破格')
        self.assertTrue(any('逐个验证' in t for t in trace))
    def test_route_strength_and_resolution(self):
        c=ctx(['丙','壬','甲','庚'], ['寅','子','子','申'],'七杀')
        c.update(route_label='杀印相生',route_xiang=['正印','偏印'],
                 ge_note='七杀双路线相邻相克',ge_status='真破格',route_conflict=True)
        r=X.compute_xiyong_geju(c)
        self.assertTrue(r['route_resolution'])
        self.assertTrue(all('印' in x for x in r['yong_shen_list']))

    def test_all_positions_same(self):
        # 官格伤官在年/月/时，均为有力忌神；支中伤官不计。
        for i in [0,1,3]:
            gs=['甲','辛','甲','甲'];gs[i]='丁'
            trace=[]
            out=G._evaluate_bage('甲',gs,[['丁'],['辛'],['甲'],['甲']],{'he_groups':[]},'正官','辛',['辛'],'辛',None,trace)
            self.assertEqual(out[0],'真破格')

if __name__=='__main__': unittest.main()

class AuditClosure(unittest.TestCase):
    def test_weighted_cong_dominance(self):
        from bazi_core.engine import analyze
        r=analyze(dict(gans=list('戊乙癸戊'),zhis=list('子卯卯午')))['geju']
        self.assertEqual(r['main_ge_name'],'从儿格')

    def test_blade_structural_shortfall(self):
        from bazi_core.engine import analyze
        r=analyze(dict(gans=list('乙壬丙己'),zhis=list('未午寅丑')))['geju']
        x=r['xiyong_geju']
        b=next(b for b in x['bing_list'] if b['name']=='阳刃无制')
        self.assertTrue(b['affects_ge'])
        self.assertEqual(b['treatment_status'],'原局有对应药')
        e=b['rescue_evidence'][0]
        self.assertAlmostEqual(e['blade_power'],1.25)
        self.assertAlmostEqual(e['control_power'],.5)
        self.assertAlmostEqual(e['remaining'],.75)


class Optimization20261106(unittest.TestCase):
    def chart(self, text):
        ps = text.split()
        return dict(gans=[p[0] for p in ps], zhis=[p[1] for p in ps])

    def test_unrooted_visible_ji_is_weak(self):
        r = G.compute_geju(self.chart('丁酉 辛酉 甲子 乙丑'), {'enable_special_ge': False})
        self.assertEqual(r['ge_status'], '成中有败')
        self.assertTrue(any('丁@0' in line and '等级weak' in line for line in r['trace_log']))
        self.assertFalse(any('等级strong' in line for line in r['trace_log'] if '丁@0' in line))

    def test_owned_root_not_pending_but_latent_candidates_are_split(self):
        r = G.compute_geju(self.chart('庚寅 乙酉 甲子 丙寅'), {'enable_special_ge': False})
        x = r['xiyong_geju']
        self.assertEqual(r['ge_status'], '成格')
        self.assertEqual(x['yong_shen_list'], [])
        self.assertEqual(x['primary_visible_yong_shen'], [])
        self.assertTrue(x['latent_hidden_yong_shen'])
        self.assertTrue(all('藏' in item for item in x['latent_hidden_yong_shen']))
        self.assertEqual(x['yong_visibility'], 'latent_hidden_only')

    def test_duplicate_hidden_drugs_are_deduplicated(self):
        r = G.compute_geju(self.chart('丁酉 辛酉 甲子 乙丑'), {'enable_special_ge': False})
        b = next(x for x in r['xiyong_geju']['bing_list'] if x['name'] == '伤官见官')
        keys = [X._key(item) for item in b['yao']]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(sum(item.startswith('癸') for item in b['yao']), 1)

    def test_dynamic_route_disease_uses_current_treatment_table(self):
        r = G.compute_geju(self.chart('丁午 癸酉 甲子 丁子'), {'enable_special_ge': False})
        b = next(x for x in r['xiyong_geju']['bing_list'] if x['name'].startswith('路线受损'))
        self.assertTrue(b['yao'])
        self.assertTrue(any(item.startswith('癸') for item in b['yao']))

    def test_fake_cong_is_explained_without_becoming_external_ge(self):
        for text, ge_name in [('庚戌 戊未 乙辰 戊申', '偏财格'),
                              ('己寅 壬戌 壬卯 甲巳', '七杀格')]:
            r = G.compute_geju(self.chart(text), {'enable_special_ge': False})
            self.assertEqual(r['ge_category'], '八格')
            self.assertEqual(r['main_ge_name'], ge_name)
            self.assertFalse(r['is_cong'])
            self.assertTrue(r['is_fake_cong'])
            self.assertIn('不触发外格', r['cong_context']['note'])

    def test_hua_qi_overrides_only_final_xiyong_and_keeps_raw(self):
        from bazi_core.engine import analyze
        r = analyze(self.chart('甲子 戊辰 甲申 己丑'))
        self.assertEqual(r['geju']['main_ge_name'], '化土格（甲己）')
        self.assertEqual(r['xiyong_wangshuai']['favored'], ['水', '木'])
        self.assertEqual(r['final_xiyong']['effective_source'], 'geju_special_ge')
        self.assertFalse(r['final_xiyong']['wangshuai_applicable'])
        self.assertTrue(r['final_xiyong']['geju_overrides_wangshuai'])
        self.assertEqual(r['final_xiyong']['favored'], ['土', '金'])
        self.assertEqual(r['final_xiyong']['disliked'], ['木'])
        self.assertEqual(r['geju']['xiyong_geju']['special_yong_wuxing'], ['土'])
        self.assertIn('外格由化气/两气成象', r['geju']['cong_context']['note'])
        self.assertIn('不是三维喜用融合', r['final_xiyong']['note'])

    def test_non_hua_special_does_not_override_wangshuai(self):
        from bazi_core.engine import analyze
        r = analyze(self.chart('庚戌 戊未 乙辰 戊申'))
        self.assertEqual(r['final_xiyong']['effective_source'], 'wangshuai')
        self.assertTrue(r['final_xiyong']['wangshuai_applicable'])
        self.assertEqual(r['final_xiyong']['favored'], r['xiyong_wangshuai']['favored'])

    def test_root_semantics_are_exposed(self):
        from bazi_core.engine import analyze
        r = analyze(self.chart('庚寅 乙酉 甲子 丙寅'))
        self.assertEqual(r['day_root_level'], r['wangshuai']['day_root_level'])
        self.assertIn('structural_root_scope', r['root_semantics'])
        self.assertIn('energy_root_scope', r['root_semantics'])
