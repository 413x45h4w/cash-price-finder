"""cms-hpt.txt crawler keyed by CCN (scaling path).
Input: CSV with ccn,name,domain,metro,cbsa (build from CMS Provider of Services + CBSA crosswalk).
For each domain: GET https://<domain>/cms-hpt.txt -> parse 'location-name / source-page-url / mrf-url / contact' blocks,
download each MRF (append-only: raw/<UTC-stamp>/<ccn>_<n>.bin + .headers, never overwrite), parse with parse_mrf.py,
write normalized CSV to parsed/<stamp>/, append fetch log. Raw files are then shipped off-box to
D:\\price-transparency\\raw\\<stamp>\\ (gzip -> tar -> 40 MB parts -> CopyFromBox -> reassemble + sha256 verify) and deleted locally.
Usage: python3 etl/crawl_hpt.py hospitals.csv [--limit N]"""
import csv,sys,os,json,time,urllib.request,subprocess,datetime,hashlib
R=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def hpt(domain):
  for u in(f'https://{domain}/cms-hpt.txt',f'https://www.{domain}/cms-hpt.txt'):
    try:
      t=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0 price-transparency-research'}),timeout=30).read().decode('utf-8','replace')
      blocks=[];cur={}
      for line in t.splitlines():
        if ':' in line:
          k,v=line.split(':',1); k=k.strip().lower(); v=v.strip()
          if k=='location-name' and cur: blocks.append(cur); cur={}
          cur[k]=v
      if cur: blocks.append(cur)
      return u,blocks
    except Exception as e: err=str(e)
  return None,[]
def main(src,limit=None):
  stamp=datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%S'); raw=f'{R}/raw/{stamp}'; out=f'{R}/parsed/{stamp}'; os.makedirs(raw); os.makedirs(out,exist_ok=True); log=[]
  for i,h in enumerate(csv.DictReader(open(src))):
    if limit and i>=limit: break
    u,bl=hpt(h['domain'])
    for n,b in enumerate(bl):
      mrf=b.get('mrf-url'); 
      if not mrf: continue
      f=f"{raw}/{h['ccn']}_{n}.bin"; assert not os.path.exists(f)
      r=subprocess.run(['curl','-sSL','-A','Mozilla/5.0','-D',f[:-4]+'.headers','-o',f,'-w','%{http_code}',mrf],capture_output=True,text=True)
      log.append(dict(ccn=h['ccn'],hpt=u,location=b.get('location-name'),source_page=b.get('source-page-url'),mrf=mrf,http=r.stdout,bytes=os.path.getsize(f) if os.path.exists(f) else 0,sha256=hashlib.sha256(open(f,'rb').read()).hexdigest() if os.path.exists(f) else None))
      if r.stdout=='200': subprocess.run([sys.executable,R+'/parse_mrf.py',f,f"{h['ccn']}_{n}",out])
  json.dump(log,open(f'{raw}/_fetch_log.json','w'),indent=1); print(raw)
if __name__=='__main__': main(sys.argv[1],int(sys.argv[3]) if '--limit' in sys.argv else None)
