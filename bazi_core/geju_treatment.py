from .geju_status import State
"""具体柱位候选、治法验证与全盘药力分配。

所有候选、证据都使用柱位ID；组合枚举上限为三个透干（最多8个子集）。
"""
from itertools import combinations, permutations
from .geju_rules import record_power, rescue_fraction, ke

GROUP={'正官':'官','七杀':'官','正印':'印','偏印':'印','正财':'财','偏财':'财',
       '食神':'食伤','伤官':'食伤','比肩':'比劫','劫财':'比劫'}
SHENG={'比劫':'食伤','食伤':'财','财':'官','官':'印','印':'比劫'}


class ResourceBalances(dict):
    """字典值是真正可用余额；保留两份原始账用于审核。"""
    def __init__(self,drug,flow):
        super().__init__((key,min(value,flow.get(key,value))) for key,value in drug.items())
        self.drug_budget=dict(drug)
        self.flow_budget=dict(flow)


def expands(names):
    return {ss for ss,g in GROUP.items() if ss in names or g in names}


def records(occ,he):
    result=[dict(r,ss=ss,id=f"{r['idx']}:{int(r['tou'])}:{r['gan']}",
                 atom_effective=record_power(r,he),effective=record_power(r,he),root_ids=[])
            for ss,rs in occ.items() for r in rs]
    stems=[r for r in result if r['tou'] and r['effective']>0]
    for root in [r for r in result if not r['tou']]:
        owners=[s for s in stems if s['gan']==root['gan']]
        if not owners: continue
        owner=min(owners,key=lambda s:(abs(s['idx']-root['idx']),s['idx']))
        owner['effective']+=root['effective'];owner['root_ids'].append(root['id'])
        root['root_owner_id']=owner['id']
    return result


def near(a,b):
    return a['idx']!=b['idx'] and abs(a['idx']-b['idx'])==1


def sheng_path(start,end,active,budget=None):
    queue=[[start]];found=[]
    while queue:
        path=queue.pop(0)
        if path[-1]['id']==end['id']:
            found.append(path);continue
        for r in active:
            if r['id'] in [p['id'] for p in path]: continue
            if (near(path[-1],r) or {path[-1]['idx'],r['idx']}=={1,3}) and SHENG[GROUP[path[-1]['ss']]]==GROUP[r['ss']]: queue.append(path+[r])
    return max(found,key=lambda path:(min((budget or {}).get(r['id'],r['effective']) for r in path),-len(path),tuple(r['id'] for r in path))) if found else []


def route_chain(method,drug,patient,protected,active,budget=None):
    if method in ('克掉','制伏'): return [patient,drug] if near(patient,drug) and ke(drug['ss'],patient['ss']) else []
    if method=='化掉':
        if near(patient,drug) and SHENG[GROUP[patient['ss']]]==GROUP[drug['ss']] and SHENG[GROUP[drug['ss']]]=='比劫': return [patient,drug]
        return []
    for p in protected:
        tail=sheng_path(drug,p,active,budget)
        if not tail: continue
        if method=='生扶': return [patient]+tail
        if method=='通关':
            head=sheng_path(patient,drug,active,budget)
            if head and len({r['id'] for r in head+tail[1:]})==len(head+tail[1:]): return head+tail[1:]
    return []


def route_valid(method,drug,patient,protected):
    if method in ('克掉','制伏'):
        return ke(drug['ss'],patient['ss'])
    if method=='化掉':
        return SHENG[GROUP[patient['ss']]]==GROUP[drug['ss']] and SHENG[GROUP[drug['ss']]]=='比劫'
    if method=='通关':
        return (SHENG[GROUP[patient['ss']]]==GROUP[drug['ss']] and
                any(SHENG[GROUP[drug['ss']]]==GROUP[p['ss']] and near(drug,p) for p in protected))
    if method=='生扶':
        return any(SHENG[GROUP[drug['ss']]]==GROUP[p['ss']] and near(drug,p) for p in protected)
    return False


