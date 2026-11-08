"""跨步骤有效状态回归：合化、开库、拔根、从格护栏。"""
import unittest
from bazi_core import wangshuai as W, heju, metadata as M


def chart(s):
    p = s.split()
    return {'gans': [x[0] for x in p], 'zhis': [x[1] for x in p]}


class EffectiveRootTests(unittest.TestCase):
    def test_transformed_root_feeds_stem(self):
        r = W.compute_wangshuai(chart('庚亥 乙卯 乙午 壬未'))
        stem = next(g for g in r['debug']['gan_detail'] if g['pos'] == 1)
        self.assertEqual(stem['root_level'], 2)
        self.assertEqual(stem['before_season'], 42)
        self.assertAlmostEqual(stem['contribution'],42*stem['season_factor'])

    def test_transformation_removes_old_root(self):
        self.assertEqual(W._root_level(['亥'], ['木'], '水', '壬'), 0)
        self.assertEqual(W._root_level(['亥'], ['木'], '木', '乙'), 2)

    def test_opening_updates_non_day_elements(self):
        c = chart('甲丑 乙未 丙午 丁寅')
        r = W.compute_wangshuai(c)
        self.assertEqual({x['stored_wuxing'] for x in r['root_detail']['store_opened_roots']}, {'木', '金'})
        unopened = W.compute_wangshuai(c, {'store_open_enable': False})
        self.assertGreater(r['F'], unopened['F'])
        self.assertGreater(r['K'], unopened['K'])

    def test_opening_updates_stem_tier(self):
        r = W.compute_wangshuai(chart('辛未 乙辰 庚丑 辛丑'))
        self.assertEqual(r['effective_root_level'], 3)
        self.assertEqual(r['day_root_level'], 1)
        self.assertTrue(all(g['root_level'] == 3 for g in r['debug']['gan_detail'] if g['gan'] == '辛'))

    def test_no_phantom_roots(self):
        self.assertFalse(heju._has_di_zhi_root(['午'] * 4, '木'))
        self.assertFalse(heju._has_di_zhi_root(['子'] * 4, '金'))

    def test_bound_root_remains_and_transformed_root_changes(self):
        self.assertTrue(heju._has_di_zhi_root(['寅'], '木', branch_hua=[None]))
        self.assertFalse(heju._has_di_zhi_root(['寅'], '木', branch_hua=['火']))
        self.assertTrue(heju._has_di_zhi_root(['寅'], '火', branch_hua=['火']))

    def test_intact_close_root_blocks_fake_even_with_yin(self):
        c = chart('庚戌 丙酉 乙寅 己巳')
        r = W.compute_wangshuai(c)
        self.assertNotIn(r['tag'], ('从弱', '假从弱'))

    def test_pulled_root_has_separate_effective_tier(self):
        r = W.compute_wangshuai(chart('丁酉 癸午 甲子 癸卯'))
        self.assertEqual(r['root_status'], '独根被冲拔根')
        self.assertEqual(r['effective_root_level'], 0)
        self.assertEqual(r['root_energy'], 0)

    def test_strict_gate_blocks_rooted_fake(self):
        r = W.compute_wangshuai(chart('丙未 戊酉 甲未 己辰'), {'cong_root_gate': 'strict'})
        self.assertNotIn(r['tag'], ('从弱', '假从弱'))

    def test_independent_strong_root_reference(self):
        # 独立枚举，不调用委托别名充当预期值。
        for z in M.ZHI_LIST:
            for opened in (set(), {0}):
                expected = set()
                for p, g in enumerate(M.ZHI_HIDE[z]):
                    wx = M.WUXING_GAN[g]
                    if (p == 0 or M.CHANGSHENG_10GAN[g] == z or
                        (p == 2 and 0 in opened and z in M.STORE_INFO and M.STORE_INFO[z]['wuxing'] == wx)):
                        expected.add(wx)
                self.assertEqual(W._strong_root_gan([z], [None], opened), expected)

    def test_lian_gen_uses_transformed_state(self):
        r = W.compute_wangshuai(chart('戊寅 癸午 丙戌 甲午'))
        pair = next(g for g in r['he_groups'] if g['type'] == 'wuhe')
        self.assertTrue(pair['hua_success'], pair['reason'])

    def test_scope_does_not_change_weak_cong(self):
        c = chart('甲午 丙丑 癸戌 丁未')
        a = W.compute_wangshuai(c)
        b = W.compute_wangshuai(c, {'root_include_mid_micro': True})
        self.assertEqual(a['tag'], '假从弱')
        self.assertEqual((a['tag'], a['F'], a['K']), (b['tag'], b['F'], b['K']))

    def test_multiple_effective_roots_prevent_unique_pull(self):
        r = W.compute_wangshuai(chart('庚巳 乙寅 戊申 丙卯'))
        self.assertFalse(r['root_detail']['pull_event']['triggered'])
        self.assertEqual(r['root_detail']['pull_event']['pre_count'], 3)
        self.assertEqual(r['effective_root_level'], 2)
        self.assertGreater(r['root_state']['effective_count'], 0)
        self.assertNotIn(r['tag'], ('身弱无根', '虚旺'))

    def test_changsheng_qualifies_without_inventing_energy(self):
        r = W.compute_wangshuai(chart('甲子 丙午 庚巳 壬寅'))
        root = next(x for x in r['effective_roots'] if x['branch_index'] == 2)
        self.assertEqual(root['root_type'], '长生')
        self.assertEqual(root['base_energy'], M.zhi_tier_energy('巳')[2])
        self.assertEqual(root['base_energy'], 10)

    def test_far_strong_root_needs_real_damage(self):
        c = chart('丙子 甲寅 甲卯 丙子')
        he = heju.evaluate(c['gans'], c['zhis'])
        far = [{'branch_index': 0, 'root_type': '本气根', 'is_broken': False}]
        self.assertFalse(W._cong_fake_weak_root_evidence(far, c['zhis'], he, {}))

    def test_micro_root_cannot_receive_strong_cong(self):
        r = W.compute_wangshuai(chart('丙亥 乙寅 丙卯 乙戌'))
        self.assertEqual(r['effective_root_level'], 1)
        self.assertNotIn(r['tag'], ('从强', '假从强'))
        self.assertEqual(r['cong_info']['support_profile'], '印主导')

    def test_config_rejects_invalid_values(self):
        for cfg in [{'cong_threshold': 0}, {'cong_threshold': 1.01},
                    {'branch_chong_factor': -1}, {'branch_chong_factor': float('nan')},
                    {'cong_root_gate': 'typo'}, {'store_open_enable': 1},
                    {'micro_root_factor': .1}]:
            with self.subTest(config=cfg), self.assertRaises(ValueError):
                W.compute_wangshuai(chart('甲子 丙寅 甲卯 丙子'), cfg)

    def test_invalid_chart_has_explicit_error(self):
        for c in [{'gans': ['甲'], 'zhis': ['子']},
                  {'gans': list('甲甲甲甲'), 'zhis': list('子子子错')}]:
            with self.assertRaises(ValueError):
                W.compute_wangshuai(c)

    def test_trace_and_energy_accounting(self):
        r = W.compute_wangshuai(chart('辛未 乙辰 庚丑 辛丑'))
        self.assertTrue(any(t['passed'] for t in r['decision_trace']))
        self.assertFalse(r['confidence_semantics']['calibrated_probability'])
        self.assertAlmostEqual(sum(r['relation_energy'].values()), r['F'] + r['K'], places=2)
        self.assertAlmostEqual(r['root_state']['effective_energy'],
            sum(x['eff_energy'] for x in r['effective_roots'] if not x['is_broken']), places=2)

    def test_engine_propagates_effective_state(self):
        from bazi_core.engine import analyze
        r = analyze(chart('辛未 乙辰 庚丑 辛丑'))
        self.assertEqual(r['effective_root_level'], r['wangshuai']['effective_root_level'])

    def test_effective_invariants_random(self):
        import random
        rng = random.Random(20261107)
        for _ in range(1000):
            r = W.compute_wangshuai({'gans': [rng.choice(M.GAN_LIST) for _ in range(4)],
                                     'zhis': [rng.choice(M.ZHI_LIST) for _ in range(4)]})
            if r['tag'] in ('身弱无根', '虚旺', '从弱'):
                self.assertEqual(r['effective_root_level'], 0)
            if r['tag'] in ('从强', '假从强'):
                self.assertIn(r['effective_root_level'], (2, 3))
            if r['tag'] == '假从弱' and r['effective_root_level'] in (2, 3):
                self.assertTrue(all(x['broken'] or x['weak_evidence']
                                    for x in r['cong_info']['root_evidence']))

    def test_calendar_current_state_consistency(self):
        import json
        from datetime import datetime
        from pathlib import Path
        from tests.test_calendar_regression import chart_at, assert_consistent
        from bazi_core.engine import analyze
        f = json.loads((Path(__file__).parent / 'fixtures/calendar_360.json').read_text())
        for case in f['cases']:
            c, _ = chart_at(datetime.fromisoformat(case['date']), f['sect'])
            assert_consistent(self, analyze(c, {'enable_special_ge': case['external']}))

    def test_broken_root_energy_contract(self):
        r = W.compute_wangshuai(chart('丁酉 癸午 甲子 癸卯'))
        self.assertTrue(any(x['is_broken'] for x in r['effective_roots']))
        for root in r['effective_roots']:
            if root['is_broken']:
                self.assertEqual(root['eff_energy'], 0)
                self.assertGreater(root['original_base_energy'], 0)
        self.assertEqual(sum(x['eff_energy'] for x in r['effective_roots']),
                         r['root_state']['effective_energy'])

    def test_all_root_scopes_have_identical_decisions(self):
        import random
        rng = random.Random(7)
        for _ in range(500):
            c = {'gans': [rng.choice(M.GAN_LIST) for _ in range(4)],
                 'zhis': [rng.choice(M.ZHI_LIST) for _ in range(4)]}
            a = W.compute_wangshuai(c)
            b = W.compute_wangshuai(c, {'root_include_mid_micro': True})
            for key in ('tag', 'F', 'K', 'effective_root_level', 'confidence'):
                self.assertEqual(a[key], b[key], (c, key))

    def test_unique_middle_root_can_be_pulled(self):
        r = W.compute_wangshuai(chart('甲未 丙酉 丙亥 丙丑'))
        self.assertTrue(r['root_detail']['pull_event']['triggered'])
        self.assertEqual(r['effective_root_level'], 0)

    def test_missing_input_is_value_error(self):
        for c in [{}, {'gans': ['甲'] * 4}, {'zhis': ['子'] * 4},
                  {'gans': None, 'zhis': ['子'] * 4},
                  {'year': None, 'month': {}, 'day': {}, 'hour': {}},
                  {'gans': 1234, 'zhis': ['子'] * 4},
                  {'year': {}, 'month': {}, 'day': {}, 'hour': {}}]:
            with self.subTest(chart=c), self.assertRaises(ValueError):
                W.compute_wangshuai(c)

    def test_duplicate_combination_prefers_month(self):
        r = W.compute_wangshuai(chart('癸子 甲子 壬申 庚辰'))
        group = next(g for g in r['he_groups'] if g['type'] == 'sanhe')
        self.assertIn(1, group['idx'])
        self.assertNotIn(0, group['idx'])
        self.assertEqual(r['debug']['branch_hua'][1], '水')
        self.assertIsNone(r['debug']['branch_hua'][0])
        self.assertEqual(heju._members_present(list('辰子申辰'), ['申', '子', '辰']), [2, 1, 0])

    def test_every_combination_has_unique_positions(self):
        r = W.compute_wangshuai(chart('戊寅 癸午 丙戌 甲午'))
        for group in r['he_groups']:
            self.assertEqual(len(group['idx']), len(set(group['idx'])))
            self.assertEqual(len(group['idx']), len(group['members']))

    def test_fake_weak_explains_actual_micro_roots(self):
        from bazi_core.engine import analyze
        r = analyze(chart('丙未 戊酉 甲未 己辰'))
        self.assertEqual(r['tag'], '假从弱')
        xy = r['xiyong_wangshuai']
        self.assertTrue(xy['conditional'])
        self.assertTrue(xy['residual_support'])
        self.assertNotIn('残存印比强根', xy['principle'])
        for ev in xy['residual_support']:
            if 'branch_index' in ev:
                self.assertTrue(any(x['branch_index'] == ev['branch_index']
                    and not x['is_broken'] for x in r['wangshuai']['effective_roots']))

    def test_fake_weak_without_chart_does_not_invent_evidence(self):
        from bazi_core.engine import xiyong_for_tag
        xy = xiyong_for_tag('假从弱', '木')
        self.assertEqual(xy['residual_support'], [])
        self.assertIn('未提供原局证据', xy['note'])

    def test_self_punish_excludes_transformed_duplicate(self):
        r = W.compute_wangshuai(chart('甲辰 辛酉 壬辰 丙午'),
            {'store_self_punish_open': True, 'enable_lian_gen_check': False})
        self.assertEqual(r['debug']['branch_hua'][0], '金')
        self.assertFalse(r['root_detail']['store_open'])
        self.assertEqual(r['effective_root_level'], 1)

    def test_self_punish_keeps_two_live_duplicates(self):
        c = chart('甲辰 丙午 壬辰 乙卯')
        r = W.compute_wangshuai(c, {'store_self_punish_open': True})
        self.assertEqual({x['branch_index'] for x in r['root_detail']['store_opened_roots']}, {0, 2})
        self.assertFalse(W.compute_wangshuai(c)['root_detail']['store_open'])

    def test_config_edges_have_value_error(self):
        for cfg in [{'branch_chong_factor': 0}, {'cong_root_gate': []},
                    {'cong_root_gate': {}}, {'tiangan_base': 1e308},
                    {'tiangan_base': 10 ** 1000}, {'hehua_strict': False}]:
            with self.subTest(config=cfg), self.assertRaises(ValueError):
                W.compute_wangshuai(chart('庚卯 庚酉 甲卯 庚酉'), cfg)

    def test_large_legal_config_is_finite(self):
        import json
        r = W.compute_wangshuai(chart('庚卯 庚酉 甲卯 庚酉'), {'tiangan_base': 1000000})
        json.dumps(r, allow_nan=False)
        self.assertEqual(r['rules_version'], 'wangshuai_season_v3_day_included')

    def test_direct_heju_rejects_non_strict_mode(self):
        with self.assertRaises(ValueError):
            heju.evaluate(list('甲乙丙丁'), list('子丑寅卯'), {'hehua_strict': False})

    def test_fake_strong_explains_opposition(self):
        from bazi_core.engine import analyze
        r = analyze(chart('甲亥 壬子 甲卯 壬申'))
        self.assertEqual(r['tag'], '假从强')
        xy = r['xiyong_wangshuai']
        self.assertTrue(xy['conditional'])
        self.assertTrue(xy['requires_review'])
        self.assertTrue(xy['residual_opposition'])
        for e in xy['residual_opposition']:
            self.assertGreater(e['eff_energy'], 0)
            self.assertIn(e, [dict(x, kind='克泄耗强根残存')
                for x in r['wangshuai']['cong_info']['residual_k_evidence']])
        self.assertIn('时支金', xy['note'])

    def test_fake_strong_missing_evidence_is_explicit(self):
        from bazi_core.engine import xiyong_for_tag
        xy = xiyong_for_tag('假从强', '木')
        self.assertEqual(xy['residual_opposition'], [])
        self.assertIn('未提供原局证据', xy['note'])


if __name__ == '__main__':
    unittest.main()
