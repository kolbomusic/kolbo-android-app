"""Grounded Hebrew ASR of original uploads on the small free CPU worker.

Never use the remix for speech recognition, never invent transcript text.
The preloaded multilingual base model is preferable to tiny for Hebrew; on
short WhatsApp messages VAD can discard speech, hence bounded retries.
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
from pathlib import Path

HEBREW = re.compile(r"[\u0590-\u05ff]")
_LOCK = threading.Lock()
_MODEL = None


class SourceTranscriptionUnavailable(RuntimeError):
    """Original recordings did not yield credible Hebrew speech."""


def _valid_utterance(text: str) -> bool:
    words = re.findall(r"[\u05d0-\u05ea]{2,}", str(text or ""))
    return len(words) >= 2 and len(set(words)) >= 2 and len(HEBREW.findall(text)) >= 3


def _get_model():
    global _MODEL
    with _LOCK:
        if _MODEL is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise SourceTranscriptionUnavailable("מנוע התמלול בשרת אינו מותקן") from exc
            # Prefer the build-bundled model; avoid a first-request network fetch.
            model_name = os.getenv("KOLBO_ASR_MODEL", "base")
            if model_name not in {"tiny", "base", "small"}:
                model_name = "base"
            preloaded = os.getenv("KOLBO_ASR_DIR", "").strip()
            if preloaded and (Path(preloaded) / "model.bin").is_file():
                model_name = preloaded
            try:
                _MODEL = WhisperModel(
                    model_name, device="cpu", compute_type="int8",
                    cpu_threads=1, num_workers=1,
                )
            except Exception as exc:
                raise SourceTranscriptionUnavailable("לא ניתן לטעון את מודל זיהוי הדיבור") from exc
    return _MODEL


def _recognize(model, path, *, use_vad, return_segments=False):
    # No prompting with specific actors or events: this could hallucinate
    # the user's intended movie instead of recognizing the actual recording.
    options = {
        "language": "he", "task": "transcribe", "beam_size": 5,
        "temperature": 0, "vad_filter": use_vad,
        "condition_on_previous_text": False,
        "hallucination_silence_threshold": 1.5,
        "no_speech_threshold": 0.55,
    }
    if use_vad:
        # Default VAD can discard a whole 1-3 second WhatsApp utterance.
        options["vad_parameters"] = {
            "min_silence_duration_ms": 300, "speech_pad_ms": 300,
        }
    segments, _info = model.transcribe(str(path), **options)
    recognized = []
    timed = []
    for segment in segments:
        utterance = str(getattr(segment, "text", "") or "").strip()
        if not utterance:
            continue
        # Missing metadata on test doubles or older versions is fine; do not
        # accept explicitly low-confidence or probable silence as a fact.
        logprob = getattr(segment, "avg_logprob", None)
        silence = getattr(segment, "no_speech_prob", None)
        if logprob is not None and float(logprob) < -1.2:
            continue
        if silence is not None and float(silence) > 0.80:
            continue
        recognized.append(utterance)
        if return_segments and len(timed)<80:
            try:
                start=float(segment.start)
                end=float(segment.end)
                if 0<=start<end<=125:
                    timed.append({"start":round(start,3),"end":round(end,3),
                                  "text":utterance[:400]})
            except (AttributeError,TypeError,ValueError):
                pass
    text=" ".join(recognized).strip()
    return (text,timed) if return_segments else text


def _clean_voice(path):
    """Produce a temporary normalized 16k source WAV for one last ASR pass.

    The input is ALWAYS the WhatsApp original, never voice-only remix or DJ
    audio. This retry helps with muffled, low-volume and OPUS voice messages.
    """
    src = Path(path)
    dest = src.with_name(src.stem + "-asr-normalized.wav")
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
        "-af", "highpass=f=90,lowpass=f=7000,"
               "acompressor=threshold=0.05:ratio=2.5:attack=5:release=80,"
               "alimiter=limit=0.96",
        "-f", "wav", str(dest),
    ]
    try:
        subprocess.run(command, check=True, timeout=25, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        if not dest.is_file() or dest.stat().st_size < 8000:
            raise ValueError("Normalized audio was empty")
        return dest
    except (OSError, ValueError, subprocess.SubprocessError):
        dest.unlink(missing_ok=True)
        return None


def transcribe_original_files(paths, progress=None, return_timeline=False):
    """Return (recognized words, complete[, per-file timed speech]) from originals.

    Each source gets a VAD pass, then a no-VAD pass if necessary, and a
    normalized-input retry if neither found credible Hebrew text. Unsupported
    material remains unrecognized; no fabricated words are added.
    """
    model = _get_model()
    transcripts = []
    timeline = []
    completed = True
    for index, path in enumerate(paths):
        if progress:
            progress("מזהה דיבור בעברית מהקלטה " + str(index + 1) +
                     " מתוך " + str(len(paths)))
        utterance = ""
        timed = []
        for use_vad in (True, False):
            try:
                if return_timeline:
                    utterance,timed = _recognize(model,path,use_vad=use_vad,
                                                 return_segments=True)
                else:
                    utterance = _recognize(model,path,use_vad=use_vad)
                if _valid_utterance(utterance):
                    break
            except (OSError, RuntimeError, ValueError):
                pass
        if not _valid_utterance(utterance):
            if progress:
                progress("משפר את הצלילות ומנסה לזהות שוב דיבור מהמקור")
            normalized = _clean_voice(path)
            if normalized:
                try:
                    if return_timeline:
                        utterance,timed=_recognize(model,normalized,use_vad=False,
                                                  return_segments=True)
                    else:
                        utterance = _recognize(model, normalized, use_vad=False)
                except (OSError, RuntimeError, ValueError):
                    utterance = ""
                finally:
                    normalized.unlink(missing_ok=True)
        if _valid_utterance(utterance):
            transcripts.append(utterance)
            timeline.append(timed)
        else:
            timeline.append([])
            completed = False
    result = ". ".join(transcripts)[:4000]
    if not _valid_utterance(result):
        raise SourceTranscriptionUnavailable(
            "לא זוהה דיבור עברי אמין מההקלטות גם לאחר ניסיונות פענוח נוספים"
        )
    return (result,completed,timeline) if return_timeline else (result,completed)
