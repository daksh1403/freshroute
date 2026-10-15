/** Strict application contracts: model output never authorizes a mutation. */
export const MODELS=['gemma-4-26b-a4b-it','gemma-4-31b-it'];
const fields=['commodity','quantity','quantity_unit','remaining_life','life_unit','destination_id','price_per_unit','price_quantity_unit','currency'];
export function object(v,n){if(!v||typeof v!=='object'||Array.isArray(v))throw Error(n+': expected object');return v;}
export function keys(v,allowed,n){object(v,n);for(const k of Object.keys(v))if(!allowed.includes(k))throw Error(n+': unsupported field '+k);}
export function text(v,n,max=2000){if(typeof v!=='string'||!v.trim()||v.length>max)throw Error(n+': expected nonempty text (max '+max+')');return v.trim();}
export function nonnegative(v,n,max=1e9){if(typeof v!=='number'||!Number.isFinite(v)||v<0||v>max)throw Error(n+': expected finite nonnegative number');return v;}
const normalized=s=>s.toLowerCase().replace(/\s+/g,' ').trim();
const unitAliases=[['kg','kilogram','kilograms'],['g','gram','grams'],['t','tonne','tonnes'],['h','hr','hrs','hour','hours'],['d','day','days'],['inr','₹','rupee','rupees','rs'],['usd','us dollar','us dollars'],['eur','€','euro','euros']];
function supportedUnit(value,quote){
 const token=normalized(value),aliases=unitAliases.find(group=>group.includes(token))||[token];
 return aliases.some(alias=>{if(['₹','€'].includes(alias))return quote.includes(alias);const escaped=alias.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');return new RegExp('(^|[^a-z])'+escaped+'($|[^a-z])','i').test(quote);});
}
export function parseJSON(raw){text(raw,'model response',70000);return JSON.parse(raw.trim().replace(/^```(?:json)?\s*/,'').replace(/\s*```$/,''));}
export function validateExtraction(v,c){
 keys(v,['records','unresolved'],'extraction');if(!Array.isArray(v.records)||v.records.length>25)throw Error('records: expected at most 25 rows');
 const unresolved=(v.unresolved||[]).map(s=>text(s,'unresolved',500)),issues=[],seen=new Set(),commodityValues=new Map();
 const records=v.records.map((r,i)=>{
  const n='record '+(i+1);keys(r,['kind',...fields,'source_refs','ambiguities'],n);
  if(!['inventory','demand','price'].includes(r.kind))throw Error(n+': unsupported kind');
  keys(r.source_refs,fields,n+'.source_refs');if(!Array.isArray(r.ambiguities))throw Error(n+': ambiguities must be an array');
  const out={kind:r.kind,source_refs:{},ambiguities:r.ambiguities.map(s=>text(s,'ambiguity',500))};
  for(const f of fields){const value=r[f]??null;out[f]=value;if(value===null)continue;
   if(['quantity','remaining_life','price_per_unit'].includes(f))nonnegative(value,n+'.'+f);else text(value,n+'.'+f,120);
   const ref=r.source_refs[f];if(!ref){issues.push(n+': missing source reference for '+f);out[f]=null;continue;}
   keys(ref,['quote','location'],'source reference');text(ref.quote,'quote',1000);text(ref.location,'location',200);
   if(c.source_kind==='text'&&!normalized(c.source).includes(normalized(ref.quote)))throw Error(n+': source quote not present in input for '+f);
   if(['quantity','remaining_life','price_per_unit'].includes(f)){const ns=(ref.quote.match(/[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?/g)||[]).map(s=>Number(s.replaceAll(',','')));if(!ns.some(n=>Math.abs(n-value)<1e-8))throw Error(n+': number contradicts source quote for '+f);}
   if(['quantity_unit','price_quantity_unit','life_unit','currency'].includes(f)&&!supportedUnit(value,ref.quote)){out[f]=null;issues.push(n+': '+f+' absent from source quotation; manual correction required');}
   out.source_refs[f]={quote:ref.quote,location:ref.location};
  }
  if(out.commodity&&!c.commodities.includes(out.commodity))issues.push(n+': unknown commodity '+out.commodity);
  if(out.destination_id&&!c.destinations.includes(out.destination_id))issues.push(n+': unknown destination '+out.destination_id);
  const commodityKey=JSON.stringify([out.kind,out.destination_id,out.commodity]);
  if(commodityValues.has(commodityKey)&&commodityValues.get(commodityKey)!==out.quantity)issues.push(n+': conflicting quantities for the same commodity; verify separate batches versus corrections');commodityValues.set(commodityKey,out.quantity);
  const signature=JSON.stringify(fields.map(f=>out[f]).concat(out.kind));if(seen.has(signature))issues.push(n+': possible duplicate; verify distinct batches before confirming');seen.add(signature);return out;
 });return {source_id:c.source_id,source_kind:c.source_kind,records,unresolved,issues};
}
export function validateOperations(ops,c){
 if(!Array.isArray(ops)||!ops.length||ops.length>8)throw Error('Propose 1–8 supported operations');
 const defs={delay_route:['route_id','hours'],scale_capacity:['resource_id','factor'],scale_demand:['destination_id','commodity','factor'],scale_price:['destination_id','commodity','factor'],scale_inventory:['batch_id','commodity','factor']};
 return ops.map(op=>{if(!Object.hasOwn(defs,op.op))throw Error('Unsupported scenario operation '+op.op);keys(op,['op',...defs[op.op]],'operation');for(const k of defs[op.op])if(!(k in op))throw Error('Missing operation field '+k);
  if('hours'in op)nonnegative(op.hours,'hours',168);if('factor'in op)nonnegative(op.factor,'factor',3);
  for(const [k,list]of [['route_id','routes'],['resource_id','resources'],['destination_id','destinations'],['commodity','commodities'],['batch_id','batches']])if(k in op&&op[k]!==null&&!(c[list]||[]).includes(op[k]))throw Error('Unknown '+k+': '+op[k]);return op;});
}
export function validateAnswer(v,facts){
 keys(v,['statements','unavailable'],'answer');if(!Array.isArray(v.statements)||v.statements.length>8)throw Error('Answer requires at most 8 statements');const byId=new Map(facts.map(f=>[f.id,f]));
 const statements=v.statements.map(r=>{keys(r,['text','kind','source_ids'],'statement');text(r.text,'statement',1200);if(!['fact','assumption','interpretation'].includes(r.kind))throw Error('Unknown evidence category');
  if(!Array.isArray(r.source_ids)||!r.source_ids.length||r.source_ids.some(id=>!byId.has(id)))throw Error('Unknown or missing source citation');const sources=r.source_ids.map(id=>byId.get(id));
  const nums=s=>(s.match(/[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?/g)||[]).map(n=>Number(n.replaceAll(',',''))),available=nums(sources.map(f=>f.text).join(' '));
  if(nums(r.text).some(v=>!available.some(n=>Math.abs(n-v)<1e-6)))throw Error('Unsupported numerical statement');return {...r,sources};});
 return {statements,unavailable:(v.unavailable||[]).map(s=>text(s,'unavailable',800)),guardrails:'Citations and numerical tokens checked. Interpretations are model-generated and require judgment.'};
}
