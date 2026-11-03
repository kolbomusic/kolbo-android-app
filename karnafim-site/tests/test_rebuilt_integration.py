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
        if route=="/":
            assert 'href="/signup"' in r.get_data(as_text=True)
        assert r.status_code==200,(route,r.status_code)
        assert 'lang="he" dir="rtl"' in r.get_data(as_text=True)
        assert "default-src 'none'" in r.headers["Content-Security-Policy"]
    memorial_html=browser.get("/memorial",base_url=ORIGIN).get_data(as_text=True)
    assert "יהונתן (יוני) שרעבי" in memorial_html
    assert "לוחם שריון · פלוגה ב׳ הקרנפים, גדוד 46" in memorial_html
    assert "3.8.2006" in memorial_html or "3 באוגוסט 2006" in memorial_html
    verified_memorials=(
        ("רס״ן בניה ריין ז״ל","מפקד כוח בניה","en_f5ccba845584f96f9b9334cf335d2e78"),
        ("סמ״ר אורי גרוסמן ז״ל","מפקד טנק ששימש כתותחן בכוח בניה","en_f53b79619b3f27184812b11f14e635a8"),
        ("סמ״ר אדם גורן ז״ל","טען־קשר בכוח בניה","en_e6446f8f52c2b18e0ec560602482bdda"),
        ("סמ״ר אלכסנדר (סשה) בונימוביץ׳ ז״ל","נהג הטנק בכוח בניה","en_34b2955a02b6a81f8ba932dbf6228e61"),
    )
    for name,role,official_record_id in verified_memorials:
        assert name in memorial_html,(name,"name or rank differs from official record")
        assert role in memorial_html,(name,"crew role mismatch")
        assert official_record_id in memorial_html,(name,"missing or changed Ministry of Defense record")
    assert "סמל יהונתן (יוני) שרעבי ז״ל" in memorial_html
    assert "en_53e66dd727188835acbe02a1f641a882" in memorial_html
    assert memorial_html.count('סיפור החיים באתר יזכור')>=5
    assert memorial_html.count("12.8.2006")>=4
    assert "המידע ההיסטורי מקושר לעמודי הנצחה רשמיים" in memorial_html
    assert "תפקידו כנהג טנק" in memorial_html
    assert "יוני) שרעבי שירת בפלוגה ב׳ ״הקרנפים״ כתותחן" not in memorial_html
    assert "תותחן מרכבה סימן 4 · פלוגה ב׳" not in memorial_html
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
    assert browser.get("/cohorts",base_url=ORIGIN).status_code==403
    assert browser.get("/cohorts/2003-11",base_url=ORIGIN).status_code==403

    r=browser.post("/new",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"rights":"yes",
        "title":"זיכרון בדיקה","body":"סיפור בדיקה שנכתב ללא מידע מזהה.",
        "kind":"photo","album_cohort":"2003-11",
        "uploads":(jpeg(),"photo.jpg","image/jpeg"),
    },content_type="multipart/form-data")
    assert r.status_code==303,(r.status_code,r.get_data(as_text=True)[:240])
    post=site.sql("SELECT id,status FROM b2_posts WHERE author=%s",(member["id"],),True)
    assert post["status"]=="pending"
    assert site.sql("SELECT album_cohort FROM b2_posts WHERE id=%s",(post["id"],),True)["album_cohort"]=="2003-11"
    photo=site.sql("SELECT id,mime FROM b2_media WHERE post_id=%s",(post["id"],),True)
    assert photo["mime"]=="image/jpeg"
    assert browser.get("/media/"+str(photo["id"]),base_url=ORIGIN).status_code==200
    assert browser.get("/my-posts",base_url=ORIGIN).status_code==200
    # Pending media never leaks into the public-facing gallery.
    gallery=browser.get("/photos",base_url=ORIGIN).get_data(as_text=True)
    assert "/media/"+str(photo["id"]) not in gallery
    assert browser.post("/photos/self-tag",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(photo["id"]),"action":"add"}).status_code==403

    # Non-admin pending applicants cannot list, approve or reject other members.
    assert browser.get("/photo-review",base_url=ORIGIN).status_code==403
    assert browser.post("/photos/report",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(photo["id"]),
        "reason":"בקשה של חבר לא מאושר"}).status_code==403
    assert browser.get("/dashboard",base_url=ORIGIN).status_code==403
    assert browser.get("/members",base_url=ORIGIN).status_code==403
    assert browser.post("/members",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(member["id"]),"action":"approve",
        "identity_checked":"yes"}).status_code==403

    # Audio is a single file and stays pending until moderation.
    assert browser.get("/voices",base_url=ORIGIN).status_code==403
    invalid=browser.post("/new",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"rights":"yes","title":"הקלטה שגויה",
        "kind":"voice","uploads":(jpeg(),"picture.jpg","image/jpeg")
    },content_type="multipart/form-data")
    assert invalid.status_code==400
    recording=io.BytesIO(b"\x1a\x45\xdf\xa3"+b"synthetic opus audio payload")
    saved=browser.post("/new",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"rights":"yes","title":"סיפור מוקלט ניסיוני",
        "body":"זיכרון קצר ולא מזהה","kind":"voice","album_cohort":"2003-11",
        "uploads":(recording,"voice.webm","audio/webm")
    },content_type="multipart/form-data")
    assert saved.status_code==303,(saved.status_code,saved.get_data(as_text=True)[:240])
    voice_post=site.sql("SELECT id,status FROM b2_posts WHERE kind='voice' ORDER BY id DESC LIMIT 1",one=True)
    assert voice_post["status"]=="pending"
    voice_media=site.sql("SELECT id,mime FROM b2_media WHERE post_id=%s",(voice_post["id"],),True)
    assert voice_media["mime"]=="audio/webm"

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
    assert "מנהל הקהילה הראשי" in admin_page.get_data(as_text=True)
    assert 'href="/members"' in admin_page.get_data(as_text=True)
    dashboard=browser.get("/dashboard",base_url=ORIGIN)
    assert dashboard.status_code==200
    assert "לוח הבקרה של מנהל הקהילה" in dashboard.get_data(as_text=True)
    assert 'href="/members"' in dashboard.get_data(as_text=True)
    assert 'href="/moderation"' in dashboard.get_data(as_text=True)
    assert "synthetic.member@example.test" not in dashboard.get_data(as_text=True)
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
    assert site.sql("SELECT action FROM b2_admin_audit ORDER BY id DESC LIMIT 1",one=True)["action"]=="member_approved"
    # Private referral: another approved member can vouch for a pending
    # applicant exactly once. Recommendation cannot change approval status.
    candidate=site.sql("""INSERT INTO b2_users(name,email,passhash,approved,
          membership_status,service_claim,referral_code)
          VALUES(%s,%s,%s,FALSE,'pending',%s,%s) RETURNING id""",
          ("מועמד ניסוי","candidate@example.test",
           site.hashpw("CandidateTestPassword!2026"),
           "פלוגה ב נובמבר 2003, נהג מרכבה","synthetic-private-code-abcdefghijklmnopqrstuvwxyz"),
           True)
    recommender=site.app.test_client()
    assert recommender.post("/login",base_url=ORIGIN,data={
        "csrf":get_csrf(recommender),"email":email,
        "password":"SyntheticTestPassword#2026"}).status_code==303
    assert recommender.get("/recommend",base_url=ORIGIN).status_code==200
    assert recommender.post("/recommend",base_url=ORIGIN,data={
        "csrf":get_csrf(recommender),"code":"invalid-private-code-abcdefghijklmnopqrst",
        "context":"שירתנו באותה מחלקה בפלוגה ב בשנת 2003"}).status_code==400
    referral_form={
        "csrf":get_csrf(recommender),
        "code":"synthetic-private-code-abcdefghijklmnopqrstuvwxyz",
        "context":"שירתנו באותה מחלקה בפלוגה ב בשנת 2003"}
    assert recommender.post("/recommend",base_url=ORIGIN,data=referral_form).status_code==200
    assert recommender.post("/recommend",base_url=ORIGIN,data=referral_form).status_code==200
    assert site.sql("SELECT count(*) n FROM b2_membership_recommendations WHERE applicant=%s",
        (candidate["id"],),True)["n"]==1
    assert site.sql("SELECT approved FROM b2_users WHERE id=%s",
        (candidate["id"],),True)["approved"] is False
    review=browser.get("/members",base_url=ORIGIN).get_data(as_text=True)
    assert "מועמד ניסוי" in review and "המלצות חברים מאושרים: 1" in review
    assert "שירתנו באותה מחלקה" in review
    # Memorial photo sources belong to the LIVE application flow.
    # A member may suggest evidence, but may not review or publish an image.
    assert recommender.get("/memorial-sources?person=yoni-sharabi",
                           base_url=ORIGIN).status_code==200
    assert recommender.get("/memorial-source-review",base_url=ORIGIN).status_code==403
    proposed={
        "csrf":get_csrf(recommender),
        "person_key":"yoni-sharabi",
        "source_url":"https://www.izkor.gov.il/יהונתן%20שרעבי/en_53e66dd727188835acbe02a1f641a882",
        "evidence":"רשומת ההנצחה הרשמית המזהה את המצולם בשם ובפרטים הנכונים",
        "rights_note":"אין עדיין רישיון שימוש חוזר בתמונה",
    }
    invalid=dict(proposed,source_url="https://localhost/private")
    assert recommender.post("/memorial-sources",base_url=ORIGIN,data=invalid).status_code==400
    assert recommender.post("/memorial-sources",base_url=ORIGIN,data=proposed).status_code==303
    item=site.sql("""SELECT id,person_key,izkor_id,status FROM b2_memorial_source_suggestions
                      WHERE contributor=%s ORDER BY id DESC LIMIT 1""",(member["id"],),True)
    assert item["person_key"]=="yoni-sharabi"
    assert item["izkor_id"]==site.MEMORIAL_PEOPLE["yoni-sharabi"]["izkor_id"]
    assert item["status"]=="pending"
    assert "ממתין לבדיקת מנהל" in recommender.get(
        "/memorial-sources",base_url=ORIGIN).get_data(as_text=True)
    assert "הצעת מקור תמונה לאדם זה" in recommender.get(
        "/memorial",base_url=ORIGIN).get_data(as_text=True)
    review_html=browser.get("/memorial-source-review",base_url=ORIGIN)
    assert review_html.status_code==200
    assert "רשומת ההנצחה הרשמית" in review_html.get_data(as_text=True)
    explanation="המקור נבדק; אין אישור להעתיק את התמונה לפני קבלת רישיון שימוש."
    assert browser.post("/memorial-source-review",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(item["id"]),
        "action":"reviewed","reason":explanation
    }).status_code==303
    assert site.sql("""SELECT status,decision_reason FROM b2_memorial_source_suggestions
                       WHERE id=%s""",(item["id"],),True)=={
                           "status":"reviewed","decision_reason":explanation}
    member_history=recommender.get("/memorial-sources",base_url=ORIGIN).get_data(as_text=True)
    assert explanation in member_history and "אינו אישור לפרסום" in member_history
    assert "memorial-portrait" not in recommender.get(
        "/memorial",base_url=ORIGIN).get_data(as_text=True)

    # Recommendation code and applicant identity are not exposed in public URLs.
    assert "synthetic-private-code" not in browser.get("/",base_url=ORIGIN).get_data(as_text=True)

    r=browser.post("/moderation",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(post["id"]),"action":"publish"})
    assert r.status_code==303
    assert site.sql("SELECT status FROM b2_posts WHERE id=%s",(post["id"],),True)["status"]=="published"
    assert browser.get("/feed",base_url=ORIGIN).status_code==200
    assert "סיפור מוקלט ניסיוני" not in browser.get("/voices",base_url=ORIGIN).get_data(as_text=True)
    assert browser.post("/moderation",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(voice_post["id"]),"action":"publish"}).status_code==303
    archive=browser.get("/voices?cohort=2003-11",base_url=ORIGIN)
    assert archive.status_code==200
    assert "סיפור מוקלט ניסיוני" in archive.get_data(as_text=True)
    assert browser.get("/cohorts/2003-11",base_url=ORIGIN).status_code==200
    hub=browser.get("/cohorts/2003-11",base_url=ORIGIN).get_data(as_text=True)
    assert "סיפור מוקלט ניסיוני" in hub
    assert "זיכרון בדיקה" in hub
    assert "/media/"+str(voice_media["id"]) in hub
    assert browser.get("/cohorts/2003-99",base_url=ORIGIN).status_code==404
    assert browser.get("/cohorts/2004-03",base_url=ORIGIN).status_code==200
    assert "סיפור מוקלט ניסיוני" not in browser.get("/cohorts/2004-03",base_url=ORIGIN).get_data(as_text=True)
    assert "/media/"+str(voice_media["id"]) in archive.get_data(as_text=True)
    assert "סיפור מוקלט ניסיוני" not in browser.get("/voices?cohort=2004-03",base_url=ORIGIN).get_data(as_text=True)
    assert browser.get("/voices?cohort=2004-99",base_url=ORIGIN).status_code==400

    # Only approved members see media from published, approved authors.
    gallery=browser.get("/photos",base_url=ORIGIN).get_data(as_text=True)
    assert "/media/"+str(photo["id"]) in gallery
    assert "זיכרון בדיקה" in gallery
    assert "2003-11" in gallery
    assert "זיכרון בדיקה" in browser.get("/photos?cohort=2003-11",base_url=ORIGIN).get_data(as_text=True)
    assert "זיכרון בדיקה" not in browser.get("/photos?cohort=2004-03",base_url=ORIGIN).get_data(as_text=True)
    assert browser.get("/photos?cohort=2004-99",base_url=ORIGIN).status_code==400
    assert browser.post("/photos/self-tag",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(photo["id"]),"action":"add"}).status_code==303
    assert site.sql("SELECT count(*) n FROM b2_photo_self_tags WHERE media_id=%s",(photo["id"],),True)["n"]==1
    assert browser.post("/photos/self-tag",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(photo["id"]),"action":"add"}).status_code==303
    assert site.sql("SELECT count(*) n FROM b2_photo_self_tags WHERE media_id=%s",(photo["id"],),True)["n"]==1
    assert "מנהל ניסוי" in browser.get("/photos?cohort=2003-11",base_url=ORIGIN).get_data(as_text=True)
    assert browser.post("/photos/self-tag",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(photo["id"]),"action":"remove"}).status_code==303
    assert site.sql("SELECT count(*) n FROM b2_photo_self_tags WHERE media_id=%s",(photo["id"],),True)["n"]==0
    # Photo memories remain unpublished until moderator review.
    memory=browser.post("/photos/memory",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(photo["id"]),
        "body":"סיפור מקורי של חברי הפלוגה מהצילום"})
    assert memory.status_code==303
    mem=site.sql("SELECT id,status FROM b2_photo_memories WHERE media_id=%s",
                 (photo["id"],),True)
    assert mem["status"]=="pending"
    assert "סיפור מקורי של חברי הפלוגה" not in browser.get(
        "/photos",base_url=ORIGIN).get_data(as_text=True)
    assert browser.post("/photo-review",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(mem["id"]),
        "action":"publish_memory"}).status_code==303
    assert "סיפור מקורי של חברי הפלוגה" in browser.get(
        "/photos",base_url=ORIGIN).get_data(as_text=True)
    # A privacy request is private to reviewers until resolved.
    report=browser.post("/photos/report",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(photo["id"]),
        "reason":"נא לבדוק את התמונה בהיבט הפרטיות"})
    assert report.status_code==303
    case=site.sql("SELECT id,status FROM b2_photo_reports WHERE media_id=%s",
                  (photo["id"],),True)
    assert case["status"]=="open"
    assert "נא לבדוק את התמונה בהיבט הפרטיות" not in browser.get(
        "/photos",base_url=ORIGIN).get_data(as_text=True)
    assert browser.post("/photo-review",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(case["id"]),
        "action":"hide_photo"}).status_code==303
    assert site.sql("SELECT status FROM b2_posts WHERE id=%s",
                    (post["id"],),True)["status"]=="hidden"
    assert "/media/"+str(photo["id"]) not in browser.get(
        "/photos",base_url=ORIGIN).get_data(as_text=True)

    assert browser.get("/find",base_url=ORIGIN).status_code==200
    # The directory is strictly opt-in: approved members stay invisible
    # until they deliberately enable visibility in their own profile.
    blank=browser.get("/find?q=חבר",base_url=ORIGIN).get_data(as_text=True)
    assert "חבר בדיקות" not in blank
    opt_in_user=site.app.test_client()
    r=opt_in_user.post("/login",base_url=ORIGIN,data={
        "csrf":get_csrf(opt_in_user),"email":email,
        "password":"SyntheticTestPassword#2026"})
    assert r.status_code==303
    r=opt_in_user.post("/profile",base_url=ORIGIN,data={
        "csrf":get_csrf(opt_in_user),"nickname":"שריונר בדיקה",
        "unit_year":"2003–2006","cohort":"2003-11",
        "service_role":"נהג מרכבה","platoon":"פלוגה ב׳","visible":"on"})
    assert r.status_code==303
    assert site.sql("SELECT enlistment_cohort,service_role,show_profile FROM b2_users WHERE id=%s",
        (member["id"],),True)=={
        "enlistment_cohort":"2003-11","service_role":"נהג מרכבה","show_profile":True}
    assert opt_in_user.post("/profile",base_url=ORIGIN,data={
        "csrf":get_csrf(opt_in_user),"cohort":"2003-99","visible":"on"}).status_code==400
    visible=browser.get("/find?cohort=2003-11&q=מרכבה",base_url=ORIGIN).get_data(as_text=True)
    assert "חבר בדיקות" in visible and "נהג מרכבה" in visible
    cohort_hub=browser.get("/cohorts/2003-11",base_url=ORIGIN).get_data(as_text=True)
    assert "חבר בדיקות" in cohort_hub and "נהג מרכבה" in cohort_hub
    assert "synthetic.member@example.test" not in cohort_hub
    assert 'href="/cohorts/2003-11"' in browser.get("/cohorts",base_url=ORIGIN).get_data(as_text=True)
    assert "synthetic.member@example.test" not in visible
    assert "חבר בדיקות" not in browser.get("/find?cohort=2004-03",base_url=ORIGIN).get_data(as_text=True)
    # Disabling visibility immediately removes the profile from search.
    site.sql("UPDATE b2_users SET show_profile=FALSE WHERE id=%s",(member["id"],))
    assert "חבר בדיקות" not in browser.get("/find?q=מרכבה",base_url=ORIGIN).get_data(as_text=True)
    assert "<h3>חבר בדיקות</h3>" not in browser.get("/cohorts/2003-11",base_url=ORIGIN).get_data(as_text=True)  # public post byline may remain

    r=browser.post("/chat/"+str(member["id"]),base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"text":"הודעת ניסיון פרטית"})
    assert r.status_code==303
    assert site.sql("SELECT COUNT(*) AS n FROM b2_messages",one=True)["n"]==1
    assert browser.get("/inbox",base_url=ORIGIN).status_code==200
    # Private reunion calendar: only approved members see events,
    # and only owner or delegated organizer can create/cancel them.
    assert browser.get("/meetups",base_url=ORIGIN).status_code==200
    create_event=browser.post("/meetups",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"title":"מפגש פלוגה ניסיוני",
        "when":"2027-07-15T18:30","location":"מקום כללי",
        "details":"אירוע בדיקה בלבד"})
    assert create_event.status_code==303,(create_event.status_code,create_event.get_data(as_text=True)[:200])
    meetup=site.sql("SELECT id,cancelled FROM b2_meetups ORDER BY id DESC LIMIT 1",one=True)
    assert meetup and not meetup["cancelled"]
    event_id=meetup["id"]
    assert "מפגש פלוגה ניסיוני" in browser.get("/meetups",base_url=ORIGIN).get_data(as_text=True)
    assert browser.post("/meetups/rsvp",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(event_id),"decision":"yes"}).status_code==303
    assert site.sql("SELECT COUNT(*) AS n FROM b2_meetup_rsvps WHERE meetup_id=%s AND attending=TRUE",
                    (event_id,),True)["n"]==1
    assert browser.post("/meetups/rsvp",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(event_id),"decision":"no"}).status_code==303
    assert site.sql("SELECT COUNT(*) AS n FROM b2_meetup_rsvps WHERE meetup_id=%s AND attending=TRUE",
                    (event_id,),True)["n"]==0

    # Owner delegates moderation + invitations without membership approval.
    assert browser.get("/team",base_url=ORIGIN).status_code==200
    audit_start=site.sql("SELECT COUNT(*) AS n FROM b2_admin_audit",one=True)["n"]
    grant=browser.post("/team",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(member["id"]),"action":"save",
        "can_moderate":"yes","can_invite":"yes"})
    assert grant.status_code==303
    assert site.sql("SELECT COUNT(*) AS n FROM b2_admin_audit",one=True)["n"]==audit_start+1
    assert site.sql("SELECT action FROM b2_admin_audit ORDER BY id DESC LIMIT 1",one=True)["action"]=="roles_saved"
    assert site.sql("SELECT can_approve,can_moderate,can_invite FROM b2_staff_roles WHERE user_id=%s",
        (member["id"],),True)=={"can_approve":False,"can_moderate":True,"can_invite":True}
    delegate=site.app.test_client()
    login=delegate.post("/login",base_url=ORIGIN,data={
        "csrf":get_csrf(delegate),"email":email,"password":"SyntheticTestPassword#2026"})
    assert login.status_code==303
    assert delegate.get("/invite",base_url=ORIGIN).status_code==200
    assert "wa.me" in delegate.get("/invite",base_url=ORIGIN).get_data(as_text=True)
    assert delegate.get("/moderation",base_url=ORIGIN).status_code==200
    assert delegate.get("/meetups",base_url=ORIGIN).status_code==200
    assert delegate.post("/meetups",base_url=ORIGIN,data={
        "csrf":get_csrf(delegate),"title":"מפגש מורשה",
        "when":"2027-08-11T20:00","location":"פארק ציבורי"}).status_code==303
    assert delegate.get("/media/"+str(photo["id"]),base_url=ORIGIN).status_code==200
    assert delegate.get("/members",base_url=ORIGIN).status_code==403
    assert delegate.get("/team",base_url=ORIGIN).status_code==403
    assert delegate.get("/dashboard",base_url=ORIGIN).status_code==403
    assert delegate.post("/team",base_url=ORIGIN,data={
        "csrf":get_csrf(delegate),"id":str(member["id"]),"action":"save",
        "can_approve":"yes"}).status_code==403
    # Changes take effect in already active sessions, no stale admin grants.
    revoked=browser.post("/team",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(member["id"]),"action":"revoke"})
    assert revoked.status_code==303
    assert site.sql("SELECT action FROM b2_admin_audit ORDER BY id DESC LIMIT 1",one=True)["action"]=="roles_revoked"
    assert "פעולות ניהול אחרונות" in browser.get("/team",base_url=ORIGIN).get_data(as_text=True)
    assert delegate.get("/invite",base_url=ORIGIN).status_code==403
    assert delegate.get("/moderation",base_url=ORIGIN).status_code==403
    assert delegate.post("/meetups",base_url=ORIGIN,data={
        "csrf":get_csrf(delegate),"title":"מפגש אסור",
        "when":"2027-09-11T20:00"}).status_code==403
    assert delegate.get("/meetups",base_url=ORIGIN).status_code==200
    assert delegate.get("/team",base_url=ORIGIN).status_code==403
    # Owner can cancel a meetup, which rejects further attendance.
    assert browser.post("/meetups/manage",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(event_id),"action":"cancel"}).status_code==303
    assert browser.post("/meetups/rsvp",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(event_id),"decision":"yes"}).status_code==404
    # Owner never appears in delegation list and can't change own permissions.
    assert browser.post("/team",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(admin_id),"action":"revoke"}).status_code==403

    # A revoked author's published audio must become unavailable to other
    # ordinary members, even while its post still has status='published'.
    site.sql("""INSERT INTO b2_users(name,email,passhash,approved)
        VALUES(%s,%s,%s,TRUE)""",
        ("צופה בדיקה","synthetic.viewer@example.test",
         site.hashpw("SyntheticViewerPassword!2026")))
    viewer=site.app.test_client()
    assert viewer.post("/login",base_url=ORIGIN,data={
        "csrf":get_csrf(viewer),"email":"synthetic.viewer@example.test",
        "password":"SyntheticViewerPassword!2026"}).status_code==303
    assert viewer.get("/media/"+str(voice_media["id"]),base_url=ORIGIN).status_code==200
    site.sql("UPDATE b2_users SET approved=FALSE WHERE id=%s",(member["id"],))
    assert viewer.get("/media/"+str(voice_media["id"]),base_url=ORIGIN).status_code==403
    # The moderator can still inspect the evidence for appeals/decisions.
    assert browser.get("/media/"+str(voice_media["id"]),base_url=ORIGIN).status_code==200

    # Conservative zero-cost automated moderator: explicit, explainable,
    # no automatic identity approval or image/audio content moderation.
    assert site.moderate_submission("טקסט", "קצר", "story", [], True)[0]=="pending"
    assert site.moderate_submission("סיפור מסחרי", "קנו עכשיו אצלנו באתר", "story", [], True)[0]=="rejected"
    assert site.moderate_submission("סיפור", "סיפור דוגמה עם פרטי קשר test@example.test "*4,
        "story", [], True)[0]=="pending"
    assert site.moderate_submission("סיפור", "זיכרון נחמד מהפלוגה "*9,
        "voice", [("audio/webm","audio",b"hello")], True)[0]=="pending"
    assert site.moderate_submission("סיפור", "זיכרון נחמד מהפלוגה "*9,
        "story", [], False)[0]=="pending"
    os.environ["BARKAN_AUTO_MODERATION"]="1"
    safe_text=("באותו ערב ישבנו עם החברים בחדר האוכל, סיפרנו בדיחות, "
               "נזכרנו ברגעים מצחיקים מהשירות וצחקנו יחד עד סוף המשמרת. ")
    auto=browser.post("/new",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"rights":"yes","title":"זיכרון משותף מהפלוגה",
        "kind":"story","body":safe_text})
    assert auto.status_code==303,(auto.status_code,auto.get_data(as_text=True)[:300])
    approved=site.sql("""SELECT id,status,moderation_reason,moderation_summary,
                                 moderation_source FROM b2_posts
                    WHERE title=%s ORDER BY id DESC LIMIT 1""",("זיכרון משותף מהפלוגה",),True)
    assert approved["status"]=="published",approved
    assert approved["moderation_summary"] and approved["moderation_source"]=="rules-v1"
    assert "תקציר שנוצר אוטומטית" in browser.get("/my-posts",base_url=ORIGIN).get_data(as_text=True)
    denied=browser.post("/new",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"rights":"yes","title":"הודעה מסחרית",
        "kind":"story","body":"קנו עכשיו מוצר במבצע מיוחד. "*8})
    assert denied.status_code==303
    rejected=site.sql("""SELECT id,status,moderation_reason FROM b2_posts
              WHERE title=%s ORDER BY id DESC LIMIT 1""",("הודעה מסחרית",),True)
    assert rejected["status"]=="rejected" and rejected["moderation_reason"]
    assert "בקשת בדיקה חוזרת" in browser.get("/my-posts",base_url=ORIGIN).get_data(as_text=True)
    assert browser.post("/my-posts/appeal",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(rejected["id"])}).status_code==303
    assert site.sql("SELECT status,appealed FROM b2_posts WHERE id=%s",
        (rejected["id"],),True)=={"status":"pending","appealed":True}
    assert browser.post("/my-posts/appeal",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(rejected["id"])}).status_code==409
    assert site.sql("SELECT COUNT(*) n FROM b2_moderation_events WHERE post_id=%s",
        (rejected["id"],),True)["n"]==2
    # Manual rejection requires an explanation available to the author.
    assert browser.post("/moderation",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(rejected["id"]),
        "action":"reject"}).status_code==400
    assert browser.post("/moderation",base_url=ORIGIN,data={
        "csrf":get_csrf(browser),"id":str(rejected["id"]),
        "action":"reject","reason":"פרסום מסחרי אינו מתאים לארכיון."}).status_code==303
    assert site.sql("SELECT moderation_reason FROM b2_posts WHERE id=%s",
        (rejected["id"],),True)["moderation_reason"]=="פרסום מסחרי אינו מתאים לארכיון."
    os.environ.pop("BARKAN_AUTO_MODERATION",None)

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
  "service_claim":"נובמבר 2003, פלוגה ב, תפקיד נהג מרכבה",
  "email":"manual-pending@example.test","password":"SyntheticOnlyManualPassword!2026","agree":"yes"})
