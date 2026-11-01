"""Offline integration checks: Google login must preserve approval and never leak
or silently create an account before verified identity and consent.
No external requests, credentials, or production database operations.
"""
from pathlib import Path
import os
import sys
from unittest.mock import patch

from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import google_identity as identity


CLIENT = "761981450509-3bvp5njfhghvrsitipl0vcde0g92q9h.apps.googleusercontent.com"


def run_login(userinfo, existing=None):
    calls = []
    class GoogleClient:
        def authorize_access_token(self):
            return {"userinfo": userinfo}
    class OfflineOAuth:
        def __init__(self, app):
            self.google = GoogleClient()
        def register(self, **kwargs):
            return self.google

    def database(query, values=(), fetch=False):
        calls.append((query, values))
        if query.startswith("SELECT id FROM members WHERE google_sub="):
            return []
        if query.startswith("SELECT id,google_sub FROM members WHERE email="):
            return [existing] if existing is not None else []
        if query.startswith("UPDATE members SET google_sub="):
            assert existing is not None
            assert existing["google_sub"] is None
            assert values[1] == existing["id"]
            assert values[0] == userinfo["sub"]
            return [{"id": existing["id"]}]
        raise AssertionError("Unexpected DB access: " + query[:90])

    flask_app = Flask(__name__)
    flask_app.secret_key = "test-key-no-production-use"
    env = {
        "GOOGLE_CLIENT_ID": CLIENT,
        "GOOGLE_CLIENT_SECRET": "mock-client-secret-not-valid",
        "KARNAFIM_GOOGLE_AUTH_ENABLED": "1",
    }
    with patch.dict(os.environ, env), patch.object(identity, "OAuth", OfflineOAuth):
        identity.install_google_login(flask_app, database, lambda t, body: body,
                                      lambda: None, lambda s: s, lambda s: s)
        with flask_app.test_client() as client:
            resp = client.get("/auth/google/callback", follow_redirects=False)
            with client.session_transaction() as sess:
                state = dict(sess)
    return resp, state, calls


def test():
    verified = {
        "iss": "https://accounts.google.com", "aud": CLIENT,
        "sub": "10294039249929301", "email": "veteran@gmail.com",
        "email_verified": True, "name": "Veteran",
    }
    old_member = {"id": 42, "google_sub": None}

    # An existing approved member is linked by Google-verified Gmail without
    # changing approval or visible flags, without INSERTing a duplicate member.
    resp, state, calls = run_login(verified, old_member)
    assert resp.status_code == 303 and resp.location == "/"
    assert state["uid"] == 42 and state["auth_method"] == "google"
    assert sum("UPDATE members SET google_sub=" in q for q, _ in calls) == 1
    assert not any("INSERT" in q or "SET approved" in q for q, _ in calls)

    # A verified Google identity with a nonauthoritative domain must not
    # silently claim the legacy account sharing that email.
    other = dict(verified, email="person@example.org", hd=None)
    resp, state, calls = run_login(other, old_member)
    assert resp.status_code == 409 and "uid" not in state
    assert not any("UPDATE" in q or "INSERT" in q for q, _ in calls)

    # A token with an unverified email is never granted a session or DB update.
    unverified = dict(verified, email_verified=False)
    resp, state, calls = run_login(unverified, old_member)
    assert resp.status_code == 401 and "uid" not in state
    assert calls == []

    # A brand new Google identity must explicitly consent BEFORE account
    # creation; the callback only stores temporary identity in signed session.
    resp, state, calls = run_login(verified, None)
    assert resp.status_code == 303 and resp.location == "/auth/google/consent"
    assert "pending_google_signup" in state and "uid" not in state
    assert not any("INSERT" in q or "UPDATE" in q for q, _ in calls)

    print("PASS legacy Gmail account link, non-Gmail impersonation defense, "
          "unverified email rejection and explicit new-account consent")


if __name__ == "__main__":
    test()
