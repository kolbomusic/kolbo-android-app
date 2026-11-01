/* Behavioral regression: WhatsApp share must NEVER submit or auto-run.
   Only a real click on #generate may start the expensive original audio job.
*/
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const src=fs.readFileSync('trance-studio/web/studio.html','utf8');
const bridge=fs.readFileSync('trance-studio/android/app/src/main/java/com/kolbomusic/trancestudio/MainActivity.java','utf8');
assert.match(src,/window\.kolboImportSharedAudio\s*=\s*function\(items\)/);
assert.match(src,/\$\('generate'\)\.onclick\s*=\s*run;/);
assert.match(src,/<button[^>]+id="generate"[^>]+disabled/);
assert.match(src,/<button[^>]+id="retryVideo"[^>]+hidden/);
assert.match(src,/retry\.onclick\s*=\s*async function\(\)/);
assert.doesNotMatch(src,/if\(!active&&files\.length\)\s*setTimeout/);
assert.match(bridge,/window\.kolboImportSharedAudio\)window\.kolboImportSharedAudio\(clips\)/);
const manifest=fs.readFileSync('trance-studio/android/app/src/main/AndroidManifest.xml','utf8');
assert.match(manifest,/android\.intent\.action\.SEND/);
assert.match(manifest,/android\.intent\.action\.SEND_MULTIPLE/);
assert.equal((manifest.match(/android:mimeType="video\/\*"/g)||[]).length,2,
             'Both SEND and SEND_MULTIPLE must register WhatsApp videos');
assert.match(bridge,/MAX_VIDEO_BYTES=45L\*1024L\*1024L/);
assert.match(bridge,/WhatsApp-Video-/);
assert.match(bridge,/isVideoUri\(uri\)/);
assert.match(src,/accept="[^"]*video\/\*/);
assert.match(src,/45MB לסרטון/);
const from=src.indexOf('function setFiles(items){');
const end=src.indexOf("audio.addEventListener('change'",from);
assert.ok(from>0&&end>from,'share handler code found');
const handler=src.slice(from,end);
assert.doesNotMatch(handler,/\brun\s*\(/,'Share import may never start creation');
assert.doesNotMatch(handler,/\bsetTimeout\s*\(/,'Share import may never schedule creation');
let count=0, notified=[],stage=[],scheduled=0,focus=0;
let button={disabled:true,focus(){focus++}};
let files=[];
const context={
    files,active:false,window:{},
    Array, console,
    '$':id=>{assert.equal(id,'generate');return button;},
    message:value=>notified.push(value),
    markStage:value=>stage.push(value),
    syncFiles(){},
    run(){count++},
    setTimeout(){scheduled++}
};
vm.runInNewContext(handler,context);
const voice={name:'WhatsApp-PTT.opus',size:12044};
context.window.kolboImportSharedAudio([voice]);
assert.equal(context.files.length,1);
assert.equal(context.files[0].name,voice.name);
assert.equal(button.disabled,false,'Create button must be enabled only after import');
assert.equal(count,0,'No automatic generation on WhatsApp share');
const sharedVideo={name:'VID-20261101-WA0037.mp4',type:'video/mp4',size:6*1048576};
context.window.kolboImportSharedAudio([sharedVideo]);
assert.equal(context.files.length,1);
assert.equal(context.files[0].name,sharedVideo.name,
             'Original MP4 video must stay staged without conversion to audio');
assert.equal(count,0,'WhatsApp video sharing must not trigger rendering');
assert.equal(scheduled,0,'WhatsApp video sharing must not schedule rendering');
assert.equal(scheduled,0,'No delayed generation on WhatsApp share');
assert.equal(focus,2,'Each intentional WhatsApp share focuses Create without starting it');
assert.ok(notified.at(-1).includes('לחץ'));
context.window.kolboImportSharedAudio([]);
assert.equal(button.disabled,true);
assert.equal(count,0);
context.window.kolboImportSharedAudio([voice]);
context.active=true;
context.window.kolboImportSharedAudio([{name:'new.opus'}]);
assert.equal(context.files.length,1);
assert.equal(context.files[0].name,voice.name,'An active job must not silently overwrite inputs');
assert.equal(count,0);
console.log('MANUAL_WHATSAPP_SHARE_ONLY_WAITS_FOR_EXPLICIT_CREATE_BUTTON_PASS');
