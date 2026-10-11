"""Free demo two-person STAGE SCENE image editor.

FLUX Kontext takes one collage containing both reference identities and
attempts to synthesize ONE new shared stage. This may change faces and
outfits and cannot certify identity, exact city, audience count or singing.
This model runs on a public shared GPU with unknown quotas; images are shared
with the third-party host. NO paid key, NO retries after uncertain submit.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from pathlib import Path
from typing import Callable
from PIL import Image, ImageStat,ImageChops,UnidentifiedImageError
import os,time

SPACE="black-forest-labs/FLUX.1-Kontext-dev"
MAX_INPUT=5_000_000

class SceneUnavailable(RuntimeError):pass
class SceneUncertain(RuntimeError):pass

@dataclass(frozen=True)
class SceneReceipt:
    generated_new_scene:bool
    source:str
    pixel_difference_mean:float
    two_subject_identity_verified:bool=False
    specified_venue_verified:bool=False
    crowd_count_verified:bool=False
    faces_preserved_verified:bool=False
    free_gpu_unlimited:bool=False
    license_commercial_verified:bool=False
    def as_dict(self):return asdict(self)

def validate(*,source:Path,prompt:str,consent:bool,commercial:bool) ->None:
    if os.getenv("KOLBO_SCENE_BUILDER_V433")!="EXPLICITLY_ENABLED":
        raise SceneUnavailable("Scene builder trial not enabled")
    if os.getenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA")!="EXPLICITLY_ENABLED":
        raise SceneUnavailable("External photo transfer disabled")
    if not consent:
        raise SceneUnavailable("Third-party stage-image transfer needs explicit consent")
    if commercial:
        raise SceneUnavailable("FLUX Kontext commercial permissions unverified")
    if not isinstance(prompt,str) or not 5<=len(prompt.strip())<=3000:
        raise SceneUnavailable("Stage prompt missing")
    if (source.is_symlink() or not source.is_file() or
            not 100<=source.stat().st_size<=MAX_INPUT or
            source.suffix.lower() not in (".png",".jpg",".jpeg",".webp")):
        raise SceneUnavailable("Composite reference is missing or unsafe")

def build(*,source:Path,prompt:str,destination:Path,consent:bool,
          commercial:bool=False,client_factory:Callable|None=None,
          handle_file_fn:Callable|None=None,wait_seconds:int=450)->SceneReceipt:
    source,destination=Path(source),Path(destination)
    validate(source=source,prompt=prompt,consent=consent,commercial=commercial)
    if destination.exists():raise SceneUnavailable("Output already exists")
    with Image.open(source) as im:
        original=im.convert("RGB").resize((512,512))
    scene_prompt=(
        "Transform the two separate reference portraits into ONE NEW "
        "natural cinematic scene, with both original people together "
        "standing on the SAME shared stage in a coherent perspective. "
        "Do not preserve source image backgrounds, vertical portrait "
        "borders, collage layout, a split screen, or framed photographs. "
        "There must be exactly two featured performers, one on each "
        "side, with microphones, crowd in front, stage lighting and "
        "concert context. Keep separate identities as closely as the "
        "model can, but never invent or blend additional foreground faces. "
        "Perform the following creative scene specification: "
        +prompt)
    if client_factory is None or handle_file_fn is None:
        from gradio_client import Client,handle_file
        client_factory=client_factory or Client
        handle_file_fn=handle_file_fn or handle_file
    try:
        client=client_factory(SPACE,verbose=False)
        job=client.submit(handle_file_fn(str(source)),scene_prompt,
                    42,False,2.5,16,api_name="/infer")
    except Exception as e:
        raise SceneUncertain("Public scene model request may have been accepted") from e
    until=time.monotonic()+wait_seconds
    while not job.done() and time.monotonic()<until:
        time.sleep(5)
    if not job.done():
        job.cancel()
        raise SceneUncertain("Scene creation timed out; not resubmitting")
    try:
        response=job.result()
        result=response[0] if isinstance(response,(list,tuple)) and response else None
        if isinstance(result,dict):result=result.get("path") or result.get("name")
        output=Path(result) if isinstance(result,str) else None
        if output is None or not output.is_file() or output.is_symlink():
            raise SceneUnavailable("Public scene editor returned no image")
        with Image.open(output) as image:
            if image.format not in ("PNG","JPEG","WEBP"):
                raise SceneUnavailable("Invalid model image format")
            if image.width<256 or image.height<256 or image.width*image.height>8_000_000:
                raise SceneUnavailable("Invalid model image dimensions")
            new=image.convert("RGB").resize((512,512))
            difference=sum(ImageStat.Stat(ImageChops.difference(
                original,new)).mean)/3.0
            if difference<18:
                raise SceneUnavailable("Scene model only reproduced input portraits")
            destination.parent.mkdir(parents=True,exist_ok=True)
            with destination.open("xb") as dest:
                new.save(dest,"PNG")
        return SceneReceipt(True,SPACE,round(difference,4))
    except (SceneUnavailable,SceneUncertain):
        raise
    except Exception as exc:
        raise SceneUnavailable("Cannot verify output of public scene editor") from exc
