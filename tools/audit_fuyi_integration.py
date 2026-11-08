"""扶抑调整后的跨层行为检查；统计不是命理正确率。"""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bazi_core.engine import analyze
from bazi_core.direction_fusion import fuse_direction
root=Path(__file__).resolve().parents[1]
stats=dict(balanced=0,balanced_hard_disliked=0,conditional_promoted=0,unhandled_drug_gap=0);examples={}
for c in json.loads((root/'tests/fixtures/calendar_360.json').read_text())['cases']:
 p=c['pillars'];r=analyze(dict(gans=[x[0] for x in p],zhis=[x[1] for x in p]));d=r.get('direction_fusion');g=r['geju']['xiyong_geju']
 if r['tag'] in ('中和偏弱','中和偏旺'):
  stats['balanced']+=1
  if r['final_xiyong']['disliked']:
   stats['balanced_hard_disliked']+=1;examples.setdefault('balanced',dict(pillars=p,tag=r['tag'],disliked=r['final_xiyong']['disliked']))
 if d:
  for item in g.get('conditional_yong_shen',[]):
   if item.get('shen','')[:1] in d['dimensions']['geju']:
    stats['conditional_promoted']+=1;examples.setdefault('conditional',dict(pillars=p,record=item))
 if not r['luck_plans'] and any(b.get('treatment_status')=='原局有对应药' and any(e.get('remaining',0)>0 for e in b.get('rescue_evidence',[])) for b in g.get('bing_list',[])):
  stats['unhandled_drug_gap']+=1;examples.setdefault('gap',p)
r=analyze(dict(gans=list('庚戊己壬'),zhis=list('午寅酉申')))
g={'ge_category':'八格','xiyong_geju':{'conditional_yong_shen':[{'id':'0:1:丙','shen':'丙（有条件）'}],'selected_records':[{'id':'0:1:丙','gan':'丙'}],'xi_shen_list':['丙（有条件辅助）']}}
d=fuse_direction(r['wangshuai'],g,r['tiaohou'],r['xiyong_wangshuai'],r['arbitration'])
result=dict(count=360,statistics=stats,examples=examples,constructed_conditional_bypass=bool(d and '丙' in d['dimensions']['geju']),note='构造复现与真实冻结四柱试跑分开统计，不作准确率。')
(root/'validation/fuyi_integration_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
