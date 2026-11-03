'use strict';
/* Android regression: incoming SEND intents must not reload the active WebView. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const java=fs.readFileSync('trance-studio/android/app/src/main/java/com/kolbomusic/trancestudio/MainActivity.java','utf8');
const html=fs.readFileSync('trance-studio/web/studio.html','utf8');
const start=java.indexOf('@Override protected void onNewIntent(Intent intent)');
const end=java.indexOf('@Override protected void onActivityResult',start);
assert.ok(start>0&&end>start,'onNewIntent handler exists');
const handler=java.slice(start,end);
assert.match(handler,/if\(pageReady\)\s*\{/,'Share on a ready page must use an in-place path');
const ready=handler.slice(handler.indexOf('if(pageReady){'),handler.indexOf('}else{'));
assert.match(ready,/webView\.evaluateJavascript/);
assert.match(ready,/kolboCanImportSharedAudio/);
assert.match(ready,/importIncoming\(\)/);
assert.doesNotMatch(ready,/beginLoad\(/,'Never reload running mix on new SEND');
assert.match(handler,/if\(!isShare\)/);
assert.match(handler,/Intent\.ACTION_SEND_MULTIPLE/);
assert.match(handler,/collectIncoming\(intent\)/);
assert.match(java,/lastImportedVersion==incomingVersion&&lastImportNavigation==navigationId/,
 'Prevent duplicate imports from onPageFinished');
assert.match(java,/incomingVersion\+\+/);
assert.match(java,/String js="\(async function\(\)/);
assert.match(java,/importFailure\(\)/,'Provide visible error when Android content URI expired');
assert.match(java,/typeof window\.kolboImportSharedAudio==='function'/);
assert.match(java,/typeof button\.onclick==='function'/,
 'Only remove native startup overlay when web UI has bound Create button');
assert.match(java,/private void pollStudioReady\(/,
 'Avoid a one-shot WebView DOM-ready race during startup');
assert.match(java,/mainHandler\.postDelayed\(\(\)->pollStudioReady\(token,attempt\+1\),700\)/);
assert.match(java,/Button browserOffline=new Button\(this\)/,
 'Provide a fallback if Android WebView cannot load the cloud studio');
assert.match(java,/webView\.clearCache\(true\)/,
 'Recover from stale cached startup content');
assert.match(html,/window\.kolboCanImportSharedAudio=function\(\)\{return !active;\}/);
assert.match(html,/window\.kolboImportSharedAudio=function\(items\)/);
assert.match(html,/\$\('generate'\)\.onclick=run/);
const receiver=java.slice(java.indexOf('private void importIncoming()'),java.indexOf('@Override protected void onNewIntent'));
assert.doesNotMatch(receiver,/(?:\.click\(|\bstartActivity\(|\brun\(\))/,'Imported voice must never auto-create');
console.log('ANDROID_RESHARE_PRESERVES_CURRENT_MIX_AND_DEFERS_CREATE_PASS');
