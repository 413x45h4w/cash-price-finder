import csv,glob,os,json,sqlite3,statistics as S,collections,importlib.util,datetime
R=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sp=importlib.util.spec_from_file_location('p',R+'/providers.py'); P=importlib.util.module_from_spec(sp); sp.loader.exec_module(P)
PARSED=R+'/parsed/20261023T114040_v2'; VINT='20261023T114040'
IL={'amh','anderson','carlinville','gateway','hshshf','hshsse','hshssj1','hshssj2','jersey','mhb','osfsa','staunton','touchette'}
GEO=json.load(open(R+'/ref/geocode.json')); BM=json.load(open(R+'/app/data/benchmarks.json'))
SEC=json.load(open(R+'/ref/secondary_providers.json'))
db=R+'/app/data/prices.sqlite'
if os.path.exists(db): os.remove(db)
c=sqlite3.connect(db); c.executescript('''
create table metros(metro text primary key,name text,cbsa text,states text);
create table providers(id text primary key,metro text,ccn text,name text,type text,city text,state text,system text,address text,lat real,lon real,page_url text,file_url text,file_format text,vintage text,last_updated text,note text);
create table prices(provider_id text,code text,code_type text,description text,setting text,cash real,cash_min real,cash_max real,n_lines int,gross real,all_inclusive int,flag text);
create table benchmarks(loc text,metro text,state text,code text,code_type text,description text,facility real,professional real,combined real,office real,fair_facility real,fair_professional real,fair_combined real,fair_office real,basis text,note text);
create table episodes(id text primary key,name text,aliases text,primary_code text,components text,description text);
create table meta(k text primary key,v text);''')
c.execute("insert into metros values('stl','St. Louis, MO-IL','41180','MO,IL')")
for b in BM: c.execute('insert into benchmarks values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',[b[k] for k in('loc','metro','state','code','code_type','desc','facility','professional','combined','office','fair_facility','fair_professional','fair_combined','fair_office','basis','note')])
B={(b['state'],b['code']):b for b in BM}
for p in P.P:
  pid,ccn,name,city,system,page,mrf=p; m=json.load(open(f'{PARSED}/{pid}.meta.json')); h=m.get('header',{}); g=GEO.get(pid,{})
  st='IL' if pid in IL else 'MO'
  c.execute('insert into providers values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(pid,'stl',ccn,name,'Hospital',city,st,system,g.get('address'),g.get('lat'),g.get('lon'),page,mrf,m.get('format'),VINT,str(h.get('last_updated_on','')),None))
  per=collections.defaultdict(list)
  for r in csv.DictReader(open(f'{PARSED}/{pid}.csv')):
    try: cash=float(r['cash'])
    except: continue
    if cash<=0: continue
    if r['code_type']=='MS-DRG':
      if r['setting'] not in('inpatient','both'): continue
    else:
      if r['code'] in('59400','59510','59610'): pass
      elif r['billing_class']=='professional': continue
      elif r['setting']=='inpatient': continue
      if r['modifiers'] and r['modifiers'] not in('TC',): continue
    per[(r['code'],r['code_type'])].append((cash,float(r['gross']) if r['gross'] else None,r['description']))
  for (code,ct),v in per.items():
    cs=[x[0] for x in v]; gs=[x[1] for x in v if x[1]]
    c.execute('insert into prices values(?,?,?,?,?,?,?,?,?,?,?,?)',(pid,code,'MS-DRG' if ct=='MS-DRG' else 'CPT/HCPCS',v[0][2][:200],'inpatient' if ct=='MS-DRG' else 'outpatient',round(S.median(cs),2),min(cs),max(cs),len(cs),round(S.median(gs),2) if gs else None,0,None))
for s in SEC:
  g=GEO.get(s['id'],{})
  c.execute('insert into providers values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(s['id'],'stl',None,s['name'],s['type'],s['city'],s['state'],None,g.get('address'),g.get('lat'),g.get('lon'),s['page'],s['page'],s['format'],'2026-10-23 (web)',None,s['note']))
  for code,pr in s['prices']:
    c.execute('insert into prices values(?,?,?,?,?,?,?,?,?,?,?,?)',(s['id'],code,'episode' if code.startswith('EP:') else 'CPT/HCPCS',s['note'],'outpatient',pr,pr,pr,1,None,1,None))
# low-price flags (facility-only hospital lines)
med={k:S.median([x[0] for x in v]) for k,v in collections.defaultdict(list,{}).items()}
rows=c.execute('select rowid,provider_id,code,cash from prices where all_inclusive=0').fetchall()
bycode=collections.defaultdict(list)
for _,_,code,cash in rows: bycode[code].append(cash)
for rid,pid,code,cash in rows:
  st='IL' if pid in IL else 'MO'; b=B.get((st,code)); fl=[]
  if b and b['facility'] and b['facility']>100 and cash<0.5*b['facility']: fl.append(f"below 50% of Medicare facility rate (${b['facility']:,.0f})")
  if len(bycode[code])>=4 and cash<0.25*S.median(bycode[code]): fl.append('under 25% of metro median')
  if fl: c.execute('update prices set flag=? where rowid=?',('Implausibly low single line - likely not the full service: '+'; '.join(fl),rid))
EP=[
 ('mri_knee','MRI of the knee (no contrast) incl. radiologist read','mri knee,knee mri','73721',[['73721','facility+professional']],'Facility (technical) + radiologist read.'),
 ('mri_lumbar','MRI lower back (no contrast) incl. read','mri back,lumbar mri,mri spine,back mri','72148',[['72148','facility+professional']],'Facility + read.'),
 ('mri_brain_contrast','MRI brain with & without contrast incl. contrast and read','mri brain,brain mri,head mri','70553',[['70553','facility+professional'],['A9579','contrast',1],['A9585','contrast',1]],'Facility + gadolinium (packaged under Medicare) + read.'),
 ('ct_abd_contrast','CT abdomen & pelvis with contrast incl. read','ct abdomen,ct scan belly,cat scan abdomen','74177',[['74177','facility+professional'],['Q9967','contrast',1]],'Facility + contrast (packaged) + read.'),
 ('colonoscopy','Colonoscopy (screening/diagnostic) all-in: facility, gastroenterologist, anesthesia','colonoscopy,screening colonoscopy,colon screening','45378',[['45378','facility+professional'],['00812','anesthesia']],'Facility + physician + MAC anesthesia (00812). Add pathology if biopsy.'),
 ('colonoscopy_biopsy','Colonoscopy with biopsy all-in: facility, physician, anesthesia, pathology','colonoscopy biopsy,colonoscopy polyp','45380',[['45380','facility+professional'],['00811','anesthesia'],['88305','pathology']],'Facility + physician + anesthesia (00811) + pathology (88305).'),
 ('egd_biopsy','Upper endoscopy (EGD) with biopsy all-in','egd,upper endoscopy,scope stomach','43239',[['43239','facility+professional'],['00731','anesthesia'],['88305','pathology']],'Facility + physician + anesthesia + pathology.'),
 ('cataract','Cataract surgery with lens, all-in','cataract','66984',[['66984','facility+professional'],['00142','anesthesia']],'Facility + surgeon + anesthesia.'),
 ('knee_scope','Knee arthroscopy / meniscectomy, all-in','knee arthroscopy,meniscus,knee scope','29881',[['29881','facility+professional'],['01400','anesthesia']],'Facility + surgeon + anesthesia.'),
 ('lap_chole','Gallbladder removal (laparoscopic), all-in','gallbladder,cholecystectomy','47562',[['47562','facility+professional'],['00790','anesthesia'],['88305','pathology']],'Facility + surgeon + anesthesia + pathology.'),
 ('tka_inpatient','Total knee replacement (inpatient DRG 470) all-in','knee replacement,total knee,tka','470',[['470','facility'],['27447','professional'],['01402','anesthesia']],'Hospital DRG 470 + surgeon (27447) + anesthesia (01402).'),
 ('vaginal_birth','Vaginal delivery (DRG 807) + global OB care','childbirth,delivery,having a baby,vaginal birth','807',[['807','facility'],['59400','professional']],'Hospital DRG 807 + obstetrician global (59400). Newborn care not included.'),
 ('csection','C-section (DRG 788) + global OB care','c-section,cesarean','788',[['788','facility'],['59510','professional']],'Hospital DRG 788 + obstetrician global (59510). Newborn not included.'),
]
for e in EP: c.execute('insert into episodes values(?,?,?,?,?,?)',(e[0],e[1],e[2],e[3],json.dumps(e[4]),e[5]))
c.execute("insert into meta values('vintage',?)",(f'Hospital MRFs fetched {VINT[:4]}-{VINT[4:6]}-{VINT[6:8]}; Medicare: OPPS Add. B Oct-2026, PFS 2026 RVU26D, CLFS 2026 Q4, IPPS FY2027 CN; secondary sites checked 2026-10-23',))
c.commit(); print(c.execute('select count(*) from prices').fetchone(), c.execute('select count(*) from prices where flag is not null').fetchone())
