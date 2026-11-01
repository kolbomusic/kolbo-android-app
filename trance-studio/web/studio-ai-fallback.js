/* Kolbo Trance Story: optional phone-network free AI video recovery.

   This file runs only after the user opted in to send recognized TEXT to a
   public model; it never gives the model original WhatsApp audio, passwords,
   payment information or a private API token. Both origins and MP4 URLs are
   exact HTTPS allow-listed. Any failure keeps the completed original MP3.
*/
(function(){
'use strict';
var MODELS=[
  {id:'ltx-distilled',host:'lightricks-ltx-video-distilled.hf.space',
   call:'/gradio_api/call/text_to_video'},
  {id:'ltx25',host:'lightricks-ltx-2-5.hf.space',
   call:'/gradio_api/call/v2/run',result:'/gradio_api/call/run/'}
];
var MAX_VIDEO_BYTES=10*1024*1024;
var MAX_SHOTS=2;
var HEBREW=/[\u0590-\u05ff]/;

function fail(msg){return new Error(msg)}
function safeUrl(raw,host){
  var u;
  try{u=new URL(String(raw))}catch(e){throw fail('השירות החיצוני החזיר כתובת סרטון לא תקינה')}
  if(u.protocol!=='https:'||u.hostname!==host||u.username||u.password||u.port||
     !u.pathname.startsWith('/gradio_api/file='))
      throw fail('כתובת הווידאו אינה מאחד ממנועי היצירה המאושרים');
  return u.href;
}
function withTimeout(ms,run){
  var controller=new AbortController();
  var timer=setTimeout(function(){controller.abort()},ms);
  return Promise.resolve().then(function(){return run(controller.signal)})
     .finally(function(){clearTimeout(timer)});
}
async function getResponse(url,options,ms){
  var response=await withTimeout(ms,function(signal){
    return fetch(url,Object.assign({mode:'cors',credentials:'omit',signal:signal},options||{}));
  });
  if(!response.ok)throw fail('השירות החינמי עמוס או החזיר שגיאה ('+response.status+')');
  return response;
}
function parseEventStream(text,host){
  var blocks=String(text||'').split(/\r?\n\r?\n/).filter(Boolean);
  for(var i=blocks.length-1;i>=0;i--){
    var e=blocks[i].match(/(?:^|\n)event:\s*([^\r\n]+)/);
    var d=blocks[i].match(/(?:^|\n)data:\s*([^\r\n]+)/);
    if(!e||!d)continue;
    var type=e[1].trim();
    if(type==='error')throw fail('מנוע ה־AI החינמי אינו יכול לבצע כעת את הבקשה');
    if(type!=='complete')continue;
    var data;
    try{data=JSON.parse(d[1])}catch(ex){throw fail('השרת החזיר תשובת וידאו פגומה')}
    var result=Array.isArray(data)?data[0]:null;
    if(result&&result.video)result=result.video;
    if(!result||typeof result.url!=='string')throw fail('לא הוחזר קליפ וידאו');
    return safeUrl(result.url,host);
  }
  throw fail('יצירת הווידאו לא הסתיימה בתור החינמי');
}
function requestPayload(model,prompt){
  if(model.id==='ltx25'){
    return {prompt:prompt,image_path:null,height:512,width:768,
            duration_s:1.0,seed:42,decoder:'conv',auto_len:false,
            randomize_seed:false,do_enhance:false};
  }
  return {data:[prompt,
    'blurry, deformed, text, watermark, anime, cartoon, illustration',
    '','',704,512,'text-to-video',1.0,9,42,true,1.0,true]};
}
async function oneClip(model,prompt,onStage){
  var base='https://'+model.host;
  onStage('פונה למנוע '+model.id+' ליצירת סצנה חדשה לפי הדיבור...');
  var submit=await getResponse(base+model.call,{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(requestPayload(model,prompt))
    },30000);
  var event=await submit.json();
  if(!event||! /^[a-f0-9]{24,80}$/.test(String(event.event_id||'')))
    throw fail('מנוע ה־AI לא החזיר מספר משימה');
  var url=base+(model.result||model.call+'/')+event.event_id;
  var response=await getResponse(url,{headers:{Accept:'text/event-stream'}},105000);
  var text=await withTimeout(105000,function(signal){
    // Reading an already-open streaming response is independent from fetch's
    // timeout, but this fallback still works on Android WebViews without
    // AbortSignal.timeout.
    return response.text();
  });
  var videoUrl=parseEventStream(text,model.host);
  onStage('הקליפ נוצר. מעביר את קטע הווידאו לשרת המיקס...');
  var download=await getResponse(videoUrl,{},45000);
  var blob=await download.blob();
  if(blob.size<12000||blob.size>MAX_VIDEO_BYTES)
    throw fail('הסרטון שהמנוע החזיר ריק או גדול מדי');
  var magic=new Uint8Array(await blob.slice(0,12).arrayBuffer());
  if(magic.length<8||String.fromCharCode(magic[4],magic[5],magic[6],magic[7])!=='ftyp')
    throw fail('המנוע החזיר קובץ שאינו סרטון MP4');
  return blob;
}
async function getPlan(id){
  var response=await fetch('/api/jobs/'+encodeURIComponent(id)+'/ai-plan',
    {credentials:'same-origin',cache:'no-store'});
  var data=await response.json();
  if(!response.ok)throw fail(data.error||'לא ניתן לבנות סיפור מתוך ההקלטה המקורית');
  if(!data||!Array.isArray(data.prompts)||!data.prompts.length)
    throw fail('אין תמלול מספיק ברור להפקת סצנה');
  return data.prompts.slice(0,MAX_SHOTS).filter(function(p){
    return typeof p==='string'&&p.length>20&&p.length<2000&&HEBREW.test(p);
  });
}
async function generate(jobId,onStage){
  if(!document.getElementById('ai_video_consent').checked)
    throw fail('נדרשת הסכמה לשימוש במנוע AI חיצוני');
  if(!/^[a-f0-9]{48}$/.test(String(jobId||'')))
    throw fail('לא נמצא מזהה המיקס');
  var prompts=await getPlan(jobId);
  var blobs=[];
  for(var i=0;i<prompts.length;i++){
    var clip=null;
    for(var p=0;p<MODELS.length;p++){
      try{
        onStage('יוצר סצנה '+(i+1)+' מתוך '+prompts.length+' — '+MODELS[p].id);
        clip=await oneClip(MODELS[p],prompts[i],onStage);
        break;
      }catch(error){
        // A free community model may be paused/limited. Try the other model.
        // Never log or display the original transcript in error messages.
        onStage('המנוע הראשון לא השלים סצנה; מנסה מנוע חינמי חלופי...');
      }
    }
    if(!clip)break;
    blobs.push(clip);
  }
  if(!blobs.length)throw fail('שני מנועי הווידאו החינמיים אינם זמינים כרגע');
  onStage('מחבר את סצנות ה־AI לקול ולמיקס המקורי...');
  var form=new FormData();
  blobs.forEach(function(blob,i){
    form.append('clip',blob,'kolbo-ai-scene-'+i+'.mp4');
  });
  var resp=await fetch('/api/jobs/'+encodeURIComponent(jobId)+'/ai-clips',
                       {method:'POST',credentials:'same-origin',body:form});
  var answer=await resp.json();
  if(!resp.ok||!answer.video_url)
    throw fail(answer.error||'לא ניתן לשלב את סצנות הווידאו');
  return answer;
}
window.KolboAIFallback={generate:generate,
  version:'1.14.0',isDirectBrowserMode:true};
})();
