import sqlite3,json,os
R=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); S=R+'/site/data'
c=sqlite3.connect(R+'/app/data/prices.sqlite'); c.row_factory=sqlite3.Row
Q=lambda s,a=():[dict(x) for x in c.execute(s,a)]
metros=Q('select * from metros'); vint=Q("select v from meta where k='vintage'")[0]['v']
json.dump(dict(metros=metros,vintage=vint),open(S+'/meta.json','w'),separators=(',',':'))
for m in metros:
  M=m['metro']; d=f'{S}/{M}'; os.makedirs(d,exist_ok=True)
  w=lambda n,o: json.dump(o,open(f'{d}/{n}.json','w'),separators=(',',':'))
  w('providers',Q('select * from providers where metro=?',(M,)))
  w('prices',Q('select p.* from prices p join providers v on v.id=p.provider_id where v.metro=?',(M,)))
  w('benchmarks',Q('select * from benchmarks where metro=?',(M,)))
  w('episodes',[dict(e,components=json.loads(e['components'])) for e in Q('select * from episodes')])
  idx=[dict(c=b['code'],d=b['description'],n=Q('select count(*) n from prices p join providers v on v.id=p.provider_id where code=? and v.metro=?',(b['code'],M))[0]['n']) for b in Q("select distinct code,description from benchmarks where metro=? and state='MO'",(M,))]
  w('search_index',dict(codes=idx,episodes=[dict(id=e['id'],name=e['name'],aliases=e['aliases'],code=e['primary_code']) for e in Q('select * from episodes')]))
print(os.popen(f'du -sh {S}').read())
