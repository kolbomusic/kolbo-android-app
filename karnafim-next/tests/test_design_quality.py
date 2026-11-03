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

css=(ROOT/"static/site.css").read_text(encoding="utf-8")
js=(ROOT/"static/site.js").read_text(encoding="utf-8")
for token in (".auth-page",".auth-trust",":focus-visible","prefers-reduced-motion",
              "prefers-contrast","forced-colors","@media(max-width:680px)"):
    assert token in css,token
assert 'aria-expanded' in js
print("PASS: public navigation, RTL, images, auth safety gate and responsive/a11y design hooks")
