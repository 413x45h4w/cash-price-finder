import json,glob,os,urllib.request,urllib.parse
R=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OV={'mercys':'10010 Kennerly Rd, St. Louis, MO 63128','mercystl':'615 S New Ballas Rd, St. Louis, MO 63141','mercyw':'901 E 5th St, Washington, MO 63090','mercyj':'1400 US Highway 61, Festus, MO 63028','centerpointe':'4801 Weldon Spring Pkwy, St. Charles, MO 63304','touchette':'5900 Bond Ave, Cahokia Heights, IL 62207'}
SEC={'sunsethills':'12152 Tesson Ferry Rd, St. Louis, MO 63128','signature':'12639 Old Tesson Rd, St. Louis, MO 63128','specialt':'1823 Smizer Station Rd, Fenton, MO 63026','crhc':'456 N New Ballas Rd, St. Louis, MO 63141'}
out=json.load(open(R+'/ref/geocode.json')) if os.path.exists(R+'/ref/geocode.json') else {}
addrs=dict(SEC)
for f in glob.glob(R+'/parsed/20261023T114040_v2/*.meta.json'):
  i=os.path.basename(f)[:-10]; m=json.load(open(f)); a=OV.get(i) or str(m['header'].get('hospital_address','')).split('|')[0]; addrs[i]=a
for i,a in addrs.items():
  if i in out and out[i].get('lat'): continue
  u='https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?'+urllib.parse.urlencode(dict(address=a,benchmark='Public_AR_Current',format='json'))
  try:
    mm=json.load(urllib.request.urlopen(u,timeout=30))['result']['addressMatches']
    out[i]=dict(address=a,lat=mm[0]['coordinates']['y'],lon=mm[0]['coordinates']['x']) if mm else dict(address=a,lat=None,lon=None)
  except Exception as e: out[i]=dict(address=a,lat=None,lon=None,err=str(e))
  print(i,out[i])
json.dump(out,open(R+'/ref/geocode.json','w'),indent=1)
