"""真从格顺势分流，复用旺衰验真与格局取用结果。"""
from copy import deepcopy
from . import metadata as M


def _root_contract(ws, info):
    """核对上游证据合同，不在仲裁层复制从格阈值或辨根算法。"""
    roots = ws.get("effective_roots")
    evidence = info.get("root_evidence")
    if not isinstance(roots, list) or not isinstance(evidence, list):
        return False
    def signature(items, broken_key):
        result = []
        for item in items:
            if (not isinstance(item, dict) or type(item.get("branch_index")) is not int
                    or item["branch_index"] not in range(4)
                    or type(item.get(broken_key)) is not bool
                    or not isinstance(item.get("root_type"), str)):
                return None
            result.append((item["branch_index"], item["root_type"], item[broken_key]))
        return sorted(result)
    actual = signature(roots, "is_broken")
    stated = signature(evidence, "broken")
    return actual is not None and actual == stated



def blocked(reason,message):
    return dict(mode='external',decision_status='pending',reason_code=reason,positions=[],
        favored=[],avoid=[],conditional_avoid=[],release_ready=False,
        blocking_missing_evidence=[reason],priority_reason=message)


def true_cong_verdict(facts):
    ws,geju=facts['ws'],facts['geju'];info=ws.get('cong_info',{})
    name=geju.get('special_ge') or geju.get('main_ge_name','')
    if geju.get('ge_category')!='外格' or '从' not in name or '专旺' in name: return None
    if (info.get('is_cong') is not True or info.get('is_fake_cong') is True
            or ws.get('tag') not in ('从弱','从强') or geju.get('ge_status')!='成格'):
        return blocked('true_cong_structure_conflict','从格标记与旺衰验真矛盾，暂停裁决。')
    if ('从强' in name and ws['tag']!='从强') or ('从弱' in name and ws['tag']!='从弱') or (any(k in name for k in ('从财','从杀','从儿')) and ws['tag']!='从弱'):
        return blocked('true_cong_structure_conflict','从格方向与旺衰标签不一致。')
    if not _root_contract(ws,info):
        reason='true_cong_evidence_missing' if not isinstance(info.get('root_evidence'),list) or not isinstance(ws.get('effective_roots'),list) else 'true_cong_evidence_conflict'
        return blocked(reason,'真从逐根证据缺失或矛盾，暂停最终裁决。')
    return _selection_verdict(facts,'cong')


def special_structure_verdict(facts):
    geju=facts['geju'];ws=facts['ws']
    if geju.get('ge_category')!='外格': return None
    name=geju.get('special_ge') or geju.get('main_ge_name','')
    kind='hua' if name.startswith('化') else 'zhuanwang' if '专旺' in name else 'two_elements' if '两气成象' in name else 'cong' if '从' in name else 'unknown'
    if kind=='cong': return true_cong_verdict(facts)
    witness=geju.get('structure_evidence',{})
    if (not isinstance(witness,dict) or witness.get('source')!='geju._screen_special_ge'
            or witness.get('kind')!=kind or witness.get('name')!=name or witness.get('matched') is not True
            or geju.get('ge_status')!='成格'):
        return blocked('special_structure_evidence_missing','特殊结构缺少上游验真依据，暂停裁决。')
    if kind=='hua':
        hua=ws.get('he_detail',{}).get('gan_hua',[])
        if len(hua)!=4 or hua[2]!=witness.get('day_hua') or not hua[2] or witness.get('day_isolated') is not True:
            return blocked('special_structure_conflict','化气证据与日主合化状态不一致。')
    elif kind=='zhuanwang':
        if ws.get('tag')!='从强' or ws.get('cong_info',{}).get('is_cong') is not True or not _root_contract(ws,ws['cong_info']):
            return blocked('special_structure_conflict','专旺缺少旺衰真从强证据。')
    elif kind=='two_elements':
        if witness.get('pair')!=[w for w in M.WUXING_LIST if w in name] or len(witness['pair'])!=2:
            return blocked('special_structure_conflict','两气成象主体证据不一致。')
    else: return blocked('special_structure_unknown','未支持的特殊结构。')
    return _selection_verdict(facts,kind)


