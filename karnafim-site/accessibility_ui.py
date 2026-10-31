"""Self-hosted Hebrew RTL accessibility primitives, without third-party widgets.

These enhancements support access but do not constitute WCAG certification.
"""
CSS = r"""<style id="karnafim-accessibility-css">
html{scroll-padding-top:95px}
:root{--access-accent:#ffde75}
*{overflow-wrap:break-word}
:focus-visible{outline:3px solid #e2a900!important;outline-offset:4px!important}
a:focus-visible,button:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid #e2a900!important;outline-offset:3px!important}
.skip-to-content{position:absolute;right:10px;top:-120px;z-index:20000;background:#ffed9a;color:#182b20!important;padding:12px 18px!important;border:3px solid #182b20;border-radius:11px;font-weight:900;text-decoration:none!important}
.skip-to-content:focus{top:8px}
main:focus{outline:none}
.access-box{position:relative;margin:12px auto;max-width:1120px;padding:0 16px;font-size:16px}
.access-box summary{cursor:pointer;display:inline-flex;align-items:center;gap:7px;border:2px solid #25523c;border-radius:11px;background:#fff;color:#193b29;padding:10px 15px;min-height:44px;font-size:16px;font-weight:800}
.access-box[open] summary{border-radius:11px 11px 0 0}
.access-panel{background:#fff;color:#183326;border:2px solid #25523c;padding:14px;border-radius:0 13px 13px 13px;max-width:570px;box-shadow:0 5px 24px #06150f25}
.access-panel p{color:#294e3a}
.access-actions{display:flex;flex-wrap:wrap;gap:10px}
.access-actions button{border:2px solid #284f38!important;background:#f1f5ed!important;color:#163322!important;padding:11px 16px!important;font-weight:700;min-height:44px;min-width:44px;border-radius:9px;cursor:pointer}
.access-actions button[aria-pressed=true]{background:#193d2b!important;color:#fff!important}
.access-feedback{min-height:25px;font-weight:700}
body :is(button,summary,select,input[type=checkbox],input[type=radio]){cursor:pointer}
body :is(input:not([type=checkbox]):not([type=radio]),textarea,select){min-height:44px}
body :is(a,button){text-underline-offset:.18em}
body :is(.card,.tile,.source,.event){max-width:100%}
body :is(h1,h2,h3){overflow-wrap:anywhere}
html.access-large body :is(p,li,label,input,textarea,select,button,a,summary,figcaption){font-size:1.14rem!important;line-height:1.9!important}
html.access-spacing body{letter-spacing:.5px!important;word-spacing:3px!important;line-height:2!important}
html.access-spacing body :is(p,li,label){line-height:2.1!important}
html.access-contrast body,html.access-contrast main{background:#080e0b!important;color:#fff!important}
html.access-contrast body :is(.card,.tile,.source,.event,.note,.metric,.form-box,.access-panel,.access-box summary,.photo-card,.photo-warning){background:#111c15!important;color:#fff!important;border-color:#e7d06c!important}
html.access-contrast body :is(p,small,label,h1,h2,h3,figcaption,.muted){color:#fff!important}
html.access-contrast body a{color:#fff0a8!important;text-decoration:underline!important}
html.access-contrast body input,html.access-contrast body select,html.access-contrast body textarea{background:#101c13!important;color:#fff!important;border:2px solid #fff09c!important}
html.access-contrast body :is(button,.btn,.cta){background:#ffdf84!important;color:#111f16!important;border:2px solid #15251a!important}
html.access-contrast .access-actions button{background:#ffdf84!important;color:#111f16!important}
html.access-contrast .access-actions button[aria-pressed=true]{background:#173a25!important;color:#fff!important;border-color:#ffdf84!important}
html.access-no-motion *,html.access-no-motion *::before,html.access-no-motion *::after{scroll-behavior:auto!important;transition:none!important;animation:none!important}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;transition-duration:.01ms!important;scroll-behavior:auto!important}}
@media(max-width:640px){.access-box{padding:0 12px}.access-actions button{flex:1;min-width:132px}header nav{flex-wrap:wrap;max-width:100%}body{overflow-x:hidden}}
</style>"""

SKIP = '<a class="skip-to-content" href="#main-content">דילוג לתוכן הראשי</a>'

TOOLBAR = r"""<details class="access-box" id="accessibility-tools">
<summary>♿ התאמות נגישות ותצוגה</summary>
<div class="access-panel" role="group" aria-label="אפשרויות התאמה אישיות">
<p>אפשר להגדיל טקסט, לשפר ניגודיות ולצמצם תנועה. הגדרות התצוגה נשמרות בדפדפן בלבד.</p>
<div class="access-actions">
<button type="button" data-access="large" aria-pressed="false">א+ הגדלת טקסט</button>
<button type="button" data-access="contrast" aria-pressed="false">◐ ניגודיות גבוהה</button>
<button type="button" data-access="spacing" aria-pressed="false">↔ ריווח קריא</button>
<button type="button" data-access="no-motion" aria-pressed="false">⏸ ללא אנימציות</button>
<button type="button" data-access="reset">איפוס התאמות</button>
</div>
<p id="access-feedback" class="access-feedback" role="status" aria-live="polite"></p>
<p><a href="/accessibility">הצהרת נגישות והנחיות שימוש באתר</a></p>
</div></details>"""

