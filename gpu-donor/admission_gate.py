"""Kolbo donor gate: local evidence only, NEVER issues credentials or leases media."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path

def inspect_graph(path:Path, image_count:int) -> dict:
    out={"present":False,"structural_api_graph":False,"bindings_ok":False,"sha256":None}
    try:
        if path.is_symlink() or not path.is_file() or not 100<=path.stat().st_size<=4_000_000:return out
        raw=path.read_bytes()
        obj=json.loads(raw)
        out["present"]=True
        if not isinstance(obj,dict) or not obj or "nodes" in obj:return out
        if not all(isinstance(k,str) and k.isdecimal() and isinstance(v,dict) and
                   isinstance(v.get("class_type"),str) and isinstance(v.get("inputs"),dict)
                   for k,v in obj.items()):return out
        out["structural_api_graph"]=True
        out["sha256"]=hashlib.sha256(raw).hexdigest()
        expected=["__KOLBO_PROMPT__","__KOLBO_FRAMES__"]
        if image_count==1:expected.append("__KOLBO_IMAGE1__")
        found=re.findall(r"__KOLBO_[A-Z0-9_]+__",json.dumps(obj))
        out["bindings_ok"]=sorted(found)==sorted(expected)
    except (OSError,ValueError,TypeError,UnicodeError):pass
    return out

def inspect_receipt(path:Path|None)->bool:
    if path is None:return False
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size>=16_384:return False
        o=json.loads(path.read_text())
        return (o.get("verified") is True and o.get("audio_verified") is True and
                o.get("audible_audio_verified") is True and
                type(o.get("changing_frame_intervals")) is int and o["changing_frame_intervals"]>0 and
                isinstance(o.get("sha256"),str) and
                re.fullmatch(r"[0-9a-f]{64}",o["sha256"]) is not None)
    except (OSError,ValueError,UnicodeError,TypeError):return False

def inspect_donor(*,hardware_report:dict,workflows:Path,receipt:Path|None=None)->dict:
    zero=inspect_graph(workflows/"workflow_0_images.json",0)
    one=inspect_graph(workflows/"workflow_1_images.json",1)
    local_proof=inspect_receipt(receipt)
    ready=(hardware_report.get("eligible_for_operator_review") is True and
           zero["bindings_ok"] and one["bindings_ok"] and local_proof)
    # Local evidence is not trust. A human owner separately verifies proof and scopes.
    return {"hardware_reported_eligible":hardware_report.get("eligible_for_operator_review") is True,
            "workflow_0":zero,"workflow_1":one,"synthetic_local_proof":local_proof,
            "eligible_for_independent_review":bool(ready),
            "owner_approved":False,"registered_worker":False,
            "allowed_to_receive_private_media":False,
            "real_ai_e2e_verified":False,"paid_fallback_enabled":False}
