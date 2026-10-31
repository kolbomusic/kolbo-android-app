"""Memorial image discovery and moderated photo attribution.
No face-recognition, no Google scraping, and no unapproved public photo.
"""
import html, io, hashlib, ipaddress
from urllib.parse import quote, urlsplit
from flask import request, redirect, abort, Response, send_file
from PIL import Image, ImageOps, UnidentifiedImageError

PEOPLE = (
 {"slug":"yehonatan-sharabi","name":"יהונתן (יוני) שרעבי","date":"03.08.2006","unit":"פלוגה ב׳ הקרנפים, גדוד 46","role":"לוחם שריון","official":"https://www.izkor.gov.il/יהונתן%20שרעבי/en_53e66dd727188835acbe02a1f641a882","query":"יהונתן יוני שרעבי ז״ל גדוד 46 תמונה"},
 {"slug":"benaya-rein","name":"בניה ריין","date":"12.08.2006","unit":"כוח בניה, גדוד 46","role":"מפקד הכוח","official":"https://www.izkor.gov.il/בניה%20ריין/en_f5ccba845584f96f9b9334cf335d2e78","query":"בניה ריין ז״ל תמונות"},
 {"slug":"uri-grossman","name":"אורי גרוסמן","date":"12.08.2006","unit":"כוח בניה, גדוד 46","role":"תותחן","official":"https://www.izkor.gov.il/אורי%20גרוסמן/en_f53b79619b3f27184812b11f14e635a8","query":"אורי גרוסמן ז״ל חייל תמונה"},
 {"slug":"adam-goren","name":"אדם גורן","date":"12.08.2006","unit":"כוח בניה, גדוד 46","role":"טען־קשר","official":"https://www.izkor.gov.il/אדם%20גורן/en_e6446f8f52c2b18e0ec560602482bdda","query":"אדם גורן ז״ל שריון תמונה"},
 {"slug":"alexander-bunimovich","name":"אלכסנדר (סשה) בונימוביץ׳","date":"12.08.2006","unit":"כוח בניה, גדוד 46","role":"נהג הטנק","official":"https://www.izkor.gov.il/אלכסנדר%20בונימוביץ/en_34b2955a02b6a81f8ba932dbf6228e61","query":"אלכסנדר סשה בונימוביץ ז״ל תמונה"},
)

