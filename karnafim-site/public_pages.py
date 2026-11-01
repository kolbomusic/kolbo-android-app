"""Unauthenticated read-only pages during security incident."""
import html
import re
from pathlib import Path
from urllib.parse import quote
from archive_data import ARCHIVE
from memorial_photos import PEOPLE

BASE=Path(__file__).resolve().parent
def e(x):return html.escape(str(x if x is not None else ""),quote=True)
def shell(body,title):
 s=(BASE/"maintenance_public.html").read_text("utf-8")
 s=re.sub(r"<main>.*?</main>",lambda _: "<main>"+body+"</main>",s,flags=re.S)
 return s.replace("<title>הקרנפים / ברקן — אתר קהילת פלוגה ב׳ בבדיקת אבטחה</title>","<title>"+e(title)+" | הקרנפים – ברקן</title>")
NOTICE='<div class="banner"><h2>🔐 לצפייה בלבד</h2><p>ההרשמה, ההתחברות, ההודעות והעלאת הקבצים מושבתות עד לסיום טיפול באזהרת האבטחה. אין לעקוף אזהרת Chrome.</p></div>'
def card(title,text,meta,href=None):
 link=('<p><a href="'+e(href)+'">לקריאה באתר ←</a></p>') if href else ""
 return '<article class="card"><div class="year">'+e(meta)+'</div><h3>'+e(title)+'</h3><p>'+e(text)+'</p>'+link+'</article>'
def archive():
 return '<section><h1>📜 ארכיון הקרנפים וגדוד 46</h1><p>תיעוד המורשת נשמר כאן בתוך האתר כדי להימנע משליחה לקישורים חיצוניים שבורים.</p><div class="cards">'+''.join(card(x["title"],x["summary"],x["source"]+" · "+str(x["year"] or "ללא תאריך"),"/source/"+str(x["id"])) for x in ARCHIVE)+'</div></section>'
def memorials():
 cards=''.join(card(p["name"],p["unit"]+" | "+p["role"]+" | "+p["date"],"לזכרו","/memorial/"+p["slug"]) for p in PEOPLE)
 return '<section><h1>🕯️ דפי הנצחה</h1><p>זוכרים את חברינו ואת לוחמי כוח בניה. התמונות עוד לא אושרו לפרסום באתר. מנגנון ההצעות נותר מושבת עד לסיום בדיקת האבטחה.</p><div class="cards">'+cards+'</div></section>'
def find():
 return ('<section><h1>🔎 איתור חברי הקרנפים — מידע ציבורי</h1>'
  '<p class="intro">האתר נועד לחדש קשר בין חברי פלוגה ב׳ הקרנפים / ברקן, גדוד 46, חטיבה 401. '
  'החיפוש בתוך רשימת החברים אינו פעיל כרגע כדי להגן על פרטיות המשתמשים בזמן בדיקת האבטחה.</p>'
  '<div class="cards">'
  '<article class="card"><div class="year">שלב ראשון</div><h2>זיהוי הפלוגה והמחזור</h2>'
  '<p>התחילו במידע מאומת על הפלוגה ובפריטי הארכיון של מחזורי 2003–2006. '
  'אין להניח שאדם בעל שם דומה הוא חבר פלוגה.</p>'
  '<p><a href="/archive">לארכיון המורשת המלא ←</a></p></article>'
  '<article class="card"><div class="year">שלב שני</div><h2>איתור עדויות השירות</h2>'
  '<p>קורות החיים והעדויות באתר יזכור עשויים להזכיר חברים ומפקדים שהיו בפלוגה. '
  'שמות המוזכרים שם אינם חשבונות פעילים באתר.</p>'
  '<p><a href="/source/1">לעדות ההנצחה של יוני שרעבי ←</a></p></article>'
  '<article class="card"><div class="year">שלב שלישי</div><h2>יצירת קשר בהסכמה</h2>'
  '<p>לאחר בדיקת אבטחה, כל חבר מאומת יוכל לבחור אם להופיע במדריך ולקבל בקשות קשר. '
  'לא יפורסמו כתובות, מספרי טלפון או פרטי חשבונות ללא הסכמה.</p>'
  '<p><a href="/status">מצב החברות וההתחברות ←</a></p></article>'
  '</div>'
  '<div class="note"><h2>למה אין כאן טופס איתור שמבקש פרטים?</h2>'
  '<p>בעקבות אזהרת אבטחה של Chrome, גישה לחשבונות ואיסוף פרטים חדשים מושהים זמנית. '
  'לא כדאי לעקוף את אזהרת הדפדפן. '
  'זהו אתר ותיקים עצמאי, ללא קשר רשמי לצה״ל.</p></div></section>')
