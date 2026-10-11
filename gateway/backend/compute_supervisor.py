"""Measured Free-tier compute admission for Kolbo Video, not an imaginary GPU.

No billing APIs, no cloud provisioning, no waking other services, no GPU
mining or third-party quota circumvention. This is a *truthful* low-capacity
CPU supervisor for photo-motion jobs and read-only client diagnostics.

Limits and capacity are measured from cgroups when readable and deliberately
reported as unknown otherwise. "output-video seconds" is NOT GPU/CPU seconds.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
import os
import shutil

from fastapi import HTTPException

MIN_FREE_MEMORY = 128 * 1024 * 1024
MIN_FREE_DISK = 128 * 1024 * 1024
LOW_MEMORY_MAX_INPUT_PIXELS = 4_000_000
MAX_STAGING_CPU_JOBS = 1
MAX_OUTPUT_SECONDS = 12


def _integer(path: Path) -> int | None:
    try:
        value=path.read_text(encoding="ascii").strip()
        if value=="max":
            return None
        result=int(value)
        return result if result>=0 else None
    except (ValueError,OSError):
        return None


def _cpu_cores() -> float | None:
    """cgroup v2 CPU quota as a fraction of one core."""
    try:
        quota,period=Path("/sys/fs/cgroup/cpu.max").read_text().strip().split()
        if quota=="max":return None
        period_n=int(period)
        return round(int(quota)/period_n,3) if period_n>0 else None
    except (ValueError, OSError):
        return None


@dataclass(frozen=True)
class ComputeSnapshot:
    cpu_quota_cores: float | None
    memory_limit_bytes: int | None
    memory_used_bytes: int | None
    memory_free_bytes: int | None
    disk_free_bytes: int | None
    active_jobs: int
    queued_jobs: int
    max_parallel_jobs: int
    cpu_editor_ready: bool
    readiness_reason: str
    gpu_verified_available: bool = False
    paid_compute_enabled: bool = False
    external_ai_enabled_for_guests: bool = False
    durable_storage: bool = False
    daily_gpu_quota_seconds: int | None = None

    def public(self) -> dict:
        out=asdict(self)
        out["kind"]="bounded_cpu_photo_editing"
        out["not_supported"]=[
            "unlimited_compute","gpu_inference","spoken_dialogue",
            "singing","identity_preserving_character_animation",
            "multi_actor_scene_generation"]
        out["cost_claim"]="no_paid_compute_configured_not_unlimited_or_cost_guarantee"
        out["render_free_hours_remaining"]="not_measured"
        out["performance_guaranteed"]=False
        return out


def inspect(*,work_dir:Path,active_jobs:int,queued_jobs:int) -> ComputeSnapshot:
    # cgroup v2 paths used by Docker and cloud runtimes. Missing metrics do
    # not imply zero consumption or unrestricted availability.
    memory_limit=_integer(Path("/sys/fs/cgroup/memory.max"))
    memory_used=_integer(Path("/sys/fs/cgroup/memory.current"))
    free_mem=(max(0,memory_limit-memory_used)
              if memory_limit is not None and memory_used is not None else None)
    try:
        location=Path(work_dir)
        probe=location if location.exists() else location.parent
        disk_free=shutil.disk_usage(probe).free
    except OSError:
        disk_free=None
    if active_jobs>=MAX_STAGING_CPU_JOBS or queued_jobs>0:
        reason="all_cpu_slots_busy"
    elif free_mem is not None and free_mem<MIN_FREE_MEMORY:
        reason="insufficient_container_memory"
    elif disk_free is not None and disk_free<MIN_FREE_DISK:
        reason="insufficient_ephemeral_disk"
    elif free_mem is None or disk_free is None:
        reason="unverified_resources"
    else:
        reason="ready_with_free_tier_limits"
    # Unknown measurements are tolerated in isolated CI only by explicit
    # environment opt-in, never inferred to mean unlimited compute.
    allow_unknown=os.getenv("KOLBO_ALLOW_UNKNOWN_CPU_METRICS")=="CI_TEST_ONLY"
    ready=(reason=="ready_with_free_tier_limits"
           or reason=="unverified_resources" and allow_unknown)
    return ComputeSnapshot(
        cpu_quota_cores=_cpu_cores(),
        memory_limit_bytes=memory_limit,
        memory_used_bytes=memory_used,
        memory_free_bytes=free_mem,
        disk_free_bytes=disk_free,
        active_jobs=active_jobs,
        queued_jobs=queued_jobs,
        max_parallel_jobs=MAX_STAGING_CPU_JOBS,
        cpu_editor_ready=ready,
        readiness_reason=reason
    )


def admit(*,snapshot:ComputeSnapshot,seconds:int,pixel_counts:tuple[int,...]) -> None:
    if type(seconds) is not int or not 2<=seconds<=MAX_OUTPUT_SECONDS:
        raise HTTPException(422,"הבקשה חורגת ממגבלות משך עריכת התמונות")
    if not 1<=len(pixel_counts)<=2 or any(
        type(n) is not int or n<1 or n>15_000_000 for n in pixel_counts
    ):
        raise HTTPException(422,"נתוני תמונות אינם תקינים")
    if snapshot.memory_limit_bytes is not None and snapshot.memory_limit_bytes<=600_000_000:
        if any(n>LOW_MEMORY_MAX_INPUT_PIXELS for n in pixel_counts):
            raise HTTPException(422,"התמונה גדולה מכדי לערוך אותה בשרת החינמי. יש להקטין אותה.")
    if not snapshot.cpu_editor_ready:
        raise HTTPException(503,
            "מחשוב העריכה החינמי אינו זמין כרגע: "+snapshot.readiness_reason,
            headers={"Retry-After":"60"})


def route(*,wants_real_ai:bool,requires_voice:bool,requires_duet:bool,
          image_count:int,seconds:int,snapshot:ComputeSnapshot,
          media_rights:bool) -> dict:
    """Pure, fail-closed planner. Never claims a camera-pan is AI acting."""
    if wants_real_ai or requires_voice or requires_duet:
        return {"can_execute":False,"compute_route":None,
            "blocker":"verified_gpu_video_and_audio_backend_unavailable",
            "fallback_to_photo_motion":False,"potential_charge_usd":0,
            "alternative_requires_explicit_new_user_choice":True}
    if not media_rights:
        return {"can_execute":False,"compute_route":None,
            "blocker":"media_rights_attestation_required",
            "fallback_to_photo_motion":False}
    try:
        admit(snapshot=snapshot,seconds=seconds,
              pixel_counts=tuple(1 for _ in range(image_count)))
    except HTTPException as exc:
        return {"can_execute":False,"compute_route":None,
                "blocker":str(exc.detail),
                "fallback_to_photo_motion":False}
    return {"can_execute":True,"compute_route":"cpu_photo_motion",
        "ai_video":False,"max_concurrent_jobs":1,
        "clip_type":"photo_camera_movement",
        "external_provider":False,"provider_paid_compute":False,
        "fallback_to_photo_motion":False}
