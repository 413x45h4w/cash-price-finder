"""Medicare benchmark per (metro-state part, code). Facility + professional + combined; fair cash = 80% of Medicare full allowed amount."""
import csv,sys,os,json
R=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,R+'/ref')
from target_codes import ALL
M=R+'/ref/medicare/'
# Locality config: one row per metro part. Scaling: generate from CBSA->locality crosswalk (26LOCCO) + Table 2/3.
LOC={'stl-MO':dict(metro='stl',state='MO',cbsa='41180',pfs_loc='MO-01',gpci=(1.000,0.952,1.002),anes_cf=20.36,opps_wi=0.9673,ipps_wi=0.9505,gaf=0.9658),
     'stl-IL':dict(metro='stl',state='IL',cbsa='41180',pfs_loc='IL-12',gpci=(1.000,0.920,2.014),anes_cf=21.63,opps_wi=1.0815,ipps_wi=1.1719,gaf=1.1147)}
ANES_BASE={'00811':4,'00812':3,'00813':5,'00731':5,'01402':7,'01400':4,'00790':7,'00142':4}
ANES_MIN={'00811':30,'00812':30,'00813':40,'00731':20,'01402':120,'01400':60,'00790':90,'00142':20}  # assumed typical minutes
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
def pf(code,mod,L,fac):
  x=pfs.get((code,mod))
  if not x or x['st'] not in('A','R','T','C'): return None
  w,pe,mp=L['gpci']; v=(x['work']*w+(x['pe_f'] if fac else x['pe_nf'])*pe+x['mp']*mp)*x['cf']
  return round(v,2) if v>0 else None
def opps_adj(code,L):
  o=opps.get(code); return round(o['rate']*(0.6*L['opps_wi']+0.4),2) if o and o['rate'] else None
SEP={'S','T','J1','J2','Q1','Q2','Q3','V','R','U','P'}
PROXY={'99243':'99203','99244':'99204','99385':'99203','99386':'99204'}
rows=[]
for lk,L in LOC.items():
  for code,desc in ALL.items():
    r=dict(loc=lk,metro=L['metro'],state=L['state'],cbsa=L['cbsa'],code=code,desc=desc,code_type='MS-DRG' if len(code)==3 else 'CPT/HCPCS',facility=None,professional=None,office=None,basis='',note='')
    if code in drgw:
      wt,t=drgw[code]; op=(4519.68*L['ipps_wi']+2328.32) if L['ipps_wi']>1 else (4245.76*L['ipps_wi']+2602.24)
      r['facility']=round(wt*(op+539.95*L['gaf']),2); r['basis']=f'IPPS FY2027 CN: DRG wt {wt} x (wage-adj operating std amt + capital x GAF)'; r['note']='Excludes IME/DSH/outlier; professional fees billed separately'
    elif code in ANES_BASE:
      u=ANES_BASE[code]+ANES_MIN[code]/15; r['professional']=round(u*L['anes_cf'],2); r['basis']=f'PFS anesthesia: ({ANES_BASE[code]} base + {ANES_MIN[code]} min/15) x CF {L["anes_cf"]}'; r['note']='Base units from CMS anesthesia base-unit list; time assumed'
    else:
      o=opps.get(code,{}); si=o.get('si','')
      if code in clfs: r['facility']=clfs[code]; r['basis']='CLFS 2026 Q4 (national limit)'
      elif si in SEP: r['facility']=opps_adj(code,L); r['basis']=f'OPPS Oct-2026 APC {o.get("apc")} SI {si}, wage-adj (0.6xWI+0.4)'
      elif si in('A','M') or code.startswith('99') or code.startswith('908'):
        pass
      elif si=='N': r['note']='Packaged into primary service under OPPS ($0 separate)'; r['facility']=0.0; r['basis']='OPPS packaged (SI N)'
      if (code,'26') in pfs: r['professional']=pf(code,'26',L,True)
      elif r['basis'].startswith('CLFS'): pass
      else: r['professional']=pf(code,'',L,True)
      r['office']=pf(code,'',L,False)
      if code[:3] in('992','993') and code not in('99281','99282','99283','99284','99285') and si in('B','E1',''):
        r['facility']=opps_adj('G0463',L); r['basis']='Hospital clinic: OPPS G0463 + PFS facility rate'
      if si in('A','M') and r['facility'] is None:
        r['basis']='PFS global (paid under physician fee schedule in all settings)'; r['facility']=r['office']; r['professional']=None
    tot=sum(x for x in(r['facility'],r['professional']) if x)
    r['combined']=round(tot,2) if tot else (r['office'] or None)
    for k in('facility','professional','combined','office'): r['fair_'+k]=round(r[k]*0.8,2) if r[k] else None
    if code in PROXY:
      pr=pf(PROXY[code],'',L,True); r['professional']=pr; r['office']=pf(PROXY[code],'',L,False)
      r['note']=f'Medicare does not pay this code; priced as {PROXY[code]} (same visit level)'
      r['combined']=round((r['facility'] or 0)+(pr or 0),2)
      for k in('facility','professional','combined','office'): r['fair_'+k]=round(r[k]*0.8,2) if r[k] else None
    if r['combined'] is None and not r['note']: r['note']='No Medicare rate found in 2026/FY2027 files (code deleted, renumbered, or not covered)'
    rows.append(r)
os.makedirs(R+'/app/data',exist_ok=True)
json.dump(rows,open(R+'/app/data/benchmarks.json','w'),indent=0)
if __name__=='__main__':
  for r in rows:
    if r['state']=='MO': print(r['code'],r['desc'][:28].ljust(28),r['facility'],r['professional'],r['combined'],'|',r['basis'][:50])
