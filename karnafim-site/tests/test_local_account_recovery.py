"""Local account recovery: test original PBKDF2 hashes with a synthetic user, never production data."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
BASE="https://karnafim-community-46.onrender.com"

class FakeCursor:
 def __enter__(self):return self
 def __exit__(self,*args):return False
 def execute(self,query,params=()):pass
 def fetchall(self):return []
class FakeConnection:
 def __enter__(self):return self
 def __exit__(self,*args):return False
 def cursor(self):return FakeCursor()

def main():
 env={
  "SECRET_KEY":"local-login-tests-no-production-secret",
  "DATABASE_URL":"postgresql://fake/db",
  "KARNAFIM_MAINTENANCE":"0",
  "KARNAFIM_SAFETY_RELEASE_APPROVED":"1",
  "KARNAFIM_LOCAL_AUTH_ENABLED":"1",
  "KARNAFIM_ALLOW_REGISTRATION":"0",
 }
 with patch.dict(os.environ,env,clear=True):
  import psycopg
  with patch.object(psycopg,"connect",return_value=FakeConnection()):
   import app as site
  assert not site.READ_ONLY_BOOT and site.AUTH_READY
  original_password="synthetic-test-only-Password-42"
  account={
   "id":7,"name":"Test Veteran","email":"sample@example.test",
   "password":site.hashpw(original_password),"session_version":0,"verification_required":False,
   "approved":True,"visible":False,"nickname":"",
   "company":"ב","role":"","about":"","service_start":"",
   "service_end":"","facebook_url":"","instagram_url":"","linkedin_url":""
  }
  attempts=[]
  def fake_sql(query,params=(),fetch=False):
   if query.startswith("SELECT COUNT(*) AS n FROM login_failures"):
    count=sum(1 for f in attempts if f==params[0])
    return [{"n":count}]
   if query.startswith("INSERT INTO login_failures"):
    attempts.append(params[0]);return None
   if query.startswith("SELECT id,password,session_version,verification_required FROM members WHERE lower(email)="):
    return [account.copy()] if params[0]==account["email"] else []
   if query.startswith("SELECT * FROM members WHERE id="):
    return [account.copy()] if params[0]==account["id"] else []
   if query.startswith("UPDATE members SET password="):
    if params[1]==account["id"] and params[2]==account["password"]:
     account["password"]=params[0]
     account["session_version"]+=1
    return None
   if fetch:return []
   return None
  site.sql=fake_sql
  with site.app.test_client() as client:
   login=client.get("/login",base_url=BASE)
   assert login.status_code==200
   assert 'name="password"' in login.get_data(as_text=True)
   assert 'name="csrf"' in login.get_data(as_text=True)
   # Local credentials must not load Google identity resources on the login form.
   login_csp=login.headers.get("Content-Security-Policy","")
   assert "default-src 'none'" in login_csp and "form-action 'self'" in login_csp
   assert "accounts.google.com" not in login_csp
   assert "unsafe-eval" not in login_csp
   assert "script-src 'sha256-" in login_csp
   assert client.get("/register",base_url=BASE).status_code==503
   assert client.get("/find",base_url=BASE).status_code==410
   assert client.get("/auth/google/start",base_url=BASE).status_code==404
   assert client.post("/login",base_url=BASE,data={"email":account["email"],"password":original_password}).status_code==403
   with client.session_transaction(base_url=BASE) as sess: csrf=sess["csrf"]
   wrong=client.post("/login",base_url=BASE,data={"csrf":csrf,"email":account["email"],"password":"incorrect"})
   assert wrong.status_code==401
   assert site.app.config["MAX_CONTENT_LENGTH"] >= 32*1024*1024
   live_status=client.get("/status",base_url=BASE)
   assert live_status.status_code==200
   assert "דוא״ל וסיסמה אישית" in live_status.get_data(as_text=True)
   assert "התחברות Google עדיין אינה זמינה" not in live_status.get_data(as_text=True)
   # Eight failures for an unrelated account must not lock out this member.
   for _ in range(8):
    unlisted=client.post("/login",base_url=BASE,data={"csrf":csrf,"email":"not-listed@example.test","password":"incorrect"})
    assert unlisted.status_code in (401,429)
   correct=client.post("/login",base_url=BASE,data={"csrf":csrf,"email":account["email"],"password":original_password})
   assert correct.status_code==303,(correct.status_code,correct.get_data(as_text=True)[:150])
   with client.session_transaction(base_url=BASE) as sess:
    assert sess["uid"]==7 and sess["auth_method"]=="local"
    assert sess["credential_version"]==0
   update_form=client.get("/password",base_url=BASE)
   assert update_form.status_code==200
   with client.session_transaction(base_url=BASE) as sess: csrf2=sess["csrf"]
   new_password="synthetic-new-Password-99"
   change=client.post("/password",base_url=BASE,data={"csrf":csrf2,"old":original_password,"new":new_password})
   assert change.status_code==200 and account["session_version"]==1
   assert site.verify(new_password,account["password"])
   assert not site.verify(original_password,account["password"])
   with client.session_transaction(base_url=BASE) as sess:
    assert "uid" not in sess
    sess["uid"]=7;sess["auth_method"]="local";sess["credential_version"]=0
   client.get("/login",base_url=BASE)
   with client.session_transaction(base_url=BASE) as sess:assert "uid" not in sess
  print("PASS local login, CSRF, wrong password, account hash reuse, password change, session revocation and disabled signup")

if __name__=="__main__":main()
