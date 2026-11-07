# -*- coding: utf-8 -*-
"""Render checks use real engine responses; Node provides a minimal DOM and fetch."""
import json
import subprocess
import unittest
from pathlib import Path
from web.server import do_analyze
from tests.test_wangshuai_state import chart


class RenderTests(unittest.TestCase):
    def test_current_root_and_both_fake_cong_views(self):
        outputs = [do_analyze({"chart": s}) for s in
                   ('甲亥 壬子 甲卯 壬申', '丙未 戊酉 甲未 己辰', '甲辰 甲丑 戊巳 甲辰')]
        result = subprocess.run(['node', str(Path(__file__).with_suffix('.js'))],
                                input=json.dumps(outputs, ensure_ascii=False),
                                text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('render checks passed', result.stdout)
