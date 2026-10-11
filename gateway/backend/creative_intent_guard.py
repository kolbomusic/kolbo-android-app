"""Strict creative intent preflight for Kolbo Video.

Fail-closed on known unsupported voice/sound/duet requests BEFORE any user
image reaches a third party. This is a conservative lexical guard, not an AI
semantic understanding engine or evidence that a generated film matches text.
Explicit request flags always take precedence over lexical detection.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import re

# Intent clues only. These lists are intentionally incomplete; a real product
# needs a structured storyboard/intent model, not an imagined "universal" regex.
SOUND = re.compile(
    r"(?:\b(?:audio|sound|sing|singing|sings|song|songs|music|"
    r"speaks?|says?|talks?|dialog(?:ue)?|voice|fart(?:s|ing)?|"
    r"burp(?:s|ing)?|sfx|narrat(?:ion|or)|lyrics|"
    r"lip[\s-]?sync)\b|"
    r"(?<![\u0590-\u05ff])(?:שיר(?:ה|ים)?|שר(?:ים|ה)?|שרה|"
    r"לשיר|מוזיקה|מנגינה|קול(?:ות)?|סאונד|צליל(?:ים)?|"
    r"דיבור|מדבר(?:ים|ת)?|אומר(?:ים|ת)?|מפליץ|מפליצים|"
    r"פליצ(?:ה|ות)|נפיח(?:ה|ות)|קריינ(?:ות|ית)|"
    r"שפתיים|דיאלוג)(?![\u0590-\u05ff]))",
    re.IGNORECASE,
)
LIPSYNC = re.compile(
    r"\b(?:lip[\s-]?sync|mouth[\s-]?synchroni[sz])\b|"
    r"(?:סנכרון\s*שפתיים|תנוע(?:ת|ות)\s*שפתיים|"
    r"השפתיים\s*(?:זזות|מותאמות))",re.IGNORECASE,
)
MULTI_IDENTITY = re.compile(
    r"\b(?:both\s+(?:characters|people|subjects)|two\s+(?:people|characters|persons)|"
    r"two\s+separate\s+(?:faces|people))\b|"
    r"(?:שתי\s+(?:דמויות|נשים)|שני\s+(?:אנשים|גברים|פרצופים)|"
    r"שניהם|שתיהן|שתיהם|שתי\s+התמונות|שתי\s+הדמויות)",
    re.IGNORECASE,
)
NEGATE_SOUND = re.compile(
    r"(?:\b(?:without|no)\s+(?:sound|audio|music|dialog(?:ue)?|voice)\b|"
    r"(?:בלי|ללא)\s+(?:קול|קולות|מוזיקה|שמע|דיבור|שירה|צליל))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CreativePlan:
    status: str
    provider: str | None
    supported_image_count: int
    requested_duration_seconds: float
    needs_audio: bool
    needs_lipsync: bool
    needs_two_independent_people: bool
    needs_commercial_rights: bool
    blockers: tuple[str, ...]
    limits: tuple[str, ...]
    consent_required: bool = True
    cost_verified_free: bool = False
    automatic_success_claim: bool = False

    def as_dict(self) -> dict:
        value = asdict(self)
        # JSON serializable arrays
        value["blockers"] = list(self.blockers)
        value["limits"] = list(self.limits)
        return value


def plan(*, prompt: str, seconds: float, image_count: int,
         requires_audio: bool = False,
         requires_lipsync: bool = False,
         requires_two_independent_people: bool = False,
         commercial_use: bool = False,
         consent: bool = False,
         compute_available: bool = False) -> CreativePlan:
    if not isinstance(prompt,str) or not 5 <= len(prompt.strip()) <= 3000:
        raise ValueError("Invalid creative request")
    if not isinstance(seconds,(int,float)) or isinstance(seconds,bool) or not 1<=seconds<=360:
        raise ValueError("Invalid requested seconds")
    if not isinstance(image_count,int) or isinstance(image_count,bool) or not 0<=image_count<=2:
        raise ValueError("Invalid reference count")
    # Do not infer that a prompt without sound keywords never needs sound.
    # Users and future models must carry explicit structured intent flags.
    sound_prompt = NEGATE_SOUND.sub(" ", prompt)
    audio=requires_audio or requires_lipsync or bool(SOUND.search(sound_prompt))
    lipsync=requires_lipsync or bool(LIPSYNC.search(sound_prompt))
    duo=requires_two_independent_people or image_count==2 or bool(MULTI_IDENTITY.search(prompt))
    blockers: list[str]=[]
    if image_count!=1:
        blockers.append("single_reference_only")
    if not 1 <= seconds <= 5:
        blockers.append("duration_unsupported")
    if audio:
        blockers.append("requested_audio_unavailable")
    if lipsync:
        blockers.append("lip_sync_unavailable")
    if duo:
        blockers.append("multiple_subject_identity_unavailable")
    if commercial_use:
        blockers.append("commercial_rights_not_verified")
    if not consent:
        blockers.append("external_image_transfer_consent_missing")
    if not compute_available:
        blockers.append("no_enabled_verified_free_gpu_route")
    if not blockers:
        # This only means a technically compatible *draft* can be requested,
        # not that content, identities or motion match the prompt.
        status="draft_possible"
    else:
        status="blocked"
    return CreativePlan(
        status=status,
        provider="zerogpu-wan2.2-experimental" if not blockers else None,
        supported_image_count=1,
        requested_duration_seconds=seconds,
        needs_audio=audio,
        needs_lipsync=lipsync,
        needs_two_independent_people=duo,
        needs_commercial_rights=commercial_use,
        blockers=tuple(blockers),
        limits=("human_semantic_review_required","identity_not_verified",
                "prompt_adherence_not_verified","audio_not_supported",
                "result_temporary_on_free_render"),
        consent_required=True,
        cost_verified_free=False,
        automatic_success_claim=False,
    )
