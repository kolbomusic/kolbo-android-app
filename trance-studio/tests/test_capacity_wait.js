'use strict';
/* A second user must wait for capacity via GET, not upload their WhatsApp
   voice/video twice while the free single-worker Render service is busy. */
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const src=fs.readFileSync('trance-studio/web/studio.html','utf8');
const start=src.indexOf('function studioResponseIsJson(response){');
const end=src.indexOf('async function run(){',start);
assert.ok(start>=0&&end>start);
const helper=src.slice(start,end);
const run=src.slice(end);
assert.match(run,/await waitForJobCapacity\(\);\s*var data=await submitMixJob\(form\);/);
assert.equal((run.match(/var data=await submitMixJob\(form\)/g)||[]).length,1);
function resp(status,body,type='application/json'){
 return {status,ok:status>=200&&status<300,
         headers:{get:()=>type},json:async()=>body};
}
function makeEnv(fetch){
 const alerts=[];
 const context={
  fetch, message:x=>alerts.push(x),
  pause:async()=>{},AbortController,setTimeout,clearTimeout
 };
 vm.createContext(context);
 vm.runInContext(helper+'\nthis.waitForJobCapacity=waitForJobCapacity;'+
                 '\nthis.submitMixJob=submitMixJob;',context);
 return {context,alerts};
}
(async()=>{
 let get=0,post=0;
 const job={id:'a'.repeat(48),status_url:'/api/jobs/'+'a'.repeat(48)};
 const first=makeEnv(async (url,options)=>{
  if(options.method==='GET'){
   get++;
   assert.equal(url,'/api/jobs/capacity');
   return resp(200,{available:get>=3});
  }
  post++;assert.equal(url,'/api/jobs');return resp(202,job);
 });
 await first.context.waitForJobCapacity();
 const accepted=await first.context.submitMixJob({original:'voice'});
 assert.equal(accepted.id,job.id);
 assert.equal(get,3);
 assert.equal(post,1);
 assert.ok(first.alerts.some(x=>x.includes('הקובץ נשאר במכשיר')));
 let blockedGet=0,blockedPost=0;
 const full=makeEnv(async(url,options)=>{
  if(options.method==='GET'){
   blockedGet++;return resp(200,{available:false});
  }
  blockedPost++;throw Error('Never upload to a full queue');
 });
 await assert.rejects(full.context.waitForJobCapacity(),/כל מקומות התור תפוסים/);
 assert.equal(blockedGet,45);
 assert.equal(blockedPost,0);
 let deniedGet=0,deniedPost=0;
 const denied=makeEnv(async(url,options)=>{
  if(options.method==='GET'){deniedGet++;return resp(401,{error:'unauthorized'});}
  deniedPost++;throw Error('Not allowed');
 });
 await assert.rejects(denied.context.waitForJobCapacity(),/התחברות מחודשת/);
 assert.equal(deniedGet,1);
 assert.equal(deniedPost,0);
 console.log('RENDER_CAPACITY_WAIT_BEFORE_SINGLE_MEDIA_POST_PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
