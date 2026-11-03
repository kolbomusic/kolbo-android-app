"""Static design, accessibility and safe-auth regression checks.

Runs without production credentials or a member database.
"""
import os
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.pop("DATABASE_URL",None)
os.environ.pop("BARKAN_DATABASE_URL",None)
os.environ.pop("BARKAN_PUBLIC_AUTH",None)
os.environ.pop("BARKAN_SAFETY_RELEASE_APPROVED",None)
import app as site

class Inspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links=[]
        self.ids=set()
        self.lang=None
        self.forms=[]
        self.inputs=[]
        self.images=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="html":self.lang=(a.get("lang"),a.get("dir"))
        if "id" in a:self.ids.add(a["id"])
        if tag=="a":self.links.append(a.get("href",""))
        if tag=="form":self.forms.append(a)
        if tag=="input":self.inputs.append(a)
        if tag=="img":self.images.append(a)

client=site.app.test_client()
# A public-only deployment must never confuse liveness with readiness.
unconfigured=client.get("/ready",base_url="https://karnafim-community-46.onrender.com")
assert unconfigured.status_code==503
assert unconfigured.get_json()["member_portal"]=="closed"
origin="https://karnafim-community-46.onrender.com"
routes=["/","/heritage","/memorial","/photos","/about","/help","/privacy","/terms","/safety","/status"]
all_links=set()
for path in routes:
    res=client.get(path,base_url=origin)
    assert res.status_code==200,(path,res.status_code)
    assert res.headers["Content-Security-Policy"].startswith("default-src 'none'"),path
    parser=Inspector()
    parser.feed(res.get_data(as_text=True))
    assert parser.lang==("he","rtl"),path
    assert "main" in parser.ids and "nav" in parser.ids,path
    assert all(img.get("alt") is not None for img in parser.images),path
    assert not [i for i in parser.inputs if i.get("type")=="password"],path
    all_links.update(x for x in parser.links if x.startswith("/") and not x.startswith("//"))
for link in all_links:
    p=link.split("#",1)[0].split("?",1)[0]
    response=client.get(p or "/",base_url=origin)
    assert response.status_code==200,(link,response.status_code)
for path in ("/login","/signup","/new","/profile","/inbox","/find"):
    assert client.get(path,base_url=origin).status_code in (503,303),path

memorial_html=client.get("/memorial",base_url=origin).get_data(as_text=True)
for label in ("בניה ריין", "אורי גרוסמן", "אדם גורן", "אלכסנדר", "יוני", "www.izkor.gov.il"):
    assert label in memorial_html, label
assert memorial_html.count('class="memorial"')==5

# Only the Render ingress may supply the client IP used by throttling.
# Regular test deployments must ignore spoofed X-Forwarded-For headers.
import subprocess
import textwrap
for render_mode,expected in ((False,"10.0.0.1"),(True,"203.0.113.16")):
    env=dict(os.environ)
    env.pop("RENDER_SERVICE_ID",None)
    if render_mode:
        env["RENDER_SERVICE_ID"]="synthetic-render-service"
    check=subprocess.run([sys.executable,"-c",textwrap.dedent("""
        import app
        from flask import request
        @app.app.get("/_probe_ip")
        def probe():
            return request.remote_addr
        c=app.app.test_client()
        r=c.get("/_probe_ip",base_url="https://karnafim-community-46.onrender.com",
                environ_overrides={"REMOTE_ADDR":"10.0.0.1"},
                headers={"X-Forwarded-For":"203.0.113.16"})
        assert r.status_code==200
        print(r.get_data(as_text=True))
    """)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=20)
    assert check.returncode==0,(check.stdout,check.stderr[-1200:])
    assert check.stdout.strip()==expected,(render_mode,check.stdout,expected)

css=(ROOT/"static/site.css").read_text(encoding="utf-8")
js=(ROOT/"static/site.js").read_text(encoding="utf-8")
for token in (".auth-page",".auth-trust",":focus-visible","prefers-reduced-motion",
              "prefers-contrast","forced-colors","@media(max-width:680px)"):
    assert token in css,token
# Recovery UX must never leak member details, auto-submit or poll while idle.
root=client.get("/",base_url=origin).get_data(as_text=True)
assert 'id="site-connection-notice"' in root
assert 'id="site-connection-retry"' in root
assert 'role="status"' in root
assert 'document.addEventListener("visibilitychange"' in js
assert 'method: "GET"' in js and '"/health"' in js
assert 'method: "POST"' not in js
assert 'setInterval(' not in js
# Existing voice recorder remains permitted; reconnect code never uploads.
assert 'aria-expanded' in js
print("PASS: public navigation, RTL, images, auth safety gate and responsive/a11y design hooks")
