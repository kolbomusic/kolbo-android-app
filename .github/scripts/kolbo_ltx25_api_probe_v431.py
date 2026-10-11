"""Investigate public ZeroGPU LTX-2.5 native video+audio API without GPU submission.

This reads Gradio public endpoint descriptions only. It does NOT send user
photos/prompts or consume inference credits. No account token or payments.
"""
import json
import os
import sys
from gradio_client import Client
SPACES=[
    "ChopperBlu/ltx-2-5-demo",
    "Gangsternerd/ltx-2-5-demo",
]
for space in SPACES:
    print("PROBE",space,flush=True)
    try:
        client=Client(space,verbose=False)
        api=client.view_api(return_format="dict")
        data=api
        print("RESULT",space,json.dumps(data,default=str,ensure_ascii=False)[:30000],flush=True)
    except Exception as exc:
        print("UNAVAILABLE",space,type(exc).__name__,str(exc)[:650],flush=True)
