"""Offline regression tests for member-created stories, events and photo albums.
All user accounts and DB writes are faked: no production data is changed.
"""
import html
import io
import os
import sys
from pathlib import Path
from unittest.mock import patch
from werkzeug.datastructures import MultiDict
from flask import Flask, session, abort
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import community_portal

records=[]
class Cursor:
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,statement,params=None):
        self.statement=statement
        records.append((statement,params))
    def fetchone(self):
        if "INSERT INTO community_posts" in self.statement:return (1001,)
        if "SELECT COALESCE" in self.statement:return (0,)
        return (1,)
class Connection:
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def cursor(self):return Cursor()
def sql(query,params=(),fetch=False):
    if not fetch:return None
    # The upload validation reads DB-backed storage quotas before the write.
    # The fake DB must return the same row shape as the real SELECT SUM().
    if "SELECT COALESCE(SUM(length),0)" in query:
        return [{"n":0}]
    return []
def make_image(kind="JPEG"):
    out=io.BytesIO()
    image=Image.new("RGB",(80,60),(120,160,110))
    kw={}
    if kind=="JPEG":
        exif=Image.Exif()
        exif[270]="EXIF_SECRET_SHOULD_DISAPPEAR"
        kw["exif"]=exif
    image.save(out,kind,**kw)
    out.seek(0)
    return out
def setup():
    app=Flask("karnafim_publishing_tests")
    app.secret_key="test-only-secret"
    def current_user():
        return {"id":42,"approved":True,"name":"חבר בדיקה"} if session.get("uid")==42 else None
    community_portal.install(
        app,sql,
        lambda title,markup:markup,
        current_user,
        lambda u:bool(u and u["id"]==42),
        lambda:None,
        lambda content:content,
        lambda v:html.escape(str(v or ""),quote=True),
    )
    return app
def expect(status,result,marker=""):
    assert result.status_code==status,(result.status_code,result.get_data(as_text=True)[:1000])
    assert not marker or marker in result.get_data(as_text=True),marker
def test():
    os.environ["DATABASE_URL"]="postgresql://unreachable.invalid/not-used"
    app=setup()
    client=app.test_client()
    resp=client.get("/new-post")
    assert resp.status_code==303 and "/login?next=/new-post" in resp.headers["Location"]
    unauthed=client.get("/my-posts")
    assert unauthed.status_code==303 and "/login?next=/my-posts" in unauthed.headers["Location"]
    unauthed_chat=client.get("/chats")
    assert unauthed_chat.status_code==303 and "/login?next=/chats" in unauthed_chat.headers["Location"]
    with client.session_transaction() as sess:sess["uid"]=42
    expect(200,client.get("/new-post"),'name="attachments" multiple')
    expect(200,client.get("/my-posts"),"הפרסומים שלי")
    records.clear()
    data=MultiDict([
      ("post_type","photo"),("title","טנק מהשירות"),("body","שיתוף של התמונות"),("rights","on"),("ai_consent","on"),
      ("attachments",(make_image("JPEG"),"1.jpg","image/jpeg")),
      ("attachments",(make_image("PNG"),"2.png","image/png")),
    ])
    with patch.object(community_portal.psycopg,"connect",lambda *a,**k:Connection()):
        res=client.post("/new-post",data=data,content_type="multipart/form-data")
    assert res.status_code==303,res.status_code
    assert res.headers["Location"].endswith("/my-posts?submitted=1")
    post=[x for x in records if x[0].startswith("INSERT INTO community_posts")]
    media=[x for x in records if x[0].startswith("INSERT INTO community_media")]
    assert len(post)==1 and len(media)==2,(len(post),len(media))
    for statement,params in media:
        assert params[2]=="image/jpeg" and params[3]=="image"
        payload=params[5]
        assert payload[:3]==b"\xff\xd8\xff"
        assert b"EXIF_SECRET_SHOULD_DISAPPEAR" not in payload
    records.clear()
    form={"post_type":"event","title":"מפגש מחזור","body":"נפגשים לחידוש קשר","event_date":"2026-07-14","event_place":"רחובות","rights":"on","ai_consent":"on"}
    with patch.object(community_portal.psycopg,"connect",lambda *a,**k:Connection()):
        expect(303,client.post("/new-post",data=form))
    insert=[x for x in records if x[0].startswith("INSERT INTO community_posts")]
    assert len(insert)==1
    assert insert[0][1][4]=="event" and insert[0][1][5].isoformat()=="2026-07-14" and insert[0][1][6]=="רחובות"
    before=len(records)
    bad=MultiDict([("post_type","story"),("title","סיפור"),("body","כמה משפטים על השירות"),("rights","on"),("ai_consent","on"),("attachments",(io.BytesIO(b"GIF89a"+b"\x00"*40),"bad.gif","image/gif"))])
    expect(400,client.post("/new-post",data=bad,content_type="multipart/form-data"))
    assert len(records)==before,"An invalid file must not persist a post"
    extra=[("post_type","photo"),("title","גלריה"),("body",""),("rights","on"),("ai_consent","on")]
    extra.extend(("attachments",(make_image(),"pic%d.jpg"%n,"image/jpeg")) for n in range(5))
    expect(400,client.post("/new-post",data=MultiDict(extra),content_type="multipart/form-data"))
    assert len(records)==before,"Too many files should not write anything"
    # No consent to external AI processing must stop even before persistence.
    no_consent={"post_type":"story","title":"שלום","body":"סיפור שירות","rights":"on"}
    expect(400,client.post("/new-post",data=no_consent))
    assert len(records)==before,"Consent must precede storing anything"
    # Mock an AI response; ensure low-risk content becomes visible automatically.
    records.clear()
    safe={"post_type":"story","title":"יום בבסיס","body":"יום מצחיק עם הטנק בשטח האימונים","rights":"on","ai_consent":"on"}
    from moderation_engine import Verdict
    with patch.object(community_portal,"moderate",return_value=Verdict("approved","סיווג בטוח","model-test",True)),patch.object(community_portal.psycopg,"connect",lambda *a,**k:Connection()):
        approved_result=client.post("/new-post",data=safe)
    assert approved_result.status_code==303
    assert approved_result.headers["Location"].endswith("?auto=1")
    saved=[x for x in records if x[0].startswith("INSERT INTO community_posts")]
    assert saved[0][1][7] is True and saved[0][1][8]=="approved","Auto approved text must publish"
    expect(200,client.get("/community/moderation"),"אישור סיפורים")
    print("PASS: permissions, multi-image moderation, EXIF stripping, events, invalid files, consent, fail-closed pending, AI auto-approval, moderation")
if __name__=="__main__":test()
