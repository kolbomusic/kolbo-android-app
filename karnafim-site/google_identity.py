"""Google-only OIDC authentication for the Karnafim veterans community.

Explicitly disabled until Google OAuth client credentials are configured and the
Google Safe Browsing warning is resolved. Uses Authlib's signed ID-token,
issuer/audience validation and per-request state+nonce. Never accepts a raw
client-supplied email as proof of identity.

Google identity != verification of military service; admin approval is separate.
"""
from __future__ import annotations

import os
import re
import secrets
import time

from authlib.integrations.flask_client import OAuth
from authlib.integrations.base_client.errors import OAuthError
from flask import abort, redirect, request, session

CALLBACK = "https://karnafim-community-46.onrender.com/auth/google/callback"
RETURN_PATHS = {"/", "/new-post", "/my-posts", "/feed", "/chats",
                "/directory", "/photos", "/profile"}


CLIENT_ID_RE = re.compile(r"^[0-9]+-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$")


def configuration_checks():
    """Non-secret configuration diagnostics; never include credential values."""
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    enabled_flag = os.getenv("KARNAFIM_GOOGLE_AUTH_ENABLED", "0") == "1"
    return {
        "explicitly_enabled": enabled_flag,
        "valid_client_id": bool(CLIENT_ID_RE.fullmatch(client_id)),
        "client_secret_present": len(secret) >= 8 and secret.lower() not in (
            "your-client-secret", "replace-me", "changeme", "placeholder"),
        "callback": CALLBACK,
    }


def enabled():
    checks = configuration_checks()
    return all(checks[key] for key in
               ("explicitly_enabled", "valid_client_id", "client_secret_present"))


def authoritative_email(email: str, hd: str | None) -> bool:
    """Google is authoritative for @gmail and hosted Workspace domains only."""
    try:
        domain = email.rsplit("@", 1)[1].lower()
    except (IndexError, AttributeError):
        return False
    return domain in ("gmail.com", "googlemail.com") or bool(
        isinstance(hd, str) and domain == hd.lower()
    )


def validate_google_identity(info, client_id: str) -> dict:
    """Validate *verified* ID-token claims returned by Authlib, not user input."""
    if not isinstance(info, dict):
        raise ValueError("Unvalidated identity")
    issuer = info.get("iss")
    aud = info.get("aud")
    if issuer not in ("accounts.google.com", "https://accounts.google.com"):
        raise ValueError("Unexpected token issuer")
    if isinstance(aud, list):
        if client_id not in aud or info.get("azp") != client_id:
            raise ValueError("Unexpected multiple-audience token")
    elif aud != client_id:
        raise ValueError("Unexpected token audience")
    elif info.get("azp") not in (None, client_id):
        raise ValueError("Unexpected authorized party")
    sub = info.get("sub")
    email = info.get("email")
    if not isinstance(sub, str) or not 1 <= len(sub) <= 255 or not sub.isascii():
        raise ValueError("Missing subject")
    if not isinstance(email, str) or not 3 <= len(email) <= 200 or not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Missing email")
    if info.get("email_verified") is not True:
        raise ValueError("Unverified Google email")
    hd = info.get("hd")
    name = info.get("name")
    return {"sub": sub, "email": email.lower(), "name": (name if isinstance(name, str) else "")[:100],
            "hd": hd if isinstance(hd, str) else None}


