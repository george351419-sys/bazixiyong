"""方向融合：结构化来源、共识与季节取舍；不认证实际药效。"""
from . import metadata as M
VERSION='direction_v7_conditions_conflicts'
from .fuyi_policy import MINIMUM_SUPPORT,PROBE_AMOUNT,BALANCED_FUYI_WEIGHT,reduced_fuyi
PARAMETERS=dict(low_share=.10,extreme_share=.35,minimum_support=MINIMUM_SUPPORT,probe_amount=PROBE_AMOUNT)


def _gan(record):
    if isinstance(record,dict):
        if record.get('gan') in M.GAN_LIST:return record['gan']
        identity=record.get('id','').split(':')[-1]
        if identity in M.GAN_LIST:return identity
        record=record.get('shen','')
    return record[0] if isinstance(record,str) and record and record[0] in M.GAN_LIST else None


def candidate_records(gx):
    """文本只在入口兼容转换一次；条件身份覆盖结构、辅助和潜在入口。"""
    blocked={_gan(r) for r in gx.get('conditional_yong_shen',[])}-{None}
    specs=[('selected_records','selected_remedy_candidate',3),('structure_primary','structure_primary',3),
           ('structure_secondary','structure_secondary',2),('xi_shen_list','auxiliary',2),
           ('potential_yong_shen','latent',1),('latent_hidden_yong_shen','latent',1)]
    result=[];seen=set()
    for field,role,grade in specs:
        for record in gx.get(field,[]):
            g=_gan(record)
            if not g or g in blocked or (g,role) in seen:continue
            seen.add((g,role));result.append(dict(gan=g,wuxing=M.WUXING_GAN[g],dimension='geju',
                role=role,grade=grade,source=field,source_record=record,condition_status='waiting_visibility' if role=='latent' else 'unconditional',current_support=role!='latent',conditions=['待透或待运，需重新核验作用'] if role=='latent' else []))
    return result,sorted(blocked,key=M.GAN_LIST.index)


def _policy_key(support,roles,priority,balanced,structural=0,fuyi_preference=(0,0)):
    core=sum(d in support for d in ('geju','tiaohou'))
    tier=3 if core==2 else 2 if core==1 and 'fuyi' in support and not balanced else 1 if core else 0
    weight=sum(BALANCED_FUYI_WEIGHT if balanced and d=='fuyi' else 1 for d in support)
    key=[structural,tier]
    for d in priority:
        key.append(roles.get(d,0))
        if d=='fuyi':key.extend(fuyi_preference)
    return key+[weight]


def structural_conflicts(gx):
    result=[]
    for disease in gx.get('bing_list',[]):
        evidence=[e for e in disease.get('rescue_evidence',[]) if isinstance(e.get('remaining'),(int,float)) and e['remaining']>0]
        if not evidence:continue
        for gan in dict.fromkeys(_gan(x) for x in disease.get('bing_shen',[])):
            if gan:
                result.append(dict(gan=gan,wuxing=M.WUXING_GAN[gan],name=disease.get('name'),
                    affects_ge=disease.get('affects_ge',False),target_evidence=evidence,
                    current_remaining=sum(e['remaining'] for e in evidence),
                    scope='原局未解决问题，不直接推定未来增量效果',
                    condition='若选用此字，须复核是否加重本问题或有其他救应',
                    automatically_rejected=False))
    return result


def assign_ties(rows,limit):
    last=None;rank=0
    for i,row in enumerate(rows):
        if row['ranking_key']!=last:rank=i+1;last=row['ranking_key']
        row.update(rank=rank,tie_group='rank:'+str(rank),selected=i<limit)
        row['selection_note']='名额内展示；同分不代表更优' if i<limit else '超出展示数量，未据此判忌'
    if len(rows)>limit and rows[limit-1]['ranking_key']==rows[limit]['ranking_key']:
        group=rows[limit]['tie_group']
        for row in rows:
            if row['tie_group']==group:row['cutoff_tie']=True
    return rows


