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

def delivery_ready():
    return bool(os.getenv("KARNAFIM_RESEND_API_KEY","").strip()
                and os.getenv("KARNAFIM_MAIL_FROM","").strip())

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
