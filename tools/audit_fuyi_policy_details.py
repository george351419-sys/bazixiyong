"""direction_v6后续反例审计；不修改生产规则。"""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bazi_core.engine import analyze
from bazi_core.wangshuai import _balance_tag
from bazi_core.direction_fusion import fuse_direction
root=Path(__file__).resolve().parents[1]
stats=dict(latent_unconditional_cases=0,unresolved_disease_records_in_favored=0,unresolved_disease_cases_in_favored=0,element_cutoff_ties=0,unannotated_disease_records=0,unannotated_cutoff_ties=0);examples={}
for c in json.loads((root/'tests/fixtures/calendar_360.json').read_text())['cases']:
 p=c['pillars'];r=analyze(dict(gans=[x[0] for x in p],zhis=[x[1] for x in p]));d=r.get('direction_fusion')
 if not d:continue
 if any(s['role']=='latent' and s['condition_status']=='unconditional' for s in d['candidate_records']):stats['latent_unconditional_cases']+=1
 found=False
 for b in r['geju']['xiyong_geju'].get('bing_list',[]):
  remaining=sum(e.get('remaining',0) for e in b.get('rescue_evidence',[]))
  if b.get('affects_ge') and remaining>0 and any(s[:1] in d['favored_gans'] for s in b.get('bing_shen',[])):
   stats['unresolved_disease_records_in_favored']+=1;found=True
   matching={s[:1] for s in b.get('bing_shen',[]) if s[:1] in d['favored_gans']}
   if not any(row.get('structural_conflicts') for row in d['stem_ranking'] if row['gan'] in matching):stats['unannotated_disease_records']+=1
   examples.setdefault('disease',dict(pillars=p,bing=b['name'],favored=d['favored_gans'],remaining=remaining))
 stats['unresolved_disease_cases_in_favored']+=int(found)
 rows=d['candidates']
 if len(rows)>3 and rows[2]['ranking_key']==rows[3]['ranking_key']:
  stats['element_cutoff_ties']+=1
  if not rows[2].get('cutoff_tie') or not rows[3].get('cutoff_tie'):stats['unannotated_cutoff_ties']+=1
  examples.setdefault('cutoff',dict(pillars=p,ranking=[(x['wuxing'],x['ranking_key']) for x in rows]))
p='甲子 戊辰 甲申 己丑'.split();c=dict(gans=[x[0] for x in p],zhis=[x[1] for x in p]);a=analyze(c);b=analyze(c,config={'include_day_stem':False})
examples['transformed_day_diagnostic']=dict(pillars=p,actual_included=a['wangshuai']['ratio_share_f_exact'],predicted_included_from_excluded=b['wangshuai']['seasonal_assessment']['day_stem_diagnostic']['inclusive_share'])
examples['float_boundary']=dict(F=.6*.1,K=.4*.1,ratio=repr((.6*.1)/(.4*.1)),tag=_balance_tag((.6*.1)/(.4*.1),None),intended='身旺')
r=analyze(dict(gans=list('庚戊己壬'),zhis=list('午寅酉申')));w=dict(r['wangshuai'],tag='身弱',month_zhi='寅')
d=fuse_direction(w,{'ge_category':'八格','xiyong_geju':{'xi_shen_list':['丙（辅助）','丁（辅助）']}},{'ok':True,'zhuyong':'丁','yongshen':['丁','丙']},{'favored':['火','土'],'disliked':[]},r['arbitration'])
examples['spring_priority_constructed']=[dict(gan=x['gan'],key=x['ranking_key'],fuyi=x['fuyi_preference']) for x in d['stem_ranking'] if x['gan'] in '丙丁']
report=dict(count=360,statistics=stats,examples=examples,note='构造反例与360盘实际输出分开记录；命中不代表已证明所有用神结论错误。')
(root/'validation/fuyi_policy_detail_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(stats,ensure_ascii=False))
