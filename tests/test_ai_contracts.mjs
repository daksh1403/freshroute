import test from 'node:test';
import assert from 'node:assert/strict';
import {parseJSON,validateExtraction,validateAnswer,validateOperations} from '../cloudflare/contracts.mjs';
const context={source:'Tomatoes 120 kg, 2 days remaining',source_id:'note-1',source_kind:'text',commodities:['tomato'],destinations:['Market A'],routes:['R1'],resources:['V1'],batches:['B1']};
const record={kind:'inventory',commodity:'tomato',quantity:120,quantity_unit:'kg',remaining_life:2,life_unit:'days',source_refs:{commodity:{quote:'Tomatoes',location:'line 1'},quantity:{quote:'120 kg',location:'line 1'},quantity_unit:{quote:'kg',location:'line 1'},remaining_life:{quote:'2 days',location:'line 1'},life_unit:{quote:'days',location:'line 1'}},ambiguities:[]};
test('strict JSON and malformed output',()=>{assert.deepEqual(parseJSON('```json\n{"records":[]}\n```'),{records:[]});assert.throws(()=>parseJSON('Here is {"records":[]}'));});
test('source-grounded extraction preserves missing fields',()=>{const result=validateExtraction({records:[record],unresolved:[]},context);assert.equal(result.records[0].quantity,120);const missing=structuredClone(record);missing.quantity=null;delete missing.source_refs.quantity;assert.equal(validateExtraction({records:[missing],unresolved:['Missing quantity']},context).records[0].quantity,null);});
test('unsupported fields and fabricated quotes rejected',()=>{assert.throws(()=>validateExtraction({records:[{...record,execute:'rm'}],unresolved:[]},context));const bad=structuredClone(record);bad.source_refs.quantity.quote='999 kg';assert.throws(()=>validateExtraction({records:[bad],unresolved:[]},context));});
test('contradictory quantity provenance rejected',()=>{const bad=structuredClone(record);bad.quantity=999;assert.throws(()=>validateExtraction({records:[bad],unresolved:[]},context));});
test('negative and nonfinite values rejected',()=>{for(const q of [-1,Infinity,true])assert.throws(()=>validateExtraction({records:[{...record,quantity:q}],unresolved:[]},context));});
test('unrelated image can produce zero records',()=>{assert.deepEqual(validateExtraction({records:[],unresolved:['No produce found']},{...context,source_kind:'image'}).records,[]);});
test('unknown commodities and duplicate evidence are flagged',()=>{const r=validateExtraction({records:[record,record],unresolved:[]},context);assert(r.issues.some(s=>s.includes('duplicate')));assert(validateExtraction({records:[{...record,commodity:'cement'}],unresolved:[]},{...context,source_kind:'image'}).issues.some(s=>s.includes('commodity')));});
test('unsupported operations and selectors rejected',()=>{assert.throws(()=>validateOperations([{op:'execute_code',code:'x'}],context));assert.throws(()=>validateOperations([{op:'delay_route',route_id:'unknown',hours:4}],context));assert.throws(()=>validateOperations([{op:'scale_demand',commodity:'cement',destination_id:null,factor:1.2}],context));assert.deepEqual(validateOperations([{op:'delay_route',route_id:'R1',hours:4}],context)[0].hours,4);});
test('grounding rejects unknown citations and invented numbers',()=>{const facts=[{id:'metrics.net',text:'Net revenue 120 CU'}];assert.throws(()=>validateAnswer({statements:[{text:'Profit 999 CU',source_ids:['metrics.net'],kind:'interpretation'}],unavailable:[]},facts));assert.throws(()=>validateAnswer({statements:[{text:'Good',source_ids:['unknown'],kind:'fact'}],unavailable:[]},facts));assert.equal(validateAnswer({statements:[{text:'The plan earns 120 CU.',source_ids:['metrics.net'],kind:'interpretation'}],unavailable:[]},facts).statements.length,1);});

test('provider failures do not fall through to fake responses',async()=>{
 const {generate}=await import('../cloudflare/intelligence.mjs');
 await assert.rejects(generate('extract',{text:context.source,context:{...context,source:undefined,source_id:undefined,source_kind:undefined}},{}),/GEMINI_API_KEY/);
});
test('Worker reports missing key and preserves core/static routes',async()=>{
 const {default:worker}=await import('../cloudflare/worker.mjs');const env={ASSETS:{fetch:()=>new Response('core available')}};
 const response=await worker.fetch(new Request('https://test/api/ai/extract',{method:'POST',body:'{}'}),env);assert.equal(response.status,503);assert((await response.json()).core_available);
 assert.equal(await(await worker.fetch(new Request('https://test/'),env)).text(),'core available');
 assert.equal((await worker.fetch(new Request('https://test/api/ai/extract',{method:'POST',headers:{Origin:'https://other'},body:'{}'}),env)).status,403);
});

test('potential contradictory stock and negative source numbers require rejection or review',()=>{
 const changed=structuredClone(record);changed.quantity=90;changed.source_refs.quantity.quote='90 kg';
 const result=validateExtraction({records:[record,changed],unresolved:[]},{...context,source_kind:'image'});
 assert(result.issues.some(s=>s.includes('conflicting')));
 const negative=structuredClone(record);negative.source_refs.quantity.quote='-120 kg';
 assert.throws(()=>validateExtraction({records:[negative],unresolved:[]},{...context,source_kind:'image'}));
});
test('timeout is surfaced without inventing an AI answer',async()=>{
 const {generate}=await import('../cloudflare/intelligence.mjs');
 const c={commodities:['tomato'],destinations:['Market A'],routes:['R1'],resources:['V1'],batches:['B1'],currency:'CU',quantity_unit:'kg'};
 await assert.rejects(generate('extract',{text:'tomato 1 kg',context:c},{GEMINI_API_KEY:'unit-test-only'},{models:{generateContent:async()=>{throw Object.assign(Error('provider timeout'),{status:504});}}}),/timeout/);
});

test('missing unit evidence cannot invent quantity, shelf-life or currency units',()=>{
 const bad=structuredClone(record);for(const field of ['quantity_unit','life_unit'])bad.source_refs[field].quote='Tomatoes 120 remaining 2';
 bad.currency='INR';bad.source_refs.currency={quote:'Tomatoes 120 remaining 2',location:'line 1'};
 const result=validateExtraction({records:[bad],unresolved:[]},{...context,source_kind:'image'});
 for(const field of ['quantity_unit','life_unit','currency'])assert.equal(result.records[0][field],null);
 assert(result.issues.length>=3);
 const alias=structuredClone(record);alias.quantity_unit='kilograms';alias.life_unit='day';
 const accepted=validateExtraction({records:[alias],unresolved:[]},context);
 assert.equal(accepted.records[0].quantity_unit,'kilograms');assert.equal(accepted.records[0].life_unit,'day');
});
