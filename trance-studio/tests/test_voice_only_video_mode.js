'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('trance-studio/web/studio.html','utf8');
const start=html.indexOf('function message(txt)');
const end=html.indexOf('function youtubeId(url){',start);
assert(start>0&&end>start,'File and video mode selection block must be accessible');
const fragment=html.slice(start,end);
assert.match(html,/id="switchToAiVideo"/);
assert.match(html,/switchButton\.onclick=function\(\)/);
assert.match(html,/if\(\$\('video_strategy'\)\.value==='remix_original'\)\{/);
const run=html.slice(html.indexOf('async function run(){'));
assert(run.indexOf("if($('video_strategy').value==='remix_original')")<
       run.indexOf("active=true;markStage('upload')"),
       'Do not render a full audio mix before validating original-video mode');
assert(run.includes('await hasDecodableVideoTrack(candidates[vi])'));
const elements={
  video_strategy:{value:'remix_original',focus:()=>{}},
  files:{textContent:''},
  generate:{disabled:false},
  status:{textContent:''}
};
let explanationCalls=0;
const url={
  createObjectURL:()=> 'blob:test-local',
  revokeObjectURL:()=>{}
};
const doc={
 createElement:()=> {
  const video={videoWidth:0,videoHeight:0,onloadedmetadata:null,onerror:null,
   preload:'',muted:false,playsInline:false,src:'',
   removeAttribute:()=>{},
   load(){
    if(this.src&&this.onloadedmetadata)
     Promise.resolve().then(()=>this.onloadedmetadata());
   }
  };
  return video;
 }
};
const ctx={files:[],active:false,socialImported:false,
 videoModeChosenByUser:true,
 explainVideoStrategy:()=>{explanationCalls++},
 $:id=>elements[id],
 window:{URL:url},
 URL:url,document:doc,setTimeout,clearTimeout};
vm.createContext(ctx);
vm.runInContext(fragment+';this.setFiles=setFiles;this.hasDecodableVideoTrack=hasDecodableVideoTrack;',ctx);
(async()=>{
 ctx.setFiles([{name:'whatsapp-voice.opus',type:'audio/ogg',size:12345}]);
 assert.equal(elements.video_strategy.value,'new_story',
  'A manually chosen original-video mode must not survive a voice-only upload');
 assert.match(elements.status.textContent,/הקלטת קול/);
 assert.equal(elements.generate.disabled,false);
 assert.equal(ctx.files.length,1,'Original voice remains selected');
 assert.equal(ctx.videoModeChosenByUser,false);
 ctx.setFiles([{name:'moving-video.mp4',type:'video/mp4',size:123450}]);
 assert.equal(elements.video_strategy.value,'remix_original',
  'A genuine video selected after audio automatically returns to video remix');
 assert(explanationCalls>=2);
 assert.equal(await ctx.hasDecodableVideoTrack({
   name:'audio-only-file.mp4',type:'video/mp4',size:12000
 }),false,'An MP4 with audio-only videoWidth=0 must not be claimed as a video');
 assert.equal(await ctx.hasDecodableVideoTrack({
   name:'voice.opus',type:'audio/ogg',size:12000
 }),false);
 console.log('VOICE_ONLY_PREVENTS_IMPOSSIBLE_VIDEO_REMIX_AND_OFFERS_AI_RECOVERY_PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
