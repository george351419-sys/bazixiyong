"""月令季节有效作用系数；工程初版，不用于替换调候气候账。"""
from . import metadata as M
from .fuyi_policy import SEASON_VALUES as VALUES,SOIL_WEIGHT
def factors(month):
 def table(e):
  return {e:VALUES[0],M.SHENG[e]:VALUES[1],next(w for w in M.WUXING_LIST if M.SHENG[w]==e):VALUES[2],M.KE_OF[e]:VALUES[3],M.KE[e]:VALUES[4]}
 a=table(M.WUXING_ZHI[month])
 if month in '辰未戌丑':
  b=table(dict(辰='木',未='火',戌='金',丑='水')[month])
  a={w:SOIL_WEIGHT*a[w]+(1-SOIL_WEIGHT)*b[w] for w in a}
  a["土"]=VALUES[0]
 return a

def adjust(fk,gans,zhis,day_wx,he,config,relation,root_level,opened=None,broken=None):
 if not config.get('seasonal_strength',True): return fk
 c=factors(zhis[1]);before=dict(F=fk['F'],K=fk['K'],relation_energy=dict(fk['relation_energy']))
 for wx in M.WUXING_LIST: fk['relation_energy'][relation(wx,day_wx)]*=c[wx]
 fk['F']=sum(v for k,v in fk['relation_energy'].items() if k in ('bi','yin'))
 fk['K']=sum(v for k,v in fk['relation_energy'].items() if k not in ('bi','yin'))
 fk['raw_F']=fk['F'];fk['raw_K']=fk['K']
 for g in fk['gan_detail']:
  g['before_season']=g['contribution'];g['season_factor']=c[g['eff_wx']];g['contribution']=round(g['contribution']*c[g['eff_wx']],2)
 for b in fk['branch_detail']:
  b['before_season']=dict(F=b['contribution_F'],K=b['contribution_K'])
  for field,support in [('contribution_F',True),('contribution_K',False)]:
   b[field]=sum(r['power']*c[r['wuxing']] for r in fk['energy_records'] if r['id'].startswith('branch:'+str(b['branch_index'])+':') or r['id']=='branch:'+str(b['branch_index']) if (relation(r['wuxing'],day_wx) in ('bi','yin'))==support)
 effective_wx=he['gan_hua'][2] or day_wx
 lv=root_level(zhis,he['branch_hua'],effective_wx,gans[2],opened,broken if effective_wx==day_wx else None)
 root={2:1.,3:config['middle_root_factor'],1:config['micro_root_factor'],0:config['void_gan_factor']}[lv]
 own=config['tiangan_base']*he['gan_mag'][2]*root*c[he['gan_hua'][2] or day_wx]
 external_share=fk['F']/(fk['F']+fk['K'])
 effective_wx=he['gan_hua'][2] or day_wx
 rel=relation(effective_wx,day_wx)
 included=config.get('include_day_stem',True)
 if included:
  fk['relation_energy'][rel]+=own
  field='F' if rel in ('bi','yin') else 'K'
  fk[field]+=own;fk['raw_'+field]=fk[field]
  fk['f_elements' if field=='F' else 'k_elements'].add(effective_wx)
  fk['gan_detail'].append(dict(pos=2,gan=gans[2],eff_wx=effective_wx,relation=rel,root_level=lv,root_factor=root,gan_mag=he['gan_mag'][2],before_season=own/c[effective_wx],season_factor=c[effective_wx],contribution=round(own,2)))
 fk['seasonal_assessment']=dict(version='season_v3_day_included',factors=c,soil_fixed=1.3 if zhis[1] in '辰未戌丑' else None,soil_blend=.5 if zhis[1] in '辰未戌丑' else None,
  before=before,external_share=external_share,day_stem_policy='included_effective' if included else 'excluded_subject',day_stem_diagnostic=dict(contribution=own,
  relation=rel,inclusive_share=fk['F']/(fk['F']+fk['K']) if included else (fk['F']+(own if rel in ('bi','yin') else 0))/(fk['F']+fk['K']+own)),
  note='F/K为季节有效作用账；原始climate_energy不作季节重复加权。日干按配置纳入主账或仅作对照；external_share保留排除日干的对照。')
 return fk
