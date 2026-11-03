'use strict';
/* Transient Render 429 during STATUS GET must never trigger another media POST. */
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const src=fs.readFileSync('trance-studio/web/studio.html','utf8');
const from=src.indexOf('function studioResponseIsJson(response){');
const to=src.indexOf('async function run(){',from);
assert.ok(from>0&&to>from);
assert.equal((src.match(/var data=await submitMixJob\(form\)/g)||[]).length,1);
const helpers=src.slice(from,to);
function result(code,contentType='application/json',retryAfter=''){
 return {
   status:code,ok:code>=200&&code<300,
   headers:{get:header=>
      String(header).toLowerCase()==='retry-after'?retryAfter:contentType},
   json:async()=>({state:'processing',percent:50})
 };
}
function context(replies){
 const requests=[],delays=[],messages=[];
 const scope={
   fetch:async(url,options)=>{
     requests.push({url,method:options.method});
     return replies[Math.min(requests.length-1,replies.length-1)];
   },
   pause:async ms=>{delays.push(ms)},
   message:msg=>{messages.push(msg)},
   Number,Math
 };
 vm.createContext(scope);
 vm.runInContext(helpers+'\nthis.readExistingJobStatus=readExistingJobStatus;',scope);
 return {scope,requests,delays,messages};
}
(async()=>{
 const url='/api/jobs/'+'a'.repeat(48);
 const first=context([
   result(429,'text/html','5'),
   result(502,'text/html'),
   result(429,'application/json','15'),
   result(200)
 ]);
 const ready=await first.scope.readExistingJobStatus(url);
 assert.equal(ready.status,200);
 assert.equal(first.requests.length,4);
 assert(first.requests.every(r=>r.method==='GET'&&r.url===url));
 assert(first.delays[0]>=5000);
 assert(first.delays[2]>=15000);
 assert(first.messages.some(x=>x.includes('429')));
 const longBusy=context(Array.from({length:32},()=>result(429,'text/html')));
 await assert.rejects(longBusy.scope.readExistingJobStatus(url),/מספר המשימה נשמר/);
 assert.equal(longBusy.requests.length,32);
 assert.equal(longBusy.delays.length,31);
 assert(longBusy.requests.every(r=>r.method==='GET'));
 const missing=context([result(404)]);
 await assert.rejects(missing.scope.readExistingJobStatus(url),/איבד את המשימה/);
 assert.equal(missing.requests.length,1);
 const auth=context([result(401)]);
 const authResult=await auth.scope.readExistingJobStatus(url);
 assert.equal(authResult.status,401,'Nontransient auth errors must not loop');
 console.log('STATUS_429_RETRIES_SAME_JOB_WITHOUT_DUPLICATE_WHATSAPP_POST_PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
