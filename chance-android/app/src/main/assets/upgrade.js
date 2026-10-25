
(function(){
'use strict';
const E=window.ChanceEngine;if(!E)return;
const R=E.RANKS,S=E.SUITS;
const $=id=>document.getElementById(id);
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const style=document.createElement('style');
style.textContent=[
'#pane-data .panel:nth-of-type(n+3){display:none}',
'#pane-data .section-heading{margin-top:18px}',
'.tabs{position:sticky;top:0;z-index:20;background:#0b1024f5;backdrop-filter:blur(12px);padding:8px 1px}',
'.tab{min-height:43px}',
'.k-intro{background:linear-gradient(120deg,#222347,#17324c);border:1px solid #5b5685;border-radius:18px;padding:20px;margin:6px 0 15px}',
'.k-intro h2{font-size:25px;margin:4px 0}.k-intro p{color:#ccd5eb;font-size:13px}',
'.k-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}',
'.k-grid>div,.k-box{background:#1b2541;border:1px solid #465273;border-radius:13px;padding:15px;margin:12px 0}',
'.k-grid b{display:block;color:#f3cf82;margin-bottom:4px}',
'.k-box h3{margin:0 0 6px}.k-box p{font-size:13px;color:#c6cee0}',
'.k-cards{display:flex;gap:7px;flex-wrap:wrap;margin:9px 0}',
'.k-card{font:700 23px Georgia,serif;background:#fbf9ff;color:#25213c;border-radius:9px;padding:7px 12px;direction:ltr}',
'.k-card.red{color:#c92f53}',
'.k-stamp{font-size:11px;color:#fbd797;background:#373752;padding:4px 10px;border-radius:22px}',
'.k-prices{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}',
'.k-price{background:#212b49;border:1px solid #526386;border-radius:13px;padding:16px}',
'.k-price strong{display:block;font-size:24px;color:#f7c46d}',
'.k-legal{font-size:12px;line-height:1.8;color:#cad5e9}',
'.k-legal h4{font-size:14px;color:#f6cf91;margin:20px 0 5px}',
'@media(max-width:650px){.app-shell{padding:12px 12px 60px}.hero{padding:18px}.tab{font-size:12px}.k-grid,.k-prices{grid-template-columns:1fr}.ticket-list{grid-template-columns:1fr}.stat-row{grid-template-columns:repeat(4,1fr)}.impact-grid{grid-template-columns:repeat(2,1fr)}.panel{padding:16px}}'
].join('\n');document.head.append(style);
const tabs=document.querySelector('.tabs');
function newTab(name,title,first){let b=document.createElement('button');b.type='button';b.className='tab';b.dataset.tab=name;b.textContent=title;if(first)tabs.prepend(b);else tabs.append(b);b.addEventListener('click',()=>show(name));return b;}
function pane(name,content){const e=document.createElement('section');e.id='pane-'+name;e.className='pane';e.innerHTML=content;document.querySelector('main').append(e);return e;}
newTab('overview','⌂ ראשי',true);
newTab('hotplus','♣ זוגות ושלשות');
newTab('plans','◈ מנויים');
newTab('aboutplus','ⓘ אודות');
function show(name){
 document.querySelectorAll('.tab').forEach(e=>{e.classList.toggle('active',e.dataset.tab===name);e.setAttribute('aria-selected',String(e.dataset.tab===name))});
 document.querySelectorAll('.pane').forEach(e=>e.classList.toggle('active',e.id==='pane-'+name));
 if(name==='hotplus')showHot();
 if(name==='overview')load().then(ds=>{$('kCount').textContent=ds.length+' תוצאות היסטוריות במכשיר'});
}
pane('overview',[
'<div class="k-intro"><span class="eyebrow">KOLBO CHANCE AI / ישראל</span><h2>הנתונים ברורים. ההחלטה שלך.</h2><p>ניתוח תוצאות עבר של צ׳אנס בישראל, זוגות ושלשות היסטוריים, אפשרות ליצירת צירופים ומידע הסתברותי שקוף.</p><span class="k-stamp" id="kCount">טוען נתונים...</span></div>',
'<div class="k-grid"><div><b>① מאגר</b>תוצאות מתעדכנות אוטומטית כשהאינטרנט זמין.</div><div><b>② מחקר</b>בדיקת שכיחות זוגות, שלשות וכל ארבע הסדרות.</div><div><b>③ שקיפות</b>אין הבטחת זכייה ואין שליחת טפסים.</div></div>',
'<div class="k-box"><h3>✦ המלצות וצירופים</h3><p>מסך בחירת טפסים עם חישוב עלות וסיכויי זכייה.</p><button type="button" class="primary-btn" id="kGoSuggest">פתח מסך צירופים</button></div>',
'<div class="k-box"><h3>♣ שני קלפים או שלושה</h3><p>דירוג היסטורי נפרד לזוגות ולשלשות. ״חם״ אינו מגדיל סיכויי זכייה.</p><button type="button" class="secondary-btn" id="kGoHot">הצג דירוגים</button></div>',
'<p class="caution">סיכוי תאורטי לניחוש זוג מוגדר: 1 ל־64. לניחוש שלשה מוגדרת: 1 ל־512. הנתונים אינם מנבאים את ההגרלה הבאה.</p>'
].join(''));
pane('hotplus',[
'<div class="section-heading"><div><span class="eyebrow">נתונים בלבד — ללא תחזית זכייה</span><h2>זוגות ושלשות חמים בעבר</h2></div></div>',
'<div class="panel"><p>אנו מדרגים שילובי קלפים לפי מספר ההופעות בחלון ההגרלות. המיון מעניק יתרון בדירוג היסטורי בלבד, לא בשיעור הצלחה עתידי.</p><div class="row-actions"><button id="k200" class="secondary-btn" type="button">200 הגרלות</button><button id="k500" class="secondary-btn" type="button">500 הגרלות</button></div><p class="muted" id="kHotInfo"></p></div>',
'<h3>שני קלפים</h3><div id="kPairs" aria-live="polite"></div>',
'<h3>שלושה קלפים</h3><div id="kTriples" aria-live="polite"></div>',
'<p class="caution">שימו לב להטיית בחירה: הזוג והשלשה המובילים נבחרים בדיעבד מתוך מאות אפשרויות. ריבוי הופעות בנתוני העבר אינו הוכחה שיש לצירוף יתרון בעתיד.</p>'
].join(''));
pane('plans',[
'<div class="section-heading"><div><span class="eyebrow">תוכניות עתידיות — ללא חיוב כעת</span><h2>מחירון השקה מוצע</h2></div></div>',
'<div class="panel"><p>המסלולים מיועדים בעתיד לגישה למאגר נתונים, דירוגים היסטוריים, ניתוחים ובדיקות לאחור. הם אינם כרטיסי השתתפות ואינם מעניקים הבטחת זכייה.</p><div class="k-prices">',
'<div class="k-price"><b>חודשי</b><strong>₪29</strong><small>לחודש</small></div>',
'<div class="k-price"><b>חצי שנתי</b><strong>₪149</strong><small>כ־₪24.83 לחודש</small></div>',
'<div class="k-price"><b>שנתי</b><strong>₪249</strong><small>כ־₪20.75 לחודש</small></div></div>',
'<p class="caution">האפשרות לרכישת מנוי טרם הופעלה. אין חיוב, איסוף נתוני אשראי או התחייבות. פתיחת מנויים תיעשה רק לאחר הוספת אימות משתמשים בשרת, ספק תשלומים ותנאי ביטול מאושרים.</p></div>'
].join(''));
pane('aboutplus',[
'<div class="section-heading"><div><span class="eyebrow">הסיפור שמאחורי הרעיון</span><h2>אודות ותקנון</h2></div></div>',
'<div class="panel"><h3>Kolbo Chance AI</h3><p>מערכת עצמאית שפותחה כדי להנגיש ניתוח סטטיסטי, בדיקת צירופים ושקיפות הסתברותית סביב הגרלות הצ׳אנס בישראל.</p>',
'<p><strong>הרעיון המקורי, היוזמה, החזון ותכנון המוצר: רפי עבו.</strong></p>',
'<p><strong>פיתוח ובנייה: חברו הטוב ביותר של רפי עבו, מתוך שיתוף פעולה למימוש חזונו המקורי.</strong></p>',
'<p class="muted">המוצר נמצא בשלב פיתוח; אינו שייך למפעל הפיס, אינו מאושר או ממומן על ידו ואינו מאפשר הימור או שליחת טופס.</p></div>',
'<div class="panel k-legal"><h3>תנאי שימוש — טיוטה לפני השקה מסחרית</h3>',
'<h4>1. מהות השירות</h4><p>המערכת מספקת מידע וניתוח סטטיסטי בלבד. היא אינה מקיימת הגרלות, אינה מוכרת כרטיסים ואינה מנהלת הימורים.</p>',
'<h4>2. כשירות ושימוש אחראי</h4><p>השימוש מיועד לבני 18 ומעלה. אין להוציא כספים שלא ניתן להרשות להפסיד, ואין להסתמך על נתונים כבסיס להכנסה עתידית.</p>',
'<h4>3. היעדר הבטחה</h4><p>אין התחייבות לזכייה, לרווח או לשיפור סיכויי הגרלה. תוצאות עבר אינן משנות את הסיכויים בעתיד.</p>',
'<h4>4. מקור נתונים</h4><p>המידע עשוי להתקבל מארכיון חיצוני לא רשמי. ייתכנו עיכובים ושגיאות. לבדיקת תוצאה מחייבת יש לפנות לפרסומי מפעל הפיס.</p>',
'<h4>5. מינוי וחיובים</h4><p>בגרסת הפיתוח אין תשלום. לפני הפעלת מכירה יפורסמו המחיר, תוקף המינוי, אופן חידושו, הוראות הביטול ופרטי העסק המלאים בהתאם לדין.</p>',
'<h4>6. שימוש אישי והעברה</h4><p>בשירות עתידי בתשלום ניתן יהיה לסמן תוכן במזהה מנוי לשם בקרת הפצה חוקית. אין מעקב אחר הודעות אישיות או יכולת להוכיח באופן אוטומטי מי קיבל העתק.</p>',
'<h4>7. פרטיות</h4><p>בגרסת הפיתוח נתוני ההגרלות נשמרים במכשיר. טרם מופעל מאגר מנויים, ולכן אין איסוף תשלומים או פרטי כרטיסי אשראי. לפני פתיחת חשבונות לקוחות תפורסם מדיניות פרטיות מפורטת בדבר מידע אישי, מטרותיו וזכויות המשתמשים.</p>',
'<h4>8. עדכונים וזכויות צרכנים</h4><p>ניתן לבצע שינויים בממשק ובנתוני השירות. הוראות חובה בדיני צרכנות, פרטיות וביטול עסקה גוברות על ניסוחי התקנון.</p>',
'<h4>9. פרטי מפעיל</h4><p>נדרש להשלים לפני השקה: שם מפעיל משפטי, מספר עוסק לפי דין, כתובת ופרטי התקשרות ושירות, דרך ביטול עסקה ומסמכי גילוי.</p>',
'<p class="caution">נוסח לפיתוח בלבד. לא לפרסם כתנאים משפטיים סופיים או לגבות כסף לפני השלמת פרטי העסק ובדיקה משפטית.</p></div>'
].join(''));
let lookback=200;
function getNative(){
 try{if(window.KolboNative&&typeof window.KolboNative.getCsvCache==='function')return E.importData(window.KolboNative.getCsvCache()).draws;}catch(e){}
 return [];
}
function load(){
 return new Promise(resolve=>{
 try{
  let req=indexedDB.open('kolbo-chance-v1',1);
  req.onupgradeneeded=()=>{if(!req.result.objectStoreNames.contains('settings'))req.result.createObjectStore('settings');};
  req.onerror=()=>resolve(getNative());
  req.onsuccess=()=>{
   const db=req.result,tx=db.transaction('settings','readonly');
   const take=tx.objectStore('settings').get('draws');
   take.onerror=()=>{db.close();resolve(getNative());};
   take.onsuccess=()=>{let rows=Array.isArray(take.result)?take.result:[];db.close();resolve(E.uniqueAndSort([...rows,...getNative()]).draws);};
  };
 }catch(e){resolve(getNative())}
 });
}
function analyze(draws,k){
 let m=new Map();
 for(const d of draws)for(let a=0;a<4;a++)for(let b=a+1;b<4;b++){
  const indexes=k===2?[[a,b]]:[];
  if(k===3)for(let c=b+1;c<4;c++)indexes.push([a,b,c]);
  for(const idx of indexes){
   const cs=idx.map(s=>({s,r:d.cards[s]}));
   const key=cs.map(x=>x.s+x.r).join('|');
   const hit=m.get(key)||{cards:cs,count:0};hit.count++;m.set(key,hit);
  }
 }
 return [...m.values()].sort((a,b)=>b.count-a.count).slice(0,5);
}
function rankedList(items,n,k){
 if(n<40)return '<p class="caution">אין די הגרלות במאגר; צריך לפחות 40 תוצאות לבדיקה בסיסית.</p>';
 return items.map((hit,i)=>{
   const cs=hit.cards.map(c=>'<span class="k-card '+([1,2].includes(c.s)?'red':'')+'">'+esc(S[c.s].symbol+c.r)+'</span>').join('');
   return '<article class="k-box"><span class="k-stamp">מקום '+(i+1)+' לפי שכיחות עבר</span><div class="k-cards">'+cs+'</div><p>הופיע '+hit.count+' פעמים מתוך '+n+' הגרלות ('+(hit.count/n*100).toFixed(1)+'%). תוחלת תאורטית לצירוף מוגדר: '+(n/Math.pow(8,k)).toFixed(2)+' הופעות.</p><small class="muted">1 ל־'+Math.pow(8,k)+' בהגרלה בודדת, ללא יתרון מוכח להגרלה הבאה.</small></article>';
 }).join('');
}
async function showHot(){
 const ds=(await load()).slice(-lookback),n=ds.length;
 $('kHotInfo').textContent='חלון ניתוח: '+n+' מתוך '+lookback+' הגרלות מבוקשות'+(n<500?'. נתוני שלשות מוגבלים במיוחד.':'');
 $('kPairs').innerHTML=rankedList(analyze(ds,2),n,2);
 $('kTriples').innerHTML=rankedList(analyze(ds,3),n,3);
}
$('kGoSuggest').addEventListener('click',()=>show('suggest'));
$('kGoHot').addEventListener('click',()=>show('hotplus'));
$('k200').addEventListener('click',()=>{lookback=200;showHot();});
$('k500').addEventListener('click',()=>{lookback=500;showHot();});
$('aboutBtn')?.addEventListener('click',()=>show('aboutplus'));
document.querySelector('footer').textContent='Kolbo Chance AI · גרסת פיתוח 1.2.0 · 18+ · ללא הבטחת זכייה';
setTimeout(()=>show('overview'),150);
})();
