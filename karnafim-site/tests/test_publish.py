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
    if fetch:return []
    return None
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
    expect(403,client.get("/new-post"))
    expect(403,client.get("/my-posts"))
    with client.session_transaction() as sess:sess["uid"]=42
    expect(200,client.get("/new-post"),'name="attachments" multiple')
    expect(200,client.get("/my-posts"),"הפרסומים שלי")
    records.clear()
    data=MultiDict([
      ("post_type","photo"),("title","טנק מהשירות"),("body","שיתוף של התמונות"),("rights","on"),
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
        assert params[3]=="image/jpeg" and params[4]=="image"
        payload=params[6]
        assert payload[:3]==b"\xff\xd8\xff"
        assert b"EXIF_SECRET_SHOULD_DISAPPEAR" not in payload
    records.clear()
    form={"post_type":"event","title":"מפגש מחזור","body":"נפגשים לחידוש קשר","event_date":"2026-07-14","event_place":"רחובות","rights":"on"}
    with patch.object(community_portal.psycopg,"connect",lambda *a,**k:Connection()):
        expect(303,client.post("/new-post",data=form))
    insert=[x for x in records if x[0].startswith("INSERT INTO community_posts")]
    assert len(insert)==1
    assert insert[0][1][4]=="event" and insert[0][1][5].isoformat()=="2026-07-14" and insert[0][1][6]=="רחובות"
    before=len(records)
    bad=MultiDict([("post_type","story"),("title","סיפור"),("body","כמה משפטים על השירות"),("rights","on"),("attachments",(io.BytesIO(b"GIF89a"+b"\x00"*40),"bad.gif","image/gif"))])
    expect(400,client.post("/new-post",data=bad,content_type="multipart/form-data"))
    assert len(records)==before,"An invalid file must not persist a post"
    extra=[("post_type","photo"),("title","גלריה"),("body",""),("rights","on")]
    extra.extend(("attachments",(make_image(),"pic%d.jpg"%n,"image/jpeg")) for n in range(5))
    expect(400,client.post("/new-post",data=MultiDict(extra),content_type="multipart/form-data"))
    assert len(records)==before,"Too many files should not write anything"
    expect(200,client.get("/community/moderation"),"אישור סיפורים")
    print("PASS 9 tests: access control, composer, private list, multi-image upload, EXIF stripping, atomic insertion, event metadata, invalid type, file-count limit and moderation page")
if __name__=="__main__":test()
