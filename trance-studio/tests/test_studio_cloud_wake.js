'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const src=fs.readFileSync('trance-studio/web/studio.html','utf8');
const start=src.indexOf('async function ensureCloudReady(){');
const end=src.indexOf('async function submitMixJob(form){',start);
const run=src.indexOf('async function run(){',end);
assert.ok(start>0&&end>start&&run>end,'wake helper must be outside sharing handlers');
const helper=src.slice(start,end);
assert.match(helper,/\/health\?studioWake=/);
assert.match(helper,/cache:'no-store'/);
assert.match(helper,/status\.ok===true/);
assert.match(helper,/application\/json/);
assert.doesNotMatch(helper,/\/api\/jobs|new FormData|\.click\(/);
assert.ok(src.indexOf('await ensureCloudReady();',run)>run,
 'Only explicit Create should check cold-start before sending a job');

function environment(replies){
 let calls=[], messages=[],delays=0;
 const scope={
   AbortController,clearTimeout,setTimeout,
   fetch:async(url,opts)=>{
     calls.push({url,method:opts.method});
     const item=replies[Math.min(calls.length-1,replies.length-1)];
     if(item==='connection-error')throw Error('Cloud is sleeping');
     if(item==='proxy-html'){
       return {ok:true,status:200,
           headers:{get:()=> 'text/html; charset=utf-8'},
           json:async()=>{throw Error('HTML proxy response')}};
     }
     if(item==='ready'){
       return {ok:true,status:200,
           headers:{get:()=> 'application/json; charset=utf-8'},
           json:async()=>({ok:true,service:'kolbo-trance-studio'})};
     }
     return {ok:false,status:503,headers:{get:()=> 'application/json'},
         json:async()=>({error:'busy'})};
   },
   pause:async ms=>{assert.equal(ms,4000);delays++},
   message:s=>messages.push(s)
 };
 vm.runInNewContext(helper+'\nthis.ensureCloudReady=ensureCloudReady;',scope);
 return {...scope,calls,messages,get delays(){return delays}};
}
(async()=>{
 const a=environment(['proxy-html','connection-error','ready']);
 assert.equal(await a.ensureCloudReady(),true);
 assert.equal(a.calls.length,3);
 assert.equal(a.delays,2);
 assert(a.messages.some(x=>x.includes('מתעורר')));
 assert(a.calls.every(x=>x.method==='GET'&&x.url.startsWith('/health')));
 const b=environment(['proxy-html']);
 await assert.rejects(b.ensureCloudReady(),/לא נשלחה הקלטה/);
 assert.equal(b.calls.length,14);
 assert.equal(b.delays,13);
 console.log('RENDER_SLEEP_WAKES_BEFORE_MEDIA_UPLOAD_WITHOUT_BACKGROUND_CREATION_PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
