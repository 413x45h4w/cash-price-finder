"""National streaming MRF parser (CSV tall/wide v2/v3, JSON v2/v3, gz, zip). Extracts only TARGET codes.
Usage: parse_national.py <outdir> [workers] [limit]   (resumable: skips files whose .meta.json exists in outdir)"""
import sys,os,csv,json,gzip,zipfile,io,time,sqlite3,re,traceback,multiprocessing as mp,tempfile,shutil
ROOT='D:/price-transparency'; RAW=ROOT+'/raw_national/'
sys.path.insert(0,ROOT+'/app/ref'); from target_codes import ALL,DRG
CPT={c for c in ALL if len(c)!=3}
csv.field_size_limit(2**31-1)
COLS=['provider','line','code_type','code','all_codes','description','setting','billing_class','modifiers','gross','cash','min','max','neg_min','neg_max','n_neg','methodologies','units','notes']
def norm(code,typ):
  c=str(code or '').strip().upper(); t=str(typ or '').strip().upper()
  if t in('MS-DRG','DRG','MSDRG','MS DRG'):
    d=c.lstrip('0').zfill(3)
    return ('MS-DRG',d) if d in DRG else None
  if t in('CPT','HCPCS','HCPCS/CPT','CPT/HCPCS') or (t=='' and len(c)==5):
    c=c[:5]
    return ('CPT' if c[:1].isdigit() else 'HCPCS',c) if c in CPT else None
  return None
def fnum(x):
  try:
    v=float(str(x).replace('$','').replace(',','').strip()); return v
  except: return None
class Agg:
  def __init__(s): s.items={}
  def add(s,key,base,neg,meth):
    it=s.items.get(key)
    if it is None: it=s.items[key]=dict(base,negs=[],meth=set())
    if neg is not None: it['negs'].append(neg)
    if meth: it['meth'].add(str(meth).strip().lower())
  def rows(s,pid):
    for it in s.items.values():
      n=it.pop('negs'); m=it.pop('meth'); hits=it.pop('hits')
      for ct,c in hits:
        yield dict(it,provider=pid,code_type=ct,code=c,neg_min=min(n) if n else '',neg_max=max(n) if n else '',n_neg=len(n),methodologies='|'.join(sorted(m)))
def open_text(fb):
  return io.TextIOWrapper(fb,encoding='utf-8-sig',errors='replace',newline='')
def parse_csv(fb,meta,agg):
  rd=csv.reader(open_text(fb)); head=None; pre=[]
  for i,row in enumerate(rd):
    low=[x.strip().lower() for x in row]
    if 'description' in low and any(x.startswith('code|') for x in low): head=low; break
    pre.append(row)
    if i>8: raise ValueError('nonstandard_csv: no description/code| header')
  if head is None: raise ValueError('nonstandard_csv: no header row (file too short)')
  if len(pre)>=2:
    h=dict(zip([x.strip().lower() for x in pre[0]],pre[1])); meta.update(hospital_name=h.get('hospital_name',''),version=h.get('version',''),location_name=h.get('location_name',''),last_updated_on=h.get('last_updated_on',''))
  ix={n:i for i,n in enumerate(head)}
  codes=[(ix[n],ix.get(n+'|type')) for n in head if re.fullmatch(r'code\|\d+',n)]
  g=lambda r,n: r[ix[n]] if n in ix and ix[n]<len(r) else ''
  wide_neg=[i for i,n in enumerate(head) if n.endswith('|negotiated_dollar') and n!='standard_charge|negotiated_dollar']
  tall='payer_name' in ix; meta['layout']='tall' if tall else 'wide'
  di=ix['description']; nrows=0
  for ln,r in enumerate(rd,start=len(pre)+2):
    nrows+=1; hits=[]; toks=[]
    for ci,ti in codes:
      if ci<len(r) and r[ci]:
        t=r[ti].strip().upper() if ti is not None and ti<len(r) else ''
        toks.append(f'{t}:{r[ci].strip()}'); h=norm(r[ci],t)
        if h and h not in hits: hits.append(h)
    if not hits: continue
    gross=g(r,'standard_charge|gross'); cash=g(r,'standard_charge|discounted_cash')
    base=dict(line=ln,all_codes=';'.join(toks),description=r[di] if di<len(r) else '',setting=g(r,'setting'),billing_class=g(r,'billing_class'),modifiers=g(r,'modifiers'),
      gross=fnum(gross) if gross else '',cash=fnum(cash) if cash else '',min=fnum(g(r,'standard_charge|min')) or '',max=fnum(g(r,'standard_charge|max')) or '',
      units=g(r,'drug_unit_of_measurement'),notes=g(r,'additional_generic_notes')[:300],hits=hits)
    key=(base['description'],base['all_codes'],base['setting'],base['billing_class'],base['modifiers'],gross,cash)
    if tall: agg.add(key,base,fnum(g(r,'standard_charge|negotiated_dollar')),g(r,'standard_charge|methodology'))
    else:
      agg.add(key,base,None,None)
      it=agg.items[key]
      for i in wide_neg:
        if i<len(r) and r[i]:
          v=fnum(r[i])
          if v is not None: it['negs'].append(v)
      for i,n in enumerate(head):
        if n.endswith('|methodology') and i<len(r) and r[i]: it['meth'].add(r[i].strip().lower())
  meta['rows']=nrows
