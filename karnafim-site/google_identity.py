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
import hmac
import html
import threading
import requests

from authlib.jose import JsonWebToken, JoseError
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


def auth_mode():
    """Default remains confidential OAuth; GIS is explicit and secretless."""
    return os.getenv("KARNAFIM_GOOGLE_AUTH_MODE", "oauth").strip().lower()


def enabled():
    checks = configuration_checks()
    return (checks["explicitly_enabled"] and checks["valid_client_id"]
            and (auth_mode() == "gis" or
                 (auth_mode() == "oauth" and checks["client_secret_present"])))


# The callback is deterministic so the exact first-party script can be hashed
# in the Content Security Policy instead of permitting unsafe-inline.
GIS_CALLBACK_JS = (
    "function karnafimGoogleResponse(response){"
    "if(!response||typeof response.credential!=='string'||"
    "response.credential.length<50||response.credential.length>8192)return;"
    "var form=document.getElementById('karnafim-gis-form');"
    "if(!form)return;"
    "form.elements.namedItem('credential').value=response.credential;"
    "form.submit();"
    "}"
)


def gis_button_html():
    """Google's popup returns a signed ID token via a first-party form POST.

    The callback runs on our own login page; posting a local form keeps the
    secure SameSite=Lax session cookie and the one-time CSRF/nonce available.
    """
    if not enabled() or auth_mode() != "gis":
        return ""
    nonce = secrets.token_urlsafe(32)
    session["google_gis_nonce"] = nonce
    csrf = session.setdefault("csrf", secrets.token_urlsafe(24))
    client_id = html.escape(os.environ["GOOGLE_CLIENT_ID"].strip(), quote=True)
    return (
        '<div id="g_id_onload" data-client_id="' + client_id + '" '
        'data-callback="karnafimGoogleResponse" data-ux_mode="popup" '
        'data-auto_prompt="false" data-nonce="' + html.escape(nonce, quote=True) + '"></div>'
        '<div class="g_id_signin" data-type="standard" data-size="large" '
        'data-theme="outline" data-text="signin_with" data-shape="rectangular"></div>'
        '<form id="karnafim-gis-form" action="' + CALLBACK + '" '
        'method="post" hidden autocomplete="off">'
        '<input type="hidden" name="csrf" value="' + html.escape(csrf, quote=True) + '">'
        '<input type="hidden" name="credential" value="">'
        '</form>'
        '<script>' + GIS_CALLBACK_JS + '</script>'
        '<script src="https://accounts.google.com/gsi/client" async defer></script>'
    )


# A short in-process cache prevents an outbound request on *every* attempted
# sign-in. Stale certificates are never used past expiry; a failed fetch leaves
# login closed rather than accepting a token without signature verification.
_GOOGLE_JWKS_CACHE = {"keys": None, "expires_at": 0.0}
_GOOGLE_JWKS_LOCK = threading.RLock()


def _get_google_jwks():
    now = time.monotonic()
    with _GOOGLE_JWKS_LOCK:
        if _GOOGLE_JWKS_CACHE["keys"] and now < _GOOGLE_JWKS_CACHE["expires_at"]:
            return _GOOGLE_JWKS_CACHE["keys"]
        response = requests.get(
            "https://www.googleapis.com/oauth2/v3/certs",
            headers={"Accept": "application/json"}, timeout=7
        )
        response.raise_for_status()
        if len(response.content) > 100000:
            raise ValueError("JWKS too large")
        keys = response.json()
        if not isinstance(keys, dict) or not isinstance(keys.get("keys"), list) or not 1 <= len(keys["keys"]) <= 20:
            raise ValueError("Invalid Google public keys")
        cache_control = getattr(response, "headers", {}).get("Cache-Control", "")
        max_age = re.search(r"(?:^|,)\\s*max-age=(\\d+)(?:,|$)", cache_control, re.I)
        ttl = min(300, max(30, int(max_age.group(1)))) if max_age else 120
        _GOOGLE_JWKS_CACHE["keys"] = keys
        _GOOGLE_JWKS_CACHE["expires_at"] = time.monotonic() + ttl
        return keys


def verify_google_gis_token(raw_token, client_id):
    """Verify Google's RSA signature and expiry against fresh public JWKS."""
    if not isinstance(raw_token, str) or not 50 < len(raw_token) <= 8192:
        raise ValueError("Malformed ID token")
    keys = _get_google_jwks()
    # RS256 only, reject HS256, none, and token-key algorithm confusion.
    claims = JsonWebToken(["RS256"]).decode(raw_token, keys)
    claims.validate(leeway=60)
    for claim in ("exp", "iat", "iss", "aud", "sub"):
        if claim not in claims:
            raise ValueError("Missing mandatory Google claim")
    if not isinstance(claims["exp"], int) or not isinstance(claims["iat"], int):
        raise ValueError("Invalid Google issue/expiry timestamps")
    if claims["iat"] > time.time() + 60:
        raise ValueError("Future-issued Google credential")
    if claims["exp"] - claims["iat"] > 7200:
        raise ValueError("Unreasonable Google credential lifetime")
    return validate_google_identity(dict(claims), client_id), dict(claims)


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

    def finish_google_login(identity):
        """Keep all account linking, consent and privilege decisions in one place."""
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

    @app.route("/auth/google/start", methods=["GET"])
    def google_start():
        if enabled() and auth_mode() == "gis":
            return redirect("/login", code=303)
        if not enabled():
            return view("ההתחברות אינה זמינה",
                        '<h1>כניסה באמצעות Google עדיין אינה פעילה</h1>'
                        '<p>האתר ממתין להשלמת בדיקות האבטחה ולהגדרת התחברות רשמית.</p>'), 503
        path = request.args.get("next", "/")
        session["google_return"] = path if path in RETURN_PATHS else "/"
        return oauth.google.authorize_redirect(
            CALLBACK, nonce=secrets.token_urlsafe(32)
        )

    @app.route("/auth/google/callback", methods=["GET", "POST"])
    def google_callback():
        if not enabled():
            abort(503)
        if request.method == "POST":
            if auth_mode() != "gis":
                abort(405)
            # This callback uses a same-origin POST, not Google's cross-site
            # form POST. Flask's session-bound CSRF token and one-time nonce
            # protect the operation without weakening SameSite cookie policy.
            guard()
            nonce = session.pop("google_gis_nonce", "")
            if not isinstance(nonce, str) or len(nonce) < 32:
                abort(403)
            try:
                identity, claims = verify_google_gis_token(
                    request.form.get("credential", ""),
                    os.environ["GOOGLE_CLIENT_ID"].strip())
                if not hmac.compare_digest(str(claims.get("nonce") or ""), nonce):
                    raise ValueError("Google nonce does not match this session")
            except (JoseError, requests.RequestException, ValueError, TypeError, KeyError):
                session.pop("google_return", None)
                return ('אימות Google נכשל. לא נוצר חשבון.', 401)
            return finish_google_login(identity)
        if auth_mode() != "oauth":
            abort(405)
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

        return finish_google_login(identity)

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
