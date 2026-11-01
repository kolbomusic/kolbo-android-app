"""Karnafim community features: sourced archive, opt-in feed and private conversations."""
import io, html, hashlib, os
from datetime import date
import psycopg
from PIL import Image, ImageOps, UnidentifiedImageError
from moderation_engine import moderate, configured
from urllib.parse import quote, urlsplit
from flask import request, redirect, abort, send_file, session, Response
from archive_data import ARCHIVE

CSS = """<style>
.portal{--pine:#18392e;--cream:#eff2e9;--line:#d8e3d4;--lime:#d5ea99}
.portal h1{font-size:clamp(32px,5vw,52px);line-height:1.18;letter-spacing:-1.2px;margin:4px 0 18px}
.portal h2{font-size:clamp(22px,3vw,30px);margin:6px 0 15px}
.portal h3{font-size:19px;margin:8px 0}
.portal p{line-height:1.75}
.portal .mast{background:linear-gradient(115deg,#142e25,#345b45);color:white;padding:clamp(26px,5vw,52px);border-radius:20px;position:relative;overflow:hidden}
.portal .mast:after{content:'46';font-size:clamp(150px,22vw,280px);font-weight:900;position:absolute;bottom:-120px;left:-10px;color:#fff;opacity:.065;pointer-events:none}
.portal .mast p{font-size:17px;color:#e7ecdd;max-width:650px}
.portal .kicker{color:#b7d775;font-weight:800;font-size:13px;letter-spacing:.6px}
.portal .actions{display:flex;gap:10px;flex-wrap:wrap;margin:22px 0 0}
.portal .cta{background:#d9eba0;color:#1a3127;text-decoration:none;padding:12px 18px;border-radius:11px;display:inline-flex;align-items:center;justify-content:center;font-weight:800}
.portal .cta.alt{border:1px solid #c6d9be;background:#ffffff15;color:white}
.portal .tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(225px,1fr));gap:14px;margin:20px 0 30px}
.portal .tile,.portal .source,.portal .event{border:1px solid #dce5da;background:white;border-radius:16px;padding:21px;box-shadow:0 5px 15px #1936280a}
.portal .tile p,.portal .source p{color:#52695b}
.portal .tile .emoji{font-size:30px}
.portal .tile a,.portal .source a{font-weight:750}
.portal .metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:17px 0}
.portal .metric{padding:17px;border-radius:14px;background:#fff;border:1px solid #dee5da}
.portal .metric strong{display:block;font-size:26px;color:#244b3b}.portal .metric small{color:#708071}
.portal .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin:20px 0}
.portal .source{display:flex;flex-direction:column;gap:7px;min-height:220px}
.portal .source .emoji{font-size:26px}.portal .source p{flex:1;margin:0 0 8px}.portal .source small{color:#66796a}
.portal .tag{display:inline-block;background:#e9f0de;color:#38533f;font-size:12px;font-weight:700;border-radius:22px;padding:4px 10px}
.portal .filters{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}
.portal .filters a{border:1px solid #cbddc8;border-radius:22px;padding:7px 12px;background:#fff;text-decoration:none}
.portal .filters a.on{background:#284c3c;color:#fff}
.portal .note{background:#e8efe3;color:#345342;padding:17px 19px;border-radius:13px;margin:20px 0}
.portal .event{margin:15px 0}
.portal .event .preview{max-width:100%;max-height:340px;border-radius:12px;display:block;margin:15px 0;background:#e9efe3}
.portal .event audio{width:100%;margin:12px 0}
.portal .event video{width:100%;max-height:360px;border-radius:12px;margin:12px 0;background:#091a15}
.portal .event .byline{font-size:12px;color:#607266}
.portal .form-box{background:#fff;padding:23px;border:1px solid #d9e4d5;border-radius:16px}
.portal .btn{display:inline-flex;align-items:center;justify-content:center;text-decoration:none;font-weight:800}
.portal textarea{width:100%;min-height:100px}
.portal .voice{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.portal .voice button{background:#e5eddd}
.portal .voice small{color:#62786d}
.portal .search{display:flex;gap:10px;max-width:none}
.portal .search input{flex:1;min-width:150px}
.portal .chat-layout{display:grid;grid-template-columns:minmax(180px,1fr) 2fr;gap:18px}
.portal .bubble{background:#fff;padding:12px 15px;border:1px solid #d9e3d5;border-radius:14px;max-width:85%;margin:11px 0}
.portal .bubble.mine{background:#e3efce;margin-right:auto}
.portal .bubble img{max-width:100%;max-height:270px;border-radius:8px}
.portal .bubble video{max-width:100%;max-height:260px}
.portal .bubble audio{width:100%}
.portal .bubble small{display:block;color:#657c6d}
.portal .people a{display:block;border-radius:10px;padding:10px;background:white;margin:7px 0;border:1px solid #e0e6da}
.portal .muted{color:#627568}
.portal .copy-area{background:#ecf0e5;border:1px solid #d2dec7;border-radius:12px;padding:15px;overflow-wrap:anywhere}
.portal .media-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:13px}
.portal .media-grid img{height:190px;object-fit:cover;width:100%;border-radius:10px}
.portal .compact{margin:0}
.portal .photo-heritage{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(240px,1fr);gap:22px;margin:22px 0;padding:20px;background:white;border:1px solid #dce5da;border-radius:18px;align-items:center}
.portal .photo-heritage figure{margin:0}.portal .photo-heritage img{display:block;width:100%;max-height:290px;object-fit:contain;border-radius:12px;background:#f4f5f1}.portal .photo-heritage figcaption{font-size:12px;color:#5c6b60;line-height:1.6;margin-top:8px}
@media(max-width:720px){.portal .photo-heritage{grid-template-columns:1fr;padding:14px}}
@media(max-width:720px){.portal .chat-layout{display:block}.portal .metrics{gap:5px}.portal .metric{padding:10px}.portal .metric strong{font-size:23px}.portal .actions{flex-direction:column}.portal .actions a{width:100%}.portal .mast{padding:27px 20px}}
</style>"""

RECENT = ARCHIVE

