#!/usr/bin/env python3
"""Read-only public Gradio contract inventory. No media, tokens, inference or GPU use.

Never submit a generation job from this module. A reported endpoint does not
imply free capacity, permissions to automate it, or suitability for Kolbo.
"""
from __future__ import annotations
import json
from pathlib import Path
import socket
import urllib.error
import urllib.request

# Fixed, reviewed public candidates. Hosts are not assembled from user input.
PROVIDERS = (
    ("LTX-2.5 Official", "https://lightricks-ltx-2-5.hf.space"),
    ("Wan2.2 Fast AOTI", "https://zerogpu-aoti-wan2-2-fp8da-aoti-faster.hf.space"),
    ("LTX-2.3 10Eros", "https://00000tt-ltx-2-3-10eros.hf.space"),
    ("Wan2.2 Lightning", "https://saravutw-wan2-2-i2v-lightning-4-8step-custom.hf.space"),
)

def load_metadata(base: str, path: str, *, timeout: int = 12) -> dict:
    req = urllib.request.Request(
        base + path,
        headers={"Accept": "application/json", "User-Agent": "KolboPublicContractAudit/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if response.status != 200 or "json" not in response.headers.get("content-type","").lower():
            raise ValueError("non_json_or_non_200")
        raw = response.read(700_001)
        if len(raw) > 700_000:
            raise ValueError("oversized_metadata")
    obj = json.loads(raw)
    if not isinstance(obj,dict):
        raise ValueError("non_object_metadata")
    return obj

def inspect_provider(name: str, base: str, getter=load_metadata) -> dict:
    result = {
        "name": name, "space_url": base, "metadata_available": False,
        "generation_endpoints": [], "gpu_job_submitted": False,
        "video_generated": False, "zero_cost_inference_verified": False,
        "media_uploaded": False, "supports_two_person_identity_verified": False,
        "native_audio_verified": False,
    }
    try:
        api = getter(base, "/gradio_api/info")
        endpoints = api.get("named_endpoints", {})
        if not isinstance(endpoints,dict) or len(endpoints)>100:
            raise ValueError("invalid_endpoint_collection")
        result["metadata_available"] = True
        for name_api, descriptor in endpoints.items():
            if not isinstance(name_api,str) or not isinstance(descriptor,dict):
                continue
            if not any(keyword in name_api.lower() for keyword in
                       ("generate","video","infer","render","predict")):
                continue
            params = descriptor.get("parameters") or []
            if not isinstance(params,list):
                continue
            param_names = [str(p.get("parameter_name",""))[:60] for p in params[:24]
                           if isinstance(p,dict)]
            result["generation_endpoints"].append({
                "api_name":name_api[:100],
                "parameter_names":param_names,
                "parameter_count":len(params),
                "response_count":len(descriptor.get("returns") or []),
            })
        result["generation_endpoints"] = result["generation_endpoints"][:15]
        result["api_contract_detected"] = bool(result["generation_endpoints"])
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, socket.timeout,
            ValueError, TypeError, OSError, json.JSONDecodeError) as err:
        result["metadata_error_type"] = type(err).__name__
    return result

def inspect_all() -> dict:
    inventory = [inspect_provider(n, url) for n,url in PROVIDERS]
    return {
        "schema_version": 1,
        "public_contract_only": True,
        "providers_checked": len(inventory),
        "providers_with_generation_endpoints": sum(bool(p.get("generation_endpoints")) for p in inventory),
        "any_gpu_generation_verified": False,
        "any_unlimited_zero_cost_verified": False,
        "private_media_transferred": False,
        "providers": inventory,
    }

def main() -> int:
    data=inspect_all()
    filename=Path("public-gpu-contract-audit.json")
    filename.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(data,indent=2,ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