def _allocate_ordered(occ,he,diseases,selected,rules,ge_ss=None):
    """一次全盘分配；同一病字被多个病名引用时共享同一份已验证证据。"""
    all_records=sorted(records(occ,he),key=lambda r:r['id'])
    stems=[r for r in all_records if r['tou'] and r['effective']>0]
    capacity={d['id']:max(0,d['effective']-sum(x['effective'] for x in stems
                  if near(x,d) and ke(x['ss'],d['ss']))) for d in selected}
    allocations=[];statuses=[];cache={}
    flow_capacity={r['id']:r['effective'] for r in stems}
    for b in diseases:
        methods=rules.get(b['name'],[])
        if b['name']=='阳刃无制':
            from .geju_rules import blade_metrics
            blade,control=blade_metrics(occ,he)
            demand=blade*b.get('blade_control_ratio',1.0)
            relief=min(demand,control)
            evidence=[dict(target_id='structure:阳刃无制',blade_power=blade,control_power=control,
                initial_demand=demand,relief_realized=relief,remaining=max(0,demand-relief),
                execution_status='realized',demand_method='制刃',
                demand_basis='blade_metrics × blade_control_ratio')]
            statuses.append(dict(name=b['name'],status=State.CORRESPONDING if control>0 else State.NO_DRUG,evidence=evidence,strength_check='未通过',reason='已透官杀制力不足，需补足制刃力量' if control>0 else '无有效官杀制刃'))
            continue
        targets=[r for r in stems if r['ss'] in b['bing_ss'] and ('target_ids' not in b or r['id'] in b['target_ids'])]
        if b['name']=='财多官埋': targets=[r for r in stems if GROUP[r['ss']]=='财']
        protected=[r for r in stems if r['ss']==ge_ss or r['ss']==b.get('target')]
        if b['name']=='伤官见官': protected=[r for r in stems if r['ss']=='正官']
        if b['name']=='比劫夺财': protected=[r for r in stems if GROUP[r['ss']]=='财']
        if b['name']=='枭印夺食': protected=[r for r in stems if r['ss']=='食神']
        if b['name']=='财来坏印': protected=[r for r in stems if GROUP[r['ss']]=='印']
        evidence=[]
        for patient in targets:
            need=patient['effective'];used_total=0;direct_relief=0;strength_gain=0
            if any(method=='生扶' for method,_,_ in methods):
                total=sum(t['effective'] for t in targets)
                baseline=sum(p['effective'] for p in protected)
                need=max(0,total-baseline)*patient['effective']/total if total else 0
            initial_demand=need
            demand_method='生扶' if any(m=='生扶' for m,_,_ in methods) else '直接处理'
            for priority,(method,names,_) in enumerate(methods):
                for d in selected:
                    if d['ss'] not in expands(names): continue
                    chain_records=route_chain(method,d,patient,protected,stems,flow_capacity)
                    if not chain_records: continue
                    action=(patient['id'],d['id'],method,tuple(r['id'] for r in chain_records))
                    if action in cache:
                        original_evidence=cache[action]
                        used=min(need,original_evidence['power']);need-=used;used_total+=used
                        if method in ('克掉','制伏'): direct_relief+=used
                        if method=='生扶': strength_gain+=used
                        evidence.append(dict(original_evidence,power=used,reused_evidence=True,evidence_ref=original_evidence['evidence_id']))
                        continue
                    flow_nodes=[r for r in chain_records if r['id'] not in (patient['id'],d['id'])]
                    limit=min([capacity[d['id']],flow_capacity[d['id']]]+[flow_capacity[r['id']] for r in flow_nodes]) if method in ('通关','化掉','生扶') else min(capacity[d['id']],flow_capacity[d['id']])
                    used=min(need,limit);need-=used;used_total+=used
                    if method in ('通关','化掉','生扶'):
                        for node in flow_nodes: flow_capacity[node['id']]-=used
                    if used:
                        capacity[d['id']]-=used;flow_capacity[d['id']]-=used
                        if method in ('克掉','制伏'): direct_relief+=used
                        if method=='生扶': strength_gain+=used
                        chain=[r['id'] for r in chain_records]
                        if method=='化掉': chain.append('day_master')
                        entry=dict(target_id=patient['id'],drug_id=d['id'],method=method,power=used,priority=priority,chain=chain,
                                   effect='降低病神作用力' if method in ('克掉','制伏') else '承接冲突流量' if method in ('通关','化掉') else '增加保护对象力量')
                        entry['evidence_id']='action:'+':'.join((patient['id'],d['id'],method,','.join(chain)))
                        cache[action]=entry
                        evidence.append(entry);allocations.append(entry)
            full=need<=1e-9
            evidence.append(dict(target_id=patient['id'],remaining=need,initial_demand=initial_demand,demand_method=demand_method,relief_realized=used_total,disease_power=max(0,patient['effective']-direct_relief),protected_gain=strength_gain,check='力量检查通过' if full else '力量检查未通过'))
        # 结构性病使用专属条件，不虚构单一病字。
        structural=False
        if b['name']=='财露无官杀':
            wealth=[r for r in stems if GROUP[r['ss']]=='财' and r['effective']>0]
            for d in selected:
                if not wealth or GROUP[d['ss']]!='官' or min(capacity[d['id']],flow_capacity[d['id']])<1: continue
                if not all(near(d,w) for w in wealth): continue
                capacity[d['id']]-=1;flow_capacity[d['id']]-=1
                entry=dict(target_id='structure:财露无官杀',drug_id=d['id'],method='护财',power=1,priority=0,chain=[d['id']]+[w['id'] for w in wealth],effect='保护财星',evidence_id='guard:'+d['id'])
                evidence.append(entry);allocations.append(entry);structural=True
                break
        elif b['name'] in ('财多官埋','印过旺'):
            group='财' if b['name']=='财多官埋' else '印'
            load=sum(r.get('atom_effective',r['effective']) for r in all_records if GROUP[r['ss']]==group)
            relief=sum(e.get('power',0) for e in evidence if e.get('method') in ('克掉','制伏'))
            structural=load-relief<3 and relief>0
        is_structural=b['name'] in ('财露无官杀','财多官埋','印过旺')
        full=structural if is_structural else (bool(targets) and all(e.get('remaining',0)<=1e-9 for e in evidence))
        corresponding=any(d['ss'] in expands(names) for _,names,_ in methods for d in selected)
        if full and not any(e.get('power',0)>0 for e in evidence): state=State.BALANCED
        elif full: state=State.RESCUED
        elif any(e.get('power',0)>0 for e in evidence): state=State.PARTIAL
        elif corresponding: state=State.CORRESPONDING
        else: state=State.NO_DRUG
        statuses.append(dict(name=b['name'],status=state,evidence=evidence,
                             strength_check='通过' if full else '未通过'))
    return statuses,allocations,ResourceBalances(capacity,flow_capacity)


