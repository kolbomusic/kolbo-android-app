"""Export public veteran-community pages for Render static CDN.

No DATABASE_URL, accounts, login form, private posts, or third-party credentials
are used by this build. It is a first-party public-only mirror of the Flask UI.
"""
import os
import shutil
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"public"
# GitHub Pages repository sites live under /<repository>; Render static lives at /.
URL_PREFIX=os.getenv("BARKAN_STATIC_BASE_PATH","").strip().rstrip("/")
if URL_PREFIX and not re.fullmatch(r"/[A-Za-z0-9_-]+",URL_PREFIX):
    raise ValueError("Only a single clean GitHub Pages repository base path is supported")
if os.getenv("BARKAN_PUBLIC_AUTH","0")=="1":
    raise RuntimeError("Static build must not export authenticated routes")
os.environ.pop("DATABASE_URL",None)
os.environ["BARKAN_PUBLIC_AUTH"]="0"
os.environ["BARKAN_SAFETY_RELEASE_APPROVED"]="0"
os.environ["BARKAN_ALLOW_SIGNUP"]="0"

from app import app

PAGES=("/", "/heritage", "/memorial", "/photos", "/about", "/help",
       "/privacy", "/terms", "/safety", "/status")

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
for route in PAGES:
    with app.test_client() as c:
        response=c.get(route,base_url="https://karnafim-barkan-46.onrender.com")
    if response.status_code!=200:
        raise RuntimeError(f"Static export {route} returned {response.status_code}")
    if b'lang="he" dir="rtl"' not in response.data:
        raise RuntimeError(f"Not RTL: {route}")
    if b'Karnafim' in response.data or b'csrf' in response.data:
        # Export must never accidentally publish private forms.
        raise RuntimeError(f"Private or unexpected content in public export {route}")
    folder=OUT if route=="/" else OUT/route.lstrip("/")
    folder.mkdir(parents=True,exist_ok=True)
    markup=response.data.decode("utf-8")
    if URL_PREFIX:
        # Use explicit index.html for nested public routes to work on every CDN
        # without rewrites, including shared Render static subdirectories.
        def static_link(match):
            attr,path=match.group(1),match.group(2)
            if path.startswith("static/") or path.endswith((".css",".js",".png",".svg",".ico")):
                mapped=path
            elif not path or path.strip("/")=="":
                mapped="index.html"
            else:
                mapped=path.rstrip("/")+"/index.html"
            return attr+'="'+URL_PREFIX+'/'+mapped+'"'
        markup=re.sub(r'(href|src)="/([^"]*)"',static_link,markup)
    (folder/"index.html").write_text(markup,encoding="utf-8")

shutil.copytree(ROOT/"static",OUT/"static",dirs_exist_ok=True)
# GitHub Pages does not run Jekyll or process Flask templates.
(OUT/".nojekyll").write_text("",encoding="utf-8")
(OUT/"robots.txt").write_text("User-agent: *\nAllow: /\nDisallow: /signup\nDisallow: /login\nDisallow: /verify-email\nDisallow: /media/\n",encoding="utf-8")
(OUT/"404.html").write_text(
    '<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8">'
    '<title>העמוד לא נמצא · הקרנפים / ברקן</title>'
    '<link rel="stylesheet" href="/static/site.css"><main>'
    '<section class="pagehead"><h1>העמוד לא נמצא</h1>'
    '<p>אפשר לחזור לעמוד הבית ולבקר בארכיון המורשת.</p>'
    '<a class="primary" href="'+(URL_PREFIX or "")+'/">חזרה לבית</a></section></main></html>',encoding="utf-8")
# These are deliberately public pages only; there is no login form on static.
print(f"Exported {len(PAGES)} public pages to {OUT}")
