"""Export public veteran-community pages for Render static CDN.

No DATABASE_URL, accounts, login form, private posts, or third-party credentials
are used by this build. It is a first-party public-only mirror of the Flask UI.
"""
import os
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"public"
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
    (folder/"index.html").write_bytes(response.data)

shutil.copytree(ROOT/"static",OUT/"static",dirs_exist_ok=True)
(OUT/"robots.txt").write_text("User-agent: *\nAllow: /\nDisallow: /signup\nDisallow: /login\nDisallow: /verify-email\nDisallow: /media/\n",encoding="utf-8")
(OUT/"404.html").write_text(
    '<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8">'
    '<title>העמוד לא נמצא · הקרנפים / ברקן</title>'
    '<link rel="stylesheet" href="/static/site.css"><main>'
    '<section class="pagehead"><h1>העמוד לא נמצא</h1>'
    '<p>אפשר לחזור לעמוד הבית ולבקר בארכיון המורשת.</p>'
    '<a class="primary" href="/">חזרה לבית</a></section></main></html>',encoding="utf-8")
# These are deliberately public pages only; there is no login form on static.
print(f"Exported {len(PAGES)} public pages to {OUT}")
