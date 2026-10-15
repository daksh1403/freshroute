/* Python runs in a worker so the interface remains usable during optimization. */
let python;
let queue=Promise.resolve();
const progress=text=>self.postMessage({type:'progress',text});
async function initialize(){
  progress('Loading the local Python runtime…');
  const config=await (await fetch('./runtime-config.json')).json();
  const indexURL=new URL(config.index_url,self.location.href).href;
  const {loadPyodide}=await import(indexURL+'pyodide.mjs');
  python=await loadPyodide({indexURL});
  progress('Loading NumPy, SciPy and the HiGHS mathematical solver…');
  await python.loadPackage('scipy',{messageCallback:progress,checkIntegrity:true});
  const manifest=await (await fetch('./python/manifest.json')).json();
  python.FS.mkdirTree('/home/pyodide/freshroute');
  for(const name of manifest){
    const response=await fetch('./python/'+name);
    if(!response.ok)throw new Error('Cannot load Python source: '+name);
    python.FS.writeFile('/home/pyodide/'+name,await response.text());
  }
  await python.runPythonAsync('from freshroute.webbridge import run, preview, disrupt, workbook, ai_review, ai_apply, ai_facts, ai_whatif');
  self.postMessage({type:'ready',version:python.version});
}
async function handle({id,method,args}){
  try{
    if(method==='xlsx'){
      progress('Loading the local spreadsheet parser…');
      const archive=await (await fetch('./xlsx-support.zip')).arrayBuffer();
      python.unpackArchive(archive,'zip',{extractDir:'/home/pyodide'});
      const value=python.toPy(new Uint8Array(args[0]));
      python.globals.set('xlsx_data',value);
      try{self.postMessage({id,result:await python.runPythonAsync('workbook(bytes(xlsx_data))')});}
      finally{value.destroy();python.globals.delete('xlsx_data');}
      return;
    }
    if(!['run','preview','disrupt','ai_review','ai_apply','ai_facts','ai_whatif'].includes(method))throw new Error('Unknown operation');
    args.forEach((arg,index)=>python.globals.set('arg_'+index,arg));
    try{
      const result=await python.runPythonAsync(`${method}(${args.map((_,i)=>'arg_'+i).join(',')})`);
      self.postMessage({id,result});
    }finally{args.forEach((_,i)=>python.globals.delete('arg_'+i));}
  }catch(error){self.postMessage({id,error:String(error)});}
}
self.onmessage=({data})=>{queue=queue.then(()=>handle(data));};
initialize().catch(error=>self.postMessage({type:'fatal',error:String(error)}));
