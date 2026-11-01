"""Investigate the *same* synthetic ASR mistranscription and provider requests.

Only invented synthetic speech words are used. Avoid burning public GPU quota:
one attempt for each distinct engine and a short 1s shot.
"""
from ai_video import cinematic_prompt,_request_ltx25_generation,_request_video_generation,AIVideoUnavailable
from urllib.parse import urlsplit
import json
words="יש זורק קוס זחוכית על הרצפה, הקוס נשברת לרסיסים"
p=cinematic_prompt(words)
variants=[
    ("original_ltx_distilled_1s", _request_video_generation, p),
    ("second_ltx25_1s", _request_ltx25_generation, p),
    ("second_short_hebrew_1s", _request_ltx25_generation, "Photorealistic live-action moving video: "+words+". No on-screen text."),
]
for label,provider,prompt in variants:
    print("PROBE_BEGIN",label,"prompt_chars",len(prompt),flush=True)
    try:
        url=provider(prompt,duration=1.0,max_wait=90)
        print("PROBE_SUCCEEDED",label,"url_host",urlsplit(url).hostname,flush=True)
    except AIVideoUnavailable as exc:
        print("PROBE_REJECTED",label,"reason",str(exc),flush=True)
    except Exception as exc:
        print("PROBE_EXCEPTION",label,type(exc).__name__,str(exc)[:120],flush=True)
