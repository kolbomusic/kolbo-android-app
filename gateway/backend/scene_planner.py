"""Durable multi-scene plan with exact timing and no phantom model capabilities.

A plan preserves identity continuity metadata across scene boundaries but
cannot guarantee identity fidelity: real provider-specific reference conditioning
and media QA must be implemented and verified separately.
"""
from __future__ import annotations
from dataclasses import dataclass

class UnsupportedPlan(ValueError):pass

@dataclass(frozen=True)
class PlannedScene:
    index:int
    start_ms:int
    end_ms:int
    duration_ms:int
    identity_slots:int
    previous_scene_index:int|None

def plan_exact(requested_seconds:int,allowed_scene_seconds:tuple[int,...],
               *,people:int,max_scenes:int=12)->tuple[PlannedScene,...]:
    if isinstance(requested_seconds,bool) or not 1<=requested_seconds<=120:
        raise UnsupportedPlan('Requested duration outside supported range')
    if people not in (0,1,2) or isinstance(people,bool):
        raise UnsupportedPlan('At most two distinct subject slots')
    if not 1<=max_scenes<=24:
        raise UnsupportedPlan('Invalid scene count ceiling')
    if not allowed_scene_seconds or any(
        type(n)is not int or not 1<=n<=120 for n in allowed_scene_seconds):
        raise UnsupportedPlan('Provider scene durations must be verified integers')
    allowed=tuple(sorted(set(allowed_scene_seconds),reverse=True))
    # Dynamic programming, preferring minimum cuts and longer early scenes.
    # Reduces seams and helps with temporal continuity when identities are hard.
    arrangements:dict[int,tuple[int,...]]={0:()}
    for target in range(1,requested_seconds+1):
        valid=[]
        for duration in allowed:
            before=arrangements.get(target-duration)
            if before is not None and len(before)<max_scenes:
                valid.append(tuple(sorted(before+(duration,),reverse=True)))
        if valid:
            arrangements[target]=min(valid,key=lambda seq:(len(seq),
                tuple(-n for n in seq)))
    durations=arrangements.get(requested_seconds)
    if durations is None:
        raise UnsupportedPlan(
            'No exact-duration scene plan exists with the verified provider lengths')
    result=[]
    start=0
    for i,length in enumerate(durations):
        finish=start+length*1000
        result.append(PlannedScene(i,start,finish,length*1000,people,
                                   i-1 if i else None))
        start=finish
    if start!=requested_seconds*1000:
        raise AssertionError('Scene planner duration invariant failed')
    return tuple(result)
