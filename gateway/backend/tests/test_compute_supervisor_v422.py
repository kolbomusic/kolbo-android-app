"""Computed CPU budget verified independently from the app, not fake GPU claims."""
from dataclasses import replace
import io
import base64
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
import compute_supervisor as compute
import staging_wan_api as api


def fake_snapshot(**kw):
    base=dict(cpu_quota_cores=0.1,memory_limit_bytes=512*1024*1024,
              memory_used_bytes=100*1024*1024,
              memory_free_bytes=412*1024*1024,
              disk_free_bytes=500*1024*1024,
              active_jobs=0,queued_jobs=0,max_parallel_jobs=1,
              cpu_editor_ready=True,readiness_reason="ready_with_free_tier_limits")
    base.update(kw)
    return compute.ComputeSnapshot(**base)


def test_compute_receipt_never_fabricates_gpu_or_billing():
    snapshot=fake_snapshot()
    report=snapshot.public()
    assert report["cpu_quota_cores"]==0.1
    assert report["gpu_verified_available"] is False
    assert report["external_ai_enabled_for_guests"] is False
    assert report["paid_compute_enabled"] is False
    assert report["daily_gpu_quota_seconds"] is None
    assert report["render_free_hours_remaining"]=="not_measured"
    assert "unlimited_compute" in report["not_supported"]
    assert report["performance_guaranteed"] is False


def test_cpu_memory_and_disk_backpressure():
    for kwargs,reason in [
        ({"active_jobs":1,"cpu_editor_ready":False,"readiness_reason":"all_cpu_slots_busy"},"all_cpu_slots_busy"),
        ({"memory_free_bytes":4*1024*1024,"cpu_editor_ready":False,"readiness_reason":"insufficient_container_memory"},"insufficient_container_memory"),
        ({"disk_free_bytes":1234,"cpu_editor_ready":False,"readiness_reason":"insufficient_ephemeral_disk"},"insufficient_ephemeral_disk")
    ]:
        snapshot=fake_snapshot(**kwargs)
        with pytest.raises(HTTPException) as exc:
            compute.admit(snapshot=snapshot,seconds=3,pixel_counts=(5000,))
        assert exc.value.status_code==503
        assert reason in exc.value.detail


def test_small_render_memory_caps_original_photos():
    snapshot=fake_snapshot()
    compute.admit(snapshot=snapshot,seconds=8,pixel_counts=(2000,2000))
    with pytest.raises(HTTPException) as exc:
        compute.admit(snapshot=snapshot,seconds=8,pixel_counts=(5_000_000,))
    assert exc.value.status_code==422


def test_unknown_cgroup_has_explicit_tiny_photo_fallback():
    snapshot=fake_snapshot(memory_limit_bytes=None,memory_used_bytes=None,
        memory_free_bytes=None,readiness_reason="memory_capacity_unverified_tiny_cpu_jobs_only")
    compute.admit(snapshot=snapshot,seconds=2,pixel_counts=(150*220,))
    with pytest.raises(HTTPException):
        compute.admit(snapshot=snapshot,seconds=2,pixel_counts=(2_000_000,))


def test_ai_route_never_mutates_to_camera_pan():
    snapshot=fake_snapshot()
    for needs_voice,needs_duet in ((True,False),(False,True),(True,True)):
        x=compute.route(wants_real_ai=True,requires_voice=needs_voice,
            requires_duet=needs_duet,image_count=2,seconds=8,
            snapshot=snapshot,media_rights=True)
        assert x["can_execute"] is False
        assert x["compute_route"] is None
        assert x["fallback_to_photo_motion"] is False


def test_gpu_claim_never_from_host_driver(monkeypatch,tmp_path):
    # Even on a runner with GPU drivers, plan never advertises a verified GPU
    # without configured and authenticated provider routing.
    x=compute.inspect(work_dir=tmp_path,active_jobs=0,queued_jobs=0)
    assert x.gpu_verified_available is False
    assert x.paid_compute_enabled is False
    assert x.durable_storage is False


def test_api_compute_readout_needs_authenticated_owner(monkeypatch,tmp_path):
    monkeypatch.setenv("KOLBO_V416_API_TOKEN","test_master_key_that_is_long_enough_123456")
    monkeypatch.setattr(api,"ROOT",tmp_path)
    monkeypatch.setattr(api.compute,"inspect",
        lambda **kw:fake_snapshot(active_jobs=kw["active_jobs"],
                                  queued_jobs=kw["queued_jobs"]))
    c=TestClient(api.app)
    assert c.get("/v1/compute/capacity").status_code==401
    r=c.get("/v1/compute/capacity",
            headers={"Authorization":"Bearer test_master_key_that_is_long_enough_123456"})
    assert r.status_code==200
    x=r.json()
    assert x["cpu_editor_ready"] is True
    assert x["gpu_verified_available"] is False
    assert x["max_parallel_jobs"]==1


def test_compute_admission_prevents_media_job_submission(monkeypatch,tmp_path):
    monkeypatch.setenv("KOLBO_V416_API_TOKEN","test_master_key_that_is_long_enough_123456")
    monkeypatch.setattr(api,"ROOT",tmp_path)
    monkeypatch.setattr(api.compute,"inspect",
        lambda **kw:fake_snapshot(cpu_editor_ready=False,
                readiness_reason="insufficient_container_memory",
                memory_free_bytes=0))
    with api.LOCK:
        api.JOBS.clear(); api.DIGESTS.clear()
    picture=Image.new("RGB",(64,64),(20,30,40))
    buf=io.BytesIO();picture.save(buf,"PNG")
    data={"mode":"cpu_photo_motion","seconds":8,
          "images":[{"mime_type":"image/png",
                      "data_base64":base64.b64encode(buf.getvalue()).decode()}],
          "media_rights_attested":True}
    c=TestClient(api.app)
    r=c.post("/v1/studio/jobs",json=data,
             headers={"Authorization":"Bearer test_master_key_that_is_long_enough_123456"})
    assert r.status_code==503
    assert len(api.JOBS)==0
    assert not list(tmp_path.iterdir())


def test_no_machine_cost_or_gpu_claims_from_cpu_policy():
    snap=fake_snapshot()
    choice=compute.route(wants_real_ai=False,requires_voice=False,
          requires_duet=False,image_count=2,seconds=4,
          media_rights=True,snapshot=snap)
    assert choice["can_execute"]
    assert choice["compute_route"]=="cpu_photo_motion"
    assert choice["ai_video"] is False
    assert choice["provider_paid_compute"] is False
