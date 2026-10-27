"""Price sanity rules (shared by build_national.py and the STL post-pass). Marks rows Low + hidden; never deletes.
1) cash within 1% of the same line's gross charge -> sticker price, not a negotiated cash price
2) cash > gross (by >1%) -> likely data error
3) cash > 30x the Medicare amount the site compares that row against -> implausibly high
Usage (standalone, in place on one metro dir): sanity.py data/<cbsa>"""
import json,sys,collections
R1='cash price equals full charge'; R2="cash exceeds hospital's own full charge (likely data error)"; R3='implausibly high vs Medicare'
def medicare_for(r,prov,B):
  part=prov.get('part') or prov.get('state')
  b=(B.get(('H'+str(prov.get('ccn')),r['code'])) if r.get('code_type')=='MS-DRG' and prov.get('ccn') else None) or B.get((part,r['code']))
  if not b: return None
  if r.get('all_inclusive'): return b.get('combined')
  if (r.get('included') or '').startswith('Professional'): return b.get('professional') if b.get('professional') is not None else b.get('combined')
  return b.get('facility') if b.get('facility') is not None else b.get('combined')
def apply(prices,providers,bms):
  P={p['id']:p for p in providers}; B={(b.get('lk') or b['state'],b['code']):b for b in bms}; n=collections.Counter()
  for r in prices:
    if r.get('sanity'): continue
    c=r.get('cash'); g=r.get('gross'); why=None
    if isinstance(c,(int,float)) and isinstance(g,(int,float)) and g>0:
      if abs(c-g)<=0.01*g: why=R1
      elif c>1.01*g: why=R2
    if not why and isinstance(c,(int,float)):
      m=medicare_for(r,P.get(r['provider_id'],{}),B)
      if m and m>0 and c>30*m: why=R3
    if why:
      r['comparability_pre']=r.get('comparability'); r['sanity']=why; r['comparability']='Low'
      r['comp_reasons']=list(r.get('comp_reasons') or [])+[why]
      r['flag']=('Not comparable: '+why)+(' | '+r['flag'] if r.get('flag') else '')
      n[why]+=1
  return n
def recount(idx,prices):
  n=collections.Counter(r['code'] for r in prices if r['comparability']!='Low')
  return dict(idx,codes=[dict(x,n=n.get(x['c'],0)) for x in idx['codes']])
if __name__=='__main__':
  D=sys.argv[1]; L=lambda n: json.load(open(f'{D}/{n}.json',encoding='utf-8'))
  pr,pv,bm,ix=L('prices'),L('providers'),L('benchmarks'),L('search_index')
  n=apply(pr,pv,bm); print(D,dict(n))
  for r in pr:
    if r.get('sanity'): print(' ',r['provider_id'],r['code'],r['cash'],r.get('gross'),r['comparability_pre'],'->',r['sanity'])
  W=lambda nm,o: json.dump(o,open(f'{D}/{nm}.json','w',encoding='utf-8'),separators=(',',':'),ensure_ascii=False)
  W('prices',pr); W('search_index',recount(ix,pr))