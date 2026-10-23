// Client-side port of app/server.py (search, service, episode). Data: data/<metro>/*.json
const D={};
async function load(m){if(D[m])return D[m];const g=n=>fetch(`data/${m}/${n}.json`).then(r=>r.json());
 const [providers,prices,benchmarks,episodes,index]=await Promise.all(['providers','prices','benchmarks','episodes','search_index'].map(g));
 const P=Object.fromEntries(providers.map(p=>[p.id,p])),B={};benchmarks.forEach(b=>B[b.state+'|'+b.code]=b);
 const byProv={};prices.forEach(r=>{(byProv[r.provider_id]??={})[r.code]=r});
 return D[m]={providers,prices,P,B,byProv,episodes,index};}
const bm=(d,code,st)=>d.B[st+'|'+code]||null;
function search(d,s){s=s.trim().toLowerCase();const out=[];
 for(const e of d.index.episodes) if(s&&(e.name.toLowerCase().includes(s)||e.aliases.split(',').some(a=>s.includes(a)||a.includes(s))||s==e.code)) out.push({kind:'episode',id:e.id,label:e.name,code:e.code});
 const words=s.split(/[^A-Za-z0-9_]+/).filter(Boolean);
 for(const b of d.index.codes){const dd=b.d.toLowerCase(),c=b.c.toLowerCase();
  if(s==c||(words.length&&words.every(w=>dd.includes(w)||w==c))) out.push({kind:'service',id:b.c,label:`${b.c} · ${b.d}`,code:b.c,n:b.n});}
 return out.slice(0,25);}
function fairFor(b,role){if(!b)return null;
 if(role=='facility+professional')return ((b.fair_facility||0)+(b.fair_professional||0))||b.fair_combined;
 if(role=='facility')return b.fair_facility; if(role=='professional'||role=='anesthesia')return b.fair_professional||b.fair_combined;
 if(role=='pathology')return b.fair_combined; return 0;}
const r2=x=>Math.round(x*100)/100;
function service(d,code){const bms={MO:bm(d,code,'MO'),IL:bm(d,code,'IL')};
 const rows=d.prices.filter(p=>p.code==code).map(p=>{const v=d.P[p.provider_id];const r={...p,name:v.name,type:v.type,city:v.city,state:v.state,lat:v.lat,lon:v.lon,page_url:v.page_url,file_url:v.file_url,file_format:v.file_format,vintage:v.vintage,pnote:v.note};
  const b=bms[r.state]||bms.MO;const ref=b?(r.all_inclusive?b.fair_combined:(b.fair_facility||b.fair_combined)):null;
  r.benchmark_used=ref;r.benchmark_basis=r.all_inclusive?'fair all-in (facility+professional)':'fair facility';r.multiple=ref?r2(r.cash/ref):null;return r}).sort((a,b)=>a.cash-b.cash);
 return {code,benchmarks:bms,rows};}
function episode(d,id){const e=d.episodes.find(x=>x.id==id),comps=e.components;
 const ebm=st=>{let tot=0;const parts=comps.map(cp=>{const b=bm(d,cp[0],st),f=cp[1]!='contrast'?fairFor(b,cp[1]):0;tot+=f||0;return{code:cp[0],role:cp[1],desc:b?b.description:'',fair:f,note:b?b.note:''}});return{total:r2(tot),parts}};
 const B={MO:ebm('MO'),IL:ebm('IL')},out=[];
 for(const p of d.providers){const pr=d.byProv[p.id]||{};const pc=pr[e.primary_code];
  const allin=pr['EP:'+id]||(pc&&pc.all_inclusive?pc:null);
  if(allin){out.push({provider:p,total:allin.cash,listed:allin.cash,estimated:0,missing:[],all_inclusive:true,flag:null});continue}
  if(!pc)continue;let listed=0,est=0;const missing=[];
  for(const cp of comps){const b=bm(d,cp[0],p.state);if(cp[1]=='contrast')continue;
   if(cp[1]=='facility+professional'){listed+=pc.cash;const f=b?b.fair_professional:null;if(f){est+=f;missing.push(`${cp[0]} professional (physician) fee`)}}
   else if(pr[cp[0]])listed+=pr[cp[0]].cash; else{const f=fairFor(b,cp[1]);est+=f||0;missing.push(`${cp[0]} ${cp[1]}`)}}
  out.push({provider:p,total:r2(listed+est),listed:r2(listed),estimated:r2(est),missing,all_inclusive:false,flag:pc.flag})}
 out.forEach(o=>{const b=B[o.provider.state].total;o.multiple=b?r2(o.total/b):null});out.sort((a,b)=>a.total-b.total);
 return {episode:e,components:comps,benchmarks:B,rows:out};}
