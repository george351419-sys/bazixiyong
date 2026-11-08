"""360盘初版方向参数描述统计；不是独立命理验证。"""
import sys,json,hashlib
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bazi_core.engine import analyze
from bazi_core.direction_fusion import PARAMETERS,VERSION
root=Path(__file__).resolve().parents[1]
source=root/'tests/fixtures/calendar_360.json'
cs=json.loads(source.read_text())['cases'];rows=[];vs={k:[] for k in ['fire','water','support']}
for c in cs:
    p=c['pillars'];r=analyze(dict(gans=[x[0] for x in p],zhis=[x[1] for x in p]));w=r['wangshuai'];e=w['climate_energy_raw'];t=sum(e.values());d=r['direction_fusion']
    for k,v in [('fire',e['火']/t),('water',e['水']/t),('support',w['ratio_share_f'])]:vs[k].append(v)
    rows.append(dict(pillars=p,direction=d,strict_status=r['arbitration']['decision_status']))
quantiles={k:{str(q):round(sorted(v)[int((len(v)-1)*q)],4) for q in [.1,.25,.5,.75,.9]} for k,v in vs.items()}
assert all(len(x['direction']['favored_gans'])<=6 and len(x['direction']['favored'])<=3 for x in rows if x['direction'])
report=dict(version=VERSION,parameters=PARAMETERS,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    caveat='同一算法冻结行为样本的描述统计；不作为独立验证、准确率或参数最优性证据。',
    quantiles=quantiles,count=len(rows),direction_count=sum(x['direction'] is not None for x in rows),
    primary_counts=dict(Counter(x['direction']['primary_wuxing'] for x in rows if x['direction'])),
    severity_counts=dict(Counter(x['direction']['climate_proxy']['severity'] for x in rows if x['direction'])),cases=rows)
(root/'validation/direction_fusion_v3_cases.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='cases'},ensure_ascii=False,indent=2))
