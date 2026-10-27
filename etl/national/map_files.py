"""Map each unique MRF (sha256) to a CMS hospital (CCN, CBSA). Uses manifest ccn when the file names that hospital,
else fuzzy-matches the MRF location_name / header hospital_name against hospitals in the same system domain, then same state."""
import sqlite3,re,difflib,csv,json,os,sys,glob,collections,time
ROOT='D:/price-transparency'; PARSED=sys.argv[1] if len(sys.argv)>1 else ''
c=sqlite3.connect('file:'+ROOT+'/raw_national/manifest.sqlite?mode=ro',uri=True)
H={}
for r in c.execute('select ccn,name,city,state,zip,county,type,cbsa,cbsa_title,domain from hospitals order by run'):
  H[r[0]]=dict(zip(['ccn','name','city','state','zip','county','type','cbsa','cbsa_title','domain'],r))
STOP={'the','of','and','inc','llc','hospital','hospitals','medical','center','centre','health','healthcare','system','campus','regional','memorial','community','general','university','dba','a','at','mc','hosp','ctr','med','facility','location','standard','charges','standardcharges'}
SYN={'saint':'st','st.':'st','mt':'mount','ft':'fort','childrens':'children','children\'s':'children'}
def toks(s):
  s=re.sub(r'[^a-z0-9 ]',' ',str(s).lower().replace("'",''))
  return [SYN.get(w,w) for w in s.split() if w not in STOP and not w.isdigit()]
import math
DF=collections.Counter(w for h in H.values() for w in set(toks(h['name'])))
IDF=lambda w: math.log(len(H)/(1+DF.get(w,0)))+0.5
def sim(a,b):   # a=file name, b=CMS name; IDF-weighted overlap
  sa,sb=set(toks(a)),set(toks(b))
  if not sa or not sb: return 0
  wi=sum(IDF(w) for w in sa&sb); wu=sum(IDF(w) for w in sa|sb); j=wi/wu
  if sa<=sb and j>=0.4: return max(j,0.66)
  return j
by_dom=collections.defaultdict(list); by_state=collections.defaultdict(list)
for h in H.values(): by_dom[h['domain']].append(h); by_state[h['state']].append(h)
meta={}
if PARSED:
  for f in glob.glob(PARSED+'/files/*.meta.json'):
    m=json.load(open(f)); meta[m['sha256']]=m
rows=c.execute("select sha256,run,ccn,hospital_name,state,cbsa,domain,location_name,mrf_url,stored_path from manifest where error='' and sha256!='' order by run").fetchall()
F=collections.defaultdict(list)
for r in rows: F[r[0]].append(r)
out=[]
for sha,R in F.items():
  names=[x for x in {r[7] for r in R}|{meta.get(sha,{}).get('hospital_name','')} if x and str(x).strip()]
  url=R[-1][8]; fn=re.sub(r'[_\-]+',' ',os.path.basename(url.split('?')[0]).rsplit('.',1)[0]); fn=re.sub(r'^\d{9}\s*','',fn)
  names=[n if isinstance(n,str) else str(n) for n in names]+[fn]
  best=(0,None,'')
  for r in R:   # manifest hospital itself
    if r[2] in H:
      s=max(sim(n,H[r[2]]['name']) for n in names)
      if len(F[sha])==1 and len({x[2] for x in R})==1 and len([1 for x in rows if False])==0: pass
      if s>best[0]: best=(s,r[2],'manifest')
  if best[0]<0.65:
    cand={h['ccn']:h for r in R for h in by_dom.get(r[6],[])}
    for st in {r[4] for r in R}: cand.update({h['ccn']:h for h in by_state.get(st,[])})
    for h in cand.values():
      s=max(sim(n,h['name']) for n in names)
      if s>best[0]+0.02: best=(s,h['ccn'],'fuzzy')
  # single-file hospital with ccn: accept even if names differ (own file)
  own=[r for r in R if r[2] in H]
  if best[0]<0.65 and own and len(by_dom.get(own[0][6],[]))<=1 and len({r[2] for r in R})==1 and len(names)<=2: best=(0.65,own[0][2],'manifest-own')
  ok=best[0]>=0.65
  h=H.get(best[1],{}) if ok else {}
  out.append(dict(sha256=sha,run=R[-1][1],stored_path=[r[9] for r in R if r[9].startswith('2026')][-1] if any(r[9].startswith('2026') for r in R) else '',
    file_name=names[0][:120],ccn=h.get('ccn',''),matched_name=h.get('name',''),score=round(best[0],3),method=best[2] if ok else 'unmatched',
    city=h.get('city',''),state=h.get('state',''),zip=h.get('zip',''),county=h.get('county',''),cbsa=h.get('cbsa',''),cbsa_title=h.get('cbsa_title',''),type=h.get('type','')))
ts=time.strftime('%Y%m%dT%H%M%S'); fo=f'{ROOT}/ref_national/file_ccn_map_{ts}.csv'
w=csv.DictWriter(open(fo,'w',newline='',encoding='utf-8'),list(out[0])); w.writeheader(); w.writerows(out)
print(fo,len(out),collections.Counter(o['method'] for o in out))
m=[o for o in out if o['ccn']]; print('ccns',len({o['ccn'] for o in m}),'cbsas',len({o['cbsa'] for o in m if o['cbsa']}))
import random; random.seed(3)
for o in random.sample(m,25): print(o['score'],o['method'],'|',o['file_name'][:50],'=>',o['matched_name'],o['state'])