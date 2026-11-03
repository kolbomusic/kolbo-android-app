'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('trance-studio/web/studio.html','utf8');
const java=fs.readFileSync('trance-studio/android/app/src/main/java/com/kolbomusic/trancestudio/MainActivity.java','utf8');
const a=html.indexOf('var kolboScreenWakeLock=null;');
const b=html.indexOf("window.addEventListener('beforeinstallprompt'",a);
assert.ok(a>0&&b>a,'PWA screen wake logic must be part of loaded studio script');
const script=html.slice(a,b);
assert.match(script,/navigator\.wakeLock\.request\('screen'\)/);
assert.match(script,/document\.visibilityState==='visible'/);
assert.match(script,/old\.release\(\)/);
assert.match(script,/document\.addEventListener\('visibilitychange'/);
assert.doesNotMatch(script,/\bsetInterval\(|navigator\.serviceWorker|\/api\/jobs/);
const onCreate=java.slice(java.indexOf('@Override public void onCreate('),java.indexOf('private void openStudioInBrowser()'));
assert.match(java,/import android\.view\.WindowManager;/);
assert.match(onCreate,/getWindow\(\)\.addFlags\(WindowManager\.LayoutParams\.FLAG_KEEP_SCREEN_ON\)/);
assert.doesNotMatch(onCreate,/WAKE_LOCK|PowerManager/);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function setup({native=false,supported=true,denied=false}={}){
 const events={},windowEvents={};let requests=0,releases=0,releaseEvent=null;
 const doc={visibilityState:'visible',addEventListener:(event,cb)=>{events[event]=cb}};
 const lock={addEventListener:(name,cb)=>{if(name==='release')releaseEvent=cb},
   release:async()=>{releases++;if(releaseEvent)releaseEvent()}};
 const nav=supported?{wakeLock:{request:async()=>{requests++;if(denied)throw new Error('Permission denied');return lock}}}:{};
 const context={navigator:nav,document:doc,window:{KolboAndroid:native?{}:null,addEventListener:(e,cb)=>windowEvents[e]=cb}};
 vm.runInNewContext(script,context);
 return {doc,events,windowEvents,get requests(){return requests},get releases(){return releases}};
}
(async()=>{
 const p=setup();await flush();
 assert.equal(p.requests,1,'Installed PWA must request wake lock when visible');
 p.doc.visibilityState='hidden';p.events.visibilitychange();await flush();
 assert.equal(p.releases,1,'Hidden tab must release wake lock');
 p.doc.visibilityState='visible';p.events.visibilitychange();await flush();
 assert.equal(p.requests,2,'Foreground PWA reacquires the screen lock');
 const native=setup({native:true});await flush();assert.equal(native.requests,0,'Native Android uses OS window flag instead');
 const unavailable=setup({supported:false});await flush();assert.equal(unavailable.requests,0,'Unsupported browsers must still load');
 const denied=setup({denied:true});await flush();assert.equal(denied.requests,1,'Denied wake lock cannot break application');
 console.log('KOLBO_NATIVE_FOREGROUND_SCREEN_AWAKE_AND_PWA_VISIBILITY_WAKE_LOCK_PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
