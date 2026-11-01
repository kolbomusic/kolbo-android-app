"""Best-effort Hebrew ASR from the ORIGINAL uploaded media (never the remix).

A browser may lack OPUS decoding, enough RAM for Whisper WASM, or reliable
CDN access.  The server retries on the original uploaded file.  This is not
forced alignment and an ASR result must never be described as verified speech.
"""
from __future__ import annotations

import os
import re
import threading

HEBREW = re.compile(r"[\u0590-\u05ff]")
_LOCK = threading.Lock()
_MODEL = None


class SourceTranscriptionUnavailable(RuntimeError):
    """Neither a grounded transcript nor a usable ASR worker is available."""


def _valid_utterance(text: str) -> bool:
    words = str(text or "").strip().split()
    return len(words) >= 2 and len(HEBREW.findall(text)) >= 3 and len(set(words)) >= 2


def _get_model():
    global _MODEL
    with _LOCK:
        if _MODEL is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise SourceTranscriptionUnavailable("מנוע התמלול בשרת אינו מותקן") from exc
            # Tiny is an intentionally bounded CPU fallback for the free server;
            # the browser attempts the more accurate base model first.
            model_name = os.getenv("KOLBO_ASR_MODEL", "tiny")
            if model_name not in {"tiny", "base", "small"}:
                model_name = "tiny"
            try:
                _MODEL = WhisperModel(
                    model_name, device="cpu", compute_type="int8",
                    cpu_threads=2, num_workers=1,
                )
            except Exception as exc:
                raise SourceTranscriptionUnavailable("לא ניתן לטעון את מודל זיהוי הדיבור") from exc
    return _MODEL


def transcribe_original_files(paths, progress=None):
    """Return (text, completed) after genuine file-level transcription.

    completed=False means one or more original recordings were undecipherable;
    successful parts may still produce grounded visual beats. No invented text.
    """
    model = _get_model()
    transcripts = []
    completed = True
    for index, path in enumerate(paths):
        if progress:
            progress("מפענח הקלטת מקור "+str(index + 1)+" מתוך "+str(len(paths)))
        try:
            # PyAV used by faster-whisper can read OPUS/OGG/M4A/MP4. No
            # resynthesized voice, background music, or guessed words are fed in.
            segments, _info = model.transcribe(
                str(path), language="he", task="transcribe", beam_size=3,
                vad_filter=True, condition_on_previous_text=False,
                hallucination_silence_threshold=1.5,
            )
            utterance = " ".join(str(s.text or "").strip() for s in segments).strip()
            if not _valid_utterance(utterance):
                completed = False
                continue
            transcripts.append(utterance)
        except Exception:
            completed = False
    text = ". ".join(transcripts)[:4000]
    if not _valid_utterance(text):
        raise SourceTranscriptionUnavailable(
            "התמלול במכשיר ובשרת לא הצליח לזהות דיבור ברור מתוך קובצי המקור"
        )
    return text, completed