JS = r"""<script id="karnafim-accessibility-js">
(function(){
  'use strict';
  var modes=['large','contrast','spacing','no-motion'];
  var prefix='access-';
  var store='karnafim_accessibility_v1';
  var saved={};
  try{saved=JSON.parse(localStorage.getItem(store)||'{}')}catch(_){}
  function sync(){
    modes.forEach(function(mode){
      document.documentElement.classList.toggle(prefix+mode,!!saved[mode]);
      var b=document.querySelector('[data-access="'+mode+'"]');
      if(b)b.setAttribute('aria-pressed',saved[mode]?'true':'false');
    });
  }
  sync();
  document.addEventListener('click',function(event){
    var button=event.target.closest('[data-access]');
    if(!button)return;
    var mode=button.getAttribute('data-access');
    if(mode==='reset')saved={};
    else if(modes.indexOf(mode)!==-1)saved[mode]=!saved[mode];
    else return;
    try{localStorage.setItem(store,JSON.stringify(saved))}catch(_){}
    sync();
    var status=document.getElementById('access-feedback');
    if(status)status.textContent=mode==='reset'?'התאמות התצוגה אופסו.':'התאמת הנגישות עודכנה.';
  });
})();
</script>"""

def integrate_html(markup: str, scripts_allowed: bool = True, toolbar_enabled: bool = True) -> str:
    """Add controls to a complete HTML document; skip duplicate injection."""
    if 'id="karnafim-accessibility-css"' in markup:
        return markup
    markup=markup.replace("</head>",CSS+"</head>",1)
    if "<body>" in markup:
        markup=markup.replace("<body>","<body>"+SKIP,1)
    if "<main>" in markup:
        markup=markup.replace("<main>","<main id=\"main-content\" tabindex=\"-1\">",1)
    elif "<main " in markup and 'id="main-content"' not in markup:
        markup=markup.replace("<main ","<main id=\"main-content\" tabindex=\"-1\" ",1)
    if toolbar_enabled:
        if "<header>" in markup:
            markup=markup.replace("</header>","</header>"+TOOLBAR,1)
        elif "<main " in markup:
            markup=markup.replace("<main ",TOOLBAR+"<main ",1)
    if scripts_allowed:
        markup=markup.replace("</body>",JS+"</body>",1)
    return markup

def accessibility_statement_body(read_only: bool = False) -> str:
    mode = (
        '<p><strong>מצב אבטחה מוגבל:</strong> האתר מציג כרגע מידע ציבורי בלבד. '
        'כניסה לחשבונות, שליחת טפסים והעלאת קבצים עשויות להיות מושבתות עד לסיום בדיקת אבטחה.</p>'
        if read_only else ''
    )
    contact = ('<p>טופס הדיווח אינו פעיל במצב האבטחה המוגבל.</p>' if read_only
               else '<p>לשליחת דיווח פרטי למנהל: <a href="/accessibility/report">טופס דיווח על בעיית נגישות</a>. אפשר לדווח גם ללא חשבון.</p>')
    return ('''<section class="access-statement" aria-labelledby="access-title">
<h1 id="access-title">♿ נגישות אתר הקרנפים | ברקן</h1>
<p>מטרת האתר לאפשר גם למשתמשים עם מוגבלויות להשתמש בו בצורה נוחה ועצמאית. האתר ממשיך לעבור שיפורי נגישות, ולא הושלם עבורו עדיין סקר נגישות חיצוני מקיף.</p>'''
        +mode+'''<h2>התאמות שבוצעו בקוד</h2>
<ul>
<li>כיווניות ימין לשמאל ושפה עברית בעמודים הראשיים.</li>
<li>קישור מקלדת לדילוג ישיר לתוכן; כותרות, קישורים וטפסים סמנטיים.</li>
<li>סימון מיקוד ברור למשתמשי מקלדת.</li>
<li>כלים להגדלת טקסט, להגברת ניגודיות, לריווח טקסט ולהפחתת תנועה באזורי הקהילה הפעילים.</li>
<li>תמיכה בפריסת נייד ותיאורי תמונות במקומות שבהם התוכן ידוע.</li>
<li>דרישה לבדיקת קבצים ופרסומים לפני חשיפה לקהילה.</li>
</ul>
<h2>דרכי שימוש נגישות</h2>
<p>ניתן לעבור בין קישורים וכפתורים באמצעות Tab, להפעיל לחצנים באמצעות Enter או רווח, ולחזור לאחור באמצעות Shift+Tab. בתחילת כל עמוד ניתן להגיע באמצעות מקלדת לקישור "דילוג לתוכן הראשי".</p>
<p>אפשר להיעזר גם בהגדלת הדפדפן עם Ctrl+Plus או בתכונות הנגישות המובנות בטלפון ובמערכת ההפעלה.</p>
<h2>מה עדיין דורש בדיקה ושיפור</h2>
<p>לא בוצעה עדיין בדיקת תאימות מקיפה מול כל דרישות ת״י 5568 ו־WCAG ברמה AA. כמו כן, כתוביות ותמלול לכל סרטוני או הקלטות החברים אינם זמינים אוטומטית, ותכני משתמשים עשויים להצריך תיאור חלופי או תיקון נגישות.</p>
<h2>בקשות לסיוע ודיווח על תקלה</h2>
'''+contact+'''
<p>אין למסור סיסמאות, מספרים אישיים או פרטי בריאות בתוך פנייה.</p>
<p><a href="/">חזרה לדף הבית</a></p>
</section>''')
