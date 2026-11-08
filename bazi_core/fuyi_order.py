"""扶抑内部逐干次序；极弱阈值为工程初版，不改变旺衰标签。"""
from . import metadata as M
from .fuyi_policy import EXTREME_WEAK_SHARE


def fuyi_order(ws, favored):
    weak=ws.get('tag') in ('身弱','中和偏弱','身弱无根')
    rooted=ws.get('root_state',{}).get('effective_count',len(ws.get('effective_roots',[])))>0
    extreme=weak and ws.get('ratio_share_f_exact',ws.get('ratio_share_f',1))<=EXTREME_WEAK_SHARE
    rows=[]
    for gan in M.GAN_LIST:
        if M.WUXING_GAN[gan] not in favored: continue
        ss=M.shishen(ws['day_gan'],gan)
        key=[0,0]
        if weak:
            if ss in ('正印','偏印'):
                key=[1 if rooted else 0,2 if ss=='正印' else 1]
            elif ss in ('比肩','劫财'):
                first='劫财' if extreme else '比肩'
                key=[0,2 if ss==first else 1]
        rows.append(dict(gan=gan,shishen=ss,preference_key=key))
    rows.sort(key=lambda x:(tuple(-v for v in x['preference_key']),M.GAN_LIST.index(x['gan'])))
    last=None;rank=0
    for i,row in enumerate(rows):
        if row['preference_key']!=last: rank=i+1;last=row['preference_key']
        row['rank']=rank
    return dict(weak=weak,rooted=rooted,extreme_weak=extreme,
        extreme_threshold=EXTREME_WEAK_SHARE,extreme_metric='ratio_share_f_exact',
        note='有根印先于比劫；同条件正印先于偏印；极弱劫先比，否则比先劫。无根不另设印比组先后。',
        ranked_gans=rows)