def fuse_direction(ws,geju,th,fuyi,arbitration):
    if arbitration.get('mode')!='incomplete' or arbitration.get('fact_validation',{}).get('status')!='valid':return None
    if geju.get('ge_category')=='外格' or ws['tag'] in ('从强','从弱','假从强','假从弱'):return None
    season=next(s for s,z in [('春','寅卯辰'),('夏','巳午未'),('秋','申酉戌'),('冬','亥子丑')] if ws['month_zhi'] in z)
    priority=['tiaohou','geju','fuyi'] if season in ('冬','夏') else ['geju','fuyi','tiaohou']
    balanced=reduced_fuyi(ws)
    if balanced:priority=[d for d in priority if d!='fuyi']+['fuyi']
    gx=geju.get('xiyong_geju',{});sources,blocked=candidate_records(gx)
    tc=list(dict.fromkeys((th.get('xiyong') or {}).get('favored_effective',th.get('yongshen',[])))) if th.get('ok') else []
    for g in tc:
        if g in M.GAN_LIST:sources.append(dict(gan=g,wuxing=M.WUXING_GAN[g],dimension='tiaohou',role='primary' if g==th.get('zhuyong') else 'secondary',grade=3 if g==th.get('zhuyong') else 2,source='tiaohou.favored_effective',condition_status='general_or_triggered',current_support=True))
    dims=dict(geju=list(dict.fromkeys(r['gan'] for r in sources if r['dimension']=='geju')),tiaohou=tc,fuyi=fuyi.get('favored',[]))
    conflicts=structural_conflicts(gx)
    primary={r['gan'] for r in sources if r['role']=='structure_primary'};secondary={r['gan'] for r in sources if r['role']=='structure_secondary'}
    def structural(gs):return (2 if primary.intersection(gs) else 1 if secondary.intersection(gs) else 0) if priority[0]=='geju' and primary else 0
    energy=ws.get('climate_energy_raw',ws.get('climate_energy',{}));total=sum(energy.values()) or 1
    shares={w:energy.get(w,0)/total for w in M.WUXING_LIST};p=PARAMETERS
    urgent=(season=='冬' and shares['火']<p['low_share'] and shares['水']>=p['extreme_share']) or (season=='夏' and shares['水']<p['low_share'] and shares['火']>=p['extreme_share'])
    share=ws.get('ratio_share_f_exact',ws.get('ratio_share_f',.5));rows=[]
    for wx in M.WUXING_LIST:
        src=[r for r in sources if r['wuxing']==wx];roles={d:max([r['grade'] for r in src if r['dimension']==d] or [0]) for d in ('geju','tiaohou')}
        roles['fuyi']=1 if wx in dims['fuyi'] else 0
        support=[d for d in priority if roles[d]]
        if not support:continue
        gs=list(dict.fromkeys(r['gan'] for r in src));against=['fuyi'] if wx in fuyi.get('direction_opposition',fuyi.get('disliked',[])) else []
        helps=wx==ws['day_wuxing'] or M.SHENG[wx]==ws['day_wuxing'];after=(share+(p["probe_amount"] if helps else 0))/(1+p["probe_amount"])
        qualified=[d for d in support if d=='fuyi' or any(r['dimension']==d and r.get('current_support',True) for r in src)]
        key=_policy_key(qualified,roles,priority,balanced,structural(gs))
        # 真实药效不从结构主用推导；代理仅告知限制，不拥有否决政策的资格。
        allocations=gx.get('treatment_allocations',[])
        realized=[a for a in allocations if a.get('power',0)>0 and str(a.get('drug_id','')).split(':')[-1] in gs]
        rows.append(dict(wuxing=wx,gans=gs,support=support,against=against,fuyi_caution=bool(against),intersection=len(qualified)>=2,
            ranking_key=key,roles=roles,source_records=src,qualified_support=qualified,structural_conflicts=[x for x in conflicts if x["wuxing"]==wx],
            bearing=dict(support_before=share,support_after=round(after,4),status='supported' if helps else 'limited' if after<p['minimum_support'] else 'tolerable_proxy',method='normalized_share_probe',not_actual_dose=True),
            repair=dict(status='realized_treatment' if realized else 'not_established',realized=bool(realized),allocations=realized),
            conflict_score=(len(against)+int(any(x['wuxing']==wx for x in conflicts)))/max(1,len(support)+len(against)+1),compatibility='direction_conflict' if against or any(x['wuxing']==wx for x in conflicts) else 'direction_agreement' if len(qualified)>=2 else 'single_dimension'))
    rows.sort(key=lambda r:(tuple(-v for v in r['ranking_key']),M.WUXING_LIST.index(r['wuxing'])))
    if not rows:return None
    assign_ties(rows,3)
    stems=rank_stems(rows,dims,priority,sources,ws,balanced,structural)
    accepted=rows[:3]
    primary_gans=[r['gan'] for r in stems if r['rank']==1]
    primary_elements=[r['wuxing'] for r in rows if r['rank']==1]
    cutoff_gans=[r['gan'] for r in stems[6:] if r.get('cutoff_tie')]
    caution=list(dict.fromkeys([x['wuxing'] for x in conflicts]+[r['wuxing'] for r in rows if r['against']]+[w for w in fuyi.get('direction_opposition',fuyi.get('disliked',[])) if w not in [r['wuxing'] for r in accepted]]))
    return dict(version=VERSION,decision_status='heuristic',scope='direction_only',season=season,priority=priority,
        fuyi_priority='reduced' if balanced else 'normal',fuyi_support_weight=BALANCED_FUYI_WEIGHT if balanced else 1.,parameters=dict(p),
        climate_proxy=dict(severity='urgent' if urgent else 'seasonal' if season in ('冬','夏') else 'ordinary',shares=shares),
        dimensions=dims,candidate_records=sources,structural_conflicts=conflicts,conditional_geju_gans=blocked,tiaohou_avoid_pending_review=(th.get('xiyong') or {}).get('disliked',[]),candidates=rows,stem_ranking=stems[:6],
        stem_candidates=stems,unselected_gans=[r['gan'] for r in stems[6:]],favored_gans=[r['gan'] for r in stems[:6]],restricted_candidates=rows[3:],unselected=[r['wuxing'] for r in rows[3:]],
        primary_gans=primary_gans,primary_status='tied' if len(primary_gans)>1 else 'unique' if primary_gans else 'empty',cutoff_tied_gans=cutoff_gans,primary_wuxings=primary_elements,primary_gan=primary_gans[0] if len(primary_gans)==1 else None,primary_wuxing=primary_elements[0] if len(primary_elements)==1 else None,favored=[r['wuxing'] for r in accepted],secondary=[r['wuxing'] for r in accepted[1:]],
        caution=caution,avoid=[],conditional_tiaohou=(th.get('xiyong') or {}).get('pending_conditions',[]),
        warnings=['工程方向规则；扶抑分歧和承受代理不等于已验证的结构失败。']+(['季节极端代理触发；不证明具体药效。'] if urgent else []),action_release_ready=False,domain_validated=False)


