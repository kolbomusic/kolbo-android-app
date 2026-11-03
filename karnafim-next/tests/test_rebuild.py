"""Integration regression suite for the *new* Barkan app only.

Always use a disposable local Postgres. Email is mocked; no production sending,
no real member credentials, and no deployment is involved.
"""
import hashlib
import io
import os
import subprocess
import sys
from pathlib import Path
from PIL import Image

APP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP))
DB=os.environ.get("DATABASE_URL","")
assert "localhost" in DB or "127.0.0.1" in DB, "Refuse nonlocal database"
assert "/barkan_ci" in DB, "Refuse non-test database"
assert os.environ.get("BARKAN_SAFETY_RELEASE_APPROVED")=="1"
assert os.environ.get("BARKAN_PUBLIC_AUTH")=="1"
assert os.environ.get("BARKAN_ALLOW_SIGNUP")=="1"
import app as site
assert site.PUBLIC_AUTH and site.ALLOW_SIGNUP
ORIGIN="https://karnafim-barkan-46.onrender.com"

def get_csrf(client):
    # Logout clears the session, so bootstrap the new CSRF with an ordinary GET.
    client.get("/health",base_url=ORIGIN)
    with client.session_transaction(base_url=ORIGIN) as sess:
        return sess["csrf"]

def jpeg():
    buf=io.BytesIO()
    Image.new("RGB",(60,60),(130,160,120)).save(buf,"JPEG")
    buf.seek(0)
    return buf

send_log=[]
def mock_delivery(email,uid):
    token="syntheticToken"+"A"*45
    value=hashlib.sha256(token.encode()).hexdigest()
    site.sql("""INSERT INTO b2_tokens(user_id,digest,expires)
        VALUES(%s,%s,NOW()+INTERVAL '24 hours')
        ON CONFLICT(user_id) DO UPDATE SET digest=EXCLUDED.digest,expires=EXCLUDED.expires""",
        (uid,value))
    send_log.append((email,token))
    return True
site.send_verification=mock_delivery

