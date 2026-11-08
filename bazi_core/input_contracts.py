"""公开入口的共同输入合同；规则构造盘与真实命盘明确区分。"""
from .numeric import finite as safe_finite
import re
from math import isfinite
from . import metadata as M


def integer(value, name, low=None, high=None):
    if isinstance(value,str) and re.fullmatch(r'[+-]?\d+',value.strip()): value=int(value)
    if type(value) is not int or (low is not None and value<low) or (high is not None and value>high):
        raise ValueError(name+'需为范围内的整数')
    return value


def boolean(value,name):
    if type(value) is not bool: raise ValueError(name+'需为JSON布尔值')
    return value


def finite_number(value,name,low,high):
    if type(value) not in (int,float) or not safe_finite(value) or not low<=value<=high:
        raise ValueError(name+'需为范围内的有限数值')
    return value


def normalize_chart(chart, default_kind='rule_case'):
    if isinstance(chart,str):
        parts=chart.split()
        if len(parts)!=4 or any(len(p)!=2 for p in parts): raise ValueError('需提供四柱干支')
        chart=dict(gans=[p[0] for p in parts],zhis=[p[1] for p in parts])
    if not isinstance(chart,dict): raise ValueError('chart需为四柱对象或四柱字符串')
    out=dict(chart)
    try:
        if 'gans' in chart or 'zhis' in chart:
            if not all(isinstance(chart.get(k),(list,tuple,str)) for k in ('gans','zhis')):
                raise ValueError('gans和zhis需同时提供四项序列')
            gs,zs=list(chart['gans']),list(chart['zhis'])
        else:
            gs=[chart[k]['gan'] for k in ('year','month','day','hour')]
            zs=[chart[k]['zhi'] for k in ('year','month','day','hour')]
    except (KeyError,TypeError): raise ValueError('四柱输入不完整')
    if (len(gs)!=4 or len(zs)!=4 or any(not isinstance(g,str) or g not in M.GAN_LIST for g in gs)
            or any(not isinstance(z,str) or z not in M.ZHI_LIST for z in zs)):
        raise ValueError('需要四个有效天干和四个有效地支')
    for i,name in enumerate(('year','month','day','hour')):
        if ('gans' in chart or 'zhis' in chart) and name in chart:
            pillar=chart[name]
            if not isinstance(pillar,dict) or pillar.get('gan')!=gs[i] or pillar.get('zhi')!=zs[i]:
                raise ValueError('两套四柱表示不一致：'+name)
    kind=out.get('input_kind',default_kind)
    if kind not in ('real_chart','rule_case'): raise ValueError('input_kind需为real_chart或rule_case')
    errors=[]
    gi=[M.GAN_LIST.index(g) for g in gs];zi=[M.ZHI_LIST.index(z) for z in zs]
    if any(g%2!=z%2 for g,z in zip(gi,zi)): errors.append('干支阴阳不配，非六十甲子组合')
    if gi[1] != ((gi[0]%5)*2+2+(zi[1]-2)%12)%10: errors.append('年干与月柱不符合五虎遁')
    offset=integer(out.get('hour_stem_day_offset',0),'hour_stem_day_offset',0,1)
    if offset and zi[3]!=0: raise ValueError('次日日干定时干仅适用于晚子时')
    if gi[3] != (((gi[2]+offset)%5)*2+zi[3])%10: errors.append('日干与时柱不符合五鼠遁')
    if kind=='real_chart' and errors: raise ValueError('；'.join(errors))
    for key in ('solar_term_day',):
        if out.get(key) is not None: out[key]=integer(out[key],key,0,40)
    if out.get('night') is not None: boolean(out['night'],'night')
    out['input_kind']=kind
    for name,g,z in zip(('year','month','day','hour'),gs,zs): out[name]=dict(gan=g,zhi=z)
    return out,dict(input_kind=kind,calendar_consistency='inconsistent' if errors else 'consistent',
                    issues=errors,scope='干支组合及年月/日时推导一致性；不替代出生日期核验')
