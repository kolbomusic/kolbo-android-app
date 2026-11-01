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
        env["SECRET_KEY"] = "readonly-boot-test-only-not-a-production-key"
        env.pop("DATABASE_URL", None)
        code = """
import app as site
assert site.READ_ONLY_BOOT
client = site.app.test_client()
for path in ('/', '/health', '/archive', '/source/1', '/memorial/yehonatan-sharabi', '/robots.txt', '/sitemap.xml'):
    result = client.get(path)
    assert result.status_code == 200, (path, result.status_code, result.get_data(as_text=True)[:150])
assert client.get('/health').json['access'] == 'read_only'
for path in ('/login', '/register', '/auth/google/start', '/password', '/find'):
    assert client.get(path).status_code == 410, path
for path in ('/new-post', '/admin', '/chats', '/profile'):
    assert client.get(path).status_code == 503, path
assert "Disallow: /login" not in client.get('/robots.txt').get_data(as_text=True)
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


if __name__ == "__main__":
    unittest.main()
