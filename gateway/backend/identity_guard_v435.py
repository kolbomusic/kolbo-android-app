"""Kolbo Video 4.3.5: local strict two-face *resemblance* gate.

No name/person identification, uploads to face-recognition services,
persistent embeddings, logging of embeddings, or facial recognition database.
The user-provided combined portraits and model outputs are compared only
inside this single authorized video job. The score is NOT proof of identity;
facial resemblance classifiers can err and are unreliable at extreme poses.

OpenCV Zoo YuNet (face landmarks) + SFace int8 (face feature) CPU backend.
Models are Apache-2.0-listed Zoo files, SHA256 pinned in Docker.
No OpenCV/model dependencies? Fail closed BEFORE contacting free GPU.
"""
from __future__ import annotations

from dataclasses import dataclass,asdict
from pathlib import Path
from typing import Protocol, Any
from functools import lru_cache
import hashlib
import os

DETECTOR_NAME="face_detection_yunet_2023mar.onnx"
MATCHER_NAME="face_recognition_sface_2021dec_int8.onnx"
DETECTOR_SHA="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
MATCHER_SHA="2b0e941e6f16cc048c20aee0c8e31f569118f65d702914540f7bfdc14048d78a"

# Deliberately stricter than OpenCV SFace baseline 0.363 cosine threshold.
# NOT universal/calibrated across demographic subgroups or camera conditions.
MIN_SAME_SCORE=0.45
MIN_CROSS_MARGIN=0.085
MIN_LEFT_RIGHT_SEPARATION=0.055

class IdentityUnavailable(RuntimeError):pass
class IdentityMismatch(ValueError):pass

@dataclass(frozen=True)
class IdentityScores:
    source_faces:int
    result_faces:int
    left_similarity:float
    right_similarity:float
    minimum_wrong_pair_margin:float
    left_right_not_swapped:bool
    checked_by:str="YuNet+SFace-int8 (local CPU)"
    same_real_people_guaranteed:bool=False

    def as_dict(self)->dict:return asdict(self)

class Extractor(Protocol):
    def embeddings(self,image:Path)->list[tuple[float,Any]]:...
    def cosine(self,a:Any,b:Any)->float:...

def _checksum(path:Path,expected:str)->bool:
    try:
        if path.is_symlink() or not path.is_file():return False
        if not 20000<=path.stat().st_size<=30_000_000:return False
        with path.open("rb") as handle:return hashlib.file_digest(handle,"sha256").hexdigest()==expected
    except (OSError,ValueError):return False

def model_paths()->tuple[Path,Path]:
    base=Path(os.getenv("KOLBO_LOCAL_FACE_MODELS_DIR","/app/face-models"))
    return base/DETECTOR_NAME,base/MATCHER_NAME

def models_present()->bool:
    detector,recognizer=model_paths()
    return _checksum(detector,DETECTOR_SHA) and _checksum(recognizer,MATCHER_SHA)

def configured()->bool:
    return (os.getenv("KOLBO_STRICT_FACE_GUARD")=="EXPLICITLY_ENABLED"
            and models_present())

class OpenCVExtractor:
    def __init__(self):
        if not configured():
            raise IdentityUnavailable("Local facial resemblance models are not verified")
        try:
            import cv2
        except ImportError as e:
            raise IdentityUnavailable("OpenCV face backend unavailable") from e
        cv2.setNumThreads(1)
        detector_path,matcher_path=model_paths()
        try:
            self.cv2=cv2
            self.detector=cv2.FaceDetectorYN.create(str(detector_path),"",(320,320),
                score_threshold=0.85,nms_threshold=0.3,top_k=10)
            self.recognizer=cv2.FaceRecognizerSF.create(str(matcher_path),"")
        except Exception as e:
            raise IdentityUnavailable("Face backend could not load its verified models") from e

    def embeddings(self,image:Path)->list[tuple[float,Any]]:
        cv2=self.cv2
        try:
            src=cv2.imread(str(image),cv2.IMREAD_COLOR)
            if src is None:
                raise IdentityMismatch("Could not decode reference faces")
            h,w=src.shape[:2]
            if h<128 or w<128 or h*w>4_000_000:
                raise IdentityMismatch("Face image out of bounded resolution")
            self.detector.setInputSize((w,h))
            _,faces=self.detector.detect(src)
            result=[]
            if faces is None:return result
            for row in faces:
                x,y,fw,fh=row[:4]
                if fw<24 or fh<24:continue
                crop=self.recognizer.alignCrop(src,row)
                feat=self.recognizer.feature(crop)
                result.append((float(x+fw*.5)/w,feat.copy()))
            return sorted(result,key=lambda item:item[0])
        except IdentityMismatch:raise
        except Exception as e:
            raise IdentityUnavailable("Unable to extract faces without reliable evidence") from e

    def cosine(self,a:Any,b:Any)->float:
        try:
            return float(self.recognizer.match(
                a,b,self.cv2.FaceRecognizerSF_FR_COSINE))
        except Exception as e:
            raise IdentityUnavailable("Cannot compare local face features") from e

