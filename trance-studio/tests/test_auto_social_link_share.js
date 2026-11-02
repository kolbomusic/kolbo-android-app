'use strict';
/* Test the actual shared-link importer handler in a VM: it must import
   from an Android/PWA share without an extra click, never start creation. */
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const html=fs.readFileSync('trance-studio/web/studio.html','utf8');
const script=html.slice(html.lastIndexOf('<script>')+8,html.lastIndexOf('</script>'));
const start=script.indexOf('window.kolboReceiveSharedLink=function(url)');
const end=script.indexOf('window.kolboImportSharedAudio=function(items)',start);
assert(start>0&&end>start);
const code=script.slice(start,end);
function makeCase(options={}){
 const elements=new Map();
 const $=(id)=>{
  if(!elements.has(id))elements.set(id,{
   value:'',checked:false,hidden:false,disabled:false,open:false,
   focus(){},scrollIntoView(){},textContent:''
  });
  return elements.get(id);
 };
 const fetches=[],imports=[],messages=[];
 let creationCalls=0;
 const mockFetch=async (url,args)=>{
  fetches.push({url,options:args});
  if(options.blocked)return {
   ok:false,json:async()=>({
    code:'extractor_parse',trace_id:'cafebeef',
    error:'Facebook לא מוסרת את המדיה'
   })
  };
  return {
   ok:true,headers:{get:()=> 'video/mp4'},
   blob:async()=>new Blob([new Uint8Array(4096)],{type:'video/mp4'})
  };
 };
 class File{
  constructor(parts,name,opts){this.name=name;this.size=parts[0].size;this.type=opts.type;}
 }
 const sandbox={
  window:{},URL,Blob,File,AbortController,Promise,fetch:mockFetch,
  sharedLinkSerial:0,linkImportController:null,socialImported:false,
  active:false,audio:{click(){}},message:s=>messages.push(s),
  $ ,setFiles:arr=>{imports.push(arr);$("generate").disabled=!arr.length;},
  run:()=>{creationCalls++;}
 };
 vm.runInNewContext(code,sandbox);
 return {sandbox,$,fetches,imports,messages,get creationCalls(){return creationCalls;}};
}
(async function(){
 const a=makeCase();
 const imported=await a.sandbox.window.kolboReceiveSharedLink('https://www.facebook.com/share/v/1Demo/');
 assert.equal(imported,true);
 assert.equal(a.fetches.length,1,'sharing must auto-call server importer');
 assert.equal(a.fetches[0].url,'/api/import-link');
 assert.equal(a.imports.at(-1).length,1);
 assert.equal(a.imports.at(-1)[0].type,'video/mp4');
 assert.equal(a.$('generate').disabled,false);
 assert.equal(a.$('linkRights').checked,false,'never forge copyright permission');
 assert.equal(a.sandbox.socialImported,true);
 assert.equal(a.creationCalls,0,'auto-import cannot start rendering');
 assert.equal(a.$('linkRecovery').hidden,true);
 const b=makeCase({blocked:true});
 const result=await b.sandbox.window.kolboReceiveSharedLink('https://www.facebook.com/share/v/1Demo/');
 assert.equal(result,false);
 assert.equal(b.fetches.length,1);
 assert.equal(b.$('linkRecovery').hidden,false,'show file-import fallback on blocked link');
 assert.match(b.$('linkStatus').textContent,/cafebeef/);
 assert.equal(b.creationCalls,0);
 const c=makeCase();
 const invalid=await c.sandbox.window.kolboReceiveSharedLink('http://localhost/video');
 assert.equal(invalid,false);
 assert.equal(c.fetches.length,0,'never import unsafe shared URLs');
 console.log('ANDROID_PWA_FIRST_SHARE_AUTOMATIC_IMPORT_WITHOUT_AUTOGENERATION_PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
