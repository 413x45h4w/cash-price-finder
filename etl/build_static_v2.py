# Comparability-model static export. Reads parsed MRF CSVs (v3) + existing benchmarks/providers JSON.
import csv,glob,os,json,re,statistics as S,collections
R=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # site/
ROOT=os.path.dirname(R); PARSED=ROOT+'/parsed/20261023T114040_v3'; D=R+'/data/stl'
J=lambda n: json.load(open(f'{D}/{n}.json',encoding='utf-8'))
provs=J('providers'); BMs=J('benchmarks'); old=J('prices'); eps=J('episodes')
P={p['id']:p for p in provs}; B={(b['state'],b['code']):b for b in BMs}
for p in provs:
  if p['id']=='hshssj1': p.update(name="HSHS St. Joseph's Hospital - Breese",ccn='140145',city='Breese')
  if p['id']=='hshssj2': p.update(name="HSHS St. Joseph's Hospital - Highland",ccn='141336',city='Highland')
CODES={b['code'] for b in BMs}
ED_CODES={'99281','99282','99283','99284','99285','99291','G0380','G0381','G0382','G0383','G0384'}
OB_GLOBAL={'59400','59510','59610'}
def revs(ac): return [t.split(':',1)[1].lstrip('0') for t in ac.split(';') if t.startswith('RC:')]
def desc_mod(d): return '|' in d   # BJC-style: modifier text appended after '|'
out=[]; diag={}
for p in provs:
  pid=p['id']; f=f'{PARSED}/{pid}.csv'
  if p['type']!='Hospital' or not os.path.exists(f): continue
  cand=collections.defaultdict(list); rej={}
  for r in csv.DictReader(open(f,encoding='utf-8')):
    code=r['code']
    if code not in CODES: continue
    try: cash=float(r['cash'])
    except: continue
    if cash<=0: continue
    ac=r['all_codes']; bc=r['billing_class'].strip().lower(); st=r['setting'].strip().lower(); rc=revs(ac)
    if 'LOCAL:CASE' in ac.upper(): continue                      # Mercy case-rate lines: hidden
    drg=r['code_type']=='MS-DRG'
    ex=[]
    if drg:
      if st not in('inpatient','both'): continue
    else:
      if st=='inpatient': continue
      rr=None
      if code not in OB_GLOBAL:
        if bc=='professional': rr='professional-fee line (billing class professional)'
        elif any(x[:2] in('96','98') and len(x)==3 for x in rc): rr='professional-fee revenue code '+','.join(rc)
      if not rr and code not in ED_CODES and '450' in rc: rr='emergency-department line (rev 0450)'
      if rr:
        rej.setdefault(code,(rr,cash,r,rc)); continue
    mod=bool(r['modifiers'].strip()) or desc_mod(r['description'])
    addon=bool(re.search(r'add[\s-]?on',r['description'],re.I))
    cand[code].append(dict(cash=cash,gross=float(r['gross']) if r['gross'] else None,desc=r['description'][:200],bc=bc,setting=st,mods=r['modifiers'],rev=','.join(rc),mod=mod,addon=addon,drg=drg,neg_min=r['neg_min'],neg_max=r['neg_max']))
  for code,(rr,cash,r,rc) in rej.items():
    if code in cand: continue
    out.append(dict(provider_id=pid,code=code,code_type='CPT/HCPCS',description=r['description'][:200],setting='outpatient',cash=round(cash,2),cash_min=cash,cash_max=cash,n_lines=1,
      gross=float(r['gross']) if r['gross'] else None,all_inclusive=0,flag='Not comparable: '+rr,comparability='Low',comp_reasons=['only '+rr+' listed'],
      included='Professional fee only' if 'professional' in rr else 'Emergency-department facility fee',
      source=dict(description=r['description'][:200],billing_class=r['billing_class'] or None,setting=r['setting'],modifiers=r['modifiers'] or None,revenue_code=','.join(rc) or None)))
  for code,v in cand.items():
    clean=[x for x in v if not x['mod'] and not x['addon']]
    why=[]
    if clean: pool=clean
    else: pool=[x for x in v if not x['addon']] or v; why.append('only modifier/add-on variants listed')
    outp=[x for x in pool if x['setting']=='outpatient' or x['drg']] or pool
    prices=sorted({x['cash'] for x in outp})
    pick=max(outp,key=lambda x:x['cash'])   # most complete facility charge among unmodified lines
    if len(prices)>1: why.append(f'{len(prices)} different unmodified prices listed ({prices[0]:,.0f}-{prices[-1]:,.0f}); highest used')
    if pick['setting']=='both': why.append('setting listed as both inpatient/outpatient')
    if not pick['bc'] and not pick['drg']: why.append('billing class not stated')
    st=p['state']; b=B.get((st,code)) or B.get(('MO',code))
    flag=None
    if b and b.get('facility') and b['facility']>100 and pick['cash']<0.5*b['facility']:
      flag=f"Below 50% of Medicare facility rate (${b['facility']:,.0f}) - likely a single component, not the full service"
    if not clean or flag: comp='Low'
    elif why: comp='Medium'
    else: comp='High'
    if pick['drg']: inc='Facility inpatient stay (DRG); physician fees billed separately'
    elif code in OB_GLOBAL: inc='Professional (physician global fee)'
    else: inc='Facility fee only; physician/anesthesia/pathology billed separately'
    out.append(dict(provider_id=pid,code=code,code_type='MS-DRG' if pick['drg'] else 'CPT/HCPCS',description=pick['desc'],setting='inpatient' if pick['drg'] else 'outpatient',
      cash=round(pick['cash'],2),cash_min=prices[0],cash_max=prices[-1],n_lines=len(v),gross=pick['gross'],all_inclusive=0,flag=flag,
      comparability=comp,comp_reasons=why,included=inc,
      source=dict(description=pick['desc'],billing_class=pick['bc'] or None,setting=pick['setting'],modifiers=pick['mods'] or None,revenue_code=pick['rev'] or None)))
for r in old:
  if r['all_inclusive']:
    out.append(dict(r,comparability='Medium',comp_reasons=['price published on provider website; scope as stated'],included='All-in (facility + professional) per provider',
      source=dict(description=r['description'],billing_class=None,setting=r['setting'],modifiers=None,revenue_code=None)))
w=lambda n,o: json.dump(o,open(f'{D}/{n}.json','w',encoding='utf-8'),separators=(',',':'),ensure_ascii=False)
w('prices',out); w('providers',provs)
idx=J('search_index'); n=collections.Counter(r['code'] for r in out if r['comparability']!='Low')
for c in idx['codes']: c['n']=n.get(c['c'],0)
w('search_index',idx)
print(len(out),collections.Counter(r['comparability'] for r in out))
h=sorted((r['cash'],r['provider_id'],r['comparability']) for r in out if r['code']=='45385')
for x in h: print(x)
core=[x[0] for x in h if x[2]=='High']; allc=[x[0] for x in h if x[2]!='Low']
print('45385 High: %.0f-%.0f = %.2fx'%(min(core),max(core),max(core)/min(core)) if core else 'none')
q=sorted(allc); import statistics; qs=statistics.quantiles(q,n=4); print('45385 middle 50%%: %.0f-%.0f = %.2fx'%(qs[0],qs[2],qs[2]/qs[0]))
print('45385 comparable: %.0f-%.0f = %.2fx'%(min(allc),max(allc),max(allc)/min(allc)))
