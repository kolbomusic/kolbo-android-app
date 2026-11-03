'use strict';
/* Browser-tab recovery for a Render Free transient worker.
 * No original WhatsApp audio, video, transcript, auth secret or AI prompt
 * is persisted here. Only a short-lived opaque job ID is kept.
 * Read-only GET checks; NEVER POST/replay media on restart or page load.
 */
(function(){
  const KEY='kolbo_trance_pending_job_v1';
  const VALID=/^[a-f0-9]{48}$/;
  const TTL=55*60*1000;
  let timer=null, checks=0, working=false;
  const panel=document.getElementById('recoveryPanel');
  const label=document.getElementById('recoveryMessage');
  const links=document.getElementById('recoveryLinks');
  const button=document.getElementById('recoveryCheck');
  if(!panel||!label||!links||!button)return;
  function clear(){
    try{sessionStorage.removeItem(KEY)}catch(e){}
  }
  function getPrevious(){
    try{
      const item=JSON.parse(sessionStorage.getItem(KEY)||'null');
      if(!item||!VALID.test(String(item.id||''))||
          typeof item.at!=='number'||item.at>Date.now()||
          Date.now()-item.at>TTL){clear();return null}
      return item;
    }catch(e){return null}
  }
  function storeJob(data){
    if(!data||!VALID.test(String(data.id||'')))return false;
    try{
      sessionStorage.setItem(KEY,JSON.stringify({id:data.id,at:Date.now()}));
      return true;
    }catch(e){return false}
  }
  function stopTimer(){if(timer!==null){clearTimeout(timer);timer=null}}
  function addDownload(name,url,id){
    if(typeof url!=='string'||!new RegExp('^/api/jobs/'+id+'/(audio|voice|video)$').test(url))return;
    const item=document.createElement('a');
    item.href=url;item.textContent=name;item.className='secondary';
    item.style.cssText='color:#f7e4ff;padding:10px;text-align:center';
    links.appendChild(item);
  }
  async function check(){
    if(working||document.hidden)return;
    const previous=getPrevious();
    if(!previous){panel.hidden=true;return}
    working=true;panel.hidden=false;links.replaceChildren();
    label.textContent='בודק את המשימה הקודמת — ללא העלאת ההקלטה מחדש...';
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),12000);
    try{
      const response=await fetch('/api/jobs/'+previous.id,{
        method:'GET',credentials:'same-origin',cache:'no-store',
        headers:{Accept:'application/json'},signal:controller.signal
      });
      if(response.status===404){
        clear();stopTimer();
        label.textContent='שרת העיבוד נסגר או שתוקף הקובץ פג. המשימה אינה שמורה עוד בשרת הזמני, ולא בוצעה העלאה נוספת.';
        return;
      }
      const type=String(response.headers.get('content-type')||'');
      if(!response.ok||!type.includes('application/json'))throw new Error('temporarily offline');
      const job=await response.json();
      if(job.state==='error'){
        clear();stopTimer();
        label.textContent='המשימה הקודמת נכשלה. הקלטה חדשה לא נשלחה אוטומטית.';
        return;
      }
      if(job.state==='done'){
        stopTimer();
        label.textContent='ההפקה הקודמת נמצאה בשרת. ניתן לפתוח את קישורי התוצאות בלי ליצור מחדש:';
        addDownload('הורדת MP3',job.download_url,previous.id);
        addDownload('קול עם אפקטים',job.voice_url,previous.id);
        addDownload('הורדת MP4',job.video_url,previous.id);
        return;
      }
      label.textContent='המשימה הקודמת עדיין קיימת: '+
        (typeof job.label==='string'?job.label:'ממתינה לעיבוד')+
        '. אין צורך לשלוח מחדש את הקובץ.';
      if(checks<60&&document.visibilityState==='visible'){
        checks++;timer=setTimeout(()=>{timer=null;check()},5000);
      }
    }catch(e){
      label.textContent='החיבור לשרת מתחדש. אפשר לבדוק שוב ללא העלאה מחדש.';
    }finally{clearTimeout(timeout);working=false}
  }
  window.KolboJobRecovery={storeJob,check};
  button.addEventListener('click',()=>{checks=0;stopTimer();check()});
  document.addEventListener('visibilitychange',()=>{
    if(document.hidden)stopTimer();else check();
  });
  setTimeout(check,300);
})();
