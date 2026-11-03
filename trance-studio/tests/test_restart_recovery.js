'use strict';
/* A WhatsApp share imports files; one Create tap may send at most one POST.
   Render 512 MiB restarts and HTTP 429 never trigger automatic reuploads. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const src=fs.readFileSync('trance-studio/web/studio.html','utf8');
const begin=src.indexOf('function studioResponseIsJson(response){');
const end=src.indexOf('async function run(){',begin);
assert.ok(begin>0&&end>begin,'bounded submission helper exists');
const helper=src.slice(begin,end);
assert.match(src,/var active=false,runLock=false;/);
assert.match(src,/async function run\(\)\{\s*if\(active\|\|runLock\)return;\s*runLock=true;/);
assert.match(src,/if\(statusResponse\.status===404\)\{\s*throw new Error/);
assert.match(src,/if\(statusResponse\.status===429\)\{/);
assert.doesNotMatch(src,/lostJobRecovery|busyAttempt/);
assert.equal((src.match(/var data=await submitMixJob\(form\)/g)||[]).length,1);
assert.match(src,/finally\{\s*runLock=false;/);
assert.doesNotMatch(helper,/setInterval|window\.kolboImportSharedAudio/);

const job={id:'a'.repeat(48),status_url:'/api/jobs/'+'a'.repeat(48)};
function response(status,content,body){
 return {status,ok:status>=200&&status<300,
  headers:{get:()=>content},json:async()=>body};
}
async function check(){
 let uploads=0;
 const replies=[
  response(429,'text/html','Render busy page'),
  response(202,'application/json',job),
 ];
 const ctx={
  message:()=>{},pause:async()=>{throw Error('Unexpected automatic delay/retry')},
  fetch:async()=>replies[uploads++],
 };
 vm.runInNewContext(helper+'\nthis.submitMixJob=submitMixJob;',ctx);
 await assert.rejects(ctx.submitMixJob({original:'voice'}),/429/);
 assert.equal(uploads,1,'busy must NOT resubmit user media');
 // A subsequent, explicit NEW click is allowed after the user sees the error.
 const accepted=await ctx.submitMixJob({original:'voice'});
 assert.equal(accepted.id,job.id);
 assert.equal(uploads,2);
 let errors=0;
 const failedCtx={
  message:()=>{},pause:async()=>{},
  fetch:async()=>{errors++;return response(500,'application/json',{error:'תקלה'});}
 };
 vm.runInNewContext(helper+'\nthis.submitMixJob=submitMixJob;',failedCtx);
 await assert.rejects(failedCtx.submitMixJob({}),/תקלה/);
 assert.equal(errors,1,'Non-429 failures must not create another server job');
 console.log('RENDER_RESTART_NEVER_AUTO_REPOSTS_WHATSAPP_MEDIA_PASS');
}
check().catch(err=>{console.error(err);process.exitCode=1});
