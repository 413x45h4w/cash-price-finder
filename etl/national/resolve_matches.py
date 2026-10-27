"""Resolve or drop low-confidence file->CCN matches (score<0.8 or manifest-own) using the MRF's own header (address/zip/location).
Usage: resolve_matches.py <map.csv> <parsed_dir>  -> writes new timestamped map + audit csv in ref_national."""
import csv,sys,json,glob,gzip,zipfile,re,io,time,sqlite3,collections
MAP,PARSED=sys.argv[1],sys.argv[2]; RN='D:/price-transparency/ref_national/'
rows=list(csv.DictReader(open(MAP,encoding='utf-8')))
META={}
for f in glob.glob(PARSED+'/files/*.meta.json'):
  m=json.load(open(f,encoding='utf-8')); META[m['sha256']]=m
c=sqlite3.connect('file:D:/price-transparency/raw_national/manifest.sqlite?mode=ro',uri=True)
H={r[0]:dict(name=r[1],city=r[2],state=r[3],zip=(r[4] or '')[:5],county=r[5],type=r[6],cbsa=r[7],cbsa_title=r[8]) for r in c.execute('select ccn,name,city,state,zip,county,type,cbsa,cbsa_title from hospitals')}
BYZIP=collections.defaultdict(list)
for k,v in H.items(): BYZIP[(v['state'],v['zip'])].append(k)
def head(path,n=400000):
  try:
    if path.lower().endswith('.zip'):
      z=zipfile.ZipFile(path); nm=[x for x in z.namelist() if x.lower().endswith(('.csv','.json'))]
      if not nm: return None
      return z.open(nm[0]).read(n).decode('utf-8','ignore')
    op=gzip.open if path.lower().endswith('.gz') else open
    with op(path,'rb') as f: b=f.read(n)
    if b[:2]==b'PK': return None
    return b.decode('utf-8','ignore')
  except Exception as e: return None
def header_zips(txt,st):
  if txt.lstrip().startswith(('{','[')):
    seg=txt.split('"standard_charge_information"')[0]
    m=re.findall(r'"(?:hospital_address|location_name|hospital_location|address)"\s*:\s*(\[[^\]]*\]|"[^"]*")',seg,re.I)
    s=' '.join(m)
  else:
    ls=txt.splitlines()[:2]
    if len(ls)<2: return set()
    hd=next(csv.reader([ls[0]])); vals=next(csv.reader([ls[1]]))
    s=' '.join(v for h,v in zip(hd,vals) if re.search(r'address|location',h,re.I))
  return set(re.findall(r'\b'+st+r'\.?,?\s+(\d{5})\b',s,re.I))|set(re.findall(r'\b(\d{5})(?:-\d{4})?\s*$',s))
STOP=set('hospital hospitals medical center centre health healthcare system systems inc llc of the at and dba campus st saint mc ctr hosp med a an'.split())
def toks(x): return {t for t in re.findall(r'[a-z]+',x.lower().replace("'",'')) if t not in STOP and len(t)>1}
def namesim(a,b):
  A,B=toks(a),toks(b)
  return len(A&B)/max(len(A),len(B)) if A and B else 0
out=[];aud=[];cnt=collections.Counter()
for r in rows:
  low=r['ccn'] and (float(r['score'])<0.8 or r['method']=='manifest-own')
  if not low: out.append(r); continue
  mt=META.get(r['sha256']); txt=head('D:/price-transparency/raw_national/'+mt['path'].replace('\\','/')) if mt and mt.get('path') else None
  zs=header_zips(txt,r['state']) if txt else set()
  dec='drop'; why='no address/zip in MRF header'
  if len(zs)>1: why=f'header lists {len(zs)} locations (system-wide file)'
  elif len(zs)==1:
    z=next(iter(zs))
    if z==r['zip'][:5]: dec='keep'; why=f'header zip {z} matches CCN zip'
    else:
      cands=BYZIP.get((r['state'],z),[])
      fn=([r['file_name'],(mt or {}).get('location_name') or ''])
      if len(cands)==1 and max(namesim(x,H[cands[0]]['name']) for x in fn)<0.5: why=f'header zip {z} -> {H[cands[0]]["name"]} but name does not match'; cands=[]
      if len(cands)==1:
        n=cands[0]; h=H[n]; dec='reassign'; why=f'header zip {z} -> sole CMS hospital {h["name"]}'
        r=dict(r,ccn=n,matched_name=h['name'],city=h['city'],zip=h['zip'],county=h['county'],cbsa=h['cbsa'] or '',cbsa_title=h['cbsa_title'] or '',type=h['type'])
      else: why=f'header zip {z} != CCN zip {r["zip"][:5]} ({len(cands)} CMS hospitals at {z})'
  cnt[dec]+=1; aud.append(dict(sha256=r['sha256'],file_name=r['file_name'],old_score=r['score'],method=r['method'],ccn=r['ccn'],name=r['matched_name'],decision=dec,reason=why))
  if dec=='drop': r=dict(r,ccn='',matched_name='',cbsa='',cbsa_title='',method='dropped:'+r['method'])
  else: r=dict(r,score='0.9' if dec!='keep' or float(r['score'])<0.9 else r['score'],method=r['method']+'+addr')
  out.append(r)
ts=time.strftime('%Y%m%dT%H%M%S')
w=csv.DictWriter(open(RN+f'file_ccn_map_{ts}.csv','w',newline='',encoding='utf-8'),fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(out)
w=csv.DictWriter(open(RN+f'match_resolution_{ts}.csv','w',newline='',encoding='utf-8'),fieldnames=list(aud[0].keys())); w.writeheader(); w.writerows(aud)
print(ts,dict(cnt)); print(collections.Counter(a['reason'].split(' (')[0][:40] for a in aud if a['decision']=='drop').most_common(6))