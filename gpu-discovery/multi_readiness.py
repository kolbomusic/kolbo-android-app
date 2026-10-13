"""Public readiness inventory of authorized Gradio demos. No inference and no tokens."""
import json,urllib.request
providers=[
 ("Lightricks/LTX-2.5","https://lightricks-ltx-2-5.hf.space"),
 ("ChopperBlu/ltx-2-5-demo","https://chopperblu-ltx-2-5-demo.hf.space"),
 ("akhaliq/LTX-2.5-workflow","https://akhaliq-ltx-2-5-workflow.hf.space"),
 ("hugging-apps/ltx25-multi-subject-reference","https://hugging-apps-ltx25-multi-subject-reference.hf.space")
]
def get(base,path):
 req=urllib.request.Request(base+path,headers={"Accept":"application/json","User-Agent":"KolboMetadataOnly/1.0"})
 with urllib.request.urlopen(req,timeout=16) as r:
  data=r.read(700001)
  if r.status!=200 or len(data)>700000:raise ValueError("invalid metadata")
  return json.loads(data)
items=[]
for name,url in providers:
 row={"space":name,"config_ok":False,"ready_notice":"unknown","can_generate":False,"gpu_executed":False}
 try:
  cfg=get(url,"/config"); row["config_ok"]=True
  for c in cfg.get("components",[]):
   if c.get("type") not in ("markdown","html"):continue
   txt=str(c.get("props",{}).get("value",""))
   if "Model access configured" in txt or "Model is ready" in txt:
    row["ready_notice"]="configured"
   if "Setup required" in txt or "add a read-scoped" in txt or "Model loading failed" in txt:
    row["ready_notice"]="setup_required"
  info=get(url,"/gradio_api/info")
  row["can_generate"]=any(x in (info.get("named_endpoints") or {}) for x in
      ("/run","/generate_video","/generate"))
 except Exception as e:row["error_type"]=type(e).__name__
 items.append(row)
print(json.dumps(items,indent=2))
with open("public-spaces-readiness.json","w") as f:json.dump(items,f,indent=2)
