"""固定公历行为基线与时间边界。360例不是命理正确性的独立金标准。"""
import json
import sys
import unittest
from pathlib import Path
from datetime import datetime,timedelta
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.vendor')]
from lunar_python import Solar
from bazi_core.engine import analyze
from bazi_core.paipan import auto_solar_term_day
from bazi_core.metadata import default_config


def chart_at(dt,sect=2):
    ec=Solar.fromYmdHms(dt.year,dt.month,dt.day,dt.hour,dt.minute,dt.second).getLunar().getEightChar()
    ec.setSect(sect)
    ps=[ec.getYear(),ec.getMonth(),ec.getDay(),ec.getTime()]
    return dict(gans=[p[0] for p in ps],zhis=[p[1] for p in ps]),ps


def assert_consistent(test,result):
    test.assertTrue(result['ok'])
    x=result['geju']['xiyong_geju']
    test.assertEqual(x['has_unresolved_bing'],bool(x['unresolved_bing']))
    test.assertEqual(x['used_original_drug'],bool(x['treatment_allocations']))
    test.assertTrue(all(v>=-1e-9 for v in x['remaining_drug_capacity'].values()))
    test.assertEqual(len(x['yong_shen_list']),len(set(x['yong_shen_list'])))
    registry=x['evidence_registry']
    for disease in x['bing_list']:
        for evidence in disease.get('rescue_evidence',[]):
            if evidence.get('evidence_ref'):
                test.assertIn(evidence['evidence_ref'],registry)
                test.assertEqual(evidence['chain'],registry[evidence['evidence_ref']]['chain'])
    json.dumps(result,ensure_ascii=False,allow_nan=False)


class CalendarRegression(unittest.TestCase):
    def test_fixed_360_dates(self):
        fixture=json.loads((ROOT/'tests/fixtures/calendar_360.json').read_text())
        self.assertEqual(default_config(),fixture['config'],
                         '默认配置已变更，请先审核基线迁移，勿直接覆盖预期结果')
        self.assertEqual(len(fixture['cases']),360)
        for case in fixture['cases']:
            with self.subTest(date=case['date'],external=case['external']):
                chart,ps=chart_at(datetime.fromisoformat(case['date']),fixture['sect'])
                self.assertEqual(ps,case['pillars'])
                result=analyze(chart,config=dict(fixture['config'],enable_special_ge=case['external']))
                assert_consistent(self,result)
                self.assertEqual({k:result['geju'][k] for k in case['baseline']},case['baseline'])
                self.assertEqual({k:result['wangshuai'][k] for k in case['wangshuai_baseline']},
                                 case['wangshuai_baseline'])
                ws = result['wangshuai']
                self.assertTrue(all(not r['is_broken'] or r['eff_energy'] == 0
                                    for r in ws['effective_roots']))
                self.assertAlmostEqual(sum(r['eff_energy'] for r in ws['effective_roots']),
                                       ws['root_state']['effective_energy'], delta=.04)
    def test_jie_boundaries(self):
        table=Solar.fromYmdHms(2026,6,1,12,0,0).getLunar().getJieQiTable()
        names=['小寒','立春','惊蛰','清明','立夏','芒种','小暑','立秋','白露','寒露','立冬','大雪']
        for name in names:
            dt=datetime.fromisoformat(table[name].toYmdHms())
            before,_=chart_at(dt-timedelta(seconds=1))
            at,_=chart_at(dt)
            after,_=chart_at(dt+timedelta(seconds=1))
            with self.subTest(jie=name):
                self.assertNotEqual(before['zhis'][1],at['zhis'][1])
                self.assertEqual(at['zhis'][1],after['zhis'][1])
                if name=='立春': self.assertNotEqual(before['gans'][0],at['gans'][0])
                for moment,chart in ((dt-timedelta(seconds=1),before),(dt,at),(dt+timedelta(seconds=1),after)):
                    info=auto_solar_term_day(moment.isoformat(' '))
                    self.assertIsNotNone(info)
                    chart.update(solar_term_day=info['day'],jie_name=info['jie_name'])
                    assert_consistent(self,analyze(chart))
                self.assertEqual(auto_solar_term_day(dt.isoformat(' '))['day'],0)
    def test_zi_hour_both_conventions(self):
        start=datetime(2026,11,6)
        times=[start.replace(hour=22,minute=59,second=59),start.replace(hour=23),start.replace(hour=23,minute=59,second=59),start+timedelta(days=1),start+timedelta(days=1,hours=1)]
        for sect in (1,2):
            samples=[chart_at(dt,sect)[0] for dt in times]
            with self.subTest(sect=sect):
                day=lambda c:(c['gans'][2],c['zhis'][2])
                if sect==1: self.assertNotEqual(day(samples[0]),day(samples[1]));self.assertEqual(day(samples[1]),day(samples[3]))
                else:self.assertEqual(day(samples[0]),day(samples[1]));self.assertNotEqual(day(samples[2]),day(samples[3]))
                self.assertEqual([c['zhis'][3] for c in samples],['亥','子','子','子','丑'])
                for sample in samples:assert_consistent(self,analyze(sample))

if __name__=='__main__':unittest.main()
