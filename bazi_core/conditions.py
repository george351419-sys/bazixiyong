"""有限条件表达式；禁止执行字符串代码，缺事实按三态 unknown 处理。"""
from .numeric import finite as safe_finite
from math import isfinite


def scalar(value):
    return value is None or type(value) in (str, bool) or (type(value) in (int,float) and safe_finite(value))


def valid_condition(expr, depth=0):
    if depth > 16 or not isinstance(expr,dict): return False
    op=expr.get('op')
    if op in ('all','any'):
        return (set(expr)=={'op','args'} and isinstance(expr['args'],list)
                and 0<len(expr['args'])<=64 and all(valid_condition(e,depth+1) for e in expr['args']))
    if op not in ('eq','ne','gt','ge','lt','le') or set(expr)!= {'op','path','value'}: return False
    path=expr['path']
    return (isinstance(path,str) and bool(path) and len(path)<=256
            and all(part and part.isidentifier() and not part.startswith('_') for part in path.split('.'))
            and scalar(expr['value'])
            and (op in ('eq','ne') or type(expr['value']) in (int,float)))


def evaluate_condition(expr, facts):
    if not valid_condition(expr): return 'invalid'
    op=expr['op']
    if op in ('all','any'):
        values=[evaluate_condition(e,facts) for e in expr['args']]
        if op=='all': return 'false' if 'false' in values else 'true' if all(v=='true' for v in values) else 'unknown'
        return 'true' if 'true' in values else 'false' if all(v=='false' for v in values) else 'unknown'
    value=facts
    for part in expr['path'].split('.'):
        if not isinstance(value,dict) or part not in value: return 'unknown'
        value=value[part]
    expected=expr['value']
    if not scalar(value): return 'unknown'
    numeric=type(value) in (int,float) and type(expected) in (int,float)
    if not numeric and type(value) is not type(expected): return 'unknown'
    if op in ('gt','ge','lt','le') and not numeric: return 'unknown'
    result={'eq':lambda:value==expected,'ne':lambda:value!=expected,
            'gt':lambda:value>expected,'ge':lambda:value>=expected,
            'lt':lambda:value<expected,'le':lambda:value<=expected}[op]()
    return 'true' if result else 'false'


def fact_condition(path, value=True):
    expr = {'op':'eq', 'path':path, 'value':value}
    if not valid_condition(expr): raise ValueError('非法事实条件路径')
    return expr


def referenced_paths(expr):
    if not valid_condition(expr): return []
    if expr['op'] in ('all','any'):
        return sorted({p for e in expr['args'] for p in referenced_paths(e)})
    return [expr['path']]
