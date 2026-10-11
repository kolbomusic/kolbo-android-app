"""Deterministic source-role and scene-timeline contract (STAGING ONLY).

A scene plan is not AI footage. It prevents fake 10-second outputs assembled
from unsupported 3-second clips, accidental swapping of two people's identity
reference handles and claims of lip-sync unsupported by the model.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
import re,uuid

class UnsupportedScenePlan(ValueError):pass

@dataclass(frozen=True)
class SceneCapabilities:
    provider:str
    exact_seconds:tuple[int,...]
    independent_people:int
    supports_continuation_keyframes:bool
    supports_requested_audio:bool
    supports_bukhori_lipsync:bool
    commercial_use_approved:bool

@dataclass(frozen=True)
class SceneSegment:
    index:int
    id:str
    start_ms:int
    end_ms:int
    seconds:int
    provider:str
    person_one_reference:str|None
    person_two_reference:str|None
    prior_end_keyframe_required:bool
    end_keyframe_must_be_saved:bool
    audio_required:bool
    lip_sync_required:bool
    language:str
    source_identity_verified:bool=False

@dataclass(frozen=True)
class Timeline:
    job_id:str
    expected_ms:int
    segments:tuple[SceneSegment,...]
    semantic_continuity_verified:bool=False
    audio_synchronized_verified:bool=False

def build_timeline(job_id:str, *,seconds:int,
                   provider:SceneCapabilities,
                   person_one:str|None=None,person_two:str|None=None,
                   audio:bool=True,lip_sync:bool=False,
                   language:str='he',commercial:bool=False,
                   max_scenes:int=12)->Timeline:
    try:guid=str(uuid.UUID(job_id))
    except (TypeError,ValueError) as e:
        raise UnsupportedScenePlan('Invalid job ID') from e
    if not (type(seconds)is int and 1<=seconds<=60 and
            type(max_scenes)is int and 1<=max_scenes<=12):
        raise UnsupportedScenePlan('Requested duration or scene count unsupported')
    for handle in (person_one,person_two):
        if handle is not None:
            try:uuid.UUID(handle)
            except (TypeError,ValueError) as e:
                raise UnsupportedScenePlan('Reference handle must be an opaque UUID') from e
    if person_two is not None and person_one is None:
        raise UnsupportedScenePlan('Reference two cannot be used without reference one')
    if person_one and person_two and person_one==person_two:
        raise UnsupportedScenePlan('Two characters require two distinct references')
    count=int(person_one is not None)+int(person_two is not None)
    if count>provider.independent_people:
        raise UnsupportedScenePlan('Provider cannot preserve separate identity references')
    if audio and not provider.supports_requested_audio:
        raise UnsupportedScenePlan('Provider cannot produce requested audio')
    if lip_sync and not provider.supports_bukhori_lipsync and language=='bukhori':
        raise UnsupportedScenePlan('Bukhori lip-sync not verified on this provider')
    if commercial and not provider.commercial_use_approved:
        raise UnsupportedScenePlan('Commercial use not verified on provider')
    if not re.fullmatch('[a-z0-9_-]{3,64}',provider.provider):
        raise UnsupportedScenePlan('Untrusted provider')
    options=tuple(sorted(set(d for d in provider.exact_seconds
                         if type(d) is int and 1<=d<=seconds),reverse=True))
    if not options:raise UnsupportedScenePlan('Provider offers no compatible segment length')

    @lru_cache(None)
    def schedule(remaining:int)->tuple[int,...]|None:
        if remaining==0:return ()
        candidates=[]
        for duration in options:
            if duration>remaining:continue
            remainder=schedule(remaining-duration)
            if remainder is not None and len(remainder)<max_scenes:
                result=(duration,)+remainder
                candidates.append(result)
        if not candidates:return None
        # Minimize cuts first, then minimize scene-length variation. Prefer
        # longer opening clips on exact ties to establish characters.
        return min(candidates,key=lambda x:(len(x),sum(
            (duration*len(x)-seconds)**2 for duration in x),
            tuple(-duration for duration in x)))
    lengths=schedule(seconds)
    if not lengths:
        raise UnsupportedScenePlan(
            'Provider cannot cover requested total duration with exact supported scene lengths')
    if len(lengths)>1 and not provider.supports_continuation_keyframes:
        raise UnsupportedScenePlan(
            'Provider cannot carry a continuity keyframe between scene segments')
    position=0
    result=[]
    for index,duration in enumerate(lengths):
        scene_id=str(uuid.uuid5(uuid.NAMESPACE_URL,f'kolbo-scene-v1:{guid}:{index}'))
        result.append(SceneSegment(
            index=index,id=scene_id,start_ms=position,end_ms=position+duration*1000,
            seconds=duration,provider=provider.provider,
            person_one_reference=person_one,person_two_reference=person_two,
            prior_end_keyframe_required=index>0,
            end_keyframe_must_be_saved=index<len(lengths)-1,
            audio_required=audio,lip_sync_required=lip_sync,language=language))
        position+=duration*1000
    return Timeline(guid,seconds*1000,tuple(result))
