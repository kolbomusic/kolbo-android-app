"""Regression checks for public-only mode; no user accounts or writes touched."""
import ast, sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parent
URL="https://karnafim-community-46.onrender.com"
VALID=["/","/archive","/memorials","/find","/status"] + ["/source/"+str(i) for i in range(1,15)] + ["/memorial/"+s for s in ("yehonatan-sharabi","benaya-rein","uri-grossman","adam-goren","alexander-bunimovich")]
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
    errors=[]
    for route in VALID:
        status,headers,body,landed=fetch(route)
        ok=status==200 and landed.startswith(URL) and "<form" not in body.lower() and "<script" not in body.lower()
        if route=="/":
            ok=ok and "החברות נשארה" in body
        if route.startswith("/memorial/"):ok=ok and "לזכר" in body
        if route.startswith("/source/"):ok=ok and "מה ידוע מהתיעוד" in body
        if "form-action 'none'" not in headers.get("Content-Security-Policy",""):ok=False
        print(("PASS" if ok else "FAIL"),route,"HTTP",status)
        if not ok:errors.append((route,status))
    for route in BLOCKED:
        status,headers,body,landed=fetch(route)
        ok=status==503 and "no-store" in headers.get("Cache-Control","")
        print(("PASS" if ok else "FAIL"),route,"BLOCKED",status)
        if not ok:errors.append((route,status))
    health_status,head,health,_=fetch("/health")
    if health_status!=200 or '"access":"read_only"' not in health.replace(" ",""):errors.append(("health",health_status))
    fav,*_=fetch("/favicon.svg")
    if fav!=200:errors.append(("favicon",fav))
    print("FAILURES",errors)
    if errors:sys.exit(1)
if __name__=="__main__":
    static()
    if "--live" in sys.argv:live()
