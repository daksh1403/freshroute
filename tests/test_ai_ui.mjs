/** Mocked UI state regression tests, not inference quality measurements. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

function harness(){
 const nodes=new Map();const get=id=>{if(!nodes.has(id))nodes.set(id,{value:'',checked:false,hidden:true,disabled:false,files:[],innerHTML:'',textContent:''});return nodes.get(id);};
 let fail=false,calls=0,version=1;
 const scenario=()=>({inventory:[{batch_id:'B1',commodity:'tomato'}],demand:[{commodity:'tomato',destination_id:'A'}],routes:[{route_id:'R1'}],resources:[{resource_id:'V1'}],config:{quantity_unit:'kg',currency:'CU'},version});
 const F={escape:String,isReady:()=>true,getScenario:scenario,getResult:()=>({scenario:scenario()}),table:()=>'',call:async task=>{if(task==='ai_review')return {draft:{inventory:[],demand:[],price_updates:[]},issues:[],provenance:[]};calls++;throw Error('Mutation must not run');}};
 const fetch=async path=>{if(path.endsWith('/status'))return {json:async()=>({configured:true,model:'unit-test'})};if(fail)throw Error('Simulated provider failure');return {ok:true,json:async()=>({model:'unit-test',latency_ms:1,result:{records:[],operations:[{op:'delay_route',route_id:'R1',hours:3}],clarifications:[]}})};};
 vm.runInNewContext(fs.readFileSync('web/ai.js','utf8'),{window:{FreshRoute:F},document:{getElementById:get},fetch,AbortSignal,console});
 return {get,fail:()=>{fail=true;version++;},calls:()=>calls};
}

test('failed replacement extraction invalidates old confirmation and source/base state',async()=>{
 const h=harness();h.get('ai-consent').checked=true;h.get('ai-source').value='tomato';
 await h.get('ai-extract').onclick();assert.equal(h.get('ai-review').hidden,false);
 h.get('ai-confirm').checked=true;h.fail();await h.get('ai-extract').onclick();
 assert.equal(h.get('ai-review').hidden,true);assert.equal(h.get('ai-confirm').checked,false);assert.equal(h.get('ai-apply').disabled,true);
 await h.get('ai-apply').onclick();assert.match(h.get('ai-progress').textContent,/Extract a source first/);assert.equal(h.calls(),0);
});

test('failed replacement what-if invalidates an older confirmed proposal',async()=>{
 const h=harness();h.get('ai-whatif-question').value='delay';await h.get('ai-whatif-propose').onclick();
 assert.equal(h.get('ai-whatif-proposal').hidden,false);h.get('ai-whatif-confirm').checked=true;h.fail();await h.get('ai-whatif-propose').onclick();
 assert.equal(h.get('ai-whatif-proposal').hidden,true);assert.equal(h.get('ai-whatif-confirm').checked,false);assert.equal(h.get('ai-whatif-run').disabled,true);
 await h.get('ai-whatif-run').onclick();assert.match(h.get('ai-whatif-progress').textContent,/fresh scenario proposal/);assert.equal(h.calls(),0);
});
