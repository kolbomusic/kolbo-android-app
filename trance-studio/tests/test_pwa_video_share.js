'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const manifest=JSON.parse(fs.readFileSync('trance-studio/web/studio.webmanifest','utf8'));
const accept=manifest.share_target.params.files[0].accept;
assert.ok(accept.includes('video/*'));
assert.ok(accept.includes('audio/*'));
const sw=fs.readFileSync('trance-studio/web/studio-sw.js','utf8');
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
 console.log('PWA_WHATSAPP_VIDEO_45MB_SHARE_TARGET_PASS');
})().catch(err=>{console.error(err);process.exit(1)});
