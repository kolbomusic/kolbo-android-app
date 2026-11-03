'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const manifest=JSON.parse(fs.readFileSync('trance-studio/web/studio.webmanifest','utf8'));
const accept=manifest.share_target.params.files[0].accept;
assert.ok(accept.includes('video/*'));
assert.ok(accept.includes('audio/*'));
const sw=fs.readFileSync('trance-studio/web/studio-sw.js','utf8');
const ui=fs.readFileSync('trance-studio/web/studio.html','utf8');
assert.match(ui,/files\.some\(isVideoFile\)/,
 'Video from WhatsApp must auto-select the original-source video editor');
assert.match(ui,/\$\('video_strategy'\)\.value='smart_story'/,
 'Source-first smart-video mode automatically edits the uploaded footage before attempting generation');
assert.match(ui,/videoModeChosenByUser/,
 'Never overwrite a deliberate new-story selection');
assert.match(ui,/video_edit_style==='voice_fx_synced_motion_warp'/,
 'Show factual source-video FX sync information only on verified status');
const cached=[];
let listener=null;
class FakeResponse{
 constructor(body,options){this.body=body;this.headers=options?.headers||{}}
 static redirect(url,status){return {url,status}}
}
const context={
 URL,Response:FakeResponse,encodeURIComponent,
 self:{addEventListener:(type,fn)=>{assert.equal(type,'fetch');listener=fn}},
 caches:{open:async()=>({put:async(key,response)=>cached.push({key,response})})}
};
vm.runInNewContext(sw,context);
assert.equal(typeof listener,'function');
async function share(name,type,size){
 let responsePromise;
 const blob={name,type,size};
 listener({
  request:{url:'https://kolbo-trance-studio.onrender.com/studio/share',
    method:'POST',formData:async()=>new Map([['audio',blob]])},
  respondWith:promise=>responsePromise=promise});
 return await responsePromise;
}
(async()=>{
 let result=await share('WA-video.mp4','video/mp4',20*1048576);
 assert.equal(result.url,'/studio?shared=1');
 assert.equal(cached.at(-1).response.headers['content-type'],'video/mp4');
 result=await share('WA-voice.opus','audio/ogg',20*1048576);
 assert.equal(result.url,'/studio?error=upload');
 result=await share('WA-video.mp4','video/mp4',46*1048576);
 assert.equal(result.url,'/studio?error=upload');
 result=await share('WA-video.mp4','',20*1048576);
 assert.equal(result.url,'/studio?shared=1');
 assert.equal(cached.at(-1).response.headers['content-type'],'video/mp4');
 let sharedResponse;
 const multi=[{name:'WA-voice.opus',type:'audio/ogg',size:8*1048576},
              {name:'WA-video.mp4',type:'video/mp4',size:40*1048576}];
 const data={get:key=>key==='audio'?multi[0]:null,getAll:key=>key==='audio'?multi:[]};
 const before=cached.length;
 listener({request:{url:'https://kolbo-trance-studio.onrender.com/studio/share',
  method:'POST',formData:async()=>data},respondWith:promise=>sharedResponse=promise});
 result=await sharedResponse;
 assert.equal(result.url,'/studio?shared=1');
 assert.deepEqual(cached.slice(before).map(x=>x.key),[
  '/studio/shared-count','/studio/shared-audio','/studio/shared-audio/1']);
 assert.match(ui,/sharedClips\.push\(new File\(/);
 assert.match(ui,/setFiles\(sharedClips\)/);
 const excessive=[{name:'one.mp4',type:'video/mp4',size:40*1048576},
                  {name:'two.mp4',type:'video/mp4',size:30*1048576}];
 const tooLarge={get:key=>key==='audio'?excessive[0]:null,
                 getAll:key=>key==='audio'?excessive:[]};
 listener({request:{url:'https://kolbo-trance-studio.onrender.com/studio/share',
  method:'POST',formData:async()=>tooLarge},respondWith:promise=>sharedResponse=promise});
 assert.equal((await sharedResponse).url,'/studio?error=upload');
 console.log('PWA_WHATSAPP_MULTI_VIDEO_AUDIO_60MB_SHARE_TARGET_PASS');
})().catch(err=>{console.error(err);process.exit(1)});
