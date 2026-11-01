'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const src=fs.readFileSync('trance-studio/web/studio-ai-fallback.js','utf8');
const from=src.indexOf('async function generate(jobId,onStage,passedPrompt,passedScenes){');
const to=src.indexOf('window.KolboAIFallback=',from);
assert.ok(from>0&&to>from,'phone AI recovery implementation must exist');
let gpuCalls=0,muxCalls=0;
const messages=[];
class FakeFormData{
 constructor(){this.values=[]}
 append(name,data,filename){this.values.push({name,data,filename})}
}
const vars={
 FormData:FakeFormData,encodeURIComponent,
 MODELS:[{id:'ltx25'}],
 getPlan:async()=>['Photorealistic real scene: החמור נוער'],
 oneClip:async()=>{gpuCalls++;return {size:50000}},
 fail:(message)=>new Error(message),
 document:{getElementById:()=>({checked:true})},
 fetch:async()=>{
  muxCalls++;
  if(muxCalls===1)return {
    status:429,ok:false,headers:{get:()=> '0'},
    json:async()=>({error:'busy'})};
  return {status:200,ok:true,headers:{get:()=>null},
    json:async()=>({video_url:'/api/jobs/abc/video',
      video_status:'done',ai_clips_generated:1})};
 },
 setTimeout:(fn)=>{fn();return 1},
 Promise
};
vm.createContext(vars);
vm.runInContext(src.slice(from,to),vars);
(async()=>{
 const result=await vars.generate('a'.repeat(48),m=>messages.push(m),
            'photorealistic red ball: החמור',null);
 assert.equal(result.video_status,'done');
 assert.equal(gpuCalls,1,'Busy Render must not trigger AI re-generation');
 assert.equal(muxCalls,2,'The same already-generated video must retry');
 assert.ok(messages.some(m=>m.includes('השרת עסוק')));
 console.log('PHONE_AI_MP4_SAVED_AND_RETRIED_WITHOUT_GPU_REGENERATION_PASS');
})().catch(err=>{console.error(err);process.exitCode=1});
