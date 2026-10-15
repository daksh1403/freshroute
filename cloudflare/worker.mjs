import {generate} from './intelligence.mjs';
import {MODELS} from './contracts.mjs';
const json=(value,status=200)=>Response.json(value,{status,headers:{'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
export default {
 async fetch(request,env){
  const url=new URL(request.url);
  if(url.pathname.startsWith('/runtime/')){
   const asset=await env.ASSETS.fetch(request);if(asset.status!==404)return asset;
   const name=url.pathname.slice('/runtime/'.length);
   const allowed=['pyodide.mjs','pyodide.js','pyodide.asm.mjs','pyodide.asm.wasm','pyodide-lock.json','python_stdlib.zip','numpy-2.4.6-cp314-cp314-pyemscripten_2026_0_wasm32.whl','scipy-1.18.0-cp314-cp314-pyemscripten_2026_0_wasm32.whl'];
   if(!allowed.includes(name)||!['GET','HEAD'].includes(request.method))return json({error:'Unknown runtime asset'},404);
   const upstream=await fetch('https://cdn.jsdelivr.net/pyodide/v314.0.7/full/'+name,{cf:{cacheTtl:86400,cacheEverything:true}});
   const response=new Response(upstream.body,upstream);if(upstream.ok)response.headers.set('Cache-Control','public, max-age=86400, immutable');return response;
  }
  if(url.pathname==='/api/health')return json({ok:true,service:'FreshRoute Intelligence',runtime:'Cloudflare Workers',core_solver:'Python/SciPy in browser worker'});
  if(url.pathname==='/api/ai/status')return json({configured:Boolean(env.GEMINI_API_KEY),model:env.GEMMA_MODEL||MODELS[0],allowed_models:MODELS,provider:'Google Gemini API / official Google GenAI SDK',availability:env.GEMINI_API_KEY?'configured; actual requests verify provider access':'unavailable: API key missing',core_available:true});
  if(!url.pathname.startsWith('/api/ai/'))return env.ASSETS.fetch(request);
  if(request.method!=='POST')return json({error:'Use POST'},405);
  const origin=request.headers.get('Origin');if(origin&&origin!==url.origin)return json({error:'Cross-origin AI requests are not allowed'},403);
  if(env.AI_RATE_LIMITER){const {success}=await env.AI_RATE_LIMITER.limit({key:request.headers.get('CF-Connecting-IP')||'local'});if(!success)return json({error:'AI request limit reached. Please wait a minute; optimization remains available.'},429);}
  if(Number(request.headers.get('Content-Length')||0)>6000000)return json({error:'Request too large; use an image under 3 MB'},413);
  try{
   const raw=await request.text();if(raw.length>6000000)return json({error:'Request too large'},413);
   const result=await generate(url.pathname.split('/').pop(),JSON.parse(raw),env);
   console.log(JSON.stringify({task:result.task,model:result.model,latency_ms:result.latency_ms,status:'success'}));
   return json(result);
  }catch(error){
   const message=String(error.message||error).replaceAll(env.GEMINI_API_KEY||'__no_key__','[REDACTED]');
   const provider=error.status||error.code;const status=provider===429?429:provider>=500?503:provider===401||provider===403?503:400;
   return json({error:message.slice(0,1500),core_available:true,model:env.GEMMA_MODEL||MODELS[0]},status);
  }
 }
};
