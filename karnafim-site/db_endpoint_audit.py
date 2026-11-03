"""Non-secret Neon endpoint identification for Render release audits.

The tag is a hash of the public Neon *compute endpoint label*, not of user
records, credentials or any database content. Never log a full DATABASE_URL.
"""
import hashlib
import re
from urllib.parse import urlsplit


def neon_endpoint_tag(dsn: str) -> str:
    if not isinstance(dsn, str) or not dsn:
        return "unconfigured"
    try:
        parsed = urlsplit(dsn)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in ("postgresql", "postgres") or not host:
            return "unrecognized"
        label = host.partition(".")[0].removesuffix("-pooler")
        # Only recognized Neon compute endpoint labels get fingerprinted.
        if not re.fullmatch(r"ep-[a-z0-9-]{6,80}", label):
            return "unrecognized"
        return hashlib.sha256(label.encode("ascii")).hexdigest()[:20]
    except (ValueError, UnicodeError):
        return "unrecognized"
