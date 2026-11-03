'use strict';
/* Exercise a real async preview gate: a second Create tap must be ignored
   BEFORE hasDecodableVideoTrack resolves and before upload is scheduled. */
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const src=fs.readFileSync('trance-studio/web/studio.html','utf8');
const start=src.indexOf('async function run(){');
const end=src.indexOf("if($('make_video').checked&&$('video_strategy').value==='new_story'",start);
assert.ok(start>=0&&end>start);
const prefix=src.slice(start,end);
assert.match(prefix,/if\(active\|\|runLock\)return;/);
assert.match(prefix,/runLock=true;/);
assert.match(prefix,/await hasDecodableVideoTrack/);
const partial=prefix+
 "\n}finally{runLock=false;$('generate').disabled=!files.length;}"+
 "\n}\nthis.run=run;";
const file={name:'whatsapp-video.mp4',type:'video/mp4',size:2000};
let previews=0,resolvePreflight;
const prompt=new Promise(resolve=>{resolvePreflight=resolve});
const ui={generate:{disabled:false},video_strategy:{value:'remix_original'}};
const ctx={
 active:false,runLock:false,files:[file],socialImported:false,
 $:id=>ui[id]||{checked:true,focus:()=>{}},
 isVideoFile:()=>true,window:{kolboVideoPreflightActive:false},
 hasDecodableVideoTrack:async()=>{previews++;return prompt;},
 message:()=>{},selectNewStoryFromVoice:()=>{throw Error('Unexpected mode switch')},
 };
vm.createContext(ctx);
vm.runInContext(partial,ctx);
(async()=>{
 const first=ctx.run();
 assert.equal(ctx.runLock,true);
 assert.equal(ui.generate.disabled,true);
 const second=ctx.run();
 await second;
 assert.equal(previews,1,'Double tap must not start second local preview');
 resolvePreflight(true);
 await first;
 assert.equal(ctx.runLock,false);
 assert.equal(ui.generate.disabled,false);
 console.log('CREATE_DOUBLE_TAP_BLOCKED_DURING_ASYNC_VIDEO_PREFLIGHT_PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