assert r.status_code==202,r.status_code
user=app.sql("SELECT id,approved,email_verification_required FROM b2_users WHERE email=%s",
             ("manual-pending@example.test",),True)
assert user and not user["approved"] and not user["email_verification_required"]
review=app.sql("SELECT membership_status,membership_reason,membership_summary,service_claim FROM b2_users WHERE id=%s",
               (user["id"],),True)
assert review["membership_status"]=="pending"
assert "נובמבר 2003" in review["service_claim"]
assert "חבר הרשמה ידנית" in review["membership_summary"]
assert app.sql("SELECT COUNT(*) AS n FROM b2_tokens WHERE user_id=%s",(user["id"],),True)["n"]==0
c.get("/login",base_url=origin)
with c.session_transaction(base_url=origin) as ses: csrf=ses["csrf"]
assert c.post("/login",base_url=origin,data={"csrf":csrf,
  "email":"manual-pending@example.test","password":"SyntheticOnlyManualPassword!2026"}).status_code==303
assert c.get("/feed",base_url=origin).status_code==403
assert c.get("/voices",base_url=origin).status_code==403
assert c.get("/cohorts",base_url=origin).status_code==403
assert c.get("/dashboard",base_url=origin).status_code==403
response=c.get("/application",base_url=origin)
assert response.status_code==200
assert "ממתין לבדיקה" in response.get_data(as_text=True)
assert "הקוד האישי הבא" in response.get_data(as_text=True)
assert app.sql("SELECT referral_code FROM b2_users WHERE id=%s",(user["id"],),True)["referral_code"]
# Rejection/appeal route is tested with a synthetic state, not a real applicant.
app.sql("UPDATE b2_users SET membership_status='rejected',membership_reason=%s WHERE id=%s",
        ("דרוש מידע נוסף על שנות השירות והמחלקה לצורך אימות.",user["id"]))
