"""Local email confirmation by one-time HTTPS delivery; no social-login provider.

The outbound email transport is an HTTPS transactional API because Render's free
web instances cannot connect to standard outbound SMTP ports.
"""
import hashlib
import html
import os
import re
import secrets
from urllib import request as http

PUBLIC_ORIGIN="https://karnafim-community-46.onrender.com"

def mail_transport():
    """Mail route is server-selected; the website never receives Gmail credentials."""
    if os.getenv("KARNAFIM_MAIL_TRANSPORT","").strip().lower()=="gmail_queue":
        return "gmail_queue"
    return "resend"

def delivery_ready():
    if mail_transport()=="gmail_queue":
        return (os.getenv("KARNAFIM_GMAIL_QUEUE_ENABLED","0")=="1"
                and bool(os.getenv("DATABASE_URL","").strip()))
    return bool(os.getenv("KARNAFIM_RESEND_API_KEY","").strip()
                and os.getenv("KARNAFIM_MAIL_FROM","").strip())

def queue_confirmation(address,token):
    """Queue for an authorized Gmail sender; never expose Gmail credentials in app.

    The token-bearing link is held only until dispatch, then immediately redacted.
    Shared database advisory lock enforces a small account-wide daily allowance.
    """
    if not re.fullmatch(r"[^\\s@]+@[^\\s@]+\\.[^\\s@]+",address or ""):
        return False
    if digest_token(token) is None:
        return False
    import psycopg
    try:
        with psycopg.connect(os.environ["DATABASE_URL"],connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(460021119)")
                cur.execute("""SELECT COUNT(*) FROM email_outbox
                    WHERE created_at>NOW()-INTERVAL '24 hours'""")
                if cur.fetchone()[0]>=20:
                    return False
                cur.execute("""SELECT COUNT(*) FROM email_outbox
                    WHERE lower(to_address)=lower(%s)
                    AND created_at>NOW()-INTERVAL '24 hours'""",(address,))
                if cur.fetchone()[0]>=3:
                    return False
                cur.execute("""SELECT COUNT(*) FROM email_outbox
                    WHERE lower(to_address)=lower(%s)
                    AND created_at>NOW()-INTERVAL '20 minutes'""",(address,))
                if cur.fetchone()[0]>=1:
                    return False
                cur.execute("""INSERT INTO email_outbox
                    (kind,to_address,verification_url,status,expires_at)
                    VALUES('verification',%s,%s,'pending',NOW()+INTERVAL '24 hours')""",
                    (address,PUBLIC_ORIGIN+"/verify-email?token="+token))
        return True
    except (psycopg.Error, OSError, ValueError, KeyError):
        return False

def issue_token():
    token=secrets.token_urlsafe(36)
    return token,hashlib.sha256(token.encode("ascii")).hexdigest()

def digest_token(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]{40,100}",value or ""):
        return None
    return hashlib.sha256(value.encode("ascii")).hexdigest()

def send_confirmation(address,token):
    """Returns True only when the provider accepted the verification email."""
    if not delivery_ready():
        return False
    if mail_transport()=="gmail_queue":
        return queue_confirmation(address,token)
    import json
    from urllib.error import HTTPError,URLError
    url=PUBLIC_ORIGIN+"/verify-email?token="+token
    body=('<div dir="rtl" lang="he" style="font-family:Arial,sans-serif">'
          '<h2>אימות כתובת הדוא״ל לקהילת הקרנפים / ברקן</h2>'
          '<p>התקבלה בקשת הצטרפות לאתר. לאימות כתובת המייל שלך, לחץ על הקישור:</p>'
          '<p><a href="'+html.escape(url,quote=True)+'">אימות כתובת הדוא״ל</a></p>'
          '<p>הקישור תקף למשך 24 שעות. אם לא ביקשת להצטרף, אין צורך לפעול.</p>'
          '<p>אישור כתובת הדוא״ל אינו אישור חברות; פרסומים ייבדקו לפני חשיפה לקהילה.</p>'
          '</div>')
    payload={"from":os.environ["KARNAFIM_MAIL_FROM"].strip(),
             "to":[address],"subject":"אימות כתובת המייל — הקרנפים / ברקן","html":body}
    req=http.Request("https://api.resend.com/emails",
        data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),
        headers={"Authorization":"Bearer "+os.environ["KARNAFIM_RESEND_API_KEY"].strip(),
                 "Content-Type":"application/json"},method="POST")
    try:
        with http.urlopen(req,timeout=8) as response:
            return response.status in (200,201,202)
    except (HTTPError,URLError,TimeoutError,OSError):
        return False
