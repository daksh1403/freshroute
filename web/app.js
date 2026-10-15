const $=id=>document.getElementById(id);
let worker,ready=false,busy=false,scenario=null,result=null,disrupted=null,version='',requestId=0;
const waiting=new Map();
const labels={overview:'Overview',plan:'Dispatch plan',inventory:'Inventory & inputs',evidence:'Decision evidence',disruptions:'Disruption sandbox',reports:'Reports'};
const escape=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const number=(value,digits=1)=>Number.isFinite(Number(value))?Number(value).toLocaleString(undefined,{maximumFractionDigits:digits}):'—';
const money=value=>number(value,2);
const title=value=>String(value).replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
function showTab(id){document.querySelectorAll('.tab-panel').forEach(el=>el.classList.toggle('active',el.id===id));document.querySelectorAll('.nav').forEach(el=>el.classList.toggle('active',el.dataset.tab===id));$('breadcrumb').textContent=labels[id];}
document.querySelectorAll('.nav').forEach(el=>el.onclick=()=>showTab(el.dataset.tab));
document.querySelectorAll('.jump').forEach(el=>el.onclick=()=>showTab(el.dataset.target));
function error(message){$('error').hidden=!message;$('error').textContent=message||'';}
function status(message,kind='ready'){$('runtime-status').className='runtime-banner '+kind;$('runtime-status').innerHTML=(kind==='busy'?'<span class="spinner"></span>':'<span>●</span>')+'<span>'+escape(message)+'</span>';}
function setBusy(value){busy=value;['generate','replan','apply-json'].forEach(id=>$(id).disabled=value||!ready||(id==='replan'&&!result));$('cancel').hidden=!value;['upload','reset-demo','horizon','handling','time-limit'].forEach(id=>$(id).disabled=value);}
function call(method,...args){return new Promise((resolve,reject)=>{if(!ready)return reject(new Error('The Python engine is not ready.'));const id=++requestId;waiting.set(id,{resolve,reject});worker.postMessage({id,method,args});});}
function launchEngine(){
  ready=false;setBusy(false);status('Preparing the local Python engine. First load downloads NumPy and SciPy.','busy');
  worker=new Worker('./worker.js',{type:'module'});
  worker.onmessage=async({data})=>{
    if(data.type==='progress'){status(data.text,'busy');return;}
    if(data.type==='fatal'){error('Engine initialization failed. '+data.error);status('Engine unavailable. Check your connection, then retry.','busy');$('cancel').hidden=false;return;}
    if(data.type==='ready'){
      ready=true;version=data.version;setBusy(false);status('Engine ready · Python + HiGHS · computation stays in your browser');
      if(scenario){try{await validateScenario(scenario);}catch(err){error(err.message);}}
      return;
    }
    const pending=waiting.get(data.id);if(!pending)return;waiting.delete(data.id);
    if(data.error)pending.reject(new Error(data.error));else pending.resolve(JSON.parse(data.result));
  };
  worker.onerror=event=>{error('Browser worker failed: '+event.message);ready=false;setBusy(false);$('cancel').hidden=false;};
}
$('cancel').onclick=()=>{worker.terminate();for(const {reject}of waiting.values())reject(new Error('Operation cancelled.'));waiting.clear();error('');launchEngine();};
function table(rows,columns){
  if(!rows?.length)return '<p class="muted" style="padding:20px">No records for this scenario.</p>';
  const keys=columns||Object.keys(rows[0]);
  return '<table><thead><tr>'+keys.map(key=>'<th>'+escape(title(key))+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+keys.map(key=>{let value=row[key];if(value===null||value===undefined)value='—';else if(typeof value==='number')value=number(value,4);else if(typeof value==='boolean')value=value?'Yes':'No';return '<td'+(String(value).length>80?' class="wrap"':'')+'>'+escape(value)+'</td>';}).join('')+'</tr>').join('')+'</tbody></table>';
}
function resetResults(){
  result=null;disrupted=null;$('tradeoff-note').hidden=true;['net-revenue','fulfillment','spoilage','violations'].forEach(id=>$(id).textContent='—');
  $('net-delta').textContent='Generate a plan to compare';$('net-delta').className='';$('evaluation-status').textContent='Inputs changed · run a new evaluation';
  $('solver-detail').textContent='Independently checked';$('fulfillment-detail').textContent='Demand within this horizon';$('spoilage-detail').textContent='Only stock that expires in time';
  $('route-board').className='empty';$('route-board').innerHTML='<span class="empty-symbol">↗</span><h3>Your inputs are ready.</h3><p>Generate a plan to calculate feasible dispatches.</p>';
  $('comparison-chart').innerHTML='<p class="muted">Generate a new plan to compare both strategies.</p>';
  $('risk-list').innerHTML='<p class="muted">Generate a plan to identify unshipped risk.</p>';
  ['shipment-table','comparison-table','baseline-table','explanation-list','remaining-table','utilization-table','rejection-table','discount-list','disruption-results'].forEach(id=>$(id).innerHTML='');
  $('solver-metadata').textContent='';document.querySelectorAll('.download').forEach(el=>el.disabled=true);$('replan').disabled=true;
}
function renderInputs(){
  if(!scenario)return;
  $('dataset-name').textContent=scenario.config.label||'Imported scenario';$('money-unit').textContent=scenario.config.currency;
  $('horizon').value=scenario.config.horizon_hours;$('handling').value=scenario.config.handling_hours||0;
  $('json-editor').value=JSON.stringify(scenario,null,2);
  $('input-tables').innerHTML=['inventory','demand','routes','resources'].map(name=>'<h3>'+title(name)+'</h3><div class="card table-card">'+table(scenario[name])+'</div>').join('');
  $('delay-route').innerHTML='<option value="">All routes</option>'+scenario.routes.map(r=>'<option value="'+escape(r.route_id)+'">'+escape(r.route_id)+' · '+escape(r.destination_id)+'</option>').join('');
}
async function validateScenario(raw){
  const preview=await call('preview',JSON.stringify(raw));scenario=preview.scenario;resetResults();renderInputs();
  status(`Validated · ${number(preview.inventory_quantity)} ${scenario.config.quantity_unit} inventory · ${number(preview.demand_quantity)} demand · ${number(preview.at_risk_quantity)} expires by horizon`);
}
async function demo(){error('');const response=await fetch('./demo.json');if(!response.ok)throw new Error('Cannot load demo dataset');const data=await response.json();if(ready)await validateScenario(data);else{scenario=data;renderInputs();}}
$('reset-demo').onclick=()=>demo().catch(err=>error(err.message));
async function syncSettings(){
  const copy=structuredClone(scenario);copy.config.horizon_hours=Number($('horizon').value);copy.config.handling_hours=Number($('handling').value);
  if(copy.config.horizon_hours!==scenario.config.horizon_hours||copy.config.handling_hours!==scenario.config.handling_hours){const validated=await call('preview',JSON.stringify(copy));scenario=validated.scenario;resetResults();renderInputs();}
}
['horizon','handling'].forEach(id=>$(id).addEventListener('change',async()=>{try{await syncSettings();error('');}catch(err){error(err.message);}}));
function currentLimit(){const limit=Number($('time-limit').value);if(!Number.isFinite(limit)||limit<1||limit>60)throw new Error('Solver limit must be between 1 and 60 seconds.');return limit;}
$('generate').onclick=async()=>{
  try{error('');setBusy(true);await syncSettings();status('Optimizing allocations, then independently checking every constraint…','busy');const data=await call('run',JSON.stringify(scenario),currentLimit());result=data;disrupted=null;renderResult();showTab('overview');}
  catch(err){error(err.message);}finally{setBusy(false);}
};
function miniChart(label,before,after,format=number){
  const maximum=Math.max(Math.abs(before),Math.abs(after),1);
  return '<div class="chart-group"><div class="chart-label"><span>'+escape(label)+'</span></div>'+[['FEFO',before,''],['FreshRoute',after,' optimized']].map(([name,value,css])=>'<div class="chart-bar-row"><span>'+name+'</span><div class="chart-track"><div class="chart-fill'+css+'" style="width:'+Math.abs(value)/maximum*100+'%"></div></div><span class="chart-value">'+escape(format(value))+'</span></div>').join('')+'</div>';
}
function renderResult(){
  const m=result.optimized_metrics,b=result.baseline_metrics,s=result.scenario,p=result.optimized_plan,unit=s.config.quantity_unit;
  $('tradeoff-note').hidden=!(m.spoiled_quantity>b.spoiled_quantity+1e-6);
  $('tradeoff-note').textContent='Economic trade-off: this plan leaves '+number(m.spoiled_quantity-b.spoiled_quantity)+' '+unit+' more spoilage than FEFO. The economic objective uses the disposal penalties supplied in the input; inspect all comparison metrics before dispatch.';
  $('net-revenue').textContent=money(m.net_revenue);const delta=m.net_revenue-b.net_revenue;
  $('net-delta').textContent=(delta>=0?'+':'')+money(delta)+' vs FEFO'+(b.net_revenue?' · '+number(100*delta/Math.abs(b.net_revenue))+'%':' · % undefined');$('net-delta').className=delta>=0?'positive':'negative';
  $('fulfillment').textContent=number(m.demand_fulfillment_percent)+'%';$('fulfillment-detail').textContent=number(m.shipped_quantity)+' / '+number(m.demand_quantity)+' '+unit+' demanded';
  $('spoilage').textContent=number(m.spoiled_quantity)+' '+unit;$('spoilage-detail').textContent=number(m.viable_remaining_quantity)+' '+unit+' remains viable';
  $('violations').textContent=m.constraint_violations.length;$('solver-detail').textContent=p.status+' · '+number(p.runtime_seconds,3)+' seconds';
  status('Independently validated · solver: '+p.status+' · '+result.shipments.length+' selected allocations · '+m.constraint_violations.length+' constraint violations');
  if(m.constraint_violations.length)error(m.constraint_violations.join('\n'));else if(p.status!=='optimal')error('Feasible fallback / time limit: '+p.message);
  $('evaluation-status').textContent='Evaluated on current inputs · '+p.status;
  const rows=result.shipments;
  $('route-board').className='route-list';
  const grouped=new Map();rows.forEach(row=>{if(!grouped.has(row.route_id))grouped.set(row.route_id,[]);grouped.get(row.route_id).push(row);});
  $('route-board').innerHTML=grouped.size?[...grouped].map(([id,loads])=>{
    const r=s.routes.find(r=>r.route_id===id),q=loads.reduce((a,row)=>a+row.quantity,0),hours=r.travel_hours+s.config.handling_hours;
    const fill=loads.map(row=>'<span class="'+(['tomato','banana','spinach'].includes(row.commodity)?row.commodity:'other')+'" style="width:'+100*row.quantity/Math.max(r.capacity,1)+'%" title="'+escape(row.commodity)+': '+escape(number(row.quantity))+'"></span>').join('');
    return '<div class="route-item"><div class="route-line"><div class="route-dest"><span class="route-icon">↗</span>'+escape(r.destination_id)+'</div><span class="route-quantity">'+escape(number(q))+' '+escape(unit)+'</span></div><div class="route-meta"><span>'+escape(id)+' · '+escape(number(hours))+'h to arrival</span><span class="positive">'+escape(number(100*q/Math.max(r.capacity,1)))+'% route capacity</span></div><div class="load-track">'+fill+'</div></div>';
  }).join(''):'<p class="muted">No feasible economically beneficial allocation. Inspect decision evidence.</p>';
  $('comparison-chart').innerHTML=miniChart('NET REVENUE · '+s.config.currency,b.net_revenue,m.net_revenue,money)+miniChart('DEMAND FULFILLMENT · %',b.demand_fulfillment_percent,m.demand_fulfillment_percent)+miniChart('SPOILAGE BY HORIZON · '+unit,b.spoiled_quantity,m.spoiled_quantity);
  const atRisk=result.explanations.remaining_inventory.filter(row=>row.expires_by_horizon);
  $('risk-list').innerHTML=atRisk.length?atRisk.map(row=>{const batch=s.inventory.find(b=>b.batch_id===row.batch_id);return '<div class="risk-row"><div><strong>'+escape(row.batch_id)+'</strong><p>'+escape(title(batch.commodity))+'</p></div><span>'+escape(number(row.quantity))+' '+escape(unit)+'</span><span class="time-pill">'+escape(number(batch.shelf_life_hours))+'h remaining</span></div>';}).join(''):'<p class="muted">No unshipped stock expires within this horizon.</p>';
  $('shipment-table').innerHTML=table(rows);$('baseline-table').innerHTML=table(result.baseline_shipments);
  const comparisons=Object.entries(result.comparison).map(([metric,values])=>({metric,...values}));$('comparison-table').innerHTML=table(comparisons);
  $('explanation-list').innerHTML=result.explanations.shipments.map(row=>'<article class="card explanation"><h3>'+escape(row.batch_id)+' → '+escape(row.destination_id)+'<span class="badge">'+escape(number(row.quantity))+' '+escape(unit)+'</span></h3><p>'+escape(row.reason)+'</p></article>').join('');
  $('remaining-table').innerHTML=table(result.explanations.remaining_inventory);$('utilization-table').innerHTML=table(result.explanations.constraint_utilization);$('rejection-table').innerHTML=table(result.explanations.rejected_allocations);
  $('discount-list').innerHTML=result.discount_scenarios.length?result.discount_scenarios.map(row=>'<article class="card explanation"><h3>'+escape(row.batch_id)+' · '+(row.suggested_discount_percent===null?'No economically viable markdown':escape(row.suggested_discount_percent)+'% markdown scenario')+'</h3><p>'+escape(row.reason)+'</p><p style="margin-top:10px">Break-even quantity multiplier: '+(row.break_even_quantity_multiplier===null?'undefined':number(row.break_even_quantity_multiplier,2))+' · Additional sales assumed: 0</p></article>').join(''):'<p class="muted">No at-risk unshipped inventory requires a markdown scenario.</p>';
  $('solver-metadata').textContent=JSON.stringify({status:p.status,runtime_seconds:p.runtime_seconds,primary_objective:p.primary_objective,secondary_status:p.secondary_status,mip_gap:p.mip_gap,message:p.message,browser_runtime:version},null,2);
  document.querySelectorAll('.download').forEach(el=>el.disabled=false);$('disruption-results').innerHTML='';$('replan').disabled=false;
}
$('replan').onclick=async()=>{
  try{
    error('');setBusy(true);status('Revalidating changed conditions and solving a new feasible plan…','busy');
    const changes={delay_hours:Number($('delay').value),capacity_factor:Number($('capacity-factor').value)/100,demand_factor:Number($('demand-factor').value)/100,price_factor:Number($('price-factor').value)/100,inventory_factor:Number($('inventory-factor').value)/100,route_id:$('delay-route').value||null};
    disrupted=await call('disrupt',JSON.stringify(result.scenario),JSON.stringify(result.optimized_plan),JSON.stringify(changes),currentLimit());
    const r=disrupted.replanning,m=disrupted.optimized_metrics,b=disrupted.baseline_metrics;
    $('disruption-results').innerHTML='<div class="notice">'+(r.previous_plan_feasible?'Previous plan remains feasible under the updated conditions.':'Previous plan is infeasible under the updated conditions. Its old revenue is not a feasible benchmark.')+'</div>'+(r.previous_plan_violations.length?'<div class="card explanation"><p>'+r.previous_plan_violations.map(escape).join('<br>')+'</p></div>':'')+'<div class="disruption-metrics"><article class="metric"><div>Updated optimized net revenue</div><strong>'+money(m.net_revenue)+'</strong><small>'+escape(disrupted.scenario.config.currency)+' · baseline '+money(b.net_revenue)+'</small></article><article class="metric"><div>Updated demand fulfillment</div><strong>'+number(m.demand_fulfillment_percent)+'%</strong><small>'+m.constraint_violations.length+' constraint violations</small></article><article class="metric"><div>Updated spoilage</div><strong>'+number(m.spoiled_quantity)+'</strong><small>'+escape(disrupted.scenario.config.quantity_unit)+' by horizon</small></article></div><h3>Allocation changes</h3><div class="card table-card">'+table(r.changes)+'</div><h3>Updated shipments</h3><div class="card table-card">'+table(disrupted.shipments)+'</div><button class="secondary" id="download-disruption">Download disruption report ↓</button><details><summary>Updated decision evidence and metrics</summary><pre>'+escape(JSON.stringify({metrics:m,explanations:disrupted.explanations},null,2))+'</pre></details>';
    $('download-disruption').onclick=()=>download('freshroute-disruption.json',JSON.stringify(disrupted,null,2),'application/json');
    status('Disruption evaluated · '+disrupted.optimized_plan.status+' · '+m.constraint_violations.length+' constraint violations');
  }catch(err){error(err.message);}finally{setBusy(false);}
};
function parseCSV(text){
  const rows=[];let row=[],field='',quoted=false;
  text=text.replace(/^\uFEFF/,'');
  for(let i=0;i<text.length;i++){const c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){field+='"';i++;}else if(quoted||field==='')quoted=!quoted;else throw new Error('Unexpected quote in CSV');}else if(c===','&&!quoted){row.push(field);field='';}else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;row.push(field);if(row.some(v=>v!==''))rows.push(row);row=[];field='';}else field+=c;}
  if(quoted)throw new Error('Unclosed CSV quote');if(field||row.length){row.push(field);rows.push(row);}const header=rows.shift();if(!header)throw new Error('CSV requires column headers');if(new Set(header).size!==header.length)throw new Error('Duplicate CSV column headers');return rows.map((values,i)=>{if(values.length!==header.length)throw new Error('CSV row '+(i+2)+' has a different number of columns');return Object.fromEntries(header.map((name,j)=>[name,values[j]]));});
}
$('upload').onchange=async event=>{
  try{error('');setBusy(true);const files=[...event.target.files];let raw;
    if(files.length===1&&files[0].name.toLowerCase().endsWith('.json'))raw=JSON.parse(await files[0].text());
    else if(files.length===1&&files[0].name.toLowerCase().endsWith('.xlsx'))raw=await call('xlsx',await files[0].arrayBuffer());
    else{const names=new Map(files.map(file=>[file.name.toLowerCase(),file]));if(!['config.json','inventory.csv','demand.csv','routes.csv','resources.csv'].every(name=>names.has(name)))throw new Error('Select one JSON scenario, one XLSX workbook, or config.json and all four CSV tables together.');raw={config:JSON.parse(await names.get('config.json').text())};for(const name of ['inventory','demand','routes','resources'])raw[name]=parseCSV(await names.get(name+'.csv').text());}
    await validateScenario(raw);showTab('inventory');
  }catch(err){error(err.message);status('Import failed; previous valid inputs retained. Review the field error above.');}finally{setBusy(false);event.target.value='';}
};
$('apply-json').onclick=async()=>{try{error('');setBusy(true);await validateScenario(JSON.parse($('json-editor').value));}catch(err){error(err.message);}finally{setBusy(false);}};
function download(name,content,type){const url=URL.createObjectURL(new Blob([content],{type}));const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function csv(rows){if(!rows?.length)return '';const keys=Object.keys(rows[0]);const cell=value=>{let s=String(value??'');if(typeof value==='string'&&/^[\s]*[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};return [keys.map(cell).join(','),...rows.map(row=>keys.map(key=>cell(row[key])).join(','))].join('\r\n');}
document.querySelectorAll('.download').forEach(button=>button.onclick=()=>{if(!result)return;const kind=button.dataset.kind;if(kind==='report')download('freshroute-report.json',JSON.stringify(result,null,2),'application/json');if(kind==='shipments')download('freshroute-shipments.csv',csv(result.shipments),'text/csv');if(kind==='comparison')download('freshroute-comparison.csv',csv(Object.entries(result.comparison).map(([metric,values])=>({metric,...values}))),'text/csv');});
$('download-scenario').onclick=()=>{if(scenario)download('freshroute-scenario.json',JSON.stringify(scenario,null,2),'application/json');};
launchEngine();demo().catch(err=>error(err.message));
