"""事实身份与派生评估身份分离；同名模型修改内容也会使旧评估失效。"""
import hashlib
import json

ASSESSMENT_SCHEMA_VERSION = 'assessment_v1'
NEED_SCHEMA_VERSION = 'needs_v3_monitoring'
EFFECT_SCHEMA_VERSION = 'effects_v3_monitoring'


def assessment_identity(facts, model, policy_version):
    if not isinstance(facts.get('snapshot_id'), str): return None
    payload = dict(facts_snapshot_id=facts['snapshot_id'],
        # 包含实际消费的派生能量，防止测试注入修改后继续沿用旧事实身份。
        element_energy=facts.get('element_energy'),
        model=model, policy_version=policy_version,
        assessment_schema=ASSESSMENT_SCHEMA_VERSION,
        need_schema=NEED_SCHEMA_VERSION, effect_schema=EFFECT_SCHEMA_VERSION)
    try:
        raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':'))
    except (TypeError, ValueError): return None
    return hashlib.sha256(raw.encode()).hexdigest()
