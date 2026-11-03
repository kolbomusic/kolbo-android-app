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
# Exercise the real one-time legacy import using a synthetic account.
# This test runs against /barkan_ci on localhost only.
import psycopg
legacy_password="Old#2468"
legacy_salt="0123456789abcdef0123456789abcdef"
legacy_hash=legacy_salt+":"+hashlib.pbkdf2_hmac(
    "sha256",legacy_password.encode(),bytes.fromhex(legacy_salt),250000).hex()
with psycopg.connect(DB) as connection:
    with connection.cursor() as cursor:
        cursor.execute("""CREATE TABLE members(
            id BIGSERIAL PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE,
            password TEXT NOT NULL,nickname TEXT DEFAULT '',approved BOOLEAN DEFAULT FALSE)""")
        cursor.execute("""INSERT INTO members(name,email,password,nickname,approved)
            VALUES(%s,%s,%s,%s,TRUE)""",
            ("חבר בדיקת מעבר","legacy-test@example.test",legacy_hash,"חבר ותיק"))
# Even with an API key configured and member login enabled, registration
# MUST stay locked until a real delivery test is independently approved.
isolated_env=dict(os.environ)
isolated_env["BARKAN_MAIL_DELIVERY_VERIFIED"]="0"
lock_test=subprocess.run([sys.executable,"-c", """
import app
assert app.PUBLIC_AUTH is True
assert app.MAIL_READY is True
assert app.MAIL_DELIVERY_VERIFIED is False
assert app.ALLOW_SIGNUP is False
c=app.app.test_client()
base="https://karnafim-community-46.onrender.com"
assert c.get("/signup",base_url=base).status_code==503
assert c.get("/health",base_url=base).get_json()["email_delivery_release_verified"] is False
"""],cwd=APP,env=isolated_env,capture_output=True,text=True,timeout=30)
assert lock_test.returncode==0,(lock_test.stdout,lock_test.stderr[-1200:])

# Validate both provider adapters without making any outbound request.
# Verify that an API key alone cannot enable public registration.
for name, key_name, other_key, expected_endpoint in (
    ("brevo","BARKAN_BREVO_API_KEY","BARKAN_RESEND_API_KEY",
     "https://api.brevo.com/v3/smtp/email"),
    ("resend","BARKAN_RESEND_API_KEY","BARKAN_BREVO_API_KEY",
     "https://api.resend.com/emails"),
):
    mail_env=dict(os.environ)
    mail_env[key_name]="synthetic-test-api-key"
    mail_env.pop(other_key,None)
    mail_env["BARKAN_MAIL_DELIVERY_VERIFIED"]="0"
    provider_test=subprocess.run([sys.executable,"-c", """
import json
import unittest.mock as mock
import app
assert app.EMAIL_TRANSPORT == "EXPECTED_PROVIDER"
assert app.MAIL_READY and not app.MAIL_DELIVERY_VERIFIED
assert not app.ALLOW_SIGNUP
from urllib.request import Request
class MockResponse:
    status=201
    def __enter__(self):return self
    def __exit__(self,*args):pass
def capture(request,timeout):
    assert isinstance(request,Request)
    assert request.full_url=="EXPECTED_ENDPOINT"
    assert timeout==7
    payload=json.loads(request.data.decode())
    assert payload["subject"]=="אימות דוא״ל — הקרנפים / ברקן"
    if app.EMAIL_TRANSPORT=="brevo":
        assert payload["sender"]["email"]=="noreply@example.test"
        assert payload["to"]==[{"email":"synthetic.member@example.test"}]
        assert "htmlContent" in payload
    else:
        assert payload["from"]=="noreply@example.test"
        assert payload["to"]==["synthetic.member@example.test"]
        assert "html" in payload
    return MockResponse()
with mock.patch("urllib.request.urlopen",side_effect=capture):
    assert app.send_verification("synthetic.member@example.test",1)
assert app.sql("SELECT COUNT(*) AS n FROM b2_tokens WHERE user_id=1",one=True)["n"]==1
""" .replace("EXPECTED_PROVIDER",name).replace("EXPECTED_ENDPOINT",expected_endpoint)],
       cwd=APP,env=mail_env,capture_output=True,text=True,timeout=30)
    assert provider_test.returncode==0,(
        name,provider_test.stdout,provider_test.stderr[-1500:])

