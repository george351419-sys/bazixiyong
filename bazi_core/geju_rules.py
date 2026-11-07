from .geju_status import State
"""格局共享力量、合去状态和清浊规则。"""
from . import metadata as M


def rescue_fraction(rec, he):
    if not rec['tou']:
        return 0.0
    return max([0.0] + [1.0 if abs(g['idx'][0]-g['idx'][1]) == 1 else .5
        for g in he['he_groups'] if g['type']=='wuhe' and len(g.get('idx', []))==2
        and rec['idx'] in g['idx']])


def record_power(rec, he=None):
    return rec.get('weight', 1 if rec['tou'] else .5) * (1-rescue_fraction(rec, he) if he else 1)


def power(occ, ss, he=None):
    from .geju_treatment import records
    rs=[r for r in records(occ,he or {'he_groups':[]}) if r['ss']==ss]
    stems=[r for r in rs if r['tou']]
    return sum(r['effective'] for r in (stems if stems else rs))


def clean_level(occ, he):
    pairs=[('正官','七杀'),('正印','偏印'),('食神','伤官')]
    mixed=False
    for a,b in pairs:
        ra=[r for r in occ.get(a,[]) if r['tou']]
        rb=[r for r in occ.get(b,[]) if r['tou']]
        if ra and rb:
            mixed=True
            if any(rescue_fraction(r,he)<1 for r in ra) and any(rescue_fraction(r,he)<1 for r in rb):
                return '浊而无去'
    return '浊而能清' if mixed else '清纯'


def resolve_wuhe(he, gans, occ):
    """一字一合；相邻优先，再按两端受冲后力量，最后柱位稳定排序。"""
    candidates = [g for g in he['he_groups'] if g['type']=='wuhe' and len(g.get('idx',[]))==2]
    def rank(g):
        i,j=g['idx']
        strength=sum(r.get('weight',1) for rs in occ.values() for r in rs if r['tou'] and r['idx'] in (i,j))
        return (abs(i-j)!=1,-strength,i,j)
    used=set(); accepted=[]; rejected=[]
    for g in sorted(candidates,key=rank):
        if used.intersection(g['idx']): rejected.append(g)
        else: accepted.append(g);used.update(g['idx'])
    return dict(he,he_groups=[g for g in he['he_groups'] if g['type']!='wuhe']+accepted,
                wuhe_rejected=rejected)


def ke(a,b):
    """有方向的十神生克，官杀/财等同组亦支持。"""
    groups={'正官':'官','七杀':'官','正印':'印','偏印':'印','正财':'财','偏财':'财',
            '食神':'食伤','伤官':'食伤','比肩':'比劫','劫财':'比劫'}
    return {'印':'食伤','财':'印','食伤':'官','官':'比劫','比劫':'财'}.get(groups.get(a,a))==groups.get(b,b)


def effective_occ(occ,he):
    result={}
    for ss,rs in occ.items():
        result[ss]=[]
        for r in rs:
            fraction=rescue_fraction(r,he)
            if r['tou'] and fraction==1: continue
            result[ss].append(dict(r,weight=record_power(r,he),rescue_fraction=fraction))
    return result


def verify_rescue(occ, he, targets, drugs, require_visible=True):
    """兼容旧接口；仅允许真正克制病神的直接治法。生产多病调用使用allocate。"""
    from .geju_treatment import allocate, records
    rules={ss:[("克掉",[d for d in drugs if ke(d,ss)],"直接制伏")] for ss in targets}
    selected=[r for r in records(occ,he) if r['ss'] in drugs and (r['tou'] or not require_visible)]
    diseases=[dict(name=ss,bing_ss=[ss]) for ss in targets]
    statuses,_,_=allocate(occ,he,diseases,selected,rules)
    evidence=[]
    for ss,status in zip(targets,statuses):
        for r in occ.get(ss,[]):
            if not r['tou']: continue
            ident=f"{r['idx']}:1:{r['gan']}"
            remaining=next((e['remaining'] for e in status['evidence'] if e.get('target_id')==ident and 'remaining' in e),record_power(r,he))
            evidence.append(dict(ss=ss,idx=r['idx'],gan=r['gan'],remaining=remaining,
                                 status=State.RESCUED if remaining<=1e-9 else State.PARTIAL if remaining<record_power(r,he) else '未获救'))
    return evidence


def qi_table(gans,zhis,he,eff_hide=None):
    """全局原子气势，包含日主；真实本气1、中余0.5，虚拟阴阳均分。"""
    result={w:0.0 for w in M.WUXING_LIST}
    opposite={'甲':'庚','庚':'甲','乙':'辛','辛':'乙','丙':'壬','壬':'丙','丁':'癸','癸':'丁'}
    for i,g in enumerate(gans):
        w=(he.get('gan_hua') or [None]*4)[i] or M.WUXING_GAN[g]
        result[w]+=.5 if opposite.get(g) in gans else 1
    for i,z in enumerate(zhis):
        factor=.5 if M.CHONG.get(z) in zhis else 1
        hua=he['branch_hua'][i]
        if eff_hide is not None:
            hides=eff_hide[i]
            virtual=type(hides).__name__=='VirtualHide'
            for j,g in enumerate(hides): result[M.WUXING_GAN[g]]+=factor*((1/len(hides)) if virtual else (1 if j==0 else .5))
        elif hua: result[hua]+=factor
        else:
            for j,g in enumerate(M.ZHI_HIDE[z]): result[M.WUXING_GAN[g]]+=factor*(1 if j==0 else .5)
    return result


def blade_metrics(occ,he):
    blade=power(occ,"劫财",he)
    controls=[ss for ss in ("正官","七杀") if any(r['tou'] and record_power(r,he)>0 for r in occ.get(ss,[]))]
    strength=0
    if len(controls)==1:
        tops=[r for r in occ[controls[0]] if r['tou'] and record_power(r,he)>0]
        strength=sum(record_power(r,he) for r in occ[controls[0]] if r['tou'] or any(t['gan']==r['gan'] for t in tops))
        strength-=sum(record_power(r,he) for ss in ('食神','伤官') for r in occ.get(ss,[]) if r['tou'] and any(abs(r['idx']-t['idx'])==1 for t in tops))
    return blade,max(0,strength)
