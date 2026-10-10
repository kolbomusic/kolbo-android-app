"""Multi-engine provider capability safety and no double paid generation."""
import json, pytest
import provider_router as routing

def test_two_people_dont_silently_morph_to_keyframes():
    b=routing.Breaker(clock=lambda:10)
    engines=routing.candidates(2,v20_enabled=True,v20_cost_approved=True,breaker=b)
    assert [e.name for e in engines]==['agnes_flash']
    assert engines[0].max_independent_references==2

def test_one_photo_selects_second_engine_after_explicit_refusal():
    clock=[500]
    b=routing.Breaker(clock=lambda:clock[0])
    submitted=[]
    class QueueRefusal(Exception):pass
    def submit(provider):
        submitted.append(provider.name)
        if provider.name=='agnes_flash':raise QueueRefusal()
        return 'accepted_legacy_task_001'
    engine,task=routing.select_and_submit(1,submit,
        lambda ex:isinstance(ex,QueueRefusal),
        v20_enabled=True,v20_cost_approved=True,breaker=b)
    assert task=='accepted_legacy_task_001'
    assert submitted==['agnes_flash','agnes_legacy']
    assert engine.name=='agnes_legacy'
    assert not b.available('agnes_flash')
    clock[0]+=91
    assert b.available('agnes_flash')

def test_ambiguous_failure_cannot_submit_to_next_engine():
    class TimeoutAfterPossibleAcceptance(Exception):pass
    attempted=[]
    def submit(p):
        attempted.append(p.name)
        raise TimeoutAfterPossibleAcceptance('response timed out after provider may accept')
    with pytest.raises(TimeoutAfterPossibleAcceptance):
        routing.select_and_submit(1,submit,lambda ex:False,
            v20_enabled=True,v20_cost_approved=True,
            breaker=routing.Breaker(clock=lambda:10))
    assert attempted==['agnes_flash']

def test_provider_unavailable_or_unapproved_never_produces_phantom_job():
    b=routing.Breaker(clock=lambda:100)
    b.rejected('agnes_flash',cooldown=3600)
    with pytest.raises(routing.NoCompatibleProvider):
        routing.select_and_submit(2,lambda provider:'would_not_run',
           lambda _:True,v20_enabled=True,v20_cost_approved=True,breaker=b)
    # A second engine that has not been explicitly cost approved is excluded.
    with pytest.raises(routing.NoCompatibleProvider):
        routing.select_and_submit(0,lambda provider:'would_not_run',
           lambda _:True,flash_enabled=False,v20_enabled=True,
           v20_cost_approved=False,breaker=b)

def test_all_explicit_refusals_end_in_truthful_busy_status():
    calls=[]
    class Busy(Exception):pass
    def submit(p):
        calls.append(p.name)
        raise Busy()
    with pytest.raises(routing.ProviderQueueExhausted):
        routing.select_and_submit(1,submit,lambda ex:isinstance(ex,Busy),
            v20_enabled=True,v20_cost_approved=True,
            breaker=routing.Breaker(clock=lambda:100))
    assert calls==['agnes_flash','agnes_legacy']

def test_nonpersistent_checkpoint_saves_no_identity_or_media(tmp_path):
    dest=routing.snapshot(tmp_path,'12345678-1234-1234-1234-123456789abc',
                          'reference',2,8,None,'queued')
    data=json.loads(dest.read_text())
    assert data['persistent_storage'] is False
    assert 'prompt' not in data and 'images' not in data
    assert dest.stat().st_mode & 0o777 ==0o600

def test_unknown_reference_count_is_rejected():
    with pytest.raises(ValueError): routing.candidates(3)
