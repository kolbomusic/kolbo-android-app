"""Karnafim public route and source quality audit.
Use: python karnafim-site/link_audit.py --live
Performs read-only GET/HEAD requests. Never logs in or submits data.
"""
from __future__ import annotations
import argparse
import ast
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

BASE=Path(__file__).resolve().parent
ORIGIN="https://karnafim-community-46.onrender.com"
KNOWN_BAD_LABELS=("אין קישור ישיר לפרסום", "חיפוש הפרסום במקור", "הקישור הישיר לא נבדק")
RETIRED_SOURCE_IDS={4,5,7,12}  # Legacy Yad Lashiryon article URLs confirmed 404 on 2026-11-01
AGENT="KarnafimLinkAudit/1.0 (read-only; contact: site administrator)"
MUST_HAVE={
    "/":"הקרנפים",
    "/archive":"ארכיון",
    "/photos":"תמונות",
    "/memorials":"הנצחה",
    "/help":"עזרה",
    "/accessibility":"נגישות",
    "/status":"קהילה",
    "/privacy":"פרטיות",
    "/about":"הקרנפים",
}
ALLOWED_LOGIN_PREFIXES=("/login",)
ALLOWED_AUTH_PATHS=(
    "/new-post","/my-posts","/chats","/directory","/profile","/password",
    "/admin","/community/moderation","/admin/accessibility","/invite",
    "/logout","/delete-account","/inbox",
)
ALLOWED_DYNAMIC_AUTH_PREFIXES=("/contact/","/chat/","/post/","/community-media/","/memorial-photo/")

class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links=[]
        self.images=[]
        self.h1=0
        self.text=[]
    def handle_starttag(self, tag, attrs):
        attributes=dict(attrs)
        if tag=="a" and attributes.get("href"):self.links.append(attributes["href"])
        if tag=="img":
            if attributes.get("src"):self.images.append(attributes["src"])
            if not (attributes.get("alt") or "").strip():self.images.append("__missing_alt__")
        if tag=="h1":self.h1+=1
    def handle_data(self, data):
        self.text.append(data)

def repo_sources():
    tree=ast.parse((BASE/"archive_data.py").read_text(encoding="utf-8"))
    node=next(n for n in tree.body if isinstance(n,ast.Assign)
              and any(isinstance(t,ast.Name) and t.id=="ARCHIVE" for t in n.targets))
    return ast.literal_eval(node.value)

def memorial_people():
    tree=ast.parse((BASE/"memorial_photos.py").read_text(encoding="utf-8"))
    node=next(n for n in tree.body if isinstance(n,ast.Assign)
              and any(isinstance(t,ast.Name) and t.id=="PEOPLE" for t in n.targets))
    return ast.literal_eval(node.value)

def request(path):
    url=urllib.parse.urljoin(ORIGIN+"/",path.lstrip("/"))
    req=urllib.request.Request(url,headers={"User-Agent":AGENT},method="GET")
    try:
        with urllib.request.urlopen(req,timeout=24) as r:
            return r.status,r.geturl(),r.headers,r.read(150_000).decode("utf-8","replace")
    except urllib.error.HTTPError as e:
        with e:
            return e.code,e.geturl(),e.headers,e.read(3000).decode("utf-8","replace")
    except (TimeoutError,urllib.error.URLError,OSError) as e:
        return 0,url,{},str(e)[:150]