def about():
 return ('<section><h1>על קהילת הקרנפים | ברקן</h1><p>זוהי יוזמה עצמאית של יוצאי פלוגה ב׳, '
  'גדוד 46 ״שלח״, חטיבה 401, שמטרתה חידוש הקשר בין חברי הפלוגה ושימור סיפורי השירות.</p>'
  '<div class="cards">'
  +card("המורשת שלנו","איסוף מידע מתקופות שונות של הגדוד, עם סימון ברור למקור ולשנת הפרסום.","קהילה ותיקה","/archive")
  +card("זוכרים את הנופלים","עדויות וקישורים לאתרי הנצחה רשמיים, ללא זיהוי אוטומטי של אנשים בתצלומים.","הנצחה","/memorials")
  +card("חברים ופרטיות","חברים יוכלו להצטרף ולבחור כיצד ליצור קשר רק לאחר אימות האבטחה וחידוש ההתחברות.","גישה מוגבלת","/status")
  +'</div><p><strong>הבהרה:</strong> האתר אינו אתר רשמי של צה״ל, משרד הביטחון או עמותת יד לשריון.</p></section>')
def privacy():
 return ('<section><h1>פרטיות המידע באתר</h1>'
  '<p>קהילת ותיקים מיועדת לאפשר חידוש קשר מרצון, תוך הגנה על פרטים אישיים ומידע מהשירות.</p>'
  '<div class="cards"><article class="card"><h2>מידע שמספק חבר רשום</h2>'
  '<p>במערכת החברים מתוכננת שמירת שם, כתובת דוא״ל ופרטים שהחבר בוחר למסור על תקופת השירות. '
  'פרטים כאלה אינם מפורסמים בדפי המורשת הציבוריים.</p></article>'
  '<article class="card"><h2>שליטה על הפרופיל</h2>'
  '<p>תצוגה במדריך החברים מותנית באישור הקהילה ובהעדפת השיתוף של החבר. '
  'בקשת קשר אינה אישור אוטומטי לשיתוף פרטים עם אדם אחר.</p></article>'
  '<article class="card"><h2>תמונות וסיפורים</h2>'
  '<p>יש לפרסם תמונות וסיפורים רק כשקיימות זכויות והסכמת המצולמים. '
  'נתוני EXIF של תמונות המועלות עוברים הסרה בקוד מערכת ההעלאות.</p></article></div>'
  '<div class="note"><h2>מצב האבטחה הנוכחי</h2>'
  '<p>ההרשמה, ההתחברות, ההודעות והעלאות הקבצים חסומות זמנית. '
  'לא נשלחים פרטים חדשים מהדפים הציבוריים.</p>'
  '<p>ביקורת תוכן מבוססת AI היא רכיב בפיתוח, ואין לראות בה הבטחה לזיהוי מושלם '
  'או לאישור זכויות של כל תמונה.</p></div>'
  '<p>אין להעביר באתר מספרים אישיים צבאיים, סיסמאות, תעודות זהות, פרטים מסווגים '
  'או כתובות של אחרים ללא הרשאה.</p></section>')
def safety():
 return ('<section><h1>מצב אבטחת אתר הקרנפים</h1>'
  '<div class="banner"><h2>הגישה לחשבונות מושהית</h2>'
  '<p>Chrome הציג אזהרה לגבי האתר. העניין בבדיקה וטרם התקבל אישור '
  'שהאזהרה הוסרה. אנא אל תעקפו את האזהרה בדפדפן.</p></div>'
  '<div class="cards">'
  +card("מה פעיל?","מידע מורשת, דפי הנצחה וגלריית תמונות היסטורית לצפייה בלבד.","ציבורי","/archive")
  +card("מה חסום?","כניסה, הרשמה, צ׳אט, פרסום תמונות ואירועים ושיתוף פרטים אישיים.","מוגן","/status")
  +card("מה נדרש לפתיחה?","בדיקת מקור אזהרת Google, טיפול בממצאים, אימות מחדש ובדיקות שימוש מקצה לקצה.","בטיחות תחילה","/accessibility")
  +'</div><p>תצוגה של דף ציבורי אינה הוכחה שהדפדפן כבר מחשיב את האתר לבטוח.</p></section>')
def help_center():
 return ('<section><h1>עזרה ושאלות נפוצות</h1>'
  '<div class="cards">'
  +card("האם אפשר להתחבר עכשיו?","לא. כל הכניסות וההרשמות מושהות עד לבירור אזהרת Chrome.","גישה מוגבלת","/status")
  +card("היכן נמצאים סיפורי הפלוגה?","14 פריטי תיעוד היסטורי וקישורים למקורות המקוריים שמורים בארכיון.","המורשת","/archive")
  +card("איך אפשר לראות תמונות?","קיימת גלריה של תמונות שריון היסטוריות עם קרדיט; אלו אינן תמונות מאומתות של הפלוגה.","גלריה ציבורית","/photos")
  +card("כיצד מגינים על פרטי חברים?","לא מתבצע איסוף או שיתוף פרטים חדשים במצב הבטיחות המוגבל.","פרטיות","/privacy")
  +'</div><p>נגישות: אפשר להשתמש במקלדת, להיעזר בקוראי מסך '
  'ובאפשרויות הנגישות המובנות בדפדפן.</p>'
  '<p><a href="/accessibility">להצהרת הנגישות באתר ←</a></p></section>')
