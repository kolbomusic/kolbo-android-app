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
    '<a href="/members/index.html">כניסה לאזור החברים</a>'
    ' · <a href="/members/index.html">בקשת הצטרפות</a>'
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

# Reliable transition page: this page always loads from the static CDN, even
# while the private member server is asleep. Navigation to the actual auth
# endpoint happens only on a deliberate human click, with no background ping.
member_dir = OUTPUT / "members"
member_dir.mkdir(exist_ok=True)
member_html = """<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<meta name="theme-color" content="#142e27">
<title>אזור החברים · הקרנפים / ברקן</title>
<link rel="stylesheet" href="/static/site.css">
<style>
.member-entry {max-width:780px;margin:5vh auto; padding:35px clamp(20px,5vw,45px);
 background:#fffdf6; border:1px solid #d9dfd5; border-radius:22px;
 box-shadow:0 14px 38px #18322613;}
.member-entry h1{font-size:clamp(28px,5vw,42px);line-height:1.3;margin:0 0 20px}
.member-entry p{margin:10px 0 22px}
.member-actions{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0}
.member-actions a{display:inline-block; padding:12px 19px;border-radius:12px;
 background:#153c30;color:#fff; text-decoration:none;font-weight:700}
.member-actions a.outline{background:#fff; border:1px solid #153c30;color:#153c30}
.member-note{padding:15px 20px;border-right:4px solid #b58b47;
 background:#f6e3c0;border-radius:8px}
#connection-hint{background:#e6eade;padding:14px;border-radius:9px}
</style></head><body>
<a class="skip" href="#main">דלג לתוכן</a>
<header><div class="bar"><a class="logo" href="/">◈ הקרנפים <span>ברקן · פלוגה ב׳</span></a>
<nav aria-label="ניווט"><a href="/">בית</a><a href="/memorial/">הנצחה</a><a href="/heritage/">מורשת</a></nav></div></header>
<main id="main"><section class="member-entry">
<h1>אזור החברים</h1>
<p>מערכת החברים המאובטחת פועלת בשרת נפרד. במסלול האירוח החינמי הוא יכול להיכנס למצב שינה לאחר חוסר פעילות. בעת הכניסה הראשונה ייתכן שיהיה צורך להמתין עד שהשרת יעלה.</p>
<div class="member-actions">
<a data-member-transition href="__BACKEND__/login">התחברות לחברים</a>
<a data-member-transition class="outline" href="__BACKEND__/signup">בקשת הצטרפות</a>
</div>
<p id="connection-hint" role="status" aria-live="polite" hidden>מתחברים לשרת החברים. אם הדף מתעכב, מדובר ככל הנראה בהתעוררות השירות. אין לשלוח שוב טפסים או סיסמאות בזמן ההמתנה.</p>
<div class="member-note">האתר הציבורי נשאר זמין גם כשהשרת הפרטי מתעורר. לא מקלידים סיסמה בדף זה. פרטים אישיים ומסמכים נשלחים רק דרך שרת החברים המאובטח.</div>
<p><a href="/">חזרה לאתר הציבורי</a> · <a href="/status/">מצב השירותים</a></p>
</section></main>
<script>
document.querySelectorAll('[data-member-transition]').forEach(link => {
  link.addEventListener('click', () => {
    document.getElementById('connection-hint').hidden = false;
  });
});
window.addEventListener('pageshow', () => {
  document.getElementById('connection-hint').hidden = true;
});
</script>
</body></html>
""".replace("__BACKEND__", BACKEND)
(member_dir / "index.html").write_text(member_html, encoding="utf-8")

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