def install(app, sql, view, me, admin, guard, formwrap, esc):
    # Persistent metadata and compact binary storage for the free-tier pilot.
    sql("""ALTER TABLE requests ADD COLUMN IF NOT EXISTS accepted BOOLEAN NOT NULL DEFAULT FALSE""")
    sql("""ALTER TABLE members ADD COLUMN IF NOT EXISTS facebook_url TEXT NOT NULL DEFAULT ''""")
    sql("""ALTER TABLE members ADD COLUMN IF NOT EXISTS instagram_url TEXT NOT NULL DEFAULT ''""")
    sql("""ALTER TABLE members ADD COLUMN IF NOT EXISTS linkedin_url TEXT NOT NULL DEFAULT ''""")
    sql("""CREATE TABLE IF NOT EXISTS community_posts (
      id BIGSERIAL PRIMARY KEY, author_id BIGINT NOT NULL REFERENCES members(id) ON DELETE CASCADE,
      title TEXT NOT NULL, body TEXT NOT NULL, story_year INTEGER, approved BOOLEAN NOT NULL DEFAULT FALSE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    sql("ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS post_type TEXT NOT NULL DEFAULT 'story'")
    sql("ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS event_date DATE")
    sql("ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS event_place TEXT NOT NULL DEFAULT ''")
    sql("ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS ai_consent BOOLEAN NOT NULL DEFAULT FALSE")
    sql("ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS ai_status TEXT NOT NULL DEFAULT 'held'")
    sql("ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS ai_reason TEXT NOT NULL DEFAULT 'Legacy post requires review'")
    sql("ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS ai_model TEXT NOT NULL DEFAULT ''")
    sql("ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS ai_checked_at TIMESTAMPTZ")
    sql("ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS ai_attempts INTEGER NOT NULL DEFAULT 0")
    sql("""CREATE TABLE IF NOT EXISTS community_comments (
      id BIGSERIAL PRIMARY KEY,
      post_id BIGINT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
      author_id BIGINT NOT NULL REFERENCES members(id) ON DELETE CASCADE,
      body TEXT NOT NULL,
      approved BOOLEAN NOT NULL DEFAULT FALSE,
      ai_consent BOOLEAN NOT NULL DEFAULT FALSE,
      ai_status TEXT NOT NULL DEFAULT 'pending_ai',
      ai_reason TEXT NOT NULL DEFAULT '',
      ai_model TEXT NOT NULL DEFAULT '',
      ai_checked_at TIMESTAMPTZ,
      ai_attempts INTEGER NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    sql("""CREATE INDEX IF NOT EXISTS community_comments_visible ON community_comments(post_id,approved,created_at DESC)""")
    sql("""CREATE TABLE IF NOT EXISTS community_media (
      id BIGSERIAL PRIMARY KEY, owner_id BIGINT NOT NULL REFERENCES members(id) ON DELETE CASCADE,
      post_id BIGINT REFERENCES community_posts(id) ON DELETE CASCADE,
      recipient_id BIGINT REFERENCES members(id) ON DELETE CASCADE,
      mime TEXT NOT NULL, kind TEXT NOT NULL, filename TEXT NOT NULL DEFAULT '',
      data BYTEA NOT NULL, length INTEGER NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    sql("""ALTER TABLE messages ADD COLUMN IF NOT EXISTS media_id BIGINT REFERENCES community_media(id) ON DELETE SET NULL""")
    sql("""CREATE INDEX IF NOT EXISTS community_media_post_idx ON community_media(post_id)""")
    sql("""CREATE INDEX IF NOT EXISTS community_media_recipient_idx ON community_media(recipient_id)""")
    sql("""CREATE INDEX IF NOT EXISTS community_posts_approved_idx ON community_posts(approved,created_at DESC)""")
    app.config["MAX_CONTENT_LENGTH"]=36*1024*1024
    app.config["SEND_FILE_MAX_AGE_DEFAULT"]=0

    def e(v):
        return html.escape(str(v if v is not None else ""),quote=True)

    def link(url,text,external=False):
        return '<a href="'+e(url)+'"'+(' target="_blank" rel="noopener noreferrer"' if external else '')+'>'+e(text)+'</a>'

    def page(title,markup):
        return view(title,CSS+'<div class="portal">'+markup+'</div>')

    def approved():
        user=me()
        if not user or not user["approved"]: abort(403)
        return user

    def is_connected(a,b):
        if a==b:return False
        return bool(sql("SELECT 1 FROM requests WHERE accepted=TRUE AND ((sender_id=%s AND recipient_id=%s) OR (sender_id=%s AND recipient_id=%s)) LIMIT 1",(a,b,b,a),True))

    def search_card(x):
        return '<article class="source"><div class="emoji">'+e(x["icon"])+'</div><span class="tag">'+e(x["tag"])+((' · '+e(x["year"])) if x["year"] else '')+'</span><h3>'+e(x["title"])+'</h3><p>'+e(x["summary"])+'</p><small>הוזכר במקור: '+e(x["source"])+'</small>'+link("/source/"+str(x["id"]),"לפרטי האזכור באתר ←")+'</article>'

    @app.route("/source/<int:source_id>")
    def source_detail(source_id):
        item=next((x for x in ARCHIVE if x["id"]==source_id),None)
        if not item:abort(404)
        verified_source=item["url"]
        detail={
            1:"דף יזכור הרשמי כולל את סיפור חייו של יוני, פרטים על שירותו, דברי חברים וזיכרונות. זהו המקור המלא, ולא רק אזכור שמו.",
            2:"עדויות החברים מופיעות כחלק מדף ההנצחה הרשמי של יוני. המקור כולל את דברי אלעד זומר וחברים נוספים, לצד סיפור חייו.",
            3:"שמות מפקדים וחברים מוזכרים בעדויות מדף יזכור של יוני. אין לפרש אזכור במקור כהשתתפות רשומה באתר הקהילה.",
            4:"כתבה המתארת את ערב המורשת של גדוד 46 לציון עשור למלחמת לבנון השנייה, ואת פעילות הלוחמים והמפקדים.",
            5:"רישום ביבליוגרפי מפורט על חוברת הגדוד (2007, 84 עמודים), עם מידע על תולדותיו. זהו רישום ספר ולא עותק מלא של 84 העמודים.",
            6:"האתר הרשמי של צה״ל מתאר את גדוד 46 ואת פלוגת ברקן כחלק מגדודי חטיבה 401.",
            7:"עמוד יד לשריון מרכז הפניות לתמונות וסרטונים של חטיבה 401. זמינות קובצי המדיה החיצוניים עצמם אינה מובטחת.",
            8:"אתר המורשת ההיסטורי מתמקד בפעילות גדוד 46 במלחמת יום הכיפורים, לרבות תצלומים וסיפורים מהתקופה.",
            9:"דף יזכור הרשמי כולל קורות חיים, שירות צבאי, תיאור כוח בניה והנצחה.",
            10:"דף יזכור הרשמי כולל את סיפור חייו ושירותו של אורי גרוסמן, עדויות וחומרי הנצחה.",
            11:"אתר הנצחה ייעודי לבניה ריין, עם פרקים על חייו, כוח בניה, כתבים, סרטים וגלריה.",
            12:"עמוד ארכיון המדיה של חטיבה 401 וגדוד 46 באתר יד לשריון. הוא מכיל קישורים למקורות נוספים אך לא בהכרח מארח בעצמו את כל הסרטונים.",
            13:"דף יזכור הרשמי כולל את סיפור חייו של אדם גורן, שירותו והנצחתו.",
            14:"דף יזכור הרשמי כולל את קורותיו של אלכסנדר (סשה) בונימוביץ׳ ופעילות צוות הטנק."
        }
        is_full=source_id not in (5,7,12)
        label="📖 לקריאת התוכן המלא במקור המאומת ↗" if is_full else "📚 לפתיחת עמוד המקור והרישום המפורט ↗"
        page_html='<h1>'+e(item["title"])+'</h1><span class="tag">'+e(item["tag"])+' · '+e(item["year"] or "ארכיון")+'</span>'
        page_html+='<article class="event"><h2>מה מתועד בפרסום?</h2><p>'+e(detail.get(source_id,item["summary"]))+'</p><p><strong>תקציר המורשת:</strong> '+e(item["summary"])+'</p><p class="muted">גוף המקור: '+e(item["source"])+'</p></article>'
        page_html+='<div class="note"><h2>המקור המקורי</h2><p>הקישור מוביל ישירות לעמוד שנמצא במקור הרשמי או לאתר המורשת. לא לחיפוש בגוגל. זמינותו יכולה להשתנות בעתיד.</p>'
        page_html+='<p><a class="cta" href="'+e(verified_source)+'" target="_blank" rel="noopener noreferrer">'+label+'</a></p>'
        page_html+='<p><small>באתר הקרנפים מוצג תקציר מקורי. כל התוכן המלא, התמונות והמסמכים מתפרסמים בכפוף לזכויות באתר המקור.</small></p></div>'
        page_html+='<div class="actions"><a class="cta alt" href="/archive">↩ חזרה לכל מקורות הארכיון</a></div>'
        return page(item["title"],page_html)

    def sources(count=0,filtertag=""):
        items=[x for x in RECENT if not filtertag or x["tag"]==filtertag]
        if count:items=items[:count]
        return '<div class="grid">'+''.join(search_card(x) for x in items)+'</div>'

    def statistics():
        members=sql("SELECT COUNT(*) n FROM members WHERE approved AND visible",fetch=True)[0]["n"]
        posts=sql("SELECT COUNT(*) n FROM community_posts WHERE approved",fetch=True)[0]["n"]
        return '<div class="metrics"><div class="metric"><strong>'+e(len(RECENT))+'</strong><small>מקורות בארכיון</small></div><div class="metric"><strong>'+e(members)+'</strong><small>חברים שהסכימו להופיע</small></div><div class="metric"><strong>'+e(posts)+'</strong><small>סיפורים שאושרו</small></div></div>'

    def home():
        u=me()
        actions=('<a class="cta" href="/directory">🔎 איתור חברים</a><a class="cta alt" href="/new-post">📸 שתפו סיפור, אירוע או תמונות</a><a class="cta alt" href="/my-posts">📝 הפרסומים שלי</a><a class="cta alt" href="/chats">💬 הודעות</a>' if u and u["approved"] else '<a class="cta" href="/register">🦏 הייתי שם — מצטרפים</a><a class="cta alt" href="/login">🔑 כבר חברים? כניסה לחשבון</a>')
        b='<section class="mast"><span class="kicker">401 / 46 / פלוגה ב׳ • 2003–2006</span><h1>עשרים שנה עברו.<br>החברים עדיין כאן.</h1><p>הקרנפים, שלימים נקראו ברקן. בית לקולות, לסיפורים, לתמונות ולחברים ששירתו איתנו. כאן מתחברים מחדש — ושומרים יחד על המורשת.</p><div class="actions">'+actions+'</div></section>'
        b+='<section class="photo-heritage"><figure><img loading="lazy" src="https://upload.wikimedia.org/wikipedia/commons/thumb/6/69/Merkava-4-tank-6611a-white1.jpg/1280px-Merkava-4-tank-6611a-white1.jpg" alt="טנק מרכבה סימן 4 — צילום המחשה מארכיון Wikimedia Commons"><figcaption>טנק מרכבה סימן 4, צילום המחשה משנת 2015 — <strong>לא תצלום של פלוגת הקרנפים</strong>. צילום: <a href="https://commons.wikimedia.org/wiki/File:Merkava-4-tank-6611a-white1.jpg" target="_blank" rel="noopener noreferrer">צחי אבנור / MathKnight, Wikimedia Commons</a>, רישיון <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener noreferrer">CC BY-SA 4.0</a>.</figcaption></figure><div><h2>התמונות שלנו מתחילות כאן</h2><p>תצלומים מקוריים מהפלוגה יופיעו לאחר שחברים יעלו אותם, יסכימו לשיתוף ויאושרו על ידי מנהלי הקהילה.</p><a class="cta" href="/photos">📸 לאלבום התמונות</a></div></section>'
        b+=statistics()
        b+='<h2>לא צריך לזכור הכול — מתחילים מכאן</h2><div class="tiles">'
        tiles=[("🧭","מאתרים חברים","חיפוש לפי שם, כינוי ומחזור + איתור מבוסס קישורים ברשתות.","/find"),("📸","תמונות וזיכרונות","משתפים סיפור, תמונה, הקלטה או סרטון קצר באישור מנהל.","/feed"),("💬","צ׳אט חברים","הודעות פרטיות, תמונות, קול וסרטונים אחרי אישור בקשת קשר.","/chats"),("📜","ארכיון מתועד","עדויות, סרטוני מורשת ומקורות על גדוד 46 ופלוגת הקרנפים.","/archive"),("🤝","מזמינים חברים","שליחת קישור לפלוגה בוואטסאפ, פייסבוק או בהעתקה.","/invite"),("🕯️","זוכרים יחד","דפי הנצחה אישיים וחיפוש תמונות המאפשר להציע תמונות לגלריה המתאימה.","/memorials")]
        b+=''.join('<article class="tile"><div class="emoji">'+t[0]+'</div><h3>'+t[1]+'</h3><p>'+t[2]+'</p>'+link(t[3],"לפתיחה ←")+'</article>' for t in tiles)+'</div>'
        b+='<h2>רגעים בציר הזמן שלנו</h2><div class="tiles"><article class="tile"><span class="tag">2005</span><h3>יוני מצטרף לפלוגה</h3><p>לפי אתר יזכור, יוני התגייס ביולי 2005 ובהמשך שובץ בפלוגה ב׳ שכונתה ״הקרנפים״.</p>'+link("/source/1","לפרטי האזכור ←")+'</article><article class="tile"><span class="tag">אוגוסט 2006</span><h3>מלחמת לבנון השנייה</h3><p>הגדוד איבד את יוני שרעבי ואת אנשי כוח בניה. נזכור את חברינו בכבוד.</p>'+link("/source/4","לפרטי כתבת המורשת ←")+'</article><article class="tile"><span class="tag">2007</span><h3>ספר מורשת גדוד שלח</h3><p>חוברת מורשת הגדוד יצאה לאור בשנת 2007 וחולקה באירוע מורשת בגבעת ברנר.</p>'+link("/source/5","לפרטי ספר המורשת ←")+'</article></div>'
        b+='<div class="tile"><h2>🎞️ תצלומים וסרטוני מורשת — גדוד 46</h2><p>קישורים לאלבומים וסרטונים באתר יד לשריון. חלק מהסרטונים הישנים הוסרו משירותי וידאו, ולכן כדי למנוע נגן שבור מפנים לעמוד המקור המאומת.</p><div class="actions"><a class="cta" href="/source/12">🎬 לפרטי ארכיון התמונות והסרטונים ←</a></div></div>'
        b+='<h2>מתוך הארכיון של הפלוגה והגדוד</h2><p class="muted">אזכורים ממקורות מתועדים. קישורים לפרסומים ישנים עלולים להיות לא זמינים.</p>'+sources(4)+link("/archive","צפייה בכל המקורות ←")
        b+='<section class="note"><strong>הראשונים שפותחים את הדרך</strong><p>חברי הפלוגה שיבחרו להירשם ולהופיע במדריך יוכלו לאתר אחד את השני. שמות שמוזכרים במקורות אינם חשבונות רשומים, ולא מופיעים כאן פרטי קשר פרטיים.</p></section>'
        return page("בית הקרנפים",b)

    @app.route("/archive")
    def archive():
        tag=request.args.get("type","")[:30]
        b='<h1>ארכיון הקרנפים וגדוד שלח</h1><p>קורות הפלוגה, זיכרונות החברים, פרסומים וסרטוני מורשת. כל כרטיס נפתח כאן באתר, עם פרטי מקור ואפשרות לחפש אותו. אין הפניה לכתבות שהקישור הישיר שלהן אינו מאומת.</p><div class="filters">'
        for x in ["","זיכרון","אנשים","מורשת","וידאו"]:
            b+='<a class="'+("on" if x==tag else "")+'" href="/archive'+("?type="+quote(x) if x else "")+'">'+e(x or "הכול")+'</a>'
        b+='</div>'+sources(filtertag=tag)
        b+='<div class="note">רוצים להוסיף פרסום שמצאתם? אפשר לפרסם קישור בהוספת זיכרון. מנהל הקהילה יאמת את המידע לפני אישורו.</div>'
        return page("ארכיון מקורות",b)

    @app.route("/find")
    def find():
        q=request.args.get("q","").strip()[:80]
        search=q if q else '"גדוד 46" "ברקן"'
        qs={
            "🌐 חיפוש כללי": "https://www.google.com/search?q="+quote(search),
            "🖼️ תמונות ברשת": "https://www.google.com/search?tbm=isch&q="+quote(search),
            "👥 קבוצות פייסבוק": "https://www.facebook.com/search/groups/?q="+quote(q or "גדוד 46 שלח"),
            "🔵 פייסבוק דרך Google": "https://www.google.com/search?q="+quote("site:facebook.com "+search),
            "📹 YouTube": "https://www.youtube.com/results?search_query="+quote(search),
            "📸 אינסטגרם": "https://www.google.com/search?q="+quote("site:instagram.com "+search),
            "💼 לינקדאין": "https://www.google.com/search?q="+quote("site:linkedin.com/in "+search),
            "📜 יד לשריון": "https://www.google.com/search?q="+quote("site:yadlashiryon.com "+search),
            "🕯️ יזכור": "https://www.google.com/search?q="+quote("site:izkor.gov.il "+search),
        }
        b='<h1>מאיפה מתחילים למצוא את החברים?</h1><p>כותבים שם, כינוי או אירוע. המערכת מכינה חיפוש ממוקד במאגרים ובקבוצות ציבוריות; היא אינה נכנסת לחשבונות פרטיים או שואבת פרטים אישיים ללא הסכמה.</p><form class="search" action="/find" method="get"><label for="veteran-search">חיפוש מידע פומבי על חברים ופלוגה</label><input id="veteran-search" name="q" placeholder="למשל: פלוגת הקרנפים 2006" value="'+e(q)+'"><button>חיפוש</button></form>'
        b+='<div class="tiles">'+''.join('<div class="tile"><h3>'+e(k)+'</h3><p>פתיחת חיפוש ממוקד במקור החיצוני</p>'+link(v,"הצגת תוצאות ↗",True)+'</div>' for k,v in qs.items())+'</div>'
        b+='<div class="note">מכירים מישהו מהרשימה ההיסטורית? פנו אליו דרך ערוץ פומבי המקובל עליו או שלחו לו את קישור ההזמנה. אין לבצע התאמת זהות אוטומטית בין אדם שמוזכר במקור לבין פרופיל פרטי ברשת.</div>'
        return page("איתור חברים",b)

    @app.route("/invite")
    def invite():
        url="https://karnafim-community-46.onrender.com/"
        msg="מחפשים חברים מפלוגה ב׳ הקרנפים / ברקן, גדוד 46 חטיבה 401, במיוחד מחזורי 2003–2006. בואו לחדש קשר: "+url
        wa="https://wa.me/?text="+quote(msg)
        fb="https://www.facebook.com/sharer/sharer.php?u="+quote(url)
        b='<h1>הזמינו חברים מהפלוגה</h1><p>כל חבר שיצטרף יוכל לבקש אישור ולהחליט מה להציג לאחרים.</p><div class="copy-area" id="share-link">'+e(msg)+'</div><div class="actions"><a class="cta" href="'+e(wa)+'" target="_blank" rel="noopener">וואטסאפ</a><a class="cta" href="'+e(fb)+'" target="_blank" rel="noopener">פייסבוק</a><button type="button" id="copy-link" onclick="navigator.clipboard.writeText(document.getElementById(\'share-link\').innerText).then(()=>{this.textContent=\'הועתק ✓\'})">📋 העתקת הודעה</button></div><div class="note">כדאי לשתף בקבוצות יוצאי חטיבה 401 / גדוד 46 ובקבוצות מחזור, בלי לפרסם מספרים אישיים של אחרים.</div>'
        return page("הזמנת חברים",b)

    def inspect_file(f):
        if not f or not getattr(f,"filename",""):return None
        f.stream.seek(0)
        data=f.read(9*1024*1024)
        mime=(f.mimetype or "").lower().split(";")[0]
        kind=None;maxsize=0
        if mime=="image/jpeg" and data[:3]==b"\xff\xd8\xff":kind,maxsize="image",8*1024*1024
        elif mime=="image/png" and data[:8]==b"\x89PNG\r\n\x1a\n":kind,maxsize="image",8*1024*1024
        elif mime=="image/webp" and data[:4]==b"RIFF" and data[8:12]==b"WEBP":kind,maxsize="image",8*1024*1024
        elif mime in ("video/mp4","video/quicktime") and data[4:8]==b"ftyp":kind,maxsize="video",8*1024*1024
        elif mime=="video/webm" and data[:4]==b"\x1a\x45\xdf\xa3":kind,maxsize="video",8*1024*1024
        elif mime=="audio/webm" and data[:4]==b"\x1a\x45\xdf\xa3":kind,maxsize="audio",2*1024*1024
        elif mime in ("audio/ogg","application/ogg") and data[:4]==b"OggS":kind,maxsize="audio",2*1024*1024
        elif mime in ("audio/mp4","audio/x-m4a") and data[4:8]==b"ftyp":kind,maxsize="audio",2*1024*1024
        elif mime=="audio/wav" and data[:4]==b"RIFF" and data[8:12]==b"WAVE":kind,maxsize="audio",2*1024*1024
        if not kind or not data or len(data)>maxsize:
            abort(400,"קובץ לא נתמך או גדול מהמותר. תמונה עד 8MB לפני כיווץ, קול 2MB, וידאו 8MB.")
        if kind=="image":
            try:
                check=Image.open(io.BytesIO(data))
                check.verify()
                check=Image.open(io.BytesIO(data))
                if check.format not in ("JPEG","PNG","WEBP") or check.width*check.height>12_000_000:
                    abort(400,"ממדי תמונה לא תקינים")
                image=ImageOps.exif_transpose(check).convert("RGB")
                image.thumbnail((1800,1800))
                sanitized=io.BytesIO()
                image.save(sanitized,format="JPEG",quality=82,optimize=True)
                data=sanitized.getvalue()
                mime="image/jpeg"
                if len(data)>3*1024*1024:abort(413,"תמונה גדולה מדי")
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                abort(400,"קובץ תמונה פגום או לא תקין")
        total=sql("SELECT COALESCE(SUM(length),0) n FROM community_media",fetch=True)[0]["n"]
        user=me()
        mine=sql("SELECT COALESCE(SUM(length),0) n FROM community_media WHERE owner_id=%s",(user["id"],),True)[0]["n"]
        if total+len(data)>150*1024*1024 or mine+len(data)>25*1024*1024:abort(413,"מכסת האחסון התמלאה.")
        return {"data":data,"mime":mime,"kind":kind,"size":len(data),"filename":("photo.jpg" if kind=="image" else "member-upload")}

    def store_attachment(owner, f, post_id=None, recipient_id=None):
        info=inspect_file(f)
        if not info:return None
        rows=sql("INSERT INTO community_media(owner_id,post_id,recipient_id,mime,kind,filename,data,length) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
          (owner["id"],post_id,recipient_id,info["mime"],info["kind"],info["filename"],info["data"],info["size"]),True)
        return rows[0]["id"]

    def recorder(input_id):
        return """<div class="voice"><button type="button" class="record-voice" data-target='"""+e(input_id)+"""'>🎙️ הקלטת הודעה קולית</button><small class="record-status">ניתן להקליט עד 20 שניות בדפדפן, באישור גישה למיקרופון.</small></div>"""

    RECORD_JS = """<script>
document.querySelectorAll('.record-voice').forEach(btn=>{
 let rec,stream,parts=[],timer;
 btn.addEventListener('click', async ()=>{
  if(rec && rec.state==='recording'){rec.stop();return;}
  const status=btn.parentElement.querySelector('.record-status');
  if(!navigator.mediaDevices || !window.MediaRecorder){status.textContent='הדפדפן אינו תומך בהקלטה. אפשר להעלות קובץ שמע.';return;}
  try{
   stream=await navigator.mediaDevices.getUserMedia({audio:true});
   const prefs=['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'];
   const mime=prefs.find(x=>MediaRecorder.isTypeSupported(x))||'';
   rec=mime?new MediaRecorder(stream,{mimeType:mime}):new MediaRecorder(stream);
   parts=[];
   rec.ondataavailable=e=>{if(e.data.size)parts.push(e.data)};
   rec.onstop=()=>{
    clearTimeout(timer);
    stream.getTracks().forEach(x=>x.stop());
    const blob=new Blob(parts,{type:rec.mimeType});
    if(blob.size>2*1024*1024){status.textContent='ההקלטה גדולה מדי. נסו הקלטה קצרה יותר.';return;}
    const ext=rec.mimeType.includes('mp4')?'m4a':rec.mimeType.includes('ogg')?'ogg':'webm';
    const dt=new DataTransfer();
    dt.items.add(new File([blob],'voice.'+ext,{type:rec.mimeType.split(';')[0]}));
    const input=document.getElementById(btn.dataset.target);
    input.files=dt.files;
    status.textContent='✓ ההקלטה מוכנה לשליחה ('+Math.ceil(blob.size/1024)+' KB)';
    btn.textContent='🎙️ הקלטה חדשה';
   };
   rec.start();
   btn.textContent='⏹️ עצירת הקלטה';
   status.textContent='מקליט כעת…';
   timer=setTimeout(()=>{if(rec.state==='recording')rec.stop()},20000);
  }catch(e){status.textContent='לא ניתן להפעיל מיקרופון: '+e.message;}
 })
});
</script>"""

    def media_html(mid,kind,chat=False):
        url="/community-media/"+str(mid)
        if kind=="image":return '<a href="'+url+'" target="_blank" rel="noopener"><img class="'+("preview" if not chat else "")+'" src="'+url+'" alt="תמונה שחבר שיתף"></a>'
        if kind=="video":return '<video controls preload="metadata" playsinline aria-label="סרטון שחבר שיתף" src="'+url+'">הדפדפן אינו תומך בהצגת הסרטון.</video>'
        if kind=="audio":return '<audio controls preload="none" aria-label="הקלטה קולית שחבר שיתף" src="'+url+'">הדפדפן אינו תומך בהשמעת הקובץ.</audio>'
        return ""

    @app.route("/community-media/<int:media_id>")
    def community_media(media_id):
        u=me()
        if not u or not u["approved"]:abort(403)
        r=sql("SELECT m.*,p.approved post_approved FROM community_media m LEFT JOIN community_posts p ON p.id=m.post_id WHERE m.id=%s",(media_id,),True)
        if not r:abort(404)
        m=r[0]
        can_view=False
        if m["owner_id"]==u["id"]:can_view=True
        elif m["post_id"] is not None:can_view=bool(m["post_approved"])
        elif m["recipient_id"]==u["id"] and is_connected(m["owner_id"],u["id"]):can_view=True
        elif admin(u):can_view=True
        if not can_view:abort(403)
        response=send_file(io.BytesIO(bytes(m["data"])),mimetype=m["mime"],as_attachment=False,download_name="shared-"+str(media_id))
        response.headers["Cache-Control"]="private, no-store"
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Content-Security-Policy"]="default-src 'none'; sandbox"
        return response

    def upload_form(is_post=True):
        if is_post:
            target="post-files"
            form='<label>📎 הוספת תמונות, סרטון או הקלטה (עד ארבעה קבצים)<input id="'+target+'" type="file" name="attachments" multiple accept="image/jpeg,image/png,image/webp,video/mp4,video/webm,audio/webm,audio/ogg,audio/mp4,audio/wav"></label>'
            form+='<div id="file-summary" aria-live="polite" class="muted">ניתן לצרף עד ארבעה קבצים. תמונות עד 8MB לקובץ לפני כיווץ אוטומטי; סרטון עד 8MB וקול עד 2MB.</div>'
            form+='<div id="upload-previews" class="media-grid"></div>'
            return form+recorder(target)+'<p class="muted">תמונות יעברו כיווץ והסרת פרטי מיקום. שמרו על הסכמת המצולמים. עד 25MB אחסון לכל חבר במסגרת הניסוי.</p>'
        return '<label>📎 צירוף תמונה / סרטון / קול<input id="chat-file" type="file" name="attachment" accept="image/jpeg,image/png,image/webp,video/mp4,video/webm,audio/webm,audio/ogg,audio/mp4,audio/wav"></label>'+recorder("chat-file")+'<p class="muted">תמונה עד 8MB לפני כיווץ, קול עד 2MB, וידאו עד 8MB.</p>'

    UPLOAD_JS = """<script>
(()=>{
  const input=document.getElementById('post-files');
  if(!input)return;
  const previews=document.getElementById('upload-previews');
  const summary=document.getElementById('file-summary');
  let urls=[];
  input.addEventListener('change',()=>{
    urls.forEach(url=>URL.revokeObjectURL(url));urls=[];previews.replaceChildren();
    const files=Array.from(input.files||[]);
    if(files.length>4){summary.textContent='ניתן להעלות עד ארבעה קבצים בפרסום אחד.';input.setCustomValidity('עד ארבעה קבצים');return;}
    const bytes=files.reduce((sum,f)=>sum+f.size,0);
    if(bytes>32*1024*1024){input.setCustomValidity('הקבצים גדולים מדי');summary.textContent='סך כל הקבצים גדול מ־32MB.';return;}
    input.setCustomValidity('');
    summary.textContent=files.length+' קבצים נבחרו, '+(bytes/1024/1024).toFixed(1)+'MB לפני כיווץ.';
    files.filter(f=>f.type.startsWith('image/')).forEach(f=>{
      const img=document.createElement('img');
      const url=URL.createObjectURL(f);urls.push(url);
      img.src=url;img.alt='תצוגה מקדימה: '+f.name;
      img.loading='lazy';img.style='width:100%;max-height:170px;object-fit:contain;border-radius:9px';
      previews.appendChild(img);
    });
  });
})();
</script>"""

    # The free Render host can sleep during long drafting sessions. Keep text in
    # tab-local sessionStorage, never store attachments or credentials in the browser.
    DRAFT_JS = """<script>
(function(){
 const form=document.querySelector('form[action="/new-post"],form[enctype="multipart/form-data"]');
 if(!form || !form.querySelector('[name="post_type"]'))return;
 const key='karnafim-post-draft-v1';
 const fields=['post_type','title','body','year','event_date','event_place'];
 const status=document.getElementById('draft-note');
 function data(){const d={};fields.forEach(n=>{const f=form.elements.namedItem(n);if(f)d[n]=f.value});return d}
 function save(){
   try{sessionStorage.setItem(key,JSON.stringify(data()));if(status)status.textContent='✓ טיוטת הטקסט נשמרה בלשונית זו בלבד. יש לבחור מחדש קבצים לאחר טעינת העמוד.'}catch(_){}
 }
 try{
   const old=JSON.parse(sessionStorage.getItem(key)||'null');
   if(old && typeof old==='object'){
     let count=0;fields.forEach(n=>{const f=form.elements.namedItem(n);if(f && !f.value && typeof old[n]==='string' && old[n].length<5000){f.value=old[n];count++}});
     if(count && status)status.textContent='שוחזרה טיוטת טקסט מהלשונית הזו. אם נבחרו קבצים, יש לצרף אותם מחדש.';
   }
 }catch(_){}
 form.addEventListener('input',save);
 form.addEventListener('change',save);
 window.addEventListener('pagehide',save);
})();
</script>"""

    @app.route("/new-post",methods=["GET","POST"])
    def new_post():
        u=me()
        if not u:
            return redirect("/login?next=/new-post",code=303)
        if not u["approved"]:
            return page("ממתינים לאישור חברות",'<div class="note" role="status"><h1>החשבון ממתין לאישור</h1><p>מנהל קהילת הקרנפים צריך לאשר את החברות לפני פרסום תמונות, אירועים וסיפורים.</p><a href="/archive">אפשר לצפות בינתיים בארכיון</a></div>'),403
        if request.method=="POST":
            guard()
            if request.form.get("rights")!="on":abort(400)
            if request.form.get("ai_consent")!="on":abort(400,"נדרש אישור לעיבוד על ידי שירות AI חיצוני, או הימנעות משליחת הפרסום.")
            post_type=request.form.get("post_type","story")
            if post_type not in ("story","event","photo"):abort(400)
            title=request.form.get("title","").strip()[:130]
            body=request.form.get("body","").strip()[:4000]
            y=request.form.get("year","").strip()
            when=request.form.get("event_date","").strip()
            place=request.form.get("event_place","").strip()[:120]
            if y and (not y.isdigit() or not 1960<=int(y)<=2100):abort(400)
            if post_type!="event":when="";place=""
            event_date=None
            if when:
                try:
                    event_date=date.fromisoformat(when)
                    if not 1960<=event_date.year<=2100:abort(400)
                except ValueError:abort(400)
            files=[f for f in request.files.getlist("attachments") if f and f.filename]
            if not files:
                single=request.files.get("attachment")
                if single and single.filename:files=[single]
            if len(files)>4:abort(400,"עד ארבעה קבצים בכל פרסום")
            if not title or (len(body)<5 and not files):abort(400,"נדרשים כותרת, וסיפור קצר או תמונה")
            infos=[inspect_file(f) for f in files]
            # Moderation runs BEFORE the transaction that creates a post. Failure is private.
            verdict=moderate({"post_type":post_type,"title":title,"body":body,
                              "year":y,"date":when,"place":place},infos)
            if verdict.status=="rejected":
                return page("הפרסום לא התקבל",'<div class="note" role="alert"><h1>הפרסום לא עבר בדיקת בטיחות</h1><p>'+e(verdict.reason)+'</p><a href="/new-post">עריכת הפרסום וניסיון נוסף</a></div>'),422
            total_size=sum(info["size"] for info in infos)
            if total_size>12*1024*1024:abort(413,"הקבצים חורגים ממכסת הפרסום")
            # One database transaction: the story and all its media appear together or not at all.
            with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM members WHERE id=%s FOR UPDATE",(u["id"],))
                    cur.execute("SELECT COALESCE(SUM(length),0) FROM community_media WHERE owner_id=%s",(u["id"],))
                    mine=cur.fetchone()[0]
                    cur.execute("SELECT COALESCE(SUM(length),0) FROM community_media")
                    site=cur.fetchone()[0]
                    if mine+total_size>25*1024*1024 or site+total_size>150*1024*1024:abort(413,"אין מספיק מקום אחסון לפרסום")
                    cur.execute("INSERT INTO community_posts(author_id,title,body,story_year,post_type,event_date,event_place,approved,ai_status,ai_reason,ai_model,ai_checked_at,ai_attempts,ai_consent) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s THEN NOW() ELSE NULL END,%s,TRUE) RETURNING id",
                                (u["id"],title,body,int(y) if y else None,post_type,event_date,place,
                                 verdict.status=="approved",verdict.status,verdict.reason,verdict.model,
                                 verdict.attempted,1 if verdict.attempted else 0))
                    post_id=cur.fetchone()[0]
                    for info in infos:
                        cur.execute("INSERT INTO community_media(owner_id,post_id,recipient_id,mime,kind,filename,data,length) VALUES(%s,%s,NULL,%s,%s,%s,%s,%s)",
                                    (u["id"],post_id,info["mime"],info["kind"],info["filename"],info["data"],info["size"]))
            return redirect("/my-posts?auto=1" if verdict.status=="approved" else "/my-posts?submitted=1",code=303)
        b='<h1>📸 מפרסמים זיכרון מהפלוגה</h1><p>חבר מאושר יכול לשתף סיפור, אירוע או תמונות. הפרסום יהיה גלוי לחברים המאושרים רק לאחר בדיקת מנהל.</p>'
        b+='<form method="post" enctype="multipart/form-data" class="form-box">'+formwrap(
            '<label>סוג פרסום<select name="post_type" required><option value="story">סיפור מהשירות</option><option value="event">אירוע, מפגש או זיכרון מאירוע</option><option value="photo">אלבום תמונות</option></select></label>'
            '<label>כותרת הפרסום<input name="title" maxlength="130" required placeholder="למשל: צוות הטנק שלנו בבסיס"></label>'
            '<label>שנה (אופציונלי)<input name="year" type="number" min="1960" max="2100" placeholder="2005"></label>'
            '<label>תאריך האירוע (אופציונלי)<input name="event_date" type="date"></label>'
            '<label>מקום כללי לאירוע (אופציונלי)<input name="event_place" maxlength="120" placeholder="למשל: מפגש מחזור — רחובות"></label>'
            '<label>הסיפור או פרטי האירוע<textarea name="body" maxlength="4000" placeholder="מי היה, מה קרה, ומה אתם זוכרים? אפשר לשתף תמונות עם כותרת בלבד."></textarea></label>'
            +upload_form(True)
            +'<label><input type="checkbox" name="rights" style="width:auto;display:inline" required> אני מאשר שיש לי זכויות והרשאה לשתף את החומרים, ושלא כללתי פרטים אישיים של אחרים ללא הסכמתם.</label>'
            +'<label><input type="checkbox" name="ai_consent" style="width:auto;display:inline" required> אני מסכים להעברת התוכן והקבצים לשירות Google Gemini לצורך ביקורת AI אוטומטית, ככל שהשירות מחובר. בשכבת השימוש החינמית Google עשויה להשתמש בתוכן לשיפור שירותיה. תוכן שלא עובר בדיקה יישמר פרטי ולא יפורסם אוטומטית.</label>'
            +'<p class="muted">בדיקה חכמה: '+("מחוברת — תוכן בסיכון נמוך עשוי להתפרסם מיד" if configured() else "טרם חובר מנוע AI; כל פרסום יישאר פרטי עד לבדיקה")+'</p>'
            +'<p id="draft-note" class="muted" role="status" aria-live="polite">טקסט הטיוטה נשמר בלשונית זו כדי לצמצם אובדן מידע במקרה שהשרת מתעורר מחדש. קבצים לא נשמרים בטיוטה.</p>'
            +'<button type="submit">שליחת הפרסום לביקורת אוטומטית</button></form>')
        return page("הוספת סיפור, תמונות או אירוע",b+UPLOAD_JS+RECORD_JS+DRAFT_JS)

    def retry_ai_queue():
        """Best-effort single-item retry for earlier provider outages.
        Only consented submissions from currently approved accounts are eligible.
        Never publish on provider errors or uncertain results.
        """
        if not configured():return
        pending=sql("""SELECT p.id,p.author_id,p.title,p.body,p.post_type,p.story_year,
                         p.event_date,p.event_place
                         FROM community_posts p JOIN members m ON p.author_id=m.id
                         WHERE p.ai_status='pending_ai' AND p.ai_consent=TRUE
                         AND m.approved=TRUE AND p.approved=FALSE AND p.ai_attempts<5
                         AND (p.ai_checked_at IS NULL OR p.ai_checked_at<NOW()-INTERVAL '10 minutes')
                         ORDER BY p.created_at LIMIT 1""",fetch=True)
        if not pending:return
        p=pending[0]
        media=sql("SELECT mime,kind,data FROM community_media WHERE post_id=%s ORDER BY id",(p["id"],),True)
        files=[{"mime":m["mime"],"kind":m["kind"],"data":bytes(m["data"])} for m in media]
        verdict=moderate({"post_type":p["post_type"],"title":p["title"],"body":p["body"],
                          "year":p["story_year"],"date":p["event_date"],"place":p["event_place"]},files)
        status="held" if verdict.status=="rejected" else verdict.status
        allowed=status=="approved"
        sql("""UPDATE community_posts
                 SET approved=%s, ai_status=%s,ai_reason=%s,ai_model=%s,
                     ai_checked_at=NOW(),ai_attempts=ai_attempts+1
                 WHERE id=%s AND approved=FALSE AND ai_status='pending_ai' AND ai_consent=TRUE""",
            (allowed,status,verdict.reason,verdict.model,p["id"]))

    @app.route("/my-posts")
    def my_posts():
        u=approved()
        retry_ai_queue()
        rows=sql("SELECT id,title,body,post_type,story_year,event_date,event_place,approved,ai_status,ai_reason,created_at FROM community_posts WHERE author_id=%s ORDER BY created_at DESC LIMIT 100",(u["id"],),True)
        b='<h1>📝 הפרסומים שלי</h1><p>תמונות, אירועים וסיפורים ששלחת. עד שהמנהל מאשר אותם, רק אתה והמנהל יכולים לראות את התוכן.</p>'
        if request.args.get("submitted") in ("1",) or request.args.get("auto")=="1":
            b+='<script>try{sessionStorage.removeItem("karnafim-post-draft-v1")}catch(_){}</script>'
        if request.args.get("submitted")=="1":b+='<div class="note" role="status">✓ הפרסום נשמר במצב פרטי. ביקורת ה־AI לא אישרה פרסום אוטומטי.</div>'
        if request.args.get("auto")=="1":b+='<div class="note" role="status">✓ הפרסום אושר בביקורת אוטומטית והופיע בציר הזמן של החברים.</div>'
        b+='<div class="actions"><a class="cta" href="/new-post">➕ פרסום חדש</a><a class="cta" href="/feed">לציר הזמן</a></div>'
        if not rows:b+='<div class="note">אין לך עדיין פרסומים. אפשר להעלות עכשיו תמונה, סיפור או אירוע מהשירות.</div>'
        labels={"story":"סיפור","event":"אירוע","photo":"אלבום תמונות"}
        for p in rows:
            state="פורסם לחברי הקהילה" if p["approved"] else ("ממתין לחיבור או לחידוש בדיקת AI" if p["ai_status"]=="pending_ai" else "נשאר פרטי — בדיקה לא חד־משמעית")
            b+='<article class="event"><span class="tag">'+e(labels.get(p["post_type"],"סיפור"))+'</span> <span class="tag">'+e(state)+'</span><h2>'+e(p["title"])+'</h2>'
            if p["event_date"]:b+='<p>📅 '+e(p["event_date"])+'</p>'
            if p["event_place"]:b+='<p>📍 '+e(p["event_place"])+'</p>'
            if not p["approved"]:b+='<p class="muted">🛡️ '+e(p["ai_reason"])+'</p>'
            b+='<p>'+e(p["body"]).replace("\n","<br>")+'</p>'
            attachments=sql("SELECT id,kind FROM community_media WHERE post_id=%s ORDER BY id",(p["id"],),True)
            b+=''.join(media_html(a["id"],a["kind"]) for a in attachments)
            comments=sql("SELECT c.body,m.name FROM community_comments c JOIN members m ON m.id=c.author_id WHERE c.post_id=%s AND c.approved=TRUE ORDER BY c.created_at DESC LIMIT 40",(p["id"],),True)
            b+='<div id="post-'+str(p["id"])+'"><h3>תגובות החברים</h3>'
            for comment_row in reversed(comments):
                b+='<div class="note"><strong>'+e(comment_row["name"])+'</strong><p>'+e(comment_row["body"])+'</p></div>'
            b+='<form method="post" action="/post/'+str(p["id"])+'/comment" class="form-box">'+formwrap(
                '<label>הוספת תגובה<textarea name="body" required minlength="3" maxlength="1200" placeholder="איזה זיכרון טוב..."></textarea></label>'
                '<label><input style="width:auto;display:inline" type="checkbox" name="ai_consent" required> אני מסכים לבדיקת התגובה באמצעות שירות AI חיצוני; במסלול החינמי ספק השירות עשוי להשתמש בתוכן לשיפור מוצריו.</label>'
                '<button>בדיקה ופרסום תגובה</button>')+'</form></div></article>'
        return page("הפרסומים שלי",b)

    @app.route("/photos")
    def photos():
        u=me()
        b='<h1>📷 תמונות וגלריות</h1><p>כאן נאספות תמונות מהשירות לצד תיעוד היסטורי בעל רישיון שימוש. התצלומים הכלליים שלהלן אינם מוצגים כתמונות של פלוגה ב׳ או של חבריה.</p>'
        b+='<div class="media-grid"><figure class="tile"><a href="https://commons.wikimedia.org/wiki/File:Merkava_tanks_in_northern_Israel.jpg" target="_blank" rel="noopener noreferrer"><img loading="lazy" src="https://upload.wikimedia.org/wikipedia/commons/f/fe/Merkava_tanks_in_northern_Israel.jpg" alt="טנקי מרכבה בצפון הארץ באוגוסט 2006 — לא מזוהים כטנקי פלוגה ב׳"></a><figcaption><strong>טנקי מרכבה בצפון הארץ, 18 באוגוסט 2006</strong><p>צילום: ליאור גולגר · <a target="_blank" rel="noopener noreferrer" href="https://creativecommons.org/licenses/by-sa/2.0/">CC BY-SA 2.0</a>. לא תצלום מאומת של הפלוגה.</p></figcaption></figure>'
        b+='<figure class="tile"><a href="https://commons.wikimedia.org/wiki/File:Merkava-4-tank-6611a-white1.jpg" target="_blank" rel="noopener noreferrer"><img loading="lazy" src="https://upload.wikimedia.org/wikipedia/commons/thumb/6/69/Merkava-4-tank-6611a-white1.jpg/1280px-Merkava-4-tank-6611a-white1.jpg" alt="טנק מרכבה סימן 4 ביד לשריון, צילום משנת 2015"></a><figcaption><strong>מרכבה סימן 4, יד לשריון, 2015</strong><p>צילום: צחי אבנור / MathKnight · <a target="_blank" rel="noopener noreferrer" href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>. צילום המחשה בלבד.</p></figcaption></figure></div>'
        if u and u["approved"]:
            rows=sql("SELECT m.id FROM community_media m JOIN community_posts p ON p.id=m.post_id WHERE p.approved=TRUE AND m.kind='image' ORDER BY m.created_at DESC LIMIT 30",fetch=True)
            b+='<h2>תמונות שהחברים אישרו לשיתוף בקהילה</h2>'
            if rows:
                b+='<div class="media-grid">'+''.join('<figure class="tile"><a href="/community-media/'+str(r["id"])+'" target="_blank" rel="noopener"><img loading="lazy" src="/community-media/'+str(r["id"])+'" alt="תמונה מהקהילה שאושרה לפרסום"></a></figure>' for r in rows)+'</div>'
            else:b+='<div class="note">הגלריה הקהילתית עדיין ממתינה לתמונות המקוריות הראשונות.</div>'
            b+='<div class="actions"><a class="cta" href="/new-post">➕ שיתוף תמונה מהפלוגה</a><a class="cta" href="/feed">לכל הסיפורים</a></div>'
        else:b+='<div class="note">הגלריה האישית של חברי הפלוגה מיועדת לחברים מאושרים בלבד. <a href="/register">בקשת הצטרפות</a> · <a href="/login">כניסה לחשבון</a></div>'
        b+='<p class="muted">לא בוצע זיהוי פנים אוטומטי ואין כאן טענה שהמצולמים שירתו ביחידה. תצלומי קהילה יוצגו רק לאחר אישור ובדיקת זכויות.</p>'
        return page("גלריית תמונות",b)

    @app.route("/post/<int:post_id>/comment",methods=["POST"])
    def comment(post_id):
        u=approved()
        guard()
        visible=sql("SELECT id,title FROM community_posts WHERE id=%s AND approved=TRUE",(post_id,),True)
        if not visible:abort(404)
        if request.form.get("ai_consent")!="on":abort(400)
        message=request.form.get("body","").strip()[:1200]
        if len(message)<3:abort(400)
        verdict=moderate({"post_type":"comment","title":"תגובה לפרסום קיים",
                          "body":message,"year":"","date":"","place":""},[])
        if verdict.status=="rejected":
            return page("התגובה לא נשלחה",'<div class="note" role="alert">'+e(verdict.reason)+'</div><a href="/feed">חזרה לפרסומים</a>'),422
        sql("""INSERT INTO community_comments(post_id,author_id,body,approved,ai_consent,ai_status,
                 ai_reason,ai_model,ai_checked_at,ai_attempts)
                 VALUES(%s,%s,%s,%s,TRUE,%s,%s,%s,
                 CASE WHEN %s THEN NOW() ELSE NULL END,%s)""",
            (post_id,u["id"],message,verdict.status=="approved",verdict.status,
             verdict.reason,verdict.model,verdict.attempted,1 if verdict.attempted else 0))
        return redirect("/feed?comment="+("approved" if verdict.status=="approved" else "pending")+"#post-"+str(post_id),code=303)

    @app.route("/feed")
    def feed():
        u=me()
        if u and u["approved"]:retry_ai_queue()
        if not u or not u["approved"]:return page("זיכרונות",'<h1>זיכרונות הפלוגה</h1><div class="note">הסיפורים והתמונות שחברים מעלים זמינים רק לחברים מאושרים. '+link("/register","הצטרפו לקהילה")+'</div>'+sources(4))
        rows=sql("SELECT p.id,p.title,p.body,p.story_year,p.post_type,p.event_date,p.event_place,p.created_at,m.name FROM community_posts p JOIN members m ON m.id=p.author_id WHERE p.approved=TRUE ORDER BY p.created_at DESC LIMIT 60",fetch=True)
        b='<h1>📸 סיפורים, תמונות ואירועים</h1><p>זיכרונות, אלבומים ומפגשי הפלוגה — תכנים שחברי הקהילה בחרו לשתף ואושרו לפרסום.</p><div class="actions"><a class="cta" href="/new-post">➕ מוסיפים סיפור, תמונות או אירוע</a><a class="cta" href="/my-posts">📝 הפרסומים שלי</a></div>'
        if request.args.get("comment")=="approved":b+='<div class="note">התגובה עברה ביקורת אוטומטית ופורסמה.</div>'
        elif request.args.get("comment")=="pending":b+='<div class="note">התגובה נקלטה אך נשארה פרטית עד להשלמת הבדיקה האוטומטית.</div>'
        if not rows:b+='<div class="note">עדיין לא פורסמו סיפורי חברים מאושרים. אפשר להיות הראשונים ולשתף זיכרון או תמונה.</div>'
        for p in rows:
            kind={"story":"סיפור","event":"אירוע","photo":"אלבום תמונות"}.get(p["post_type"],"סיפור")
            b+='<article class="event"><span class="tag">'+e(kind)+'</span> <span class="tag">'+e(p["story_year"] or "מהפלוגה")+'</span><h2>'+e(p["title"])+'</h2>'
            if p["event_date"]:b+='<p>📅 '+e(p["event_date"])+'</p>'
            if p["event_place"]:b+='<p>📍 '+e(p["event_place"])+'</p>'
            b+='<p>'+e(p["body"]).replace("\n","<br>")+'</p><div class="byline">שותף על ידי '+e(p["name"])+'</div>'
            attachments=sql("SELECT id,kind FROM community_media WHERE post_id=%s ORDER BY id",(p["id"],),True)
            b+=''.join(media_html(a["id"],a["kind"]) for a in attachments)+'</article>'
        return page("ציר הזמן",b)

    @app.route("/chats")
    def chats():
        u=approved()
        incoming=sql("SELECT r.sender_id,m.name,r.note FROM requests r JOIN members m ON m.id=r.sender_id WHERE r.recipient_id=%s AND NOT r.accepted ORDER BY r.created_at DESC",(u["id"],),True)
        connected=sql("SELECT DISTINCT m.id,m.name FROM members m JOIN requests r ON r.accepted AND ((r.sender_id=%s AND r.recipient_id=m.id) OR (r.recipient_id=%s AND r.sender_id=m.id)) WHERE m.approved ORDER BY m.name",(u["id"],u["id"]),True)
        pending=sql("SELECT m.name FROM requests r JOIN members m ON m.id=r.recipient_id WHERE r.sender_id=%s AND NOT r.accepted",(u["id"],),True)
        b='<h1>💬 הודעות לחברים</h1><p>כמו מסנג׳ר: הודעות, תמונות, קול וסרטונים. השיחה נפתחת רק אחרי שחבר מאשר את בקשת הקשר.</p>'
        if incoming:
            b+='<h2>בקשות קשר חדשות</h2>'
            for r in incoming:
                b+='<article class="tile"><h3>'+e(r["name"])+'</h3><p>'+e(r["note"])+'</p><form method="post" action="/chats/accept">'+formwrap('<input type="hidden" name="uid" value="'+str(r["sender_id"])+'"><button name="action" value="accept">אישור שיחה</button><button name="action" value="decline">דחייה</button>')+'</form></article>'
        b+='<h2>החברים שאיתם אפשר לדבר</h2>'
        if connected:b+='<div class="tiles">'+''.join('<div class="tile"><h3>👤 '+e(r["name"])+'</h3>'+link("/chat/"+str(r["id"]),"פתיחת שיחה ←")+'</div>' for r in connected)+'</div>'
        else:b+='<div class="note">אין עדיין שיחות פעילות. אפשר למצוא חבר במדריך ולשלוח לו בקשת קשר.</div>'
        if pending:b+='<p class="muted">בקשות שנשלחו וממתינות לאישור: '+", ".join(e(x["name"]) for x in pending)+'</p>'
        b+=link("/directory","🔎 לחיפוש חברים במדריך")
        return page("ההודעות שלי",b)

    @app.route("/chats/accept",methods=["POST"])
    def accept_chat():
        u=approved();guard()
        uid=request.form.get("uid","")
        if not uid.isdigit():abort(400)
        if request.form.get("action")=="accept":
            sql("UPDATE requests SET accepted=TRUE WHERE sender_id=%s AND recipient_id=%s",(int(uid),u["id"]))
        elif request.form.get("action")=="decline":
            sql("DELETE FROM requests WHERE sender_id=%s AND recipient_id=%s AND accepted=FALSE",(int(uid),u["id"]))
        else:abort(400)
        return redirect("/chats")

    @app.route("/chat/<int:other_id>",methods=["GET","POST"])
    def chat(other_id):
        u=approved()
        if not is_connected(u["id"],other_id):abort(403)
        other=sql("SELECT name FROM members WHERE id=%s AND approved",(other_id,),True)
        if not other:abort(404)
        if request.method=="POST":
            guard()
            body=request.form.get("body","").strip()[:2000]
            f=request.files.get("attachment")
            if not body and not (f and f.filename):abort(400)
            if f and f.filename:inspect_file(f)
            mid=store_attachment(u,f,recipient_id=other_id) if f and f.filename else None
            sql("INSERT INTO messages(sender_id,recipient_id,body,media_id) VALUES(%s,%s,%s,%s)",(u["id"],other_id,body,mid))
            return redirect("/chat/"+str(other_id))
        msgs=sql("SELECT x.id,x.sender_id,x.body,x.created_at,md.id media_id,md.kind FROM messages x LEFT JOIN community_media md ON md.id=x.media_id WHERE (x.sender_id=%s AND x.recipient_id=%s) OR (x.sender_id=%s AND x.recipient_id=%s) ORDER BY x.created_at DESC LIMIT 100",(u["id"],other_id,other_id,u["id"]),True)
        last_id=msgs[0]["id"] if msgs else 0
        after=request.args.get("after","0")
        if not after.isdigit():after="0"
        def message_fragment(m):
            h='<div data-message-id="'+str(m["id"])+'" class="bubble '+("mine" if m["sender_id"]==u["id"] else "")+'">'
            if m["body"]:h+='<p>'+e(m["body"]).replace("\n","<br>")+'</p>'
            if m["media_id"]:h+=media_html(m["media_id"],m["kind"],True)
            h+='<small>'+("אתה" if m["sender_id"]==u["id"] else e(other[0]["name"]))+' · '+e(str(m["created_at"])[:16])+'</small></div>'
            return h
        if request.args.get("partial")=="1":
            markup=''.join(message_fragment(m) for m in reversed(msgs) if m["id"]>int(after))
            response=Response(markup,mimetype="text/html")
            response.headers["Cache-Control"]="no-store"
            return response
        b='<h1>שיחה עם '+e(other[0]["name"])+'</h1><p><a href="/chats">חזרה לשיחות</a></p><div id="messages" role="log" aria-label="הודעות השיחה" aria-live="polite" aria-relevant="additions">'
        if not msgs:b+='<div class="note" id="no-messages">עוד לא נשלחו הודעות בשיחה הזאת. אפשר לכתוב שלום או להקליט הודעה קצרה.</div>'
        for m in reversed(msgs):b+=message_fragment(m)
        b+='</div><form method="post" enctype="multipart/form-data" class="form-box">'+formwrap('<label>הודעה<textarea name="body" maxlength="2000" placeholder="כתוב הודעה לחבר…"></textarea></label>'+upload_form(False)+'<button>שליחת הודעה</button></form>')
        js="""<script>
(()=>{let last="""+str(last_id)+""";
const panel=document.getElementById('messages');
async function check(){
 if(document.hidden)return;
 try{
  const res=await fetch(location.pathname+'?partial=1&after='+last,{cache:'no-store'});
  if(!res.ok)return;
  const h=await res.text();
  if(!h.trim())return;
  const holder=document.createElement('div');
  holder.innerHTML=h;
  const newItems=holder.querySelectorAll('[data-message-id]');
  if(!newItems.length)return;
  const empty=document.getElementById('no-messages');
  if(empty)empty.remove();
  newItems.forEach(el=>{last=Math.max(last,Number(el.dataset.messageId));panel.appendChild(el)});
 }catch(_){}
}
setInterval(check,12000);
})();</script>"""
        return page("שיחה פרטית",b+RECORD_JS+js)

    @app.route("/community/moderation",methods=["GET","POST"])
    def moderation():
        u=approved()
        if not admin(u):abort(403)
        if request.method=="POST":
            guard()
            pid=request.form.get("id","")
            if not pid.isdigit():abort(400)
            op=request.form.get("op")
            if op=="publish":sql("UPDATE community_posts SET approved=TRUE WHERE id=%s",(int(pid),))
            elif op=="reject":sql("DELETE FROM community_posts WHERE id=%s AND approved=FALSE",(int(pid),))
            else:abort(400)
            return redirect("/community/moderation")
        pending=sql("SELECT p.*,m.name FROM community_posts p JOIN members m ON p.author_id=m.id WHERE NOT p.approved ORDER BY p.created_at DESC LIMIT 100",fetch=True)
        b='<h1>אישור סיפורים, אירועים ותמונות</h1><p>בדוק זכויות שימוש, פרטיות, דיוק היסטורי והסכמת המצולמים לפני פרסום. גם אירועים עתידיים נבדקים לפני הופעתם בקהילה.</p>'
        if not pending:b+='<div class="note">אין כרגע פרסומים הממתינים לאישור.</div>'
        for p in pending:
            b+='<article class="event"><span class="tag">'+e({"story":"סיפור","photo":"אלבום","event":"אירוע"}.get(p["post_type"],"סיפור"))+'</span><h3>'+e(p["title"])+'</h3>'
            if p["event_date"]:b+='<p>📅 '+e(p["event_date"])+'</p>'
            if p["event_place"]:b+='<p>📍 '+e(p["event_place"])+'</p>'
            b+='<p>'+e(p["body"])+'</p><small>מאת '+e(p["name"])+'</small>'
            for m in sql("SELECT id,kind FROM community_media WHERE post_id=%s",(p["id"],),True):
                b+=media_html(m["id"],m["kind"])
            b+='<form method="post">'+formwrap('<input type="hidden" name="id" value="'+str(p["id"])+'"><button name="op" value="publish">אישור לפרסום</button><button name="op" value="reject">מחיקת הפרסום</button>')+'</form></article>'
        return page("אישור תכנים",b)

    app.extensions["karnafim_portal"]={"home":home,"page":page}