def setup(app, sql, page, me, admin, guard, formwrap):
    sql("""CREATE TABLE IF NOT EXISTS memorial_photos (
      id BIGSERIAL PRIMARY KEY,
      person_slug TEXT NOT NULL,
      submitted_by BIGINT NOT NULL REFERENCES members(id) ON DELETE CASCADE,
      image BYTEA NOT NULL,
      image_sha256 TEXT NOT NULL,
      caption TEXT NOT NULL DEFAULT '',
      credit TEXT NOT NULL DEFAULT '',
      source_url TEXT NOT NULL DEFAULT '',
      rights_basis TEXT NOT NULL,
      rights_detail TEXT NOT NULL DEFAULT '',
      approved BOOLEAN NOT NULL DEFAULT FALSE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      reviewed_at TIMESTAMPTZ,
      UNIQUE(person_slug,image_sha256)
    )""")
    sql("""CREATE TABLE IF NOT EXISTS memorial_photo_leads (
      id BIGSERIAL PRIMARY KEY,
      person_slug TEXT NOT NULL,
      submitted_by BIGINT NOT NULL REFERENCES members(id) ON DELETE CASCADE,
      source_url TEXT NOT NULL,
      note TEXT NOT NULL DEFAULT '',
      approved BOOLEAN NOT NULL DEFAULT FALSE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE(person_slug,source_url)
    )""")
    def e(v):
        return html.escape(str(v if v is not None else ''),quote=True)

    def pick(slug):
        p=next((v for v in PEOPLE if v["slug"]==slug),None)
        if p is None:abort(404)
        return p

    def approved_member():
        u=me()
        if u is None:return None
        return u if u["approved"] else None

    def safe_public_url(value):
        value=(value or "").strip()[:750]
        if not value:return ""
        try:
            u=urlsplit(value)
            if u.scheme!="https" or not u.hostname or u.username or u.password: return ""
            host=u.hostname.lower().rstrip(".")
            if host=="localhost" or host.endswith((".local",".internal",".localhost")):return ""
            try:
                addr=ipaddress.ip_address(host)
                if not addr.is_global:return ""
            except ValueError:pass
            return value if "." in host else ""
        except ValueError:return ""

    def google_images(p):
        return "https://www.google.com/search?tbm=isch&q="+quote(p["query"])
    def google_izkor(p):
        return "https://www.google.com/search?tbm=isch&q="+quote("site:izkor.gov.il "+p["name"])

    @app.route("/memorials")
    def memorials():
        counts=sql("SELECT person_slug,COUNT(*) AS n FROM memorial_photos WHERE approved=TRUE GROUP BY person_slug",fetch=True)
        counts={r["person_slug"]:r["n"] for r in counts}
        body='<h1>🕯️ זוכרים את חברינו</h1><p>דפי הנצחה של לוחמים מתקופת מלחמת לבנון השנייה. אפשר לחפש תמונות היסטוריות ולהציע להוסיף אותן, אך כל תמונה תפורסם רק לאחר אימות זהות ואישור זכויות שימוש.</p>'
        body+='<div class="grid">'
        for p in PEOPLE:
            body+='<article class="tile"><span class="tag">'+e(p["date"])+'</span><h2>'+e(p["name"])+'</h2><p>'+e(p["unit"])+' · '+e(p["role"])+'</p><p class="muted">'+e(counts.get(p["slug"],0))+' תמונות מאושרות בגלריה</p><a class="cta" href="/memorial/'+e(p["slug"])+'">לסיפורו ולתמונות ←</a></article>'
        body+='</div><div class="note">החיפוש בגוגל פותח תוצאות חיצוניות. איננו משייכים פנים או זהויות לפי זיהוי ביומטרי אוטומטי, ולא מעתיקים תמונות מאתרים אחרים ללא רשות.</div>'
        return page("הנצחת החברים",body)

    @app.route("/memorial/<slug>")
    def memorial_person(slug):
        p=pick(slug)
        user=approved_member()
        rows=sql("SELECT id,caption,credit,source_url FROM memorial_photos WHERE person_slug=%s AND approved=TRUE ORDER BY reviewed_at DESC,id DESC LIMIT 50",(slug,),True)
        leads=sql("SELECT source_url,note FROM memorial_photo_leads WHERE person_slug=%s AND approved=TRUE ORDER BY created_at DESC LIMIT 20",(slug,),True)
        body='<nav class="muted"><a href="/memorials">כל דפי ההנצחה</a> / '+e(p["name"])+'</nav><h1>לזכר '+e(p["name"])+'</h1><p><strong>'+e(p["unit"])+'</strong> · '+e(p["role"])+' · נפל ביום '+e(p["date"])+'</p>'
        body+='<section class="note"><strong>איסוף תמונות מהתקופה</strong><p>בחרו תמונה מוכרת, בדקו את זהות האדם במקור ההנצחה ואת הזכות להשתמש בתמונה, והציעו אותה לגלריה שלו. שיוך לגלריה אינו אוטומטי ללא בדיקה.</p></section>'
        body+='<div class="actions"><a class="cta" href="'+e(google_images(p))+'" target="_blank" rel="noopener noreferrer">🔎 חיפוש תמונות בגוגל ↗</a>'
        body+='<a class="cta" href="'+e(google_izkor(p))+'" target="_blank" rel="noopener noreferrer">🖼️ תמונות מאתר יזכור בגוגל ↗</a>'
        body+='<a class="cta" href="'+e(p["official"])+'" target="_blank" rel="noopener noreferrer">🕯️ דף ההנצחה הרשמי ↗</a>'
        if user:body+='<a class="cta" href="/memorial/'+e(slug)+'/suggest">➕ מציעים תמונה / קישור</a>'
        body+='</div><h2>גלריית התמונות המאושרות</h2>'
        if not rows:body+='<div class="tile"><p>אין עדיין תמונות שהועלו ושזכויות השימוש בהן נבדקו. המקורות והחיפוש זמינים דרך הקישורים שמעל.</p></div>'
        else:
            body+='<div class="media-grid">'
            for r in rows:
                body+='<figure class="tile"><img src="/memorial-photo/'+str(r["id"])+'" loading="lazy" alt="תמונה מאושרת הקשורה להנצחת '+e(p["name"])+'" style="width:100%;height:210px;object-fit:contain;border-radius:10px"><figcaption><strong>'+e(r["caption"] or p["name"])+'</strong><p class="muted">קרדיט: '+e(r["credit"])+'</p>'
                if r["source_url"]:body+='<a href="'+e(r["source_url"])+'" target="_blank" rel="noopener noreferrer nofollow">עמוד המקור ↗</a>'
                body+='</figcaption></figure>'
            body+='</div>'
        if leads:
            body+='<h2>מקורות תמונות שנשלחו ונבדקו</h2><div class="grid">'
            for x in leads:
                body+='<div class="tile"><p>'+e(x["note"])+'</p><a href="'+e(x["source_url"])+'" target="_blank" rel="noopener noreferrer nofollow">למקור החיצוני ↗</a></div>'
            body+='</div>'
        if not user:body+='<p class="muted">להצעת תמונה דרושה כניסה לחשבון חבר מאושר.</p>'
        return page("הנצחת "+p["name"],body)

    @app.route("/memorial/<slug>/suggest",methods=["GET","POST"])
    def memorial_suggest(slug):
        p=pick(slug)
        user=approved_member()
        if not user:return redirect("/login")
        if request.method=="POST":
            guard()
            if request.form.get("ack")!="on":abort(400)
            source_url=safe_public_url(request.form.get("source_url",""))
            caption=request.form.get("caption","").strip()[:200]
            credit=request.form.get("credit","").strip()[:160]
            detail=request.form.get("rights_detail","").strip()[:700]
            basis=request.form.get("rights_basis","")
            note=request.form.get("note","").strip()[:450]
            upload=request.files.get("photo")
            if upload and upload.filename:
                if basis not in ("own","permission","licensed") or len(credit)<2 or len(detail)<8:abort(400,"יש לפרט זכויות שימוש וקרדיט")
                if basis=="licensed" and not source_url:abort(400,"תמונה ברישיון מחייבת קישור מקור")
                original=upload.read(3*1024*1024+1)
                if len(original)>3*1024*1024:abort(413,"התמונה גדולה מ־3MB")
                try:
                    im=Image.open(io.BytesIO(original))
                    im.verify()
                    im=Image.open(io.BytesIO(original))
                    if im.format not in ("JPEG","PNG","WEBP"):abort(400,"תמונה לא נתמכת")
                    if im.width*im.height>12_000_000:abort(400,"תמונה גדולה מדי בפיקסלים")
                    im=ImageOps.exif_transpose(im).convert("RGB")
                    im.thumbnail((1400,1400))
                    buf=io.BytesIO()
                    im.save(buf,format="JPEG",quality=83,optimize=True)
                    payload=buf.getvalue()
                except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):abort(400,"קובץ תמונה לא תקין")
                digest=hashlib.sha256(payload).hexdigest()
                sql("INSERT INTO memorial_photos(person_slug,submitted_by,image,image_sha256,caption,credit,source_url,rights_basis,rights_detail) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(person_slug,image_sha256) DO NOTHING",(slug,user["id"],payload,digest,caption,credit,source_url,basis,detail))
            else:
                if not source_url:abort(400,"נדרש קישור לעמוד המקור")
                sql("INSERT INTO memorial_photo_leads(person_slug,submitted_by,source_url,note) VALUES(%s,%s,%s,%s) ON CONFLICT(person_slug,source_url) DO NOTHING",(slug,user["id"],source_url,note))
            return page("ההצעה התקבלה",'<div class="tile"><h1>תודה על הסיוע להנצחה</h1><p>ההצעה שויכה ל־'+e(p["name"])+' ותמתין לבדיקה ואישור מנהל הקהילה.</p><a href="/memorial/'+e(slug)+'">חזרה להנצחה</a></div>')
        b='<h1>תמונה לזכר '+e(p["name"])+'</h1><p>אפשר להציע קישור שמצאת בגוגל או להעלות תמונה שיש ברשותך אישור שימוש בה. ההצעות אינן מתפרסמות אוטומטית.</p>'
        b+='<form enctype="multipart/form-data" method="post" class="form-box">'+formwrap('<label>קישור לעמוד המקור (HTTPS)<input type="url" name="source_url" placeholder="https://..." maxlength="750"></label><label>הערה על המקור<textarea name="note" maxlength="450" placeholder="היכן צולמה התמונה? איך יודעים שזה האדם הנכון?"></textarea></label><label>תמונה (אופציונלי, עד 3MB)<input type="file" name="photo" accept="image/jpeg,image/png,image/webp"></label><label>כיתוב לתמונה<input type="text" name="caption" maxlength="200"></label><label>שם הצלם / בעל הזכויות<input type="text" name="credit" maxlength="160"></label><label>בסיס הרשאה לשימוש<select name="rights_basis"><option value="">בחרו אם מעלים קובץ</option><option value="own">אני בעל זכויות היוצרים</option><option value="permission">יש לי רשות מפורשת מבעל הזכויות</option><option value="licensed">התמונה ברישיון המאפשר שימוש</option></select></label><label>פרטי אישור / רישיון<textarea name="rights_detail" maxlength="700" placeholder="הסכמה שקיבלתם, שם רישיון ותנאי קרדיט"></textarea></label><label><input type="checkbox" name="ack" value="on" required style="width:auto;display:inline"> אני מאשר/ת שהמידע נכון ושלא אעלה תמונה ללא זכויות מתאימות</label><button>שליחה לבדיקה ולשיוך</button></form>')
        b+='<p class="muted">חיפוש בגוגל אינו מהווה רישיון שימוש. תמונות שעולות מתנקות ממידע EXIF, מוקטן גודלן ונבדקות ידנית לפני פרסום.</p>'
        return page("הצעת תמונה",b)

    @app.route("/memorial-photo/<int:photo_id>")
    def memorial_photo(photo_id):
        user=approved_member()
        if user and admin(user):
            r=sql("SELECT image,approved FROM memorial_photos WHERE id=%s",(photo_id,),True)
        else:
            r=sql("SELECT image,approved FROM memorial_photos WHERE id=%s AND approved=TRUE",(photo_id,),True)
        if not r:abort(404)
        return send_file(io.BytesIO(bytes(r[0]["image"])),mimetype="image/jpeg",download_name="memorial-photo.jpg",max_age=0,conditional=False)

    @app.route("/memorials/review",methods=["GET","POST"])
    def memorial_review():
        user=approved_member()
        if not user or not admin(user):abort(403)
        if request.method=="POST":
            guard()
            kind=request.form.get("kind","")
            op=request.form.get("op","")
            record_id=request.form.get("record_id","")
            if kind not in ("photo","lead") or op not in ("approve","reject") or not record_id.isdigit():abort(400)
            table="memorial_photos" if kind=="photo" else "memorial_photo_leads"
            if op=="approve":
                sql("UPDATE "+table+" SET approved=TRUE WHERE id=%s",(int(record_id),))
            else:
                sql("DELETE FROM "+table+" WHERE id=%s AND approved=FALSE",(int(record_id),))
            return redirect("/memorials/review")
        photos=sql("SELECT id,person_slug,caption,credit,source_url,rights_basis,rights_detail FROM memorial_photos WHERE approved=FALSE ORDER BY created_at LIMIT 50",fetch=True)
        leads=sql("SELECT id,person_slug,source_url,note FROM memorial_photo_leads WHERE approved=FALSE ORDER BY created_at LIMIT 50",fetch=True)
        b='<h1>בדיקת תמונות להנצחה</h1><p>אישור מחייב אימות האדם במקור, זכויות הצלם, כיתוב מתאים והתחשבות במשפחה. אין לאשר בגלל דמיון פנים בלבד.</p>'
        if not photos and not leads:b+='<div class="note">אין הצעות הממתינות לאישור.</div>'
        for p in photos:
            b+='<article class="event"><h3>תמונה: '+e(p["person_slug"])+'</h3><img style="max-width:240px;width:100%;border-radius:9px" src="/memorial-photo/'+str(p["id"])+'" alt="תמונה ממתינה לאישור"><p>'+e(p["caption"])+'</p><p>קרדיט: '+e(p["credit"])+' · הרשאה: '+e(p["rights_basis"])+' / '+e(p["rights_detail"])+'</p><p>מקור: '+e(p["source_url"])+'</p>'
            b+='<form method="post">'+formwrap('<input type="hidden" name="kind" value="photo"><input type="hidden" name="record_id" value="'+str(p["id"])+'"><button name="op" value="approve">אישור התמונה</button><button name="op" value="reject">דחייה</button>')+'</form></article>'
        for x in leads:
            b+='<article class="event"><h3>קישור: '+e(x["person_slug"])+'</h3><p>'+e(x["note"])+'</p><a target="_blank" rel="noopener noreferrer nofollow" href="'+e(x["source_url"])+'">למקור ↗</a>'
            b+='<form method="post">'+formwrap('<input type="hidden" name="kind" value="lead"><input type="hidden" name="record_id" value="'+str(x["id"])+'"><button name="op" value="approve">אישור קישור</button><button name="op" value="reject">דחייה</button>')+'</form></article>'
        return page("אישור תמונות",b)