response=c.get("/application",base_url=origin)
assert "דרוש מידע נוסף" in response.get_data(as_text=True)
with c.session_transaction(base_url=origin) as ses: csrf=ses["csrf"]
assert c.post("/application",base_url=origin,data={
 "csrf":csrf,"appeal":"שירתתי בפלוגה ב במחזור נובמבר 2003, אוסיף פרטים לאימות"}).status_code==303
assert app.sql("SELECT membership_status,membership_appealed FROM b2_users WHERE id=%s",
               (user["id"],),True)=={"membership_status":"pending","membership_appealed":True}
assert c.post("/application",base_url=origin,data={
 "csrf":csrf,"appeal":"בקשה חוזרת נוספת עם פרטי זיהוי"}).status_code==409
assert c.get("/find",base_url=origin).status_code==403
assert c.get("/new",base_url=origin).status_code==200  # own pending posts only
assert c.get("/inbox",base_url=origin).status_code==403
assert c.get("/photo-review",base_url=origin).status_code==403
assert c.post("/photos/memory",base_url=origin,data={"id":"1","body":"סיפור לא מאושר"}).status_code==403
assert c.get("/meetups",base_url=origin).status_code==403
assert c.post("/photos/self-tag",base_url=origin,data={
  "id":"1","action":"add"}).status_code==403
assert c.post("/meetups/rsvp",base_url=origin,data={"id":"1","decision":"yes"}).status_code==403
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
