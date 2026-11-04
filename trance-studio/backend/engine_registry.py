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
    requires_payment:bool=False
    note:str=""


def catalog():
    """Report installed capability only. 'ready' never implies GPU quota."""
    from audio_tools import FREE_VOICE_MODES
    sound_labels={
        "speech_clean":"ניקוי דיבור","podcast":"פודקאסט והבהרת קול",
        "radio":"שדר רדיו","telephone":"טלפון ישן",
        "megaphone":"מגפון","robot":"רובוט","chorus":"מקהלת קולות",
        "flanger":"פלנג׳ר","delay":"הד DJ","room":"הדהוד חדר",
        "tremolo":"טרמולו","slow":"האטת קצב","fast":"האצת קצב",
        "pitch_up":"העלאת טון","pitch_down":"הורדת טון",
        "reverse":"השמעה לאחור"
    }
    sound_lab=[
        CreativeEngine(
            id="ffmpeg-"+effect,task="sound-fx",kind="local-ffmpeg",
            ready=shutil.which("ffmpeg") is not None,
            default=False,output="audio/mpeg",
            note=sound_labels.get(effect,effect)+" — ללא מנוי או GPU")
        for effect in FREE_VOICE_MODES
    ]
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
            ready=True,default=False,output="video/mp4",
            quota_limited=True,needs_consent=True,
            note="שימוש ציבורי אנונימי בלבד, מכסה חינמית מוגבלת; אין מנוי, אסימון חיוב, רכישת קרדיטים או הבטחת MP4"),
        CreativeEngine(
            id="kolbo-remix-existing",task="video",kind="local-ffmpeg",
            ready=shutil.which("ffmpeg") is not None,default=True,
            output="video/mp4",
            note="עורך את הסרטון המקורי, ואינו יוצר סצנות AI חדשות")
    ]
    # No model weights are shipped on the tiny Render Free server.
    # Reporting these as disabled is intentional: central/side cancellation
    # must never be called AI source separation or singer voice conversion.
    separate=[
        CreativeEngine(
            id="demucs-two-stem",task="source-separation",
            kind="optional-local-ml",ready=False,default=False,
            output="audio/wav",
            note="נדרש מודל הפרדת שירה וליווי שהותקן ואומת; כרגע לא זמין בענן")
    ]
    voice_cover=[
        CreativeEngine(
            id="authorized-singing-voice-conversion",task="ai-cover",
            kind="optional-ml-model",ready=False,default=False,
            output="audio/mpeg",needs_consent=True,
            note="נדרש מודל המרת קול בשירה ודוגמת קול מורשית; אינו מחובר עדיין")
    ]
    return {
        "api_version":ENGINE_API_VERSION,
        "selection_policy":"local-dsp-first-public-ai-when-user-consents",
        "music":[asdict(x) for x in music],
        "vocal_fx":[asdict(x) for x in speech],
        "sound_lab":[asdict(x) for x in sound_lab],
        "import":[asdict(x) for x in extract],
        "video":[asdict(x) for x in generative],
        "separation":[asdict(x) for x in separate],
        "voice_cover":[asdict(x) for x in voice_cover],
        "promises_unlimited_public_gpu":False,
        "billing_enabled":False,
        "supports_payment":False,
        "uses_paid_api_tokens":False,
        "public_ai_mode":"anonymous_free_quota_only",
        "cost_policy":"local_processing_first; no upgrades or credit purchases",
    }
