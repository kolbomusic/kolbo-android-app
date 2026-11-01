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
 # All searches below are public and do not submit identifying data to our site.
 searches=[
  ("פלוגת הקרנפים 2003–2006",'"פלוגה ב" "הקרנפים" "גדוד 46"'),
  ("פלוגת ברקן — גדוד 46",'"פלוגת ברקן" "גדוד 46"'),
  ("זיכרונות ותיעוד השירות",'"גדוד 46" "2006" "קרנפים"'),
  ("קבוצות ותיקי הגדוד בפייסבוק",'"גדוד 46" "קרנפים" site:facebook.com'),
  ("מורשת פלוגת ברקן",'"ברקן" "חטיבה 401"'),
 ]
 cards=[]
 for title,term in searches:
  url="https://www.google.com/search?q="+quote(term)
  cards.append('<article class="card"><h2>'+e(title)+'</h2><p>חיפוש ברשת הציבורית. התוצאות משתנות ואין להסיק מהן שאדם שירת בפלוגה.</p><p><a href="'+e(url)+'" target="_blank" rel="noopener noreferrer">פתיחת חיפוש ממוקד ↗</a></p></article>')
 return ('<section><h1>🔎 איתור חברי פלוגת הקרנפים / ברקן</h1>'
  '<p class="intro">פלוגה ב׳, גדוד 46 ״שלח״, חטיבה 401 — בדגש על מחזורי 2003–2006.</p>'
  '<div class="banner" role="status"><h2>מדריך החברים הפרטי אינו זמין כרגע</h2>'
  '<p>עד להשלמת בדיקת האבטחה, אין הרשמה או חיפוש בפרופילים פרטיים. '
  'אפשר בינתיים להשתמש בחיפושים הציבוריים שלהלן, ללא מסירת פרטים לאתר הקהילה.</p></div>'
  '<h2>חיפושים מוכנים לשימוש</h2><div class="cards">'+''.join(cards)+'</div>'
  '<div class="cards"><article class="card"><h2>תיעוד ממקורות היסטוריים</h2>'
  '<p>ארכיון עדויות, שמות ואזכורים מהפלוגה. מדובר במקורות מורשת, לא ברשימת חברים רשומים.</p>'
  '<p><a href="/archive">פתיחת ארכיון המורשת ←</a></p></article>'
  '<article class="card"><h2>חידוש קשר בהסכמה</h2>'
  '<p>לאחר חידוש השירות, חברים מאושרים יוכלו לבחור אם להופיע במדריך ולנהל בקשות קשר.</p>'
  '<p><a href="/status">מצב השירות וההתחברות ←</a></p></article></div>'
  '<div class="note"><strong>פרטיות:</strong> אין לפרסם מספרי טלפון, כתובות, מספרים אישיים או תמונות של חברים ללא רשותם. '
  'החיפוש אינו מבצע זיהוי פנים או אימות שירות צבאי.</div></section>')
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
def terms():
 return ('<section><h1>תנאי שימוש — קהילת הקרנפים / ברקן</h1>'
  '<p>האתר הוא יוזמה קהילתית עצמאית של ותיקי פלוגה ב׳ בגדוד 46, חטיבה 401, '
  'ואינו קשור רשמית לצה״ל, למשרד הביטחון או לגוף ממשלתי כלשהו.</p>'
  '<div class="cards"><article class="card"><h2>מטרת השירות</h2>'
  '<p>שימור סיפורי מורשת והנצחה וחידוש קשר מרצון בין חברי השירות. '
  'אימות זהות באמצעות Google, כשיתאפשר, אינו הוכחה לשירות צבאי; '
  'הצטרפות לקהילה תהיה כפופה לאישור מנהל.</p></article>'
  '<article class="card"><h2>פרטיות ותוכן</h2>'
  '<p>אין לפרסם מספר אישי, מידע מסווג, כתובות פרטיות או תמונות של אחרים ללא הסכמתם. '
  'על מפרסמי תוכן לוודא זכויות שימוש ונכונות המידע.</p></article>'
  '<article class="card"><h2>ביקורת תוכן</h2>'
  '<p>מנהל הקהילה רשאי להסיר תוכן פוגעני, מטעה או מפר זכויות. '
  'אין הבטחה שאמצעי ביקורת אוטומטיים יזהו כל הפרה.</p></article>'
  '<article class="card"><h2>זמינות</h2>'
  '<p>תכונות החברים מושבתות בתקופת בדיקת האבטחה. '
  'מידע ארכיוני וקישורים חיצוניים מוצגים לצורכי מורשת ואינם הבטחה לזמינות המקורות.</p>'
  '</article></div><p><a href="/privacy">למדיניות הפרטיות ←</a> · '
  '<a href="/safety">למצב האבטחה ←</a></p></section>')
