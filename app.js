// Client-side port of app/server.py (search, service, episode). Data: data/<metro>/*.json
const D={};let META={metros:[]};const metroInfo=m=>META.metros.find(x=>x.metro==m)||{};
async function load(m){if(D[m])return D[m];const g=n=>fetch(`data/${m}/${n}.json`).then(r=>r.json());
 const [providers,prices,benchmarks,episodes,index]=await Promise.all(['providers','prices','benchmarks','episodes','search_index'].map(g));
 const P=Object.fromEntries(providers.map(p=>[p.id,p])),B={};benchmarks.forEach(b=>B[b.state+'|'+b.code]=b);
 const byProv={};prices.forEach(r=>{(byProv[r.provider_id]??={})[r.code]=r});
 const parts=metroInfo(m).parts||[...new Set(providers.map(p=>p.state))];
 return D[m]={providers,prices,P,B,byProv,episodes,index,parts};}
// Reimbursement rate: assumed % of Medicare full allowed amount (user control)
let RATE=0.75;const F=(b,k,rt=RATE)=>b&&b[k]!=null?Math.round(b[k]*rt*100)/100:null;
const bm=(d,code,st)=>d.B[st+'|'+code]||null;
function search(d,s){s=s.trim().toLowerCase();const out=[];
 for(const e of d.index.episodes) if(s&&(e.name.toLowerCase().includes(s)||e.aliases.split(',').some(a=>s.includes(a)||a.includes(s))||s==e.code)) out.push({kind:'episode',id:e.id,label:e.name,code:e.code});
 const words=s.split(/[^A-Za-z0-9_]+/).filter(Boolean);
 for(const b of d.index.codes){const dd=b.d.toLowerCase(),c=b.c.toLowerCase();
  if(s==c||(words.length&&words.every(w=>dd.includes(w)||w==c))) out.push({kind:'service',id:b.c,label:`${b.c} · ${b.d}`,code:b.c,n:b.n});}
 return out.slice(0,25);}
function fairFor(b,role,rt=RATE){if(!b)return null;const F2=(x,k)=>F(x,k,rt);
 if(role=='facility+professional')return ((F2(b,'facility')||0)+(F2(b,'professional')||0))||F2(b,'combined');
 if(role=='facility')return F2(b,'facility'); if(role=='professional'||role=='anesthesia')return F2(b,'professional')||F2(b,'combined');
 if(role=='pathology')return F2(b,'combined'); return 0;}
const r2=x=>Math.round(x*100)/100;
function service(d,code){const bms=Object.fromEntries(d.parts.map(s=>[s,bm(d,code,s)]));
 const rows=d.prices.filter(p=>p.code==code).map(p=>{const v=d.P[p.provider_id];const r={...p,name:v.name,type:v.type,city:v.city,state:v.state,lat:v.lat,lon:v.lon,page_url:v.page_url,file_url:v.file_url,file_format:v.file_format,vintage:v.vintage,pnote:v.note};
  const hb=r.code_type=='MS-DRG'&&v.ccn?d.B['H'+v.ccn+'|'+code]:null,b=hb||bms[r.state]||bms[d.parts[0]];const prof=/^Professional/.test(r.included||'');
  const k=!b?null:r.all_inclusive?'combined':prof?(b.professional!=null?'professional':'combined'):(b.facility!=null?'facility':'combined');
  r.medicare=b&&k?b[k]:null;r.medicare_basis=!k?'':k=='combined'?'Medicare all-in (facility+professional)':k=='professional'?'Medicare professional fee':(hb?'Medicare DRG rate (this hospital\'s wage index)':'Medicare facility rate');
  r.no_bm_reason=!b?'no Medicare benchmark for this code':r.medicare==null?(b.note?'no Medicare rate in 2026 files (code deleted/renumbered or not covered)':'Medicare amount not published for this setting'):null;
  r.implied=r.medicare!=null?r2(r.medicare*RATE):null;r.benchmark_used=r.implied;r.benchmark_basis=r.medicare_basis;r.multiple=r.implied?r2(r.cash/r.implied):null;return r}).sort((a,b)=>a.cash-b.cash);
 return {code,benchmarks:bms,rows};}
function episode(d,id){const e=d.episodes.find(x=>x.id==id),comps=e.components;
 const ebm=st=>{let tot=0,med=0;const parts=comps.map(cp=>{const b=bm(d,cp[0],st),f=cp[1]!='contrast'?fairFor(b,cp[1]):0;tot+=f||0;const m=cp[1]!='contrast'?fairFor(b,cp[1],1):0;med+=m||0;return{code:cp[0],role:cp[1],desc:b?b.description:'',fair:f,medicare:m,note:b?b.note:''}});return{total:r2(tot),medicare:r2(med),parts}};
 const B=Object.fromEntries(d.parts.map(s=>[s,ebm(s)])),out=[];
 for(const p of d.providers){const pr=d.byProv[p.id]||{};const pc=pr[e.primary_code];
  const allin=pr['EP:'+id]||(pc&&pc.all_inclusive?pc:null);
  if(allin){out.push({provider:p,total:allin.cash,listed:allin.cash,estimated:0,missing:[],all_inclusive:true,flag:null,comparability:allin.comparability||'Medium'});continue}
  if(!pc)continue;let listed=0,est=0;const missing=[];
  for(const cp of comps){const b=bm(d,cp[0],p.state);if(cp[1]=='contrast')continue;
   if(cp[1]=='facility+professional'){listed+=pc.cash;const f=b?F(b,'professional'):null;if(f){est+=f;missing.push(`${cp[0]} professional (physician) fee`)}}
   else if(pr[cp[0]])listed+=pr[cp[0]].cash; else{const f=fairFor(b,cp[1]);est+=f||0;missing.push(`${cp[0]} ${cp[1]}`)}}
  out.push({provider:p,total:r2(listed+est),listed:r2(listed),estimated:r2(est),missing,all_inclusive:false,flag:pc.flag,comparability:pc.comparability||'Medium'})}
 out.forEach(o=>{const E=B[o.provider.state]||B[d.parts[0]];o.medicare=E.medicare||null;o.medicare_basis='Medicare episode total';o.no_bm_reason=o.medicare?null:'no Medicare benchmark for these components';o.implied=o.medicare?r2(o.medicare*RATE):null;o.multiple=o.implied?r2(o.total/o.implied):null});out.sort((a,b)=>a.total-b.total);
 return {episode:e,components:comps,benchmarks:B,rows:out};}
