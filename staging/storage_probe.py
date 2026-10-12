"""Read-only and synthetic-write proof for external Neon Postgres and private S3.

The production upload API does NOT exist here. This probe's single synthetic
object is deleted immediately. Do not log DB URLs, passwords or signed URLs.
"""
import hashlib
import os
import secrets
from urllib.parse import urlsplit
proof={"db":False,"private_bucket":False,"synthetic_roundtrip":False,"gpu":False}
def _settings():
    db=os.environ.get("KOLBO_NEON_DATABASE_URL","")
    endpoint=os.environ.get("KOLBO_S3_ENDPOINT","")
    bucket=os.environ.get("KOLBO_S3_PRIVATE_BUCKET","")
    key=os.environ.get("KOLBO_S3_ACCESS_KEY","")
    secret=os.environ.get("KOLBO_S3_SECRET_KEY","")
    u=urlsplit(db);s=urlsplit(endpoint)
    if u.scheme!="postgresql" or not u.hostname or not u.hostname.endswith(".neon.tech"):
        raise ValueError("Neon Postgres URL required")
    if "sslmode=require" not in u.query and "sslmode=verify-full" not in u.query:
        raise ValueError("Postgres TLS required")
    if s.scheme!="https" or not s.hostname or not s.hostname.endswith(".neon.tech") or s.query or s.username or s.password:
        raise ValueError("Neon HTTPS S3 endpoint required")
    if bucket!="kolbo-private-media" or len(key)<12 or len(secret)<20:
        raise ValueError("Private media settings incomplete")
    return db,endpoint,bucket,key,secret

def verify_synthetic_storage():
    global proof
    proof.clear();proof.update({"db":False,"private_bucket":False,"synthetic_roundtrip":False,"gpu":False})
    db,url,bucket,key,secret=_settings()
    import psycopg
    import boto3
    from botocore.config import Config
    # Explicit SQL read + TLS handshake, not merely a syntactically valid URL.
    with psycopg.connect(db,connect_timeout=8) as cn:
        with cn.cursor() as cur:
            cur.execute("SELECT 1")
            if cur.fetchone()[0]!=1:raise RuntimeError("Database test failed")
    proof["db"]=True
    s3=boto3.client("s3",endpoint_url=url,aws_access_key_id=key,
       aws_secret_access_key=secret,region_name="us-east-1",
       config=Config(signature_version="s3v4",s3={"addressing_style":"path"},
            connect_timeout=8,read_timeout=25,retries={"max_attempts":2}))
    s3.head_bucket(Bucket=bucket)
    proof["private_bucket"]=True
    # No user photos or prompts. A 128-byte synthetic test object is created
    # and deleted on the real provider; cleanup is unconditional.
    objkey="private/system-probes/"+secrets.token_hex(16)+".txt"
    raw=("kolbo-storage-proof-"+secrets.token_hex(16)).encode()
    try:
        s3.put_object(Bucket=bucket,Key=objkey,Body=raw,ContentType="text/plain")
        remote=s3.get_object(Bucket=bucket,Key=objkey)["Body"].read()
        if hashlib.sha256(remote).digest()!=hashlib.sha256(raw).digest():
            raise RuntimeError("S3 digest mismatch")
        proof["synthetic_roundtrip"]=True
    finally:
        s3.delete_object(Bucket=bucket,Key=objkey)
    return dict(proof)
