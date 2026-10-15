import {GoogleGenAI,ThinkingLevel} from '@google/genai';
import fs from 'node:fs';
const local=fs.existsSync('.dev.vars')?Object.fromEntries(fs.readFileSync('.dev.vars','utf8').split(/\r?\n/).filter(line=>line.includes('=')).map(line=>{const i=line.indexOf('=');return [line.slice(0,i),line.slice(i+1).trim()];})):{};
const key=process.env.GEMINI_API_KEY||local.GEMINI_API_KEY;
const model=process.env.GEMMA_MODEL||local.GEMMA_MODEL||'gemma-4-26b-a4b-it';
if(!key){console.error('GEMINI_API_KEY is missing');process.exit(1);}
const client=new GoogleGenAI({apiKey:key,httpOptions:{timeout:30000,retryOptions:{attempts:1}}});
try{
 const info=await client.models.get({model});
 const start=performance.now();
 const response=await client.models.generateContent({model,contents:'Reply with exactly: GEMMA_READY',config:{maxOutputTokens:256,thinkingConfig:{thinkingLevel:ThinkingLevel.MINIMAL}}});
 console.log(JSON.stringify({model:info.name,model_version:response.modelVersion,latency_ms:Math.round(performance.now()-start),text:response.text,live:true}));
}catch(error){console.error(String(error).replaceAll(key,'[REDACTED]').slice(0,2500));process.exitCode=1;}