def path_type(url):
    parsed=urllib.parse.urlsplit(url)
    return parsed.path.rstrip("/") or "/"

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--live",action="store_true")
    args=parser.parse_args()
    sources=repo_sources()
    persons=memorial_people()
    ids=[x["id"] for x in sources]
    assert ids==list(range(1,15)),("Missing or duplicate archive article",ids)
    assert len(persons)>=5
    assert all(x["url"].startswith("https://") and "google.com/search" not in x["url"] for x in sources)
    app=(BASE/"community_portal.py").read_text(encoding="utf-8")
    readonly=(BASE/"public_pages.py").read_text(encoding="utf-8")
    assert 'verified_source=item["url"]' in app, "Source details must link full original"
    assert 'url=item["url"]' in readonly, "Read-only page must link original"
    assert "חיפוש הפרסום במקור" not in readonly
    print("PASS static: 14 unique archive ids, HTTPS official links, original-content actions in both modes")
    if not args.live:return 0
    health_code,_,_,h=request("/health")
    if health_code!=200:
        print("FAIL health",health_code,h[:150]);return 2
    locked='"read_only"' in h
    pages=list(MUST_HAVE)
    if locked:pages=[p for p in pages if p not in ("/help",)]
    pages += [f"/source/{x['id']}" for x in sources]
    pages += [f"/memorial/{p['slug']}" for p in persons]
    findings=[]
    crawled={}
    for path in pages:
        code,url,headers,document=request(path)
        parser=Links()
        if code==200:parser.feed(document)
        meaningful=len(" ".join(parser.text).strip())
        expected=MUST_HAVE.get(path)
        has_h1=parser.h1>0
        ok=(code==200 and meaningful>=75 and has_h1 and (not expected or expected in document)
            and "__missing_alt__" not in parser.images)
        if path.startswith("/source/"):
            item=sources[int(path.split("/")[-1])-1]
            direct=html.escape(item["url"],quote=True)
            ok=ok and (direct in document or item["url"] in document)
            # A source name in visible text does not establish a functional link.
            # Never restore the four verified dead article URLs as clickable hrefs.
            if item["id"] in RETIRED_SOURCE_IDS:
                ok=ok and 'href="'+direct+'"' not in document
                ok=ok and 'https://www.yadlashiryon.com/archives' in document
                ok=ok and "הקישור למאמר המקורי אינו פעיל" in document
            else:
                ok=ok and 'href="'+direct+'"' in document
            ok=ok and not any(bad in document for bad in KNOWN_BAD_LABELS)
        if path.startswith("/memorial/"):
            person=next(p for p in persons if path.endswith("/"+p["slug"]))
            ok=ok and (person["official"] in document or html.escape(person["official"]) in document)
        if not ok:findings.append({"path":path,"status":code,"bodyChars":meaningful,"h1":parser.h1,"problem":"missing_or_incomplete_content"})
        if code==200:
            crawled[path]=parser.links
            for src in parser.images:
                if src.startswith("/") and src!="__missing_alt__":
                    imgcode,imgurl,imgheaders,imgbody=request(src)
                    # Image bytes cannot be decoded by request(); only check status/content-type here.
                    good=imgcode==200 and "image/" in imgheaders.get("Content-Type","")
                    if not good:findings.append({"path":src,"status":imgcode,"linked_from":[path],"problem":"broken_local_image"})
                    print(("PASS" if good else "FAIL"),"image",src,"HTTP",imgcode)
        print(("PASS" if ok else "FAIL"),"content",path,"HTTP",code,"chars",meaningful)
    # Follow EVERY internal link actually rendered on public pages. Avoid private URLs,
    # which are checked separately for the correct unauthenticated behavior.
    internal={}
    for page,links in crawled.items():
        for link in links:
            absolute=urllib.parse.urljoin(ORIGIN+page,link)
            u=urllib.parse.urlsplit(absolute)
            if u.netloc not in ("karnafim-community-46.onrender.com",""):continue
            if u.scheme not in ("https",""):continue
            path=u.path.rstrip("/") or "/"
            if path in pages or path in ALLOWED_AUTH_PATHS or any(path.startswith(p) for p in ALLOWED_DYNAMIC_AUTH_PREFIXES):continue
            internal.setdefault(path,[]).append(page)
    for path,parents in sorted(internal.items()):
        code,landing,headers,document=request(path)
        parsed=Links()
        if code==200:parsed.feed(document)
        good_content=parsed.h1>0 and len(" ".join(parsed.text).strip())>=75
        ok=(code==200 and good_content) or (code in (302,303,403,503) and path in ALLOWED_AUTH_PATHS)
        if not ok:findings.append({"path":path,"status":code,"linked_from":parents,"problem":"invalid_internal_link"})
        print(("PASS" if ok else "FAIL"),"navigation",path,"HTTP",code)
    for path in ("/new-post","/my-posts","/chats","/directory","/profile","/admin"):
        code,landing,headers,doc=request(path)
        if locked:
            ok=code==503
        elif path=="/new-post":
            ok=code==200 and urllib.parse.urlsplit(landing).path=="/login" and "next=/new-post" in landing
        else:
            ok=code in (200,302,303,403)
        if not ok:findings.append({"path":path,"status":code,"problem":"unexpected_auth_flow"})
        print(("PASS" if ok else "FAIL"),"auth",path,code)
    report={"mode":"read_only" if locked else "community","public_pages_checked":len(pages),
            "extra_navigation_checked":len(internal),"errors":findings}
    print("AUDIT_RESULT_JSON",json.dumps(report,ensure_ascii=False))
    return 1 if findings else 0

if __name__=="__main__":
    sys.exit(main())
