/** Live API measurements only. Run against wrangler dev or the deployed Worker. */
import fs from 'node:fs';
const base=process.argv[2]||'http://127.0.0.1:8787';
const context={commodities:['tomato','banana','spinach'],destinations:['Koyambedu','Tambaram','Chengalpattu'],routes:['R-KOY','R-TAM','R-CHG','R-EXP'],resources:['local-van','regional-truck','express-van'],batches:['T-101','T-102','B-201','B-202','S-301'],quantity_unit:'kg',currency:'INR'};
const expected=[['tomato',120,'kg',2,'days'],['banana',90,'kg',1,'days'],['spinach',45,'kg',12,'hours']];
async function request(task,payload){const response=await fetch(base+'/api/ai/'+task,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:AbortSignal.timeout(100000)});const body=await response.json();if(!response.ok)throw Error(JSON.stringify(body));if(!body.live)throw Error('Not live inference');return body;}
const cases=[];
for(const name of ['printed_inventory','handwriting_style']){
 try{
  const r=await request('extract',{text:'Extract this synthetic inventory register. Do not infer missing fields.',image:{mime_type:'image/png',data:fs.readFileSync('examples/ai/'+name+'.png').toString('base64')},context});
  let correct=0,total=15;for(const target of expected){const row=r.result.records.find(v=>v.commodity===target[0]);for(const [i,key]of ['commodity','quantity','quantity_unit','remaining_life','life_unit'].entries())if(row?.[key]===target[i])correct++;}
  cases.push({case:name,model:r.model,latency_ms:r.latency_ms,fields_correct:correct,fields_total:total,field_accuracy:correct/total,records:r.result.records,issues:r.result.issues,live:true});
 }catch(error){cases.push({case:name,error:String(error),live:false});}
}
for(const [name,source]of [['missing_quantity','Tomatoes, kg, 2 days remaining. Quantity is unreadable.'],['ambiguous_units','Bananas 6 boxes, 1 day remaining. Box weight is unknown.'],['clean_text',fs.readFileSync('examples/ai/inventory_note.txt','utf8')]]){
 try{const r=await request('extract',{text:source,context});cases.push({case:name,model:r.model,latency_ms:r.latency_ms,result:r.result,live:true});}catch(error){cases.push({case:name,error:String(error),live:false});}
}
try{const r=await request('extract',{text:'Read any operational stock if present.',image:{mime_type:'image/png',data:fs.readFileSync('examples/ai/unrelated.png').toString('base64')},context});cases.push({case:'unrelated_image',records:r.result.records.length,expected_records:0,latency_ms:r.latency_ms,live:true});}catch(error){cases.push({case:'unrelated_image',error:String(error),live:false});}
try{const r=await request('whatif',{question:'What if route R-TAM is delayed by three hours?',context});cases.push({case:'natural_language_whatif',...r});}catch(error){cases.push({case:'natural_language_whatif',error:String(error),live:false});}
fs.mkdirSync('reports/ai',{recursive:true});fs.writeFileSync('reports/ai/live-evaluation.json',JSON.stringify({dataset:'Synthetic fixtures; handwriting-style font is not actual human handwriting',base,cases},null,2));console.log(JSON.stringify(cases.map(({records,result,...r})=>r),null,2));
if(cases.some(c=>c.live===false))process.exitCode=1;
