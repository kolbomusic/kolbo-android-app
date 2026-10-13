"""Fail closed if ChopperBlu ZeroGPU has not loaded its gated LTX model.

Called before Kolbo worker heartbeats, job lease or private media fetch.
Metadata is not proof of a successful GPU inference.
"""
from dataclasses import dataclass
ORIGIN="https://chopperblu-ltx-2-5-demo.hf.space"
@dataclass(frozen=True)
class Result:
    state:str
    eligible_for_job_lease:bool
def inspect(session,timeout=8):
    try:
        r=session.get(ORIGIN+"/config",headers={"Accept":"application/json"},timeout=timeout,allow_redirects=False)
        if r.status_code!=200 or "json" not in r.headers.get("Content-Type","").lower() or len(r.content)>700000:
            return Result("bad_metadata",False)
        data=r.json()
        ready=False
        for part in data.get("components",[]):
            if not isinstance(part,dict) or part.get("type") not in ("markdown","html"):continue
            desc=part.get("props",{}).get("value","")
            if not isinstance(desc,str):continue
            if any(word in desc for word in ("Setup required","Model loading failed","add a read-scoped")):
                return Result("provider_model_setup_required",False)
            if "Model access configured" in desc or "Model is ready for ZeroGPU" in desc:
                ready=True
        return Result("declared_ready" if ready else "unknown_model_state",bool(ready))
    except Exception:
        return Result("unreachable",False)
