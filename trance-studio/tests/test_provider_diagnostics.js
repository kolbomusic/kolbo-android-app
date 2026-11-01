'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const src=fs.readFileSync('trance-studio/web/studio-ai-fallback.js','utf8');
const model={};
const context={
 window:model,
 URL,
 AbortController,
 Promise,
 setTimeout,
 clearTimeout,
 fetch:async()=>({status:429,ok:false})
};
vm.createContext(context);
vm.runInContext(src,context);
function parse(text){
 return vm.runInContext('parseEventStream('+JSON.stringify(text)+',"lightricks-ltx-2-5.hf.space")',context);
}
for(const message of ['ZeroGPU quota exceeded','Reached gpu limit','Too many requests']){
 const event='event: error\ndata: '+JSON.stringify({error:message+' private-recording-phrase'})+'\n\n';
 assert.throws(()=>parse(event),err=>
   /GPU/.test(err.message)&&err.providerQuota===true&&!err.message.includes('private-recording-phrase'));
}
assert.throws(()=>parse('event: error\ndata: '+JSON.stringify({message:'GPU busy private-recording-phrase'})+'\n\n'),
  err=>err.providerTransient===true&&!err.message.includes('private-recording-phrase'));
assert.throws(()=>parse('event: error\ndata: '+JSON.stringify({message:'internal crash private-recording-phrase'})+'\n\n'),
  err=>!err.message.includes('private-recording-phrase'));
(async()=>{
 await assert.rejects(vm.runInContext(
   "getResponse('https://lightricks-ltx-2-5.hf.space/gradio_api/call/v2/run',{},200)",context),
   err=>err.providerQuota===true&&err.message.includes('429'));
 context.fetch=async()=>({status:503,ok:false});
 await assert.rejects(vm.runInContext(
   "getResponse('https://lightricks-ltx-2-5.hf.space/gradio_api/call/v2/run',{},200)",context),
   err=>err.providerTransient===true&&err.message.includes('503'));
 console.log('PUBLIC_VIDEO_FAILURES_CATEGORIZED_WITHOUT_LEAKING_PRIVATE_TRANSCRIPT_PASS');
})().catch(err=>{console.error(err);process.exitCode=1});
