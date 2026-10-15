import {loadPyodide} from 'pyodide';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
async function test(){
  const root=fileURLToPath(new URL('../',import.meta.url));
  const python=await loadPyodide({indexURL:root+'dist/runtime/'});
  await python.loadPackage('scipy');
  python.FS.mkdirTree('/home/pyodide/freshroute');
  for(const file of JSON.parse(fs.readFileSync(root+'dist/python/manifest.json'))){python.FS.writeFile('/home/pyodide/'+file,fs.readFileSync(root+'dist/python/'+file,'utf8'));}
  python.globals.set('raw',fs.readFileSync(root+'dist/demo.json','utf8'));
  await python.runPythonAsync(`
import json
from freshroute.webbridge import run, disrupt
result=json.loads(run(raw,15))
assert result['optimized_plan']['status']=='optimal',result['optimized_plan']
assert abs(result['optimized_metrics']['net_revenue']-21123)<1e-5,result['optimized_metrics']
assert abs(result['baseline_metrics']['net_revenue']-19811)<1e-5
assert result['optimized_metrics']['constraint_violations']==[]
changed=json.loads(disrupt(raw,json.dumps(result['optimized_plan']),json.dumps({'delay_hours':6,'capacity_factor':0.7}),15))
assert changed['optimized_metrics']['constraint_violations']==[]
assert changed['replanning']['previous_plan_feasible'] is False
print(json.dumps({'runtime':'WebAssembly/Pyodide','baseline_net':result['baseline_metrics']['net_revenue'],'optimized_net':result['optimized_metrics']['net_revenue'],'status':result['optimized_plan']['status'],'disruption_net':changed['optimized_metrics']['net_revenue'],'violations':0}))
`);
}
test().catch(error=>{console.error(String(error));process.exitCode=1;});
