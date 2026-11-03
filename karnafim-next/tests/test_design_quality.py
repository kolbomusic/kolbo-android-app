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
unconfigured=client.get("/ready",base_url="https://karnafim-barkan-46.onrender.com")
assert unconfigured.status_code==503
assert unconfigured.get_json()["member_portal"]=="closed"
origin="https://karnafim-barkan-46.onrender.com"
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

# Delegated permissions: only founding owner can manage role assignments.
from flask import g
with site.app.test_request_context("/"):
    os.environ["BARKAN_ADMIN_EMAIL"]="founder@example.org"
    g.user={"id":1,"email":"founder@example.org","approved":True,"role":"member"}
    assert site.owner() and site.can_moderate() and site.can_manage_members()
    g.user={"id":2,"email":"moderator@example.org","approved":True,"role":"moderator"}
    assert not site.owner() and site.can_moderate() and not site.can_manage_members()
    g.user={"id":3,"email":"manager@example.org","approved":True,"role":"member_manager"}
    assert not site.owner() and not site.can_moderate() and site.can_manage_members()
    g.user={"id":4,"email":"staff@example.org","approved":True,"role":"admin"}
    assert not site.owner() and site.can_moderate() and site.can_manage_members()
    g.user={"id":5,"email":"unapproved@example.org","approved":False,"role":"admin"}
    assert not site.owner() and not site.can_moderate() and not site.can_manage_members()
    os.environ.pop("BARKAN_ADMIN_EMAIL",None)
assert client.get("/staff",base_url=origin).status_code==503
# Member rejections must leave the pending queue. All staff changes need an audit log.
source=(ROOT/"app.py").read_text(encoding="utf-8")
assert "membership_status='pending'" in source
assert "membership_status=%s" in source
assert "\"member_\"+decision" in source
assert "INSERT INTO b2_admin_audit(actor,target,action,details)" in source
assert "with connect() as c:" in source
assert "role_changed" in source


# Do not publish a disputed crew position as verified memorial information.
assert "כתותחן טנק" not in memorial_html
assert "תותחן מרכבה סימן 4 · פלוגה ב׳ הקרנפים" not in memorial_html

# Canonical handoff is opt-in. Keep /health alive for deployment checks.
import subprocess
handoff_env=dict(os.environ)
handoff_env["BARKAN_CANONICAL_HANDOFF"]="1"
handoff=subprocess.run([sys.executable,"-c",'''
import app
c=app.app.test_client()
base="https://karnafim-barkan-46.onrender.com"
r=c.get("/memorial",base_url=base)
assert r.status_code==302
assert r.headers["Location"]=="https://karnafim-community-46.onrender.com/memorial"
assert c.get("/health",base_url=base).status_code==200
# Private requests and links with sensitive query data must remain local.
for path in ("/verify-email?token=secret", "/login", "/signup",
             "/profile", "/inbox", "/media/42", "/ready"):
    blocked=c.get(path,base_url=base)
    assert blocked.status_code!=302,(path,blocked.status_code)
assert c.get("/memorial?token=secret",base_url=base).status_code==200
'''],cwd=ROOT,env=handoff_env,capture_output=True,text=True,timeout=20)
assert handoff.returncode==0,(handoff.stdout,handoff.stderr[-2000:])

css=(ROOT/"static/site.css").read_text(encoding="utf-8")
js=(ROOT/"static/site.js").read_text(encoding="utf-8")
for token in (".auth-page",".auth-trust",":focus-visible","prefers-reduced-motion",
              "prefers-contrast","forced-colors","@media(max-width:680px)"):
    assert token in css,token
assert 'aria-expanded' in js
print("PASS: public navigation, RTL, images, auth safety gate and responsive/a11y design hooks")