import app as site
assert site.PUBLIC_AUTH and site.ALLOW_SIGNUP and site.MAIL_DELIVERY_VERIFIED
legacy=site.sql("SELECT id,passhash,approved FROM b2_users WHERE email=%s",
                ("legacy-test@example.test",),True)
assert legacy and legacy["approved"]
assert site.checkpw(legacy_password,legacy["passhash"])
assert not site.checkpw("incorrect-password",legacy["passhash"])
ORIGIN="https://karnafim-community-46.onrender.com"

# Free-tier storage hygiene: expired rate-limit fingerprints are discarded,
# while the current fingerprint remains available to enforce limits.
site.sql("INSERT INTO b2_throttle(fingerprint,at) VALUES(%s,NOW()-INTERVAL '4 days')",
         ("expired-ci-fingerprint",))
with site.app.test_request_context("/",base_url=ORIGIN):
    site.limit("ci-storage-sweep",5,15)
assert site.sql("SELECT COUNT(*) AS n FROM b2_throttle WHERE fingerprint=%s",
                ("expired-ci-fingerprint",),True)["n"]==0
assert site.sql("SELECT COUNT(*) AS n FROM b2_throttle WHERE at > NOW()-INTERVAL '1 minute'",
                one=True)["n"]>=1

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

with site.app.test_client() as old_member:
    r=old_member.post("/login",base_url=ORIGIN,data={
        "csrf":get_csrf(old_member),"email":"legacy-test@example.test",
        "password":legacy_password})
    assert r.status_code==303, r.status_code
    assert old_member.get("/my-posts",base_url=ORIGIN).status_code==200
    old_member.post("/logout",base_url=ORIGIN,
                    data={"csrf":get_csrf(old_member)})

with site.app.test_client() as browser:
    for route in ("/","/heritage","/memorial","/photos","/about","/privacy","/terms","/safety","/help","/status"):
        r=browser.get(route,base_url=ORIGIN)
        assert r.status_code==200,(route,r.status_code)
        assert 'lang="he" dir="rtl"' in r.get_data(as_text=True)
        assert "default-src 'none'" in r.headers["Content-Security-Policy"]
    ready=browser.get("/ready",base_url=ORIGIN)
    assert ready.status_code==200,ready.status_code
    assert ready.get_json()=={"status":"ready","database":"available",
                              "member_portal":"enabled","signup":"enabled"}
    assert "DATABASE_URL" not in ready.get_data(as_text=True)
    r=browser.get("/signup",base_url=ORIGIN)
    assert r.status_code==200
    assert 'id="account-password"' in r.get_data(as_text=True)
    assert 'autocomplete="new-password"' in r.get_data(as_text=True)
    assert 'minlength="12"' in r.get_data(as_text=True)
    assert 'data-password-toggle' in r.get_data(as_text=True)
    login_form=browser.get("/login",base_url=ORIGIN)
    assert login_form.status_code==200
    assert 'autocomplete="current-password"' in login_form.get_data(as_text=True)
    assert 'minlength="12"' not in login_form.get_data(as_text=True)
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

    # Non-admin pending applicants cannot list, approve or reject other members.
    assert browser.get("/members",base_url=ORIGIN).status_code==403
    assert browser.post("/members",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(member["id"]),"action":"approve",
        "identity_checked":"yes"}).status_code==403

    admin_email="admin@example.test"
    row=site.sql("""INSERT INTO b2_users(name,email,passhash,approved)
        VALUES(%s,%s,%s,TRUE) RETURNING id""",
        ("מנהל ניסוי",admin_email,site.hashpw("SyntheticAdminPassword!2026")),True)
    admin_id=row["id"]
    browser.post("/logout",base_url=ORIGIN,data={"csrf":get_csrf(browser)})
    r=browser.post("/login",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"email":admin_email,"password":"SyntheticAdminPassword!2026"})
    assert r.status_code==303
    admin_page=browser.get("/profile",base_url=ORIGIN)
    assert admin_page.status_code==200
    assert "מנהל קהילה" in admin_page.get_data(as_text=True)
    assert 'href="/members"' in admin_page.get_data(as_text=True)
    r=browser.post("/moderation",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(post["id"]),"action":"publish"})
    assert r.status_code==409,"Publishing unapproved member's post must fail"
    # Administrator cannot approve without an explicit identity and ownership check.
    r=browser.post("/members",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(member["id"]),"action":"approve"})
    assert r.status_code==400,"Identity confirmation required"
    assert site.sql("SELECT approved FROM b2_users WHERE id=%s",(member["id"],),True)["approved"] is False
    r=browser.post("/members",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(member["id"]),"action":"approve","identity_checked":"yes"})
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

