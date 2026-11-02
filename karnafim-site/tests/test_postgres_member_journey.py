"""Full member journey against an isolated PostgreSQL test database.

The CI DATABASE_URL MUST contain localhost and the database name karnafim_ci.
No real users, real secrets or external email providers are accessed.
"""
import io
import os
from pathlib import Path
import sys

import psycopg
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
DB=os.environ.get("DATABASE_URL","")
if "localhost" not in DB and "127.0.0.1" not in DB:
    raise RuntimeError("CI test MUST run against a local disposable PostgreSQL instance")
if "/karnafim_ci" not in DB:
    raise RuntimeError("CI test MUST use an isolated karnafim_ci database")
required=(
    "KARNAFIM_MAINTENANCE","KARNAFIM_LOCAL_AUTH_ENABLED",
    "KARNAFIM_SAFETY_RELEASE_APPROVED","KARNAFIM_ALLOW_REGISTRATION",
)
if any(os.environ.get(k)!="1" for k in required[1:]) or os.environ["KARNAFIM_MAINTENANCE"]!="0":
    raise RuntimeError("Test-only feature flags missing")

import app as site

BASE="https://karnafim-community-46.onrender.com"
assert not site.READ_ONLY_BOOT
assert site.app.config["SESSION_COOKIE_NAME"]=="karnafim_member_session"
sent=[]
site.send_confirmation=lambda address,token: sent.append((address,token)) or True

def csrf(client):
    with client.session_transaction(base_url=BASE) as sess:
        return sess["csrf"]

def image():
    f=io.BytesIO()
    Image.new("RGB",(64,64),(140,160,155)).save(f,format="JPEG")
    f.seek(0)
    return f

with site.app.test_client() as client:
    r=client.get("/register",base_url=BASE)
    assert r.status_code==200,(r.status_code,r.data[:140])
    form={"name":"חבר ניסיון","email":"test.member@example.test",
          "password":"synthetic-member-password!2026","consent":"on",
          "company":"פלוגת בדיקה"}
    r=client.post("/register",base_url=BASE,data={**form,"csrf":csrf(client)})
    assert r.status_code==200 and len(sent)==1,(r.status_code,len(sent),r.data[:200])
    row=site.sql("SELECT * FROM members WHERE email=%s",(form["email"],),True)[0]
    member_id=row["id"]
    assert row["verification_required"] and not row["approved"]
    assert row["password"]!=form["password"]
    assert site.verify(form["password"],row["password"])
    assert site.sql("SELECT COUNT(*) n FROM email_verification_tokens",fetch=True)[0]["n"]==1

    r=client.post("/login",base_url=BASE,data={"email":form["email"],
              "password":form["password"],"csrf":csrf(client)})
    assert r.status_code==403,("must verify first",r.status_code)
    token=sent[0][1]
    before=client.get("/verify-email?token="+token,base_url=BASE)
    assert before.status_code==200
    assert before.headers["Referrer-Policy"]=="no-referrer"
    r=client.post("/verify-email",base_url=BASE,data={"csrf":csrf(client),"token":token})
    assert r.status_code==200,(r.status_code,r.data[:300])
    assert not site.sql("SELECT verification_required FROM members WHERE id=%s",(member_id,),True)[0]["verification_required"]
    assert site.sql("SELECT COUNT(*) n FROM email_verification_tokens",fetch=True)[0]["n"]==0
    assert client.post("/verify-email",base_url=BASE,data={"csrf":csrf(client),"token":token}).status_code==410

    login=client.post("/login",base_url=BASE,data={"csrf":csrf(client),
          "email":form["email"],"password":form["password"]})
    assert login.status_code==303,login.status_code
    assert client.get("/new-post",base_url=BASE).status_code==200
    assert client.get("/my-posts",base_url=BASE).status_code==200

    story=client.post("/new-post",base_url=BASE,data={
        "csrf":csrf(client),"rights":"on","post_type":"photo",
        "title":"תצלום מבדיקת הקהילה","body":"תמונה מקורית מבדיקת מערכת ללא מידע אישי.",
        "attachments":(image(),"unit-test.jpg","image/jpeg"),
    },content_type="multipart/form-data")
    assert story.status_code==303,(story.status_code,story.data[:400])
    assert story.headers["Location"].endswith("submitted=1")
    posts=site.sql("SELECT * FROM community_posts WHERE author_id=%s",(member_id,),True)
    assert len(posts)==1,posts
    post=posts[0]
    assert not post["approved"],post
    assert post["ai_status"]=="pending_member_approval",post
    assert not post["ai_consent"]
    media=site.sql("SELECT id FROM community_media WHERE post_id=%s",(post["id"],),True)
    assert len(media)==1,media
    media_url="/community-media/"+str(media[0]["id"])
    assert client.get(media_url,base_url=BASE).status_code==200,("owner should see draft")
    assert client.get("/my-posts",base_url=BASE).status_code==200

    # A moderator may not make an unapproved member's material public.
    site.sql("""INSERT INTO members(name,email,password,approved)
       VALUES('מנהלת בדיקה','admin@example.test',%s,TRUE)""",
       (site.hashpw("synthetic-admin-password!2026"),))
    moderator_id=site.sql("SELECT id FROM members WHERE email='admin@example.test'",fetch=True)[0]["id"]
    with client.session_transaction(base_url=BASE) as sess:
        sess["uid"]=moderator_id
        sess["auth_method"]="local"
        sess["credential_version"]=0
        sess["csrf"]="synthetic-csrf"
    moderation=client.post("/community/moderation",base_url=BASE,
       data={"csrf":"synthetic-csrf","id":str(post["id"]),"op":"publish"})
    assert moderation.status_code==409,moderation.status_code
    assert not site.sql("SELECT approved FROM community_posts WHERE id=%s",(post["id"],),True)[0]["approved"]

    site.sql("UPDATE members SET approved=TRUE WHERE id=%s",(member_id,))
    moderated=client.post("/community/moderation",base_url=BASE,
       data={"csrf":"synthetic-csrf","id":str(post["id"]),"op":"publish"})
    assert moderated.status_code in (302,303),moderated.status_code
    assert site.sql("SELECT approved FROM community_posts WHERE id=%s",(post["id"],),True)[0]["approved"]

    # Unauthenticated public may not read member-uploaded files.
    with client.session_transaction(base_url=BASE) as sess:
        sess.clear()
    assert client.get(media_url,base_url=BASE).status_code==403

print("PASS: PostgreSQL signup, confirmation, password login, private photo upload, moderator membership gate and media isolation")
