"""Isolated media authorization checks; no member database or live credentials."""
import os
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.pop("DATABASE_URL",None)
os.environ.pop("BARKAN_ADMIN_EMAIL",None)
import app as site

original_auth=site.PUBLIC_AUTH
original_current=site.current
original_sql=site.sql
try:
    site.PUBLIC_AUTH=True
    user={"id":22,"email":"member@example.invalid","approved":True,"role":"member"}
    site.current=lambda: user
    record={"id":51,"post_id":10,"owner":11,"recipient":None,
            "post_status":"published","author_approved":False,
            "mime":"image/jpeg","body":b"test"}
    site.sql=lambda *args,**kwargs: record
    client=site.app.test_client()
    with client.session_transaction() as session:
        session["uid"]=22
    base="https://karnafim-barkan-46.onrender.com"
    res=client.get("/media/51",base_url=base)
    assert res.status_code==403, res.status_code
    record["author_approved"]=True
    res=client.get("/media/51",base_url=base)
    assert res.status_code==200, res.status_code
    record["post_status"]="pending"
    res=client.get("/media/51",base_url=base)
    assert res.status_code==403, res.status_code
    user["role"]="moderator"
    res=client.get("/media/51",base_url=base)
    assert res.status_code==200, res.status_code
    user["role"]="member"
    user["approved"]=False
    res=client.get("/media/51",base_url=base)
    assert res.status_code==403, res.status_code
finally:
    site.sql=original_sql
    site.current=original_current
    site.PUBLIC_AUTH=original_auth
print("PASS: media visibility follows membership and moderation privileges")
