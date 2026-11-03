'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('trance-studio/web/studio.html','utf8');
const start=html.indexOf('function studioResponseIsJson(response){');
const end=html.indexOf('async function run(){',start);
assert.ok(start>0&&end>start,'Safe JSON parsing must run before job creation');
const script=html.slice(start,end);
assert.match(script,/await studioJson\(response\)/);
assert.match(script,/body=await studioJson\(response\)/);
assert.match(html,/var j=await studioJson\(statusResponse\)/);
assert.match(html,/for\(var busy=0;busy<32;busy\+\+\)/);
assert.match(html,/var statusResponse=await readExistingJobStatus\(data\.status_url\)/);
assert.doesNotMatch(script,/setInterval|\bwindow\.kolboImportSharedAudio\b/);
function response(code,contentType,data){
 return {status:code,ok:code>=200&&code<300,
   headers:{get:()=>contentType},json:async()=>data};
}
async function execute(replies){
 let count=0;
 const context={fetch:async()=>{const r=replies[Math.min(count,replies.length-1)];count++;return r},
      message:()=>{},pause:async()=>{}};
 vm.runInNewContext(script+'\nthis.submitMixJob=submitMixJob;',context);
 return {context,get count(){return count}};
}
(async()=>{
 const html502=await execute([response(502,'text/html','Render temporary proxy page')]);
 await assert.rejects(html502.context.submitMixJob({}),e=>
   /HTTP 502/.test(e.message)&&/לא תישלח הקלטה שוב אוטומטית/.test(e.message));
 assert.equal(html502.count,1,'A 502 during POST cannot cause an automatic duplicate upload');
 const html429=await execute([response(429,'text/html','Render overloaded')]);
 await assert.rejects(html429.context.submitMixJob({}),/429/);
 assert.equal(html429.count,1,
   'An HTML 429 from the free proxy is backpressure, never a repeat upload');
 const html200=await execute([response(200,'text/html','wake splash')]);
 await assert.rejects(html200.context.submitMixJob({}),/עמוד במקום נתוני מיקס \(HTTP 200\)/);
 assert.equal(html200.count,1);
 const malformed=await execute([{status:202,ok:true,headers:{get:()=> 'application/json'},
     json:async()=>{throw Error('broken')} }]);
 await assert.rejects(malformed.context.submitMixJob({}),/תשובה פגומה מהשרת \(HTTP 202\)/);
 assert.equal(malformed.count,1);
 const success=await execute([response(202,'application/json',{id:'b'.repeat(48),status_url:'/api/jobs/'+'b'.repeat(48)})]);
 const job=await success.context.submitMixJob({});assert.equal(job.id.length,48);
 assert.equal(success.count,1);
 console.log('RENDER_HTML_GATEWAY_RESPONSE_IS_ACTIONABLE_WITHOUT_DUPLICATING_WHATSAPP_UPLOAD_PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
