"""Recover dropped/unmatched file->CCN matches with corroborating evidence (append-only outputs).
Usage: recover_matches.py <map.csv> <parsed_dir>"""
import csv,sys,json,glob,re,time,sqlite3,collections,os,urllib.request
sys.path.insert(0,os.path.dirname(__file__)); from resolve_matches_lib import head,toks
GEN=set('behavioral specialty surgical rehabilitation rehab kaiser foundation adventist osf regional community memorial county general childrens children university doctors psychiatric neuropsychiatric dignity commonspirit ascension baptist methodist mercy providence trinity novant banner unity unitypoint sutter intermountain kindred shriners select encompass haven oceans aurora hca lifepoint ardent prime steward tenet chi advent adventhealth atrium sentara ochsner hshs ssm bjc llc lp corporation corp authority district public north south east west northern southern new'.split())
def namesim(a,b):
  A,B=toks(a)-GEN,toks(b)-GEN
  return len(A&B)/max(len(A),len(B)) if A and B else 0
MAP,PARSED=sys.argv[1],sys.argv[2]; RN='D:/price-transparency/ref_national/'; TS=time.strftime('%Y%m%dT%H%M%S')
rows=list(csv.DictReader(open(MAP,encoding='utf-8'))); FLD=list(rows[0].keys())
META={}
for f in glob.glob(PARSED+'/files/*.meta.json'):
  m=json.load(open(f,encoding='utf-8')); META[m['sha256']]=m
c=sqlite3.connect('file:D:/price-transparency/raw_national/manifest.sqlite?mode=ro',uri=True)
H={r[0]:dict(name=r[1],city=(r[2] or '').upper(),state=r[3],zip=(r[4] or '')[:5],county=r[5],type=r[6],cbsa=r[7] or '',cbsa_title=r[8] or '') for r in c.execute('select ccn,name,city,state,zip,county,type,cbsa,cbsa_title from hospitals')}
MAN=collections.defaultdict(set)
for sha,hn,ln in c.execute("select sha256,'',location_name from manifest where sha256!=''"):
  for x in (hn,ln):
    if x: MAN[sha].add(x)
BYZIP=collections.defaultdict(list); BYCITY=collections.defaultdict(list)
for k,v in H.items(): BYZIP[v['zip']].append(k); BYCITY[(v['state'],v['city'])].append(k)
USED={r['ccn'] for r in rows if r['ccn']}
def fields(txt):
  F=collections.defaultdict(list)
  if txt.lstrip().startswith(('{','[')):
    seg=txt.split('"standard_charge_information"')[0]
    for k,v in re.findall(r'"(hospital_name|location_name|hospital_location|hospital_address|address|type_2_npi|license_number)"\s*:\s*(\[[^\]]*\]|"[^"]*"|\d+)',seg,re.I):
      F[k.lower()]+=re.findall(r'"([^"]*)"',v) or [v]
  else:
    ls=txt.splitlines()[:2]
    if len(ls)<2: return F
    try: hd=next(csv.reader([ls[0]])); vals=next(csv.reader([ls[1]]))
    except Exception: return F
    for h,v in zip(hd,vals):
      hl=h.lower()
      for k in ('hospital_name','location_name','hospital_location','hospital_address','type_2_npi','license_number'):
        if hl.startswith(k) and v: F[k]+=[x for x in re.split(r'\s*\|\s*',v) if x]
      if hl=='hospital_name' and not v: pass
  return F
NPIC={}
def npi(n):
  if n in NPIC: return NPIC[n]
  try:
    j=json.load(urllib.request.urlopen(f'https://npiregistry.cms.hhs.gov/api/?version=2.1&number={n}',timeout=20))
    r=j['results'][0]; a=[x for x in r['addresses'] if x['address_purpose']=='LOCATION'][0]
    NPIC[n]=(r['basic'].get('organization_name',''),a['postal_code'][:5],a['city'].upper(),a['state'])
  except Exception: NPIC[n]=None
  time.sleep(0.2); return NPIC[n]
def dep(x,k):
  for w in H[k]['city'].split(): x=re.sub(r'(?i)\b'+re.escape(w)+r'\b',' ',x)
  return x
def best(names,cands,thr):
  sc=[(max(namesim(dep(n,k),dep(H[k]['name'],k)) for n in names),k) for k in cands]
  sc=[x for x in sc if x[0]>=thr]; sc.sort(reverse=True)
  return sc
