"""Karnafim / Barkan — independent, Hebrew RTL veterans community.

New application and database tables (b2_*). No Google social login, no shared
shop dependency, no external scripts. The original service is not modified.
"""
import hashlib
import hmac
import io
import os
import re
import secrets
from datetime import datetime, timezone
from functools import wraps
from html import escape
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from flask import Flask, Response, abort, g, redirect, request, send_file, session, url_for
from markupsafe import Markup
from PIL import Image, ImageOps, UnidentifiedImageError

BASE=Path(__file__).resolve().parent
app=Flask(__name__,static_folder=str(BASE/"static"))
CONFIGURED_SECRET=os.environ.get("BARKAN_SESSION_SECRET","").strip()
DB=os.environ.get("DATABASE_URL","").strip()
app.config.update(
    # An ephemeral key is acceptable only for a public read-only deployment.
    # Account login requires a durable configured secret and a database.
    SECRET_KEY=CONFIGURED_SECRET or secrets.token_urlsafe(48),
    SESSION_COOKIE_NAME="barkan_46_session",
    SESSION_COOKIE_SECURE=True,SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",PERMANENT_SESSION_LIFETIME=3600*6,
    MAX_CONTENT_LENGTH=32*1024*1024, MAX_FORM_MEMORY_SIZE=128*1024,
    TRUSTED_HOSTS=["karnafim-barkan-46.onrender.com","localhost","127.0.0.1"],
)
ORIGIN=os.environ.get("BARKAN_PUBLIC_ORIGIN","https://karnafim-barkan-46.onrender.com").rstrip("/")
# Public account forms are a separate switch. Never enable until the new origin
# passes live security checks and is no longer flagged by Safe Browsing.
PUBLIC_AUTH=(bool(CONFIGURED_SECRET and DB)
             and os.environ.get("BARKAN_PUBLIC_AUTH","0")=="1"
             and os.environ.get("BARKAN_SAFETY_RELEASE_APPROVED","0")=="1")
EMAIL_PROVIDER=os.environ.get("BARKAN_RESEND_API_KEY","")
MAIL_FROM=os.environ.get("BARKAN_MAIL_FROM","")
MAIL_READY=bool(EMAIL_PROVIDER.strip() and MAIL_FROM.strip())
ALLOW_SIGNUP=(PUBLIC_AUTH and os.environ.get("BARKAN_ALLOW_SIGNUP","0")=="1" and MAIL_READY)

def connect():
    return psycopg.connect(DB,row_factory=dict_row,connect_timeout=8)

def sql(query, params=(), one=False):
    with connect() as c:
        with c.cursor() as cur:
            cur.execute(query,params)
            return (cur.fetchone() if one else cur.fetchall()) if cur.description else None

