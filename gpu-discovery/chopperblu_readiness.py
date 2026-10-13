"""Read Gradio public interface metadata, never submit a GPU request."""
import json,urllib.request
from urllib.parse import urlsplit
base="https://chopperblu-ltx-2-5-demo.hf.space"
out={"space":"ChopperBlu/ltx-2-5-demo","metadata_reachable":False,
     "model_access_notice":"unknown","run_endpoint_listed":False,
     "exact_nine_parameters":False,"gpu_called":False}
def get(path):
 req=urllib.request.Request(base+path,headers={"Accept":"application/json","User-Agent":"KolboPublicMetadataOnly/1.0"})
 with urllib.request.urlopen(req,timeout=20) as r:
  if r.status!=200:raise RuntimeError("HTTP metadata status")
  b=r.read(1000001)
  if len(b)>1000000:raise RuntimeError("Metadata too large")
  return json.loads(b)
try:
 cfg=get("/config")
 out["metadata_reachable"]=True
 for obj in cfg.get("components",[]):
  if obj.get("type") not in ("markdown","html"):continue
  msg=str(obj.get("props",{}).get("value",""))
  if "Model access configured" in msg or "Model is ready" in msg:
   out["model_access_notice"]="configured"
  if "Setup required" in msg or "add a read-scoped" in msg or "Model loading failed" in msg:
   out["model_access_notice"]="setup_required"
 info=get("/gradio_api/info")
 endpoints=info.get("named_endpoints") or {}
 params=[x.get("parameter_name") for x in endpoints.get("/generate_video",{}).get("parameters",[])]
 out["run_endpoint_listed"]="/generate_video" in endpoints
 out["exact_nine_parameters"]=params==[
    "prompt","image_path","width","height","duration_seconds","auto_length",
    "seed","randomize_seed","decoder"]
 out["reported_param_names"]=params[:15]
except Exception as e:
 out["error_type"]=type(e).__name__
print(json.dumps(out,indent=2))
with open("chopperblu-public-metadata.json","w") as f:json.dump(out,f,indent=2)
if not out["metadata_reachable"]:raise SystemExit("Metadata not reachable")
