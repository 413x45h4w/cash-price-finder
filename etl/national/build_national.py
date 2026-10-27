"""Build per-CBSA static data (data/<cbsa>/*.json) from the national parse, using the build_static_v2.py comparability rules.
Usage: build_national.py <parsed_dir> <file_ccn_map.csv> [only_complete=1]"""
import csv,os,sys,json,re,collections,statistics as S,glob,sqlite3,time
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__))); import bench as BN
SITE=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); ROOT=os.path.dirname(SITE)
PARSED,MAP=sys.argv[1],sys.argv[2]; ONLY_COMPLETE=(sys.argv[3]!='0') if len(sys.argv)>3 else True
csv.field_size_limit(2**31-1)
ED_CODES={'99281','99282','99283','99284','99285','99291','G0380','G0381','G0382','G0383','G0384'}
OB_GLOBAL={'59400','59510','59610'}
def revs(ac): return [t.split(':',1)[1].lstrip('0') for t in ac.split(';') if t.upper().startswith('RC:')]
def desc_mod(d): return '|' in d
def comp_rows(pid,rows_iter,Bget):
  """Verbatim port of build_static_v2.py per-provider logic. Bget(code)->benchmark dict."""
  out=[]; cand=collections.defaultdict(list); rej={}
  for r in rows_iter:
    code=r['code']
    try: cash=float(r['cash'])
    except: continue
    if cash<=0: continue
    ac=r['all_codes']; bc=r['billing_class'].strip().lower(); st=r['setting'].strip().lower(); rc=revs(ac)
    if 'LOCAL:CASE' in ac.upper(): continue
    drg=r['code_type']=='MS-DRG'
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
    try: gross=float(r['gross']) if r['gross'] else None
    except: gross=None
    cand[code].append(dict(cash=cash,gross=gross,desc=r['description'][:200],bc=bc,setting=st,mods=r['modifiers'],rev=','.join(rc),mod=mod,addon=addon,drg=drg))
  for code,(rr,cash,r,rc) in rej.items():
    if code in cand: continue
    try: gross=float(r['gross']) if r['gross'] else None
    except: gross=None
    out.append(dict(provider_id=pid,code=code,code_type='CPT/HCPCS',description=r['description'][:200],setting='outpatient',cash=round(cash,2),cash_min=cash,cash_max=cash,n_lines=1,
      gross=gross,all_inclusive=0,flag='Not comparable: '+rr,comparability='Low',comp_reasons=['only '+rr+' listed'],
      included='Professional fee only' if 'professional' in rr else 'Emergency-department facility fee',
      source=dict(description=r['description'][:200],billing_class=r['billing_class'] or None,setting=r['setting'],modifiers=r['modifiers'] or None,revenue_code=','.join(rc) or None)))
  for code,v in cand.items():
    clean=[x for x in v if not x['mod'] and not x['addon']]
    why=[]
    if clean: pool=clean
    else: pool=[x for x in v if not x['addon']] or v; why.append('only modifier/add-on variants listed')
    outp=[x for x in pool if x['setting']=='outpatient' or x['drg']] or pool
    prices=sorted({x['cash'] for x in outp})
    pick=max(outp,key=lambda x:x['cash'])
    if len(prices)>1: why.append(f'{len(prices)} different unmodified prices listed ({prices[0]:,.0f}-{prices[-1]:,.0f}); highest used')
    if pick['setting']=='both': why.append('setting listed as both inpatient/outpatient')
    if not pick['bc'] and not pick['drg']: why.append('billing class not stated')
    b=Bget(code); flag=None
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
  return out
# ---- inputs
MAPR=list(csv.DictReader(open(MAP,encoding='utf-8')))
META={}
for f in glob.glob(PARSED+'/files/*.meta.json'):
  m=json.load(open(f)); META[m['sha256']]=m
c=sqlite3.connect('file:'+ROOT+'/raw_national/manifest.sqlite?mode=ro',uri=True)
MURL={}; DOM={}
for sha,u,fu,d,hp in c.execute("select sha256,mrf_url,final_url,domain,hpt_url from manifest where error='' and sha256!='' order by run"): MURL[sha]=u; DOM[sha]=(d,hp)
H={r[0]:r for r in c.execute('select ccn,name,city,state,zip,county,type,cbsa,cbsa_title from hospitals')}
all_files_by_cbsa=collections.defaultdict(set)
for m in MAPR:
  if m['ccn'] and m['cbsa']: all_files_by_cbsa[m['cbsa']].add(m['sha256'])
best={}
for m in MAPR:
  if not m['ccn'] or not m['cbsa']: continue
  mt=META.get(m['sha256'])
  if not mt or mt['status']=='fail' or not mt.get('hits'): continue
  k=(float(m['score']),m['run'],mt['hits'])
  if m['ccn'] not in best or k>best[m['ccn']][0]: best[m['ccn']]=(k,m,mt)
