"""Read-only regression checks for public and authenticated routes in both deployment modes."""
import ast, sys, json, re
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parent
URL="https://karnafim-community-46.onrender.com"
VALID=["/","/about","/privacy","/terms","/safety","/help","/accessibility","/photos","/archive","/memorials","/status"] + ["/source/"+str(i) for i in range(1,15)] + ["/memorial/"+s for s in ("yehonatan-sharabi","benaya-rein","uri-grossman","adam-goren","alexander-bunimovich")]
BLOCKED=["/login","/register","/auth/google/start","/auth/google/callback","/auth/google/consent","/profile","/password","/find","/chats","/new-post","/admin","/community/moderation","/invite","/feed","/directory"]
RETIRED_CREDENTIALS={"/login","/register","/password","/find","/auth/google/start","/auth/google/callback","/auth/google/consent"}
def fetch(path, user_agent="KarnafimSecurityAudit/1.0", referer=None):
    headers={"User-Agent":user_agent}
    if referer is not None:
        headers["Referer"]=referer
    try:
        response=urlopen(Request(URL+path,headers=headers),timeout=18)
    except HTTPError as e:
        response=e
    with response:
        return response.status, response.headers, response.read(50_000).decode("utf-8","replace"),response.geturl()

def static():
    for p in ROOT.glob("*.py"):ast.parse(p.read_text("utf-8"),filename=str(p))
    app=(ROOT/"app.py").read_text("utf-8")
    media=(ROOT/"community_portal.py").read_text("utf-8")
    # A retired phishing-flagged public member search must never be restored
    # by the private community blueprint after the security hold is lifted.
    assert '@app.route("/find", methods=["GET", "HEAD"])' in app
    assert 'return Response(' in app
    assert 'status=410, mimetype="text/plain"' in app
    assert '@app.route("/find")' not in media
    assert 'action="/find"' not in media
    assert '"/directory"' in media
    assert "TRUSTED_HOSTS" in app and "SESSION_COOKIE_HTTPONLY=True" in app
    assert 'KARNAFIM_MAINTENANCE' in app
    assert "hmac.compare_digest" in app and "guard()" in app
    assert 'ImageOps.exif_transpose' in media and 'format="JPEG"' in media
    assert "image/jpeg" in media and "Image.DecompressionBombError" in media
    h=(ROOT/"maintenance_public.html").read_text("utf-8")
    assert "<form" not in h.lower() and "<script" not in h.lower()
    assert 'SESSION_COOKIE_NAME="karnafim_oidc_session"' in app
    assert 'session.get("auth_method")!=AUTH_METHOD' in app
    assert 'KARNAFIM_LOCAL_AUTH_ENABLED' in app
    assert 'SAFETY_RELEASE_APPROVED and AUTH_READY' in app
    assert 'install_google_login' in app
    print("STATIC: file syntax and security invariants OK")