def install_google_login(app, sql, view, guard, formwrap, esc):
    """Install routes; configuration, maintenance lock and membership checks apply."""
    oauth = OAuth(app)
    oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
    )

    @app.route("/auth/google/start", methods=["GET"])
    def google_start():
        if not enabled():
            return view("ההתחברות אינה זמינה",
                        '<h1>כניסה באמצעות Google עדיין אינה פעילה</h1>'
                        '<p>האתר ממתין להשלמת בדיקות האבטחה ולהגדרת התחברות רשמית.</p>'), 503
        path = request.args.get("next", "/")
        session["google_return"] = path if path in RETURN_PATHS else "/"
        return oauth.google.authorize_redirect(
            CALLBACK, nonce=secrets.token_urlsafe(32)
        )

    @app.route("/auth/google/callback", methods=["GET"])
    def google_callback():
        if not enabled():
            abort(503)
        try:
            token = oauth.google.authorize_access_token()
            identity = validate_google_identity(
                token.get("userinfo"), os.environ["GOOGLE_CLIENT_ID"])
        except (OAuthError, KeyError, ValueError, TypeError):
            session.pop("google_return", None)
            return view("אימות Google נכשל",
                        '<div class="card" role="alert"><h1>אימות ההתחברות לא הושלם</h1>'
                        '<p>לא נוצר חשבון ולא נשמרו פרטי גישה. ניתן לנסות שוב.</p>'
                        '<a href="/login">חזרה לכניסה</a></div>'), 401

        rows = sql("SELECT id FROM members WHERE google_sub=%s",
                   (identity["sub"],), True)
        if rows:
            uid = rows[0]["id"]
        else:
            existing = sql("SELECT id,google_sub FROM members WHERE email=%s",
                           (identity["email"],), True)
            if existing:
                if existing[0]["google_sub"]:
                    return view("החשבון מצריך בדיקה",
                                '<h1>נדרש אימות חשבון</h1><p>כתובת זו מקושרת לחשבון אחר.</p>'), 409
                if not authoritative_email(identity["email"], identity["hd"]):
                    return view("קישור חשבון קיים",
                                '<h1>נדרשת בדיקת בעלות של המנהל</h1>'
                                '<p>חשבון ותיק עם כתובת דוא״ל חיצונית לא יקושר ל־Google אוטומטית.</p>'), 409
                # Only Google-authoritative verified domains may link legacy emails.
                updated = sql(
                    "UPDATE members SET google_sub=%s WHERE id=%s AND google_sub IS NULL RETURNING id",
                    (identity["sub"], existing[0]["id"]), True)
                if not updated:
                    abort(409)
                uid = updated[0]["id"]
            else:
                # No member is created until explicit signup/data storage consent.
                return_path = session.get("google_return", "/")
                session.clear()
                session.permanent = True
                session["pending_google_signup"] = dict(identity, ts=int(time.time()))
                session["google_return"] = return_path if return_path in RETURN_PATHS else "/"
                return redirect("/auth/google/consent", code=303)

        destination = session.get("google_return", "/")
        session.clear()
        session.permanent = True
        session["uid"] = uid
        session["auth_method"] = "google"
        return redirect(destination if destination in RETURN_PATHS else "/", code=303)

    @app.route("/auth/google/consent", methods=["GET", "POST"])
    def google_consent():
        if not enabled():
            abort(503)
        pending = session.get("pending_google_signup")
        if not isinstance(pending, dict) or int(time.time()) - pending.get("ts", 0) > 600:
            session.clear()
            return redirect("/login", code=303)
        if request.method == "POST":
            guard()
            if request.form.get("consent") != "on":
                return view("הסכמה נדרשת",
                            '<h1>לא נוצר חשבון</h1><p>יש להסכים לשמירת פרטי החשבון.</p>'
                            '<a href="/auth/google/consent">חזרה</a>'), 400
            name = request.form.get("name", "").strip()[:100]
            if len(name) < 2:
                return view("שם חסר", '<p>יש להזין שם של לפחות שתי אותיות.</p>'), 400
            created = sql(
                """INSERT INTO members(name,email,password,google_sub,approved,visible)
                   VALUES(%s,%s,%s,%s,FALSE,FALSE)
                   ON CONFLICT (email) DO NOTHING RETURNING id""",
                (name, pending["email"], "!google-only:"+secrets.token_hex(24),
                 pending["sub"]), True)
            if not created:
                session.clear()
                return view("קיים חשבון בכתובת זו",
                            '<h1>חשבון קיים ממתין לאימות</h1>'
                            '<p>לא קישרנו את החשבון הקודם בלי אישור.</p>'), 409
            uid = created[0]["id"]
            destination = session.get("google_return", "/")
            session.clear()
            session.permanent = True
            session["uid"] = uid
            session["auth_method"] = "google"
            return redirect(destination if destination in RETURN_PATHS else "/", code=303)

        return view("הצטרפות לקהילת הקרנפים",
            '<h1>🦏 השלמת הצטרפות לאחר אימות Google</h1>'
            '<p>Google אישרה את חשבון הדוא״ל. אין בכך הוכחה ששירתת בפלוגה; '
            'מנהל הקהילה יאמת את בקשת החברות בנפרד.</p>'
            '<p><strong>כתובת החשבון:</strong> '+esc(pending["email"])+'</p>'
            '<form method="post" class="card">'+formwrap(
                '<label>השם שיוצג למנהל לבדיקה'
                '<input name="name" maxlength="100" autocomplete="name" required value="'+esc(pending["name"])+'"></label>'
                '<label><input type="checkbox" name="consent" required style="width:auto;display:inline">'
                ' אני מסכים לשמירת שמי וכתובת הדוא״ל שלי למטרת הקהילה. '
                'הפרופיל לא יופיע במדריך לפני אישור החברות והסכמתי להצגתו.</label>'
                '<button type="submit">הגשת בקשת חברות</button>'
            )+'</form><p>האתר אינו קשור באופן רשמי לצה״ל או למשרד הביטחון.</p>')
