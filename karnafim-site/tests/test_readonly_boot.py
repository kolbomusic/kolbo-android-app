"""Regression: during a Google Safe Browsing incident the public portal boots without DB."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parents[1]


class ReadOnlyBootTests(unittest.TestCase):
    def test_public_site_imports_and_serves_without_database_url(self):
        # Run in a fresh interpreter so earlier test imports cannot mask boot errors.
        env = os.environ.copy()
        env["KARNAFIM_MAINTENANCE"] = "1"
        env["RENDER_GIT_COMMIT"] = "abcdef0123456789abcdef0123456789abcdef01"
        env["SECRET_KEY"] = "readonly-boot-test-only-not-a-production-key"
        env.pop("DATABASE_URL", None)
        code = """
import app as site
assert site.READ_ONLY_BOOT
client = site.app.test_client()
for path in ('/', '/health', '/terms', '/archive', '/source/1', '/memorial/yehonatan-sharabi', '/robots.txt', '/sitemap.xml'):
    result = client.get(path)
    assert result.status_code == 200, (path, result.status_code, result.get_data(as_text=True)[:150])
assert client.get('/health').json['access'] == 'read_only'
assert client.get('/health').json['revision'] == 'abcdef012345'
status = client.get('/status')
assert status.status_code == 200
status_html = status.get_data(as_text=True)
assert 'מצב Google Sign-In בפועל' in status_html
assert 'מזהה Google Client' in status_html
assert 'אישור שחרור אבטחה' in status_html
assert 'טרם הושלם' in status_html
assert 'Google Safe Browsing' in status_html
assert 'נוצרו פרויקט Google Cloud ולקוח OAuth ייעודי' not in status_html
assert 'href="/status">התחברות</a>' not in status_html
assert 'כניסה מושהית' in status_html
for path in ('/login', '/register', '/auth/google/start', '/password', '/find'):
    assert client.get(path).status_code == 410, path
for path in ('/new-post', '/admin', '/chats', '/profile'):
    assert client.get(path).status_code == 503, path
for path in ('/.env', '/wp-admin', '/fake-login-collector', '/unknown-path'):
    response = client.get(path)
    assert response.status_code == 404, (path, response.status_code)
    assert 'noindex' in response.headers.get('X-Robots-Tag', ''), path
assert "Disallow: /login" not in client.get('/robots.txt').get_data(as_text=True)
assert 'https://karnafim-community-46.onrender.com/status' in client.get('/sitemap.xml').get_data(as_text=True)
# Public content is inert: no credential form, scripts or third-party JS.
for path in ('/', '/about', '/privacy', '/status', '/safety', '/terms'):
    result = client.get(path)
    html = result.get_data(as_text=True).lower()
    assert '<form' not in html and '<script' not in html, path
    assert "form-action 'none'" in result.headers.get('Content-Security-Policy', ''), path
    assert result.headers.get('X-Frame-Options') == 'DENY', path
    assert 'no-store' in result.headers.get('Cache-Control',''), path
# Both GET and POST to prior credential pages stay retired.
for path in ('/login', '/register', '/password', '/find', '/auth/google/start', '/auth/google/callback'):
    for method in ('GET', 'POST'):
        result = client.open(path, method=method)
        assert result.status_code == 410, (method, path, result.status_code)
        assert 'noindex' in result.headers.get('X-Robots-Tag',''), path
# Neither guessable member media URLs nor social/message endpoints reveal data.
for path in ('/directory', '/new-post', '/my-posts', '/profile', '/chats', '/chat/42',
             '/contact/42', '/community-media/10', '/community/moderation', '/admin'):
    for method in ('GET', 'POST'):
        result = client.open(path, method=method)
        assert result.status_code == 503, (method, path, result.status_code)
        assert 'no-store' in result.headers.get('Cache-Control',''), path