def allocate(occ,he,diseases,selected,rules,ge_ss=None):
    """穷举病字组与药字的分配先后，返回稳定的最优分配。"""
    if not diseases: return [],[],{d['id']:d['effective'] for d in selected}
    groups={}
    for disease in sorted(diseases,key=lambda d:(d['name'],tuple(d['bing_ss']))):
        key=tuple(sorted(disease['bing_ss'])) or (disease['name'],)
        groups.setdefault(key,[]).append(disease)
    best=None
    for order in permutations(sorted(groups)):
        ordered=[d for key in order for d in groups[key]]
        for drugs in permutations(sorted(selected,key=lambda d:d['id'])):
            result=_allocate_ordered(occ,he,ordered,drugs,rules,ge_ss)
            states,actions,capacity=result
            score=(sum(x['status'] in (State.RESCUED,State.BALANCED) for x in states),sum(x.get('power',0) for x in actions),
                   -sum(x.get('priority',0) for x in actions))
            if best is None or score>best[0]: best=(score,ordered,result)
    _,ordered,(states,actions,capacity)=best
    # 返回顺序始终跟随调用者，分配结论不依赖调用者遍历顺序。
    lookup={id(d):state for d,state in zip(ordered,states)}
    return [lookup[id(d)] for d in diseases],actions,capacity


