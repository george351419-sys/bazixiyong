import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bazi_core.engine import analyze
root=Path(__file__).resolve().parents[1];rows=[]
for case in json.loads((root/'tests/fixtures/calendar_360.json').read_text())['cases']:
 p=case['pillars'];c=dict(gans=[x[0] for x in p],zhis=[x[1] for x in p])
 old=analyze(c,config={'include_day_stem':False});new=analyze(c)
 w=new['wangshuai'];rows.append(dict(pillars=p,external_share=w['seasonal_assessment']['external_share'],inclusive_share=w['ratio_share_f'],day_contribution=w['seasonal_assessment']['day_stem_diagnostic']['contribution'],old_tag=old['tag'],new_tag=new['tag'],fuyi_priority=(new.get('direction_fusion') or {}).get('fuyi_priority')))
r=dict(count=len(rows),tag_changes=sum(x['old_tag']!=x['new_tag'] for x in rows),note='两次均用40/50/60门槛，仅比较日干纳入影响；非准确率。',cases=rows)
(root/'validation/day_stem_balance_migration.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(r['count'],r['tag_changes'])