# Manual registration uses no external mail; it creates an unapproved
# member who cannot access community content before an admin checks identity.
manual_env=dict(os.environ)
manual_env["BARKAN_MANUAL_SIGNUP"]="1"
manual_env["BARKAN_ALLOW_SIGNUP"]="0"
manual_env["BARKAN_MAIL_DELIVERY_VERIFIED"]="0"
manual_env.pop("BARKAN_BREVO_API_KEY",None)
manual_env.pop("BARKAN_RESEND_API_KEY",None)
manual=subprocess.run([sys.executable,"-c",'''
import app
origin="https://karnafim-community-46.onrender.com"
assert app.PUBLIC_AUTH and app.MANUAL_SIGNUP and app.ALLOW_SIGNUP
assert not app.MAIL_READY and not app.MAIL_DELIVERY_VERIFIED
c=app.app.test_client()
c.get("/signup",base_url=origin)
with c.session_transaction(base_url=origin) as ses: csrf=ses["csrf"]
r=c.post("/signup",base_url=origin,data={"csrf":csrf,"name":"חבר הרשמה ידנית",
  "email":"manual-pending@example.test","password":"SyntheticOnlyManualPassword!2026","agree":"yes"})
assert r.status_code==202,r.status_code
user=app.sql("SELECT id,approved,email_verification_required FROM b2_users WHERE email=%s",
             ("manual-pending@example.test",),True)
assert user and not user["approved"] and not user["email_verification_required"]
assert app.sql("SELECT COUNT(*) AS n FROM b2_tokens WHERE user_id=%s",(user["id"],),True)["n"]==0
c.get("/login",base_url=origin)
with c.session_transaction(base_url=origin) as ses: csrf=ses["csrf"]
assert c.post("/login",base_url=origin,data={"csrf":csrf,
  "email":"manual-pending@example.test","password":"SyntheticOnlyManualPassword!2026"}).status_code==303
assert c.get("/feed",base_url=origin).status_code==403
assert c.get("/find",base_url=origin).status_code==403
assert c.get("/new",base_url=origin).status_code==200  # own pending posts only
assert c.get("/inbox",base_url=origin).status_code==403
profile=c.get("/profile",base_url=origin)
assert profile.status_code==200
assert "בקשת חברות בהמתנה לאישור" in profile.get_data(as_text=True)
assert "ניהול בקשות חברות" not in profile.get_data(as_text=True)
'''],cwd=APP,env=manual_env,capture_output=True,text=True,timeout=50)
assert manual.returncode==0,(manual.stdout,manual.stderr[-1500:])

# The exact same app is public-information-only until explicitly safety approved.
off_env=dict(os.environ)
off_env["BARKAN_PUBLIC_AUTH"]="0"
off_env["BARKAN_ALLOW_SIGNUP"]="0"
off=subprocess.run([sys.executable,"-c",'''
import app
c=app.app.test_client()
base="https://karnafim-community-46.onrender.com"
assert c.get("/",base_url=base).status_code==200
assert c.get("/signup",base_url=base).status_code==503
assert c.get("/login",base_url=base).status_code==503
assert c.get("/media/1",base_url=base).status_code==503
assert c.get("/health",base_url=base).get_json()["auth_enabled"] is False
assert c.get("/ready",base_url=base).status_code==200
assert c.get("/ready",base_url=base).get_json()["member_portal"]=="closed"
'''],cwd=APP,env=off_env,capture_output=True,text=True,timeout=25)
assert off.returncode==0,(off.stdout,off.stderr[-3000:])
print("PASS: independent Barkan rebuild - public routes, email verification, password, uploads, privacy, moderation, chat, read-only safety gate")