def init():
    """Rebuild schema from scratch, preserve original account hashes as one-time seed."""
    with connect() as c:
        with c.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS b2_users(
                id BIGSERIAL PRIMARY KEY,name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,passhash TEXT NOT NULL,
                nickname TEXT NOT NULL DEFAULT '',unit_year TEXT NOT NULL DEFAULT '',
                about TEXT NOT NULL DEFAULT '',approved BOOLEAN NOT NULL DEFAULT FALSE,
                show_profile BOOLEAN NOT NULL DEFAULT FALSE,
                email_verified BOOLEAN NOT NULL DEFAULT FALSE,
                email_verification_required BOOLEAN NOT NULL DEFAULT FALSE,
                joined TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            cur.execute("""CREATE TABLE IF NOT EXISTS b2_tokens(
                user_id BIGINT PRIMARY KEY REFERENCES b2_users(id) ON DELETE CASCADE,
                digest CHAR(64) NOT NULL UNIQUE,expires TIMESTAMPTZ NOT NULL)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS b2_throttle(
                fingerprint TEXT NOT NULL,at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            cur.execute("CREATE INDEX IF NOT EXISTS b2_throttle_idx ON b2_throttle(fingerprint,at)")
            cur.execute("""CREATE TABLE IF NOT EXISTS b2_posts(
                id BIGSERIAL PRIMARY KEY,author BIGINT NOT NULL REFERENCES b2_users(id),
                title TEXT NOT NULL,body TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'story',
                year_text TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                created TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            cur.execute("CREATE INDEX IF NOT EXISTS b2_posts_status_idx ON b2_posts(status,created DESC)")
            cur.execute("""CREATE TABLE IF NOT EXISTS b2_media(
                id BIGSERIAL PRIMARY KEY,post_id BIGINT REFERENCES b2_posts(id) ON DELETE CASCADE,
                owner BIGINT NOT NULL REFERENCES b2_users(id),
                recipient BIGINT REFERENCES b2_users(id),
                mime TEXT NOT NULL,kind TEXT NOT NULL,body BYTEA NOT NULL,
                length INTEGER NOT NULL,created TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            cur.execute("""CREATE TABLE IF NOT EXISTS b2_messages(
                id BIGSERIAL PRIMARY KEY,sender BIGINT NOT NULL REFERENCES b2_users(id),
                recipient BIGINT NOT NULL REFERENCES b2_users(id),
                text TEXT NOT NULL DEFAULT '',
                media_id BIGINT REFERENCES b2_media(id),
                created TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            cur.execute("CREATE INDEX IF NOT EXISTS b2_messages_pair_idx ON b2_messages(sender,recipient,created)")
            # Preserve existing members' hashes without copying messages or passwords
            # into source code. The copied Neon branch is a rollback snapshot.
            cur.execute("""SELECT to_regclass('public.members') IS NOT NULL AS has_legacy_members""")
            if cur.fetchone()["has_legacy_members"]:
                cur.execute("""INSERT INTO b2_users(name,email,passhash,nickname,approved,show_profile,
                                  email_verified,email_verification_required)
                    SELECT name,lower(email),password,COALESCE(nickname,''),approved,
                           FALSE,FALSE,FALSE FROM members
                    WHERE email IS NOT NULL AND password IS NOT NULL
                    ON CONFLICT(email) DO NOTHING""")
if DB:
    init()

def e(value): return escape(str(value if value is not None else ""),quote=True)

def hashpw(p, salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+":"+hashlib.pbkdf2_hmac("sha256",p.encode(),bytes.fromhex(salt),250000).hex()

def checkpw(p, hashed):
    try: return hmac.compare_digest(hashpw(p,hashed.split(":")[0]),hashed)
    except (ValueError,TypeError,IndexError):return False

def finger(label):
    key=app.secret_key.encode()
    ip=request.remote_addr or "unknown"
    return hmac.new(key,(label+"|"+ip).encode(),hashlib.sha256).hexdigest()

def limit(label, maximum=8, minutes=15):
    fp=finger(label)
    with connect() as c:
        with c.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM b2_throttle WHERE fingerprint=%s AND at>NOW()-(%s * INTERVAL '1 minute')",(fp,minutes))
            if cur.fetchone()["n"]>=maximum:abort(429)
            cur.execute("INSERT INTO b2_throttle(fingerprint) VALUES(%s)",(fp,))

def current():
    uid=session.get("uid")
    if not isinstance(uid,int):return None
    return sql("SELECT id,name,email,approved,show_profile,email_verified,email_verification_required,nickname,unit_year,about FROM b2_users WHERE id=%s",(uid,),True)

@app.before_request
def before():
    # Optional canonical handoff: preserve the independent health check, but
    # forward public GET navigation to the sole community address.
    if (os.environ.get("BARKAN_CANONICAL_HANDOFF","0")=="1"
            and request.method=="GET" and request.path!="/health"):
        target="https://karnafim-community-46.onrender.com"+request.path
        if request.query_string:
            target+="?"+request.query_string.decode("latin-1")
        return redirect(target,code=302)
    if "csrf" not in session:session["csrf"]=secrets.token_urlsafe(32)
    g.user=current() if PUBLIC_AUTH and session.get("uid") is not None else None

def require_login(fn):
    @wraps(fn)
    def inner(*args,**kwargs):
        if not PUBLIC_AUTH:abort(503)
        if g.user is None:return redirect("/login",code=303)
        return fn(*args,**kwargs)
    return inner

def require_approved(fn):
    @wraps(fn)
    @require_login
    def inner(*args,**kwargs):
        if not g.user["approved"]:abort(403)
        return fn(*args,**kwargs)
    return inner

def admin():
    return bool(g.user and g.user["approved"] and
                g.user["email"].lower()==os.environ.get("BARKAN_ADMIN_EMAIL","").lower())

def protect():
    if not hmac.compare_digest(str(request.form.get("csrf","")),session.get("csrf","")):abort(400)

def button_form(body,action,extra=""):
    return '<form method="post" action="'+e(action)+'" '+extra+'><input type="hidden" name="csrf" value="'+e(session["csrf"])+'">'+body+'</form>'

def password_control(name, autocomplete):
    """Consistent accessible password field without external scripts."""
    return ('<div class="password-field"><label for="account-password">סיסמה</label>'
            '<span class="password-wrap">'
            '<input id="account-password" type="password" name="'+name+'" '
            + ('minlength="12" ' if autocomplete=="new-password" else '') +
            'maxlength="200" autocomplete="'+autocomplete+'" required '
            'aria-describedby="password-help">'
            '<button type="button" class="password-toggle" data-password-toggle '
            'aria-controls="account-password" aria-pressed="false" '
            'aria-label="הצגת הסיסמה">הצגה</button></span></div>')

def layout(title,body):
    u=g.user
    menu=[("/","בית"),("/heritage","מורשת"),("/memorial","הנצחה"),("/photos","תמונות"),("/about","על הקהילה"),("/help","עזרה")]
    if PUBLIC_AUTH and u:
        menu += [("/feed","הקהילה"),("/find","איתור חברים"),("/new","שיתוף זיכרון"),("/my-posts","הפרסומים שלי"),("/inbox","הודעות"),("/profile","הפרופיל שלי")]
        if admin():menu += [("/moderation","בקרת פרסומים"),("/members","אישור חברים")]
    elif PUBLIC_AUTH:
        menu += [("/login","כניסה")]
        if ALLOW_SIGNUP:menu += [("/signup","הצטרפות")]
    nav=''.join('<a href="'+link+'"'+(' aria-current="page"' if request.path==link else '')+'>'+label+'</a>' for link,label in menu)
    banner=('<div class="banner">האתר החדש נמצא בהכנת מערכת החברים ובבדיקת אבטחה. '
            'תכני המורשת זמינים כעת; הרשמה והתחברות ייפתחו רק לאחר אימות בטיחות האתר.</div>') if not PUBLIC_AUTH else ''
    html='''<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#142e27">
<meta name="description" content="קהילת הקרנפים / ברקן — מורשת פלוגה ב, גדוד 46, חטיבה 401">
<link rel="stylesheet" href="/static/site.css"><title>'''+e(title)+''' · הקרנפים / ברקן</title></head>
<body><a class="skip" href="#main">דלג לתוכן</a>
<header><div class="bar"><a class="logo" href="/">◈ הקרנפים <span>ברקן · פלוגה ב׳</span></a>
<button id="toggle" type="button" aria-expanded="false" aria-controls="nav">☰ תפריט</button>
<nav id="nav" aria-label="ניווט ראשי">'''+nav+'''</nav></div></header>
<main id="main" tabindex="-1">'''+banner+str(body)+'''</main>
<footer><div><strong>הקרנפים / ברקן</strong><p>מיזם עצמאי של יוצאי פלוגה ב׳, גדוד 46, חטיבה 401. אינו אתר רשמי של צה״ל.</p></div>
<nav aria-label="קישורי מדיניות"><a href="/privacy">פרטיות</a><a href="/terms">תנאי שימוש</a><a href="/safety">בטיחות</a><a href="/status">מצב המערכת</a></nav></footer>
<script src="/static/site.js" defer></script></body></html>'''
    return Response(html,mimetype="text/html")

@app.after_request
def headers(resp):
    resp.headers.setdefault("X-Content-Type-Options","nosniff")
    resp.headers.setdefault("X-Frame-Options","DENY")
    resp.headers.setdefault("Referrer-Policy","no-referrer")
    resp.headers.setdefault("Permissions-Policy","camera=(),geolocation=(),microphone=(self)")
    resp.headers.setdefault("Cross-Origin-Resource-Policy","same-origin")
    resp.headers.setdefault("Content-Security-Policy","default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
    resp.headers.setdefault("Strict-Transport-Security","max-age=31536000")
    if resp.mimetype=="text/html":resp.headers.setdefault("Cache-Control","no-store")
    if request.path in ("/login","/signup","/verify-email","/profile","/inbox","/find") or request.path.startswith("/media/"):
        resp.headers["X-Robots-Tag"]="noindex,nofollow"
    return resp

@app.get("/health")
def health():
    # Safe public liveness endpoint. No secrets, account data or raw DB errors.
    return {"status":"ok","generation":"new-build","auth_enabled":PUBLIC_AUTH,
            "database_configured":bool(DB),
            "signup_enabled":ALLOW_SIGNUP,"email_sender_configured":MAIL_READY},200

@app.get("/ready")
def ready():
    # Readiness is distinct from liveness: a configured URL is not proof
    # that the database is reachable or the member schema is provisioned.
    # Never return connection strings, hostnames, credentials or SQL errors.
    if not DB:
        return {"status":"not_ready","database":"unconfigured",
                "member_portal":"closed"},503
    try:
        with connect() as c:
            with c.cursor() as cur:
                cur.execute("""SELECT
                    to_regclass('public.b2_users') IS NOT NULL AS users,
                    to_regclass('public.b2_posts') IS NOT NULL AS posts,
                    to_regclass('public.b2_media') IS NOT NULL AS media,
                    to_regclass('public.b2_messages') IS NOT NULL AS messages,
                    to_regclass('public.b2_tokens') IS NOT NULL AS tokens""")
                schema=cur.fetchone()
        all_ready=all(bool(schema[key]) for key in
                      ("users","posts","media","messages","tokens"))
    except (psycopg.Error, OSError, TimeoutError):
        all_ready=False
    if not all_ready:
        return {"status":"not_ready","database":"unavailable",
                "member_portal":"closed"},503
    return {"status":"ready","database":"available",
            "member_portal":"enabled" if PUBLIC_AUTH else "closed",
            "signup":"enabled" if ALLOW_SIGNUP else "closed"},200

@app.get("/")
def home():
    return layout("בית",'''<section class="hero"><div class="eyebrow">חטיבה 401 · גדוד 46 · פלוגה ב׳</div>
<h1>יש קשרים<br><em>שלא משתחררים.</em></h1><p>בית אחד לחברים מהשירות, לזיכרונות, לתמונות, למורשת ולהנצחת האנשים שאיתם חלקנו דרך.</p>
<div class="hero-actions"><a class="primary" href="/heritage">לסיפורי הפלוגה</a><a class="outline" href="/memorial">לזיכרון ולהנצחה</a></div>
<div class="hero-index">2003—2006 <span>ומעבר לשנים</span></div></section>
<section class="intro"><span class="tag">הבית של הפלוגה</span><h2>החברות נשארת. עכשיו יש לה מקום.</h2>
<p>מיזם עצמאי לחידוש הקשר בין יוצאי הקרנפים, שנקראו בהמשך ברקן, ולהקמת ארכיון שיתופי מכבד.</p></section>
<section class="tiles"><a href="/heritage"><span>01 / הסיפור שלנו</span><h3>ארכיון ומורשת</h3><p>היחידה, השנים, הזיכרונות והסיפורים שעיצבו אותנו.</p><b>כניסה לארכיון ←</b></a>
<a href="/memorial"><span>02 / תמיד איתנו</span><h3>הנצחה וזיכרון</h3><p>מקום מכבד לזכור את החברים ואת המחיר שנשאו.</p><b>למרחב ההנצחה ←</b></a>
<a href="/photos"><span>03 / הרגעים הקטנים</span><h3>תמונות וזיכרונות</h3><p>שוב ביחד, גם דרך האלבומים והסיפורים.</p><b>לגלריה ←</b></a></section>''')

@app.get("/heritage")
def heritage():
    return layout("ארכיון ומורשת",'''<div class="pagehead"><span class="tag">מורשת</span><h1>הסיפור שלנו</h1><p>פלוגה ב׳ — הקרנפים, לימים ברקן; גדוד 46 ״שלח״, חטיבה 401.</p></div>
<section class="story"><h2>יותר משנים על ציר הזמן</h2><p>האתר נולד מתוך רצון לשמר את החברות בין יוצאי הפלוגה, למצוא מחדש את החברים ולשתף סיפורי שירות ממקור ראשון.</p>
<p>תאריכי שירות, מסמכים ותצלומים יתווספו בהדרגה עם הסכמה, ציון מקור ובדיקת דיוק היסטורי. אין כאן טענה לרישום רשמי של צה״ל.</p></section>
<section class="timeline"><div><b>2003</b><h3>ראשית מחזורי המפגש</h3><p>יוצאי הפלוגה ממחזורי 2003–2006 מתאחדים סביב הזיכרון המשותף.</p></div>
<div><b>2006</b><h3>השנים שנשארו איתנו</h3><p>הקרבות, החברות והזיכרונות — עם מקום לתיעוד מכבד של כל סיפור מאומת.</p></div>
<div><b>היום</b><h3>קהילה חדשה</h3><p>אתר עצמאי שמאפשר לבוגרים לשוב וליצור קשר ולשמור מורשת לדורות הבאים.</p></div></section>''')

@app.get("/memorial")
def memorial():
    """Verified public memorial records; no copying of third-party portraits."""
    force = [
        ("רס״ן בניה ריין ז״ל", "מפקד כוח בניה", "https://www.izkor.gov.il/בניה%20ריין/en_f5ccba845584f96f9b9334cf335d2e78/"),
        ("סמ״ר אורי גרוסמן ז״ל", "תותחן ומפקד טנק בכוח בניה", "https://www.izkor.gov.il/אורי%20גרוסמן/en_f53b79619b3f27184812b11f14e635a8/"),
        ("סמ״ר אדם גורן ז״ל", "טען־קשר בכוח בניה", "https://www.izkor.gov.il/אדם%20גורן/en_e6446f8f52c2b18e0ec560602482bdda"),
        ("סמ״ר אלכסנדר (סשה) בונימוביץ׳ ז״ל", "נהג הטנק בכוח בניה", "https://www.izkor.gov.il/אלכסנדר%20בונימוביץ/en_34b2955a02b6a81f8ba932dbf6228e61/"),
    ]
    def memorial_card(name,role,date,iso,source):
        return ('<article class="memorial"><div class="candle" aria-hidden="true">✦</div>'
                '<h3>'+e(name)+'</h3><p>'+e(role)+'</p>'
                '<p><time datetime="'+e(iso)+'">'+e(date)+'</time></p>'
                '<a href="'+e(source)+'" target="_blank" rel="noopener noreferrer"'
                ' aria-label="סיפור ההנצחה הרשמי של '+e(name)+'">סיפור החיים באתר יזכור</a></article>')
    cards=''.join(memorial_card(name,role,"12.8.2006","2006-08-12",source) for name,role,source in force)
    yoni=memorial_card("סמל יהונתן (יוני) שרעבי ז״ל",
                       "תותחן מרכבה סימן 4 · פלוגה ב׳ הקרנפים, גדוד 46",
                       "3.8.2006","2006-08-03",
                       "https://www.izkor.gov.il/יהונתן%20שרעבי/en_53e66dd727188835acbe02a1f641a882")
    return layout("הנצחה",
        '<div class="pagehead solemn"><span class="tag">לזכור בכבוד</span>'
        '<h1>החברים שתמיד איתנו</h1><p>הנצחה מכבדת המבוססת על רשומות אתר יזכור של משרד הביטחון.'
        'תצלומים אישיים וסיפורי משפחות יפורסמו רק בכפוף לזכויות ולהסכמות מתאימות.</p></div>'
        '<section class="story"><h2>כוח בניה — גדוד 46</h2>'
        '<p>ב־12 באוגוסט 2006 נפלו ארבעת אנשי הצוות בדרכם למשימת חילוץ נוספת בלבנון.'
        'אנו זוכרים את כל אנשי הצוות יחד.</p></section>'
        '<section class="memories" aria-label="הנצחת ארבעת אנשי כוח בניה">'+cards+'</section>'
        '<section class="story"><h2>פלוגה ב׳ — לזכר יוני שרעבי</h2>'
        '<p>יהונתן (יוני) שרעבי שירת בפלוגה ב׳ ״הקרנפים״ כתותחן טנק מרכבה סימן 4.'
        ' הוא נפל בקרב בלבנון ב־3 באוגוסט 2006, והוא בן 20.</p></section>'
        '<section class="memories" aria-label="הנצחת יהונתן שרעבי">'+yoni+'</section>'
        '<div class="note">המידע ההיסטורי מקושר לעמודי הנצחה רשמיים.'
        ' יש לכבד את פרטיות המשפחות לפני פרסום תמונות או סיפורים אישיים.</div>')

@app.get("/photos")
def photos():
    intro='<div class="pagehead"><span class="tag">אלבום הפלוגה</span><h1>כל תמונה מחזירה רגע</h1><p>רק תמונות שאושרו לפרסום מוצגות לחברים מאושרים.</p></div>'
    if not PUBLIC_AUTH or not g.user or not g.user["approved"]:
        return layout("תמונות",intro+'<section class="empty-photo"><h2>אלבום החברים פרטי</h2><p>תמונות מאושרות זמינות רק לחברי הקהילה שאושרו.</p></section>')
    rows=sql("""SELECT f.id,p.title,p.year_text,u.name
        FROM b2_media f JOIN b2_posts p ON p.id=f.post_id
        JOIN b2_users u ON u.id=p.author
        WHERE f.kind='image' AND p.status='published' AND u.approved=TRUE
        ORDER BY p.created DESC,f.id DESC LIMIT 80""")
    tiles=''.join('<article class="post">'+media_html(r["id"],"image")+
        '<h2>'+e(r["title"])+'</h2><p>'+e(r["name"])+' · '+e(r["year_text"])+'</p></article>'
        for r in rows)
    return layout("תמונות",intro+('<section class="media-grid">'+tiles+'</section>' if tiles else
        '<section class="empty-photo"><h2>עדיין אין תמונות מאושרות</h2><p>תמונות חדשות יופיעו כאן לאחר בדיקת מנהל ואישור פרסום.</p><a href="/new">העלאת זיכרון</a></section>'))

@app.get("/about")
def about():
    return layout("על הקהילה",'''<div class="pagehead"><span class="tag">מי אנחנו</span><h1>הקרנפים / ברקן</h1><p>קהילת ותיקים עצמאית לבוגרי פלוגה ב׳, גדוד 46, חטיבה 401.</p></div>
<section class="story"><h2>המטרה</h2><p>לחדש קשרים, לאתר חברים, לשתף סיפורים ולשמור את המורשת בדרך מכבדת ובטוחה.</p>
<p>השתתפות מבוססת על הסכמת המשתתפים; אין גישה לפרופילים פרטיים ברשתות החברתיות ללא הרשאה ואין הבטחה לזהות מאומתת על סמך שם בלבד.</p></section>''')

@app.get("/help")
def help_page():
    return layout("עזרה",'''<div class="pagehead"><h1>שאלות ועזרה</h1></div><section class="story">
<h2>איך מצטרפים?</h2><p>עם פתיחת ההרשמה, בוחרים כתובת דוא״ל וסיסמה. החברות מתאשרת בידי מנהל, והפרסומים עוברים ביקורת לפני פרסום.</p>
<h2>אפשר לשלוח תמונות?</h2><p>כן, עד ארבעה קבצים לכל פרסום. העלאות נשארות פרטיות עד אישור.</p>
<h2>האם הפרטים שלי מוצגים?</h2><p>לא. פרופיל חבר מופיע במדריך רק אם אושרה חברותו והוא בחר בכך.</p>
<h2>זהו אתר רשמי?</h2><p>לא. זהו מיזם קהילתי עצמאי.</p></section>''')

@app.get("/privacy")
def privacy():
    return layout("פרטיות",'''<div class="pagehead"><h1>פרטיות</h1></div><section class="story"><p>ההרשמה דורשת שם, דוא״ל וסיסמה שממנה נשמר גיבוב בלבד. כתובות המייל אינן חשופות לחברים אחרים. פרסומים פרטיים והודעות מוגנים בהרשאות.</p><p>פרופילים אינם מופיעים במדריך כברירת מחדל. הבעלים יוכל לבקש להסיר תוכן וחשבון. אין להשתמש במידע ליצירת קשר מחוץ לקהילה ללא רשות.</p></section>''')

@app.get("/terms")
def terms():
    return layout("תנאי שימוש",'''<div class="pagehead"><h1>תנאי שימוש</h1></div><section class="story"><p>הקהילה מיועדת ליוצאי הפלוגה ולחברים שאושרו. נא לפרסם תוכן שיש לכם זכויות לשתף, להגן על פרטיות אחרים ולהימנע מדברי הסתה, הטרדה, מידע צבאי רגיש או התחזות.</p><p>מפעיל האתר רשאי להשהות פרסומים מחשש להפרת מדיניות. זהו מיזם עצמאי שאינו פועל מטעם צה״ל.</p></section>''')

@app.get("/safety")
def safety():
    return layout("בטיחות ואבטחה",'''<div class="pagehead"><h1>בטיחות ואבטחה</h1></div><section class="story"><p>המערכת החדשה אינה כוללת Google Sign-In ואינה מחברת חשבונות חברים לחנות מסחרית. כל פרסום אישי נבדק לפני הצגתו לחברים.</p><p>כל עוד קיימת אזהרת דפדפן בכתובת כלשהי, אין לעקוף אותה או להזין פרטי גישה.</p></section>''')

@app.get("/status")
def status():
    return layout("מצב המערכת",'<div class="pagehead"><h1>מצב המערכת</h1></div><section class="story"><p>אתר מורשת חדש: פעיל. מערכת חברים: '+("פעילה." if PUBLIC_AUTH else "מושהית עד השלמת בדיקות אבטחה.")+'</p><p>אימות דוא״ל: '+("הוגדר ספק HTTPS; אימות המסירה עדיין נדרש." if MAIL_READY else "אין ספק משלוח מאומת.")+'</p><p>הכתובת הקודמת נשמרה לקריאה בלבד ולא אוספת סיסמאות.</p></section>')

@app.route("/signup",methods=["GET","POST"])
def signup():
    # New members must verify email before their password can be used.
    # Do not collect credentials if an email sender is not configured.
    if not ALLOW_SIGNUP:abort(503)
    if request.method=="POST":
        protect();limit("signup",4,60)
        if request.form.get("agree")!="yes" or request.form.get("website"):abort(400)
        name=request.form.get("name","").strip()[:90]
        email=request.form.get("email","").strip().lower()[:200]
        password=request.form.get("password","")
        if len(name)<2 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email) or not 12<=len(password)<=200:
            return layout("הרשמה",'<div class="note error">יש להזין שם, דוא״ל תקין וסיסמה בת 12 תווים לפחות.</div>'),400
        with connect() as c:
            with c.cursor() as cur:
                try:
                    cur.execute("""INSERT INTO b2_users(name,email,passhash,email_verification_required)
                        VALUES(%s,%s,%s,%s) RETURNING id""",(name,email,hashpw(password),True))
                    uid=cur.fetchone()["id"]
                except psycopg.errors.UniqueViolation:
                    c.rollback()
                    return layout("הרשמה",'<div class="note">אם הבקשה כבר קיימת, אין צורך להגיש אותה שוב.</div>')
        if not send_verification(email,uid):
            return layout("משלוח אימות",'<div class="pagehead"><h1>ההרשמה נשמרה, אבל המייל לא נשלח</h1><p>אפשר לנסות שוב דרך שליחת אימות מחדש. החשבון חסום לכניסה עד אימות הכתובת.</p><a href="/resend-verification" class="primary">שליחת אימות מחדש</a></div>'),503
        return layout("בקשת הצטרפות",'<div class="pagehead"><h1>בקשת ההצטרפות נשמרה</h1><p>הודעת האימות התקבלה במערכת השליחה. יש לאמת את הדוא״ל לפני הכניסה לחשבון.</p><a class="primary" href="/login">מעבר לכניסה</a></div>')
    return layout("הרשמה",'<section class="auth-page"><div class="pagehead"><span class="tag">חברות בקהילה</span><h1>מצטרפים לקרנפים</h1><p>חשבון אישי ומאובטח ליוצאי פלוגה ב׳. לאחר אימות כתובת הדוא״ל, בקשת החברות תיבדק לפני גישה לתכנים של חברים.</p></div><div class="auth-trust"><span>🔒 חיבור מוצפן</span><span>✉ אימות דוא״ל</span><span>◈ קהילה לחברים מאושרים</span></div>'+
        button_form('<label>שם מלא<input name="name" required maxlength="90" autocomplete="name" placeholder="איך קוראים לך?"></label><label>כתובת דוא״ל<input name="email" type="email" inputmode="email" dir="ltr" required autocomplete="email" placeholder="you@example.com"></label>' + password_control("password","new-password") + '<p id="password-help" class="muted">לפחות 12 תווים. מומלץ להשתמש בסיסמה ייחודית.</p><input name="website" tabindex="-1" class="honeypot" aria-hidden="true"><label class="check"><input type="checkbox" name="agree" value="yes" required> אני מסכים לשמירת הפרטים לצורך קבלה לקהילה</label><button class="primary">שליחת בקשת הצטרפות</button>','/signup','class="formcard"')+'</section>')

def send_verification(email,uid):
    if not MAIL_READY:return False
    import json
    from urllib.request import Request,urlopen
    token=secrets.token_urlsafe(36)
    with connect() as c:
        with c.cursor() as cur:
            cur.execute("""INSERT INTO b2_tokens(user_id,digest,expires) VALUES(%s,%s,NOW()+INTERVAL '24 hours')
                ON CONFLICT(user_id) DO UPDATE SET digest=EXCLUDED.digest,expires=EXCLUDED.expires""",
                (uid,hashlib.sha256(token.encode()).hexdigest()))
    link=ORIGIN+"/verify-email?token="+token
    req=Request("https://api.resend.com/emails",data=json.dumps({
        "from":MAIL_FROM,"to":[email],"subject":"אימות דוא״ל — הקרנפים / ברקן",
        "html":'<p dir="rtl">אמתו את הכתובת: <a href="'+e(link)+'">קישור אימות</a>. הקישור תקף 24 שעות.</p>'
    }).encode(),headers={"Authorization":"Bearer "+EMAIL_PROVIDER,"Content-Type":"application/json"},method="POST")
    try:
        with urlopen(req,timeout=7) as result:return result.status in (200,201,202)
    except (OSError,TimeoutError):return False

@app.route("/resend-verification",methods=["GET","POST"])
def resend_verification():
    if not ALLOW_SIGNUP:abort(503)
    if request.method=="POST":
        protect()
        limit("resend-general",10,60)
        email=request.form.get("email","").lower().strip()[:200]
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email):abort(400)
        limit("resend:"+email,3,60)
        account=sql("""SELECT id FROM b2_users
            WHERE lower(email)=%s AND email_verification_required=TRUE""",(email,),True)
        if account:send_verification(email,account["id"])
        return layout("בקשת אימות",'<div class="pagehead"><h1>הבקשה נבדקה</h1><p>אם יש חשבון שממתין לאימות ושירות המיילים קיבל את ההודעה, יישלח קישור חדש. אפשר גם לבדוק בדואר הזבל.</p></div>')
    return layout("שליחת אימות מחדש",'<div class="pagehead"><h1>שליחת אימות מחדש</h1></div>'+
        button_form('<label>כתובת הדוא״ל שלך<input type="email" name="email" autocomplete="email" required></label><button class="primary">בקשת קישור אימות</button>','/resend-verification','class="formcard"'))

@app.route("/verify-email",methods=["GET","POST"])
def verify_email():
    if not PUBLIC_AUTH:abort(503)
    token=request.values.get("token","")
    if not re.fullmatch(r"[A-Za-z0-9_-]{40,100}",token):abort(400)
    if request.method=="POST":
        protect()
        digest=hashlib.sha256(token.encode()).hexdigest()
        result=sql("""WITH t AS(DELETE FROM b2_tokens WHERE digest=%s AND expires>NOW() RETURNING user_id)
            UPDATE b2_users SET email_verified=TRUE,email_verification_required=FALSE
            FROM t WHERE b2_users.id=t.user_id RETURNING b2_users.id""",(digest,),True)
        if not result:abort(410)
        return layout("אימות הושלם",'<div class="pagehead"><h1>הדוא״ל אומת</h1><a class="primary" href="/login">כניסה</a></div>')
    return layout("אימות דוא״ל",button_form('<div class="pagehead"><h1>אימות כתובת דוא״ל</h1><p>לחצו לאישור החד־פעמי.</p></div><input type="hidden" name="token" value="'+e(token)+'"><button class="primary">אימות</button>','/verify-email','class="formcard"'))

@app.route("/login",methods=["GET","POST"])
def login():
    if not PUBLIC_AUTH:abort(503)
    if request.method=="POST":
        protect();limit("login:"+request.form.get("email","")[:200],9,15)
        email=request.form.get("email","").lower().strip()[:200]
        pw=request.form.get("password","")
        u=sql("SELECT id,passhash,approved,email_verification_required FROM b2_users WHERE lower(email)=%s",(email,),True)
        if not u or not checkpw(pw,u["passhash"]):return layout("כניסה",'<div class="note error">פרטי הכניסה שגויים.</div><a href="/login">ניסיון נוסף</a>'),401
        if u["email_verification_required"]:return layout("כניסה",'<div class="note">יש לאמת תחילה את כתובת הדוא״ל.</div>'),403
        session.clear();session["csrf"]=secrets.token_urlsafe(32);session["uid"]=u["id"];session.permanent=True
        return redirect("/my-posts",code=303)
    return layout("כניסה",'<section class="auth-page"><div class="pagehead"><span class="tag">המרחב האישי</span><h1>טוב שחזרת הביתה</h1><p>התחברות מאובטחת באמצעות כתובת דוא״ל וסיסמה. אחרי הכניסה יחכו לך הזיכרונות, החברים והפרסומים שלך.</p></div><div class="auth-trust"><span>🔒 חיבור מוצפן</span><span>◈ חשבון פרטי</span><span>✦ זיכרונות משותפים</span></div>'+
        button_form('<label>כתובת דוא״ל<input type="email" dir="ltr" inputmode="email" name="email" autocomplete="email" placeholder="you@example.com" required></label>' + password_control("password","current-password") + '<p id="password-help" class="muted">הסיסמה נשארת פרטית ולא נשלחת לשירותי התחברות חיצוניים.</p><button class="primary">כניסה לחשבון</button>' +
         ('<p><a href="/signup">עדיין לא נרשמת?</a></p>' if ALLOW_SIGNUP else ''),'/login','class="formcard"')+'</section>')

@app.post("/logout")
@require_login
def logout():
    protect();session.clear();return redirect("/",code=303)

@app.get("/profile")
@require_login
def profile():
    u=g.user
    checked="checked" if u["show_profile"] else ""
    return layout("פרופיל",'<div class="pagehead"><h1>הפרופיל שלי</h1></div>'+button_form(
        '<label>כינוי מתקופת השירות<input name="nickname" maxlength="100" value="'+e(u["nickname"])+'"></label><label>שנים / מחזור<input name="unit_year" maxlength="50" value="'+e(u["unit_year"] or "")+'"></label><label>כמה מילים עליך<textarea name="about" maxlength="500">'+e(u["about"])+'</textarea></label><label class="check"><input name="visible" type="checkbox" '+checked+'> הצגת הפרופיל לחברים מאושרים בלבד</label><button class="primary">שמירת הפרופיל</button>','/profile','class="formcard"')+button_form('<button class="subtle">התנתקות</button>','/logout'))

@app.post("/profile")
@require_login
def save_profile():
    protect()
    sql("UPDATE b2_users SET nickname=%s,unit_year=%s,about=%s,show_profile=%s WHERE id=%s",
        (request.form.get("nickname","")[:100],request.form.get("unit_year","")[:50],
         request.form.get("about","")[:500],request.form.get("visible")=="on",g.user["id"]))
    return redirect("/profile",303)

def image_or_video(f):
    if not f or not f.filename:return None
    data=f.read(9*1024*1024)
    mime=f.mimetype.split(";")[0].lower()
    kind=None
    if mime in ("image/jpeg","image/png","image/webp"):
        try:
            im=Image.open(io.BytesIO(data))
            im.verify();im=Image.open(io.BytesIO(data))
            if im.width*im.height>12_000_000:abort(413)
            im=ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((1600,1600))
            b=io.BytesIO();im.save(b,format="JPEG",quality=83,optimize=True)
            data=b.getvalue();mime="image/jpeg";kind="image"
        except (OSError,UnidentifiedImageError,ValueError):abort(400)
    elif mime in ("video/mp4","video/quicktime") and len(data)>12 and data[4:8]==b"ftyp":
        kind="video"
    elif mime=="video/webm" and data[:4]==b"\x1a\x45\xdf\xa3":
        kind="video"
    elif mime in ("audio/webm","audio/ogg") and (
        data[:4] in (b"\x1a\x45\xdf\xa3",b"OggS")):
        kind="audio"
    if not kind or len(data)==0 or len(data)>8*1024*1024:abort(400)
    return (mime,kind,data)

@app.route("/new",methods=["GET","POST"])
@require_login
def create_post():
    if request.method=="POST":
        protect();limit("post:"+str(g.user["id"]),8,60)
        title=request.form.get("title","").strip()[:120]
        body=request.form.get("body","").strip()[:4000]
        kind=request.form.get("kind","story")
        year=request.form.get("year","").strip()[:30]
        if kind not in ("story","photo","event") or not title or request.form.get("rights")!="yes":abort(400)
        files=[v for v in request.files.getlist("uploads") if v and v.filename]
        if len(files)>4:abort(413)
        safe=[image_or_video(f) for f in files]
        if not body and not safe:abort(400)
        if sum(len(v[2]) for v in safe)>16*1024*1024:abort(413)
        with connect() as c:
            with c.cursor() as cur:
                cur.execute("""INSERT INTO b2_posts(author,title,body,kind,year_text)
                    VALUES(%s,%s,%s,%s,%s) RETURNING id""",
                    (g.user["id"],title,body,kind,year))
                pid=cur.fetchone()["id"]
                for mime,typ,data in safe:
                    cur.execute("""INSERT INTO b2_media(post_id,owner,mime,kind,body,length)
                        VALUES(%s,%s,%s,%s,%s,%s)""",
                        (pid,g.user["id"],mime,typ,data,len(data)))
        return redirect("/my-posts",303)
    return layout("שיתוף סיפור",'<div class="pagehead"><h1>משתפים זיכרון</h1><p>הפרסום יישמר פרטי עד אישור חברות וביקורת התוכן.</p></div>'+button_form(
        '<label>סוג זיכרון<select name="kind"><option value="story">סיפור</option><option value="photo">תמונות או סרטון</option><option value="event">אירוע ומפגש</option></select></label><label>כותרת<input name="title" required maxlength="120"></label><label>שנה (לא חובה)<input name="year" maxlength="30"></label><label>תוכן<textarea name="body" maxlength="4000" rows="6"></textarea></label><label>קבצים (עד ארבעה)<input type="file" name="uploads" multiple accept="image/jpeg,image/png,image/webp,video/mp4,video/webm,audio/webm,audio/ogg"></label><p class="muted">עד 8MB לקובץ ו־16MB סך הכול לפרסום. תמונות יעברו כיווץ והסרת נתוני EXIF.</p><label class="check"><input type="checkbox" name="rights" value="yes" required> אני מאשר שיש לי זכויות לפרסם את התוכן</label><button class="primary">שליחה לביקורת</button>',
        "/new",'class="formcard" enctype="multipart/form-data"'))

def media_html(mid,kind):
    src="/media/"+str(mid)
    if kind=="image":return '<img loading="lazy" src="'+src+'" alt="תצלום מהקהילה">'
    if kind=="video":return '<video controls preload="metadata" src="'+src+'">סרטון</video>'
    if kind=="audio":return '<audio controls preload="none" src="'+src+'">קול</audio>'
    return ""

@app.get("/media/<int:mid>")
@require_login
def media(mid):
    u=g.user
    m=sql("""SELECT f.*,p.status post_status
      FROM b2_media f LEFT JOIN b2_posts p ON p.id=f.post_id
      WHERE f.id=%s""",(mid,),True)
    if not m:abort(404)
    can_post=bool(m["post_id"] and (u["id"]==m["owner"] or
                  (u["approved"] and (admin() or m["post_status"]=="published"))))
    can_message=bool(m["recipient"] and u["id"] in (m["recipient"],m["owner"]) and u["approved"])
    if not (can_post or can_message):abort(403)
    r=send_file(io.BytesIO(bytes(m["body"])),mimetype=m["mime"],conditional=True,download_name="community-media")
    r.headers["Cache-Control"]="private,no-store"
    r.headers["Content-Security-Policy"]="default-src 'none'; sandbox"
    return r

@app.get("/my-posts")
@require_login
def myposts():
    posts=sql("SELECT * FROM b2_posts WHERE author=%s ORDER BY created DESC LIMIT 80",(g.user["id"],))
    items=''
    for p in posts:
        files=sql("SELECT id,kind FROM b2_media WHERE post_id=%s",(p["id"],))
        status="פורסם" if p["status"]=="published" else "ממתין לבדיקת מנהל"
        items+='<article class="post"><span class="tag">'+status+'</span><h2>'+e(p["title"])+'</h2><p>'+e(p["body"])+'</p><div class="media-grid">'+''.join(media_html(f["id"],f["kind"]) for f in files)+'</div></article>'
    return layout("הפרסומים שלי",'<div class="pagehead"><h1>הפרסומים שלי</h1><p>רק אתה והמנהל רואים פרסומים שעדיין לא אושרו.</p><a class="primary" href="/new">פרסום חדש</a></div>'+(items or '<div class="note">אין לך עדיין פרסומים.</div>'))

@app.get("/feed")
@require_approved
def feed():
    posts=sql("""SELECT p.*,u.name FROM b2_posts p JOIN b2_users u ON u.id=p.author
                 WHERE p.status='published' AND u.approved=TRUE
                 ORDER BY p.created DESC LIMIT 60""")
    items=''
    for p in posts:
        files=sql("SELECT id,kind FROM b2_media WHERE post_id=%s",(p["id"],))
        items+='<article class="post"><span class="tag">'+e(p["kind"])+'</span><h2>'+e(p["title"])+'</h2><p>'+e(p["name"])+' · '+e(p["year_text"])+'</p><p>'+e(p["body"])+'</p><div class="media-grid">'+''.join(media_html(f["id"],f["kind"]) for f in files)+'</div></article>'
    return layout("מרחב החברים",'<div class="pagehead"><h1>החברים משתפים</h1><p>סיפורים ותמונות שפורסמו לאחר ביקורת.</p><a href="/new" class="primary">שיתוף משלך</a></div>'+(items or '<div class="note">עדיין אין פרסומים מאושרים.</div>'))

@app.get("/find")
@require_approved
def find():
    term=request.args.get("q","").strip()[:80]
    matches=[]
    if term:
        matches=sql("""SELECT id,name,nickname,unit_year,about FROM b2_users WHERE approved=TRUE
            AND show_profile=TRUE AND (name ILIKE %s OR nickname ILIKE %s OR unit_year ILIKE %s)
            ORDER BY name LIMIT 25""",tuple("%"+term+"%" for _ in range(3)))
    cards=''
    for m in matches:
        cards+='<article class="person"><h3>'+e(m["name"])+'</h3><p>'+e(m["nickname"])+' '+e(m["unit_year"])+'</p><p>'+e(m["about"])+'</p><a href="/chat/'+str(m["id"])+'">שליחת הודעה</a></article>'
    return layout("איתור חברים",'<div class="pagehead"><h1>מוצאים שוב את החברים</h1><p>חיפוש בין פרופילים שחבריהם אישרו להציגם.</p></div><form class="search"><label>שם, כינוי או מחזור<input name="q" value="'+e(term)+'" maxlength="80"></label><button class="primary">חיפוש</button></form><section class="people">'+(cards or '<div class="note">לא נמצאו תוצאות גלויות לחיפוש הזה.</div>')+'</section>')

@app.get("/inbox")
@require_approved
def inbox():
    peers=sql("""SELECT DISTINCT u.id,u.name FROM b2_users u
        JOIN b2_messages m ON (m.sender=u.id OR m.recipient=u.id)
        WHERE ((m.sender=%s AND m.recipient=u.id) OR
               (m.recipient=%s AND m.sender=u.id))
          AND u.approved=TRUE ORDER BY u.name LIMIT 60""",(g.user["id"],g.user["id"]))
    html=''.join('<a class="person" href="/chat/'+str(x["id"])+'">'+e(x["name"])+' ← לשיחה</a>' for x in peers)
    return layout("ההודעות שלי",'<div class="pagehead"><h1>הודעות פרטיות</h1><p>השיחות גלויות רק למשתתפים.</p></div>'+(html or '<div class="note">אין שיחות עדיין. ניתן למצוא חברים במדריך.</div>'))

@app.route("/chat/<int:peer>",methods=["GET","POST"])
@require_approved
def chat(peer):
    other=sql("SELECT id,name FROM b2_users WHERE id=%s AND approved=TRUE",(peer,),True)
    if not other or other["id"]==g.user["id"]:abort(404)
    if request.method=="POST":
        protect();limit("message:"+str(g.user["id"]),18,60)
        body=request.form.get("text","").strip()[:2000]
        f=request.files.get("file")
        info=image_or_video(f) if f and f.filename else None
        if not body and not info:abort(400)
        with connect() as c:
            with c.cursor() as cur:
                mid=None
                if info:
                    mime,kind,data=info
                    cur.execute("""INSERT INTO b2_media(owner,recipient,mime,kind,body,length)
                       VALUES(%s,%s,%s,%s,%s,%s) RETURNING id""",
                       (g.user["id"],peer,mime,kind,data,len(data)))
                    mid=cur.fetchone()["id"]
                cur.execute("INSERT INTO b2_messages(sender,recipient,text,media_id) VALUES(%s,%s,%s,%s)",
                            (g.user["id"],peer,body,mid))
        return redirect("/chat/"+str(peer),303)
    messages=sql("""SELECT m.*,f.kind FROM b2_messages m LEFT JOIN b2_media f ON f.id=m.media_id
         WHERE (m.sender=%s AND m.recipient=%s) OR (m.sender=%s AND m.recipient=%s)
         ORDER BY m.created DESC LIMIT 90""",(g.user["id"],peer,peer,g.user["id"]))
    out=''
    for m in reversed(messages):
        cls="mine" if m["sender"]==g.user["id"] else "theirs"
        out+='<div class="bubble '+cls+'"><p>'+e(m["text"])+'</p>'+(media_html(m["media_id"],m["kind"]) if m["media_id"] else '')+'</div>'
    return layout("שיחה עם "+other["name"],'<div class="pagehead"><h1>שיחה עם '+e(other["name"])+'</h1><p>הודעות פרטיות בין חברים מאושרים בלבד.</p></div><section class="conversation">'+(out or '<p>עדיין אין הודעות.</p>')+'</section>'+button_form(
        '<label>הודעה<textarea name="text" rows="3" maxlength="2000"></textarea></label><label>תמונה, סרטון או הקלטה<input type="file" name="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/webm,audio/webm,audio/ogg"></label><button class="primary">שליחה</button>',
        '/chat/'+str(peer),'class="formcard" enctype="multipart/form-data"'))

@app.route("/moderation",methods=["GET","POST"])
@require_approved
def moderation():
    if not admin():abort(403)
    if request.method=="POST":
        protect()
        pid=request.form.get("id","")
        action=request.form.get("action","")
        if not pid.isdecimal() or action not in ("publish","reject"):abort(400)
        if action=="publish":
            result=sql("""UPDATE b2_posts p SET status='published' FROM b2_users u
                WHERE p.id=%s AND p.author=u.id AND u.approved=TRUE
                AND p.status='pending' RETURNING p.id""",(int(pid),),True)
            if not result:abort(409)
        else:sql("UPDATE b2_posts SET status='rejected' WHERE id=%s AND status='pending'",(int(pid),))
        return redirect("/moderation",303)
    posts=sql("""SELECT p.*,u.name,u.approved FROM b2_posts p
        JOIN b2_users u ON u.id=p.author WHERE p.status='pending'
        ORDER BY p.created DESC LIMIT 60""")
    cards=''
    for p in posts:
        files=sql("SELECT id,kind FROM b2_media WHERE post_id=%s",(p["id"],))
        controls=('<button name="action" value="publish" class="primary">אישור לפרסום</button>' if p["approved"] else '<span>נדרש קודם אישור החבר</span>')
        controls+='<button name="action" value="reject" class="subtle">דחיית פרסום</button>'
        cards+='<article class="post"><h2>'+e(p["title"])+'</h2><p>מאת '+e(p["name"])+'</p><p>'+e(p["body"])+'</p><div class="media-grid">'+''.join(media_html(f["id"],f["kind"]) for f in files)+'</div>'+button_form('<input type="hidden" name="id" value="'+str(p["id"])+'">'+controls,'/moderation')+'</article>'
    return layout("בקרת פרסומים",'<div class="pagehead"><h1>בקרת פרסומים</h1></div>'+(cards or '<p>אין פרסומים ממתינים.</p>'))

@app.route("/members",methods=["GET","POST"])
@require_approved
def members():
    if not admin():abort(403)
    if request.method=="POST":
        protect()
        uid=request.form.get("id","")
        if not uid.isdecimal() or request.form.get("action") not in ("approve","reject"):abort(400)
        if int(uid)==g.user["id"]:abort(400)
        approved=request.form["action"]=="approve"
        sql("UPDATE b2_users SET approved=%s WHERE id=%s",(approved,int(uid)))
        return redirect("/members",303)
    rows=sql("SELECT id,name,email,joined FROM b2_users WHERE approved=FALSE ORDER BY joined DESC LIMIT 100")
    html=''
    for u in rows:
        html+='<article class="person"><h3>'+e(u["name"])+'</h3><p>'+e(u["email"])+'</p>'+button_form(
            '<input type="hidden" name="id" value="'+str(u["id"])+'"><button name="action" value="approve" class="primary">אישור חבר</button><button name="action" value="reject" class="subtle">דחייה</button>','/members')+'</article>'
    return layout("אישור חברים",'<div class="pagehead"><h1>בקשות חברות</h1></div>'+(html or '<div class="note">אין בקשות חברות ממתינות.</div>'))

@app.errorhandler(404)
def not_found(err):return layout("העמוד לא נמצא",'<div class="pagehead"><h1>העמוד לא נמצא</h1><a href="/">חזרה לדף הבית</a></div>'),404

@app.errorhandler(403)
def forbidden(err):return layout("גישה מוגבלת",'<div class="pagehead"><h1>גישה מוגבלת</h1><p>יש צורך בחברות מאושרת או בהרשאה מתאימה.</p></div>'),403

@app.errorhandler(503)
def maintenance(err):return layout("מערכת החברים בהכנה",'<div class="pagehead"><h1>החברים חוזרים לכאן בקרוב</h1><p>המערכת האישית סגורה עד בדיקות בטיחות ואבטחה; בינתיים אפשר לעיין במורשת ובהנצחה.</p><a href="/" class="primary">לעמוד הבית</a></div>'),503

if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
