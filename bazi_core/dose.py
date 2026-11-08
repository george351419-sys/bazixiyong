"""剂量只从同一目标的成对药效证据派生，不从缺口反推药力。"""
from .numeric import finite as safe_finite
from math import isfinite


def numeric(value):
    return type(value) in (int,float) and safe_finite(value) and value>=0


def assess_dose(observation):
    demand=observation.get('initial_demand')
    relief=observation.get('relief_realized')
    harm=observation.get('aggravation',0)
    execution=observation.get('execution_status','unknown')
    result=dict(dose=None,signed_relief=None,state='evidence_insufficient',action='review',
                execution_status=execution,actionable=False)
    if execution=='not_executed':
        feasible=observation.get('relief_feasible')
        result.update(state='no_medicine' if feasible==0 and relief==0 else 'not_executed',action='wait_condition' if numeric(feasible) and feasible>0 else 'review_feasibility')
        return result
    if not observation.get('valid',True) or not all(numeric(v) for v in (demand,relief,harm)) or execution!='realized':
        return result
    signed=relief-harm
    result.update(signed_relief=signed,dose=relief/demand if demand>0 else None)
    if harm>1e-9: result.update(state='adverse_effect',action='review_cost')
    elif demand==0: result.update(state='no_demand',action='no_increase')
    elif observation.get('remaining',demand)>1e-9:
        result.update(state='insufficient',action='evaluate_repair')
    else: result.update(state='satisfied',action='no_increase')
    return result
