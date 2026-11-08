"""融合入口的结构合同；错误应返回待判原因而不是下游类型异常。"""
from . import metadata as M


def action_identity(action):
    if not isinstance(action,dict): return None
    gan=action.get('gan');wx=action.get('wuxing');precision=action.get('precision','gan')
    if gan in M.GAN_LIST and precision=='gan':
        canonical=M.WUXING_GAN[gan]
        return (gan,canonical,'gan') if wx is None or wx==canonical else None
    if gan is None and precision=='wuxing' and wx in M.WUXING_LIST:
        return (None,wx,'wuxing')
    return None


def route_shape_errors(routes):
    if not isinstance(routes,list): return ['routes:not_list']
    errors=[];ids=[]
    for index,route in enumerate(routes):
        path='routes:'+str(index)
        if not isinstance(route,dict): errors.append(path);continue
        ident=route.get('route_id')
        if not isinstance(ident,str) or not ident: errors.append(path+':route_id')
        else: ids.append(ident)
        for key in ('actions','source_mappings','source_restrictions','tradeoff_authorizations','resource_usage'):
            if key in route and (not isinstance(route[key],list) or any(not isinstance(v,dict) for v in route[key])):
                errors.append(path+':'+key)
        if isinstance(route.get('actions'),list):
            for action in route['actions']:
                if isinstance(action,dict) and (not isinstance(action.get('target_id'),str) or not action.get('target_id')):
                    errors.append(path+':action_target')
        for key in ('goal_results','monitor_results','structure_goals','checks','evidence_registry','resources'):
            if key in route and (not isinstance(route[key],dict) or any(not isinstance(k,str) or not isinstance(v,dict) for k,v in route[key].items())):
                errors.append(path+':'+key)
        if 'method_choices' in route and (not isinstance(route['method_choices'],dict)
                or any(not isinstance(k,str) or not isinstance(v,str) for k,v in route['method_choices'].items())):
            errors.append(path+':method_choices')
        if 'replacement' in route and (not isinstance(route['replacement'],dict)
                or not isinstance(route['replacement'].get('replaces_route_id'),str)):
            errors.append(path+':replacement')
        for goal in route.get('structure_goals',{}).values() if isinstance(route.get('structure_goals'),dict) else []:
            if isinstance(goal,dict) and 'record' in goal and not isinstance(goal['record'],dict): errors.append(path+':structure_record')
        if 'goals' in route and (not isinstance(route['goals'],list) or any(not isinstance(g,str) for g in route['goals'])):
            errors.append(path+':goals')
    if len(ids)!=len(set(ids)): errors.append('routes:duplicate_id')
    return sorted(set(errors))
