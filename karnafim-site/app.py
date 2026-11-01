import os,re,secrets,hashlib,hmac,html
from datetime import datetime, timedelta
from flask import Flask,request,redirect,session,render_template_string,abort,Response
import psycopg
from psycopg.rows import dict_row
from accessibility_ui import integrate_html, accessibility_statement_body
from google_identity import enabled as google_ready, install_google_login

app=Flask(__name__)
app.secret_key=os.environ['SECRET_KEY']
app.config.update(SESSION_COOKIE_NAME="karnafim_oidc_session",SESSION_COOKIE_SECURE=True,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Lax",PERMANENT_SESSION_LIFETIME=timedelta(hours=6),MAX_CONTENT_LENGTH=2*1024*1024,MAX_FORM_MEMORY_SIZE=64*1024,MAX_FORM_PARTS=25,TRUSTED_HOSTS=["karnafim-community-46.onrender.com","localhost","127.0.0.1"])
# Read-only security mode must not depend on the private database being reachable.
# Enabling the community again requires an explicit restart with maintenance disabled.
READ_ONLY_BOOT=os.environ.get("KARNAFIM_MAINTENANCE","1")=="1"
DB=os.environ.get("DATABASE_URL","") if READ_ONLY_BOOT else os.environ["DATABASE_URL"]

@app.before_request
def security_hold():
 if READ_ONLY_BOOT and request.path not in ("/health","/favicon.svg","/favicon.ico","/robots.txt","/sitemap.xml"):
  import re
  can_read=(request.path in ("/","/about","/privacy","/safety","/archive","/memorials","/status","/photos","/accessibility","/help") or re.fullmatch(r"/source/[0-9]+",request.path) is not None or re.fullmatch(r"/memorial/[a-z0-9-]+",request.path) is not None)
  if request.method in ("GET","HEAD") and can_read:
   from pathlib import Path
   if request.path=="/accessibility":
    from public_pages import shell, NOTICE
    document=shell(NOTICE+accessibility_statement_body(read_only=True),"הצהרת נגישות")
   elif request.path=="/photos":
    from historical_photos import gallery_page
    document=gallery_page()
   elif request.path!="/":
    from public_pages import render_page
    document=render_page(request.path)
    if document is None: abort(404)
   else:
    document=(Path(__file__).resolve().parent/"maintenance_public.html").read_text(encoding="utf-8")
   gsc_token=os.environ.get("KARNAFIM_GSC_VERIFICATION","").strip()
   if gsc_token and re.fullmatch(r"[A-Za-z0-9_-]{20,256}",gsc_token):
    document=document.replace("</head>",'<meta name="google-site-verification" content="'+gsc_token+'"></head>',1)
   response=Response(integrate_html(document,scripts_allowed=False,toolbar_enabled=False),status=200,mimetype="text/html")
   response.headers["Content-Security-Policy"]="default-src 'none'; style-src 'unsafe-inline'; img-src https://upload.wikimedia.org; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
  else:
   # Previously active credential endpoints are fully retired while the site is under review.
   # 410 (rather than temporary 503) explicitly tells crawlers that these forms are gone;
   # no private content or credentials are served, even if an old bookmark is followed.
   retired_credentials=(request.path in ("/login","/register","/password","/find") or request.path.startswith("/auth/google/"))
   message=("שירות איתור החברים הוסר זמנית בעקבות בדיקת אבטחת האתר. לא נאספים כאן פרטים אישיים." if request.path=="/find" else "עמוד הכניסה הוסר במסגרת טיפול באבטחת האתר. אין להזין כאן פרטי התחברות." if retired_credentials else "אתר הקרנפים — גישה אישית מושהית לצורך בדיקת אבטחה.")
   response=Response(message,status=(410 if retired_credentials else 503),mimetype="text/plain")
   response.headers["Content-Security-Policy"]="default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
  response.headers["Cache-Control"]="no-store, max-age=0"
  response.headers["X-Robots-Tag"]=("index, follow" if response.status_code==200 else "noindex, nofollow")
  response.headers["X-Content-Type-Options"]="nosniff"
  response.headers["Referrer-Policy"]="no-referrer"
  return response

# Public crawl map for the temporary *read-only* site. Private routes remain
# blocked at the application layer; robots.txt is not an access-control system.
@app.route("/robots.txt")
def robots_txt():
 content="\n".join([
   "User-agent: *",
   "Allow: /",
   # /find and credential endpoints now explicitly return 410 so Google can recrawl.
   # Do not disallow crawling these URLs: Google must be able to observe removal.
   "Disallow: /new-post",
   "Disallow: /my-posts",
   "Disallow: /chats",
   "Disallow: /chat/",
   "Disallow: /admin",
   "Disallow: /profile",
   "Disallow: /directory",
   "Disallow: /community-media/",
   "Disallow: /post/",
   "Sitemap: https://karnafim-community-46.onrender.com/sitemap.xml",
   ""
 ])
 return Response(content,mimetype="text/plain")

@app.route("/sitemap.xml")
def public_sitemap():
 from memorial_photos import PEOPLE
 paths=["/","/about","/privacy","/safety","/archive","/memorials",
        "/photos","/help","/accessibility"]
 paths.extend("/source/"+str(n) for n in range(1,15))
 paths.extend("/memorial/"+p["slug"] for p in PEOPLE)
 xml='<?xml version="1.0" encoding="UTF-8"?>\n'
 xml+='<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
 xml+="".join("<url><loc>https://karnafim-community-46.onrender.com"+
              html.escape(path,quote=True)+"</loc></url>" for path in paths)
 xml+="</urlset>"
 return Response(xml,mimetype="application/xml")

@app.after_request
def harden_responses(resp):
 # Verification must remain available after the site leaves read-only mode;
 # otherwise Search Console can revoke ownership on its periodic recheck.
 if request.path=="/" and resp.status_code==200 and resp.mimetype=="text/html":
  token=os.environ.get("KARNAFIM_GSC_VERIFICATION","").strip()
  if token and re.fullmatch(r"[A-Za-z0-9_-]{20,256}",token):
   data=resp.get_data(as_text=True)
   if 'name="google-site-verification"' not in data and "</head>" in data:
    resp.set_data(data.replace("</head>",'<meta name="google-site-verification" content="'+token+'"></head>',1))
 if request.path in ("/login","/register","/password","/find") or request.path.startswith("/auth/google/"):
  resp.headers.setdefault("X-Robots-Tag","noindex, nofollow")
 resp.headers.setdefault("X-Content-Type-Options","nosniff")
 resp.headers.setdefault("X-Frame-Options","DENY")
 resp.headers.setdefault("Referrer-Policy","strict-origin-when-cross-origin")
 resp.headers.setdefault("Cross-Origin-Resource-Policy","same-origin")
 resp.headers.setdefault("Permissions-Policy","camera=(), geolocation=(), microphone=(self)")
 resp.headers.setdefault("Content-Security-Policy","frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'")
 resp.headers.setdefault("Strict-Transport-Security","max-age=31536000")
 if resp.mimetype=="text/html":
  resp.headers.setdefault("Cache-Control","private, no-store, max-age=0")
 return resp

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
if not READ_ONLY_BOOT:
 init()
 sql("ALTER TABLE members ADD COLUMN IF NOT EXISTS google_sub TEXT UNIQUE")
 sql("CREATE UNIQUE INDEX IF NOT EXISTS members_google_sub_unique ON members(google_sub) WHERE google_sub IS NOT NULL")
 sql("""CREATE TABLE IF NOT EXISTS login_failures (
 fingerprint TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
 )""")
 sql("CREATE INDEX IF NOT EXISTS login_failures_lookup ON login_failures(fingerprint,created_at DESC)")

def auth_fingerprint(email):
 raw=(email+"|"+(request.remote_addr or "")).encode("utf-8")
 return hmac.new(app.secret_key.encode("utf-8"),raw,hashlib.sha256).hexdigest()

def is_rate_limited(fingerprint):
 count=sql("SELECT COUNT(*) AS n FROM login_failures WHERE fingerprint=%s AND created_at>NOW()-INTERVAL '15 minutes'",(fingerprint,),True)[0]["n"]
 return count>=8

def hashpw(p,s=None):
 s=s or secrets.token_hex(16)
 return s+":"+hashlib.pbkdf2_hmac("sha256",p.encode(),bytes.fromhex(s),250000).hex()
def verify(p,h):
 try: return hmac.compare_digest(hashpw(p,h.split(":")[0]),h)
 except: return False
def me():
 if session.get("auth_method")!="google" or "uid" not in session:return None
 rows=sql("SELECT * FROM members WHERE id=%s",(session["uid"],),True)
 return rows[0] if rows else None
def admin(u):return bool(u and u["email"].lower()==os.getenv("ADMIN_EMAIL","").lower() and u["approved"])
def token():return session.setdefault("csrf",secrets.token_urlsafe(24))
def guard():
 saved=session.get("csrf")
 submitted=request.form.get("csrf","")
 if not saved or not submitted or not hmac.compare_digest(submitted,saved):abort(403)
def esc(v):return html.escape(str(v or ""),quote=True)
def field(name,label,type="text",required=False,value=""):
 return f'<label>{esc(label)}<input name="{esc(name)}" type="{type}" value="{esc(value)}" maxlength="200" {"required" if required else ""}></label>'
def view(title,body):
 u=me(); nav='<a href="/">🏠 בית</a> <a href="/memorials">🕯️ הנצחה</a> <a href="/archive">📜 ארכיון</a> <a href="/find">🔎 איתור</a> <a href="/photos">📷 תמונות</a> <a href="/feed">📸 סיפורים</a> <a href="/help">❔ עזרה</a> '
 if u:
  nav+='<a href="/new-post">📸 שתפו סיפור או אירוע</a> <a href="/my-posts">📝 הפרסומים שלי</a> <a href="/chats">💬 צ׳אט</a> <a href="/invite">🤝 הזמנת חברים</a> <a href="/directory">👥 מדריך</a> <a href="/profile">הפרופיל שלי</a> '
  if admin(u):nav+='<a href="/admin">ניהול</a> <a href="/admin/accessibility">דיווחי נגישות</a> <a href="/community/moderation">אישור פרסומים</a> '
  nav+='<a href="/logout">יציאה</a>'
 else:nav+='<a class="nav-register" href="/register">הצטרפות באמצעות Google</a> <a class="nav-login" href="/login">🔑 Google Sign-In</a>'
 return integrate_html(render_template_string("""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="קהילת יוצאי פלוגה ב׳ הקרנפים/ברקן גדוד 46 חטיבה 401"><title>{{title}} | הקרנפים חוזרים לקשר</title><link rel="icon" href="/favicon.svg" type="image/svg+xml"><style>
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
</style></head><body><header><div class="logo">🦏 הקרנפים | ברקן</div><nav aria-label="ניווט ראשי">{{nav|safe}}</nav></header><main>{{body|safe}}</main><footer>יוזמה קהילתית עצמאית של יוצאי הפלוגה • אין קשר רשמי לצה״ל • פרטים אישיים מוסתרים כברירת מחדל · <a href="/accessibility">♿ נגישות</a> · <a href="/accessibility/report">דיווח על בעיית נגישות</a></footer></body></html>""",title=title,body=body,nav=nav),scripts_allowed=True)
def formwrap(x):return '<input type="hidden" name="csrf" value="'+token()+'">'+x
@app.route("/")
def home():
 return app.extensions["karnafim_portal"]["home"]()
@app.route("/favicon.svg")
@app.route("/favicon.ico")
def favicon():
 return Response('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#19372c"/><path fill="#d8eaa2" d="M14 17h13v30h-7V24h-6zm17 0h13v30h-7V24h-6zm17 0h6v30h-6z"/><path d="M8 51h48" stroke="#d8eaa2" stroke-width="3" stroke-linecap="round"/></svg>',mimetype="image/svg+xml",headers={"Cache-Control":"public, max-age=604800","X-Content-Type-Options":"nosniff"})
@app.route("/health")
def health():return {"ok":True,"service":"karnafim","access":("read_only" if READ_ONLY_BOOT else "community")}
@app.route("/status")
def public_status():
 available=google_ready()
 return view("מצב הקהילה",'<h1>מצב קהילת הקרנפים</h1><div class="card"><h2>חברות והרשאות</h2>'
  '<p>האתר הוא יוזמה עצמאית של יוצאי פלוגה ב׳ ואינו אתר רשמי של צה״ל או משרד הביטחון.</p>'
  '<p>הכניסה החדשה תתבצע באמצעות Google בלבד. Google מאמתת בעלות על חשבון Google, לא שירות צבאי. '
  'כל חבר יידרש לאישור נפרד של מנהל הקהילה לפני צפייה בתוכן הקהילתי ויצירת קשר.</p>'
  +('<p><a href="/login">לכניסה באמצעות Google</a></p>'
    if available else '<p><strong>התחברות Google עדיין אינה זמינה.</strong> היא תופעל רק לאחר השלמת בדיקת האבטחה והגדרות OAuth.</p>')
  +'</div>')

# Minimal privacy-preserving accessibility feedback: no public user directory, no messages to email.
if not READ_ONLY_BOOT:
 sql("""CREATE TABLE IF NOT EXISTS accessibility_reports(
 id BIGSERIAL PRIMARY KEY,
 fingerprint TEXT NOT NULL,
 description TEXT NOT NULL,
 reply_email TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'open',
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
 sql("CREATE INDEX IF NOT EXISTS accessibility_reports_recent ON accessibility_reports(fingerprint,created_at DESC)")

@app.route("/accessibility/report",methods=["GET","POST"])
def accessibility_report():
 if request.method=="POST":
  guard()
  if request.form.get("homepage","").strip():
   return view("תודה",'<p role="status">הפנייה נקלטה.</p>')  # Honeypot.
  description=request.form.get("description","").strip()[:1800]
  reply=(request.form.get("email","").strip().lower())[:160]
  if len(description)<12 or len(description)>1800 or (reply and ("@" not in reply or any(c in reply for c in "\r\n "))):
   return view("טופס לא תקין",'<p role="alert">יש להזין תיאור ברור של לפחות 12 תווים וכתובת דוא״ל תקינה אם בחרת למסור אותה.</p><a href="/accessibility/report">חזרה לטופס</a>'),400
  fingerprint=hmac.new(app.secret_key.encode("utf-8"),(request.remote_addr or "unknown").encode("utf-8"),hashlib.sha256).hexdigest()
  n=sql("SELECT COUNT(*) AS n FROM accessibility_reports WHERE fingerprint=%s AND created_at>NOW()-INTERVAL '1 hour'",(fingerprint,),True)[0]["n"]
  if n>=3:
   return view("מגבלת פניות",'<p role="alert">התקבלו מספר פניות בפרק זמן קצר. ניתן לנסות שוב במועד אחר.</p>'),429
  sql("INSERT INTO accessibility_reports(fingerprint,description,reply_email) VALUES(%s,%s,%s)",(fingerprint,description,reply))
  return view("תודה",'<div class="card" role="status"><h1>הפנייה נקלטה</h1><p>תיאור בעיית הנגישות נשמר למנהל האתר. פרטי הקשר אינם מוצגים לציבור.</p><p><a href="/">חזרה לדף הבית</a></p></div>')
 return view("דיווח על בעיית נגישות",
 '<h1>♿ דיווח על בעיית נגישות</h1><p>נתקלתם בתוכן לא קריא, בעיה בניווט במקלדת, בחסימה בהעלאת קבצים או בטופס שקשה להשתמש בו? ספרו לנו.</p>'
 '<form method="post" class="card">'+formwrap(
 '<label>תיאור הבעיה והעמוד שבו נתקלתם בה<textarea name="description" rows="6" required minlength="12" maxlength="1800" aria-describedby="help-description"></textarea></label>'
 '<p id="help-description">אפשר לציין סוג מכשיר וקורא מסך. אין לכתוב כאן סיסמה, מספר אישי או מידע רגיש.</p>'
 '<label>כתובת דוא״ל למענה (לא חובה)<input type="email" name="email" maxlength="160" autocomplete="email"></label>'
 '<div aria-hidden="true" style="position:absolute;left:-9999px"><label>השאירו שדה זה ריק<input name="homepage" tabindex="-1" autocomplete="off"></label></div>'
 '<button>שליחת דיווח למנהל</button>')+'</form>')

@app.route("/admin/accessibility",methods=["GET","POST"])
def admin_accessibility():
 u=me()
 if not admin(u):abort(403)
 if request.method=="POST":
  guard()
  report_id=request.form.get("id","")
  if not report_id.isdigit():abort(400)
  sql("UPDATE accessibility_reports SET status='resolved' WHERE id=%s",(int(report_id),))
  return redirect("/admin/accessibility")
 reports=sql("SELECT id,description,reply_email,created_at FROM accessibility_reports WHERE status='open' ORDER BY created_at DESC LIMIT 100",fetch=True)
 body='<h1>דיווחי נגישות שטרם טופלו</h1>'
 if not reports:body+='<p role="status">לא התקבלו דיווחים פתוחים.</p>'
 for r in reports:
  body+='<article class="card"><p>'+esc(r["description"])+'</p><p>דוא״ל למענה: '+esc(r["reply_email"] or "לא נמסר")+'</p>'
  body+='<form method="post">'+formwrap('<input type="hidden" name="id" value="'+str(r["id"])+'"><button>סימון כטופל</button>')+'</form></article>'
 return view("דיווחי נגישות",body)

@app.route("/accessibility")
def accessibility_page():
 return view("הצהרת נגישות",accessibility_statement_body(read_only=False))

@app.route("/help")
def help_center():
 return view("מרכז עזרה",'''<section aria-labelledby="help-heading"><h1 id="help-heading">❔ עזרה ושאלות נפוצות</h1>
<p>כל הפעולות באתר בעברית. אין צורך להשתמש ברשת חברתית כדי לשתף זיכרונות עם חברים שאושרו לקהילה.</p>
<h2>איך מצטרפים?</h2><p>פותחים חשבון בדף <a href="/register">ההרשמה</a>. מנהל הקהילה מאשר את הקשר לפלוגה בנפרד מאימות הדוא״ל. אם האתר מציג אזהרת אבטחה, אין להזין פרטי התחברות.</p>
<h2>איך מעלים תמונות, סיפור או אירוע?</h2><p>לאחר אישור החברות בוחרים <a href="/new-post">פרסום חדש</a>, סוג הפרסום, כותרת ותיאור. אפשר לצרף עד ארבעה קבצים. לתמונות מוגבלת העלאה עד 8MB לקובץ לפני הכיווץ; קובץ שמע עד 2MB וסרטון עד 8MB. החומרים נשמרים פרטיים עד אישור ביקורת התוכן.</p>
<h2>מי רואה את הסיפור שלי?</h2><p>רק חברי קהילה מאושרים יכולים לצפות בציר הזמן המאושר. המנהל יכול לראות גם פרסומים שממתינים לבדיקה. <a href="/my-posts">הפרסומים שלי</a> מציג גם תכנים פרטיים שהעלית.</p>
<h2>איך מוצאים חברים?</h2><p><a href="/directory">מדריך החברים</a> מציג רק חברים שאושרו ושבחרו להופיע בו. אפשר לשלוח בקשת קשר ולקיים שיחה פרטית רק לאחר שהמקבל אישר את הבקשה.</p>
<h2>מה בודק מנגנון ה־AI?</h2><p>הוא מסנן פרטים רגישים ותוכן בעייתי. תכנים לא חד־משמעיים נשמרים פרטיים. אם שירות ה־AI אינו מחובר, אי אפשר להבטיח פרסום אוטומטי. הבדיקה אינה מאשרת מי המצולם בתמונה או שהתקבלה הסכמה מכל מי שמופיע בה.</p>
<h2>פרטיות וזכויות</h2><p>לא מעלים מספר אישי צבאי, כתובות של חברים, מידע מסווג או תמונות של אחרים ללא רשות. ההצגה במדריך נתונה לבחירת המשתמש.</p>
<h2>שימוש נגיש באתר</h2><p>אפשר להשתמש במקלדת, בדילוג לתוכן הראשי ובאפשרויות התצוגה בראש העמוד. <a href="/accessibility">מידע על נגישות</a> · <a href="/accessibility/report">דיווח על בעיה</a>.</p>
</section>''')

@app.route("/about")
def about_public():
 return view("על הקהילה",'<h1>על הקרנפים | ברקן</h1><div class="card"><p>אתר מפגש עצמאי ליוצאי פלוגה ב׳, גדוד 46 ״שלח״, חטיבה 401, ובפרט מחזורי 2003–2006.</p><p>האתר אינו גורם רשמי של צה״ל ואינו מאמת אוטומטית זהות או שירות צבאי.</p></div>')

@app.route("/privacy")
def privacy_public():
 return view("מדיניות פרטיות",'<h1>פרטיות בקהילה</h1><div class="card"><p>בעת חידוש הפעילות ההתחברות תהיה דרך Google בלבד; האתר ישמור מזהה חשבון, שם ודוא״ל בהסכמה, וכן הודעות ותמונות שחברים בוחרים לשתף. סיסמאות מקומיות ישנות אינן משמשות עוד להתחברות. האתר משתמש בעוגיית התחברות מאובטחת.</p><p>חברות מאושרת ידנית; פרטי קשר אינם מפורסמים במדריך כברירת מחדל. פרופיל מופיע רק כאשר החבר בחר להציגו. פרסומים אישיים זמינים לחברים מאושרים לאחר ביקורת מנהל.</p><p>אפשר לשנות את הגדרות החשיפה או למחוק את החשבון דרך <a href="/profile">הפרופיל שלי</a> לאחר כניסה. אין להעלות פרטים או תמונות של אחרים ללא אישור.</p></div>')

@app.route("/safety")
def safety_public():
 return view("כללי בטיחות",'<h1>בטיחות ושיתוף אחראי</h1><div class="card"><p>יש להימנע ממספרים אישיים, פרטי קשר של אחרים ומידע רגיש על שירות צבאי.</p><p>תמונות וסיפורים עוברים אישור לפני פרסום. תמונה הנוגעת להנצחה נבדקת בנפרד לאישור מקור וזכויות שימוש. אישור תמונה אינו אימות אוטומטי של זהות המצולם.</p><p>אם הדפדפן מציג אזהרת אבטחה, אין לעקוף אותה או להזין פרטים עד בירור הבעיה.</p></div>')

@app.route("/register",methods=["GET","POST"])
def register():
 if request.method=="POST":abort(405)
 return view("הצטרפות לקהילת הקרנפים",
  '<h1>🦏 הצטרפות לקהילה</h1><div class="card">'
  '<p>ההרשמה מתבצעת באמצעות חשבון Google מאומת בלבד. '
  'לא נבקש ממך ליצור סיסמה חדשה באתר.</p>'
  '<p>Google אינה מאמתת שירות בפלוגה. אחרי ההתחברות תתבקש להסכים לשמירת פרטי הקשר '
  'ולאחר מכן להמתין לאישור מנהל הקהילה.</p>'
  +('<a class="btn" href="/auth/google/start">המשך עם Google</a>'
    if google_ready() else '<div class="note" role="status">ההצטרפות עדיין אינה פעילה עד לסיום בדיקת האבטחה והגדרת Google OAuth.</div>')
  +'</div><p>הקהילה עצמאית ואינה מייצגת את צה״ל או משרד הביטחון.</p>')

@app.route("/login",methods=["GET","POST"])
def login():
 if request.method=="POST":abort(405)
 destination=request.args.get("next","/")
 from google_identity import RETURN_PATHS
 destination=destination if destination in RETURN_PATHS else "/"
 if me():return redirect(destination,code=303)
 href="/auth/google/start?next="+destination
 return view("כניסה לקהילת הקרנפים",
  '<h1>🔐 כניסה באמצעות Google</h1><div class="card">'
  '<p>התחברות לחשבון Google המאומת שלך — אין צורך בסיסמה נוספת לאתר הקרנפים.</p>'
  '<p><strong>חשוב:</strong> אישור זהות Google אינו אישור חברות בפלוגת הקרנפים. '
  'הגישה למדריך, להודעות ולהעלאת תמונות מותנית באישור מנהל הקהילה.</p>'
  +('<a class="btn" href="'+esc(href)+'">התחברות מאובטחת עם Google</a>'
    if google_ready() else '<div class="note" role="status">הכניסה אינה פעילה כרגע. חסרה הפעלת Google OAuth ואישור בטיחות האתר.</div>')
  +'</div><p>לא נבקש סיסמת Google בתוך אתר זה.</p>')

@app.route("/logout",methods=["GET","POST"])
def logout():
 if request.method=="POST":
  guard();session.clear();return redirect("/")
 if not me():return redirect("/")
 return view("התנתקות",'<h1>התנתקות מהחשבון</h1><form method="post">'+formwrap('<button>אישור התנתקות</button>')+'</form>')
@app.route("/directory")
def directory():
 u=me()
 if not u:return redirect("/login")
 if not u["approved"]:return view("ממתין לאישור",'<div class="card"><h2>בקשת ההצטרפות ממתינה לאישור</h2><p>בינתיים אפשר לצפות בארכיון המורשת, למצוא קבוצות חיפוש ולהזמין חברים.</p><a href="/archive">לארכיון</a> · <a href="/find">לאיתור חברים</a></div>')
 term=request.args.get("q","")[:80]
 records=sql("SELECT id,name,nickname,service_start,service_end,company,role,about,facebook_url,instagram_url,linkedin_url FROM members WHERE approved AND visible AND (name ILIKE %s OR nickname ILIKE %s) ORDER BY name LIMIT 100",('%'+term+'%','%'+term+'%'),True)
 def card_for(r):
  x='<div class="card"><h2>'+esc(r["name"])+'</h2><p>'+esc(r["nickname"])+' • '+esc(r["company"])+'</p><p class="muted">'+esc(r["service_start"])+'–'+esc(r["service_end"])+' | '+esc(r["role"])+'</p><p>'+esc(r["about"])+'</p><p><a href="/contact/'+str(r["id"])+'">שליחת בקשת קשר באתר</a></p>'
  for key,label in [("facebook_url","פייסבוק"),("instagram_url","אינסטגרם"),("linkedin_url","לינקדאין")]:
   if r[key]:x+='<a style="margin-left:12px" href="'+esc(r[key])+'" target="_blank" rel="noopener noreferrer">'+label+' ↗</a>'
  return x+'</div>'
 cards=''.join(card_for(r) for r in records)
 body='<h1>חברי הפלוגה</h1><p>חברים מאושרים שבחרו להופיע. קישור לרשת חברתית מוצג רק אם בעל הפרופיל הוסיף אותו מרצונו.</p><form method="get"><label for="directory-search">חיפוש חבר לפי שם או כינוי</label><input id="directory-search" name="q" value="'+esc(term)+'" placeholder="שם או כינוי מהשירות"><button>חיפוש</button></form><div class="grid">'+(cards or '<div class="card"><h2>אתם הראשונים!</h2><p>החברים עוד לא בחרו להופיע במדריך. בינתיים נסו חיפוש ברשתות או הזמינו חבר מהמחזור.</p><a href="/find">איתור ברשתות</a> · <a href="/invite">הזמנת חברים</a></div>')+'</div>'
 return view("מדריך חברים",body)

def social_link(value,site):
 from urllib.parse import urlsplit
 value=(value or "").strip()[:300]
 if not value:return ""
 try:
  u=urlsplit(value)
  host=(u.hostname or "").lower()
  hosts={"facebook_url":{"facebook.com","www.facebook.com","m.facebook.com"},"instagram_url":{"instagram.com","www.instagram.com"},"linkedin_url":{"linkedin.com","www.linkedin.com"}}
  if u.scheme!="https" or host not in hosts[site] or u.username or u.password:return ""
  return value
 except ValueError:return ""

@app.route("/profile",methods=["GET","POST"])
def profile():
 u=me()
 if not u:return redirect("/login")
 if request.method=="POST":
  guard()
  fb=social_link(request.form.get("facebook_url",""),"facebook_url")
  ig=social_link(request.form.get("instagram_url",""),"instagram_url")
  li=social_link(request.form.get("linkedin_url",""),"linkedin_url")
  sql("UPDATE members SET nickname=%s,about=%s,visible=%s,facebook_url=%s,instagram_url=%s,linkedin_url=%s WHERE id=%s",(request.form.get("nickname","")[:100],request.form.get("about","")[:1000],request.form.get("visible")=="on",fb,ig,li,u["id"]))
  return redirect("/profile")
 body='<h1>הפרופיל שלי</h1><p>מצב החשבון: '+("מאושר" if u["approved"] else "ממתין לאישור")+'</p><p>אתה בוחר אם להופיע במדריך. קישורים לרשתות החברתיות שלך הם אופציונליים ויוצגו רק אם בחרת להופיע.</p>'
 body+='<form method="post" class="card">'+formwrap(field("nickname","כינוי מהשירות",value=u["nickname"])+'<label>מה אתה זוכר מהפלוגה?<textarea name="about" maxlength="1000">'+esc(u["about"])+'</textarea></label>'+field("facebook_url","קישור לפרופיל פייסבוק שלי (אופציונלי)","url",value=u["facebook_url"])+field("instagram_url","קישור לפרופיל אינסטגרם שלי (אופציונלי)","url",value=u["instagram_url"])+field("linkedin_url","קישור לפרופיל לינקדאין שלי (אופציונלי)","url",value=u["linkedin_url"])+'<label><input style="display:inline;width:auto" type="checkbox" name="visible" '+("checked" if u["visible"] else "")+'> אני רוצה להופיע במדריך החברים</label><button>שמירת הפרופיל</button></form>')
 body+='<form action="/delete-account" method="post" onsubmit="return confirm(\'למחוק את החשבון והמידע לצמיתות?\')">'+formwrap('<button style="background:#f9d0ca">מחיקת החשבון שלי</button>')+'</form>'
 return view("פרופיל אישי",body)

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
@app.route("/inbox")
def inbox():
 return redirect("/chats")
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
def error(e):
 if READ_ONLY_BOOT:
  return Response("אירעה תקלה זמנית. נסו שוב מאוחר יותר.",status=500,mimetype="text/plain")
 return view("שגיאה","<p>אירעה תקלה זמנית. נסו שוב מאוחר יותר.</p>"),500

if not READ_ONLY_BOOT:
 sql("""CREATE TABLE IF NOT EXISTS memories(
 id BIGSERIAL PRIMARY KEY, author_id BIGINT REFERENCES members(id) ON DELETE CASCADE,
 title TEXT NOT NULL, story TEXT NOT NULL, year INTEGER,
 source_url TEXT NOT NULL DEFAULT '', approved BOOLEAN DEFAULT FALSE,
 created_at TIMESTAMPTZ DEFAULT NOW())""")
@app.route("/memories")
def memories():
 return redirect("/feed")
@app.route("/discover")
def discover():
 return redirect("/find")
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
 # Legacy local-password handling is retired; a Google account owns its password.
 return view("סיסמאות מנוהלות ב־Google",
  '<h1>אין סיסמה מקומית באתר הקרנפים</h1>'
  '<p>הכניסה מתבצעת דרך חשבון Google. אין כאן טופס לאיסוף או לשינוי סיסמאות.</p>'
  '<p>ניתן לנהל את סיסמת חשבון Google דרך הגדרות החשבון של Google בלבד.</p>'),410

# The public security-hold site is entirely static and must boot without DB/OAuth.
# In community mode the original migrations and route registration still run.
if not READ_ONLY_BOOT:
 install_google_login(app,sql,view,guard,formwrap,esc)
 from community_portal import install as install_portal
 install_portal(app,sql,view,me,admin,guard,formwrap,esc)
 from memorial_photos import setup as setup_memorial
 setup_memorial(app,sql,app.extensions["karnafim_portal"]["page"],me,admin,guard,formwrap)

if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))
