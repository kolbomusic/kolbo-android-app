"""Privacy-preserving classification for the two-stage native video/audio pipeline.

No exception messages, prompts, media, face embeddings, bearer tokens or
network/third-party error strings are exposed in API responses or app logs.
Classification alone does NOT fix external ZeroGPU quotas or model quality.
"""
from __future__ import annotations
from dataclasses import dataclass
import experimental_ltx25_native_av as ltx
import experimental_scene_builder_v433 as stage
import identity_guard_v435 as face
import local_face_repair_v435 as repair
import scene_integrity_v433 as scene

PHASES=frozenset((
    "queued","source_face_check","shared_stage_generation",
    "shared_stage_face_check","local_face_repair",
    "native_video_audio_generation","video_media_quality_check",
    "video_face_check","publishing"))

@dataclass(frozen=True)
class SafeFailure:
    error:str
    detail:str
    phase:str
    retry_automatically:bool=False

def classify(exc:Exception,phase:str)->SafeFailure:
    phase=phase if phase in PHASES else "publishing"
    if isinstance(exc,face.IdentityUnavailable):
        return SafeFailure("face_guard_unavailable",
            "בדיקת הדמיון לפנים אינה זמינה בשרת. הסרטון לא נשלח לאישור.",phase)
    if isinstance(exc,face.IdentityMismatch):
        if phase=="source_face_check":
            return SafeFailure("source_faces_not_detected",
                "לא ניתן לזהות שתי פנים נפרדות בתמונת המקור שהורכבה. לא הופק סרטון.",phase)
        if phase in ("shared_stage_face_check","local_face_repair"):
            return SafeFailure("generated_stage_faces_changed",
                "בבניית הבמה הפנים השתנו או התחלפו. דחיתי את הסצנה לפני הנפשת הסרטון.",phase)
        return SafeFailure("video_faces_changed",
            "בסרטון שהופק אחת הדמויות אינה תואמת מספיק למקור. הסרטון נפסל.",phase)
    if isinstance(exc,repair.RepairUnavailable):
        return SafeFailure("local_face_repair_failed",
            "ניסיון תיקון הפנים המקומי לא הצליח; לא מפיקים סרטון עם פנים לא מאומתות.",phase)
    if isinstance(exc,stage.SceneUncertain):
        return SafeFailure("stage_provider_submission_uncertain",
            "שירות בניית הבמה הציבורי לא החזיר אישור חד־משמעי. כדי לא לבזבז מכסה לא מנסים שוב אוטומטית.",phase)
    if isinstance(exc,stage.SceneUnavailable):
        reason=getattr(exc,"reason","stage_not_available")
        if reason=="public_gpu_quota_or_busy":
            return SafeFailure("stage_public_gpu_quota_or_busy",
                "ההפקה נעצרה בשירות FLUX הציבורי בגלל מכסה או עומס GPU. אין עיבוד חלופי מאומת, ולכן לא הופק סרטון.",phase)
        if reason=="public_model_runtime_error":
            return SafeFailure("stage_model_execution_failed",
                "מנוע FLUX הציבורי נכשל במהלך יצירת תמונת הבמה. לא נשלח סרטון להנפשה.",phase)
        if reason=="unchanged_scene":
            return SafeFailure("stage_was_not_reconstructed",
                "מנוע FLUX לא יצר סצנה חדשה אלא שימר את תמונת המקור. התוצאה נפסלה.",phase)
        if reason=="invalid_provider_image":
            return SafeFailure("stage_returned_invalid_image",
                "FLUX החזיר תשובת תמונה חסרה, פגומה או בלתי נתמכת. הסרטון לא נוצר.",phase)
        return SafeFailure("stage_provider_unavailable",
            "שירות בניית הבמה הציבורי לא החזיר תמונת סצנה תקינה. לא נוצר סרטון.",phase)
    if isinstance(exc,ltx.UnknownAcceptance):
        return SafeFailure("video_provider_submission_uncertain",
            "שירות הווידאו והשמע הציבורי לא אישר את המשימה באופן חד־משמעי. לא מנסים שוב אוטומטית.",phase)
    if isinstance(exc,ltx.Unavailable):
        return SafeFailure("video_provider_unavailable",
            "שירות הווידאו והשמע הציבורי לא החזיר וידאו תקין או אינו זמין כרגע.",phase)
    if isinstance(exc,scene.SceneAnalysisError):
        return SafeFailure("video_scene_validation_failed",
            "בדיקת הסצנה בסרטון נכשלה; לא ניתן לאשר שקיימת תנועה תקינה.",phase)
    if isinstance(exc,ValueError) and phase=="video_media_quality_check":
        return SafeFailure("video_quality_rejected",
            "הווידאו נוצר, אך נכשל בבדיקת תנועה או פיצול תמונות; הסרטון נפסל.",phase)
    return SafeFailure("internal_processing_error",
        "השרת נתקל בתקלה פנימית במהלך ההפקה. הסרטון לא אושר.",phase)