def parse_json(fb,meta,agg):
  import ijson
  fb2=io.BufferedReader(fb,1<<20) if not isinstance(fb,io.BufferedReader) else fb
  head=fb2.peek(4096)[:4096].decode('utf-8','replace')
  for k in('hospital_name','version','last_updated_on'):
    m=re.search(r'"%s"\s*:\s*"([^"]*)"'%k,head)
    if m: meta[k]=m.group(1)
  n=0
  for prefix in('standard_charge_information.item',):
    for it in ijson.items(fb2,prefix,use_float=True):
      n+=1; ci=it.get('code_information') or []
      toks=[f"{str(c.get('type','')).upper()}:{c.get('code','')}" for c in ci]
      hits=[]
      for c in ci:
        h=norm(c.get('code'),c.get('type'))
        if h and h not in hits: hits.append(h)
      if not hits: continue
      dmu=(it.get('drug_information') or {}).get('unit','')
      for j,sc in enumerate(it.get('standard_charges') or []):
        mods=sc.get('modifier_code') or sc.get('modifiers') or ''
        if isinstance(mods,list): mods='|'.join(map(str,mods))
        base=dict(line=f'{n}.{j}',all_codes=';'.join(toks),description=it.get('description',''),setting=sc.get('setting',''),billing_class=sc.get('billing_class',''),modifiers=mods,
          gross=sc.get('gross_charge',''),cash=sc.get('discounted_cash',''),min=sc.get('minimum',''),max=sc.get('maximum',''),units=dmu,notes=str(sc.get('additional_generic_notes',''))[:300],hits=hits)
        key=(n,j); agg.add(key,base,None,None); x=agg.items[key]
        for p in sc.get('payers_information') or []:
          v=p.get('standard_charge_dollar')
          if v is not None:
            try: x['negs'].append(float(v))
            except: pass
          if p.get('methodology'): x['meth'].add(str(p['methodology']).lower())
  meta['rows']=n; meta['layout']='json'
def sniff(fb):
  b=fb.peek(2048)[:2048] if hasattr(fb,'peek') else b''
  s=b.lstrip(b'\xef\xbb\xbf \r\n\t')
  if s[:2]==b'PK': return 'zip'
  if s[:1] in(b'{',b'['): return 'json'
  if b'\xd0\xcf\x11\xe0'==s[:4]: return 'xls'
  return 'csv'