def status():
 return '<section><h1>🔐 היכן ההתחברות והצ׳אט?</h1><div class="card"><h2>הרכיבים נשמרו, הגישה האישית מושהית</h2><p>קוד ההתחברות, הצ׳אט, ההקלטות, הפרסומים והעלאת התמונות קיים. אולם בעקבות אזהרת Chrome כל פעולה שמקבלת סיסמה, הודעה או קובץ חסומה זמנית.</p><p>לא נמחקו חשבונות משתמשים. המערכת תחזור לפעילות רק לאחר בדיקות אבטחה וטיפול תקין באזהרה.</p></div></section>'

def source_detail(source_id):
 item=next((x for x in ARCHIVE if str(x["id"])==source_id),None)
 if item is None:return None
 url=item["url"]
 label="לקריאת העמוד המקורי המלא ↗" if item["id"] not in (5,7,12) else "לעמוד המקור והחומרים הזמינים ↗"
 qualifier=("זהו רישום ספר מפורט, אך אינו כולל את כל 84 עמודי החוברת." if item["id"]==5 else
           "הכתבה מכילה גם הפניות לקבצי מדיה חיצוניים. זמינותם אינה מובטחת." if item["id"] in (7,12) else
           "העמוד המקורי מכיל תוכן מורחב, מעבר לתקציר המוצג כאן.")
 return ('<section><p><a href="/archive">← חזרה לארכיון</a></p>'
  '<div class="year">'+e(item["tag"])+' · '+e(item["year"] or "ללא תאריך")+'</div>'
  '<h1>'+e(item["title"])+'</h1>'
  '<div class="card"><h2>תמצית התיעוד</h2><p>'+e(item["summary"])+'</p>'
  '<p><strong>המקור:</strong> '+e(item["source"])+'</p></div>'
  '<div class="note"><h2>קריאת התוכן במקור</h2><p>'+e(qualifier)+'</p>'
  '<p><a href="'+e(url)+'" target="_blank" rel="noopener noreferrer">'+e(label)+'</a></p>'
  '<p>הקישור מוביל לכתובת המקור שנבדקה, ולא לדף חיפוש כללי בגוגל. תוכן של גורם חיצוני יכול להשתנות או להיעלם בהמשך.</p></div></section>')
def memorial_detail(slug):
 p=next((p for p in PEOPLE if p["slug"]==slug),None)
 if p is None:return None
 google="https://www.google.com/search?tbm=isch&q="+quote(p["query"])
 izkor="https://www.google.com/search?tbm=isch&q="+quote("site:izkor.gov.il "+p["name"])
 return '<section><p><a href="/memorials">← לכל דפי הזיכרון</a></p><div class="year">נפל ביום '+e(p["date"])+'</div><h1>לזכר '+e(p["name"])+'</h1><div class="card"><p>'+e(p["unit"])+'</p><p>'+e(p["role"])+'</p><p>דף זיכרון אישי של הקהילה. גלריית התמונות עדיין אינה מכילה תמונות שאושרו לשימוש.</p><p><a href="'+e(p["official"])+'" target="_blank" rel="noopener noreferrer"><strong>לסיפור החיים המלא באתר יזכור הרשמי ↗</strong></a></p></div><div class="cards"><article class="card"><h3>📷 איתור תמונות</h3><p>חיפוש תמונות לפי שם האדם והיחידה במקורות פומביים.</p><a href="'+e(google)+'" target="_blank" rel="noopener noreferrer">פתיחת Google Images ↗</a></article><article class="card"><h3>🕯️ ארכיון ההנצחה</h3><p>חיפוש תמונות ומידע מאתר יזכור. פרסום תמונה באתר כפוף לאימות ולרישיון שימוש.</p><a href="'+e(izkor)+'" target="_blank" rel="noopener noreferrer">חיפוש ממוקד בתמונות יזכור ↗</a></article></div><div class="note">המנגנון להצעת תמונה, שיוך לגלריה ואישור מנהל נבנה אך אינו פתוח בעת בדיקת האבטחה. אין לזהות אדם על סמך דמיון פנים בלבד.</div></section>'

def render_page(path):
 pages={"/archive":(archive,"ארכיון"),"/memorials":(memorials,"הנצחה"),"/find":(find,"איתור חברים"),"/status":(status,"מצב התחברות"),"/about":(about,"אודות"),"/privacy":(privacy,"פרטיות"),"/safety":(safety,"בטיחות"),"/help":(help_center,"עזרה")}
 if path in pages:
  fn,title=pages[path]
  return shell(NOTICE+fn()+'<p><a href="/">חזרה לעמוד הראשי ←</a></p>',title)
 if path.startswith("/source/"):
  content=source_detail(path.removeprefix("/source/"))
  return shell(NOTICE+content,"פרטי מקור") if content else None
 if path.startswith("/memorial/"):
  content=memorial_detail(path.removeprefix("/memorial/"))
  return shell(NOTICE+content,"דף הנצחה") if content else None
 return None
