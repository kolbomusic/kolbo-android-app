"""Identity-locked memorial portrait registry.

Portraits are displayed locally only after documented authorization.
A publicly available source portrait is NOT an image re-publication license.
Each record has a stable official Izkor ID to prevent same-name mismatches.
"""
from pathlib import Path

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
    if (approval.get("status")!="approved" or
            not approval.get("permission_reference") or
            not approval.get("source_url") or
            approval.get("izkor_id")!=record["izkor_id"]):
        return None
    filename=person_key+".jpg"
    path=Path(static_dir)/"memorial"/filename
    if not path.is_file():
        return None
    return "/static/memorial/"+filename