def _selection_verdict(facts,kind):
    geju=facts['geju']
    def invalid(field):
        reason='true_cong_invalid_selection' if kind=='cong' else 'special_invalid_selection'
        return dict(mode='external',decision_status='pending',reason_code=reason,
            positions=[],favored=[],avoid=[],conditional_avoid=[],release_ready=False,
            blocking_missing_evidence=['invalid_selection:'+field],
            priority_reason='真从取用字段缺失或非法，暂停裁决。')
    xy=geju.get('xiyong_geju',{})
    if not isinstance(xy,dict): return invalid('xiyong_geju')
    primary=xy.get('special_yong_wuxing',[])
    secondary=xy.get('special_xi_wuxing',[])
    if not isinstance(primary,list) or not isinstance(secondary,list) or not primary:
        return invalid('favored')
    if any(w not in M.WUXING_LIST for w in primary+secondary): return invalid('favored')
    if kind=='hua' and primary[0]!=geju['structure_evidence']['day_hua']: return invalid('hua_direction')
    if kind=='zhuanwang' and primary[0]!=facts['ws']['day_wuxing']: return invalid('zhuanwang_direction')
    if kind=='two_elements' and any(w not in geju['structure_evidence']['pair'] for w in primary+secondary): return invalid('two_element_direction')
    favored=list(dict.fromkeys(primary+secondary))
    avoided=xy.get('special_ji_wuxing')
    if not isinstance(avoided, list) or any(w not in M.WUXING_LIST for w in avoided):
        return invalid('special_ji_wuxing')
    conditional=deepcopy(xy.get('conditional_ji_shen'))
    if not isinstance(conditional,list): return invalid('conditional_ji_shen')
    for item in conditional:
        if (not isinstance(item,dict) or item.get('wuxing') not in M.WUXING_LIST
                or not isinstance(item.get('condition'),str) or not item['condition'].strip()
                or 'triggered' not in item
                or (item.get('triggered') is not None and type(item['triggered']) is not bool)):
            return invalid('conditional_ji_shen')
        item['decision_status'] = ('triggered' if item.get('triggered') is True else
                                  'not_triggered' if item.get('triggered') is False else 'pending')
        item['condition_evaluation_mode']='upstream_verified' if item['triggered'] is not None else 'manual_review'
        item['evidence_ref']='geju.xiyong_geju.conditional_ji_shen'
    avoided=list(dict.fromkeys(avoided))
    unconditional_conflicts=sorted(set(favored)&set(avoided))
    if unconditional_conflicts:
        reason='unconditional_avoid_conflict'
        return dict(mode='external',decision_status='pending',reason_code=reason,
            positions=[],favored=[],avoid=avoided,conditional_avoid=conditional,
            release_ready=False,blocking_missing_evidence=[
                'resolve_unconditional_avoid:'+w for w in unconditional_conflicts],
            priority_reason='格局主喜与无条件忌神重合，需复核取用记录后再裁决。')
    triggered_conflicts = sorted(set(favored) & {
        item['wuxing'] for item in conditional if item.get('triggered') is True})
    if triggered_conflicts:
        return dict(mode='external', decision_status='pending',
            reason_code='triggered_avoid_conflict', positions=[], favored=[], avoid=avoided,
            conditional_avoid=conditional, release_ready=False,
            blocking_missing_evidence=['resolve_triggered_avoid:'+w for w in triggered_conflicts],
            priority_reason='已触发条件忌与顺势喜用冲突，暂停最终裁决。')
    positions=[dict(idx=i+1,gan=None,wx=w,precision='wuxing',
        roles=['external'],action='顺势取用' if w in primary else '辅助顺势',
        evidence_refs=['geju.structure_evidence','geju.xiyong_geju.special_yong_wuxing' if w in primary
                       else 'geju.xiyong_geju.special_xi_wuxing']) for i,w in enumerate(favored)]
    return dict(mode='external',decision_status='decided',reason_code='confirmed_true_cong' if kind=='cong' else 'confirmed_'+kind,
        positions=positions,favored=favored,avoid=list(avoided),
        conditional_avoid=conditional,avoid_source='geju.xiyong_geju.special_ji_wuxing',
        avoid_scope='unconditional',
        priority_reason='结构验真与外格成格结果一致，按该类结构的主辅五行取用；不是三维喜用融合。',
        structure_kind=kind,scope='original_chart',climate_role='独立气候信息，普通扶抑与调候排序暂停',
        decision_scope='顺势主方向',
        conditional_review_status='pending' if any(x['decision_status']=='pending' for x in conditional) else 'complete',
        release_ready=not any(x['decision_status']=='pending' for x in conditional),
        unresolved_dimensions=['日后岁运变化需重新验真'])
