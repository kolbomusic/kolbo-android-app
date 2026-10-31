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
 cases=[("קרנפים גדוד 46",'"הקרנפים" "גדוד 46"'),("ברקן גדוד 46",'"ברקן" "גדוד 46"'),("חומרים מתקופת 2006",'"גדוד 46" "2006"'),("אזכורים מפייסבוק",'site:facebook.com "גדוד 46" ברקן'),("וידאו ומורשת",'site:youtube.com "גדוד 46" ברקן')]
 cards=''
 for name,q in cases:
  url='https://www.google.com/search?q='+quote(q)
  cards+='<article class="card"><h3>'+e(name)+'</h3><p>חיפוש ממוקד במידע ציבורי בלבד.</p><a href="'+e(url)+'" target="_blank" rel="noopener noreferrer">🔎 חיפוש בגוגל ↗</a></article>'
 return '<section><h1>🔎 דרכים לאתר חברים</h1><p>גם בלי להיכנס לחשבון אפשר לחפש מידע שכבר פורסם ברשת. אין כאן חיפוש בפרופילים פרטיים או העתקה אוטומטית.</p><div class="cards">'+cards+'</div></section>'
def status():
 return '<section><h1>🔐 היכן ההתחברות והצ׳אט?</h1><div class="card"><h2>הרכיבים נשמרו, הגישה האישית מושהית</h2><p>קוד ההתחברות, הצ׳אט, ההקלטות, הפרסומים והעלאת התמונות קיים. אולם בעקבות אזהרת Chrome כל פעולה שמקבלת סיסמה, הודעה או קובץ חסומה זמנית.</p><p>לא נמחקו חשבונות משתמשים. המערכת תחזור לפעילות רק לאחר בדיקות אבטחה וטיפול תקין באזהרה.</p></div></section>'

def source_detail(source_id):
 item=next((x for x in ARCHIVE if str(x["id"])==source_id),None)
 if item is None:return None
 domain="site:izkor.gov.il " if "יזכור" in item["source"] else ("site:yadlashiryon.com " if "שריון" in item["source"] else "")
 search="https://www.google.com/search?q="+quote(domain+item["title"])
 return '<section><p><a href="/archive">← לארכיון</a></p><div class="year">'+e(item["tag"])+' · '+e(item["year"] or "ללא תאריך")+'</div><h1>'+e(item["title"])+'</h1><div class="card"><h2>מה ידוע מהתיעוד?</h2><p>'+e(item["summary"])+'</p><p><strong>מקור התיעוד:</strong> '+e(item["source"])+'</p></div><div class="note"><h3>חיפוש המקור</h3><p>הקישור הישיר לא נבדק בהצלחה, ולכן איננו שולחים לעמוד שעלול להחזיר 404. ניתן לחפש את הפרסום באתר המקור. תוצאת החיפוש אינה הוכחה שהעמוד המקורי זמין.</p><a href="'+e(search)+'" target="_blank" rel="noopener noreferrer">חיפוש הפרסום בגוגל ↗</a></div></section>'
def memorial_detail(slug):
 p=next((p for p in PEOPLE if p["slug"]==slug),None)
 if p is None:return None
 google="https://www.google.com/search?tbm=isch&q="+quote(p["query"])
 izkor="https://www.google.com/search?tbm=isch&q="+quote("site:izkor.gov.il "+p["name"])
 return '<section><p><a href="/memorials">← לכל דפי הזיכרון</a></p><div class="year">נפל ביום '+e(p["date"])+'</div><h1>לזכר '+e(p["name"])+'</h1><div class="card"><p>'+e(p["unit"])+'</p><p>'+e(p["role"])+'</p><p>דף זיכרון אישי של הקהילה. גלריית התמונות עדיין אינה מכילה תמונות שאושרו לשימוש.</p></div><div class="cards"><article class="card"><h3>📷 איתור תמונות</h3><p>חיפוש תמונות לפי שם האדם והיחידה במקורות פומביים.</p><a href="'+e(google)+'" target="_blank" rel="noopener noreferrer">פתיחת Google Images ↗</a></article><article class="card"><h3>🕯️ ארכיון ההנצחה</h3><p>חיפוש תמונות ומידע מאתר יזכור. פרסום תמונה באתר כפוף לאימות ולרישיון שימוש.</p><a href="'+e(izkor)+'" target="_blank" rel="noopener noreferrer">חיפוש ממוקד בתמונות יזכור ↗</a></article></div><div class="note">המנגנון להצעת תמונה, שיוך לגלריה ואישור מנהל נבנה אך אינו פתוח בעת בדיקת האבטחה. אין לזהות אדם על סמך דמיון פנים בלבד.</div></section>'

def render_page(path):
 pages={"/archive":(archive,"ארכיון"),"/memorials":(memorials,"הנצחה"),"/find":(find,"איתור חברים"),"/status":(status,"מצב התחברות")}
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