with site.app.test_client() as browser:
    for route in ("/","/heritage","/memorial","/photos","/about","/privacy","/terms","/safety","/help","/status"):
        r=browser.get(route,base_url=ORIGIN)
        assert r.status_code==200,(route,r.status_code)
        assert 'lang="he" dir="rtl"' in r.get_data(as_text=True)
        assert "default-src 'none'" in r.headers["Content-Security-Policy"]
    r=browser.get("/signup",base_url=ORIGIN)
    assert r.status_code==200
    assert 'id="account-password"' in r.get_data(as_text=True)
    assert 'autocomplete="new-password"' in r.get_data(as_text=True)
    assert 'data-password-toggle' in r.get_data(as_text=True)
    login_form=browser.get("/login",base_url=ORIGIN)
    assert login_form.status_code==200
    assert 'autocomplete="current-password"' in login_form.get_data(as_text=True)
    assert 'aria-controls="account-password"' in login_form.get_data(as_text=True)
    email="synthetic.member@example.test"
    fields={
        "csrf":get_csrf(browser),"name":"חבר בדיקות",
        "email":email,"password":"SyntheticTestPassword#2026",
        "agree":"yes","website":"",
    }
    r=browser.post("/signup",base_url=ORIGIN,data=fields)
    assert r.status_code==200,(r.status_code,r.get_data(as_text=True)[:250])
    assert len(send_log)==1
    member=site.sql("SELECT id,approved,email_verification_required FROM b2_users WHERE email=%s",(email,),True)
    assert member and not member["approved"] and member["email_verification_required"]
    assert site.sql("SELECT user_id FROM b2_tokens WHERE user_id=%s",(member["id"],),True)

    r=browser.post("/login",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"email":email,"password":"SyntheticTestPassword#2026"})
    assert r.status_code==403,r.status_code
    token=send_log[0][1]
    assert browser.get("/verify-email?token="+token,base_url=ORIGIN).status_code==200
    r=browser.post("/verify-email",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"token":token})
    assert r.status_code==200
    r=browser.post("/verify-email",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"token":token})
    assert r.status_code==410
    assert not site.sql("SELECT email_verification_required FROM b2_users WHERE id=%s",
                       (member["id"],),True)["email_verification_required"]

    r=browser.post("/login",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"email":email,"password":"SyntheticTestPassword#2026"})
    assert r.status_code==303,r.status_code
    assert browser.get("/new",base_url=ORIGIN).status_code==200
    assert browser.get("/find",base_url=ORIGIN).status_code==403

    r=browser.post("/new",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"rights":"yes",
        "title":"זיכרון בדיקה","body":"סיפור בדיקה שנכתב ללא מידע מזהה.",
        "kind":"photo","uploads":(jpeg(),"photo.jpg","image/jpeg"),
    },content_type="multipart/form-data")
    assert r.status_code==303,(r.status_code,r.get_data(as_text=True)[:240])
    post=site.sql("SELECT id,status FROM b2_posts WHERE author=%s",(member["id"],),True)
    assert post["status"]=="pending"
    photo=site.sql("SELECT id,mime FROM b2_media WHERE post_id=%s",(post["id"],),True)
    assert photo["mime"]=="image/jpeg"
    assert browser.get("/media/"+str(photo["id"]),base_url=ORIGIN).status_code==200
    assert browser.get("/my-posts",base_url=ORIGIN).status_code==200
    # Pending media never leaks into the public-facing gallery.
    gallery=browser.get("/photos",base_url=ORIGIN).get_data(as_text=True)
    assert "/media/"+str(photo["id"]) not in gallery

    admin_email="admin@example.test"
    row=site.sql("""INSERT INTO b2_users(name,email,passhash,approved)
        VALUES(%s,%s,%s,TRUE) RETURNING id""",
        ("מנהל ניסוי",admin_email,site.hashpw("SyntheticAdminPassword!2026")),True)
    admin_id=row["id"]
    browser.post("/logout",base_url=ORIGIN,data={"csrf":get_csrf(browser)})
    r=browser.post("/login",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"email":admin_email,"password":"SyntheticAdminPassword!2026"})
    assert r.status_code==303
    r=browser.post("/moderation",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(post["id"]),"action":"publish"})
    assert r.status_code==409,"Publishing unapproved member's post must fail"
    r=browser.post("/members",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(member["id"]),"action":"approve"})
    assert r.status_code==303
    r=browser.post("/moderation",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(post["id"]),"action":"publish"})
    assert r.status_code==303
    assert site.sql("SELECT status FROM b2_posts WHERE id=%s",(post["id"],),True)["status"]=="published"
    assert browser.get("/feed",base_url=ORIGIN).status_code==200
    # Only approved members see media from published, approved authors.
    gallery=browser.get("/photos",base_url=ORIGIN).get_data(as_text=True)
    assert "/media/"+str(photo["id"]) in gallery
    assert "זיכרון בדיקה" in gallery
    assert browser.get("/find",base_url=ORIGIN).status_code==200

    r=browser.post("/chat/"+str(member["id"]),base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"text":"הודעת ניסיון פרטית"})
    assert r.status_code==303
    assert site.sql("SELECT COUNT(*) AS n FROM b2_messages",one=True)["n"]==1
    assert browser.get("/inbox",base_url=ORIGIN).status_code==200
    browser.post("/logout",base_url=ORIGIN,data={"csrf":get_csrf(browser)})
    assert browser.get("/media/"+str(photo["id"]),base_url=ORIGIN).status_code==303

# The exact same app is public-information-only until explicitly safety approved.
off_env=dict(os.environ)
off_env["BARKAN_PUBLIC_AUTH"]="0"
off_env["BARKAN_ALLOW_SIGNUP"]="0"
off=subprocess.run([sys.executable,"-c",'''
import app
c=app.app.test_client()
base="https://karnafim-barkan-46.onrender.com"
assert c.get("/",base_url=base).status_code==200
assert c.get("/signup",base_url=base).status_code==503
assert c.get("/login",base_url=base).status_code==503
assert c.get("/media/1",base_url=base).status_code==503
assert c.get("/health",base_url=base).get_json()["auth_enabled"] is False
'''],cwd=APP,env=off_env,capture_output=True,text=True,timeout=25)
assert off.returncode==0,(off.stdout,off.stderr[-3000:])
print("PASS: independent Barkan rebuild - public routes, email verification, password, uploads, privacy, moderation, chat, read-only safety gate")
