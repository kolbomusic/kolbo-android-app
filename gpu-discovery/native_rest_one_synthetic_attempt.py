#!/usr/bin/env python3
"""Anonymous one-request synthetic test of the exact REST protocol used by Android.
No personal media, token, auto retry or paid fallback. Public ZeroGPU can refuse.
"""
import io,json,struct,urllib.request,urllib.error,zlib,time,hashlib,subprocess
from pathlib import Path

HOST="zerogpu-aoti-wan2-2-fp8da-aoti-faster.hf.space"
BASE="https://"+HOST
OUT=Path("native-rest-proof")
OUT.mkdir(exist_ok=True)
receipt={"provider":HOST,"endpoint":"/generate_video","submitted":0,
         "user_photos_sent":False,"paid_fallback":False,"authenticated":False,
         "rest_workflow_verified":False}
def png():
    def chunk(name,data):
        return struct.pack(">I",len(data))+name+data+struct.pack(">I",zlib.crc32(name+data)&0xffffffff)
    w=h=256
    rgb=b"".join(b"\x00"+b"".join(b"\xf0\xc8\x20" if 90<x<165 and 90<y<165
                    else b"\x18\x30\x59" for x in range(w)) for y in range(h))
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">2I5B",w,h,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(rgb,7))+chunk(b"IEND",b"")
def get_json(path):
    req=urllib.request.Request(BASE+path,headers={"Accept":"application/json","User-Agent":"KolboNativeRESTProof/1.0"})
    with urllib.request.urlopen(req,timeout=25) as r:return json.loads(r.read(700000))
def post(path,data,ctype):
    req=urllib.request.Request(BASE+path,data=data,headers={"Content-Type":ctype,"Accept":"application/json","User-Agent":"KolboNativeRESTProof/1.0"})
    with urllib.request.urlopen(req,timeout=50) as r:return json.loads(r.read(700000))
def main():
    try:
        api=get_json("/gradio_api/info")
        endpoint=api["named_endpoints"]["/generate_video"]
        names=[x["parameter_name"] for x in endpoint["parameters"]]
        wanted=["input_image","prompt","steps","negative_prompt","duration_seconds",
                "guidance_scale","guidance_scale_2","seed","randomize_seed"]
        if names!=wanted:raise ValueError("public provider contract changed; no submit")
        photo=png(); boundary="KolboNativeRestProof"
        frame=(("--"+boundary+"\r\nContent-Disposition: form-data; name=\"files\"; filename=\"synthetic.png\"\r\n"
                "Content-Type: image/png\r\n\r\n").encode()+photo+
                ("\r\n--"+boundary+"--\r\n").encode())
        upload=post("/gradio_api/upload",frame,"multipart/form-data; boundary="+boundary)
        if not isinstance(upload,list) or not upload or not str(upload[0]).startswith("/"):
            raise ValueError("REST file upload contract incompatible")
        receipt["uploaded_synthetic_file"]=True
        file={"path":upload[0],"orig_name":"synthetic.png","mime_type":"image/png",
              "is_stream":False,"meta":{"_type":"gradio.FileData"}}
        args=[file,"A yellow origami square folds into a boat on a blue table. Continuous motion, medium shot.",
              8,"static frame, face closeup, text",2.0,1.0,1.0,42,False]
        receipt["submitted"]=1
        response=post("/gradio_api/call/generate_video",
                      json.dumps({"data":args}).encode("utf-8"),"application/json")
        event=response.get("event_id","")
        if not event or len(event)>160:raise ValueError("No event_id from REST call")
        receipt["event_id_received"]=True
        start=time.monotonic()
        req=urllib.request.Request(BASE+"/gradio_api/call/generate_video/"+event,
             headers={"Accept":"text/event-stream","User-Agent":"KolboNativeRESTProof/1.0"})
        with urllib.request.urlopen(req,timeout=390) as stream:
            event_name=""
            for raw in stream:
                if time.monotonic()-start>380:raise TimeoutError("job exceeds 380s")
                line=raw.decode("utf-8","replace").strip()
                if line.startswith("event:"):event_name=line[6:].strip()
                elif line.startswith("data:") and event_name=="complete":
                    data=json.loads(line[5:].strip())
                    if not isinstance(data,list) or not data:raise ValueError("missing video result")
                    receipt["returned_data_type"]=type(data[0]).__name__
                    receipt["rest_workflow_verified"]=True
                    break
                elif line.startswith("data:") and event_name=="error":
                    raise ValueError("provider generation error")
        if not receipt["rest_workflow_verified"]:raise TimeoutError("no complete event")
    except Exception as e:
        receipt["error_type"]=type(e).__name__
        receipt["error_summary"]=str(e)[:160]
    finally:
        (OUT/"receipt.json").write_text(json.dumps(receipt,indent=2))
        print(json.dumps(receipt,indent=2))
    return 0 if receipt["rest_workflow_verified"] else 1
if __name__=="__main__":raise SystemExit(main())
