"""Memorial identities and URL intake validation for the live community.

A source link is evidence to review, NOT a license to republish a portrait.
No automatic image download, name-to-face matching or remote URL fetching.
"""
import ipaddress
from urllib.parse import urlsplit, unquote

MEMORIAL_PEOPLE = {
    "benaya-rein": {"name":"בניה ריין","izkor_id":"en_f5ccba845584f96f9b9334cf335d2e78"},
    "uri-grossman": {"name":"אורי גרוסמן","izkor_id":"en_f53b79619b3f27184812b11f14e635a8"},
    "adam-goren": {"name":"אדם גורן","izkor_id":"en_e6446f8f52c2b18e0ec560602482bdda"},
    "alexander-bunimovitz": {"name":"אלכסנדר (סשה) בונימוביץ׳","izkor_id":"en_34b2955a02b6a81f8ba932dbf6228e61"},
    "yoni-sharabi": {"name":"יהונתן (יוני) שרעבי","izkor_id":"en_53e66dd727188835acbe02a1f641a882"},
}

def plausible_public_source(url):
    """Validate link form only. NEVER server-fetch a contributor URL."""
    if not isinstance(url,str) or not 12<=len(url)<=500 or any(ord(c)<32 for c in url):
        return False
    try:
        p=urlsplit(url)
        host=p.hostname
        if (p.scheme!="https" or not host or p.username or p.password or
                p.port not in (None,443) or p.fragment):
            return False
        host=host.rstrip(".").lower()
        if (host=="localhost" or host.endswith((".local",".internal",".localhost")) or
                "." not in host):
            return False
        try:
            ipaddress.ip_address(host.strip("[]"))
            return False
        except ValueError:
            pass
        return True
    except ValueError:
        return False

def official_memorial_link(key,url):
    """Exact Izkor personal ID, not merely an overlapping name."""
    record=MEMORIAL_PEOPLE.get(key)
    if not record or not plausible_public_source(url):
        return False
    p=urlsplit(url)
    pieces=unquote(p.path).strip("/").split("/")
    return (p.hostname=="www.izkor.gov.il" and len(pieces)==2 and
            pieces[1]==record["izkor_id"] and not p.query)
