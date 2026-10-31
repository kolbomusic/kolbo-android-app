import os,secrets,hashlib,hmac,html
from datetime import datetime
from flask import Flask,request,redirect,session,render_template_string,abort
import psycopg
from psycopg.rows import dict_row

app=Flask(__name__)
app.secret_key=os.environ['SECRET_KEY']
app.config.update(SESSION_COOKIE_SECURE=True,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Lax",MAX_CONTENT_LENGTH=2*1024*1024)
DB=os.environ["DATABASE_URL"]
def sql(q,params=(),fetch=False):
 with psycopg.connect(DB,row_factory=dict_row) as c:
  with c.cursor() as cur:
   cur.execute(q,params)
   return cur.fetchall() if fetch else None
def init():
 sql("""CREATE TABLE IF NOT EXISTS members (
 id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, nickname TEXT NOT NULL DEFAULT '',
 email TEXT NOT NULL UNIQUE, password TEXT NOT NULL, service_start TEXT NOT NULL DEFAULT '',
 service_end TEXT NOT NULL DEFAULT '', company TEXT NOT NULL DEFAULT '',
 role TEXT NOT NULL DEFAULT '', about TEXT NOT NULL DEFAULT '',
 approved BOOLEAN NOT NULL DEFAULT FALSE, visible BOOLEAN NOT NULL DEFAULT FALSE,
 created_at TIMESTAMPTZ DEFAULT NOW());
 CREATE TABLE IF NOT EXISTS requests (
 id BIGSERIAL PRIMARY KEY, sender_id BIGINT REFERENCES members(id) ON DELETE CASCADE,
 recipient_id BIGINT REFERENCES members(id) ON DELETE CASCADE,
 note TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ DEFAULT NOW(),
 UNIQUE(sender_id,recipient_id));
 CREATE TABLE IF NOT EXISTS messages (
 id BIGSERIAL PRIMARY KEY, sender_id BIGINT REFERENCES members(id) ON DELETE CASCADE,
 recipient_id BIGINT REFERENCES members(id) ON DELETE CASCADE,
 body TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW());""")
init()
def hashpw(p,s=None):
 s=s or secrets.token_hex(16)
 return s+":"+hashlib.pbkdf2_hmac("sha256",p.encode(),bytes.fromhex(s),250000).hex()
def verify(p,h):
 try: return hmac.compare_digest(hashpw(p,h.split(":")[0]),h)
 except: return False
def me():
 if "uid" not in session:return None
 rows=sql("SELECT * FROM members WHERE id=%s",(session["uid"],),True)
 return rows[0] if rows else None
def admin(u):return bool(u and u["email"].lower()==os.getenv("ADMIN_EMAIL","").lower() and u["approved"])
def token():return session.setdefault("csrf",secrets.token_urlsafe(24))
def guard():
 if not hmac.compare_digest(request.form.get("csrf",""),session.get("csrf","")):abort(403)
def esc(v):return html.escape(str(v or ""),quote=True)
def field(name,label,type="text",required=False,value=""):
 return f'<label>{esc(label)}<input name="{esc(name)}" type="{type}" value="{esc(value)}" maxlength="200" {"required" if required else ""}></label>'
def view(title,body):
 u=me(); nav='<a href="/">בית</a> '
 if u:
  nav+='<a href="/directory">חברים</a> <a href="/inbox">הודעות</a> <a href="/profile">הפרופיל שלי</a> '
  nav+='<a href="/memories">סיפורים</a> <a href="/discover">חיפוש ארכיון</a> '
  if admin(u):nav+='<a href="/admin">ניהול</a> '
  nav+='<a href="/password">סיסמה</a> <a href="/logout">יציאה</a>'
 else:nav+='<a href="/memories">סיפורים</a> <a class="nav-register" href="/register">הרשמה</a> <a class="nav-login" href="/login">🔑 כניסה לחשבון</a>'
 return render_template_string("""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="קהילת יוצאי פלוגה ב׳ הקרנפים/ברקן גדוד 46 חטיבה 401"><title>{{title}} | הקרנפים חוזרים לקשר</title><style>
 :root{font-family:Arial,'Segoe UI',sans-serif;background:#f3f1e8;color:#172a25}*{box-sizing:border-box}body{margin:0;line-height:1.7}header{background:#172b25;color:white;padding:16px 5%;display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}header a{color:white;text-decoration:none;margin-left:12px;font-size:14px}.logo{font-size:21px;font-weight:800;color:#dbeb9f}main{max-width:1050px;margin:auto;padding:36px 18px}h1{font-size:clamp(30px,5vw,54px);line-height:1.2;margin:0 0 18px}h2{margin-top:32px}.hero{background:linear-gradient(125deg,#142b23,#365441);padding:50px 32px;color:white;border-radius:22px}.hero p{color:#e2e9db;font-size:19px;max-width:700px}.btn,button{background:#cce38d;color:#152b24;border:0;padding:11px 20px;border-radius:10px;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block;margin:4px 0}a{color:#246448}.btn.secondary{background:#e5ebe3}.card{background:white;border:1px solid #dee2d8;border-radius:15px;padding:23px;margin:14px 0;box-shadow:0 4px 18px #13251c09}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:16px}label{display:block;font-weight:600;margin:12px 0}input,textarea,select{width:100%;display:block;padding:12px;border:1px solid #b8c4b4;border-radius:8px;font:inherit;background:white}textarea{min-height:105px}form{max-width:560px}.muted{color:#60736a}.tag{display:inline-block;padding:3px 9px;background:#e6eedb;border-radius:14px;font-size:12px}.error{background:#fff0e8;padding:14px;border-radius:8px}footer{text-align:center;padding:28px;color:#66766b;font-size:13px}
header{position:sticky;top:0;z-index:1000;min-height:76px;box-shadow:0 3px 12px #0002}
header nav{display:flex;align-items:center;flex-wrap:wrap;gap:8px;min-height:40px}
header nav a{display:inline-flex;align-items:center;justify-content:center;margin:0;padding:9px 13px;font-size:15px;font-weight:700;white-space:nowrap;border-radius:9px;color:#fff;background:rgba(255,255,255,.09)}
header nav a:hover,header nav a:focus-visible{background:rgba(255,255,255,.20);outline:2px solid #d8e7a5;outline-offset:2px}
header nav .nav-login{background:#d3ea93!important;color:#162b22!important;box-shadow:0 0 0 2px #d3ea9322}
header nav .nav-register{border:1px solid #b3c894}
.hero-actions{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-top:24px}
.hero-actions .btn{min-height:47px;display:inline-flex;align-items:center;justify-content:center;text-align:center}
.hero-actions .btn-login{background:#fff;border:2px solid #d3ea93;color:#173429}
.hero-actions .btn-login:hover{background:#f4f8ea}
.account-hint{margin-top:16px;color:#e4edda;font-size:15px}
.account-hint a{color:#efffad;font-weight:800;text-decoration:underline}
@media(max-width:700px){header{padding:12px 14px;min-height:0;align-items:stretch}header nav{width:100%;display:flex;gap:7px}header nav a{font-size:14px;padding:9px 10px}header .logo{font-size:18px}.hero{padding:33px 21px}.hero-actions{flex-direction:column;align-items:stretch}.hero-actions .btn{width:100%}}
</style></head><body><header><div class="logo">🦏 הקרנפים | ברקן</div><nav>{{nav|safe}}</nav></header><main>{{body|safe}}</main><footer>יוזמה קהילתית עצמאית של יוצאי הפלוגה • אין קשר רשמי לצה״ל • פרטים אישיים מוסתרים כברירת מחדל</footer></body></html>""",title=title,body=body,nav=nav)
def formwrap(x):return '<input type="hidden" name="csrf" value="'+token()+'">'+x
@app.route("/")
def home():
 u=me();count=sql("SELECT COUNT(*) n FROM members WHERE approved AND visible",fetch=True)[0]["n"]
 return view("בית",'<section class="hero"><span class="tag">חטיבה 401 • גדוד 46 ״שלח״ • פלוגה ב׳</span><h1>הזמן עבר.<br>החברות נשארה.</h1><p>מקום אחד לחיילי ״הקרנפים״, שבהמשך הפכו ל״ברקן״. למצוא חברים, להחליף זיכרונות ולחדש קשר אחרי שנים.</p><div class="hero-actions"><a class="btn" href="'+('/directory' if u else '/register')+'">'+('לחיפוש החברים' if u else 'הייתי שם — מצטרפים')+'</a>'+('' if u else '<a class="btn btn-login" href="/login">🔑 כבר חברים? כניסה לחשבון</a>')+'</div><p class="account-hint">חברי הפלוגה מוזמנים להתחבר או להצטרף לקהילה.</p></section><div class="grid"><div class="card"><h2>🔎 מוצאים אחד את השני</h2><p>מחפשים לפי שם או כינוי — רק חברים שאושרו ובחרו להופיע.</p></div><div class="card"><h2>🔐 הפרטיות לפני הכול</h2><p>לא מפרסמים מספרי טלפון, כתובות או דוא״ל. בקשת קשר נשלחת רק דרך המערכת.</p></div><div class="card"><h2>🕯️ זוכרים את חברינו</h2><p>זוכרים בכבוד את חללי היחידה. תוכן הנצחה יתפרסם לאחר בדיקה מתאימה.</p></div></div><p class="muted">נרשמים מרצון. הרשמה אינה הוכחה לשירות, וכל חשבון דורש אישור לפני הופעה במדריך.</p><p class="muted">חברים מאותה תקופה: 2003–2006 וגם מחזורים סמוכים.</p>')
@app.route("/health")
def health():return {"ok":True,"service":"karnafim"}
@app.route("/register",methods=["GET","POST"])
def register():
 if request.method=="POST":
  guard();
  if request.form.get("consent")!="on":abort(400)
  name=request.form.get("name","").strip()[:100];email=request.form.get("email","").lower().strip()[:200];pw=request.form.get("password","")
  if len(name)<2 or "@" not in email or len(pw)<12:return view("הרשמה",'<div class="error">שם תקין, דוא״ל תקין וסיסמה של לפחות 12 תווים נדרשים.</div><a href="/register">חזרה</a>'),400
  try:
   sql("INSERT INTO members(name,email,password,nickname,service_start,service_end,company,role) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",(name,email,hashpw(pw),request.form.get("nickname","")[:100],request.form.get("start","")[:40],request.form.get("end","")[:40],request.form.get("company","")[:100],request.form.get("role","")[:100]))
  except psycopg.errors.UniqueViolation:return view("הרשמה","<p>הכתובת כבר רשומה. אפשר להיכנס לחשבון.</p>"),409
  return view("הבקשה נקלטה",'<div class="card"><h1>הבקשה נקלטה</h1><p>החשבון ממתין לאישור מנהל הקהילה. אין פרסום אוטומטי של הפרטים.</p><a href="/login">לכניסה</a></div>')
 body='<h1>מצטרפים לקרנפים</h1><p>ההרשמה מאושרת ידנית. אין למסור מספר אישי צבאי, כתובת או מידע רגיש.</p><form method="post" class="card">'+formwrap(field("name","שם מלא",required=True)+field("nickname","כינוי מהשירות")+field("email","כתובת דוא״ל","email",True)+field("password","סיסמה (12 תווים לפחות)","password",True)+field("start","מחזור גיוס / שנה")+field("end","שנת שחרור")+field("company","פלוגה (קרנפים / ברקן)")+field("role","תפקיד / צוות")+ '<label><input type="checkbox" name="consent" required style="width:auto;display:inline"> אני מסכים/ה לשמירת הפרטים לצורך קהילת החברים</label><button>שליחת בקשת הצטרפות</button></form>')
 return view("הרשמה",body+'<p>כבר רשומים בקהילה? <a href="/login"><strong>כניסה לחשבון</strong></a></p>')
@app.route("/login",methods=["GET","POST"])
def login():
 if request.method=="POST":
  guard();email=request.form.get("email","").strip().lower()
  rows=sql("SELECT * FROM members WHERE email=%s",(email,),True)
  if rows and verify(request.form.get("password",""),rows[0]["password"]):
   session.clear();session["uid"]=rows[0]["id"];return redirect("/directory")
  return view("כניסה",'<p class="error">פרטי ההתחברות לא נכונים.</p><a href="/login">ניסיון נוסף</a>'),401
 return view("כניסה",'<h1>כניסה לחשבון</h1><form method="post" class="card">'+formwrap(field("email","דוא״ל","email",True)+field("password","סיסמה","password",True)+'<button>כניסה לחשבון</button></form><p>עדיין אין לך חשבון? <a href="/register"><strong>להרשמה לקהילה</strong></a></p><p>התחברות באמצעות Google תתווסף לאחר הגדרת OAuth מאובטחת מול Google.</p>'))
@app.route("/logout")
def logout():session.clear();return redirect("/")
@app.route("/directory")
def directory():
 u=me()
 if not u:return redirect("/login")
 if not u["approved"]:return view("בהמתנה",'<h1>הבקשה שלך בהמתנה לאישור</h1><p>רק משתמשים מאושרים יכולים לצפות במדריך.</p>')
 term=request.args.get("q","")[:80]
 records=sql("SELECT id,name,nickname,service_start,service_end,company,role,about FROM members WHERE approved AND visible AND (name ILIKE %s OR nickname ILIKE %s) ORDER BY name LIMIT 100",('%'+term+'%','%'+term+'%'),True)
 cards=''.join('<div class="card"><h2>'+esc(r["name"])+'</h2><p>'+esc(r["nickname"])+' • '+esc(r["company"])+'</p><p class="muted">'+esc(r["service_start"])+'–'+esc(r["service_end"])+' | '+esc(r["role"])+'</p><p>'+esc(r["about"])+'</p><a href="/contact/'+str(r["id"])+'">שליחת בקשת קשר</a></div>' for r in records)
 return view("חברים",'<h1>מדריך חברי הפלוגה</h1><form method="get"><input name="q" value="'+esc(term)+'" placeholder="שם או כינוי"><button>חיפוש</button></form><div class="grid">'+(cards or '<p>אין חברים מתאימים שהסכימו להופיע.</p>')+'</div>')
@app.route("/profile",methods=["GET","POST"])
def profile():
 u=me()
 if not u:return redirect("/login")
 if request.method=="POST":
  guard()
  sql("UPDATE members SET nickname=%s,about=%s,visible=%s WHERE id=%s",(request.form.get("nickname","")[:100],request.form.get("about","")[:1000],request.form.get("visible")=="on",u["id"]))
  return redirect("/profile")
 return view("פרופיל",'<h1>הפרופיל שלי</h1><p>מצב החשבון: '+("מאושר" if u["approved"] else "ממתין לאישור")+'</p><form method="post" class="card">'+formwrap(field("nickname","כינוי",value=u["nickname"])+'<label>עליי<textarea name="about" maxlength="1000">'+esc(u["about"])+'</textarea></label><label><input style="display:inline;width:auto" type="checkbox" name="visible" '+("checked" if u["visible"] else "")+'> הצג אותי במדריך החברים</label><button>שמירת הפרופיל</button></form><form action="/delete-account" method="post" onsubmit="return confirm(\'למחוק את החשבון והמידע לצמיתות?\')">'+formwrap('<button style="background:#f9d0ca">מחיקת החשבון שלי</button>')+'</form>'))
@app.route("/delete-account",methods=["POST"])
def delete_account():
 u=me()
 if not u:return redirect("/login")
 guard();sql("DELETE FROM members WHERE id=%s",(u["id"],));session.clear();return redirect("/")
@app.route("/contact/<int:uid>",methods=["GET","POST"])
def contact(uid):
 u=me()
 if not u or not u["approved"]:return redirect("/login")
 if u["id"]==uid:abort(400)
 r=sql("SELECT id,name FROM members WHERE id=%s AND approved AND visible",(uid,),True)
 if not r:abort(404)
 if request.method=="POST":
  guard();note=request.form.get("note","")[:600].strip()
  if not note:abort(400)
  sql("INSERT INTO requests(sender_id,recipient_id,note) VALUES(%s,%s,%s) ON CONFLICT(sender_id,recipient_id) DO UPDATE SET note=EXCLUDED.note",(u["id"],uid,note))
  return view("נשלח",'<p>בקשת הקשר נקלטה ותופיע בתיבה של החבר כאשר ייכנס לאתר.</p><a href="/directory">חזרה למדריך</a>')
 return view("בקשת קשר",'<h1>שליחת בקשת קשר אל '+esc(r[0]["name"])+'</h1><form method="post" class="card">'+formwrap('<label>הודעה<textarea name="note" required maxlength="600" placeholder="היי, שירתנו יחד..."></textarea></label><button>שליחה</button></form>'))
@app.route("/inbox",methods=["GET","POST"])
def inbox():
 u=me()
 if not u or not u["approved"]:return redirect("/login")
 if request.method=="POST":
  guard();uid=int(request.form.get("recipient",0));body=request.form.get("body","")[:2000].strip()
  if not body:abort(400)
  connection=sql("SELECT 1 FROM requests WHERE (sender_id=%s AND recipient_id=%s) OR (sender_id=%s AND recipient_id=%s)",(u["id"],uid,uid,u["id"]),True)
  if not connection:abort(403)
  sql("INSERT INTO messages(sender_id,recipient_id,body) VALUES (%s,%s,%s)",(u["id"],uid,body));return redirect("/inbox")
 reqs=sql("SELECT r.sender_id,r.note,m.name FROM requests r JOIN members m ON m.id=r.sender_id WHERE r.recipient_id=%s ORDER BY r.created_at DESC",(u["id"],),True)
 msgs=sql("SELECT x.sender_id,x.recipient_id,x.body,m.name FROM messages x JOIN members m ON m.id=x.sender_id WHERE x.sender_id=%s OR x.recipient_id=%s ORDER BY x.created_at DESC LIMIT 80",(u["id"],u["id"]),True)
 body='<h1>ההודעות שלי</h1><h2>בקשות קשר שהתקבלו</h2>'
 for x in reqs:body+='<div class="card"><strong>'+esc(x["name"])+'</strong><p>'+esc(x["note"])+'</p><form method="post">'+formwrap('<input type="hidden" name="recipient" value="'+str(x["sender_id"])+'"><textarea name="body" required placeholder="תשובה לחבר"></textarea><button>השב</button>')+'</form></div>'
 body+='<h2>הודעות</h2>'
 for x in msgs:body+='<div class="card"><strong>'+esc(x["name"])+'</strong><p>'+esc(x["body"])+'</p></div>'
 return view("הודעות",body)
@app.route("/admin",methods=["GET","POST"])
def manage():
 u=me()
 if not admin(u):abort(403)
 if request.method=="POST":
  guard();uid=int(request.form.get("uid",0));op=request.form.get("op")
  if uid!=u["id"]:
   if op=="approve":sql("UPDATE members SET approved=TRUE WHERE id=%s",(uid,))
   if op=="hide":sql("UPDATE members SET approved=FALSE,visible=FALSE WHERE id=%s",(uid,))
  return redirect("/admin")
 rows=sql("SELECT id,name,email,company,service_start,approved,visible FROM members ORDER BY approved,created_at DESC LIMIT 200",fetch=True)
 b='<h1>ניהול קהילה</h1><p>אימות השירות מתבצע על ידי מנהל הקהילה — לא על סמך פרטי ההרשמה בלבד.</p>'
 for r in rows:
  b+='<div class="card"><strong>'+esc(r["name"])+'</strong> • '+esc(r["email"])+'<p>'+esc(r["company"])+' '+esc(r["service_start"])+' | '+("מאושר" if r["approved"] else "ממתין")+'</p><form method="post">'+formwrap('<input type="hidden" name="uid" value="'+str(r["id"])+'"><button name="op" value="approve">אישור</button> <button name="op" value="hide">הסתרה</button>')+'</form></div>'
 pending=sql("SELECT x.id,x.title,x.story,m.name FROM memories x JOIN members m ON m.id=x.author_id WHERE NOT x.approved ORDER BY x.created_at DESC LIMIT 100",fetch=True)
 b+="<h2>אירועים הממתינים לאישור</h2>"
 for x in pending:
  b+='<div class="card"><strong>'+esc(x["title"])+'</strong><p>'+esc(x["story"])+'</p><small>'+esc(x["name"])+'</small><form method="post" action="/admin/memory">'+formwrap('<input name="mid" type="hidden" value="'+str(x["id"])+'"><button name="action" value="approve">פרסום</button><button name="action" value="delete">מחיקה</button>')+'</form></div>'
 return view("ניהול",b)
@app.errorhandler(500)
def error(e):return view("שגיאה","<p>אירעה תקלה זמנית. נסו שוב מאוחר יותר.</p>"),500

sql("""CREATE TABLE IF NOT EXISTS memories(
 id BIGSERIAL PRIMARY KEY, author_id BIGINT REFERENCES members(id) ON DELETE CASCADE,
 title TEXT NOT NULL, story TEXT NOT NULL, year INTEGER,
 source_url TEXT NOT NULL DEFAULT '', approved BOOLEAN DEFAULT FALSE,
 created_at TIMESTAMPTZ DEFAULT NOW())""")
@app.route("/memories",methods=["GET","POST"])
def memories():
 u=me()
 if request.method=="POST":
  if not u or not u["approved"]:return redirect("/login")
  guard()
  title=request.form.get("title","").strip()[:140]
  story=request.form.get("story","").strip()[:5000]
  year=request.form.get("year","").strip()
  url=request.form.get("source_url","").strip()[:500]
  if not title or len(story)<10 or (year and (not year.isdigit() or not 1960<=int(year)<=2026)) or (url and not url.startswith(("https://","http://"))):abort(400)
  sql("INSERT INTO memories(author_id,title,story,year,source_url) VALUES(%s,%s,%s,%s,%s)",(u["id"],title,story,int(year) if year else None,url))
  return view("נשלח",'<div class="card">הסיפור נשלח לאישור מנהל. <a href="/memories">חזרה</a></div>')
 rows=sql("SELECT x.*,m.name FROM memories x JOIN members m ON x.author_id=m.id WHERE x.approved ORDER BY x.year NULLS LAST, x.created_at DESC LIMIT 150",fetch=True)
 b='<h1>הסיפורים שלנו</h1><p>ציר הזמן של הקרנפים / ברקן: זיכרונות, אירועים ואזכורים מהשירות.</p>'
 if u and u["approved"]:
  b+='<details class="card"><summary>➕ הוספת זיכרון או אירוע</summary><form method="post">'+formwrap(field("title","כותרת",required=True)+field("year","שנה","number")+'<label>מה קרה?<textarea name="story" required minlength="10" maxlength="5000"></textarea></label>'+field("source_url","קישור למקור פומבי (לא חובה)","url")+'<button>שליחה לאישור</button></form></details>')
 for r in rows:
  b+='<article class="card"><span class="tag">'+esc(r["year"] or "ללא שנה")+'</span><h2>'+esc(r["title"])+'</h2><p>'+esc(r["story"])+'</p><small>'+esc(r["name"])+'</small>'
  if r["source_url"]:b+='<p><a target="_blank" rel="noopener noreferrer nofollow" href="'+esc(r["source_url"])+'">מקור חיצוני</a></p>'
  b+='</article>'
 return view("ציר זמן",b)
@app.route("/discover")
def discover():
 u=me()
 if not u or not u["approved"]:return redirect("/login")
 from urllib.parse import quote
 q=request.args.get("q","").strip()[:100]
 terms=[q+' "גדוד 46"' if q else '"הקרנפים" "גדוד 46"','"פלוגה ב" "גדוד 46"','"ברקן" "גדוד 46"','"גדוד 46" "2006"']
 b='<h1>מוצאים זיכרונות ברשת</h1><p>קישורי חיפוש במקורות פומביים בלבד. פרטים אישיים ותמונות של אחרים לא מועתקים ללא רשות.</p><form><input name="q" value="'+esc(q)+'" placeholder="שם, תאריך או אירוע"><button>חפש</button></form>'
 for term in terms:b+='<div class="card"><a target="_blank" rel="noopener noreferrer" href="https://www.google.com/search?q='+quote(term)+'">'+esc(term)+'</a></div>'
 b+='<p><a href="https://www.izkor.gov.il/">יזכור</a> · <a href="https://yadlashiryon.com/">יד לשריון</a></p>'
 return view("איתור ארכיון",b)
@app.route("/admin/memory",methods=["POST"])
def memory_admin():
 u=me()
 if not admin(u):abort(403)
 guard();mid=int(request.form.get("mid",0))
 if request.form.get("action")=="approve":sql("UPDATE memories SET approved=TRUE WHERE id=%s",(mid,))
 elif request.form.get("action")=="delete":sql("DELETE FROM memories WHERE id=%s",(mid,))
 return redirect("/admin")

@app.route("/password",methods=["GET","POST"])
def change_password():
 u=me()
 if not u:return redirect("/login")
 if request.method=="POST":
  guard()
  old=request.form.get("old","")
  new=request.form.get("new","")
  if not verify(old,u["password"]) or len(new)<12 or len(new)>200:
   return view("שינוי סיסמה",'<p class="error">הסיסמה הנוכחית שגויה או שהחדשה קצרה מדי. נדרשים לפחות 12 תווים.</p><a href="/password">חזרה</a>'),400
  sql("UPDATE members SET password=%s WHERE id=%s",(hashpw(new),u["id"]))
  session.clear()
  return view("הסיסמה הוחלפה",'<div class="card"><h1>הסיסמה עודכנה</h1><p>אפשר להיכנס מחדש עם הסיסמה החדשה.</p><a href="/login">כניסה</a></div>')
 return view("שינוי סיסמה",'<h1>שינוי סיסמה</h1><form method="post" class="card">'+formwrap(field("old","הסיסמה הנוכחית","password",True)+field("new","סיסמה חדשה (לפחות 12 תווים)","password",True)+'<button>עדכון סיסמה</button></form>'))

if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))
