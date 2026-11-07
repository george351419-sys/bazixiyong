# -*- coding: utf-8 -*-
"""固定规则预期及边界提示；案例期望不可从当前输出自动刷新。"""
import json
import unittest
from pathlib import Path
from bazi_core import wangshuai as W
from tests.test_wangshuai_state import chart


class RuleReviewTests(unittest.TestCase):
    def test_rule_derived_cases(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/wangshuai_rule_review_v1.json').read_text())
        self.assertEqual(fixture['review_status'], 'pending_user_or_expert')
        self.assertEqual(len(fixture['cases']), 14)
        for case in fixture['cases']:
            with self.subTest(case=case['id']):
                self.assertTrue(case['basis'])
                self.assertTrue(case['allowed_disagreement'])
                r = W.compute_wangshuai(chart(case['chart']))
                e = case['expected']
                for key in ('tag', 'effective_root_level'):
                    if key in e:
                        self.assertEqual(r[key], e[key])
                for key in ('effective_count', 'effective_energy'):
                    if key in e:
                        self.assertAlmostEqual(r['root_state'][key], e[key])
                if 'pull_triggered' in e:
                    self.assertEqual(r['root_detail']['pull_event']['triggered'], e['pull_triggered'])
                if 'forbidden_tags' in e:
                    self.assertNotIn(r['tag'], e['forbidden_tags'])
                if 'no_root_at' in e:
                    self.assertFalse(any(x['branch_index'] == e['no_root_at'] for x in r['effective_roots']))
                if 'root' in e:
                    root = next(x for x in r['effective_roots'] if x['branch_index'] == e['root']['branch_index'])
                    for key, value in e['root'].items():
                        self.assertEqual(root[key], value)

    def test_phase_marks_do_not_promote_soil(self):
        r = W.compute_wangshuai(chart('甲辰 甲丑 戊巳 甲辰'))
        mark = next(x for x in r['phase_marks'] if x['branch_index'] == 2)
        self.assertEqual(mark['label'], '禄')
        self.assertTrue(mark['active'])
        self.assertEqual(next(x for x in r['effective_roots'] if x['branch_index'] == 2)['root_type'], '中气根')

    def test_transformation_deactivates_original_phase(self):
        r = W.compute_wangshuai(chart('丙寅 丁午 甲戌 庚申'))
        mark = next(x for x in r['phase_marks'] if x['branch_index'] == 0)
        self.assertEqual(mark['label'], '禄')
        self.assertFalse(mark['active'])
        self.assertEqual(mark['inactive_reason'], '合化置换')

    def test_pull_deactivates_original_phase(self):
        r = W.compute_wangshuai(chart('丁酉 癸午 甲子 癸卯'))
        mark = next(x for x in r['phase_marks'] if x['branch_index'] == 3)
        self.assertFalse(mark['active'])
        self.assertEqual(mark['inactive_reason'], '根已被拔')

    def test_exact_balance_boundary_inclusive(self):
        hints = W._boundary_hints(110, 100, '身旺', True, .85)
        h = next(x for x in hints if x['kind'] == 'balance')
        self.assertEqual(h['distance'], 0)
        self.assertEqual(h['adjacent_tag'], '中和偏旺')
        self.assertEqual(W._balance_tag(1.1, True), '身旺')

    def test_balance_below_and_outside_radius(self):
        h = W._boundary_hints(109, 100, '中和偏旺', True, .85)
        self.assertEqual(h[0]['adjacent_tag'], '身旺')
        self.assertEqual(W._boundary_hints(120, 100, '身旺', True, .85), [])

    def test_from_weak_requires_root_eligibility(self):
        no = W._boundary_hints(16, 84, '身弱', True, .85)
        self.assertFalse(any(x['kind'] == 'cong_weak' for x in no))
        yes = W._boundary_hints(16, 84, '身弱', True, .85, weak_candidate='假从弱')
        h = next(x for x in yes if x['kind'] == 'cong_weak')
        self.assertEqual(h['adjacent_tag'], '假从弱')

    def test_from_weak_boundary_other_side(self):
        h = W._boundary_hints(15, 85, '从弱', False, .85, weak_candidate='从弱', rootless=True)
        self.assertEqual(next(x for x in h if x['kind'] == 'cong_weak')['adjacent_tag'], '身弱无根')

    def test_from_strong_hint(self):
        h = W._boundary_hints(84, 16, '身旺', True, .85, strong_candidate='从强')
        self.assertEqual(next(x for x in h if x['kind'] == 'cong_strong')['adjacent_tag'], '从强')

    def test_void_hint_requires_momentum(self):
        h = W._boundary_hints(51, 49, '虚旺', True, .85, rootless=True, void_momentum=12)
        self.assertEqual(next(x for x in h if x['kind'] == 'void_wang')['adjacent_tag'], '身弱无根')
        self.assertEqual(W._boundary_hints(51, 49, '身弱无根', True, .85, rootless=True, void_momentum=9), [])

    def test_overlapping_experimental_windows_do_not_invent_adjacent_tag(self):
        hints = W._boundary_hints(51, 49, '假从强', True, .51,
                                  weak_candidate='假从弱', strong_candidate='假从强')
        self.assertFalse(any(x['kind'] == 'cong_weak' for x in hints))
        self.assertTrue(any(x['kind'] == 'cong_strong' for x in hints))
