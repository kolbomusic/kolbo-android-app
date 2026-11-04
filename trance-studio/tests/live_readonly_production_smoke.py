"""Read-only live Kolbo Trance smoke test. No private recordings or billing.

Exercises production HTTP, checks the currently deployed release, confirms
free-only capabilities and UI defaults. Heavy authenticated generation is
INTENTIONALLY excluded: this script has no API_TOKEN and never POSTs media.
"""
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

ROOT="https://kolbo-trance-studio.onrender.com"
SOURCE=pathlib.Path(__file__).resolve().parents[1]
BACKEND=(SOURCE/"backend"/"app.py").read_text(encoding="utf-8")
VERSION=re.search(r"version='([0-9.]+)'",BACKEND)
assert VERSION, "Missing backend release identifier"
EXPECTED_VERSION=VERSION.group(1)


def get(path):
    last=None
    # Render Free may be asleep. A cold start may take up to a minute.
    for attempt in range(5):
        try:
            request=urllib.request.Request(
                ROOT+path,headers={"User-Agent":"KolboTranceReadOnlyQA/1.0",
                                   "Accept":"application/json,text/html"})
            with urllib.request.urlopen(request,timeout=45) as response:
                if response.status!=200:
                    raise AssertionError(f"GET {path}: HTTP {response.status}")
                return response.read(1024*1024).decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            last=exc
            if attempt<4:time.sleep(5)
    raise RuntimeError(f"GET {path} inaccessible after retries: {type(last).__name__}")


def check():
    # A GitHub PR merge can start CI a few seconds before Render Free
    # finishes its manual deployment. Retry *read-only* health, and fail
    # if the tested release never reaches production.
    for attempt in range(8):
        health=json.loads(get("/health"))
        if health.get("ok") is True and health.get("version")==EXPECTED_VERSION:
            break
        if attempt<7:time.sleep(10)
    assert health.get("ok") is True, "Production health check failed"
    assert health.get("version")==EXPECTED_VERSION, (
        "Expected Kolbo "+EXPECTED_VERSION+", got "+str(health.get("version")))
    print("PASS: production health reports",health["version"])

    cap=json.loads(get("/api/capabilities"))
    for flag in ("billing_enabled","supports_payment",
                 "uses_paid_api_tokens","promises_unlimited_public_gpu"):
        assert cap.get(flag) is False,f"Unexpected paid/unlimited promise: {flag}"
    assert len(cap.get("sound_lab",[]))>=16,"Missing free audio effects"
    assert all(not x.get("requires_payment",False)
               for group in ("music","vocal_fx","sound_lab","video")
               for x in cap.get(group,[])),"Billable creative engine exposed"
    videos=cap.get("video",[])
    assert any(v.get("kind")=="local-ffmpeg" and v.get("ready")
               for v in videos),"Local free source-video editor unavailable"
    assert all(v.get("quota_limited",False)
               for v in videos if v.get("kind")=="external-public-ai"), (
               "Public AI incorrectly represented as unlimited")
    print("PASS: 16 free sound effects, no billing, quota honesty")

    html=get("/studio")
    for snippet in ('id="creativePreset"','value="bold" selected',
                    'id="generate"','id="video_strategy"',
                    'id="fx_intensity"','id="fx_gain"',
                    'kolboImportSharedAudio'):
        assert snippet in html, f"Missing production UI feature: {snippet}"
    assert "במאי קומי אוטומטי" in html, (
        "Coherent comedy mode not visible in the deployed studio")
    print("PASS: deployed studio includes strong comic preset and manual creation")
    print("NOTE: authenticated audio/MP4 generation NOT tested from this read-only probe")


if __name__=="__main__":
    try:check()
    except Exception as exc:
        print("FAIL:",str(exc),file=sys.stderr)
        raise
