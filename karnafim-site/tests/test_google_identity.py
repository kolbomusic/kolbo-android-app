"""Security tests for migration from legacy site-passwords to Google OIDC.

No real Google credentials, web requests or production database interactions.
"""
from pathlib import Path
import os
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import google_identity as auth
from flask import Flask

def main():
    good={"iss":"https://accounts.google.com",
          "aud":"sample-client-id.apps.googleusercontent.com",
          "sub":"10294039249929301","email":"veteran@gmail.com",
          "email_verified":True,"name":"בדיקה"}
    a=auth.validate_google_identity(good,"sample-client-id.apps.googleusercontent.com")
    assert a["sub"]==good["sub"] and a["email"]=="veteran@gmail.com"
    for bad in (
        dict(good,email_verified=False),
        dict(good,iss="https://unknown.example"),
        dict(good,aud="other-client"),
        dict(good,sub=""),
        dict(good,email="not-an-email"),
    ):
        try:auth.validate_google_identity(bad,good["aud"])
        except ValueError:pass
        else:raise AssertionError("Unsafe ID token was accepted")
    assert auth.authoritative_email("veteran@gmail.com",None)
    assert auth.authoritative_email("name@company.org","company.org")
    assert not auth.authoritative_email("name@company.org",None)
    assert not auth.authoritative_email("name@other.org","company.org")
    with patch.dict(os.environ,{},clear=True):
        assert not auth.enabled(),"OAuth must be opt-in and disabled by default"
        app=Flask(__name__)
        app.secret_key="test-secret"
        def view(t,b):return b
        auth.install_google_login(app,lambda *a,**k:[],view,lambda:None,lambda x:x,str)
        c=app.test_client()
        assert c.get("/auth/google/start").status_code==503
        assert c.get("/auth/google/consent").status_code==503
        assert c.get("/auth/google/callback").status_code==503
    # Site routes must not collect or accept local passwords after maintenance.
    main_app=(Path(__file__).resolve().parents[1]/"app.py").read_text("utf-8")
    login=main_app.split('@app.route("/login",',1)[1].split('@app.route("/logout",',1)[0]
    signup=main_app.split('@app.route("/register",',1)[1].split('@app.route("/login",',1)[0]
    assert 'request.form.get("password"' not in login
    assert 'field("password"' not in login+signup
    assert 'request.method=="POST":abort(405)' in signup
    assert 'request.method=="POST":abort(405)' in login
    assert 'session.get("auth_method")!="google"' in main_app
    print("PASS Google OIDC identity validation, no unauthorized linking, opt-in startup and no local-password forms")

if __name__=="__main__":main()
