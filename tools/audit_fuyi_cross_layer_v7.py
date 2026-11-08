"""复核direction_v7跨层口径；只记录反例，不修改规则或冻结基线。"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bazi_core.engine import analyze
from bazi_core.metadata import WUXING_GAN


def main():
    stats, examples, case_sets = Counter(), {}, {}

    def hit(key, case_index, evidence):
        stats[key] += 1
        case_sets.setdefault(key, set()).add(case_index)
        examples.setdefault(key, evidence)

    cases = json.loads((ROOT / 'tests/fixtures/calendar_360.json').read_text())['cases']
    for index, case in enumerate(cases):
        p = case['pillars']
        r = analyze(dict(gans=[x[0] for x in p], zhis=[x[1] for x in p]))
        w, f, d = r['wangshuai'], r['final_xiyong'], r.get('direction_fusion')
        base = dict(pillars=p, tag=r['tag'], share=w['ratio_share_f_exact'])
        if .4 <= w['ratio_share_f_exact'] < .6 and d and d['fuyi_priority'] != 'reduced':
            hit('middle_share_normal_weight', index, dict(base,
                preference=r['xiyong_wangshuai']['strength_of_preference'],
                priority=d['fuyi_priority'] if d else None))
        if f['effective_source'] == 'ordinary_structure_fallback':
            prefs = f['fuyi_stem_preferences']
            if any(WUXING_GAN[x['gan']] not in f['favored'] for x in prefs['ranked_gans']):
                hit('fallback_preferences_raw_route', index, dict(base,
                    final_favored=f['favored'], raw_favored=r['xiyong_wangshuai']['favored'],
                    preferences=prefs))
        for plan in r['luck_plans']:
            if plan.get('remaining', 0) > 0 and not plan.get('candidate_gans'):
                hit('remaining_plan_no_candidate_gan', index, dict(base, plan=plan))
        if not d:
            continue
        for row in d['candidates']:
            evidence = dict(base, wuxing=row['wuxing'], support=row['support'],
                qualified=row['qualified_support'], compatibility=row['compatibility'])
            if row['intersection'] and len(row['qualified_support']) < 2:
                hit('intersection_without_current_consensus', index, evidence)
            if row['structural_conflicts'] and row['compatibility'] == 'direction_agreement':
                hit('agreement_with_structural_conflicts', index, dict(evidence,
                    conflicts=[x['name'] for x in row['structural_conflicts']]))
        for row in d['stem_ranking']:
            if row['exact_support_count'] > len([x for x in row['qualified_support'] if x != 'fuyi']):
                hit('exact_support_includes_latent', index, dict(base, gan=row['gan'],
                    count=row['exact_support_count'], qualified=row['qualified_support']))
            if row['conditions'] and any('：' not in x for x in row['conditions']) and any(x.get('current_support') for x in row['source_records']):
                hit('mixed_source_conditions_flattened', index, dict(base, gan=row['gan'],
                    conditions=row['conditions'], sources=[dict(source=x['source'],
                    current_support=x['current_support']) for x in row['source_records']]))
        if any(row.get('cutoff_tie') for row in d['stem_ranking']) and not f.get('unselected_gans'):
            hit('stem_cutoff_tie_not_displayed', index, base)

    output = dict(sample_count=len(cases), statistics=dict(stats),
        affected_cases={key: len(value) for key, value in case_sets.items()}, examples=examples,
        note='记录数与盘数分列；诊断字段不一致不自动表示排序错误；不作为命理准确率。')
    (ROOT / 'validation/fuyi_cross_layer_v7_audit.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(statistics=output['statistics'], affected_cases=output['affected_cases']), ensure_ascii=False))


if __name__ == '__main__':
    main()
