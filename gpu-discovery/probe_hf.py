"""Read-only compatibility probe for publicly available ZeroGPU video inference.

No token, no prompts submitted, no model calls, no cost.
"""
import json
import os
import urllib.request
from urllib.parse import urlsplit

SPACE_ORIGIN = "https://lightricks-ltx-2-5.hf.space"
KNOWN_PATHS = ["/gradio_api/openapi.json", "/config", "/gradio_api/info"]

def fetch_json(path):
    u=SPACE_ORIGIN+path
    request=urllib.request.Request(u, headers={
        "Accept":"application/json", "User-Agent":"Kolbo-Verified-Public-API-Probe/1.0"})
    with urllib.request.urlopen(request,timeout=20) as result:
        if result.status!=200: raise RuntimeError("unexpected HTTP status")
        media=result.headers.get("content-type","")
        if "json" not in media.lower():raise RuntimeError("not a JSON endpoint")
        data=result.read(1_000_001)
        if len(data)>1_000_000:raise RuntimeError("large metadata")
        return json.loads(data)

def probe():
    report={"target":"Lightricks/LTX-2.5", "metadata_readable":False,
            "live_gpu_run":False, "zero_payment":True, "authenticated":False,
            "api_names":[],"limits":[]}
    for path in KNOWN_PATHS:
        try:
            d=fetch_json(path)
            if not isinstance(d,dict): continue
            if path.endswith("openapi.json"):
                paths=d.get("paths",{})
                report["api_names"]=sorted(k for k in paths if k.startswith("/"))[:60]
            elif path=="/config":
                deps=d.get("dependencies",[])
                report["api_names"]+=sorted({"/"+str(x["api_name"]) for x in deps if isinstance(x,dict) and x.get("api_name")})
            else:
                report["api_names"]+=sorted((d.get("named_endpoints") or {}).keys())
            report["metadata_readable"]=True
        except Exception as e:
            report["limits"].append({"path":path,"error_type":type(e).__name__})
    report["api_names"]=sorted(set(report["api_names"]))
    try:
        metadata=fetch_json("/gradio_api/info")
        run=(metadata.get("named_endpoints") or {}).get("/run",{})
        report["run_parameters"]=[
            {"name":x.get("parameter_name"),"component":x.get("component"),
             "type":str(x.get("type"))[:150],
             "example":str(x.get("example_input"))[:100]}
            for x in run.get("parameters",[]) if isinstance(x,dict)
        ][:25]
        report["run_returns"]=len(run.get("returns",[]))
    except Exception as e:
        report["limits"].append({"path":"run_parameter_details","error_type":type(e).__name__})
    return report

if __name__=="__main__":
    report=probe()
    print(json.dumps(report,indent=2,ensure_ascii=False))
    with open("kolbo_gpu_api_probe.json","w",encoding="utf-8") as out:json.dump(report,out,ensure_ascii=False,indent=2)
    if not report["metadata_readable"]:
        raise SystemExit("Live public Gradio metadata unverified")
