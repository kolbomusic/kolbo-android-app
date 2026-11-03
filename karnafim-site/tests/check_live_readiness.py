"""Safe read-only live checks of Barkan's sole public origin.

Does not transmit credentials, member data, email addresses, or tokens.
"""
import json
import ssl
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE="https://karnafim-community-46.onrender.com"
CONTEXT=ssl.create_default_context()

def fetch(path):
    request=Request(BASE+path,headers={"User-Agent":"BarkanReadOnlyHealthCheck/1.0",
                                        "Accept":"application/json,text/html"})
    try:
        with urlopen(request,timeout=15,context=CONTEXT) as r:
            return r.status, dict(r.headers), r.read(20000)
    except HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read(20000)

def check():
    status,headers,body=fetch("/health")
    assert status==200,("health",status)
    health=json.loads(body)
    assert health["generation"]=="new-build",health
    assert health["auth_enabled"] is False,health
    assert health["signup_enabled"] is False,health

    status,headers,body=fetch("/ready")
    assert status==200,("ready",status,body[:100].decode("utf-8","replace"))
    ready=json.loads(body)
    assert ready["status"]=="ready" and ready["database"]=="available",ready
    assert ready["member_portal"]=="closed" and ready["signup"]=="closed",ready

    for path in ("/login","/signup"):
        status,headers,body=fetch(path)
        assert status==503,(path,status)
        assert b'type="password"' not in body,(path,"exposed password form")
    for path in ("/","/memorial","/status"):
        status,headers,body=fetch(path)
        assert status==200,(path,status)
        csp=headers.get("Content-Security-Policy","")
        assert "default-src 'none'" in csp,(path,"missing CSP")
        assert b'lang="he" dir="rtl"' in body,(path,"RTL missing")
    print("PASS: live original origin and database healthy, auth/signup blocked, public RTL routes intact")

if __name__=="__main__":
    for attempt in range(1,9):
        try:
            check()
            sys.exit(0)
        except (AssertionError, URLError, TimeoutError, ValueError) as exc:
            print("Read-only verification attempt",attempt,"not ready:",str(exc)[:200],flush=True)
            if attempt==8:
                raise
            time.sleep(12)
