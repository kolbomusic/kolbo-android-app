#!/usr/bin/env bash
# Encrypted point-in-time logical backup. NEVER commit database credentials.
# Requires Docker (PostgreSQL 18 pg_dump), GnuPG and two protected environment
# secrets. Only ciphertext and its checksum leave the ephemeral runner.
set -euo pipefail
umask 077
export LC_ALL=C

: "${KARNAFIM_BACKUP_DATABASE_URL:?Missing production backup database secret}"
: "${KARNAFIM_BACKUP_PASSPHRASE:?Missing encryption passphrase secret}"
: "${KARNAFIM_BACKUP_OUTPUT_DIR:?Set an output directory for encrypted backups}"
command -v docker >/dev/null || { echo "ERROR: Docker unavailable"; exit 2; }
command -v gpg >/dev/null || { echo "ERROR: GPG unavailable"; exit 2; }

# Fail closed on a wrong branch, unencrypted DB transport, or a weak key.
python3 - <<'PY'
import os
from urllib.parse import urlsplit,parse_qs
url=os.environ['KARNAFIM_BACKUP_DATABASE_URL']
passphrase=os.environ['KARNAFIM_BACKUP_PASSPHRASE']
if len(passphrase)<32:
    raise SystemExit("ERROR: Backup encryption secret must have at least 32 characters")
try:
    p=urlsplit(url)
    host=(p.hostname or "").lower()
    query=parse_qs(p.query)
except ValueError:
    raise SystemExit("ERROR: Invalid database secret")
if p.scheme not in ("postgres","postgresql"):
    raise SystemExit("ERROR: Invalid database protocol")
if os.environ.get('KARNAFIM_BACKUP_TEST_MODE')=='1':
    if host not in ('127.0.0.1','localhost'):
        raise SystemExit("ERROR: Test mode requires local database")
else:
    known=('ep-proud-water-bav0iyw4','ep-proud-water-bav0iyw4-pooler')
    if host.partition('.')[0] not in known or not host.endswith('.c-8.eu-central-1.aws.neon.tech'):
        raise SystemExit("ERROR: Backup target is not the verified production Neon endpoint")
    sslmode=query.get('sslmode',['require'])[0]
    if sslmode not in ('require','verify-ca','verify-full'):
        raise SystemExit("ERROR: TLS is required for the production database")
PY

mkdir -p -- "$KARNAFIM_BACKUP_OUTPUT_DIR"
work="$(mktemp -d)"
cleanup() { rm -rf -- "$work"; }
trap cleanup EXIT
export KARNAFIM_BACKUP_DATABASE_URL
export PGCONNECT_TIMEOUT=15
export PGSSLMODE="${KARNAFIM_BACKUP_SSLMODE:-require}"

# Never log or echo pg_dump args, URLs, passwords or SQL rows.
if ! docker run --rm --network host --user "$(id -u):$(id -g)" \
       -v "$work:/export" -e KARNAFIM_BACKUP_DATABASE_URL -e PGCONNECT_TIMEOUT -e PGSSLMODE \
       postgres:18-alpine sh -c 'exec pg_dump --dbname="$KARNAFIM_BACKUP_DATABASE_URL" \
          --format=custom --compress=6 --no-owner --no-privileges \
          --file=/export/community.dump' >/dev/null 2>&1; then
  echo "ERROR: PostgreSQL 18 backup failed (credentials and details suppressed)"
  exit 3
fi

# Ensure the actual membership, content and memorial tables are included.
docker run --rm --network host --user "$(id -u):$(id -g)" \
  -v "$work:/export:ro" postgres:18-alpine \
  pg_restore --list /export/community.dump > "$work/manifest.txt"
for table in b2_users b2_posts b2_messages b2_memorial_source_suggestions; do
  if ! grep -Eq "TABLE[[:space:]]+public[[:space:]]+${table}([[:space:]]|$)" "$work/manifest.txt"; then
    echo "ERROR: Required community table missing from backup" 
    exit 4
  fi
done
bytes="$(wc -c < "$work/community.dump")"
if (( bytes < 500 || bytes > 52428800 )); then
  echo "ERROR: Backup size is invalid or exceeds the 50 MiB protected limit"
  exit 5
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
filename="karnafim-${timestamp}.pgdump.gpg"
dest="$KARNAFIM_BACKUP_OUTPUT_DIR/$filename"
printf '%s' "$KARNAFIM_BACKUP_PASSPHRASE" |
  gpg --batch --yes --no-tty --pinentry-mode loopback \
      --passphrase-fd 0 --symmetric --cipher-algo AES256 \
      --output "$dest" "$work/community.dump" >/dev/null 2>&1

# Verify authenticated ciphertext can be decrypted before keeping it.
printf '%s' "$KARNAFIM_BACKUP_PASSPHRASE" |
  gpg --batch --yes --no-tty --pinentry-mode loopback \
      --passphrase-fd 0 --decrypt --output "$work/check.dump" "$dest" >/dev/null 2>&1
if ! cmp -s "$work/community.dump" "$work/check.dump"; then
  echo "ERROR: Encrypted backup round-trip verification failed"
  rm -f -- "$dest"
  exit 6
fi
( cd "$KARNAFIM_BACKUP_OUTPUT_DIR" && sha256sum "$filename" > "$filename.sha256" )
echo "PASS: encrypted backup created, community tables verified, decrypt round-trip verified"
echo "Encrypted files: $filename and $filename.sha256"