out=[];log=[];cnt=collections.Counter()
for r in rows:
  if r['ccn'] or not os.path.exists(f"{PARSED}/files/{r['sha256'][:16]}.csv"): out.append(r); continue
  mt=META.get(r['sha256']) or {}
  txt=head('D:/price-transparency/raw_national/'+mt['path'].replace('\\','/')) if mt.get('path') else None
  F=fields(txt) if txt else {}
  names=[x for x in set((F.get('hospital_name') or [])+(F.get('location_name') or [])+(F.get('hospital_location') or [])+list(MAN.get(r['sha256'],()))+[r['file_name'].replace('(fallback) ',''),mt.get('location_name') or '']) if x and len(x)>3]
  addrs=(F.get('hospital_address') or [])+(F.get('address') or [])
  zips=set(); cities=set()
  for a in addrs:
    zips|=set(re.findall(r'\b(\d{5})(?:-\d{4})?\b\s*$',a.strip()))|set(re.findall(r'\b[A-Z]{2}\.?,?\s+(\d{5})\b',a))
    m=re.search(r'([A-Za-z .\'-]+),\s*([A-Z]{2})\b',a)
    if m: cities.add((m.group(2),m.group(1).strip().upper()))
  dec=None;ev=''
  sc=best(names,{k for z in zips for k in BYZIP.get(z,[])},0.5) if zips else []
  if sc:
    top=[x for x in sc if x[0]==sc[0][0]]
    if len(top)==1 and (len(sc)==1 or sc[0][0]-sc[1][0]>=0.2): dec=sc[0][1];meth='header-zip+name';ev=f'zips={sorted(zips)} sim={sc[0][0]:.2f} vs "{H[dec]["name"]}"'
    else: cnt['ambiguous-multi']+=1; ev=f'ambiguous {[(round(a,2),H[k]["name"]) for a,k in sc[:4]]}'
  if not dec and cities and not ev.startswith('ambig'):
    sc=best(names,{k for cs in cities for k in BYCITY.get(cs,[])},0.6)
    if len(sc)==1 or (sc and sc[0][0]-sc[1][0]>=0.2): dec=sc[0][1];meth='header-city+name';ev=f'city={sorted(cities)} sim={sc[0][0]:.2f} vs "{H[dec]["name"]}"'
  if not dec and not ev.startswith('ambig'):
    for n in (F.get('type_2_npi') or [])[:3]:
      n=re.sub(r'\D','',n)
      if len(n)!=10: continue
      p=npi(n)
      if not p: continue
      sc=best(names,BYZIP.get(p[1],[]),0.5) or best(names,BYCITY.get((p[3],p[2]),[]),0.6)
      if sc and (len(sc)==1 or sc[0][0]-sc[1][0]>=0.2): dec=sc[0][1];meth='npi-registry';ev=f'NPI {n} -> {p[0]} {p[2]},{p[3]} {p[1]}; sim={sc[0][0]:.2f} vs "{H[dec]["name"]}"';break
  if dec and dec in USED: cnt['ccn-already-covered']+=1; ev+=' [CCN already has a file; not reassigned]'; dec=None
  if dec:
    h=H[dec]; USED.add(dec); cnt[meth]+=1
    r=dict(r,ccn=dec,matched_name=h['name'],city=h['city'],state=h['state'],zip=h['zip'],county=h['county'],cbsa=h['cbsa'],cbsa_title=h['cbsa_title'],type=h['type'],method='recovered:'+meth,score='0.9')
  else: cnt['still-'+('dropped' if r['method'].startswith('dropped') else 'unmatched')]+=1
  log.append(dict(sha256=r['sha256'],file_name=r['file_name'],prior=r['method'] if not dec else '',decision=r['method'] if dec else 'unresolved',ccn=r['ccn'],evidence=ev or f'no corroborating header evidence (zips={sorted(zips)}, names={names[:3]})'))
  out.append(r)
MO=RN+f'file_ccn_map_{TS}.csv'; LO=RN+f'match_recovery_{TS}.csv'
w=csv.DictWriter(open(MO,'x',newline='',encoding='utf-8'),FLD);w.writeheader();w.writerows(out)
w=csv.DictWriter(open(LO,'x',newline='',encoding='utf-8'),list(log[0]));w.writeheader();w.writerows(log)
print(MO,LO,dict(cnt))