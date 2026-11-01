"""Offline, signed-token Google Identity Services regression (no real Google/Neon)."""
import os
import sys
import time
import hmac
from pathlib import Path
from unittest.mock import patch
from flask import Flask, session, request, abort
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from authlib.jose import JsonWebKey, JsonWebToken

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import google_identity as google

CLIENT = "761981450509-3bvp5njfhghvrsitipl0vcde0g92q9h.apps.googleusercontent.com"
PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_PEM = PRIVATE.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
PRIVATE_PEM = PRIVATE.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
PUB = JsonWebKey.import_key(PUBLIC_PEM, {"kid": "test-google-key"})
TOKEN = JsonWebToken(["RS256"])

class Response:
    status_code = 200
    headers = {"Cache-Control": "public, max-age=180"}
    content = b'{"keys":[]}'
    def raise_for_status(self):
        return None
    def json(self):
        return {"keys": [PUB.as_dict()]}

def create_token(session_nonce, **updates):
    now = int(time.time())
    payload = dict(iss="https://accounts.google.com", aud=CLIENT,
                   sub="113301133011330", email="existing@gmail.com",
                   email_verified=True, iat=now, exp=now+2400, nonce=session_nonce)
    payload.update(updates)
    token = TOKEN.encode({"alg": "RS256", "kid": "test-google-key"}, payload, PRIVATE_PEM)
    return token.decode("ascii") if isinstance(token, bytes) else token

def run():
    env = dict(KARNAFIM_GOOGLE_AUTH_ENABLED="1",
               KARNAFIM_GOOGLE_AUTH_MODE="gis", GOOGLE_CLIENT_ID=CLIENT)
    with patch.dict(os.environ, env, clear=True):
        assert google.enabled(), "GIS should not require a client secret"
        assert google.auth_mode() == "gis"
        app = Flask("karnafim_gis_test")
        app.secret_key = "offline-test-key"
        db = []
        def sql(query, params=(), fetch=False):
            db.append((query, params))
            if query.startswith("SELECT id FROM members WHERE google_sub"):
                return [{"id": 42}]
            raise AssertionError("Unexpected database access")
        def guard():
            expected = session.get("csrf", "")
            supplied = request.form.get("csrf", "")
            if not expected or not supplied or not hmac.compare_digest(expected, supplied):
                abort(403)
        google.install_google_login(app, sql, lambda t,b:b, guard, lambda x:x, str)
        @app.get("/login")
        def login():
            return google.gis_button_html()

        with patch.object(google.requests, "get", return_value=Response()) as fetch:
            with app.test_client() as client:
                page = client.get("/login")
                assert page.status_code == 200
                html = page.get_data(as_text=True)
                assert 'id="g_id_onload"' in html
                assert google.CALLBACK in html
                assert 'gsi/client' in html
                assert 'data-callback="karnafimGoogleResponse"' in html
                assert 'id="karnafim-gis-form"' in html
                assert 'name="csrf"' in html
                assert 'data-login_uri=' not in html
                assert '<script>' + google.GIS_CALLBACK_JS + '</script>' in html
                with client.session_transaction() as sess:
                    nonce, csrf = sess["google_gis_nonce"], sess["csrf"]
                signed = create_token(nonce)

                assert client.post("/auth/google/callback", data={
                    "credential":signed}).status_code == 403, "Missing same-site CSRF"
                invalid_csrf = client.post("/auth/google/callback", data={
                    "csrf":"different","credential":signed})
                assert invalid_csrf.status_code == 403
                assert not db and fetch.call_count == 0
                # CSRF rejection happens before the one-time nonce is consumed.
                with client.session_transaction() as sess:
                    assert sess["google_gis_nonce"] == nonce
                ok = client.post("/auth/google/callback", data={
                    "csrf":csrf,"credential":signed})
                assert ok.status_code == 303 and ok.location == "/", (ok.status_code,ok.location)
                with client.session_transaction() as sess:
                    assert sess["uid"] == 42 and sess["auth_method"] == "google"
                    assert "google_gis_nonce" not in sess
                assert len(db) == 1
                # The signed nonce can never be replayed after first login.
                assert client.post("/auth/google/callback", data={
                    "csrf":csrf,"credential":signed}).status_code == 403

                for token_kwargs in [
                    {"aud":"attacker-client.apps.googleusercontent.com"},
                    {"email_verified":False},
                    {"iss":"https://attacker.example"},
                    {"iat":int(time.time())-4000, "exp":int(time.time())-600},
                    {"nonce":"not-the-issued-session-nonce"},
                ]:
                    client.get("/login")
                    with client.session_transaction() as sess:
                        new_nonce, new_csrf = sess["google_gis_nonce"], sess["csrf"]
                    new_signed = create_token(new_nonce, **token_kwargs)
                    failed = client.post("/auth/google/callback", data={
                        "csrf":new_csrf,"credential":new_signed})
                    assert failed.status_code == 401, (token_kwargs, failed.status_code)
                client.get("/login")
                with client.session_transaction() as sess:
                    final_csrf = sess["csrf"]
                bad_signed = create_token("unrelated-nonce")
                forged = bad_signed[:30] + ("A" if bad_signed[30] != "A" else "B") + bad_signed[31:]
                assert client.post("/auth/google/callback", data={
                    "csrf":final_csrf,"credential":forged}).status_code == 401
        assert len(db) == 1, "No rejected token should read the DB"
        assert fetch.call_count == 1, "Google JWKS must be cached across signature checks"
        assert google._GOOGLE_JWKS_CACHE["expires_at"] > time.monotonic()
        print("PASS GIS signed RS256 verification, cached Google JWKS, nonce, CSRF, replay, audience, issuer, expiry")

    with patch.dict(os.environ, {"KARNAFIM_GOOGLE_AUTH_ENABLED":"1",
                                  "KARNAFIM_GOOGLE_AUTH_MODE":"oauth",
                                  "GOOGLE_CLIENT_ID":CLIENT},clear=True):
        assert not google.enabled(), "Classic confidential OAuth still needs client secret"
        assert google.gis_button_html() == ""

if __name__=="__main__":
    run()
