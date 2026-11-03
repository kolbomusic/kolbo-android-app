"""Identity-locked memorial portrait registry.

Portraits are displayed locally only after documented authorization.
A publicly available source portrait is NOT an image re-publication license.
Each record has a stable official Izkor ID to prevent same-name mismatches.
"""
import hashlib
import re
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from urllib.parse import urlsplit, unquote

# The registered identity is the official individual record, not a web image
# search result. No face recognition or heuristic name-to-image matching.
MEMORIAL_PEOPLE = {
    "benaya-rein": {"name": "בניה ריין", "izkor_id": "en_f5ccba845584f96f9b9334cf335d2e78"},
    "uri-grossman": {"name": "אורי גרוסמן", "izkor_id": "en_f53b79619b3f27184812b11f14e635a8"},
    "adam-goren": {"name": "אדם גורן", "izkor_id": "en_e6446f8f52c2b18e0ec560602482bdda"},
    "alexander-bunimovitz": {"name": "אלכסנדר בונימוביץ", "izkor_id": "en_34b2955a02b6a81f8ba932dbf6228e61"},
    "yoni-sharabi": {"name": "יהונתן (יוני) שרעבי", "izkor_id": "en_53e66dd727188835acbe02a1f641a882"},
}

def portrait_for(person_key, static_dir):
    """Return a reviewed local image path or None, never a third-party hotlink.

    Authorizing an image requires updating the individual record with a
    rights/consent note, source URL and confirmed file name. File names are
    fixed per identity; no user-supplied URL is accepted.
    """
    record=MEMORIAL_PEOPLE.get(person_key)
    if not record:
        return None
    # Images are intentionally not enabled by default. Require affirmative
    # evidence in source control as well as a specific local reviewed file.
    approval=record.get("photo_approval")
    if not isinstance(approval,dict):
        return None
    # Every release requires documented identity, explicit permission and an
    # exact SHA-256 of the reviewed image bytes. No arbitrary remote image URLs.
    checksum=approval.get("sha256")
    if (approval.get("status")!="approved" or
            approval.get("izkor_id")!=record["izkor_id"] or
            not isinstance(approval.get("permission_reference"),str) or
            len(approval["permission_reference"].strip())<8 or
            not isinstance(approval.get("source_url"),str) or
            not approval["source_url"].strip() or
            not isinstance(approval.get("reviewed_by"),str) or
            not approval["reviewed_by"].strip() or
            not isinstance(checksum,str) or
            not re.fullmatch(r"[a-f0-9]{64}",checksum)):
        return None
    filename=person_key+".jpg"
    path=Path(static_dir)/"memorial"/filename
    if path.is_symlink() or not path.is_file():
        return None
    try:
        if path.stat().st_size>6*1024*1024:
            return None
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=checksum:
            return None
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            if image.format!="JPEG" or image.width*image.height>12_000_000:
                return None
    except (OSError,ValueError,UnidentifiedImageError,Image.DecompressionBombError):
        return None
    return "/static/memorial/"+filename

def official_source_matches(person_key, source_url):
    """Require an HTTPS Izkor individual-record URL for the exact identity.

    Do not resolve redirects or load remote content at render time. This is a
    structural integrity check, not a substitute for verifying a record manually.
    """
    record=MEMORIAL_PEOPLE.get(person_key)
    if not record or not isinstance(source_url,str):
        return False
    try:
        parsed=urlsplit(source_url)
        parts=unquote(parsed.path).strip("/").split("/")
        return (parsed.scheme=="https"
                and parsed.hostname=="www.izkor.gov.il"
                and parsed.port is None
                and parsed.username is None and parsed.password is None
                and not parsed.query and not parsed.fragment
                and len(parts)==2 and parts[1]==record["izkor_id"])
    except ValueError:
        return False