def compare_slots(reference:list[tuple[float,Any]],
                  candidate:list[tuple[float,Any]],
                  extractor:Extractor)->IdentityScores:
    if len(reference)!=2:
        raise IdentityMismatch("Two distinct visible source faces are required")
    if len(candidate)!=2:
        raise IdentityMismatch("Exactly two visible candidate faces are required")
    if reference[1][0]-reference[0][0]<.08:
        raise IdentityMismatch("Source faces overlap, cannot preserve separate slots")
    if candidate[1][0]-candidate[0][0]<.08:
        raise IdentityMismatch("Generated faces overlap, cannot verify both identities")
    a,b=reference[0][1],reference[1][1]
    left,right=candidate[0][1],candidate[1][1]
    aa=extractor.cosine(a,left)
    bb=extractor.cosine(b,right)
    ab=extractor.cosine(a,right)
    ba=extractor.cosine(b,left)
    cross=extractor.cosine(a,b)
    score_margin=min(aa-ab,bb-ba)
    if cross>min(aa,bb)-MIN_LEFT_RIGHT_SEPARATION:
        raise IdentityMismatch("Source identities too similar for reliable independent checking")
    if (min(aa,bb)<MIN_SAME_SCORE or score_margin<MIN_CROSS_MARGIN
        or aa<=ba or bb<=ab):
        raise IdentityMismatch("Generated face mismatch or left/right identities swapped")
    return IdentityScores(2,2,round(aa,4),round(bb,4),
        round(score_margin,4),True)

class JobIdentityGuard:
    """Ephemeral embeddings never returned to clients nor written to disk."""
    def __init__(self,source:Path,extractor:Extractor|None=None):
        self._extractor=extractor or OpenCVExtractor()
        self._reference=self._extractor.embeddings(Path(source))
        if len(self._reference)!=2:
            raise IdentityMismatch("Source must show exactly two detectable distinct faces")
        if self._extractor.cosine(self._reference[0][1],
                                  self._reference[1][1])>0.94:
            raise IdentityMismatch("Two separate identities could not be distinguished")

    def verify_still(self,still:Path)->IdentityScores:
        candidate=self._extractor.embeddings(Path(still))
        return compare_slots(self._reference,candidate,self._extractor)

    def verify_video(self,video:Path)->list[IdentityScores]:
        import subprocess,json,tempfile
        video=Path(video)
        try:
            meta=subprocess.run(["ffprobe","-v","error","-show_entries",
                "format=duration","-of","json",str(video)],check=True,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
            duration=float(json.loads(meta.stdout)["format"]["duration"])
        except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
            raise IdentityMismatch("Video frame sampling failed") from exc
        if not .9<=duration<=16:
            raise IdentityMismatch("Out-of-range video identity evidence")
        result=[]
        # Fixed sample positions catch identity drift throughout the video;
        # not exhaustive proof that ALL frames are preserved.
        with tempfile.TemporaryDirectory(prefix="kolbo-faces-") as temp:
            for idx,fraction in enumerate((.13,.51,.87)):
                output=Path(temp)/f"sample{idx}.png"
                try:
                    subprocess.run(["ffmpeg","-nostdin","-v","error","-y",
                        "-ss",str(max(.05,duration*fraction)),"-i",str(video),
                        "-frames:v","1",str(output)],check=True,
                        stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                        timeout=35)
                except (OSError,subprocess.SubprocessError) as e:
                    raise IdentityMismatch("Could not inspect video identities") from e
                result.append(compare_slots(self._reference,
                              self._extractor.embeddings(output),
                              self._extractor))
        return result

    def discard(self):
        self._reference=[]
