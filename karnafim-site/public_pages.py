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
def card(title,text,meta):
 return '<article class="card"><div class="year">'+e(meta)+'</div><h3>'+e(title)+'</h3><p>'+e(text)+'</p></article>'
def archive():
 return '<section><h1>📜 ארכיון הקרנפים וגדוד 46</h1><p>תיעוד המורשת נשמר כאן בתוך האתר כדי להימנע משליחה לקישורים חיצוניים שבורים.</p><div class="cards">'+''.join(card(x["title"],x["summary"],x["source"]+" · "+str(x["year"] or "ללא תאריך")) for x in ARCHIVE)+'</div></section>'
def memorials():
 cards=''.join(card(p["name"],p["unit"]+" | "+p["role"]+" | "+p["date"],"לזכרו") for p in PEOPLE)
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
def render_page(path):
 pages={"/archive":(archive,"ארכיון"),"/memorials":(memorials,"הנצחה"),"/find":(find,"איתור חברים"),"/status":(status,"מצב התחברות")}
 if path not in pages:return None
 fn,title=pages[path]
 return shell(NOTICE+fn()+'<p><a href="/">חזרה לעמוד הראשי ←</a></p>',title)