# Unrecognized paths must be permanent 404, not generic app errors.
for path in ('/accounts/google/verify', '/forgot-password', '/cgi-bin/test', '/.git/config'):
    result = client.get(path)
    assert result.status_code == 404, path
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(SITE_DIR),
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
        )
        self.assertEqual(0, result.returncode, result.stdout + "\n" + result.stderr)


    def test_search_console_html_meta_verification_in_security_mode(self):
        # Search Console URL-prefix verification must work in the public
        # read-only site WITHOUT enabling login or accessing member records.
        env = os.environ.copy()
        env["SECRET_KEY"] = "unit-test-only-secret"
        env["KARNAFIM_MAINTENANCE"] = "1"
        env["KARNAFIM_SAFETY_RELEASE_APPROVED"] = "0"
        env["KARNAFIM_GSC_VERIFICATION"] = "GoogleVerificationUnitTestAbc123xyZ"
        env.pop("DATABASE_URL", None)
        code = """
import app as site
c = site.app.test_client()
r = c.get("/")
assert r.status_code == 200
assert '<meta name="google-site-verification" content="GoogleVerificationUnitTestAbc123xyZ">' in r.get_data(as_text=True)
assert r.headers.get("Cache-Control","").startswith("no-store")
assert c.get("/login").status_code == 410
assert c.get("/directory").status_code == 503
"""
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=str(SITE_DIR),
            env=env, text=True, capture_output=True, timeout=20,
        )
        self.assertEqual(0, result.returncode, result.stdout + "\\n" + result.stderr)

    def test_release_flags_cannot_bypass_missing_google_oauth_credentials(self):
        # Even two accidentally enabled flags must not expose the private DB
        # when the real Google OAuth client secret is missing.
        env = os.environ.copy()
        env["SECRET_KEY"] = "test-readonly-oauth-gate-not-production"
        env["KARNAFIM_MAINTENANCE"] = "0"
        env["KARNAFIM_SAFETY_RELEASE_APPROVED"] = "1"
        env["KARNAFIM_GOOGLE_AUTH_ENABLED"] = "1"
        env["GOOGLE_CLIENT_ID"] = "761981450509-3bvp5njfhghvrsitipl0vcde0g92q9h.apps.googleusercontent.com"
        env.pop("GOOGLE_CLIENT_SECRET", None)
        env.pop("DATABASE_URL", None)
        code = """
import app as site
assert site.READ_ONLY_BOOT
client = site.app.test_client()
assert client.get('/health').json['access'] == 'read_only'
assert client.get('/login').status_code == 410
assert client.get('/directory').status_code == 503
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(SITE_DIR), env=env, text=True, capture_output=True, timeout=20,
        )
        self.assertEqual(0, result.returncode, result.stdout + "\\n" + result.stderr)

    def test_gis_identity_cannot_bypass_safety_hold(self):
        # A configured secretless Google Sign-In mode does not authorize
        # publishing member data while Chrome still warns about this host.
        env = os.environ.copy()
        env.update({
            "SECRET_KEY": "offline-safety-release-check",
            "GOOGLE_CLIENT_ID": "761981450509-3bvp5njfhghvrsitipl0vcde0g92q9h.apps.googleusercontent.com",
            "KARNAFIM_GOOGLE_AUTH_ENABLED": "1",
            "KARNAFIM_GOOGLE_AUTH_MODE": "gis",
            "KARNAFIM_MAINTENANCE": "0",
            "KARNAFIM_SAFETY_RELEASE_APPROVED": "0",
        })
        env.pop("GOOGLE_CLIENT_SECRET", None)
        env.pop("DATABASE_URL", None)
        code = """
import app
from google_identity import enabled,auth_mode
assert enabled() and auth_mode() == 'gis'
assert app.READ_ONLY_BOOT
c = app.app.test_client()
assert c.get('/health').json['access'] == 'read_only'
assert c.get('/login').status_code == 410
assert c.get('/directory').status_code == 503
assert c.post('/auth/google/callback').status_code == 410
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(SITE_DIR), env=env, text=True,
            capture_output=True, timeout=20,
        )
        self.assertEqual(0, result.returncode, result.stdout + "\\n" + result.stderr)

    def test_maintenance_off_cannot_bypass_the_security_release_lock(self):
        # A single wrong Render environment edit must not start the database
        # or expose member endpoints while Google marks the host unsafe.
        env = os.environ.copy()
        env["SECRET_KEY"] = "readonly-boot-test-only-not-a-production-key"
        env["KARNAFIM_MAINTENANCE"] = "0"
        env["KARNAFIM_SAFETY_RELEASE_APPROVED"] = "0"
        env.pop("DATABASE_URL", None)
        code = """
import app as site
assert site.READ_ONLY_BOOT
assert site.SAFETY_RELEASE_APPROVED is False
client = site.app.test_client()
assert client.get('/health').json['access'] == 'read_only'
for route in ('/login', '/register', '/auth/google/start', '/find'):
    assert client.get(route).status_code == 410
for route in ('/new-post', '/directory', '/chats', '/admin'):
    assert client.get(route).status_code == 503
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(SITE_DIR), env=env, text=True, capture_output=True, timeout=20,
        )
        self.assertEqual(0, result.returncode, result.stdout + "\\n" + result.stderr)



if __name__ == "__main__":
    unittest.main()
