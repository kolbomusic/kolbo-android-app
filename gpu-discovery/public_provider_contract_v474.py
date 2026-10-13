"""Read-only preflight for public, unauthenticated image-to-video Spaces.

No media is uploaded, no generation request is submitted, no authentication.
Public endpoint existence does not establish quota or entitlement to operate.
"""
from __future__ import annotations
import json, urllib.request, urllib.error, os
from pathlib import Path

CANDIDATES={
 "wan_fast":"zerogpu-aoti-wan2-2-fp8da-aoti-faster.hf.space",
 "wan_lightning":"saravutw-wan2-2-i2v-lightning-4-8step-custom.hf.space",
 "wan_preview":"r3gm-wan2-2-14b-preview.hf.space",
 "ltx_video_audio":"00000tt-ltx-2-3-10eros.hf.space",
}
def inspect(name, host):
    report={"id":name,"host":host,"status":"UNKNOWN","endpoints":[]}
    try:
        req=urllib.request.Request("https://"+host+"/gradio_api/info",
            headers={"Accept":"application/json","User-Agent":"Kolbo-readonly-contract-check/1.0"})
        with urllib.request.urlopen(req,timeout=18) as response:
            if response.status!=200: raise ValueError("non200")
            data=response.read(500_001)
            if len(data)>500_000: raise ValueError("oversized")
            meta=json.loads(data)
        for api,item in (meta.get("named_endpoints") or {}).items():
            if not isinstance(item,dict):continue
            params=item.get("parameters") or []
            if any(word in api.lower() for word in ("generate","video","render")):
                report["endpoints"].append({
                    "api":api,
                    "params":[p.get("parameter_name") for p in params if isinstance(p,dict)]
                })
        report["status"]="CONTRACT_VISIBLE" if report["endpoints"] else "NO_GENERATION_ENDPOINT"
    except Exception as e:
        report["status"]=type(e).__name__
    return report

if __name__=="__main__":
    r={"readonly":True,"no_user_media":True,"no_gpu_jobs":True,
       "providers":[inspect(n,h) for n,h in CANDIDATES.items()]}
    Path("provider-contract-probe-v474.json").write_text(
       json.dumps(r,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(r,indent=2,ensure_ascii=False))
