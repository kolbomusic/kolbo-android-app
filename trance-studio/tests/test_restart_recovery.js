'use strict';
/* A WhatsApp share only imports files. Recovery belongs inside an explicit
   Create action; it may submit a lost job once, never loop indefinitely. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const src=fs.readFileSync('trance-studio/web/studio.html','utf8');
const begin=src.indexOf('async function submitMixJob(form){');
const end=src.indexOf('async function run(){',begin);
assert.ok(begin>0&&end>begin,'bounded submission helper exists');
const helper=src.slice(begin,end);
assert.match(src,/var lostJobRecovery=0;/);
assert.match(src,/statusResponse\.status===404&&lostJobRecovery<1/);
assert.match(src,/data=await submitMixJob\(form\);\s*attempt=0;/);
assert.match(src,/temporaryStatusFailures<=4/);
assert.match(src,/\[502,503,504\]/);
assert.doesNotMatch(helper,/setTimeout|setInterval|window\.kolboImportSharedAudio/);
assert.ok(src.indexOf("$('generate').onclick=run;")>end);
async function check(){
 let calls=0,waits=0,status=[];
 const replies=[429,202];
 const ctx={
  message:x=>status.push(x),
  pause:async()=>{waits++;},
  fetch:async()=>{
    const code=replies[calls++];
    return {status:code,ok:code===202,json:async()=>code===202?
      {id:'a'.repeat(48),status_url:'/api/jobs/'+'a'.repeat(48)}:
      {error:'שרת עסוק'}};
  }
 };
 vm.runInNewContext(helper+'\nthis.submitMixJob=submitMixJob;',ctx);
 const job=await ctx.submitMixJob({original:'voice'});
 assert.equal(calls,2);
 assert.equal(waits,1);
 assert.equal(job.id.length,48);
 assert.ok(status[0].includes('עסוק'));
 let errors=0;
 const failedCtx={
  message:()=>{},pause:async()=>{},
  fetch:async()=>{errors++;return {status:500,ok:false,json:async()=>({error:'תקלה'})}}
 };
 vm.runInNewContext(helper+'\nthis.submitMixJob=submitMixJob;',failedCtx);
 await assert.rejects(failedCtx.submitMixJob({}),/תקלה/);
 assert.equal(errors,1,'Non-429 failures must not generate duplicate server jobs');
 console.log('BOUNDED_RENDER_RESTART_RECOVERY_PASS');
}
check().catch(e=>{console.error(e);process.exitCode=1;});
