"""事实身份与派生评估身份分离；同名模型修改内容也会使旧评估失效。"""
import hashlib
import json

ASSESSMENT_SCHEMA_VERSION = 'assessment_v1'
NEED_SCHEMA_VERSION = 'needs_v7_reviewed_maintenance_resolution'
EFFECT_SCHEMA_VERSION = 'effects_v7_prediction_monitoring_states'


def fact_snapshot_identity(ws, geju, tiaohou, fuyi):
    try:
        raw=json.dumps([ws,geju,tiaohou,fuyi],ensure_ascii=False,sort_keys=True,
                       allow_nan=False,separators=(',',':'))
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(raw.encode()).hexdigest()


def snapshot_error(facts):
    if not facts.get('snapshot_id'): return 'fact_snapshot_missing'
    expected=fact_snapshot_identity(*(facts.get(k) for k in ('ws','geju','tiaohou','fuyi')))
    if not expected or facts['snapshot_id'] != expected:
        return 'fact_snapshot_stale_or_invalid'
    ws=facts.get('ws',{})
    if facts.get('element_energy') != ws.get('climate_energy_raw',ws.get('climate_energy')):
        return 'energy_source_mismatch'
    if facts.get('energy_evidence') != ws.get('energy_records',[]):
        return 'energy_evidence_mismatch'
    return None


def assessment_identity(facts, model, policy_version):
    if snapshot_error(facts): return None
    # 需求基线只依赖原局事实与模型，不依赖候选路线或其效果。
    payload = dict(facts_snapshot_id=facts['snapshot_id'],
        element_energy=facts.get('element_energy'),
        model=model, policy_version=policy_version,
        assessment_schema=ASSESSMENT_SCHEMA_VERSION,
        need_schema=NEED_SCHEMA_VERSION, effect_schema=EFFECT_SCHEMA_VERSION)
    try:
        raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':'))
    except (TypeError, ValueError): return None
    return hashlib.sha256(raw.encode()).hexdigest()


def route_assessment_identity(assessment_id, routes, policy_inputs, evidence_bundle=None):
    """路线身份依赖基线；基线身份不反向依赖路线。"""
    if not assessment_id: return None
    try:
        raw=json.dumps(dict(assessment_snapshot_id=assessment_id,routes=routes,
            policy_inputs=policy_inputs,evidence_bundle=evidence_bundle),ensure_ascii=False,
            sort_keys=True,allow_nan=False,separators=(',',':'))
    except (TypeError,ValueError): return None
    return hashlib.sha256(raw.encode()).hexdigest()
