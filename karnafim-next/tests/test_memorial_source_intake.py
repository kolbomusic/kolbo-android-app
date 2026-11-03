"""Public-safe workflow checks for memorial source suggestions."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.pop("DATABASE_URL",None)
import app

assert app.accepted_source_url("https://www.izkor.gov.il/example")
assert app.accepted_source_url("https://example.org/photo?ref=42")
for url in (
    "http://example.org/photo",
    "https://localhost/private",
    "https://127.0.0.1/private",
    "https://example.org.evil.invalid/#fragment",
    "https://user:password@example.org/photo",
    "not a web address",
    "https://example.org/" + "a"*600,
):
    assert not app.accepted_source_url(url),url

client=app.app.test_client()
origin="https://karnafim-barkan-46.onrender.com"
for url in ("/memorial-sources","/memorial-source-review"):
    assert client.get(url,base_url=origin).status_code==503,url
    assert client.post(url,base_url=origin).status_code==503,url

source=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")
assert "status='pending'" in source
assert "INSERT INTO b2_memorial_sources" in source
# A contributor may read only their own proposal statuses, not other members'.
assert "FROM b2_memorial_sources WHERE submitted_by=%s" in source
assert '(g.user["id"],)' in source
assert "המקורות שהצעת" in source
assert "המקור נבדק — טרם אושר לפרסום תמונה" in source

assert "if not can_moderate():abort(403)" in source
assert '"/memorial-sources"' in source
assert "photo_approval" not in source[source.index("def memorial_sources():"):source.index('@app.get("/photos")')]
print("PASS: protected memorial source intake, moderation and no image auto-publication")
