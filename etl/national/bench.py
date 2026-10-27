"""Medicare benchmarks for any location. Same formulas as app/etl/benchmarks.py (STL), parameterized:
OPPS wage index (CY2026 OPPS uses FY2026 IPPS WI), IPPS FY2027 WI + GAF, PFS GPCI by MAC locality (ZIP5 crosswalk), CLFS national."""
import csv,sys,os,statistics as S,collections
ROOT='D:/price-transparency'; sys.path.insert(0,ROOT+'/app/ref'); from target_codes import ALL
M=ROOT+'/app/ref/medicare/'; RN=ROOT+'/ref_national/'
ANES_BASE={'00811':4,'00812':3,'00813':5,'00731':5,'01402':7,'01400':4,'00790':7,'00142':4}
ANES_MIN={'00811':30,'00812':30,'00813':40,'00731':20,'01402':120,'01400':60,'00790':90,'00142':20}
opps={}
for line in open(M+'oct2026-addb/508-compliant-version-2026_October_Web_Addendum_B.10.14.26.txt',encoding='latin-1'):
  p=line.rstrip('\n').split('\t')
  if len(p)>5 and (p[0].strip() in ALL or p[0].strip()=='G0463'):
    r=p[5].replace('$','').replace(',','').replace('"','').strip()
    opps[p[0].strip()]=dict(si=p[2].strip(),apc=p[3].strip(),rate=float(r) if r else None)
clfs={}
for r in csv.reader(open(M+'26clabq4/PUF_CLFS_CY2026_Q4V1.csv',encoding='latin-1')):
  if len(r)>5 and r[1] in ALL and r[2]=='': clfs[r[1]]=float(r[5])
pfs={}
for r in csv.reader(open(M+'rvu26d-updated-08-26-2026/PPRRVU2026_Oct_nonQPP.csv',encoding='latin-1')):
  if len(r)>25 and r[0] in ALL and r[1] in('','26','TC'):
    f=lambda x: float(x) if x.strip() not in('','NA') else 0.0
    pfs[(r[0],r[1])]=dict(st=r[3],work=f(r[5]),pe_nf=f(r[6]),pe_f=f(r[8]),mp=f(r[10]),cf=float(r[25]),desc=r[2])
drgw={}
for line in open(M+'fy2027-ipps-fr-table-5/CMS-1849-CN Table 5.txt',encoding='latin-1'):
  p=line.split('\t')
  if p[0].strip() in ALL: drgw[p[0].strip()]=(float(p[7]),p[5].strip())
# geography
T2={}
for line in open(M+'fy2027-ipps-fr-tables-2-3-4a-4b/CMS-1849-CN Table 2.txt',encoding='latin-1'):
  p=line.rstrip('\n').split('\t')
  if len(p)>12 and p[0].strip().isdigit() and len(p[0].strip())==6:
    try: T2[p[0].strip()]=dict(wi26=float(p[2]),wi27=float(p[5]),cbsa=p[11].strip(),county=p[17].strip())
    except: pass
T3={}
for line in open(M+'fy2027-ipps-fr-tables-2-3-4a-4b/CMS-1849-CN Table 3.txt',encoding='latin-1'):
  p=line.rstrip('\n').split('\t')
  if len(p)>8 and p[0].strip().isdigit():
    try: T3[(p[0].strip(),p[2].strip())]=dict(wi=float(p[6]),gaf=float(p[7]),scode=p[3].strip())
    except: pass
SCODE={v['scode']:st for (cb,st),v in T3.items()}
ZIP={}
for line in open(RN+'zl/ZIP5_OCT2026.txt',encoding='latin-1'):
  if len(line)>14: ZIP[line[2:7]]=(line[7:12],line[12:14])
GPCI={}
for r in csv.reader(open(M+'rvu26d-updated-08-26-2026/GPCI2026.csv',encoding='latin-1')):
  if len(r)>6 and r[0].strip().isdigit():
    try: GPCI[(r[0].strip(),r[2].strip())]=dict(name=r[3].strip(),g=(float(r[4]),float(r[5]),float(r[6])))
    except: pass
ANES={}
for r in csv.reader(open(M+'rvu26d-updated-08-26-2026/ANES2026.csv',encoding='latin-1')):
  if len(r)>4 and r[0].strip().isdigit():
    try: ANES[(r[0].strip(),r[1].strip())]=float(r[4])
    except: pass
GEO={}
for line in open(RN+'gz/2024_Gaz_zcta_national.txt',encoding='latin-1'):
  p=line.split('\t')
  if p[0].isdigit(): GEO[p[0]]=(float(p[5]),float(p[6]))
def state_wi(state):
  sc=[k for k,v in SCODE.items() if v==state]
  return T3.get((sc[0],state)) if sc else None