def solve(ctx,diseases,rules,allowed_ss):
    occ=ctx['occ'];he=ctx['he'];all_records=records(occ,he)
    candidates=[r for r in all_records if r['effective']>0 and r['ss'] in allowed_ss]
    visible=[r for r in candidates if r['tou']]
    targets={ss for b in diseases for ss in b['bing_ss']}
    def compatible(combo):
        protect=[r for r in all_records if r['tou'] and r['effective']>0 and
                 r['ss']==ctx.get('ge_ss') and r['ss'] not in targets and
                 r['ss'] in ('正官','正财','偏财','正印','食神')]
        if any(near(d,p) and ke(d['ss'],p['ss']) for d in combo for p in protect): return False
        return not any(near(a,b) and (ke(a['ss'],b['ss']) or ke(b['ss'],a['ss']))
                       for a,b in combinations(combo,2))
    best=None
    alternatives=[]
    for size in range(len(visible)+1):
        for combo in combinations(visible,size):
            if not diseases and len(combo)>1: continue
            if not compatible(combo): continue
            statuses,allocations,capacity=allocate(occ,he,diseases,combo,rules,ctx.get('ge_ss'))
            contributing={e['drug_id'] for e in allocations}
            contributing.update(node for e in allocations for node in e.get('chain',[]))
            if diseases and any(d['id'] not in contributing for d in combo): continue
            # 同等治疗覆盖时先选择必要简洁的组合，再按治法与力量裁决。
            priority=sum(next((i for i,(_,names,_) in enumerate(rules.get(b['name'],[])) if d['ss'] in expands(names)),99)
                         for b in diseases for d in combo)
            score=(sum(s['status'] in (State.RESCUED,State.BALANCED) for s in statuses),sum(e['power'] for e in allocations),
                   -size,-priority,sum(d['effective'] for d in combo))
            if not diseases:
                rank=ctx.get('route_priority',{})
                score=(-min((rank.get(d['ss'],99) for d in combo),default=999),
                       max((d['effective'] for d in combo),default=0),-size)
            alternatives.append((score,combo,statuses,allocations,capacity))
            if best is None or score>best[0]: best=(score,combo,statuses,allocations,capacity)
    _,combo,statuses,allocations,capacity=best
    chosen={d['id'] for d in combo}
    aux_allowed=set(ctx.get('auxiliary_ss',())) | allowed_ss
    remaining=[d for d in all_records if d['tou'] and d['effective']>0 and
               d['ss'] in aux_allowed and d['ss'] not in targets and d['id'] not in chosen]
    auxiliary=()
    aux_score=(-1,)
    for size in range(len(remaining)+1):
        for subset in combinations(remaining,size):
            if compatible(tuple(combo)+subset):
                score=(sum(d['effective'] for d in subset),len(subset))
                if score>aux_score: auxiliary=subset;aux_score=score
    auxiliary=list(auxiliary)
    alternate=[d for d in remaining if d not in auxiliary]
    return dict(selected=list(combo),auxiliary=auxiliary,alternatives=alternate,statuses=statuses,allocations=allocations,
                remaining_capacity=capacity,drug_budget=getattr(capacity,'drug_budget',dict(capacity)),flow_budget=getattr(capacity,'flow_budget',dict(capacity)),candidates=candidates)
