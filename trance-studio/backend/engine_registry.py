"""Versioned creative engine catalog for zero-cost-first Kolbo production.

This is the single place to declare which capabilities are locally available,
which need external public providers, and which cannot promise an output.
New providers can be introduced without changing the Android package or UI.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass
import importlib.util
import shutil


ENGINE_API_VERSION=1

@dataclass(frozen=True)
class CreativeEngine:
    id:str
    task:str
    kind:str
    ready:bool
    default:bool
    output:str
    quota_limited:bool=False
    needs_consent:bool=False
    note:str=""


def catalog():
    """Report installed capability only. 'ready' never implies GPU quota."""
    music=[
        CreativeEngine(
            id="kolbo-dj-v3",task="music",kind="local-dsp",
            ready=True,default=True,output="audio/mpeg",
            note="מקצבים, הלחנה חישובית ומעברי DJ; אינו מודל מוזיקה גנרטיבי"),
    ]
    speech=[
        CreativeEngine(
            id="kolbo-vocal-fx-v3",task="vocal-fx",kind="local-dsp",
            ready=True,default=True,output="audio/mpeg",
            note="אפקטים מתוך ההקלטה, לרבות מצב מיני־רמיקס למילה אחת")
    ]
    extract=[
        CreativeEngine(
            id="public-social-extractor",task="media-import",kind="local-tool",
            ready=importlib.util.find_spec("yt_dlp") is not None and
                  shutil.which("ffprobe") is not None,
            default=True,output="audio/video",
            note="רק קישורים ציבוריים מותרים ובעלי זכויות שימוש")
    ]
    generative=[
        CreativeEngine(
            id="public-zero-gpu-video",task="video",kind="external-public-ai",
            ready=True,default=True,output="video/mp4",
            quota_limited=True,needs_consent=True,
            note="זמינות מנועי AI חיצוניים אינה מובטחת; אין הבטחת MP4"),
        CreativeEngine(
            id="kolbo-remix-existing",task="video",kind="local-ffmpeg",
            ready=shutil.which("ffmpeg") is not None,default=False,
            output="video/mp4",
            note="עורך את הסרטון המקורי, ואינו יוצר סצנות AI חדשות")
    ]
    return {
        "api_version":ENGINE_API_VERSION,
        "selection_policy":"local-dsp-first-public-ai-when-user-consents",
        "music":[asdict(x) for x in music],
        "vocal_fx":[asdict(x) for x in speech],
        "import":[asdict(x) for x in extract],
        "video":[asdict(x) for x in generative],
        "promises_unlimited_public_gpu":False,
    }
