"""Recognize public Gradio image-to-video API signatures without running arbitrary code.

External metadata is untrusted. A plan is only an *inferred* calling convention,
never proof of generation quality, cost, license or provider uptime.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, asdict
from typing import Any

MAX_PARAMETERS=24
DEFAULT_UNSET=object()

class UnsupportedEndpoint(ValueError):
    pass

@dataclass
class Slot:
    name: str
    kind: str
    default: Any = None

@dataclass
class Plan:
    api_name: str
    slots: list[Slot]
    supports_explicit_duration: bool
    declares_video_output: bool
    capability: str = 'image_to_video'

    def public(self) -> dict:
        return {'api_name':self.api_name,'slots':[asdict(s) for s in self.slots],
                'supports_explicit_duration':self.supports_explicit_duration,
                'declares_video_output':self.declares_video_output,
                'capability':self.capability}

    def arguments(self, prompt: str, seconds: int, image_descriptor: dict) -> list:
        if not (3 <= seconds <= 12):
            raise ValueError('UNSUPPORTED_DURATION')
        if not self.supports_explicit_duration:
            raise ValueError('DURATION_NOT_CONTROLLABLE')
        if not isinstance(prompt,str) or not 4 <= len(prompt) <= 1200:
            raise ValueError('INVALID_PROMPT')
        values=[]
        for slot in self.slots:
            if slot.kind=='image': values.append(image_descriptor)
            elif slot.kind=='prompt': values.append(prompt)
            elif slot.kind=='duration': values.append(seconds)
            else: values.append(slot.default)
        return values

_PROMPT=re.compile(r'\b(prompt|description|instruction|caption|text_prompt)\b',re.I)
_IMAGE=re.compile(r'(input_?image|image|first_?frame|reference_?image|start_?frame|photo)',re.I)
_DURATION=re.compile(r'(duration|seconds|video_length|length_seconds|duration_seconds)',re.I)
_SAFE_DEFAULT_TYPES=(str,int,float,bool,type(None))


def _words(param:dict) -> tuple[str,str]:
    nm=str(param.get('parameter_name') or param.get('name') or '')[:128]
    label=str(param.get('label') or '')[:128]
    return nm, label


def _typeinfo(p:dict) -> str:
    info=p.get('type') or p.get('python_type') or ''
    if isinstance(info,dict): info=info.get('type','')
    return str(info).lower()[:120]


def _slot(p:dict) -> Slot:
    name,label=_words(p)
    if not name or not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]{0,90}',name):
        raise UnsupportedEndpoint('INVALID_PARAMETER_NAME')
    component=str(p.get('component') or '').lower()[:70]
    text=(name+' '+label).lower().replace('-','_')
    if ('image' in component or 'image' in _typeinfo(p)) and _IMAGE.search(text):
        return Slot(name,'image')
    if _IMAGE.search(text) and 'file' in _typeinfo(p):
        return Slot(name,'image')
    if _PROMPT.search(text) and ('image' not in text or 'prompt' in text):
        return Slot(name,'prompt')
    # Gradio labels often say 'Automatic duration' for the auto_length toggle.
    # Only the *parameter name* may choose a duration slot.
    if _DURATION.search(name) and name.lower() not in ('auto_length','automatic_duration','auto_duration'):
        return Slot(name,'duration')
    # Only safe defaults supported. Unsupported required inputs prohibit adaptation.
    default=p.get('parameter_default', DEFAULT_UNSET)
    if default is DEFAULT_UNSET:
        default=p.get('default',DEFAULT_UNSET)
    if default is DEFAULT_UNSET or not isinstance(default,_SAFE_DEFAULT_TYPES):
        raise UnsupportedEndpoint('UNMAPPED_REQUIRED_INPUT:'+name)
    if isinstance(default,str) and len(default)>256:
        raise UnsupportedEndpoint('OVERSIZED_DEFAULT:'+name)
    # Safe probe policy: no automatic length/seed drift; bounded trial resolution.
    if name.lower() in ('auto_length','automatic_duration','auto_duration','randomize_seed'):
        if not isinstance(default,bool):raise UnsupportedEndpoint('AUTO_FLAG_NOT_BOOLEAN')
        default=False
    if name.lower() in ('width','height') and isinstance(default,(int,float)) and not isinstance(default,bool):
        default=min(default,512)
    return Slot(name,'default',default)


def _declares_video(info:dict) -> bool:
    returns=info.get('returns') or info.get('outputs') or []
    if not isinstance(returns,list): return False
    for output in returns:
        if not isinstance(output,dict): continue
        meta=(str(output.get('component') or '')+' '+str(output.get('label') or '')+' '+_typeinfo(output)).lower()
        if 'video' in meta or 'mp4' in meta: return True
    return False


def recognize(gradio_info:dict, require_duration:bool=True) -> list[Plan]:
    if not isinstance(gradio_info,dict):return []
    endpoints=gradio_info.get('named_endpoints') or {}
    if not isinstance(endpoints,dict):return []
    plans=[]
    for api_name,entry in sorted(endpoints.items()):
        if not isinstance(api_name,str) or not re.fullmatch('/[a-zA-Z0-9_-]{1,80}',api_name):continue
        if not isinstance(entry,dict):continue
        if entry.get('api_visibility')=='private' or entry.get('show_api') is False:continue
        params=entry.get('parameters') or []
        if not isinstance(params,list) or not 2<=len(params)<=MAX_PARAMETERS:continue
        try:slots=[_slot(p) if isinstance(p,dict) else (_ for _ in ()).throw(UnsupportedEndpoint('BAD_PARAMETER')) for p in params]
        except UnsupportedEndpoint:continue
        kinds=[s.kind for s in slots]
        if kinds.count('image')!=1 or kinds.count('prompt')!=1:continue
        if kinds.count('duration')>1:continue
        if require_duration and kinds.count('duration')!=1:continue
        declares_video=_declares_video(entry)
        # Some apps only declare 'file' while returning MP4: don't auto-promote them.
        if not declares_video:continue
        plans.append(Plan(api_name,slots,kinds.count('duration')==1,declares_video))
    return plans


def plan_from_public(data:dict) -> Plan:
    if data.get('capability')!='image_to_video':raise ValueError('UNKNOWN_PLAN')
    slots=[]
    for s in data.get('slots',[]):
        if s.get('kind') not in ('image','prompt','duration','default'):raise ValueError('UNKNOWN_SLOT')
        slots.append(Slot(name=s['name'],kind=s['kind'],default=s.get('default')))
    return Plan(data['api_name'],slots,data.get('supports_explicit_duration',False),data.get('declares_video_output',False))