def work(job):
  sha,path,gz,outdir=job; key=sha[:16]; out=f'{outdir}/files/{key}.csv'; mf=f'{outdir}/files/{key}.meta.json'
  if os.path.exists(mf): return key,'skip',0
  t0=time.time(); meta=dict(sha256=sha,path=path,status='ok',error=''); agg=Agg(); tmp=None
  try:
    full=RAW+path
    fb=gzip.open(full,'rb') if gz else open(full,'rb'); fb=io.BufferedReader(fb,1<<22)
    k=sniff(fb); meta['format']=k
    if k=='zip':
      if gz:
        tmp=tempfile.mkdtemp(dir=ROOT+'/tmp_parse'); zp=tmp+'/f.zip'
        with open(zp,'wb') as o: shutil.copyfileobj(fb,o,1<<24)
        fb.close(); z=zipfile.ZipFile(zp)
      else: fb.close(); z=zipfile.ZipFile(full)
      mem=[i for i in z.infolist() if not i.is_dir() and i.filename.lower().rsplit('.',1)[-1] in('csv','json','txt')]
      if not mem: raise ValueError('zip without csv/json: '+','.join(i.filename for i in z.infolist())[:200])
      meta['zip_members']=[i.filename for i in mem]
      for i in mem:
        f2=io.BufferedReader(z.open(i),1<<22); k2=sniff(f2)
        (parse_json if k2=='json' else parse_csv)(f2,meta,agg)
    elif k=='json': parse_json(fb,meta,agg)
    elif k=='xls': raise ValueError('unsupported: excel')
    else: parse_csv(fb,meta,agg)
  except Exception as e:
    meta.update(status='fail',error=f'{type(e).__name__}: {str(e)[:300]}')
  finally:
    if tmp: shutil.rmtree(tmp,ignore_errors=True)
  rows=list(agg.rows(key)); meta['hits']=len(rows)
  if rows and meta['status']=='fail': meta['status']='partial'
  with open(out+'.tmp','w',newline='',encoding='utf-8') as o:
    w=csv.DictWriter(o,COLS,extrasaction='ignore'); w.writeheader(); w.writerows(rows)
  os.replace(out+'.tmp',out)
  meta['seconds']=round(time.time()-t0,1); json.dump(meta,open(mf,'w'))
  return key,meta['status'],meta['seconds']
def jobs(outdir):
  c=sqlite3.connect('file:'+RAW+'manifest.sqlite?mode=ro',uri=True)
  best={}
  for sha,sp,gz,b,run in c.execute("select sha256,stored_path,stored_gzip,bytes_orig,run from manifest where error='' and sha256!='' and stored_path like '2026%' order by run"):
    if os.path.exists(RAW+sp): best[sha]=(sha,sp,gz,b or 0)
  L=sorted(best.values(),key=lambda x:-x[3])
  return [(s,p,g,outdir) for s,p,g,b in L]
if __name__=='__main__':
  outdir=sys.argv[1]; W=int(sys.argv[2]) if len(sys.argv)>2 else 14
  os.makedirs(outdir+'/files',exist_ok=True); os.makedirs(ROOT+'/tmp_parse',exist_ok=True)
  J=jobs(outdir)
  if len(sys.argv)>3: J=J[-int(sys.argv[3]):]
  log=open(outdir+'/parse.log','a',buffering=1); log.write(f'{time.ctime()} start {len(J)} files W={W}\n')
  st={'ok':0,'fail':0,'partial':0,'skip':0}
  with mp.Pool(W,maxtasksperchild=20) as P:
    for i,(k,s,sec) in enumerate(P.imap_unordered(work,J,chunksize=1)):
      st[s]=st.get(s,0)+1; log.write(f'{time.ctime()} {i+1}/{len(J)} {k} {s} {sec}s\n')
      json.dump(dict(done=i+1,total=len(J),**st,updated=time.ctime()),open(outdir+'/status.json','w'))
  log.write(f'{time.ctime()} done {st}\n')