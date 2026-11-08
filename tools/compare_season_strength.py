import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bazi_core.engine import analyze
root=Path(__file__).resolve().parents[1];rows=[]
for c in json.loads((root/'tests/fixtures/calendar_360.json').read_text())['cases']:
 p=c['pillars'];chart=dict(gans=[x[0] for x in p],zhis=[x[1] for x in p])
 a=analyze(chart,config={'seasonal_strength':False});b=analyze(chart)
 w=b['wangshuai'];rows.append(dict(pillars=p,old_tag=a['tag'],new_tag=b['tag'],old_share=a['wangshuai']['ratio_share_f'],new_share=w['ratio_share_f'],inclusive_share=w['seasonal_assessment']['day_stem_diagnostic']['inclusive_share'],seasonal=w['seasonal_assessment']))
report=dict(count=len(rows),tag_changes=sum(x['old_tag']!=x['new_tag'] for x in rows),cases=rows,note='模型迁移与日干敏感性，不是独立领域准确率')
(root/'validation/season_strength_migration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(report['count'],report['tag_changes'])
