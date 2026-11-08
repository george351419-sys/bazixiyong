import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bazi_core.engine import analyze
root=Path(__file__).resolve().parents[1];rows=[]
for c in json.loads((root/'tests/fixtures/calendar_360.json').read_text())['cases']:
 p=c['pillars'];chart=dict(gans=[x[0] for x in p],zhis=[x[1] for x in p])
 old=analyze(chart,config={'symmetric_root_discount':False});new=analyze(chart)
 def view(r):return dict(tag=r['tag'],F=r['wangshuai']['F'],K=r['wangshuai']['K'],share=r['wangshuai']['ratio_share_f'])
 rows.append(dict(pillars=p,old=view(old),new=view(new)))
changes=[r for r in rows if r['old']['tag']!=r['new']['tag']]
report=dict(count=len(rows),changed_count=len(changes),changes=changes,cases=rows,note='行为迁移，不是独立命理准确率；不刷新旧基线')
(root/'validation/root_discount_migration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('案例',len(rows),'标签变化',len(changes))
