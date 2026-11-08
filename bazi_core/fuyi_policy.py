"""扶抑与方向政策的共享初版参数；经验规则不代表已独立标定。"""
VERSION='fuyi_policy_v4_shared_band'
BALANCE_SHARES=(.60,.50,.40)
CONG_THRESHOLD=.85
EXTREME_WEAK_SHARE=.20
MINIMUM_SUPPORT=.25
PROBE_AMOUNT=.05
SEASON_VALUES=(1.30,1.15,1.00,.85,.70)
SOIL_WEIGHT=.50
BALANCED_FUYI_WEIGHT=.50


def balance_band(F, K):
    """数值区间唯一入口；仅容忍机器运算误差，不按展示值取整。"""
    from math import ulp
    from fractions import Fraction
    for share, label in zip(BALANCE_SHARES, ('身旺','中和偏旺','中和偏弱')):
        threshold=float(Fraction(str(share))/(1-Fraction(str(share))))*K
        if F >= threshold or threshold-F <= 8*max(ulp(F),ulp(threshold)):
            return label
    return '身弱'


def reduced_fuyi(ws):
    if 'F' in ws and 'K' in ws:
        F,K=ws['F'],ws['K']
    else:
        F=ws.get('ratio_share_f_exact',ws.get('ratio_share_f',.5));K=1-F
    return balance_band(F,K) in ('中和偏弱','中和偏旺')