def status():
 # Display live non-sensitive configuration, not stale claims about setup.
 # Google Safe Browsing verdict is external: never pretend an env toggle is
 # proof that Google's warning has been removed.
 import os
 from google_identity import configuration_checks, auth_mode
 checks=configuration_checks()
 mode=auth_mode()
 client_ok=checks["valid_client_id"]
 mode_ok=mode in ("gis","oauth")
 mode_credentials=(mode=="gis" or (mode=="oauth" and checks["client_secret_present"]))
 configured=checks["explicitly_enabled"] and client_ok and mode_ok and mode_credentials
 maintenance_off=os.getenv("KARNAFIM_MAINTENANCE","1")=="0"
 safety_approved=os.getenv("KARNAFIM_SAFETY_RELEASE_APPROVED","0")=="1"
 def item(label,ok,detail=""):
  return ('<li><strong>'+e(label)+': </strong>'+
          ('הוגדר ✓' if ok else 'טרם הושלם ✗')+
          (' — '+e(detail) if detail else '')+'</li>')
 rows=''.join([
  item("מזהה Google Client",client_ok,"המזהה עצמו אינו מוצג לציבור"),
  item("מסלול התחברות תקין",mode_ok and mode_credentials,
       "Google Identity Services" if mode=="gis" else
       "OAuth דורש גם Client Secret" if mode=="oauth" else "מצב לא מוכר"),
  item("דגל הפעלת Google",checks["explicitly_enabled"]),
  item("אישור שחרור אבטחה",safety_approved,
       "נדרש אישור מפורש רק אחרי בדיקת Google ומבחני אבטחה"),
  item("יציאה ממצב תחזוקה",maintenance_off)])
 state=("ההתחברות טרם נפתחה; לפחות תנאי הפעלה אחד חסר."
        if not (configured and safety_approved and maintenance_off) else
        "הגדרות ההפעלה מוכנות. נדרש עדיין אימות ידני של כניסה והסטטוס אצל Google.")
 return ('<section><h1>🔐 כניסה ואיתור חברים — מצב אבטחה</h1>'
  '<div class="card"><h2>מצב Google Sign-In בפועל</h2>'
  '<p>להלן בדיקות תצורה בזמן אמת מהשרת. אין כאן מזהי חשבון, סודות או נתוני חברים.</p>'
  '<ul>'+rows+'</ul><p><strong>'+e(state)+'</strong></p>'
  '<p>האתר נעול כרגע לקריאה בלבד בעקבות דיווח על אזהרת Chrome. '
  'מצב Google Safe Browsing אינו מתעדכן אוטומטית מתוך דגלי התצורה, '
  'ולא ניתן להסיק מתצורה תקינה ש־Google הסירה את האזהרה.</p>'
  '<p>בדיקת הכניסה המעשית, ביקורת הרשאות החברים והפעלת פרסומים יתבצעו רק '
  'לאחר השלמת בדיקת האבטחה.</p></div>'
  '<div class="card"><h2>מה יקרה כשייפתח השירות?</h2>'
  '<p>ההתחברות תתבצע באמצעות Google בלבד, ללא סיסמה מקומית. '
  'Google תאמת את החשבון, ומנהל הקהילה יאשר בנפרד שייכות לפלוגה. '
  'החברות והפרסומים לא יהיו פתוחים לציבור.</p></div>'
  '<p><a href="/safety">הסבר על מצב האבטחה ←</a> · '
  '<a href="/privacy">מידע על שמירת פרטים ←</a></p></section>')

def source_detail(source_id):
 item=next((x for x in ARCHIVE if str(x["id"])==source_id),None)
 if item is None:return None
 url=item["url"]
 # These old articles were checked on 2026-11-01 and returned HTTP 404.
 # Never route visitors to a known-broken source URL or imply that the
 # publisher's archive is the full original article.
 if item["id"] in (4,5,7,12):
  return ('<section><p><a href="/archive">← חזרה לארכיון</a></p>'
   '<div class="year">'+e(item["tag"])+' · '+e(item["year"] or "ללא תאריך")+'</div>'
   '<h1>'+e(item["title"])+'</h1>'
   '<div class="card"><h2>תמצית התיעוד</h2><p>'+e(item["summary"])+'</p>'
   '<p><strong>מקור התיעוד:</strong> '+e(item["source"])+'</p></div>'
   '<div class="note"><h2>הקישור למאמר המקורי אינו פעיל</h2>'
   '<p>כתובת המאמר ההיסטורית החזירה שגיאת 404 בבדיקה ב־1.11.2026. '\
   'תמצית התיעוד נשמרת כאן, אך העמוד המלא אינו זמין כרגע בקישור זה.</p>'
   '<p><strong>כתובת היסטורית (לא קישור פעיל):</strong> <code dir="ltr">'+e(url)+'</code></p>'
   '<p><a href="https://www.yadlashiryon.com/archives" target="_blank" rel="noopener noreferrer">פתיחת ארכיון יד לשריון הרשמי ↗</a></p>'
   '<p>לתשומת הלב: הקישור החלופי מוביל לעמוד הארכיון הכללי ולא למאמר המקורי.</p></div></section>')
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
 pages={"/archive":(archive,"ארכיון"),"/memorials":(memorials,"הנצחה"),"/status":(status,"מצב התחברות"),"/about":(about,"אודות"),"/privacy":(privacy,"פרטיות"),"/terms":(terms,"תנאי שימוש"),"/safety":(safety,"בטיחות"),"/help":(help_center,"עזרה")}
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