by_cbsa=collections.defaultdict(list)
for ccn,(k,m,mt) in best.items(): by_cbsa[m['cbsa']].append((m,mt))
eps=json.load(open(SITE+'/data/41180/episodes.json',encoding='utf-8')); idx0=json.load(open(SITE+'/data/41180/search_index.json',encoding='utf-8'))
meta_path=SITE+'/data/meta.json'; META_SITE=json.load(open(meta_path,encoding='utf-8'))
metros={x['metro']:x for x in META_SITE['metros']}
log=open(f'{PARSED}/build_{time.strftime("%Y%m%dT%H%M%S")}.log','w',encoding='utf-8'); built=0
for cbsa,L in sorted(by_cbsa.items()):
  if cbsa=='41180': continue   # St. Louis: curated release kept as-is
  if ONLY_COMPLETE and any(s not in META for s in all_files_by_cbsa[cbsa]): continue
  provs=[]; prices=[]; bms=[]; parts=collections.defaultdict(lambda:([],[]))
  for m,mt in L: parts[m['state']][0].append(m['ccn']); parts[m['state']][1].append(m['zip'][:5])
  PL={st:BN.part_params(cbsa,st,cc,zz) for st,(cc,zz) in parts.items()}
  Bd={}
  for st,Lp in PL.items():
    for r in BN.rows_for(st,cbsa,st,cbsa,Lp): bms.append(r); Bd[(st,r['code'])]=r
  for m,mt in L:
    ccn=m['ccn']; pid='h'+ccn; st=m['state']; hi=BN.hosp_ipps(ccn)
    if hi:
      Lh=dict(PL[st],ipps_wi=hi[0],gaf=hi[1])
      for r in BN.rows_for('H'+ccn,cbsa,st,cbsa,Lh,drg_only=True,label=' (this hospital, Table 2)'): bms.append(r); Bd[('H'+ccn,r['code'])]=r
    Bget=lambda code,ccn=ccn,st=st: Bd.get(('H'+ccn,code)) or Bd.get((st,code))
    f=f"{PARSED}/files/{m['sha256'][:16]}.csv"
    try:
      pr=comp_rows(pid,csv.DictReader(open(f,encoding='utf-8')),Bget)
    except Exception as e:
      log.write(f'{cbsa} {ccn} build error {e}\n'); continue
    if not pr: log.write(f'{cbsa} {ccn} no usable rows\n'); continue
    prices+=pr
    z=m['zip'][:5]; ll=BN.GEO.get(z,(None,None)); nm=(mt.get('hospital_name') or '').strip()
    name=nm if nm and float(m['score'])>=0.8 and not nm.isupper() else m['matched_name'].title().replace("'S ","'s ")
    d,hp=DOM.get(m['sha256'],('',''))
    provs.append(dict(id=pid,metro=cbsa,ccn=ccn,name=name,type='Hospital',subtype=m['type'],city=m['city'].title(),state=st,system=d,address=f"{m['city'].title()}, {st} {z}",
      lat=ll[0],lon=ll[1],page_url=hp or MURL.get(m['sha256']),file_url=MURL.get(m['sha256']),file_format=mt.get('format'),vintage=m['run'],last_updated=mt.get('last_updated_on'),
      note=None if float(m['score'])>=0.8 else f"File matched to CMS hospital by name (score {m['score']}): '{m['file_name'][:80]}'"))
  if not provs: continue
  D=f'{SITE}/data/{cbsa}'; os.makedirs(D,exist_ok=True)
  n=collections.Counter(r['code'] for r in prices if r['comparability']!='Low')
  idx=dict(idx0,codes=[dict(x,n=n.get(x['c'],0)) for x in idx0['codes']])
  w=lambda nme,o: json.dump(o,open(f'{D}/{nme}.json','w',encoding='utf-8'),separators=(',',':'),ensure_ascii=False)
  w('providers',provs); w('prices',prices); w('benchmarks',bms); w('episodes',eps); w('search_index',idx)
  lat=[p['lat'] for p in provs if p['lat']]; lon=[p['lon'] for p in provs if p['lon']]
  title=L[0][0]['cbsa_title']
  metros[cbsa]=dict(metro=cbsa,name=title,cbsa=cbsa,states=','.join(sorted(PL)),parts=sorted(PL,key=lambda s:-len(parts[s][0])),n_hosp=len(provs),
    center=[round(S.median(lat),4),round(S.median(lon),4)] if lat else None,
    pfs=' / '.join(f"{s}: {PL[s]['pfs_loc']}, OPPS WI {PL[s]['opps_wi']}" for s in PL))
  built+=1; log.write(f'{cbsa} {title}: {len(provs)} hospitals, {len(prices)} rows\n')
ml=sorted(metros.values(),key=lambda x:(x['metro']!='41180',x['name']))
META_SITE['metros']=ml
META_SITE['vintage']='Hospital MRFs fetched 2026-10-23..24 (national collection; St. Louis curated 2026-10-23); Medicare: OPPS Add. B Oct-2026, PFS 2026 RVU26D + ZIP5 Oct-2026 localities, CLFS 2026 Q4, IPPS FY2027 CN Tables 2/3/5'
json.dump(META_SITE,open(meta_path,'w',encoding='utf-8'),separators=(',',':'),ensure_ascii=False)
print('built',built,'metros total',len(ml)); log.close()