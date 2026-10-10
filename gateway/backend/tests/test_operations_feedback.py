"""Regression: optimization must never weaken authorization, price or quality gates."""
import pytest
import operations_feedback as ops
O=ops.Outcome

def test_queue_full_becomes_pause_not_thousands_of_retries():
    clock=[1000]
    feedback=ops.Feedback(clock=lambda:clock[0])
    for _ in range(3): feedback.record('agnes_flash',O.QUEUE_FULL)
    signal=feedback.inspect('agnes_flash')
    assert signal.action=='pause_requests'
    assert signal.reason=='consecutive_explicit_queue_rejections'
    clock[0]+=121
    assert feedback.inspect('agnes_flash').action=='observe_only'

def test_uncertain_provider_job_must_reconcile_not_retry():
    f=ops.Feedback()
    f.record('agnes_flash',O.UNKNOWN_SUBMISSION)
    assert f.inspect('agnes_flash').action=='reconcile_provider_task'

def test_not_enough_samples_cannot_claim_learning():
    f=ops.Feedback(min_samples=5)
    f.record('engine_a',O.VIDEO_VALID)
    insight=f.inspect('engine_a')
    assert not insight.enough_evidence
    assert insight.action=='observe_only'
    assert insight.completed_rate==1

def test_quality_regression_triggers_review_not_fake_success():
    f=ops.Feedback()
    for _ in range(6):f.record('engine_a',O.VIDEO_REJECTED)
    q=f.inspect('engine_a')
    assert q.action=='quality_review' and q.completed_rate==0

def test_router_only_reorders_preapproved_eligible_engines():
    f=ops.Feedback()
    for _ in range(4):
        f.record('engine_busy',O.QUEUE_FULL)
        f.record('engine_ready',O.CAPACITY_OK)
    assert f.safe_order(['engine_busy','engine_ready'])==[
        'engine_ready','engine_busy']
    # No API discovery or auto-authorization of an unlisted provider.
    assert 'third_provider' not in f.safe_order(['engine_ready'])
    with pytest.raises(ValueError):
        f.safe_order(['engine_ready','engine_ready'])

def test_private_content_and_unrecognized_outcomes_rejected():
    f=ops.Feedback()
    with pytest.raises(ValueError): f.record('https://secret.example',O.QUEUE_FULL)
    with pytest.raises(ValueError): f.record('engine_a','someone said free')

def test_success_resets_cooldown_but_not_history():
    f=ops.Feedback()
    for _ in range(3):f.record('engine_a',O.QUEUE_FULL)
    f.record('engine_a',O.VIDEO_VALID)
    assert f.inspect('engine_a').action=='observe_only'
    assert f.inspect('engine_a').samples==4

def test_invalid_limits_are_rejected():
    with pytest.raises(ValueError):ops.Feedback(limit=3)
    with pytest.raises(ValueError):ops.Feedback(min_samples=2000)
