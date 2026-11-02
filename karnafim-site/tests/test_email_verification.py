"""Regression for email-only member signup and one-time email confirmation.
All accounts and outbound messages are synthetic. No production database access.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from email_delivery import issue_token,digest_token,delivery_ready

class Cursor:
 def __enter__(self):return self
 def __exit__(self,*a):return False
 def execute(self,*a):return None
 def fetchall(self):return []
class Conn:
 def __enter__(self):return self
 def __exit__(self,*a):return False
 def cursor(self):return Cursor()

def main():
 token,hashed=issue_token()
 assert len(token)>=40 and digest_token(token)==hashed
 # Never mistake 'queued in PostgreSQL' for 'email will actually be sent'.
 # This must stay off until a separate, tested sender is available.
 with patch.dict(os.environ,{"KARNAFIM_MAIL_TRANSPORT":"gmail_queue",
                             "KARNAFIM_GMAIL_QUEUE_ENABLED":"1",
                             "KARNAFIM_GMAIL_DISPATCH_VERIFIED":"0",
                             "DATABASE_URL":"postgresql://offline.invalid"}):
  assert not delivery_ready(), "Gmail queue alone is not a live mail system"
 with patch.dict(os.environ,{"KARNAFIM_MAIL_TRANSPORT":"gmail_queue",
                             "KARNAFIM_GMAIL_QUEUE_ENABLED":"1",
                             "KARNAFIM_GMAIL_DISPATCH_VERIFIED":"1",
                             "DATABASE_URL":"postgresql://offline.invalid"}):
  assert delivery_ready()
 assert digest_token(token[:-1]+"!") is None
 assert digest_token("x") is None
 assert digest_token(issue_token()[0])!=hashed
 env={"SECRET_KEY":"local-email-test-key-not-production",
      "KARNAFIM_MAINTENANCE":"0",
      "KARNAFIM_LOCAL_AUTH_ENABLED":"1",
      "KARNAFIM_SAFETY_RELEASE_APPROVED":"1",
      "KARNAFIM_ALLOW_REGISTRATION":"1",
      "KARNAFIM_RESEND_API_KEY":"test-mocked-only",
      "KARNAFIM_MAIL_FROM":"Community <example@example.test>",
      "DATABASE_URL":"postgresql://offline.invalid"}
 with patch.dict(os.environ,env,clear=True):
  assert delivery_ready()
  import psycopg
  with patch.object(psycopg,"connect",return_value=Conn()):
   import app as site
  assert not site.READ_ONLY_BOOT
  assert "google_identity" not in sys.modules
  member={}
  outstanding={}
  attempts=[]
  deliveries=[]
  def fake_sql(query,params=(),fetch=False):
   if query.startswith("SELECT COUNT(*) AS n FROM login_failures"):
    return [{"n":sum(1 for x in attempts if x==params[0])}]
   if query.startswith("INSERT INTO login_failures"):
    attempts.append(params[0]);return None
   if query.startswith("INSERT INTO members"):
    member.update({"id":12,"name":params[0],"email":params[1],
      "password":params[2],"verification_required":True,"session_version":0,
      "approved":False,"visible":False})
    return [{"id":12}]
   if query.startswith("INSERT INTO email_verification_tokens"):
    outstanding["member_id"],outstanding["digest"]=params[:2]
    return None
   if query.startswith("SELECT id,password,session_version,verification_required FROM members"):
    return [member.copy()] if member and params[0]==member["email"] else []
   if query.startswith("WITH used AS"):
    if outstanding.get("digest")==params[0]:
     member["verification_required"]=False
     outstanding.clear()
     return [{"id":12}]
    return []
   if query.startswith("SELECT * FROM members WHERE id="):
    return [member.copy()] if member else []
   return [] if fetch else None
  site.sql=fake_sql
  site.send_confirmation=lambda address,value: deliveries.append((address,value)) or True
  with site.app.test_client() as client:
   response=client.get("/register",base_url="https://karnafim-community-46.onrender.com")
   assert response.status_code==200
   with client.session_transaction(base_url="https://karnafim-community-46.onrender.com") as sess:
    csrf=sess["csrf"]
   data={"csrf":csrf,"name":"חבר ניסוי","email":"member@example.test",
     "password":"synthetic-Password-42","consent":"on"}
   r=client.post("/register",data=data,base_url="https://karnafim-community-46.onrender.com")
   assert r.status_code==200,(r.status_code,r.get_data(as_text=True)[:200])
   assert member["verification_required"] and len(deliveries)==1
   test_token=deliveries[0][1]
   wrong=client.post("/login",data={"csrf":csrf,"email":member["email"],
     "password":"synthetic-Password-42"},base_url="https://karnafim-community-46.onrender.com")
   assert wrong.status_code==403
   verify=client.get("/verify-email?token="+test_token,base_url="https://karnafim-community-46.onrender.com")
   assert verify.status_code==200 and member["verification_required"]
   assert verify.headers.get("Referrer-Policy")=="no-referrer"
   assert "no-store" in verify.headers.get("Cache-Control","")
   # A second signup with the same email must not falsely claim another message
   # was delivered or generate new tokens; it should offer controlled resend.
   original_sql=site.sql
   def duplicate_sql(query,params=(),fetch=False):
    if query.startswith("INSERT INTO members"):
     raise psycopg.errors.UniqueViolation("duplicate synthetic email")
    return original_sql(query,params,fetch)
   site.sql=duplicate_sql
   duplicate=client.post("/register",data=data,base_url="https://karnafim-community-46.onrender.com")
   assert duplicate.status_code==200
   assert "resend-verification" in duplicate.get_data(as_text=True)
   assert len(deliveries)==1
   site.sql=original_sql
   with client.session_transaction(base_url="https://karnafim-community-46.onrender.com") as sess:
    csrf=sess["csrf"]
   done=client.post("/verify-email",data={"csrf":csrf,"token":test_token},
      base_url="https://karnafim-community-46.onrender.com")
   assert done.status_code==200 and not member["verification_required"]
   reused=client.post("/verify-email",data={"csrf":csrf,"token":test_token},
      base_url="https://karnafim-community-46.onrender.com")
   assert reused.status_code==410
   logged=client.post("/login",data={"csrf":csrf,"email":member["email"],
      "password":"synthetic-Password-42"},base_url="https://karnafim-community-46.onrender.com")
   assert logged.status_code==303
  print("PASS one-use email token, registration, blocked unverified login, verified login, CSRF and zero Google identity integration")

if __name__=="__main__":main()
