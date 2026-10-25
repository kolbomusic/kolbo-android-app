(function(){
'use strict';
const $=id=>document.getElementById(id);
const root=document.querySelector('main');
if(!root || !$('dailyOwnerPanel') || !$('summary') || !$('users') || !$('output'))return;
const sections=[...root.querySelectorAll(':scope > section.panel')];
const usersPanel=sections.find(el=>el.querySelector('#users'));
const issuePanel=sections.find(el=>el.querySelector('#issue'));
const newsPanel=sections.find(el=>el.querySelector('#news'));
const privacyPanel=sections.find(el=>el.querySelector('#backup'));
const daily=$('dailyOwnerPanel'), summary=$('summary');
const oldNotice=root.querySelector(':scope > .notice');
const css=document.createElement('style');
css.textContent=[
':root{--owner-gold:#f2c876}',
'body{background:radial-gradient(ellipse at 50% -20%,#1a3358,#0b1120 60%)}',
'header{background:linear-gradient(128deg,#182a4a,#102137);padding:24px 17px 19px}header h1{font-size:26px}',
'main{max-width:900px;padding:14px 14px 70px}.panel{border-color:#405372;box-shadow:0 10px 25px #0003}',
'.owner-tabs{display:flex;gap:6px;overflow-x:auto;position:sticky;top:0;z-index:10;background:#101c31f5;backdrop-filter:blur(12px);padding:10px 3px 11px;margin:0 0 12px;border-bottom:1px solid #334965}',
'.owner-tabs button{flex:0 0 auto;background:#1d2d49;color:#c6d3e6;padding:10px 13px;border:1px solid #355073;border-radius:11px;min-height:44px;font-size:13px}',
'.owner-tabs button[aria-selected=true]{background:#edbe6d;color:#191e2c;border-color:#f1cf91}',
'.owner-screen{display:none}.owner-screen.active{display:block}',
'.owner-hint{font-size:12px;line-height:1.7;color:#c3cfe1;padding:10px 12px;background:#1c2c48;border-radius:10px}',
'.owner-keyline{border-right:3px solid #f2c876;padding-right:10px}',
'.owner-pill{background:#2a3e59;color:#f3dba5;border-radius:18px;font-size:11px;padding:5px 11px}',
'.owner-shortcuts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:12px 0}',
'.owner-shortcuts button{background:#2a3553;color:#f5f7fc;border:1px solid #536582;min-height:58px}',
'.owner-status{border-radius:12px;border:1px solid #3e5776;padding:13px;background:#152842;margin-bottom:10px;color:#d9e3f4;font-size:12px;line-height:1.8}',
'.owner-settings-help{font-size:12px;color:#b2c3d9;line-height:1.9}',
'#dailyOwnerPanel{border-top:3px solid #edbe6d}#dailyOwnerCopy{min-height:175px;line-height:1.8}',
'@media(max-width:520px){.owner-shortcuts{grid-template-columns:1fr 1fr}.owner-tabs button{font-size:12px;padding:9px 12px}header h1{font-size:23px}}'
].join('\n');document.head.append(css);
const tabbar=document.createElement('nav');tabbar.className='owner-tabs';tabbar.setAttribute('aria-label','ניווט אפליקציית הבעלים');
const mount=document.createElement('div');mount.id='ownerViews';root.prepend(mount);root.prepend(tabbar);
function screen(id,title,nodes){
 const btn=document.createElement('button');btn.type='button';btn.textContent=title;btn.dataset.ownerTab=id;btn.setAttribute('aria-selected','false');tabbar.append(btn);
 const view=document.createElement('div');view.className='owner-screen';view.id='ownerScreen-'+id;mount.append(view);
 for(const node of nodes)if(node)view.append(node);
 btn.onclick=()=>open(id);
 return view;
}
const main=screen('home','⌂ ראשי',[summary,daily]);
const users=screen('members','♙ מנויים',[usersPanel]);
const issue=screen('send','➤ הפצה',[issuePanel]);
const news=screen('messages','▤ הודעות',[newsPanel]);
const settings=screen('settings','⚙ הגדרות',[privacyPanel]);
if(oldNotice)oldNotice.remove();
const intro=document.createElement('div');intro.className='owner-status';intro.innerHTML='<strong class="owner-keyline">מרכז השליטה שלך</strong><div>כל ההמלצות והמידע הסטטיסטי במקום אחד, רק במכשיר הבעלים. אתה בוחר מה ומתי לשתף עם לקוחות.</div>';
main.prepend(intro);
const actions=document.createElement('div');actions.className='owner-shortcuts';
actions.innerHTML='<button id="ownerOpenShare" type="button">שליחת סקירת היום</button><button id="ownerOpenIssue" type="button">המלצה ללקוח</button><button id="ownerOpenMembers" type="button">ניהול מנויים</button>';
main.insertBefore(actions,daily);
const description=document.createElement('p');description.className='owner-hint';
description.textContent='הדירוג היומי הוא תיאור שכיחות בעבר, לא המלצה המבטיחה זכייה. לקוחות אינם מחוברים לממשק הזה ואין להם גישה לניהול.';
main.insertBefore(description,daily);
const latest=document.createElement('p');latest.id='ownerTodayDate';latest.className='owner-pill';main.insertBefore(latest,daily);
const refresh=document.createElement('button');refresh.type='button';refresh.id='ownerRefreshButton';refresh.className='secondary';refresh.textContent='⟳ בדוק עדכון עכשיו';refresh.style.margin='8px 0';daily.append(refresh);
const feedback=document.createElement('p');feedback.className='owner-hint';feedback.id='ownerRefreshMessage';daily.append(feedback);
const memberText=document.createElement('p');memberText.className='owner-hint';memberText.textContent='רשימת המנויים היא רישום מקומי לניסוי בלבד. תשלומים אינם נגבים מתוך האפליקציה ואין בקרה מרכזית על מנויים.';users.prepend(memberText);
const shareText=document.createElement('p');shareText.className='owner-hint';shareText.textContent='השיתוף נעשה ביוזמתך דרך חלונית השיתוף של Android. פעולה זו אינה מאשרת שהודעה הגיעה ללקוח, אינה חושפת הודעות פרטיות, ואינה מאפשרת שליחה אוטומטית לא מורשית בוואטסאפ.';issue.prepend(shareText);
const newsText=document.createElement('p');newsText.className='owner-hint';newsText.textContent='טיוטת ההודעה נשמרת במכשיר הבעלים בלבד. כדי לפרסם אותה יש להעתיק ולשתף באופן יזום. אין כרגע שליחה אוטומטית למנויים.';news.prepend(newsText);
const shareNews=document.createElement('button');shareNews.type='button';shareNews.textContent='שתף את טיוטת ההודעה';shareNews.className='secondary';shareNews.style.margin='0 0 16px';news.append(shareNews);
shareNews.onclick=()=>{const text=$('news').value.trim();if(!text)return alert('יש לכתוב הודעה קודם');if(window.KolboOwnerBridge?.share)window.KolboOwnerBridge.share(text);else if(navigator.share)navigator.share({text});};
const controls=document.createElement('section');controls.className='panel';
controls.innerHTML='<h2>פרטי הקשר והעדכונים שלך</h2><p class="owner-settings-help">הפרטים האלה נשמרים רק במכשיר. המייל היומי הוגדר דרך משימת ChatGPT נפרדת; שינוי הכתובת כאן לא משנה אוטומטית את המשימה. לא נשלחים SMS או WhatsApp למספר מתוך האפליקציה.</p><label for="ownerPhone">טלפון להתקשרות</label><input id="ownerPhone" type="tel" autocomplete="off" inputmode="tel" placeholder="מספר הטלפון שלך"><label for="ownerEmail">כתובת האימייל לדוחות</label><input id="ownerEmail" type="email" autocomplete="off" inputmode="email" placeholder="כתובת לקבלת הדוחות"><button id="ownerSaveContact" type="button">שמור במכשיר</button><p id="ownerSaveStatus" role="status" class="owner-settings-help"></p><p class="owner-settings-help"><strong>מתי מופיעים עדכונים?</strong> סקירת היום נמשכת בעת פתיחת האפליקציה ובבדיקה יומית המוגדרת על ידי Android. ניתן לרענן ידנית. הודעות מערכת תלויות בהרשאות ההתראות, החיבור לרשת ומגבלות חיסכון בסוללה. הדוח למייל מגיע דרך ChatGPT, לא מתוך APK זה.</p>';
settings.prepend(controls);
const savedKey='kolbo-owner-contact-v1';
let saved={};try{saved=JSON.parse(localStorage.getItem(savedKey)||'{}')}catch(_){}
const packaged=window.KolboOwnerInitialTargets||{};
if(!saved.phone && packaged.phone)saved.phone=String(packaged.phone);
if(!saved.email && packaged.email)saved.email=String(packaged.email);
$('ownerPhone').value=saved.phone||'';
$('ownerEmail').value=saved.email||'';
$('ownerSaveContact').onclick=()=>{
 const phone=$('ownerPhone').value.trim(),email=$('ownerEmail').value.trim();
 if(phone && !/^0\d{8,9}$/.test(phone.replace(/[-\s]/g,''))){$('ownerSaveStatus').textContent='מספר טלפון לא תקין';return;}
 if(email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)){$('ownerSaveStatus').textContent='כתובת האימייל אינה תקינה';return;}
 localStorage.setItem(savedKey,JSON.stringify({phone,email}));
 $('ownerSaveStatus').textContent='פרטי הקשר נשמרו במכשיר בלבד. שינוי כתובת הדוא״ל ב־ChatGPT מחייב שינוי נפרד במשימה היומית.';
};
$('ownerOpenShare').onclick=()=>{open('home');const btn=$('dailyOwnerShare');if(!btn||!$('dailyOwnerCopy').value)return alert('אין עדיין סקירה עדכנית לשיתוף היום.');btn.click();};
$('ownerOpenIssue').onclick=()=>open('send');
$('ownerOpenMembers').onclick=()=>open('members');
refresh.onclick=()=>{
 feedback.textContent='בודק נתונים חדשים...';
 if(window.KolboOwnerBridge?.refreshDaily){window.KolboOwnerBridge.refreshDaily();}
 else{feedback.textContent='בדיקה ידנית זמינה בגרסת Android בלבד.';}
};
window.KolboOwnerRefreshDone=function(ok){
 feedback.textContent=ok?'הנתונים נבדקו. הסקירה תוצג כאן אם יש נתוני היום.':'לא התקבלו נתונים חדשים או מאומתים. מידע ישן לא יוצג כהמלצת היום.';
 window.KolboOwnerDailyRefresh?.();
 const date=window.KolboOwnerBridge?.todayIsrael?.();
 latest.textContent='תאריך בישראל: '+(date||new Date().toLocaleDateString('he-IL'));
};
function open(id){
 tabbar.querySelectorAll('button').forEach(button=>button.setAttribute('aria-selected',String(button.dataset.ownerTab===id)));
 mount.querySelectorAll('.owner-screen').forEach(view=>view.classList.toggle('active',view.id==='ownerScreen-'+id));
 window.scrollTo(0,0);
}
const today=window.KolboOwnerBridge?.todayIsrael?.();
latest.textContent='תאריך בישראל: '+(today||new Date().toLocaleDateString('he-IL'));
open('home');
})();