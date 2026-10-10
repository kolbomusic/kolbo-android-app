"""Privacy-minimized learning from failures, staged and disabled for live routing.

A failure becomes a measurable *operational* improvement, never a reason to
loosen billing, image consent or quality gates. No user prompt, image content,
device ID or private provider response is collected by this module.
The caller must persist aggregate counters off Render Free before claiming
continuous or cross-restart optimization.
"""
from __future__ import annotations
from collections import defaultdict,deque
from dataclasses import dataclass
from enum import Enum
import threading
import time

class Outcome(str,Enum):
    QUEUE_FULL='queue_full'
    CAPACITY_OK='capacity_ok'
    PROVIDER_ACCEPTED='provider_accepted'
    VIDEO_VALID='video_valid'
    VIDEO_REJECTED='video_rejected'
    AUTH_FAILURE='auth_failure'
    UNKNOWN_SUBMISSION='unknown_submission'

@dataclass(frozen=True)
class Insight:
    provider:str
    samples:int
    busy_rate:float|None
    completed_rate:float|None
    action:str
    reason:str
    enough_evidence:bool

class Feedback:
    def __init__(self,limit:int=50,min_samples:int=5,clock=None):
        if not 5<=limit<=1000 or not 3<=min_samples<=limit:
            raise ValueError('Out-of-bounds feedback window')
        self.limit=limit
        self.minimum=min_samples
        self.clock=clock or time.monotonic
        self.history=defaultdict(lambda:deque(maxlen=limit))
        self.cooldown={}
        self.lock=threading.RLock()

    def record(self,provider:str,outcome:Outcome):
        if not 1<=len(provider)<=64 or any(
                c not in 'abcdefghijklmnopqrstuvwxyz0123456789_-'
                for c in provider):
            raise ValueError('Invalid provider name')
        if not isinstance(outcome,Outcome):
            raise ValueError('Telemetry only accepts known aggregate categories')
        with self.lock:
            self.history[provider].append(outcome)
            if outcome is Outcome.QUEUE_FULL:
                last=list(self.history[provider])[-5:]
                if len(last)>=3 and last.count(Outcome.QUEUE_FULL)>=3:
                    self.cooldown[provider]=self.clock()+120
            elif outcome is Outcome.VIDEO_VALID:
                self.cooldown.pop(provider,None)

    def inspect(self,provider:str)->Insight:
        with self.lock:
            items=tuple(self.history[provider])
            freeze=self.cooldown.get(provider,0)>self.clock()
        submitted=[x for x in items if x in (
            Outcome.QUEUE_FULL,Outcome.CAPACITY_OK,Outcome.PROVIDER_ACCEPTED)]
        produced=[x for x in items if x in (
            Outcome.VIDEO_VALID,Outcome.VIDEO_REJECTED)]
        busy=(sum(x is Outcome.QUEUE_FULL for x in submitted)/len(submitted)
              if submitted else None)
        complete=(sum(x is Outcome.VIDEO_VALID for x in produced)/len(produced)
                  if produced else None)
        enough=len(items)>=self.minimum
        if freeze:
            action='pause_requests';reason='consecutive_explicit_queue_rejections'
        elif items and items[-1] is Outcome.AUTH_FAILURE:
            action='operator_review';reason='authorization_failure'
        elif items and items[-1] is Outcome.UNKNOWN_SUBMISSION:
            action='reconcile_provider_task';reason='ambiguous_task_acceptance'
        elif produced and complete is not None and complete<0.5 and len(produced)>=self.minimum:
            action='quality_review';reason='low_verified_video_acceptance'
        else:
            action='observe_only';reason='not_enough_data' if not enough else 'no_critical_trend'
        return Insight(provider,len(items),busy,complete,action,reason,enough)

    def safe_order(self,eligible_provider_names:list[str])->list[str]:
        """Only reorder ALREADY verified eligible providers. Never enable an
        unauthorized provider or approve spend by inferring it from telemetry.
        """
        if len(set(eligible_provider_names))!=len(eligible_provider_names):
            raise ValueError('Duplicate eligible provider')
        indexed=[]
        for i,p in enumerate(eligible_provider_names):
            insight=self.inspect(p)
            paused=insight.action in ('pause_requests','operator_review',
                                       'reconcile_provider_task')
            # Bounded preference: only a demonstrated busy rate moves
            # a provider behind another; too few samples preserve order.
            queue=(insight.busy_rate if insight.enough_evidence and
                   insight.busy_rate is not None else 0.5)
            indexed.append((paused,queue,i,p))
        indexed.sort()
        return [item[-1] for item in indexed]
