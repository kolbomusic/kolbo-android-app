"""Respect the public FLUX shared-GPU quota: stop before uploading photos.

This is a local, RAM-only circuit breaker. It remembers actual whitelisted
GPU-quota/busy failures witnessed by THIS service process, not a guessed
global GPU status. It cannot check other users/hosts, cannot buy credits,
does not share session tokens or photos and does NOT defeat provider limits.
Free Render restart clears observations; no guarantee of availability.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import ceil
import threading,time

COOLDOWN_SECONDS=1800
MAX_COOLDOWN_SECONDS=3600
PROVIDER="public_FLUX_shared_GPU"

@dataclass(frozen=True)
class RecentQuotaFailure:
    blocked:bool
    retry_after_seconds:int
    observation:str="observed_public_gpu_quota_rejection"
    availability_guaranteed:bool=False
    is_global_provider_status:bool=False

class ProviderCooldown:
    def __init__(self,seconds:int=COOLDOWN_SECONDS,clock=None):
        if type(seconds)!=int or not 60<=seconds<=MAX_COOLDOWN_SECONDS:
            raise ValueError("Cooling period out of bounded range")
        self.seconds=seconds
        self.clock=clock or time.monotonic
        self._lock=threading.RLock()
        self._cool_until=0.0

    def record_quota_failure(self)->int:
        with self._lock:
            now=self.clock()
            self._cool_until=max(self._cool_until,now+self.seconds)
            return self.remaining()

    def remaining(self)->int:
        with self._lock:
            return max(0,ceil(self._cool_until-self.clock()))

    def snapshot(self)->RecentQuotaFailure:
        remaining=self.remaining()
        return RecentQuotaFailure(remaining>0,remaining)

    def reset_for_tests(self)->None:
        with self._lock:
            self._cool_until=0.0

FLUX_COOLDOWN=ProviderCooldown()
