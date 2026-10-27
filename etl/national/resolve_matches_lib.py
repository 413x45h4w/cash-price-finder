"""Resolve or drop low-confidence file->CCN matches (score<0.8 or manifest-own) using the MRF's own header (address/zip/location).
Usage: resolve_matches.py <map.csv> <parsed_dir>  -> writes new timestamped map + audit csv in ref_national."""
import csv,sys,json,glob,gzip,zipfile,re,io,time,sqlite3,collections

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