def rank_stems(elements,dims,priority,sources,ws,balanced,structural):
    from .fuyi_order import fuyi_order
    prefs={r['gan']:r for r in fuyi_order(ws,dims['fuyi'])['ranked_gans']};records=[]
    for g in M.GAN_LIST:
        wx=M.WUXING_GAN[g];element=next((r for r in elements if r['wuxing']==wx),None)
        if not element:continue
        src=[r for r in sources if r['gan']==g];roles={d:max([r['grade'] for r in src if r['dimension']==d] or [0]) for d in ('geju','tiaohou')};roles['fuyi']=1 if g in prefs else 0
        support=[d for d in priority if roles[d]]
        if not support:continue
        qualified=[d for d in support if d=='fuyi' or any(r['dimension']==d and r.get('current_support',True) for r in src)]
        key=_policy_key(qualified,roles,priority,balanced,structural({g}),prefs.get(g,{}).get('preference_key',[0,0]))
        records.append(dict(gan=g,wuxing=wx,roles=roles,exact_support_count=sum(d in qualified for d in ('geju','tiaohou')),ranking_key=key,
            qualified_support=qualified,conditions=[r['dimension']+'（'+r['source']+'）：'+c for r in src for c in r.get('conditions',[])],structural_conflicts=[x for x in element['structural_conflicts'] if x['gan']==g],source_records=src,evidence=[{'selected_remedy_candidate':'格局已选候选','structure_primary':'格局结构主用','structure_secondary':'格局结构第二用','auxiliary':'格局辅助','latent':'潜在救应','primary':'调候首用','secondary':'调候次用'}[r['role']]+':'+r['source'] for r in src]+(['扶抑支持：'+prefs[g]['shishen']] if g in prefs else []),
            against=element['against'],bearing=element['bearing'],precision='gan_evidence' if src else 'fuyi_rule',fuyi_preference=prefs.get(g),limitation='方向候选，不认证实际药效'))
    records.sort(key=lambda r:(tuple(-x for x in r['ranking_key']),M.GAN_LIST.index(r['gan'])))
    assign_ties(records,6)
    return records
