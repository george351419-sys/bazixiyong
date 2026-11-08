"""假从未来路线：具体障碍与重新验真分开，禁止把标签当去病措施。"""
from copy import deepcopy
from .conditions import fact_condition, evaluate_condition


def fake_cong_routes(facts):
    ws=facts.get('ws',{});info=ws.get('cong_info',{})
    if info.get('is_fake_cong') is not True: return []
    blockers=[]
    for key,label in [('residual_bi_root','比劫强根干扰'),('residual_yin_root','印星强根干扰'),
                      ('residual_k_root','克泄耗强根干扰')]:
        if info.get(key) is True:
            blockers.append(dict(kind=key,reason=label,evidence_ref='ws.cong_info.'+key,
                condition_expr=fact_condition('ws.cong_info.'+key,False),
                resolution='新情景重算后不再存在此干扰，不预先认定冲合必能解除'))
    roots=[r for r in ws.get('effective_roots',[]) if not r.get('is_broken')]
    if ws.get('tag')=='假从弱' and roots:
        blockers.append(dict(kind='residual_day_roots',reason='日主有效残根',
            evidence_ref='ws.effective_roots',evidence=deepcopy(roots),
            condition_expr=None,resolution='需逐根验证是否仍妨碍真从，不以根数清零替代上游门槛'))
    if not blockers:
        blockers.append(dict(kind='unresolved_structure',reason='未定位具体转真障碍',
            condition_expr=None,evidence_ref='ws.cong_info',resolution='需人工核查并重新验真'))
    expr={'op':'all','args':[fact_condition('ws.cong_info.is_cong'),fact_condition('ws.cong_info.is_fake_cong',False)]}
    return [dict(kind='fake_cong',scenario='future_reassessment',condition_expr=expr,
        current_condition_status=evaluate_condition(expr,facts),prerequisites=blockers,
        requires_reassessment=True,actionable=False,
        condition_scope='具体障碍解除后重新计算；验真表达式仅为最终验收条件',
        unresolved_evidence=deepcopy(info))]
