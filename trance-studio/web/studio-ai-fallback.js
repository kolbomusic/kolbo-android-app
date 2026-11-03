/* Kolbo Trance Story: optional phone-network free AI video recovery.

   This file runs only after the user opted in to send recognized TEXT to a
   public model; it never gives the model original WhatsApp audio, passwords,
   payment information or a private API token. Both origins and MP4 URLs are
   exact HTTPS allow-listed. Any failure keeps the completed original MP3.
*/
(function(){
'use strict';
var MODELS=[
  {id:'ltx25',host:'lightricks-ltx-2-5.hf.space',
   call:'/gradio_api/call/v2/run',result:'/gradio_api/call/run/'},
  {id:'ltx-distilled',host:'lightricks-ltx-video-distilled.hf.space',
   call:'/gradio_api/call/text_to_video'}
];
var MAX_VIDEO_BYTES=10*1024*1024;
var MAX_SHOTS=24;
var MAX_TOTAL_VIDEO_BYTES=58*1024*1024;
var MIN_SCENE_SECONDS=3.0;
var HEBREW=/[\u0590-\u05ff]/;

function fail(msg){return new Error(msg)}
function safeProviderFailure(detail){
  // Never forward Gradio's original error body: it might echo user text.
  var raw=String(detail||'').toLowerCase();
  var error;
  if(/quota|gpu limit|gpu time|rate.limit|usage limit|too many requests|zerogpu|credits/.test(raw)){
    error=fail('מכסת GPU חינמית מוצתה או הוגבלה. אפשר לנסות יצירת וידאו בלבד לאחר חידוש המכסה.');
    error.providerQuota=true;
  }else if(/busy|overload|capacity|temporarily unavailable|allocation|no gpu|queue full/.test(raw)){
    error=fail('שרת הווידאו עמוס ולא הקצה GPU כעת.');
    error.providerTransient=true;
  }else{
    error=fail('מנוע הווידאו לא הצליח להפיק קליפ מהבקשה.');
  }
  return error;
}
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
  if(!response.ok){
    var error;
    if(response.status===429){
      error=fail('שירות הווידאו הגביל את מכסת הבקשות (429).');
      error.providerQuota=true;
    }else if([502,503,504].includes(response.status)){
      error=fail('שרת הווידאו עמוס או אינו זמין זמנית ('+response.status+').');
      error.providerTransient=true;
    }else if(response.status===401||response.status===403){
      error=fail('מנוע הווידאו דורש הרשאה שאינה זמינה במצב החינמי.');
    }else{
      error=fail('שירות הווידאו החזיר שגיאה ('+response.status+').');
    }
    throw error;
  }
  return response;
}
async function readTextWithDeadline(url,ms){
  var controller=new AbortController();
  var timer=setTimeout(function(){controller.abort()},ms);
  try{
    var response=await fetch(url,{
      mode:'cors',credentials:'omit',headers:{Accept:'text/event-stream'},
      signal:controller.signal});
    if(!response.ok){
      // Preserve safe quota/overload diagnostics across Gradio requests.
      // Never expose private prompts or the provider's raw response body.
      if(response.status===429){var quota=fail('מכסת GPU/בקשות חינמית הסתיימה (429).');quota.providerQuota=true;throw quota}
      if([502,503,504].includes(response.status)){
        var busy=fail('תור יצירת הווידאו עמוס כרגע.');busy.providerTransient=true;throw busy;
      }
      if(response.status===401||response.status===403)throw fail('ספק הווידאו אינו מאפשר יצירה אנונימית.');
      throw fail('שירות יצירת הווידאו החזיר שגיאה ('+response.status+')');
    }
    return await response.text();
  }finally{clearTimeout(timer)}
}
async function readBlobWithDeadline(url,ms){
  var controller=new AbortController();
  var timer=setTimeout(function(){controller.abort()},ms);
  try{
    var response=await fetch(url,{mode:'cors',credentials:'omit',signal:controller.signal});
    if(!response.ok)throw fail('לא ניתן להוריד את הווידאו שנוצר ('+response.status+')');
    var contentLength=Number(response.headers.get('content-length')||0);
    if(contentLength>MAX_VIDEO_BYTES)throw fail('קובץ הווידאו גדול מדי');
    var blob=await response.blob();
    if(blob.size>MAX_VIDEO_BYTES)throw fail('קובץ הווידאו גדול מדי');
    return blob;
  }finally{clearTimeout(timer)}
}
function parseEventStream(text,host){
  var blocks=String(text||'').split(/\r?\n\r?\n/).filter(Boolean);
  for(var i=blocks.length-1;i>=0;i--){
    var e=blocks[i].match(/(?:^|\n)event:\s*([^\r\n]+)/);
    var d=blocks[i].match(/(?:^|\n)data:\s*([^\r\n]+)/);
    if(!e||!d)continue;
    var type=e[1].trim();
    if(type==='error'){
      var detail='';
      try{
        var payload=JSON.parse(d[1]);
        detail=(payload&&typeof payload==='object')?
          String(payload.error||payload.message||payload.detail||''):String(payload);
      }catch(ex){detail=d[1]}
      throw safeProviderFailure(detail);
    }
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
function requestPayload(model,prompt,shotIndex){
  var seed=42+(shotIndex||0)*7919;
  if(model.id==='ltx25'){
    return {prompt:prompt,image_path:null,height:512,width:768,
            duration_s:5.0,seed:seed,decoder:'conv',auto_len:false,
            randomize_seed:false,do_enhance:false};
  }
  return {data:[prompt,
    'blurry, deformed, text, watermark, anime, cartoon, illustration',
    null,null,512,704,'text-to-video',5.0,9,seed,false,1.0,true]};
}
async function oneClip(model,prompt,onStage,shotIndex){
  var base='https://'+model.host;
  onStage('פונה למנוע '+model.id+' ליצירת סצנה חדשה לפי הדיבור...');
  var submit=await getResponse(base+model.call,{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(requestPayload(model,prompt,shotIndex))
    },30000);
  var event=await submit.json();
  if(!event||! /^[a-f0-9]{24,80}$/.test(String(event.event_id||'')))
    throw fail('מנוע ה־AI לא החזיר מספר משימה');
  var url=base+(model.result||model.call+'/')+event.event_id;
  var text=await readTextWithDeadline(url,105000);
  var videoUrl=parseEventStream(text,model.host);
  onStage('הקליפ נוצר. מעביר את קטע הווידאו לשרת המיקס...');
  var blob=await readBlobWithDeadline(videoUrl,45000);
  if(blob.size<2048||blob.size>MAX_VIDEO_BYTES)
    throw fail('הסרטון שהמנוע החזיר ריק או גדול מדי');
  var magic=new Uint8Array(await blob.slice(0,12).arrayBuffer());
  if(magic.length<8||String.fromCharCode(magic[4],magic[5],magic[6],magic[7])!=='ftyp')
    throw fail('המנוע החזיר קובץ שאינו סרטון MP4');
  return blob;
}
function splitPromptIntoBeats(fullPrompt){
  var all=String(fullPrompt||'').trim();
  var marker='The narration is in HEBREW. Interpret its meaning and depict it: ';
  var i=all.lastIndexOf(marker);
  if(i<0)return all?[all]:[];
  var prefix=all.slice(0,i+marker.length);
  var words=all.slice(i+marker.length).split(/[.!?;,]+\\s*/).map(function(x){return x.trim()}).filter(function(x){
    return (x.match(/[\\u0590-\\u05ff]/g)||[]).length>=3
  });
  if(words.length<2)return [all];
  // Preserve chronological clauses. Never divide an actor/action sentence
  // in half or replace it with unrelated footage. The server normally supplies
  // its more precise narrative-beat prompts; this is a legacy safeguard.
  var count=Math.min(MAX_SHOTS,words.length),shots=[];
  for(var j=0;j<count;j++){
    var from=Math.floor(j*words.length/count);
    var to=Math.floor((j+1)*words.length/count);
    shots.push(prefix+words.slice(from,to).join('. '));
  }
  return shots.filter(Boolean);
}
async function getPlan(id,passedPrompt,passedScenes){
  // The server extracted physically specific events (actors, action and
  // objects) from the original Hebrew. Prefer those ordered grounded scenes.
  if(Array.isArray(passedScenes)&&passedScenes.length){
    var grounded=passedScenes.slice(0,MAX_SHOTS).filter(function(p){
      return typeof p==='string'&&p.length>20&&p.length<2000&&HEBREW.test(p);
    });
    if(grounded.length)return grounded;
  }
  // A full cinematic prompt is NOT a scene plan. Splitting it locally
  // can make one 5-second clip for a six-shot soundtrack, later rejected by
  // the server's anti-loop safeguard. Recover the exact approved server plan.
  var response=await fetch('/api/jobs/'+encodeURIComponent(id)+'/ai-plan',
    {credentials:'same-origin',cache:'no-store'});
  var data=await response.json();
  if(!response.ok)throw fail(data.error||'לא ניתן לשחזר סצנות מההקלטה המקורית');
  if(!data||!Array.isArray(data.prompts)||!data.prompts.length)
    throw fail('אין תוכנית סצנות זמינה למשימה המקורית');
  var grounded=data.prompts.slice(0,MAX_SHOTS).filter(function(p){
    return typeof p==='string'&&p.length>20&&p.length<2000&&HEBREW.test(p);
  });
  if(grounded.length!==data.prompts.length||
     grounded.length!==Number(data.scene_count||0))
    throw fail('תוכנית הסצנות אינה שלמה; אין לייצר קליפ חוזר או חלקי');
  return grounded;
}
async function generate(jobId,onStage,passedPrompt,passedScenes){
  if(!document.getElementById('ai_video_consent').checked)
    throw fail('נדרשת הסכמה לשימוש במנוע AI חיצוני');
  if(!/^[a-f0-9]{48}$/.test(String(jobId||'')))
    throw fail('לא נמצא מזהה המיקס');
  var prompts=await getPlan(jobId,passedPrompt,passedScenes);
  if(!prompts.length)throw fail('אין מספיק מידע מתוך ההקלטה להכנת סצנות וידאו.');
  var blobs=[];
  for(var i=0;i<prompts.length;i++){
    var clip=null, failures=[];
    for(var p=0;p<MODELS.length;p++){
      try{
        onStage('יוצר סצנה '+(i+1)+' מתוך '+prompts.length+' — '+MODELS[p].id);
        clip=await oneClip(MODELS[p],prompts[i],onStage,i);
        break;
      }catch(error){
        // Never retry quota exhaustion: retries burn the shared quota.
        // Retry once, briefly, only when the server itself is temporarily busy.
        if(error&&error.providerTransient){
          onStage('השרת החינמי עמוס. ממתין רגע ומנסה פעם נוספת...');
          await new Promise(function(resolve){setTimeout(resolve,5000)});
          try{
            clip=await oneClip(MODELS[p],prompts[i],onStage,i);
            break;
          }catch(retryError){error=retryError}
        }
        failures.push(error);
        onStage('הסצנה לא הושלמה במנוע '+MODELS[p].id+'; בודק מנוע חלופי...');
      }
    }
    if(!clip){
      var isQuota=failures.some(function(e){return !!(e&&e.providerQuota)});
      var blocked=failures.length>0&&failures.every(function(e){
        return /הרשאה|אנונימית|דורש/.test(String(e&&e.message||''));
      });
      var transient=failures.some(function(e){return !!(e&&e.providerTransient)});
      var reason=isQuota?'שירות הווידאו החינמי הגביל את מכסת GPU/הבקשות.':
         blocked?'ספקי הווידאו אינם מאפשרים כרגע יצירה ללא הרשאה.':
         transient?'שירותי הווידאו החינמיים עמוסים כרגע.':
         'מנועי הווידאו החינמיים לא הצליחו ליצור תנועה תקינה.';
      throw fail('סצנת AI מספר '+(i+1)+' לא נוצרה. '+reason+
        ' המיקס המקורי נשמר. אפשר לנסות וידאו בלבד מאוחר יותר.');
    }
    if(blobs.reduce(function(n,b){return n+b.size},0)+clip.size>MAX_TOTAL_VIDEO_BYTES)
      throw fail('קובצי סצנות ה־AI גדולים מדי להעלאה חינמית. המיקס נשמר.');
    blobs.push(clip);
  }
  if(!blobs.length)throw fail('לא נוצרו סצנות וידאו. המיקס המקורי נשמר.');
  onStage('מחבר את סצנות ה־AI לקול ולמיקס המקורי...');
  var form=new FormData();
  blobs.forEach(function(blob,i){
    form.append('clip',blob,'kolbo-ai-scene-'+i+'.mp4');
  });
  var resp,answer;
  for(var attempt=0;attempt<3;attempt++){
    resp=await fetch('/api/jobs/'+encodeURIComponent(jobId)+'/ai-clips',
      {method:'POST',credentials:'same-origin',body:form});
    answer=await resp.json().catch(function(){return {error:'תגובת שרת לא תקינה'}});
    if(resp.status!==429||attempt===2)break;
    // Preserve the already-generated original AI bytes in FormData.
    // Never call ZeroGPU again just because the Render mux is busy.
    onStage('קטעי ה־AI כבר נוצרו. השרת עסוק; שומר אותם ומנסה שוב לשלב במיקס...');
    var seconds=Number(resp.headers.get('Retry-After')||6);
    await new Promise(function(resolve){setTimeout(resolve,
      Math.min(12000,Math.max(3000,seconds*1000)))});
  }
  if(!resp.ok||!answer.video_url)
    throw fail(answer.error||'לא ניתן לשלב את סצנות הווידאו');
  return answer;
}
window.KolboAIFallback={generate:generate,
  version:'1.18.1',isDirectBrowserMode:true};
})();
