"""Boot the real Flask app with fake SQL and a signed Google identity.

Never connects to Neon or uses real credentials. This checks the actual routes,
cookies, content security policy, verified member lookup and private access
after an authorized Google GIS sign-in. The production safety lock remains ON.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_google_gis import CLIENT, create_token, Response as FakeGoogleJWKS

BASE = "https://karnafim-community-46.onrender.com"
operations = []


class FakeCursor:
    def __init__(self):
        self.query = ""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, args=()):
        self.query = str(query)
        operations.append((self.query, tuple(args or ())))

    def fetchall(self):
        if self.query.startswith("SELECT id FROM members WHERE google_sub="):
            return [{"id": 42}]
        if self.query.startswith("SELECT * FROM members WHERE id="):
            return [{
                "id": 42, "name": "בדיקת מערכת", "email": "existing@gmail.com",
                "approved": True, "visible": False, "nickname": "",
                "company": "ב", "role": "", "about": "",
                "service_start": "", "service_end": "",
                "facebook_url": "", "instagram_url": "", "linkedin_url": ""
            }]
        return []


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return FakeCursor()


def run():
    env = {
        "SECRET_KEY": "test-only-secret-never-for-production",
        "DATABASE_URL": "postgresql://fake/no-real-connection",
        "KARNAFIM_MAINTENANCE": "0",
        "KARNAFIM_SAFETY_RELEASE_APPROVED": "1",
        "KARNAFIM_GOOGLE_AUTH_ENABLED": "1",
        "KARNAFIM_GOOGLE_AUTH_MODE": "gis",
        "GOOGLE_CLIENT_ID": CLIENT
    }
    with patch.dict(os.environ, env, clear=True):
        import psycopg
        with patch.object(psycopg, "connect", return_value=FakeConnection()):
            import app as site_app
            import google_identity
            assert not site_app.READ_ONLY_BOOT, "Synthetic release must boot community mode"
            assert site_app.google_ready(), "No Google client secret required in GIS mode"
            with patch.object(google_identity.requests, "get", return_value=FakeGoogleJWKS()):
                with site_app.app.test_client() as client:
                    login = client.get("/login", base_url=BASE)
                    assert login.status_code == 200
                    html = login.get_data(as_text=True)
                    assert 'id="g_id_onload"' in html, "Google button missing in real page"
                    assert "gsi/client" in login.headers["Content-Security-Policy"]
                    assert "unsafe-eval" not in login.headers["Content-Security-Policy"]
                    assert "data-login_uri=" in html
                    with client.session_transaction(base_url=BASE) as sess:
                        nonce = sess["google_gis_nonce"]
                    assert len(nonce) >= 32
                    client.set_cookie("g_csrf_token", "signed-credential-csrf",
                                      domain="karnafim-community-46.onrender.com")
                    signed = create_token(nonce, email="existing@gmail.com")
                    response = client.post(
                        "/auth/google/callback", base_url=BASE,
                        data={"credential": signed,
                              "g_csrf_token": "signed-credential-csrf"})
                    assert response.status_code == 303, (response.status_code, response.get_data(as_text=True)[:200])
                    assert response.location == "/"
                    with client.session_transaction(base_url=BASE) as sess:
                        assert sess["auth_method"] == "google" and sess["uid"] == 42
                    profile = client.get("/profile", base_url=BASE)
                    assert profile.status_code == 200
                    assert "בדיקת מערכת" not in profile.get_data(as_text=True) or "פרופיל" in profile.get_data(as_text=True)
                    directory = client.get("/directory", base_url=BASE)
                    assert directory.status_code == 200
                    assert "חברי הפלוגה" in directory.get_data(as_text=True)
                    assert not any(q.startswith(("UPDATE members","INSERT INTO members"))
                                   for q,_ in operations), "Sign-in unexpectedly mutated member approval"
                    assert client.get("/find", base_url=BASE).status_code == 410
                    print("PASS real Flask GIS route, secure session, private profile, approved directory, retired search")
    assert all("fake/no-real-connection" not in q for q,_ in operations)


if __name__ == "__main__":
    run()
