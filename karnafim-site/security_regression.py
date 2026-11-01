"""Read-only regression checks for public and authenticated routes in both deployment modes."""
import ast, sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parent
URL="https://karnafim-community-46.onrender.com"
VALID=["/","/accessibility","/photos","/archive","/memorials","/find","/status"] + ["/source/"+str(i) for i in range(1,15)] + ["/memorial/"+s for s in ("yehonatan-sharabi","benaya-rein","uri-grossman","adam-goren","alexander-bunimovich")]
BLOCKED=["/login","/register","/profile","/password","/chats","/new-post","/admin","/community/moderation","/invite","/feed","/directory"]
def fetch(path):
    try:
        response=urlopen(Request(URL+path,headers={"User-Agent":"KarnafimSecurityAudit/1.0"}),timeout=18)
    except HTTPError as e:
        response=e
    with response:
        return response.status, response.headers, response.read(50_000).decode("utf-8","replace"),response.geturl()

def static():
    for p in ROOT.glob("*.py"):ast.parse(p.read_text("utf-8"),filename=str(p))
    app=(ROOT/"app.py").read_text("utf-8")
    media=(ROOT/"community_portal.py").read_text("utf-8")
    assert "TRUSTED_HOSTS" in app and "SESSION_COOKIE_HTTPONLY=True" in app
    assert 'KARNAFIM_MAINTENANCE' in app
    assert "hmac.compare_digest" in app and "guard()" in app
    assert 'ImageOps.exif_transpose' in media and 'format="JPEG"' in media
    assert "image/jpeg" in media and "Image.DecompressionBombError" in media
    h=(ROOT/"maintenance_public.html").read_text("utf-8")
    assert "<form" not in h.lower() and "<script" not in h.lower()
    print("STATIC: file syntax and security invariants OK")

def live():
    health_status,_,health,_=fetch("/health")
    assert health_status==200, ("health",health_status)
    active='"access":"community"' in health.replace(" ","")
    errors=[]
    if active:
        for route in ("/","/photos","/archive","/memorials","/find","/status","/about","/privacy","/safety","/help","/accessibility","/accessibility/report","/login","/register","/feed","/invite"):
            status,headers,body,landed=fetch(route)
            ok=status==200 and landed.startswith(URL) and "text/html" in headers.get("Content-Type","")
            if route in ("/login","/register","/accessibility/report"):
                ok=ok and '<form' in body and 'name="csrf"' in body
            if route not in ("/favicon.svg",):
                ok=ok and 'id="main-content"' in body and 'skip-to-content' in body
            print(("PASS" if ok else "FAIL"),route,"ACTIVE",status)
            if not ok:errors.append((route,status))
        # Publishing must guide logged-out users through login and then resume.
        status,headers,body,landed=fetch("/new-post")
        ok=(status==200 and "/login?next=/new-post" in landed and
            'name="csrf"' in body and "כניסה לחשבון" in body)
        print(("PASS" if ok else "FAIL"),"/new-post","LOGIN_REQUIRED",status)
        if not ok:errors.append(("/new-post",status))
        for route,nextpage in (("/my-posts","/my-posts"),("/chats","/chats")):
            status,headers,body,landed=fetch(route)
            ok=status==200 and "/login?next="+nextpage in landed and 'name="csrf"' in body
            print(("PASS" if ok else "FAIL"),route,"LOGIN_REQUIRED",status)
            if not ok:errors.append((route,status))
        for route in ("/profile","/directory","/password"):
            status,headers,body,landed=fetch(route)
            ok=status==200 and landed.rstrip("/")==URL+"/login"
            print(("PASS" if ok else "FAIL"),route,"REDIRECT_LOGIN",status)
            if not ok:errors.append((route,status))
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
            if route.startswith("/memorial/"):ok=ok and "לזכר" in body
            if route.startswith("/source/"):ok=ok and "מה ידוע מהתיעוד" in body
            if "form-action 'none'" not in headers.get("Content-Security-Policy",""):ok=False
            print(("PASS" if ok else "FAIL"),route,"READ_ONLY",status)
            if not ok:errors.append((route,status))
        for route in BLOCKED:
            status,headers,body,landed=fetch(route)
            ok=status==503 and "no-store" in headers.get("Cache-Control","")
            print(("PASS" if ok else "FAIL"),route,"BLOCKED",status)
            if not ok:errors.append((route,status))
    favicon,*_=fetch("/favicon.svg")
    if favicon!=200:errors.append(("favicon",favicon))
    print("MODE", "community" if active else "read_only", "FAILURES",errors)
    if errors:sys.exit(1)
if __name__=="__main__":
    static()
    if "--live" in sys.argv:live()
