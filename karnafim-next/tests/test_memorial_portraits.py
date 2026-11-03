"""Safeguards for attribution and photograph publication in memorials."""
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.pop("DATABASE_URL",None)
from memorial_portraits import MEMORIAL_PEOPLE, portrait_for, official_source_matches
import app

assert len(MEMORIAL_PEOPLE)==5
assert len({x["izkor_id"] for x in MEMORIAL_PEOPLE.values()})==5
# Wrong-person records and hostile lookalike domains must not be linked.
assert official_source_matches("yoni-sharabi", "https://www.izkor.gov.il/יהונתן%20שרעבי/en_53e66dd727188835acbe02a1f641a882")
assert not official_source_matches("yoni-sharabi", "https://www.izkor.gov.il/אורי%20גרוסמן/en_f53b79619b3f27184812b11f14e635a8")
assert not official_source_matches("yoni-sharabi", "https://www.izkor.gov.il.evil.example/יהונתן%20שרעבי/en_53e66dd727188835acbe02a1f641a882")
assert not official_source_matches("yoni-sharabi", "http://www.izkor.gov.il/יהונתן%20שרעבי/en_53e66dd727188835acbe02a1f641a882")
assert "yoni-sharabi" in MEMORIAL_PEOPLE
assert MEMORIAL_PEOPLE["yoni-sharabi"]["izkor_id"]=="en_53e66dd727188835acbe02a1f641a882"

with TemporaryDirectory() as temp:
    root=Path(temp)
    (root/"memorial").mkdir()
    # A file appearing on disk without documented approval must NOT go live.
    (root/"memorial"/"yoni-sharabi.jpg").write_bytes(b"not a reviewed portrait")
    assert portrait_for("yoni-sharabi",root) is None
    assert portrait_for("unknown-person",root) is None

client=app.app.test_client()
html=client.get("/memorial",base_url="https://karnafim-barkan-46.onrender.com").get_data(as_text=True)
assert html.count('class="memorial"')==5
assert html.count("צפייה בתמונה ובהנצחה באתר יזכור")==5
assert html.count("תמונה מאומתת תוצג כאן")==5
assert "memorial-portrait" not in html
for record in MEMORIAL_PEOPLE.values():
    assert record["izkor_id"] in html
print("PASS: five identified memorial portraits, official source links, no unlicensed images")
