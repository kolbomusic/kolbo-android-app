"""Offline identity, HTTPS and closed-portal safety tests for memorial source intake."""
import os
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.pop("BARKAN_DATABASE_URL",None)
os.environ.pop("DATABASE_URL",None)
os.environ["BARKAN_PUBLIC_AUTH"]="0"
os.environ["BARKAN_SAFETY_RELEASE_APPROVED"]="0"

from memorial_source_registry import (
    MEMORIAL_PEOPLE, plausible_public_source, official_memorial_link
)
assert len(MEMORIAL_PEOPLE)==5
assert len({v["izkor_id"] for v in MEMORIAL_PEOPLE.values()})==5
assert official_memorial_link(
    "yoni-sharabi",
    "https://www.izkor.gov.il/יהונתן%20שרעבי/en_53e66dd727188835acbe02a1f641a882"
)
assert not official_memorial_link(
    "yoni-sharabi",
    "https://www.izkor.gov.il/אורי%20גרוסמן/en_f53b79619b3f27184812b11f14e635a8"
)
for link in ("http://example.com/photo","https://localhost/private",
             "https://127.0.0.1/photo","https://192.168.1.1/image",
             "https://[::1]/private","https://me:pw@example.com/photo",
             "https://example.com/path#fragment","https://example.internal/file",
             "https://example.com:"+"1"*500):
    assert not plausible_public_source(link),link
assert plausible_public_source("https://example.org/photograph")
import app as site
client=site.app.test_client()
url="https://karnafim-community-46.onrender.com"
for path in ("/memorial-sources","/memorial-source-review"):
    assert client.get(path,base_url=url).status_code==503,path
    assert client.post(path,base_url=url).status_code==503,path
r=client.get("/memorial",base_url=url)
assert r.status_code==200
assert r.get_data(as_text=True).count('class="memorial"')==5
print("PASS: five memorial identities, safe source intake, auth-gated routes")
