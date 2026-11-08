"""待运信息展示：保留原始治法，推导候选不冒充已验证用神。"""
from . import metadata as M
PARTNER=dict(zip('甲乙丙丁戊己庚辛壬癸','己庚辛壬癸甲乙丙丁戊'))


def build_luck_plans(geju, day_gan=None):
    gx=geju.get('xiyong_geju',{});plans=[]
    for disease in gx.get('bing_list',[]):
        status=disease.get('treatment_status','')
        remaining=sum(max(0,e.get('remaining',0)) for e in disease.get('rescue_evidence',[]) if isinstance(e.get('remaining',0),(int,float)))
        if not ('待' in status or '潜在' in status or remaining>0): continue
        targets=list(dict.fromkeys(t[0] for t in disease.get('bing_shen',[]) if t and t[0] in M.GAN_LIST))
        methods=disease.get('yao',[]);candidates=[]
        for method in methods:
            if not isinstance(method,str): continue
            first=method.split('｜')[0]
            if first and first[0] in M.GAN_LIST:
                candidates.append(dict(gan=first[0],origin='upstream_candidate',method=method))
            elif day_gan and all(x in ('正印','偏印','比肩','劫财','食神','伤官','正财','偏财','正官','七杀') for x in first.split('/')):
                for gan in M.GAN_LIST:
                    if M.shishen(day_gan,gan) in first.split('/'):
                        candidates.append(dict(gan=gan,origin='shishen_candidate',method=method))
            elif '合去' in method or '喜合伤' in method:
                for g in targets:
                    candidates.append(dict(gan=PARTNER[g],origin='five_combination_candidate',target_gan=g,method='五合候选：'+g+PARTNER[g]))
        unique=[]
        for c in candidates:
            if c not in unique: unique.append(c)
        plans.append(dict(name=disease.get('name'),status=status,target_gans=targets,
            methods=methods,remaining=remaining,reason='药力或作用未通过，仍需补救' if remaining>0 else status,candidate_gans=list(dict.fromkeys(c['gan'] for c in unique)),candidates=unique,
            conditions=['须岁运出现并重新核验合绊、争合、合化及结构影响；不保证出现即奏效'],
            current_favored=False,realized=False))
    # 无病清单时仍展示上游潜在救应及待运文本。
    for text in dict.fromkeys(gx.get('latent_hidden_yong_shen',[])+gx.get('pending_yong_shen',[])):
        if not isinstance(text,str) or not text: continue
        if any(text in p['methods'] for p in plans): continue
        gan=text[0] if text[0] in M.GAN_LIST else None
        plans.append(dict(name='潜在救应',status='待透或待运',target_gans=[],methods=[text],
            candidate_gans=[gan] if gan else [],conditions=['以原始候选条件为准，岁运到位后重新评估'],
            current_favored=False,realized=False))
    return plans
