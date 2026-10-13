"""One and only one authorized anonymous LTX-2.5 ZeroGPU test.
No tokens or private images. Never retries a GPU submission.
"""
import json, os, sys, time, urllib.request, urllib.error
from urllib.parse import urlsplit
BASE="https://lightricks-ltx-2-5.hf.space"
HEADERS={"Accept":"application/json","User-Agent":"Kolbo-Open-Free-Model-Single-Proof/1.0"}
def call(path,data=None,timeout=25):
    headers=dict(HEADERS)
    if data is not None: headers["Content-Type"]="application/json"
    req=urllib.request.Request(BASE+path,data=data,headers=headers,method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req,timeout=timeout) as r:
        b=r.read(120_001)
        if len(b)>120_000:raise ValueError("response too large")
        return json.loads(b.decode("utf-8"))
def main():
    import hashlib
    meta=call("/gradio_api/info")
    run=(meta.get("named_endpoints") or {}).get("/run",{})
    required=["prompt","image_path","height","width","duration_s","seed","decoder","auto_len","randomize_seed","do_enhance"]
    actual=[x.get("parameter_name") for x in run.get("parameters",[])]
    if actual!=required:raise SystemExit("API input contract changed, no GPU work submitted")
    minDuration=next(x for x in run["parameters"] if x["parameter_name"]=="duration_s")
    # One tiny synthetic animated scene, prompt designed to test actual temporal motion.
    prompt="A tiny blue paper boat moves forward through shallow rippling water, fixed tripod close-up camera, daylight; realistic splashing and water ambience. No people, no text."
    args=[prompt,None,512,512,1.0,42,"conv",False,False,False]
    raw=json.dumps({"data":args},separators=(",",":")).encode("utf-8")
    receipt={"submitted_once":False,"gpu_run_success":False,"video_file_valid":False,
             "audio_verified":False,"charge_usd":0,"provider":"Lightricks/LTX-2.5",
             "api":"/run","no_auth":True,"no_private_media":True}
    print("ONE_ANONYMOUS_GPU_ATTEMPT (no paid fallback)")
    start=time.monotonic()
    try:
        # IMPORTANT: never resubmit on any response ambiguity or timeout.
        receipt["submitted_once"]=True
        submit=call("/gradio_api/call/v2/run",raw,timeout=45)
        event=submit.get("event_id")
        if not isinstance(event,str) or len(event)>128 or not event.replace("-","").replace("_","").isalnum():
            receipt["failure"]="provider_did_not_accept";return receipt
        receipt["accepted"]=True
        endpoint=BASE+"/gradio_api/call/run/"+event
        req=urllib.request.Request(endpoint,headers={"Accept":"text/event-stream","User-Agent":HEADERS["User-Agent"]})
        deadline=time.monotonic()+440
        with urllib.request.urlopen(req,timeout=60) as stream:
            kind=None
            while time.monotonic()<deadline:
                line=stream.readline(120_000)
                if not line:
                    receipt["failure"]="stream_closed";break
                line=line.decode("utf-8","replace").rstrip("\r\n")
                if line.startswith("event:"): kind=line.split(":",1)[1].strip()
                elif line.startswith("data:"):
                    if kind=="error":
                        receipt["failure"]="provider_rejected_or_failed";break
                    if kind=="complete":
                        try: payload=json.loads(line[5:].strip())
                        except json.JSONDecodeError:
                            receipt["failure"]="bad_result";break
                        if not isinstance(payload,list) or not payload:
                            receipt["failure"]="missing_video";break
                        obj=payload[0]
                        location=obj.get("url") if isinstance(obj,dict) else obj
                        if not isinstance(location,str):
                            receipt["failure"]="missing_video_url";break
                        u=urlsplit(location)
                        if u.scheme!="https" or not (u.hostname=="lightricks-ltx-2-5.hf.space" or u.hostname.endswith(".hf.space")):
                            receipt["failure"]="untrusted_video_origin";break
                        os.makedirs("result",exist_ok=True)
                        out="result/synthetic-ai.mp4"
                        with urllib.request.urlopen(urllib.request.Request(location,headers={"User-Agent":HEADERS["User-Agent"]}),timeout=90) as remote,open(out,"wb") as f:
                            total=0
                            while True:
                                chunk=remote.read(256*1024)
                                if not chunk:break
                                total+=len(chunk)
                                if total>100_000_000:raise ValueError("huge video")
                                f.write(chunk)
                        with open(out,"rb") as f: header=f.read(12)
                        if total<1024 or header[4:8]!=b"ftyp":receipt["failure"]="not_mp4";break
                        receipt["gpu_run_success"]=True
                        receipt["video_file_valid"]=True
                        receipt["video_bytes"]=total
                        receipt["video_sha256"]=hashlib.file_digest(open(out,"rb"),"sha256").hexdigest()
                        break
        return receipt
    except urllib.error.HTTPError as e:
        receipt["failure"]="http_"+str(e.code)
        return receipt
    except Exception as e:
        receipt["failure"]="network_or_provider_"+type(e).__name__
        return receipt
    finally:
        receipt["elapsed_s"]=round(time.monotonic()-start)
if __name__=="__main__":
    r=main()
    os.makedirs("result",exist_ok=True)
    with open("result/receipt.json","w") as f:json.dump(r,f,indent=2)
    print(json.dumps(r,indent=2))
    if not r["gpu_run_success"]:raise SystemExit("no AI video generated; no retries or paid fallback")
