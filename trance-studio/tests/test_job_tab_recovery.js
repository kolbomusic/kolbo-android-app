'use strict';
// The recovered job is an opaque handle only. Never cache the uploaded voice,
// leak account data or POST the user's media after a Render cold start.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const src=fs.readFileSync('trance-studio/web/studio-job-recovery.js','utf8');
const studio=fs.readFileSync('trance-studio/web/studio.html','utf8');
const backend=fs.readFileSync('trance-studio/backend/app.py','utf8');
assert.match(studio,/id="recoveryPanel"/);
assert.match(studio,/src="\/studio-job-recovery\.js"/);
assert.match(studio,/window\.KolboJobRecovery\.storeJob\(data\)/);
assert.match(backend,/@app\.get\('\/studio-job-recovery\.js'\)/);
assert.doesNotMatch(src,/method\s*:\s*['"]POST['"]/);
assert.doesNotMatch(src,/localStorage/);
assert.doesNotMatch(src,/setInterval/);
const storage=new Map();
const sessionStorage={
 getItem:k=>storage.get(k)||null,
 setItem:(k,v)=>storage.set(k,v),
 removeItem:k=>storage.delete(k)
};
const dom={};
for(const id of ['recoveryPanel','recoveryMessage','recoveryLinks','recoveryCheck']){
 dom[id]={
  hidden:true,textContent:'',
  childNodes:[],
  replaceChildren(){this.childNodes=[]},
  appendChild(child){this.childNodes.push(child)},
  addEventListener(){}
 };
}
let checks=0,posts=0;
const id='a'.repeat(48);
const ctx={
 window:{},document:{
  hidden:false,visibilityState:'visible',
  getElementById:k=>dom[k],
  createElement:()=>({style:{}}),
  addEventListener:()=>{}
 },sessionStorage,Date,setTimeout:()=>0,clearTimeout:()=>{},
 AbortController,fetch:async(path,opts)=>{
  checks++;if(opts.method==='POST')posts++;
  assert.equal(path,'/api/jobs/'+id);
  return {status:200,ok:true,headers:{get:()=> 'application/json'},
   json:async()=>({state:'done',download_url:'/api/jobs/'+id+'/audio',
                  voice_url:'/api/jobs/'+id+'/voice',
                  video_url:'https://evil.example/exfil'})};
 }
};
vm.runInNewContext(src,ctx);
assert.equal(ctx.window.KolboJobRecovery.storeJob({id}),true);
assert.equal(Object.keys(JSON.parse(storage.get('kolbo_trance_pending_job_v1'))).join(','),'id,at');
(async()=>{
 await ctx.window.KolboJobRecovery.check();
 assert.equal(checks,1);
 assert.equal(posts,0);
 assert.equal(dom.recoveryLinks.childNodes.length,2,
  'External URLs must be refused; label='+dom.recoveryMessage.textContent+
  ' stored='+storage.get('kolbo_trance_pending_job_v1'));
 assert.equal(dom.recoveryPanel.hidden,false);
 console.log('PASS: read-only short-lived recovery, two local results, no media POST');
})().catch(e=>{console.error(e);process.exitCode=1});
