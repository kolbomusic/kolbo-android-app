"""Read-only status of public OpenKing Wan2.2 Space, no generation, tokens, or uploads."""
import json,urllib.request,urllib.error,time
BASE="https://openking-wan2-video-generation.hf.space"
def get(path):
    req=urllib.request.Request(BASE+path,headers={"Accept":"application/json","User-Agent":"Kolbo-OneShot-GPU-Readiness/1.0"})
    with urllib.request.urlopen(req,timeout=22) as response:
        if response.status!=200 or "json" not in response.headers.get("Content-Type","").lower():
            raise ValueError("Expected JSON metadata")
        data=response.read(1_000_001)
        if len(data)>1_000_000:raise ValueError("Oversized metadata")
        return json.loads(data)
def main():
    result={"space":"OpenKing/wan2-video-generation","config_ok":False,"gradio_api_ok":False,
        "api_endpoints":[],"parameters":[],"zero_cost_verified":False,"gpu_rendered":False}
    try:
        cfg=get("/config")
        result["config_ok"]=isinstance(cfg.get("components"),list)
        components=cfg.get("components") or []
        for c in components:
            if c.get("type") in ("html","markdown"):
                s=str(c.get("props",{}).get("value","")).lower()
                if "setup required" in s or "model loading failed" in s or "error loading model" in s:
                    result["setup_required_notice"]=True
        info=get("/gradio_api/info")
        ep=info.get("named_endpoints") or {}
        result["gradio_api_ok"]=bool(ep)
        result["api_endpoints"]=sorted(ep)[:30]
        for name,details in ep.items():
            if any(k in name.lower() for k in ("generate","video","infer","run")):
                result["parameters"].append({"endpoint":name,
                    "args":[{"name":a.get("parameter_name"),"type":str(a.get("type"))[:120],
                            "example":str(a.get("example_input"))[:70]}
                            for a in details.get("parameters",[])][:15]})
    except Exception as err:
        result["error_type"]=type(err).__name__
    print(json.dumps(result,ensure_ascii=False,indent=2))
    with open("wan22_provider_report.json","w") as f:json.dump(result,f,indent=2)
    if not result["gradio_api_ok"]:raise SystemExit("No public Gradio API available")
if __name__=="__main__":main()