def part_params(cbsa,state,ccns,zips):
  t3=T3.get((cbsa,state)) or state_wi(state) or dict(wi=1.0,gaf=1.0)
  w26=[T2[c]['wi26'] for c in ccns if c in T2 and T2[c]['cbsa']==cbsa] or [T2[c]['wi26'] for c in ccns if c in T2]
  locs=collections.Counter(ZIP[z] for z in zips if z in ZIP)
  loc=locs.most_common(1)[0][0] if locs else None
  g=GPCI.get(loc) if loc else None
  return dict(opps_wi=round(S.median(w26),4) if w26 else t3['wi'],ipps_wi=t3['wi'],gaf=t3['gaf'],gpci=g['g'] if g else (1.0,1.0,1.0),
    pfs_loc=(f"{loc[0]}-{loc[1]} {g['name']}" if g else 'national (no locality)'),anes_cf=ANES.get(loc,20.50) if loc else 20.50)
def hosp_ipps(ccn):
  t=T2.get(ccn); return (t['wi27'],round(t['wi27']**0.6848,4)) if t else None
def pf(code,mod,L,fac):
  x=pfs.get((code,mod))
  if not x or x['st'] not in('A','R','T','C'): return None
  w,pe,mp=L['gpci']; v=(x['work']*w+(x['pe_f'] if fac else x['pe_nf'])*pe+x['mp']*mp)*x['cf']
  return round(v,2) if v>0 else None
def opps_adj(code,L):
  o=opps.get(code); return round(o['rate']*(0.6*L['opps_wi']+0.4),2) if o and o['rate'] else None
def drg_amt(wt,wi,gaf):
  op=(4519.68*wi+2328.32) if wi>1 else (4245.76*wi+2602.24); return round(wt*(op+539.95*gaf),2)
SEP={'S','T','J1','J2','Q1','Q2','Q3','V','R','U','P'}
PROXY={'99243':'99203','99244':'99204','99385':'99203','99386':'99204'}
def rows_for(lk,metro,state,cbsa,L,drg_only=False,label=''):
  out=[]
  for code,desc in ALL.items():
    if drg_only and code not in drgw: continue
    r=dict(lk=lk,loc=lk,metro=metro,state=state,cbsa=cbsa,code=code,description=desc,code_type='MS-DRG' if len(code)==3 else 'CPT/HCPCS',facility=None,professional=None,office=None,basis='',note='')
    if code in drgw:
      wt,t=drgw[code]; r['facility']=drg_amt(wt,L['ipps_wi'],L['gaf']); r['basis']=f'IPPS FY2027: DRG wt {wt} x (wage-adj operating std amt, WI {L["ipps_wi"]}{label} + capital x GAF {L["gaf"]})'; r['note']='Excludes IME/DSH/outlier; professional fees billed separately'
    elif code in ANES_BASE:
      u=ANES_BASE[code]+ANES_MIN[code]/15; r['professional']=round(u*L['anes_cf'],2); r['basis']=f'PFS anesthesia: ({ANES_BASE[code]} base + {ANES_MIN[code]} min/15) x CF {L["anes_cf"]} ({L["pfs_loc"]})'; r['note']='Base units from CMS anesthesia base-unit list; time assumed'
    else:
      o=opps.get(code,{}); si=o.get('si','')
      if code in clfs: r['facility']=clfs[code]; r['basis']='CLFS 2026 Q4 (national limit)'
      elif si in SEP: r['facility']=opps_adj(code,L); r['basis']=f'OPPS Oct-2026 APC {o.get("apc")} SI {si}, wage-adj (0.6xWI {L["opps_wi"]}+0.4); PFS locality {L["pfs_loc"]}'
      elif si=='N': r['note']='Packaged into primary service under OPPS ($0 separate)'; r['facility']=0.0; r['basis']='OPPS packaged (SI N)'
      if (code,'26') in pfs: r['professional']=pf(code,'26',L,True)
      elif r['basis'].startswith('CLFS'): pass
      else: r['professional']=pf(code,'',L,True)
      r['office']=pf(code,'',L,False)
      if code[:3] in('992','993') and code not in('99281','99282','99283','99284','99285') and si in('B','E1',''):
        r['facility']=opps_adj('G0463',L); r['basis']=f'Hospital clinic: OPPS G0463 + PFS facility rate ({L["pfs_loc"]})'
      if si in('A','M') and r['facility'] is None:
        r['basis']=f'PFS global (paid under physician fee schedule in all settings; {L["pfs_loc"]})'; r['facility']=r['office']; r['professional']=None
    tot=sum(x for x in(r['facility'],r['professional']) if x)
    r['combined']=round(tot,2) if tot else (r['office'] or None)
    if code in PROXY:
      pr=pf(PROXY[code],'',L,True); r['professional']=pr; r['office']=pf(PROXY[code],'',L,False)
      r['note']=f'Medicare does not pay this code; priced as {PROXY[code]} (same visit level)'
      r['combined']=round((r['facility'] or 0)+(pr or 0),2)
    if r['combined'] is None and not r['note']: r['note']='No Medicare rate found in 2026/FY2027 files (code deleted, renumbered, or not covered)'
    out.append(r)
  return out
if __name__=='__main__':
  L=part_params('41180','MO',['260032'],['63110']); print(L)
  L2=part_params('41180','IL',['140145'],['62226']); print(L2)
  for r in rows_for('MO','stl','MO','41180',L):
    if r['code'] in('45385','470','73721','00811','80053','99213'): print(r['code'],r['facility'],r['professional'],r['combined'])