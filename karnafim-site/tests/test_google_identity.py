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
        dict(good,azp="other-client"),
        dict(good,aud=["sample-client-id.apps.googleusercontent.com","other"],azp="other-client"),
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
        assert auth.configuration_checks()["callback"] == "https://karnafim-community-46.onrender.com/auth/google/callback"
    with patch.dict(os.environ,{
        "KARNAFIM_GOOGLE_AUTH_ENABLED":"1",
        "GOOGLE_CLIENT_ID":"1234567-sample.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET":"test-only-secret-not-real",
    },clear=True):
        assert auth.enabled(),"Configured Google sign-in should pass readiness"
        assert auth.configuration_checks()["valid_client_id"]
        # Real Google client IDs must be accepted; a double-escaped dot would reject them.
        os.environ["GOOGLE_CLIENT_ID"] = "761981450509-3bvp5njfhghvrsitipl0vcde0g92q9h.apps.googleusercontent.com"
        assert auth.enabled(),"The project's real Google client ID format must be valid"
        for invalid in ("761981450509-3bvp5njfhghvrsitipl0vcde0g92q9hXappsXgoogleusercontentXcom",
                        "https://accounts.google.com",
                        "761981450509-3bvp5njfhghvrsitipl0vcde0g92q9h.apps.googleusercontent.com.evil.example"):
            os.environ["GOOGLE_CLIENT_ID"] = invalid
            assert not auth.configuration_checks()["valid_client_id"], "Invalid Google client ID accepted"

    with patch.dict(os.environ,{
        "KARNAFIM_GOOGLE_AUTH_ENABLED":"1",
        "GOOGLE_CLIENT_ID":"not-a-real-client-id",
        "GOOGLE_CLIENT_SECRET":"placeholder",
    },clear=True):
        assert not auth.enabled(),"Dummy OAuth credentials must never activate sign-in"
    with patch.dict(os.environ,{},clear=True):
        assert not auth.enabled(),"OAuth must stay disabled without credentials"
        app=Flask(__name__)
        app.secret_key="test-secret"
        def view(t,b):return b
        auth.install_google_login(app,lambda *a,**k:[],view,lambda:None,lambda x:x,str)
        c=app.test_client()
        assert c.get("/auth/google/start").status_code==503
        assert c.get("/auth/google/consent").status_code==503
        assert c.get("/auth/google/callback").status_code==503
    # The site now supports two explicitly separated authentication methods.
    # Local passwords are allowed only after the independent safety release.
    main_app=(Path(__file__).resolve().parents[1]/"app.py").read_text("utf-8")
    login=main_app.split('@app.route("/login",',1)[1].split('@app.route("/logout",',1)[0]
    assert 'if AUTH_METHOD=="local":' in login
    assert 'session["auth_method"]="local"' in login
    assert 'if request.method=="POST":abort(405)' in login
    assert 'KARNAFIM_LOCAL_AUTH_ENABLED' in main_app
    assert 'SAFETY_RELEASE_APPROVED and AUTH_READY' in main_app
    assert 'session.get("auth_method")!=AUTH_METHOD' in main_app
    print("PASS Google OIDC identity validation, separate gated local login and no unauthorized linking")

if __name__=="__main__":main()
