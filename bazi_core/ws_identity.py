"""旺衰复用合同：绑定输入、有效配置、规则和完整结果，拒绝跨盘复用。"""
from .release_audit import digest
from . import metadata as M


def origin(chart, config):
    from .input_contracts import normalize_chart
    chart,_=normalize_chart(chart)
    from .fuyi_policy import VERSION
    defaults=M.default_config()
    return dict(pillars=[chart[k] for k in ('year','month','day','hour')],
                config={k:config.get(k,v) for k,v in defaults.items() if k!='enable_special_ge'},
                rules='wangshuai_effective_roots_v1.3.2',fuyi_policy=VERSION)


def seal(result, chart, config):
    result['source_identity']=origin(chart,config)
    result['result_digest']=digest({k:v for k,v in result.items() if k!='result_digest'})


def verify(result, chart, config):
    if (not isinstance(result,dict) or result.get('source_identity')!=origin(chart,config)
            or result.get('result_digest')!=digest({k:v for k,v in result.items() if k!='result_digest'})):
        raise ValueError('旺衰复用结果与当前四柱、配置或规则不一致，请重新计算')
