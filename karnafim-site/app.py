"""Karnafim / Barkan — independent, Hebrew RTL veterans community.

New application and database tables (b2_*). No Google social login, no shared
shop dependency, no external scripts. This deployment serves the original public address with the rebuilt application.
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
from werkzeug.middleware.proxy_fix import ProxyFix
from markupsafe import Markup
from PIL import Image, ImageOps, UnidentifiedImageError

BASE=Path(__file__).resolve().parent
app=Flask(__name__,static_folder=str(BASE/"static"))
# Render terminates HTTPS at its own ingress proxy. Trust exactly one ingress
# hop for the client IP used by brute-force throttling, not forwarded host
# or scheme headers. Outside Render, never trust arbitrary forwarded IPs.
if os.environ.get("RENDER_SERVICE_ID","").strip():
    app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=0,x_host=0,x_port=0,x_prefix=0)
CONFIGURED_SECRET=os.environ.get("BARKAN_SESSION_SECRET","").strip()
DB=os.environ.get("BARKAN_DATABASE_URL","").strip()
app.config.update(
    # An ephemeral key is acceptable only for a public read-only deployment.
    # Account login requires a durable configured secret and a database.
    SECRET_KEY=CONFIGURED_SECRET or secrets.token_urlsafe(48),
    SESSION_COOKIE_NAME="barkan_46_session",
    SESSION_COOKIE_SECURE=True,SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",PERMANENT_SESSION_LIFETIME=3600*6,
    MAX_CONTENT_LENGTH=32*1024*1024, MAX_FORM_MEMORY_SIZE=128*1024,
    TRUSTED_HOSTS=["karnafim-community-46.onrender.com","localhost","127.0.0.1"],
)
ORIGIN=os.environ.get("BARKAN_PUBLIC_ORIGIN","https://karnafim-community-46.onrender.com").rstrip("/")
# Public account forms are a separate switch. Never enable until the new origin
# passes live security checks and is no longer flagged by Safe Browsing.
PUBLIC_AUTH=(bool(CONFIGURED_SECRET and DB)
             and os.environ.get("BARKAN_PUBLIC_AUTH","0")=="1"
             and os.environ.get("BARKAN_SAFETY_RELEASE_APPROVED","0")=="1")
EMAIL_PROVIDER=os.environ.get("BARKAN_RESEND_API_KEY","").strip()
BREVO_API_KEY=os.environ.get("BARKAN_BREVO_API_KEY","").strip()
MAIL_FROM=os.environ.get("BARKAN_MAIL_FROM","").strip()
# Prefer a configured Brevo sender. Do not allow conflicting simultaneous
# providers: deployments must intentionally select a single email transport.
EMAIL_TRANSPORT=("brevo" if BREVO_API_KEY and not EMAIL_PROVIDER else
                 "resend" if EMAIL_PROVIDER and not BREVO_API_KEY else "")
MAIL_READY=bool(EMAIL_TRANSPORT and MAIL_FROM and
                re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",MAIL_FROM))
# Configuration is not proof of delivery. A separate explicit release attests
# that a real end-to-end verification message reached a controlled mailbox.
MAIL_DELIVERY_VERIFIED=(MAIL_READY and
                        os.environ.get("BARKAN_MAIL_DELIVERY_VERIFIED","0")=="1")
# An optional application-only path accepts requests without outgoing mail.
# Such accounts stay unapproved until a human administrator verifies the
# applicant's membership and email ownership outside the website.
MANUAL_SIGNUP=(PUBLIC_AUTH and os.environ.get("BARKAN_MANUAL_SIGNUP","0")=="1")
ALLOW_SIGNUP=(MANUAL_SIGNUP or
              (PUBLIC_AUTH and os.environ.get("BARKAN_ALLOW_SIGNUP","0")=="1"
               and MAIL_DELIVERY_VERIFIED))

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
            # Existing accounts retain their values. No directory information
            # is publicly visible until the member explicitly opts in.
            cur.execute("ALTER TABLE b2_users ADD COLUMN IF NOT EXISTS enlistment_cohort TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE b2_users ADD COLUMN IF NOT EXISTS service_role TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE b2_users ADD COLUMN IF NOT EXISTS platoon TEXT NOT NULL DEFAULT ''")
            cur.execute("CREATE INDEX IF NOT EXISTS b2_users_directory_idx ON b2_users(approved,show_profile,enlistment_cohort)")
            cur.execute("""CREATE TABLE IF NOT EXISTS b2_staff_roles(
                user_id BIGINT PRIMARY KEY REFERENCES b2_users(id) ON DELETE CASCADE,
                can_approve BOOLEAN NOT NULL DEFAULT FALSE,
                can_moderate BOOLEAN NOT NULL DEFAULT FALSE,
                can_invite BOOLEAN NOT NULL DEFAULT FALSE,
                granted_by BIGINT REFERENCES b2_users(id),
                updated TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            cur.execute("""CREATE TABLE IF NOT EXISTS b2_admin_audit(
                id BIGSERIAL PRIMARY KEY,
                actor BIGINT NOT NULL REFERENCES b2_users(id),
                subject BIGINT NOT NULL REFERENCES b2_users(id),
                action TEXT NOT NULL CHECK(action IN
                    ('roles_saved','roles_revoked','member_approved','member_rejected')),
                detail TEXT NOT NULL DEFAULT '',
                created TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            cur.execute("CREATE INDEX IF NOT EXISTS b2_admin_audit_created_idx ON b2_admin_audit(created DESC)")
            cur.execute("""CREATE TABLE IF NOT EXISTS b2_meetups(
                id BIGSERIAL PRIMARY KEY,
                creator BIGINT NOT NULL REFERENCES b2_users(id),
                title TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                location_text TEXT NOT NULL DEFAULT '',
                starts_at TIMESTAMPTZ NOT NULL,
                cancelled BOOLEAN NOT NULL DEFAULT FALSE,
                created TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            cur.execute("CREATE INDEX IF NOT EXISTS b2_meetups_time_idx ON b2_meetups(starts_at)")
            cur.execute("""CREATE TABLE IF NOT EXISTS b2_meetup_rsvps(
                meetup_id BIGINT NOT NULL REFERENCES b2_meetups(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL REFERENCES b2_users(id) ON DELETE CASCADE,
                attending BOOLEAN NOT NULL DEFAULT TRUE,
                updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY(meetup_id,user_id))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS b2_tokens(
                user_id BIGINT PRIMARY KEY REFERENCES b2_users(id) ON DELETE CASCADE,
                digest CHAR(64) NOT NULL UNIQUE,expires TIMESTAMPTZ NOT NULL)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS b2_throttle(
                fingerprint TEXT NOT NULL,at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            cur.execute("CREATE INDEX IF NOT EXISTS b2_throttle_idx ON b2_throttle(fingerprint,at)")
            cur.execute("CREATE INDEX IF NOT EXISTS b2_throttle_time_idx ON b2_throttle(at)")
            cur.execute("""CREATE TABLE IF NOT EXISTS b2_posts(
                id BIGSERIAL PRIMARY KEY,author BIGINT NOT NULL REFERENCES b2_users(id),
                title TEXT NOT NULL,body TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'story',
                year_text TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                created TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            cur.execute("ALTER TABLE b2_posts ADD COLUMN IF NOT EXISTS album_cohort TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE b2_posts ADD COLUMN IF NOT EXISTS moderation_reason TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE b2_posts ADD COLUMN IF NOT EXISTS moderation_summary TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE b2_posts ADD COLUMN IF NOT EXISTS moderation_source TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE b2_posts ADD COLUMN IF NOT EXISTS appealed BOOLEAN NOT NULL DEFAULT FALSE")
            cur.execute("""CREATE TABLE IF NOT EXISTS b2_moderation_events(
                id BIGSERIAL PRIMARY KEY,
                post_id BIGINT NOT NULL REFERENCES b2_posts(id) ON DELETE CASCADE,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL,
                created TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            cur.execute("CREATE INDEX IF NOT EXISTS b2_posts_album_cohort_idx ON b2_posts(album_cohort,status)")
            cur.execute("CREATE INDEX IF NOT EXISTS b2_posts_status_idx ON b2_posts(status,created DESC)")
            cur.execute("""CREATE TABLE IF NOT EXISTS b2_media(
                id BIGSERIAL PRIMARY KEY,post_id BIGINT REFERENCES b2_posts(id) ON DELETE CASCADE,
                owner BIGINT NOT NULL REFERENCES b2_users(id),
                recipient BIGINT REFERENCES b2_users(id),
                mime TEXT NOT NULL,kind TEXT NOT NULL,body BYTEA NOT NULL,
                length INTEGER NOT NULL,created TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            cur.execute("""CREATE TABLE IF NOT EXISTS b2_photo_self_tags(
                media_id BIGINT NOT NULL REFERENCES b2_media(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL REFERENCES b2_users(id) ON DELETE CASCADE,
                created TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY(media_id,user_id))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS b2_photo_memories(
                id BIGSERIAL PRIMARY KEY,
                media_id BIGINT NOT NULL REFERENCES b2_media(id) ON DELETE CASCADE,
                author BIGINT NOT NULL REFERENCES b2_users(id) ON DELETE CASCADE,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','published','rejected')),
                created TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            cur.execute("CREATE INDEX IF NOT EXISTS b2_photo_memories_review ON b2_photo_memories(status,created)")
            cur.execute("""CREATE TABLE IF NOT EXISTS b2_photo_reports(
                id BIGSERIAL PRIMARY KEY,
                media_id BIGINT NOT NULL REFERENCES b2_media(id) ON DELETE CASCADE,
                reporter BIGINT NOT NULL REFERENCES b2_users(id),
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open'
                    CHECK(status IN ('open','resolved','hidden')),
                created TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(media_id,reporter))""")
            cur.execute("CREATE INDEX IF NOT EXISTS b2_photo_reports_review ON b2_photo_reports(status,created)")
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
            # Old throttle entries are no longer relevant. Reclaim space
            # using an indexed timestamp, without touching member data.
            # Keep at least two days of history for all current windows.
            cur.execute("DELETE FROM b2_throttle WHERE at < NOW() - INTERVAL '2 days'")
            cur.execute("SELECT COUNT(*) n FROM b2_throttle WHERE fingerprint=%s AND at>NOW()-(%s * INTERVAL '1 minute')",(fp,minutes))
            if cur.fetchone()["n"]>=maximum:abort(429)
            cur.execute("INSERT INTO b2_throttle(fingerprint) VALUES(%s)",(fp,))

def current():
    uid=session.get("uid")
    if not isinstance(uid,int):return None
    return sql("SELECT id,name,email,approved,show_profile,email_verified,email_verification_required,nickname,unit_year,about,enlistment_cohort,service_role,platoon FROM b2_users WHERE id=%s",(uid,),True)

@app.before_request
def before():
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

def staff_permissions():
    """Owner alone grants and revokes permissions; never infer from form values."""
    if not g.user or not g.user["approved"]:
        return {"approve":False,"moderate":False,"invite":False}
    if admin():
        return {"approve":True,"moderate":True,"invite":True}
    role=sql("SELECT can_approve,can_moderate,can_invite FROM b2_staff_roles WHERE user_id=%s",
             (g.user["id"],),True)
    return {"approve":bool(role and role["can_approve"]),
            "moderate":bool(role and role["can_moderate"]),
            "invite":bool(role and role["can_invite"])}


def moderate_submission(title,body,kind,files,author_approved):
    """Conservative free local policy engine, not an LLM or a proof of identity.

    Only low-risk text stories from approved members are automatically approved.
    Ambiguous/sensitive materials require human review. Explicit commercial
    solicitation is declined with a reason and an appeal route.
    """
    if not author_approved:
        return ("pending","נדרש אישור זהות וחברות בידי מנהל לפני פרסום.","")
    text_content=(title+" "+body).strip()
    compact=" ".join(text_content.split())
    summary=(compact[:197].rstrip()+"…" if len(compact)>200 else compact)
    if files or kind!="story":
        return ("pending","קובץ קול, תמונה, סרטון או סוג תוכן רגיש מחייבים בדיקת תוכן אנושית.","")
    # Never inspect and infer intent from image/audio bytes in this lightweight engine.
    if re.search(r"(?:https?://|www\.|t\.me/|wa\.me/|קנו עכשיו|להזמנות|מבצע מיוחד)",compact,re.I):
        return ("rejected","הפרסום כולל קישור או ביטוי מסחרי שאינו מתאים לארכיון הפלוגה. אפשר לערער אם זו הפניה למקור מורשת.", "")
    if len(body.strip())<80:
        return ("pending","נדרש הקשר נוסף כדי לבדוק באופן מהימן את הסיפור.","")
    if re.search(r"(?:\b(?:05[0-9][\s-]?[0-9]{7}|[0-9]{2,3}[\s-]?[0-9]{7})\b|"
                 r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|"
                 r"כתובת מגורים|תעודת זהות|סיסמה|מסווג|סודי ביותר|מיקום כוח|"
                 r"נפל בקרב|נהרג|חלל|פצוע|התאבדות|אונס|הטרדה|אלימות|"
                 r"לשון הרע|שם מלא)",compact,re.I):
        return ("pending","זוהו נושאי פרטיות, בטיחות או הנצחה המחייבים בדיקה אנושית לפני פרסום.","")
    # Explicitly labeled machine-generated excerpt, not a claim of factual verification.
    return ("published","עמד בכללי הסינון האוטומטי הבסיסיים. דיוק היסטורי לא אומת.",summary)


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
        menu += [("/feed","הקהילה"),("/cohorts","ספר המחזורים"),("/voices","מורשת קולית"),("/meetups","מפגשי פלוגה"),("/find","איתור חברים"),("/new","שיתוף זיכרון"),("/my-posts","הפרסומים שלי"),("/inbox","הודעות"),("/profile","הפרופיל שלי")]
        permissions=staff_permissions() if u["approved"] else {"approve":False,"moderate":False,"invite":False}
        if permissions["moderate"]:menu += [("/moderation","בקרת פרסומים"),("/photo-review","בקשות פרטיות")]
        if permissions["approve"]:menu += [("/members","אישור חברים")]
        if permissions["invite"]:menu += [("/invite","הזמנת חברים")]
        if admin():menu += [("/dashboard","לוח בקרה"),("/team","הרשאות ניהול")]
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
<button id="toggle" type="button" aria-expanded="false" aria-controls="nav" aria-label="פתיחת תפריט הניווט">☰ תפריט</button>
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
            "signup_enabled":ALLOW_SIGNUP,"email_sender_configured":MAIL_READY,
            "email_delivery_release_verified":MAIL_DELIVERY_VERIFIED,
            "registration_mode":"manual_review" if MANUAL_SIGNUP else
                                "email_verified" if ALLOW_SIGNUP else "closed"},200

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
<div class="hero-actions">'''+('<a class="primary" href="/signup">הצטרפות לקהילה</a>' if ALLOW_SIGNUP else '')+'''<a class="outline" href="/heritage">לסיפורי הפלוגה</a><a class="outline" href="/memorial">לזיכרון ולהנצחה</a></div>
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
    intro='<div class="pagehead"><span class="tag">אלבומי הפלוגה</span><h1>רגעים שמחזירים את כולנו לשירות</h1><p>תמונות שעברו אישור פרסום, לפי מחזור גיוס או באלבום הכללי.</p></div>'
    if not PUBLIC_AUTH or not g.user or not g.user["approved"]:
        return layout("תמונות",intro+'<section class="empty-photo"><h2>האלבומים פרטיים</h2><p>תמונות משותפות זמינות לחברי קהילה מאושרים בלבד.</p></section>')
    cohort=request.args.get("cohort","").strip()
    if cohort and cohort!="general" and not re.fullmatch(r"(19[9][0-9]|20[0-3][0-9])-(0[1-9]|1[0-2])",cohort):
        abort(400)
    albums=sql("""SELECT p.album_cohort,COUNT(*) AS total FROM b2_media f
        JOIN b2_posts p ON p.id=f.post_id JOIN b2_users u ON u.id=p.author
        WHERE f.kind='image' AND p.status='published' AND u.approved=TRUE
        GROUP BY p.album_cohort ORDER BY p.album_cohort DESC LIMIT 120""")
    links=('<a class="outline" href="/photos">כל התמונות</a> '+
           ''.join('<a class="outline" href="/photos?cohort='+e(c["album_cohort"] or "general")+'">'+
              e(c["album_cohort"] or "אלבום כללי")+' ('+str(c["total"])+')</a> ' for c in albums))
    records=sql("""SELECT f.id,p.title,p.year_text,p.album_cohort,u.name FROM b2_media f
        JOIN b2_posts p ON p.id=f.post_id JOIN b2_users u ON u.id=p.author
        WHERE f.kind='image' AND p.status='published' AND u.approved=TRUE
          AND (%s='' OR (%s='general' AND p.album_cohort='')
               OR p.album_cohort=%s)
        ORDER BY p.created DESC,f.id DESC LIMIT 80""",(cohort,cohort,cohort))
    tiles=''
    for r in records:
        tags=sql("""SELECT u.name,t.user_id FROM b2_photo_self_tags t
                    JOIN b2_users u ON u.id=t.user_id
                    WHERE t.media_id=%s AND u.approved=TRUE ORDER BY u.name LIMIT 30""",(r["id"],))
        mine=any(t["user_id"]==g.user["id"] for t in tags)
        names=', '.join(e(t["name"]) for t in tags)
        label='<p>זיהוי עצמי מרצון: '+names+'</p>' if names else ''
        comments=sql("""SELECT m.body,u.name FROM b2_photo_memories m
                     JOIN b2_users u ON u.id=m.author
                     WHERE m.media_id=%s AND m.status='published' AND u.approved=TRUE
                     ORDER BY m.created ASC LIMIT 15""",(r["id"],))
        notes=''.join('<blockquote><p>'+e(c["body"])+'</p><p>— '+e(c["name"])+'</p></blockquote>'
                       for c in comments)
        memory_form=button_form('<input type="hidden" name="id" value="'+str(r["id"])+'">'
                      '<label>הוספת זיכרון לתמונה<textarea name="body" maxlength="1200" required rows="3"></textarea></label>'
                      '<button class="subtle">שליחת זיכרון לביקורת</button>',
                      '/photos/memory','class="formcard"')
        report_form=button_form('<input type="hidden" name="id" value="'+str(r["id"])+'">'
                      '<label>בקשת הסרה או בדיקת פרטיות<textarea name="reason" maxlength="700" required rows="2"></textarea></label>'
                      '<button class="subtle">שליחת בקשה פרטית למנהל</button>',
                      '/photos/report','class="formcard"')
        toggle=button_form('<input type="hidden" name="id" value="'+str(r["id"])+'">'+
             ('<button class="subtle" name="action" value="remove">הסרת הזיהוי שלי</button>'
              if mine else '<button class="subtle" name="action" value="add">אני מופיע/ה בתמונה — אישור הצגת שמי</button>'),
             '/photos/self-tag')
        tiles= (tiles+'<article class="post">'+media_html(r["id"],"image")+'<h2>'+e(r["title"])+
              '</h2><p>'+e(r["name"])+' · '+e(r["year_text"])+'</p><p>אלבום: '+
              e(r["album_cohort"] or "כללי")+'</p>'+label+toggle+notes+memory_form+report_form+'</article>')
    return layout("תמונות",intro+'<nav class="album-nav" aria-label="בחירת אלבום">'+links+'</nav>'+
        ('<section class="media-grid">'+tiles+'</section>' if tiles else
         '<section class="empty-photo"><h2>אין תמונות מאושרות באלבום זה</h2><p>חברים מוזמנים לתרום תמונות שצילמו ושמותר להם לשתף. הפרסום יתבצע רק אחרי ביקורת.</p><a href="/new">העלאת תמונה לביקורת</a></section>'))


@app.post("/photos/self-tag")
@require_approved
def photo_self_tag():
    """Only self-identification on a published photo; no third-party tagging."""
    protect();limit("self-tag:"+str(g.user["id"]),35,60)
    media_id=request.form.get("id","")
    action=request.form.get("action","")
    if not media_id.isdecimal() or action not in ("add","remove"):abort(400)
    mid=int(media_id)
    valid=sql("""SELECT f.id FROM b2_media f
        JOIN b2_posts p ON p.id=f.post_id
        JOIN b2_users u ON u.id=p.author
        WHERE f.id=%s AND f.kind='image' AND p.status='published'
          AND u.approved=TRUE""",(mid,),True)
    if not valid:abort(404)
    if action=="add":
        sql("""INSERT INTO b2_photo_self_tags(media_id,user_id)
               VALUES(%s,%s) ON CONFLICT(media_id,user_id) DO NOTHING""",(mid,g.user["id"]))
    else:
        sql("DELETE FROM b2_photo_self_tags WHERE media_id=%s AND user_id=%s",(mid,g.user["id"]))
    return redirect("/photos",303)


def published_photo(mid):
    return sql("""SELECT f.id,f.post_id FROM b2_media f
        JOIN b2_posts p ON p.id=f.post_id
        JOIN b2_users u ON u.id=p.author
        WHERE f.id=%s AND f.kind='image' AND p.status='published'
          AND u.approved=TRUE""",(mid,),True)

@app.post("/photos/memory")
@require_approved
def photo_memory():
    protect();limit("photo-memory:"+str(g.user["id"]),12,60)
    raw=request.form.get("id","")
    body=request.form.get("body","").strip()
    if not raw.isdecimal() or not 5<=len(body)<=1200:abort(400)
    if not published_photo(int(raw)):abort(404)
    sql("INSERT INTO b2_photo_memories(media_id,author,body) VALUES(%s,%s,%s)",
        (int(raw),g.user["id"],body))
    return redirect("/photos",303)

@app.post("/photos/report")
@require_approved
def photo_report():
    protect();limit("photo-report:"+str(g.user["id"]),10,60)
    raw=request.form.get("id","")
    reason=request.form.get("reason","").strip()
    if not raw.isdecimal() or not 10<=len(reason)<=700:abort(400)
    if not published_photo(int(raw)):abort(404)
    sql("""INSERT INTO b2_photo_reports(media_id,reporter,reason)
        VALUES(%s,%s,%s) ON CONFLICT(media_id,reporter)
        DO UPDATE SET reason=EXCLUDED.reason,status='open',created=NOW()""",
        (int(raw),g.user["id"],reason))
    return redirect("/photos",303)

@app.route("/photo-review",methods=["GET","POST"])
@require_approved
def photo_review():
    if not staff_permissions()["moderate"]:abort(403)
    if request.method=="POST":
        protect();limit("photo-review:"+str(g.user["id"]),35,60)
        raw=request.form.get("id","")
        action=request.form.get("action","")
        if not raw.isdecimal() or action not in ("publish_memory","reject_memory","resolve_report","hide_photo"):
            abort(400)
        ident=int(raw)
        if action in ("publish_memory","reject_memory"):
            status="published" if action=="publish_memory" else "rejected"
            result=sql("""UPDATE b2_photo_memories SET status=%s
                WHERE id=%s AND status='pending' RETURNING id""",(status,ident),True)
        elif action=="resolve_report":
            result=sql("""UPDATE b2_photo_reports SET status='resolved'
                WHERE id=%s AND status='open' RETURNING id""",(ident,),True)
        else:
            # A confirmed privacy complaint hides the entire post and media
            # from members, pending further review; no permanent deletion.
            with connect() as c:
                with c.cursor() as cur:
                    cur.execute("""UPDATE b2_posts SET status='hidden'
                        WHERE id=(SELECT f.post_id FROM b2_photo_reports r
                                  JOIN b2_media f ON f.id=r.media_id WHERE r.id=%s)
                        AND status='published' RETURNING id""",(ident,))
                    changed=cur.fetchone()
                    if not changed:abort(409)
                    cur.execute("UPDATE b2_photo_reports SET status='hidden' WHERE id=%s",(ident,))
            result=changed
        if not result:abort(409)
        return redirect("/photo-review",303)
    memories=sql("""SELECT m.id,m.body,m.created,u.name,post.title FROM b2_photo_memories m
        JOIN b2_users u ON u.id=m.author
        JOIN b2_media f ON f.id=m.media_id
        JOIN b2_posts post ON post.id=f.post_id
        WHERE m.status='pending' ORDER BY m.created LIMIT 60""")
    reports=sql("""SELECT r.id,r.reason,r.created,u.name,post.title,f.id media_id
        FROM b2_photo_reports r
        JOIN b2_users u ON u.id=r.reporter
        JOIN b2_media f ON f.id=r.media_id
        JOIN b2_posts post ON post.id=f.post_id
        WHERE r.status='open' ORDER BY r.created LIMIT 60""")
    cards=''
    for item in memories:
        fields=('<input type="hidden" name="id" value="'+str(item["id"])+'">'
                '<button class="primary" name="action" value="publish_memory">אישור זיכרון</button>'
                '<button class="subtle" name="action" value="reject_memory">דחיית זיכרון</button>')
        cards+='<article class="person"><h3>'+e(item["title"])+'</h3><p>'+e(item["name"])+': '+e(item["body"])+'</p>'+button_form(fields,"/photo-review")+'</article>'
    for item in reports:
        fields=('<input type="hidden" name="id" value="'+str(item["id"])+'">'
                '<button class="subtle" name="action" value="resolve_report">סימון כטופל</button>'
                '<button class="primary" name="action" value="hide_photo">הסתרת הפרסום לבדיקה</button>')
        cards+='<article class="person"><h3>בקשת פרטיות — '+e(item["title"])+'</h3><p>'+e(item["name"])+': '+e(item["reason"])+'</p>'+button_form(fields,"/photo-review")+'</article>'
    return layout("בדיקת תמונות וזיכרונות",'<div class="pagehead"><h1>בקרת זיכרונות ובקשות פרטיות</h1><p>הבקשות גלויות לצוות הבקרה בלבד. הסתרת תמונה משביתה את הפרסום עד החלטה נוספת.</p></div>'+(cards or '<p>אין פניות ממתינות.</p>'))

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
    registration=("הרשמה פתוחה עם אימות זהות ואישור מנהל ידניים." if MANUAL_SIGNUP else
                  "הרשמה פתוחה עם אימות דוא״ל." if ALLOW_SIGNUP else
                  "ההרשמה סגורה.")
    mail=("נבדקה מסירה דרך ספק דוא״ל." if MAIL_DELIVERY_VERIFIED else
          "טרם אומתה מסירה אמיתית; במסלול הידני אין משלוח דוא״ל." if MANUAL_SIGNUP else
          "ספק הדוא״ל אינו מאומת.")
    return layout("מצב המערכת",'<div class="pagehead"><h1>מצב המערכת</h1></div><section class="story"><p>אתר המורשת: פעיל.</p><p>התחברות לחברים קיימים: '+("פעילה." if PUBLIC_AUTH else "מושהית.")+'</p><p>'+registration+'</p><p>'+mail+'</p><p>זו הכתובת הראשית של קהילת הקרנפים / ברקן. גישה לתוכן ולהודעות של חברים מחייבת אישור חברות.</p></section>')

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
                        VALUES(%s,%s,%s,%s) RETURNING id""",(name,email,hashpw(password),not MANUAL_SIGNUP))
                    uid=cur.fetchone()["id"]
                except psycopg.errors.UniqueViolation:
                    c.rollback()
                    return layout("הרשמה",'<div class="note">אם הבקשה כבר קיימת, אין צורך להגיש אותה שוב.</div>')
        if MANUAL_SIGNUP:
            return layout("בקשת הצטרפות",'<div class="pagehead"><h1>בקשת ההצטרפות נקלטה</h1><p>החשבון ממתין לאישור מנהל הקהילה לאחר אימות זהות ושייכות לפלוגה. לא נשלח דוא״ל ולא אומתה כתובת הדוא״ל שהוזנה. עד לאישור, אין גישה לתכנים ולהודעות של חברים.</p><a class="primary" href="/login">מעבר לכניסה לחשבון</a></div>'),202
        if not send_verification(email,uid):
            return layout("משלוח אימות",'<div class="pagehead"><h1>ההרשמה נשמרה, אבל המייל לא נשלח</h1><p>אפשר לנסות שוב דרך שליחת אימות מחדש. החשבון חסום לכניסה עד אימות הכתובת.</p><a href="/resend-verification" class="primary">שליחת אימות מחדש</a></div>'),503
        return layout("בקשת הצטרפות",'<div class="pagehead"><h1>בקשת ההצטרפות נשמרה</h1><p>הודעת האימות התקבלה במערכת השליחה. יש לאמת את הדוא״ל לפני הכניסה לחשבון.</p><a class="primary" href="/login">מעבר לכניסה</a></div>')
    return layout("הרשמה",'<section class="auth-page"><div class="pagehead"><span class="tag">חברות בקהילה</span><h1>מצטרפים לקרנפים</h1><p>חשבון אישי ומאובטח ליוצאי פלוגה ב׳. בקשת ההצטרפות תישלח לאישור מנהל. זהות החבר ובעלות על הדוא״ל יאומתו באופן אישי לפני מתן גישה לתוכן הפרטי.</p></div><div class="auth-trust"><span>🔒 חיבור מוצפן</span><span>◈ אישור מנהל לאחר אימות זהות</span><span>◈ קהילה לחברים מאושרים</span></div>'+
        button_form('<label>שם מלא<input name="name" required maxlength="90" autocomplete="name" placeholder="איך קוראים לך?"></label><label>כתובת דוא״ל<input name="email" type="email" inputmode="email" dir="ltr" required autocomplete="email" placeholder="you@example.com"></label>' + password_control("password","new-password") + '<p id="password-help" class="muted">לפחות 12 תווים. מומלץ להשתמש בסיסמה ייחודית.</p><input name="website" tabindex="-1" class="honeypot" aria-hidden="true"><label class="check"><input type="checkbox" name="agree" value="yes" required> אני מסכים לשמירת הפרטים לצורך קבלה לקהילה</label><button class="primary">שליחת בקשת הצטרפות</button>','/signup','class="formcard"')+'</section>')

def send_verification(email,uid):
    """Send a single-use email link with an explicitly selected API provider.

    Provider keys and verification tokens are never returned to the client.
    MAIL_DELIVERY_VERIFIED remains a separate deployment approval.
    """
    if not MAIL_READY:return False
    import json
    from urllib.request import Request,urlopen
    token=secrets.token_urlsafe(36)
    with connect() as c:
        with c.cursor() as cur:
            cur.execute("""INSERT INTO b2_tokens(user_id,digest,expires)
                VALUES(%s,%s,NOW()+INTERVAL '24 hours')
                ON CONFLICT(user_id) DO UPDATE
                SET digest=EXCLUDED.digest,expires=EXCLUDED.expires""",
                (uid,hashlib.sha256(token.encode()).hexdigest()))
    link=ORIGIN+"/verify-email?token="+token
    html='<p dir="rtl">לאימות כתובת הדוא״ל שלך באתר הקרנפים / ברקן: <a href="'+e(link)+'">לחצו כאן לאימות</a>. הקישור תקף 24 שעות.</p>'
    if EMAIL_TRANSPORT=="brevo":
        endpoint="https://api.brevo.com/v3/smtp/email"
        payload={"sender":{"name":"הקרנפים / ברקן","email":MAIL_FROM},
                 "to":[{"email":email}],"subject":"אימות דוא״ל — הקרנפים / ברקן",
                 "htmlContent":html}
        headers={"api-key":BREVO_API_KEY,"content-type":"application/json"}
    elif EMAIL_TRANSPORT=="resend":
        endpoint="https://api.resend.com/emails"
        payload={"from":MAIL_FROM,"to":[email],
                 "subject":"אימות דוא״ל — הקרנפים / ברקן","html":html}
        headers={"Authorization":"Bearer "+EMAIL_PROVIDER,
                 "Content-Type":"application/json"}
    else:
        return False
    req=Request(endpoint,data=json.dumps(payload).encode("utf-8"),
                headers=headers,method="POST")
    try:
        with urlopen(req,timeout=7) as result:
            return result.status in (200,201,202)
    except (OSError,TimeoutError):
        return False

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
        protect();limit("login-ip-total",30,15);limit("login:"+request.form.get("email","")[:200],9,15)
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
    permissions=staff_permissions()
    role=("מנהל הקהילה הראשי" if admin() else
          "צוות ניהול" if any(permissions.values()) else
          "חבר מאושר" if u["approved"] else "בקשת חברות בהמתנה לאישור")
    links=([('<a class="primary" href="/members">אישור חברים</a>' if permissions["approve"] else ''),
            ('<a href="/moderation">בקרת פרסומים</a>' if permissions["moderate"] else ''),
            ('<a href="/invite">הזמנת חברים</a>' if permissions["invite"] else ''),
            ('<a href="/team">ניהול הרשאות</a>' if admin() else '')])
    access=('<p>'+' '.join(x for x in links if x)+'</p>' if any(permissions.values()) else
            '<p>לאחר אימות זהות ואישור מנהל, ייפתחו הגישה לאיתור חברים ולהודעות.</p>'
            if not u["approved"] else '')
    return layout("פרופיל",'<div class="pagehead"><h1>הפרופיל שלי</h1><p>מעמד החשבון: '+e(role)+'</p>'+access+'</div>'+button_form(
        '<label>כינוי מתקופת השירות<input name="nickname" maxlength="100" value="'+e(u["nickname"])+'"></label><label>שנים / מחזור<input name="unit_year" maxlength="50" value="'+e(u["unit_year"] or "")+'"></label><label>מחזור גיוס (חודש ושנה)<input type="month" name="cohort" min="1990-01" max="2035-12" value="'+e(u["enlistment_cohort"])+'"></label><label>תפקיד בשירות<input name="service_role" maxlength="100" value="'+e(u["service_role"])+'" placeholder="לדוגמה: נהג מרכבה"></label><label>מחלקה / צוות<input name="platoon" maxlength="80" value="'+e(u["platoon"])+'"></label><label>כמה מילים עליך<textarea name="about" maxlength="500">'+e(u["about"])+'</textarea></label><label class="check"><input name="visible" type="checkbox" '+checked+'> הצגת הפרופיל לחברים מאושרים בלבד</label><button class="primary">שמירת הפרופיל</button>','/profile','class="formcard"')+button_form('<button class="subtle">התנתקות</button>','/logout'))

@app.post("/profile")
@require_login
def save_profile():
    protect()
    cohort=request.form.get("cohort","").strip()
    if cohort and not re.fullmatch(r"(19[9][0-9]|20[0-3][0-9])-(0[1-9]|1[0-2])",cohort):
        abort(400)
    role=request.form.get("service_role","").strip()[:100]
    platoon=request.form.get("platoon","").strip()[:80]
    sql("""UPDATE b2_users SET nickname=%s,unit_year=%s,about=%s,
           enlistment_cohort=%s,service_role=%s,platoon=%s,show_profile=%s WHERE id=%s""",
        (request.form.get("nickname","")[:100],request.form.get("unit_year","")[:50],
         request.form.get("about","")[:500],cohort,role,platoon,
         request.form.get("visible")=="on",g.user["id"]))
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
        cohort=request.form.get("album_cohort","").strip()
        if cohort and not re.fullmatch(r"(19[9][0-9]|20[0-3][0-9])-(0[1-9]|1[0-2])",cohort):
            abort(400)
        if kind not in ("story","photo","event","voice") or not title or request.form.get("rights")!="yes":abort(400)
        files=[v for v in request.files.getlist("uploads") if v and v.filename]
        if len(files)>4:abort(413)
        safe=[image_or_video(f) for f in files]
        if kind=="voice" and (len(safe)!=1 or safe[0][1]!="audio"):abort(400)
        if not body and not safe:abort(400)
        if sum(len(v[2]) for v in safe)>16*1024*1024:abort(413)
        decision,explanation,summary=("pending","ממתין לביקורת מנהל.","")
        if os.environ.get("BARKAN_AUTO_MODERATION","0")=="1":
            decision,explanation,summary=moderate_submission(title,body,kind,safe,bool(g.user["approved"]))
        with connect() as c:
            with c.cursor() as cur:
                cur.execute("""INSERT INTO b2_posts(author,title,body,kind,year_text,album_cohort,
                    status,moderation_reason,moderation_summary,moderation_source)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (g.user["id"],title,body,kind,year,cohort,decision,explanation,summary,
                     "rules-v1" if os.environ.get("BARKAN_AUTO_MODERATION","0")=="1" else "human-queue"))
                pid=cur.fetchone()["id"]
                for mime,typ,data in safe:
                    cur.execute("""INSERT INTO b2_media(post_id,owner,mime,kind,body,length)
                        VALUES(%s,%s,%s,%s,%s,%s)""",
                        (pid,g.user["id"],mime,typ,data,len(data)))
                cur.execute("""INSERT INTO b2_moderation_events(post_id,decision,reason,summary,source)
                    VALUES(%s,%s,%s,%s,%s)""",(pid,decision,explanation,summary,
                    "rules-v1" if os.environ.get("BARKAN_AUTO_MODERATION","0")=="1" else "human-queue"))
        return redirect("/my-posts",303)
    moderation_notice=('סיפורים כתובים ופשוטים של חברים מאושרים יכולים להתפרסם אחרי סינון אוטומטי. תמונות, סרטונים, הקלטות ותוכן רגיש מועברים לבדיקת צוות. לכל החלטה יוצג הסבר, ואפשר לבקש בדיקה חוזרת.' if os.environ.get("BARKAN_AUTO_MODERATION","0")=="1" else 'הפרסום יישמר פרטי עד אישור חברות וביקורת התוכן.')
    return layout("שיתוף סיפור",'<div class="pagehead"><h1>משתפים זיכרון</h1><p>'+e(moderation_notice)+'</p></div>'+button_form(
        '<label>סוג זיכרון<select name="kind"><option value="story">סיפור</option><option value="photo">תמונות או סרטון</option><option value="event">אירוע ומפגש</option><option value="voice">זיכרון קולי</option></select></label><label>כותרת<input name="title" required maxlength="120"></label><label>שנה (לא חובה)<input name="year" maxlength="30"></label><label>אלבום מחזור גיוס (אופציונלי)<input type="month" name="album_cohort" min="1990-01" max="2035-12"></label><label>תוכן<textarea name="body" maxlength="4000" rows="6"></textarea></label><label>קבצים (עד ארבעה)<input id="story-uploads" type="file" name="uploads" multiple accept="image/jpeg,image/png,image/webp,video/mp4,video/webm,audio/webm,audio/ogg"></label><section class="story" data-voice-recorder hidden><h2>הקלטת זיכרון מהמיקרופון</h2><p>ההקלטה מתחילה רק בלחיצה על התחלה. ניתן להאזין לפני שליחה. הקובץ לא נשלח עד ללחיצה על ״שליחה לביקורת״.</p><div class="hero-actions"><button type="button" class="outline" data-record-start>התחלת הקלטה</button><button type="button" class="subtle" data-record-stop disabled>עצירת הקלטה</button></div><p role="status" aria-live="polite" data-record-status>לא הוקלט עדיין.</p><audio controls preload="none" data-record-preview hidden></audio></section><p class="muted">עד 8MB לקובץ ו־16MB סך הכול לפרסום. תמונות יעברו כיווץ והסרת נתוני EXIF. להקלטות קוליות יש לבחור ״זיכרון קולי״ ולצרף קובץ WebM או OGG אחד, או להשתמש בהקלטה הישירה אם הדפדפן תומך.</p><label class="check"><input type="checkbox" name="rights" value="yes" required> אני מאשר שיש לי זכויות לפרסם את התוכן</label><button class="primary">שליחה לביקורת</button>',
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
    m=sql("""SELECT f.*,p.status post_status,
             author.approved author_approved
      FROM b2_media f LEFT JOIN b2_posts p ON p.id=f.post_id
      LEFT JOIN b2_users author ON author.id=p.author
      WHERE f.id=%s""",(mid,),True)
    if not m:abort(404)
    can_post=bool(m["post_id"] and (u["id"]==m["owner"] or
                  (u["approved"] and
                   (staff_permissions()["moderate"] or
                    (m["post_status"]=="published" and m["author_approved"])))))
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
        status=({"published":"פורסם","pending":"ממתין לבדיקה","rejected":"לא אושר","hidden":"הוסתר לבדיקת פרטיות"}).get(p["status"],"בבדיקה")
        reasoning=('<p><strong>הסבר החלטה: </strong>'+e(p["moderation_reason"])+'</p>' if p["moderation_reason"] else '')
        digest=('<p><strong>תקציר שנוצר אוטומטית: </strong>'+e(p["moderation_summary"])+'</p>' if p["moderation_summary"] else '')
        appeal=(button_form('<input type="hidden" name="id" value="'+str(p["id"])+'"><button class="subtle">בקשת בדיקה חוזרת</button>','/my-posts/appeal')
                if p["status"]=="rejected" and not p["appealed"] else '')
        items+='<article class="post"><span class="tag">'+status+'</span><h2>'+e(p["title"])+'</h2><p>'+e(p["body"])+'</p>'+reasoning+digest+'<div class="media-grid">'+''.join(media_html(f["id"],f["kind"]) for f in files)+'</div>'+appeal+'</article>'
    return layout("הפרסומים שלי",'<div class="pagehead"><h1>הפרסומים שלי</h1><p>רק אתה והמנהל רואים פרסומים שעדיין לא אושרו.</p><a class="primary" href="/new">פרסום חדש</a></div>'+(items or '<div class="note">אין לך עדיין פרסומים.</div>'))

@app.post("/my-posts/appeal")
@require_login
def moderation_appeal():
    protect();limit("moderation-appeal:"+str(g.user["id"]),5,3600)
    raw=request.form.get("id","")
    if not raw.isdecimal():abort(400)
    with connect() as c:
        with c.cursor() as cur:
            cur.execute("""UPDATE b2_posts SET status='pending',appealed=TRUE,
                moderation_reason='המשתמש ביקש בדיקה חוזרת; ממתין לבקרת מנהל.'
                WHERE id=%s AND author=%s AND status='rejected' AND appealed=FALSE RETURNING id""",
                (int(raw),g.user["id"]))
            if not cur.fetchone():abort(409)
            cur.execute("""INSERT INTO b2_moderation_events(post_id,decision,reason,source)
                VALUES(%s,'pending','Appeal requested by author','appeal')""",(int(raw),))
    return redirect("/my-posts",303)

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

@app.get("/voices")
@require_approved
def voice_archive():
    """Opt-in published voice histories, without external audio or transcription."""
    cohort=request.args.get("cohort","").strip()
    if cohort and not re.fullmatch(r"(19[9][0-9]|20[0-3][0-9])-(0[1-9]|1[0-2])",cohort):
        abort(400)
    rows=sql("""SELECT p.title,p.body,p.year_text,p.album_cohort,
                       u.name,f.id media_id
        FROM b2_posts p JOIN b2_media f ON f.post_id=p.id
        JOIN b2_users u ON u.id=p.author
        WHERE p.kind='voice' AND p.status='published' AND u.approved=TRUE
          AND f.kind='audio' AND (%s='' OR p.album_cohort=%s)
        ORDER BY p.created DESC,p.id DESC LIMIT 60""",(cohort,cohort))
    cohorts=sql("""SELECT p.album_cohort,COUNT(DISTINCT p.id) AS n
        FROM b2_posts p JOIN b2_media f ON f.post_id=p.id
        JOIN b2_users u ON u.id=p.author
        WHERE p.kind='voice' AND p.status='published' AND u.approved=TRUE
          AND f.kind='audio' AND p.album_cohort<>''
        GROUP BY p.album_cohort ORDER BY p.album_cohort DESC LIMIT 120""")
    opts=''.join('<option value="'+e(r["album_cohort"])+'"'+
                 (' selected' if cohort==r["album_cohort"] else '')+'>'+
                 e(r["album_cohort"])+' ('+str(r["n"])+')</option>' for r in cohorts)
    cards=''.join('<article class="post"><span class="tag">מורשת קולית</span><h2>'+
        e(row["title"])+'</h2><p>'+e(row["name"])+' · '+e(row["album_cohort"] or row["year_text"] or "כללי")+
        '</p><p>'+e(row["body"])+'</p>'+
        '<audio controls preload="none" src="/media/'+str(row["media_id"])+
        '">נגן הקול אינו זמין בדפדפן זה.</audio></article>' for row in rows)
    form=('<form action="/voices" method="get" class="search"><label>סינון מחזור גיוס'
          '<select name="cohort"><option value="">כל המחזורים</option>'+
          opts+'</select></label><button class="primary">הצגת הקלטות</button></form>')
    return layout("מורשת קולית",'<div class="pagehead"><h1>הקולות והסיפורים של הפלוגה</h1><p>סיפורי שירות מוקלטים של חברים מאושרים, רק לאחר בדיקת תוכן. אין להקליט אחרים ללא הסכמתם או לחשוף מידע צבאי רגיש.</p><a class="primary" href="/new">שיתוף זיכרון קולי</a></div>'+form+
         (cards or '<div class="note">אין עדיין הקלטות מאושרות במחזור שנבחר.</div>'))


COHORT_PATTERN=r"(19[9][0-9]|20[0-3][0-9])-(0[1-9]|1[0-2])"

@app.get("/cohorts")
@require_approved
def cohort_directory():
    """A member-only index derived exclusively from opt-in profiles and
    previously approved records; never disclose non-opt-in member rosters."""
    rows=sql("""SELECT cohort,COUNT(*) AS items FROM (
        SELECT enlistment_cohort AS cohort FROM b2_users
          WHERE approved=TRUE AND show_profile=TRUE AND enlistment_cohort<>''
        UNION ALL
        SELECT p.album_cohort AS cohort FROM b2_posts p
          JOIN b2_users u ON u.id=p.author
          WHERE p.status='published' AND u.approved=TRUE AND p.album_cohort<>''
    ) indexed GROUP BY cohort ORDER BY cohort DESC LIMIT 120""")
    cards=''.join('<a class="person" href="/cohorts/'+e(r["cohort"])+'"><h2>מחזור '+
        e(r["cohort"])+'</h2><p>חברים שבחרו להופיע ותכני מורשת מאושרים · '+
        str(r["items"])+' רשומות משויכות</p></a>' for r in rows)
    return layout("ספר המחזורים",'<div class="pagehead"><h1>ספר מחזורי הפלוגה</h1><p>מרחב משותף לתמונות, סיפורים וקולות השירות. הספירה כוללת פרסומים ופרופילים גלויים בהסכמה — לא רשימת גיוס רשמית.</p></div><section class="people">'+
        (cards or '<div class="note">עדיין אין מחזורים עם תכנים מאושרים או פרופילים שהסכימו להופיע.</div>')+
        '</section><p><a href="/profile">עדכון המחזור והעדפות הפרטיות שלי</a></p>')

@app.get("/cohorts/<cohort>")
@require_approved
def cohort_page(cohort):
    if not re.fullmatch(COHORT_PATTERN,cohort):abort(404)
    members=sql("""SELECT id,name,nickname,service_role,platoon FROM b2_users
        WHERE approved=TRUE AND show_profile=TRUE AND enlistment_cohort=%s
        ORDER BY name LIMIT 60""",(cohort,))
    posts=sql("""SELECT p.id,p.title,p.body,p.kind,p.year_text,u.name
        FROM b2_posts p JOIN b2_users u ON u.id=p.author
        WHERE p.album_cohort=%s AND p.status='published' AND u.approved=TRUE
        ORDER BY p.created DESC,p.id DESC LIMIT 50""",(cohort,))
    member_cards=''
    for u in members:
        context=' · '.join(e(v) for v in (u["nickname"],u["service_role"],u["platoon"]) if v)
        member_cards+='<article class="person"><h3>'+e(u["name"])+'</h3><p>'+context+'</p><a href="/chat/'+str(u["id"])+'">הודעה פרטית</a></article>'
    photo_count=0
    voice_count=0
    stories=''
    for p in posts:
        files=sql("SELECT id,kind FROM b2_media WHERE post_id=%s ORDER BY id LIMIT 4",(p["id"],))
        images=[x for x in files if x["kind"]=="image"]
        audio=[x for x in files if x["kind"]=="audio"]
        photo_count+=len(images)
        voice_count+=len(audio)
        stories+='<article class="post"><h3>'+e(p["title"])+'</h3><p>'+e(p["name"])+' · '+e(p["year_text"])+'</p><p>'+e(p["body"])+'</p><div class="media-grid">'+''.join(media_html(f["id"],f["kind"]) for f in files)+'</div></article>'
    empty='<div class="note">אין עדיין פרסומים מאושרים במחזור הזה.</div>'
    quick=('<nav class="album-nav" aria-label="קישורי מחזור">'
           '<a class="outline" href="/photos?cohort='+e(cohort)+'">אלבום התמונות ('+str(photo_count)+')</a> '
           '<a class="outline" href="/voices?cohort='+e(cohort)+'">הקלטות ('+str(voice_count)+')</a> '
           '<a class="outline" href="/find?cohort='+e(cohort)+'">איתור חברים</a> '
           '<a class="outline" href="/meetups">לוח מפגשים כללי</a></nav>')
    return layout("מחזור "+cohort,'<div class="pagehead"><h1>מחזור גיוס '+e(cohort)+'</h1><p>הזיכרונות והחברים של המחזור במקום אחד. המפגשים הם כלל-פלוגתיים, ואינם משויכים אוטומטית למחזור.</p></div>'+quick+
        '<section class="story"><h2>חברים שבחרו להופיע ('+str(len(members))+')</h2><div class="people">'+
        (member_cards or '<div class="note">אף חבר במחזור לא בחר עדיין להציג פרופיל.</div>')+
        '</div></section><section class="story"><h2>סיפורים ותיעוד ('+str(len(posts))+')</h2>'+
        (stories or empty)+'</section><p><a class="primary" href="/new">הוספת זיכרון לביקורת</a> <a href="/cohorts">בחזרה לספר המחזורים</a></p>')

@app.get("/find")
@require_approved
def find():
    # Only approved members who explicitly opt in are searchable.
    term=request.args.get("q","").strip()[:80]
    cohort=request.args.get("cohort","").strip()
    if cohort and not re.fullmatch(r"(19[9][0-9]|20[0-3][0-9])-(0[1-9]|1[0-2])",cohort):
        abort(400)
    # Escape LIKE wildcards so searching for % or _ does not enumerate the directory.
    escaped=term.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")
    needle="%"+escaped+"%"
    matches=[]
    if term or cohort:
        matches=sql("""SELECT id,name,nickname,unit_year,about,enlistment_cohort,
                               service_role,platoon FROM b2_users
            WHERE approved=TRUE AND show_profile=TRUE
              AND (%s='' OR enlistment_cohort=%s)
              AND (%s='' OR name ILIKE %s ESCAPE '\\'
                        OR nickname ILIKE %s ESCAPE '\\'
                        OR unit_year ILIKE %s ESCAPE '\\'
                        OR service_role ILIKE %s ESCAPE '\\'
                        OR platoon ILIKE %s ESCAPE '\\')
            ORDER BY name LIMIT 30""",
            (cohort,cohort,term,needle,needle,needle,needle,needle))
    cohorts=sql("""SELECT enlistment_cohort,COUNT(*) AS n FROM b2_users
        WHERE approved=TRUE AND show_profile=TRUE AND enlistment_cohort<>''
        GROUP BY enlistment_cohort ORDER BY enlistment_cohort DESC LIMIT 120""")
    options=''.join('<option value="'+e(c["enlistment_cohort"])+'"'+
                    (' selected' if cohort==c["enlistment_cohort"] else '')+'>'+
                    e(c["enlistment_cohort"])+' ('+str(c["n"])+')</option>' for c in cohorts)
    cards=''
    for m in matches:
        details=' · '.join(e(v) for v in
             (m["nickname"],m["unit_year"],m["enlistment_cohort"],
              m["service_role"],m["platoon"]) if v)
        cards+='<article class="person"><h3>'+e(m["name"])+'</h3><p>'+details+'</p><p>'+e(m["about"])+'</p><a href="/chat/'+str(m["id"])+'">שליחת הודעה פרטית</a></article>'
    form=('<form class="search" method="get" action="/find"><label>שם, כינוי, תפקיד או מחלקה'
          '<input name="q" value="'+e(term)+'" maxlength="80"></label>'
          '<label>מחזור גיוס<select name="cohort"><option value="">כל המחזורים</option>'+
          options+'</select></label><button class="primary">חיפוש חברים</button></form>')
    return layout("איתור חברים",'<div class="pagehead"><h1>ספר המחזורים ואיתור החברים</h1><p>החיפוש פתוח לחברים מאושרים בלבד ומציג רק חברים שבחרו להופיע בו. אין פרסום של כתובות דוא״ל או טלפונים.</p></div>'+form+'<section class="people">'+(cards or '<div class="note">לא נמצאו פרופילים גלויים בהתאם לחיפוש.</div>')+'</section>')

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
    if not staff_permissions()["moderate"]:abort(403)
    if request.method=="POST":
        protect()
        pid=request.form.get("id","")
        action=request.form.get("action","")
        if not pid.isdecimal() or action not in ("publish","reject"):abort(400)
        if action=="publish":
            note="אושר לאחר בדיקת צוות הבקרה."
            result=sql("""UPDATE b2_posts p SET status='published',
                moderation_reason=%s,moderation_source='human'
                FROM b2_users u WHERE p.id=%s AND p.author=u.id AND u.approved=TRUE
                AND p.status='pending' RETURNING p.id""",(note,int(pid)),True)
            if not result:abort(409)
        else:
            note=request.form.get("reason","").strip()[:700]
            if len(note)<8:
                return layout("נדרש הסבר",'<section class="note error">כדי לדחות פרסום, יש להזין הסבר ברור לחבר. <a href="/moderation">חזרה לבקרה</a></section>'),400
            result=sql("""UPDATE b2_posts SET status='rejected',
                 moderation_reason=%s,moderation_source='human'
                 WHERE id=%s AND status='pending' RETURNING id""",(note,int(pid)),True)
            if not result:abort(409)
        sql("""INSERT INTO b2_moderation_events(post_id,decision,reason,source)
            VALUES(%s,%s,%s,'human')""",(int(pid),
             "published" if action=="publish" else "rejected",note))
        return redirect("/moderation",303)
    posts=sql("""SELECT p.*,u.name,u.approved FROM b2_posts p
        JOIN b2_users u ON u.id=p.author WHERE p.status='pending'
        ORDER BY p.created DESC LIMIT 60""")
    cards=''
    for p in posts:
        files=sql("SELECT id,kind FROM b2_media WHERE post_id=%s",(p["id"],))
        controls=('<button name="action" value="publish" class="primary">אישור לפרסום</button>' if p["approved"] else '<span>נדרש קודם אישור החבר</span>')
        controls+='<label>נימוק לדחייה<input name="reason" maxlength="700" placeholder="מה נדרש לתקן כדי לאשר?"></label><button name="action" value="reject" class="subtle">דחיית פרסום עם הסבר</button>'
        cards+='<article class="post"><h2>'+e(p["title"])+'</h2><p>מאת '+e(p["name"])+'</p><p>'+e(p["body"])+'</p><div class="media-grid">'+''.join(media_html(f["id"],f["kind"]) for f in files)+'</div>'+button_form('<input type="hidden" name="id" value="'+str(p["id"])+'">'+controls,'/moderation')+'</article>'
    return layout("בקרת פרסומים",'<div class="pagehead"><h1>בקרת פרסומים</h1></div>'+(cards or '<p>אין פרסומים ממתינים.</p>'))

@app.route("/members",methods=["GET","POST"])
@require_approved
def members():
    if not staff_permissions()["approve"]:abort(403)
    if request.method=="POST":
        protect()
        uid=request.form.get("id","")
        if not uid.isdecimal() or request.form.get("action") not in ("approve","reject"):abort(400)
        if int(uid)==g.user["id"]:abort(400)
        approved=request.form["action"]=="approve"
        if approved and request.form.get("identity_checked")!="yes":
            return layout("נדרש אימות",'<div class="note error">לפני אישור חבר יש לאמת מחוץ לאתר את זהותו, שייכותו לפלוגה ואת בעלותו על כתובת הדוא״ל. <a href="/members">חזרה לבקשות</a></div>'),400
        with connect() as c:
            with c.cursor() as cur:
                cur.execute("""UPDATE b2_users SET approved=%s WHERE id=%s
                    AND approved=FALSE RETURNING id""",(approved,int(uid)))
                changed=cur.fetchone()
                if not changed:abort(409)
                cur.execute("""INSERT INTO b2_admin_audit(actor,subject,action,detail)
                    VALUES(%s,%s,%s,%s)""",(g.user["id"],int(uid),
                    "member_approved" if approved else "member_rejected",
                    "identity manually checked" if approved else "application rejected"))
        return redirect("/members",303)
    rows=sql("SELECT id,name,email,joined FROM b2_users WHERE approved=FALSE ORDER BY joined DESC LIMIT 100")
    html=''
    for u in rows:
        html+='<article class="person"><h3>'+e(u["name"])+'</h3><p>'+e(u["email"])+'</p>'+button_form(
            '<input type="hidden" name="id" value="'+str(u["id"])+'"><label class="check"><input type="checkbox" name="identity_checked" value="yes"> אימתתי באופן אישי את זהות החבר, שייכותו לפלוגה ובעלותו על כתובת הדוא״ל</label><button name="action" value="approve" class="primary">אישור חבר</button><button name="action" value="reject" class="subtle">דחייה</button>','/members')+'</article>'
    return layout("אישור חברים",'<div class="pagehead"><h1>בקשות חברות</h1></div>'+(html or '<div class="note">אין בקשות חברות ממתינות.</div>'))


@app.route("/team",methods=["GET","POST"])
@require_approved
def manage_team():
    """Owner-only permission delegation; never change ownership here."""
    if not admin():abort(403)
    if request.method=="POST":
        protect()
        limit("role-change:"+str(g.user["id"]),30,60)
        uid=request.form.get("id","")
        if not uid.isdecimal():abort(400)
        uid=int(uid)
        if uid==g.user["id"]:abort(403)
        target=sql("SELECT id,approved,email_verification_required,email FROM b2_users WHERE id=%s",(uid,),True)
        if not target or not target["approved"] or target["email_verification_required"]:
            abort(403)
        if target["email"].lower()==os.environ.get("BARKAN_ADMIN_EMAIL","").lower():
            abort(403)
        action=request.form.get("action")
        if action not in ("save","revoke"):abort(400)
        # Role mutation and its audit event must commit together.
        with connect() as c:
            with c.cursor() as cur:
                if action=="revoke":
                    cur.execute("DELETE FROM b2_staff_roles WHERE user_id=%s",(uid,))
                    record="roles_revoked"
                    detail="all permissions revoked"
                else:
                    a=request.form.get("can_approve")=="yes"
                    m=request.form.get("can_moderate")=="yes"
                    i=request.form.get("can_invite")=="yes"
                    cur.execute("""INSERT INTO b2_staff_roles(user_id,can_approve,can_moderate,can_invite,granted_by)
                        VALUES(%s,%s,%s,%s,%s) ON CONFLICT(user_id) DO UPDATE SET
                        can_approve=EXCLUDED.can_approve,can_moderate=EXCLUDED.can_moderate,
                        can_invite=EXCLUDED.can_invite,granted_by=EXCLUDED.granted_by,
                        updated=NOW()""",(uid,a,m,i,g.user["id"]))
                    record="roles_saved"
                    detail="approve="+str(a)+",moderate="+str(m)+",invite="+str(i)
                cur.execute("""INSERT INTO b2_admin_audit(actor,subject,action,detail)
                    VALUES(%s,%s,%s,%s)""",(g.user["id"],uid,record,detail))
        return redirect("/team",303)
    rows=sql("""SELECT u.id,u.name,u.email,u.approved,
               COALESCE(r.can_approve,FALSE) can_approve,
               COALESCE(r.can_moderate,FALSE) can_moderate,
               COALESCE(r.can_invite,FALSE) can_invite
        FROM b2_users u LEFT JOIN b2_staff_roles r ON r.user_id=u.id
        WHERE u.approved=TRUE AND u.id<>%s AND u.email_verification_required=FALSE
        ORDER BY u.name LIMIT 150""",(g.user["id"],))
    cards=''
    for person in rows:
        check=lambda key: ' checked' if person[key] else ''
        form=('<input type="hidden" name="id" value="'+str(person["id"])+'">'
              '<label class="check"><input type="checkbox" name="can_approve" value="yes"'+check("can_approve")+'> אישור חברים אחרי אימות זהות</label>'
              '<label class="check"><input type="checkbox" name="can_moderate" value="yes"'+check("can_moderate")+'> ביקורת פרסומים</label>'
              '<label class="check"><input type="checkbox" name="can_invite" value="yes"'+check("can_invite")+'> גיוס והזמנת חברים</label>'
              '<button class="primary" name="action" value="save">שמירת הרשאות</button> '
              '<button class="subtle" name="action" value="revoke">ביטול כל ההרשאות</button>')
        cards+='<article class="person"><h2>'+e(person["name"])+'</h2><p>'+e(person["email"])+'</p>'+button_form(form,"/team",'class="formcard"')+'</article>'
    events=sql("""SELECT audit.action,audit.detail,audit.created,
                 actor.name actor_name,subject.name subject_name
        FROM b2_admin_audit audit
        JOIN b2_users actor ON actor.id=audit.actor
        JOIN b2_users subject ON subject.id=audit.subject
        ORDER BY audit.created DESC,audit.id DESC LIMIT 25""")
    labels={"roles_saved":"הרשאות נשמרו","roles_revoked":"הרשאות בוטלו",
            "member_approved":"חבר אושר","member_rejected":"בקשת חברות נדחתה"}
    activity=''.join('<li><strong>'+e(labels.get(event["action"],"פעולת ניהול"))+
        '</strong> · '+e(event["subject_name"])+' · בוצע על ידי '+e(event["actor_name"])+
        ' · '+e(event["created"].strftime("%d/%m/%Y %H:%M"))+'</li>' for event in events)
    history=('<section class="story"><h2>פעולות ניהול אחרונות</h2><ol>'+
             (activity or '<li>לא נרשמו עדיין פעולות.</li>')+'</ol></section>')
    return layout("ניהול הרשאות",'<div class="pagehead"><h1>צוות ניהול והרשאות</h1><p>רק מנהל הקהילה הראשי יכול למנות בעלי תפקידים או לבטל הרשאות. אפשר לשלב כמה תפקידים לאותו חבר מאושר. כל שינוי תקף גם לסשנים קיימים.</p></div>'+(cards or '<div class="note">עדיין אין חברים מאושרים נוספים למינוי. ניתן להזמין חברים דרך קישור ההרשמה.</div>')+history)

@app.get("/invite")
@require_approved
def invite_members():
    if not staff_permissions()["invite"]:abort(403)
    signup=ORIGIN+"/signup"
    whatsapp="https://wa.me/?text="+__import__("urllib.parse",fromlist=["quote"]).quote("חברי פלוגה ב׳ הקרנפים / ברקן — מוזמנים להירשם לקהילה שלנו: "+signup,safe="")
    return layout("מזמינים חברים",'<div class="pagehead"><h1>מחזירים את החברים הביתה</h1><p>שלחו את קישור ההרשמה ישירות לחברים מהפלוגה. ההרשמה אינה מקנה גישה לפני אישור זהות ושייכות לפלוגה.</p></div><section class="story"><p><a class="primary" href="'+e(signup)+'">פתיחת הרשמה</a> <a class="outline" href="'+e(whatsapp)+'" target="_blank" rel="noopener noreferrer">שיתוף הזמנה בוואטסאפ</a></p><p dir="ltr">'+e(signup)+'</p><p>נא לא לפרסם רשימות טלפונים או פרטים אישיים של חברים ללא הסכמתם.</p></section>')


@app.route("/meetups",methods=["GET","POST"])
@require_approved
def meetups():
    """Private reunion calendar; all event data and attendance stay members-only."""
    can_manage=staff_permissions()["moderate"]
    if request.method=="POST":
        if not can_manage:abort(403)
        protect();limit("meetup-admin:"+str(g.user["id"]),12,60)
        title=request.form.get("title","").strip()
        details=request.form.get("details","").strip()
        location=request.form.get("location","").strip()
        begins=request.form.get("when","").strip()
        if not 3<=len(title)<=120 or len(details)>1500 or len(location)>180:abort(400)
        try:
            start=datetime.fromisoformat(begins)
            if start.tzinfo is not None:abort(400)
            # datetime-local is explicitly local Israel time; convert to UTC.
            from zoneinfo import ZoneInfo
            start=start.replace(tzinfo=ZoneInfo("Asia/Jerusalem")).astimezone(timezone.utc)
            if not datetime.now(timezone.utc)<start or start.year>datetime.now(timezone.utc).year+3:abort(400)
        except (ValueError,TypeError,OverflowError):abort(400)
        sql("""INSERT INTO b2_meetups(creator,title,details,location_text,starts_at)
            VALUES(%s,%s,%s,%s,%s)""",(g.user["id"],title,details,location,start))
        return redirect("/meetups",303)
    events=sql("""SELECT m.id,m.title,m.details,m.location_text,m.starts_at,m.cancelled,
             (SELECT COUNT(*) FROM b2_meetup_rsvps r WHERE r.meetup_id=m.id AND r.attending=TRUE) attending_count,
             EXISTS(SELECT 1 FROM b2_meetup_rsvps r WHERE r.meetup_id=m.id
                    AND r.user_id=%s AND r.attending=TRUE) my_attendance
             FROM b2_meetups m WHERE m.starts_at>=NOW()-INTERVAL '90 days'
             ORDER BY m.starts_at ASC LIMIT 60""",(g.user["id"],))
    cards=''
    for event in events:
        eid=str(event["id"])
        date=event["starts_at"].astimezone(__import__("zoneinfo",fromlist=["ZoneInfo"]).ZoneInfo("Asia/Jerusalem")).strftime("%d/%m/%Y %H:%M")
        controls='<p>מפגש בוטל</p>' if event["cancelled"] else (
            button_form('<input type="hidden" name="id" value="'+eid+'">'+
                ('<button class="subtle" name="decision" value="no">ביטול השתתפות</button>'
                 if event["my_attendance"] else '<button class="primary" name="decision" value="yes">אני מגיע/ה</button>'),
                "/meetups/rsvp",'class="formcard"')
            if event["starts_at"]>datetime.now(timezone.utc) else '<p>המפגש הסתיים</p>')
        if can_manage and not event["cancelled"]:
            controls+=button_form('<input type="hidden" name="id" value="'+eid+'"><button name="action" value="cancel" class="subtle">ביטול המפגש</button>',"/meetups/manage")
        cards+='<article class="post"><h2>'+e(event["title"])+'</h2><p><strong>מועד: </strong>'+e(date)+'</p><p><strong>מיקום: </strong>'+e(event["location_text"] or "יעודכן בהמשך")+'</p><p>'+e(event["details"])+'</p><p>אישורי הגעה: '+str(event["attending_count"])+'</p>'+controls+'</article>'
    form=button_form('<label>שם המפגש<input name="title" maxlength="120" required></label><label>תאריך ושעה<input type="datetime-local" name="when" required></label><label>מיקום כללי<input name="location" maxlength="180"></label><label>פרטים נוספים<textarea name="details" maxlength="1500" rows="4"></textarea></label><button class="primary">יצירת מפגש</button>','/meetups','class="formcard"') if can_manage else ''
    return layout("מפגשי הפלוגה",'<div class="pagehead"><h1>מפגשי הקרנפים / ברקן</h1><p>תכנון מפגשים ואישורי הגעה — גלויים לחברי הקהילה המאושרים בלבד. אין להעלות כתובות פרטיות ללא הסכמה.</p></div>'+('<section class="story"><h2>ארגון מפגש חדש</h2>'+form+'</section>' if form else '')+(cards or '<div class="note">טרם נקבעו מפגשים חדשים.</div>'))

@app.post("/meetups/rsvp")
@require_approved
def meetup_rsvp():
    protect();limit("meetup-rsvp:"+str(g.user["id"]),25,60)
    eid=request.form.get("id","")
    decision=request.form.get("decision","")
    if not eid.isdecimal() or decision not in ("yes","no"):abort(400)
    with connect() as c:
        with c.cursor() as cur:
            cur.execute("SELECT id FROM b2_meetups WHERE id=%s AND cancelled=FALSE AND starts_at>NOW()",(int(eid),))
            if not cur.fetchone():abort(404)
            cur.execute("""INSERT INTO b2_meetup_rsvps(meetup_id,user_id,attending)
                VALUES(%s,%s,%s) ON CONFLICT(meetup_id,user_id)
                DO UPDATE SET attending=EXCLUDED.attending,updated=NOW()""",
                (int(eid),g.user["id"],decision=="yes"))
    return redirect("/meetups",303)

@app.post("/meetups/manage")
@require_approved
def meetup_manage():
    if not staff_permissions()["moderate"]:abort(403)
    protect();limit("meetup-cancel:"+str(g.user["id"]),12,60)
    eid=request.form.get("id","")
    if not eid.isdecimal() or request.form.get("action")!="cancel":abort(400)
    result=sql("UPDATE b2_meetups SET cancelled=TRUE WHERE id=%s AND cancelled=FALSE RETURNING id",(int(eid),),True)
    if not result:abort(404)
    return redirect("/meetups",303)


@app.get("/dashboard")
@require_approved
def dashboard():
    """Owner-only operational overview without exposing account information publicly."""
    if not admin():abort(403)
    summary=sql("""SELECT
        (SELECT COUNT(*) FROM b2_users) AS total_members,
        (SELECT COUNT(*) FROM b2_users WHERE approved=TRUE) AS approved_members,
        (SELECT COUNT(*) FROM b2_users WHERE approved=FALSE) AS pending_members,
        (SELECT COUNT(*) FROM b2_posts WHERE status='pending') AS pending_posts,
        (SELECT COUNT(*) FROM b2_photo_memories WHERE status='pending') AS pending_memories,
        (SELECT COUNT(*) FROM b2_photo_reports WHERE status='open') AS privacy_requests,
        (SELECT COUNT(*) FROM b2_meetups WHERE starts_at>NOW() AND cancelled=FALSE) AS upcoming_meetups,
        (SELECT COUNT(*) FROM b2_posts WHERE status='published') AS published_posts,
        (SELECT COUNT(*) FROM b2_posts WHERE status='rejected') AS rejected_posts,
        (SELECT COUNT(*) FROM b2_posts WHERE moderation_source='rules-v1'
            AND status='published') AS auto_published,
        (SELECT COUNT(*) FROM b2_staff_roles
            WHERE can_approve OR can_moderate OR can_invite) AS delegates""",one=True)
    items=[
        ("בקשות הצטרפות",summary["pending_members"],"/members","חברים הממתינים לאימות ואישור"),
        ("פרסומים לביקורת",summary["pending_posts"],"/moderation","סיפורים, תמונות והקלטות שממתינים לאישור"),
        ("פרסומים אוטומטיים",summary["auto_published"],"/feed","סיפורים טקסטואליים שעברו סינון אוטומטי"),
        ("פרסומים שנדחו",summary["rejected_posts"],"/moderation","החלטות שתועדו עם נימוק; ערעורים חוזרים לתור הבקרה"),
        ("זיכרונות לתמונות",summary["pending_memories"],"/photo-review","תגובות וזיכרונות הממתינים לבקרה"),
        ("בקשות פרטיות",summary["privacy_requests"],"/photo-review","בקשות להסרה או לבדיקת תמונות"),
        ("מפגשים מתוכננים",summary["upcoming_meetups"],"/meetups","מפגשי פלוגה עתידיים"),
        ("חברי צוות מורשים",summary["delegates"],"/team","חברים בעלי תפקידי ניהול מוגבלים")
    ]
    tiles=''.join('<a class="person" href="'+url+'"><h2>'+e(label)+'</h2>'
        '<p><strong>'+str(value)+'</strong> · '+e(description)+'</p></a>'
        for label,value,url,description in items)
    recent=sql("""SELECT action,created,actor.name actor_name,subject.name subject_name
        FROM b2_admin_audit audit JOIN b2_users actor ON actor.id=audit.actor
        JOIN b2_users subject ON subject.id=audit.subject
        ORDER BY audit.created DESC,audit.id DESC LIMIT 10""")
    labels={"roles_saved":"עדכון הרשאות","roles_revoked":"ביטול הרשאות",
        "member_approved":"אישור חבר","member_rejected":"דחיית בקשה"}
    history=''.join('<li>'+e(labels.get(row["action"],"פעולת ניהול"))+
                    ' · '+e(row["subject_name"])+' · '+e(row["actor_name"])+
                    ' · '+e(row["created"].strftime("%d/%m/%Y %H:%M"))+'</li>' for row in recent)
    overview=('<section class="story"><h2>מצב הקהילה</h2><p>חברים רשומים: <strong>'+
        str(summary["total_members"])+'</strong> · חברים מאושרים: <strong>'+
        str(summary["approved_members"])+'</strong> · פרסומים מאושרים: <strong>'+
        str(summary["published_posts"])+'</strong></p></section>')
    activity=('<section class="story"><h2>פעילות ניהול אחרונה</h2><ol>'+
             (history or '<li>אין פעולות חדשות.</li>')+'</ol></section>')
    return layout("לוח בקרה",'<div class="pagehead"><h1>לוח הבקרה של מנהל הקהילה</h1><p>תמונת מצב עדכנית. הנתונים נגישים למנהל הראשי בלבד ומחושבים מתוך מסד הנתונים.</p></div>'+overview+
                  '<section class="people" aria-label="משימות ניהול">'+tiles+'</section>'+activity)

@app.errorhandler(404)
def not_found(err):return layout("העמוד לא נמצא",'<div class="pagehead"><h1>העמוד לא נמצא</h1><a href="/">חזרה לדף הבית</a></div>'),404

@app.errorhandler(403)
def forbidden(err):return layout("גישה מוגבלת",'<div class="pagehead"><h1>גישה מוגבלת</h1><p>יש צורך בחברות מאושרת או בהרשאה מתאימה.</p></div>'),403

@app.errorhandler(503)
def maintenance(err):return layout("מערכת החברים בהכנה",'<div class="pagehead"><h1>החברים חוזרים לכאן בקרוב</h1><p>המערכת האישית סגורה עד בדיקות בטיחות ואבטחה; בינתיים אפשר לעיין במורשת ובהנצחה.</p><a href="/" class="primary">לעמוד הבית</a></div>'),503

if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
