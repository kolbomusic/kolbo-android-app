#!/usr/bin/env python3
"""Build always-on read-only public Karnafim pages for Render Static Sites.

Only checked-in public content is copied. All authenticated member workflows
remain at the existing Flask URL. This is NOT an authentication proxy or a
keep-alive workaround for free Render web services.
"""
from pathlib import Path
import re
import shutil
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "trance-studio" / "entry" / "karnafim"
OUTPUT = ROOT / "karnafim-render-public"
BACKEND = "https://karnafim-community-46.onrender.com"

if not (SOURCE / "index.html").is_file() or not (SOURCE / "static/site.css").is_file():
    raise SystemExit("Missing checked-in static Karnafim assets")
if OUTPUT.exists():
    shutil.rmtree(OUTPUT)
shutil.copytree(SOURCE, OUTPUT)

banner = (
    '<div class="banner">דפי המורשת וההנצחה מוצגים משרת סטטי שאינו נכנס למצב שינה. '
    'ממשק החברים נמצא בשרת נפרד ועלול להתעורר באיטיות אחרי זמן ללא פעילות. '
    '<a href="' + BACKEND + '/login" rel="noopener noreferrer">כניסה לחברים</a>'
    ' · <a href="' + BACKEND + '/signup" rel="noopener noreferrer">בקשת הצטרפות</a>'
    '</div>'
)
count = 0
for path in OUTPUT.rglob("*.html"):
    html = path.read_text(encoding="utf-8").replace("/karnafim/", "/")
    html, replaced = re.subn(
        r'<div class="banner">.*?</div>', banner, html,
        count=1, flags=re.DOTALL
    )
    if path.name != "404.html" and replaced != 1:
        raise SystemExit(f"Missing public-page disclosure banner: {path}")
    count += replaced
    if path == OUTPUT / "status" / "index.html":
        updated = ('<section class="story">'
                   '<p>דפי הבית, המורשת, התמונות הציבוריות וההנצחה מופצים דרך CDN סטטי.</p>'
                   '<p>התחברות, הודעות, הרשמה והעלאות מתקיימות רק בשרת הקהילה הנפרד.'
                   ' בחבילת Render Free השרת הדינמי מתעורר לאחר חוסר פעילות, וייתכן עיכוב של כדקה בכניסה הראשונה.</p>'
                   '<p>אישור חברות ממשיך להיות כפוף לבדיקת מנהל. אימות דוא״ל אוטומטי לא אושר כפעיל.</p>'
                   '<p><a href="' + BACKEND + '/status" rel="noopener noreferrer">'
                   'למצב העדכני של שירות החברים</a></p>'
                   '</section>')
        html, status_count = re.subn(
            r'<section class="story">.*?</section>', updated, html, count=1,
            flags=re.DOTALL
        )
        if status_count != 1:
            raise SystemExit("Missing status disclosure block")
    # A meaningful login link is always present, but no private content or
    # credential form is replicated onto the public static CDN.
    if path.name != "404.html":
        html = html.replace(
            '</nav></div></header>',
            '<a class="member-link" href="' + BACKEND +
            '/login" rel="noopener noreferrer">התחברות לחברים</a></nav></div></header>'
        ) if '</nav></div></header>' in html else html
    path.write_text(html, encoding="utf-8")

# This JS is only for the public menu. On static CDN paths /health does not
# exist, so disable old app connectivity banners that would falsely claim an
# outage even though the CDN is serving correctly.
script = OUTPUT / "static" / "site.js"
js = script.read_text(encoding="utf-8")
start = js.index("  // Render Free can suspend an idle web service.")
end = js.index("  if (!toggle || !nav) return;", start)
js = js[:start] + "  // Public static pages never probe or submit member data.\n" + js[end:]
script.write_text(js, encoding="utf-8")

class LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []
    def handle_starttag(self, tag, attrs):
        if tag not in ("a", "script", "link", "img"):
            return
        attributes = dict(attrs)
        url = attributes.get("href") if tag in ("a", "link") else attributes.get("src")
        if url and url.startswith("/") and not url.startswith("//"):
            self.paths.append(url.split("?", 1)[0].split("#", 1)[0])

for htmlpath in OUTPUT.rglob("*.html"):
    parser = LinkCollector()
    parser.feed(htmlpath.read_text(encoding="utf-8"))
    for url in parser.paths:
        resource = OUTPUT / url.lstrip("/")
        if resource.is_dir():
            resource = resource / "index.html"
        if not resource.is_file():
            raise SystemExit(f"Broken static link {url!r} in {htmlpath.relative_to(OUTPUT)}")

memorial = (OUTPUT / "memorial" / "index.html").read_text(encoding="utf-8")
for personal_id in (
    "en_f5ccba845584f96f9b9334cf335d2e78",
    "en_f53b79619b3f27184812b11f14e635a8",
    "en_e6446f8f52c2b18e0ec560602482bdda",
    "en_34b2955a02b6a81f8ba932dbf6228e61",
    "en_53e66dd727188835acbe02a1f641a882",
):
    if personal_id not in memorial:
        raise SystemExit("Official memorial identity link missing")
if 'fetch("/health"' in script.read_text(encoding="utf-8"):
    raise SystemExit("Static CDN JS still probes dynamic /health")
print(f"PASS: {count} public pages built with verified links, no static member auth or backend probing")
