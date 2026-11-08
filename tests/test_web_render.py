# -*- coding: utf-8 -*-
"""Render checks use real engine responses; Node provides a minimal DOM and fetch."""
import json
import subprocess
import unittest
from pathlib import Path
from web.server import do_analyze
from tests.test_wangshuai_state import chart
from bazi_core.engine import analyze
from tests.test_arbitration import model
from tests.test_fusion_completion import prepared


class RenderTests(unittest.TestCase):
    def test_current_root_and_both_fake_cong_views(self):
        outputs = [do_analyze({"chart": s,"input_kind":"rule_case"}) for s in
                   ('甲亥 壬子 甲卯 壬申', '丙未 戊酉 甲未 己辰', '甲辰 甲丑 戊巳 甲辰')]
        def provider(context): return prepared(context['facts'])[0]['fusion_evidence']
        integrated=analyze(chart('甲子 癸丑 甲午 丙寅'),config={'climate_model':model()},fusion_provider=provider)
        self.assertTrue(integrated['final_xiyong']['action_release_ready'])
        outputs.append(integrated)
        outputs += [analyze(chart(s)) for s in ('丙午 庚子 辛亥 癸巳','辛亥 壬辰 丙寅 乙未')]
        result = subprocess.run(['node', str(Path(__file__).with_suffix('.js'))],
                                input=json.dumps(outputs, ensure_ascii=False),
                                text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('render checks passed', result.stdout)