def live(expected_revision=None):
    health_status,_,health,_=fetch("/health")
    assert health_status==200, ("health",health_status)
    if expected_revision is not None:
        assert re.fullmatch(r"[0-9a-fA-F]{40}", expected_revision), "Invalid expected commit SHA"
        try:
            actual_revision=json.loads(health).get("revision", "unknown")
        except (ValueError, AttributeError):
            actual_revision="unknown"
        assert actual_revision==expected_revision[:12].lower(), ("Deployment drift: Render is not running the tested commit", actual_revision, expected_revision[:12].lower())
    active='"access":"community"' in health.replace(" ","")
    errors=[]
    if active:
        _,_,login_html,_=fetch("/login")
        local_mode='name="password"' in login_html
        for route in ("/","/photos","/archive","/memorials","/status","/about","/privacy","/safety","/help","/accessibility","/accessibility/report","/login","/register","/feed","/invite"):
            status,headers,body,landed=fetch(route)
            ok=status==200 and landed.startswith(URL) and "text/html" in headers.get("Content-Type","")
            if route=="/accessibility/report":
                ok=ok and '<form' in body and 'name="csrf"' in body
            if local_mode and route=="/register":
                ok=status in (200,503) and "text/html" in headers.get("Content-Type","")
            elif route=="/login":
                ok=ok and ('name="password"' in body if local_mode else 'name="password"' not in body and "Google" in body)
            elif route=="/register":
                ok=ok and 'name="password"' not in body and "Google" in body
            if route not in ("/favicon.svg",):
                ok=ok and 'id="main-content"' in body and 'skip-to-content' in body
            print(("PASS" if ok else "FAIL"),route,"ACTIVE",status)
            if not ok:errors.append((route,status))
        # Publishing must guide logged-out users through login and then resume.
        status,headers,body,landed=fetch("/new-post")
        ok=(status==200 and "/login?next=/new-post" in landed and
            ('name="password"' in body if local_mode else 'name="password"' not in body and "Google" in body))
        print(("PASS" if ok else "FAIL"),"/new-post","LOGIN_REQUIRED",status)
        if not ok:errors.append(("/new-post",status))
        for route,nextpage in (("/my-posts","/my-posts"),("/chats","/chats")):
            status,headers,body,landed=fetch(route)
            ok=status==200 and "/login?next="+nextpage in landed
            print(("PASS" if ok else "FAIL"),route,"LOGIN_REQUIRED",status)
            if not ok:errors.append((route,status))
        for route in ("/profile","/directory"):
            status,headers,body,landed=fetch(route)
            ok=status==200 and landed.rstrip("/")==URL+"/login"
            print(("PASS" if ok else "FAIL"),route,"REDIRECT_LOGIN",status)
            if not ok:errors.append((route,status))
        for retired in ("/password", "/find"):
            status,headers,body,landed=fetch(retired)
            if retired=="/password" and local_mode:
                ok=status==200 and landed.rstrip("/")==URL+"/login"
            else:
                ok=status==410 and "noindex" in headers.get("X-Robots-Tag","").lower()
            print(("PASS" if ok else "FAIL"),retired,"PASSWORD_OR_RETIRED",status)
            if not ok:errors.append((retired,status))
        for route in ("/admin","/community/moderation","/community-media/1"):
            status,headers,body,landed=fetch(route)
            ok=status==403
            print(("PASS" if ok else "FAIL"),route,"FORBIDDEN",status)
            if not ok:errors.append((route,status))
    else:
        for route in VALID:
            status,headers,body,landed=fetch(route)
            ok=status==200 and landed.startswith(URL) and "<form" not in body.lower() and "<script" not in body.lower()
            if route=="/":ok=ok and "החברות נשארה" in body
            if route=="/accessibility":ok=ok and "הצהרת נגישות" in body and 'id="main-content"' in body
            if route=="/about":ok=ok and "על קהילת הקרנפים" in body
            if route=="/privacy":ok=ok and "פרטיות המידע באתר" in body
            if route=="/terms":ok=ok and "תנאי שימוש" in body
            if route=="/safety":ok=ok and "מצב אבטחת אתר הקרנפים" in body
            if route=="/help":ok=ok and "שאלות נפוצות" in body
            if route=="/find":ok=ok and "איתור חברי פלוגת הקרנפים" in body
            if route.startswith("/memorial/"):ok=ok and "לזכר" in body
            if route.startswith("/source/"):ok=ok and "תמצית התיעוד" in body
            if "form-action 'none'" not in headers.get("Content-Security-Policy",""):ok=False
            if "noindex" in headers.get("X-Robots-Tag","").lower():ok=False
            print(("PASS" if ok else "FAIL"),route,"READ_ONLY",status)
            if not ok:errors.append((route,status))
        # Detect basic user-agent/referrer cloaking of retired login endpoints.
        # These are Googlebot-like request headers, not an authenticated Google crawl.
        googlebot="Googlebot/2.1 (+http://www.google.com/bot.html)"
        google_referer="https://www.google.com/search?q=karnafim"
        for route in ("/", "/status", "/login", "/register", "/password", "/find", "/auth/google/start"):
            regular,reg_headers,reg_body,reg_url=fetch(route)
            bot,bot_headers,bot_body,bot_url=fetch(route,googlebot,google_referer)
            same=(regular==bot and reg_body==bot_body and reg_url==bot_url
                  and reg_headers.get("X-Robots-Tag")==bot_headers.get("X-Robots-Tag")
                  and reg_headers.get("Content-Security-Policy")==bot_headers.get("Content-Security-Policy"))
            correct=bot==(200 if route in ("/", "/status") else 410)
            clean="<form" not in bot_body.lower() and "<script" not in bot_body.lower()
            ok=same and correct and clean
            print(("PASS" if ok else "FAIL"),route,"GOOGLEBOT_HEADER_PARITY",bot)
            if not ok:errors.append(("Googlebot-header parity: "+route,bot))
        for route in BLOCKED:
            status,headers,body,landed=fetch(route)
            expected=410 if route in RETIRED_CREDENTIALS else 503
            ok=status==expected and "no-store" in headers.get("Cache-Control","") and "noindex" in headers.get("X-Robots-Tag","")
            print(("PASS" if ok else "FAIL"),route,"BLOCKED",status)
            if not ok:errors.append((route,status))
    robots,_,rules,_=fetch("/robots.txt")
    sitemap,_,xml,_=fetch("/sitemap.xml")
    if robots!=200 or (not active and ("Disallow: /login" in rules or "Disallow: /register" in rules)):errors.append(("robots",robots))
    if sitemap!=200 or "https://karnafim-community-46.onrender.com/memorial/" not in xml:errors.append(("sitemap",sitemap))
    favicon,*_=fetch("/favicon.svg")
    if favicon!=200:errors.append(("favicon",favicon))
    print("MODE", "community" if active else "read_only", "FAILURES",errors)
    if errors:sys.exit(1)
if __name__=="__main__":
    static()
    if "--live" in sys.argv:
        expected=None
        if "--expect-revision" in sys.argv:
            index=sys.argv.index("--expect-revision")
            if index+1>=len(sys.argv):sys.exit("--expect-revision requires a 40-character Git SHA")
            expected=sys.argv[index+1]
        live(expected)
