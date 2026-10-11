"""Optional LOCAL face-preserving stage repair before any video-GPU call.

A direct comparison shows FLUX can invent replacement faces. To give the
generation one deterministic, FREE chance at retaining original appearance,
map the ORIGINAL source face pixels onto the freshly generated stage's facial
landmarks and blend locally (OpenCV); then run the strict YuNet/SFace verifier
AGAIN. If it still fails, DO NOT send the video GPU job.

This is not a photorealism guarantee, may result in visible seams, and is
disabled until local tests/calibration are approved.
No external face-swap/biometric API, face database, user-identification or
retry of any paid/free remote GPU provider.
"""
from pathlib import Path
from PIL import Image
import os
from identity_guard_v435 import OpenCVExtractor,IdentityUnavailable,IdentityMismatch

class RepairUnavailable(RuntimeError):pass

def enabled()->bool:
    return os.getenv("KOLBO_LOCAL_FACE_REPAIR")=="EXPLICITLY_ENABLED"

def _detect_two(extractor,photo):
    import cv2
    img=cv2.imread(str(photo),cv2.IMREAD_COLOR)
    if img is None or img.shape[0]<128 or img.shape[1]<128:
        raise RepairUnavailable("Invalid local face repair input")
    extractor.detector.setInputSize((img.shape[1],img.shape[0]))
    try:_,faces=extractor.detector.detect(img)
    except Exception as exc:raise RepairUnavailable("Face landmarks unavailable") from exc
    if faces is None or len(faces)!=2:
        raise RepairUnavailable("Exactly two local faces required for face repair")
    faces=sorted(faces,key=lambda row:float(row[0]+row[2]*.5))
    if faces[1][0]-faces[0][0] < img.shape[1]*.07:
        raise RepairUnavailable("Source face positions overlap")
    return img,faces

def reconstruct(source:Path,stage:Path,destination:Path,
                extractor:OpenCVExtractor|None=None)->Path:
    if not enabled():
        raise RepairUnavailable("Local face reconstruction not activated")
    source,stage,destination=Path(source),Path(stage),Path(destination)
    if source.is_symlink() or stage.is_symlink() or destination.exists():
        raise RepairUnavailable("Untrusted or existing face repair file")
    verifier=extractor or OpenCVExtractor()
    cv2=verifier.cv2
    src,src_faces=_detect_two(verifier,source)
    target,dst_faces=_detect_two(verifier,stage)
    import numpy as np
    for from_face,to_face in zip(src_faces,dst_faces):
        src_landmarks=np.array(from_face[4:14],dtype=np.float32).reshape((5,2))
        dst_landmarks=np.array(to_face[4:14],dtype=np.float32).reshape((5,2))
        transform,_=cv2.estimateAffinePartial2D(src_landmarks,dst_landmarks,
              method=cv2.LMEDS)
        if transform is None:
            raise RepairUnavailable("Cannot align reference facial landmarks")
        width,height=target.shape[1],target.shape[0]
        warped=cv2.warpAffine(src,transform,(width,height),
              flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
        mask=np.zeros(src.shape[:2],dtype=np.uint8)
        x,y,w,h=(int(v) for v in from_face[:4])
        center=(int(x+w*.5),int(y+h*.53))
        axes=(max(1,int(w*.53)),max(1,int(h*.59)))
        cv2.ellipse(mask,center,axes,0,0,360,255,-1)
        dest_mask=cv2.warpAffine(mask,transform,(width,height))
        # Feather edges. Note: masks never include surrounding gallery border.
        blurred=cv2.GaussianBlur(dest_mask,(0,0),sigmaX=4,sigmaY=4)
        alpha=(blurred.astype(np.float32)/255.0)[:,:,None]
        target=(warped.astype(np.float32)*alpha+
                target.astype(np.float32)*(1-alpha)).clip(0,255).astype(np.uint8)
    destination.parent.mkdir(parents=True,exist_ok=True)
    if not cv2.imwrite(str(destination),target):
        raise RepairUnavailable("Local facial compositing failed")
    return destination
