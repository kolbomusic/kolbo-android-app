"""Read-only endpoint fingerprint regression: no password, hostname or PII leaks."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from db_endpoint_audit import neon_endpoint_tag

direct="postgresql://someone:super-secret@ep-proud-water-bav0iyw4.c-8.eu-central-1.aws.neon.tech/neondb"
pooled="postgresql://someone:super-secret@ep-proud-water-bav0iyw4-pooler.c-8.eu-central-1.aws.neon.tech/neondb"
alternate="postgresql://someone:super-secret@ep-green-cloud-ba5h9e88.c-8.eu-central-1.aws.neon.tech/neondb"
tag=neon_endpoint_tag(direct)
assert tag==neon_endpoint_tag(pooled)
assert tag!=neon_endpoint_tag(alternate)
assert len(tag)==20 and all(c in "0123456789abcdef" for c in tag)
assert "secret" not in tag and "ep-" not in tag
assert neon_endpoint_tag("")=="unconfigured"
for bad in ("", "postgresql://user:pw@localhost/db",
            "https://ep-proud-water-bav0iyw4.example/db",
            "postgresql://no-server-name/db"):
    assert neon_endpoint_tag(bad) in ("unconfigured","unrecognized")
print("PASS: stable Neon endpoint tag, pooler normalization, no connection URL leakage")
