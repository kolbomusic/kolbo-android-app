"""No third-party contact, no paid credits, transactional reward replay guards."""
from datetime import datetime,timezone,timedelta
from concurrent.futures import ThreadPoolExecutor
import hashlib
import pytest
from studio_credit_ledger import EditPointLedger,InsufficientCredits,InvalidCredit,funding_contract

OWNER=hashlib.sha256(b"anonymous-device").hexdigest()
DAY=datetime(2026,10,11,10,0,tzinfo=timezone.utc)
DIGEST=hashlib.sha256(b"one render").hexdigest()

def test_earn_and_spend_without_ads_or_gpu(tmp_path):
    ledger=EditPointLedger(tmp_path/"credits.db")
    assert ledger.gift(OWNER,now=DAY)==3
    assert ledger.gift(OWNER,now=DAY)==3
    did,bal=ledger.spend_cpu_edit(OWNER,DIGEST,now=DAY)
    assert did is True and bal==2
    did,bal=ledger.spend_cpu_edit(OWNER,DIGEST,now=DAY)
    assert did is False and bal==2
    assert ledger.refund_cpu_edit(OWNER,DIGEST,now=DAY)==3
    assert ledger.refund_cpu_edit(OWNER,DIGEST,now=DAY)==3

def test_real_cache_reuse_reward_unique_and_capped(tmp_path):
    ledger=EditPointLedger(tmp_path/"credits.db")
    for i in range(5):
        ledger.reward_reused_clip(OWNER,hashlib.sha256(str(i).encode()).hexdigest(),
                                 verified_cache_hit=True,now=DAY)
    assert ledger.balance(OWNER)==2
    assert ledger.gift(OWNER,now=DAY)==5
    assert ledger.gift(OWNER,now=DAY+timedelta(days=1))==8

def test_unverified_client_claim_cannot_mint_rewards(tmp_path):
    ledger=EditPointLedger(tmp_path/"credits.db")
    with pytest.raises(InvalidCredit):
        ledger.reward_reused_clip(OWNER,DIGEST,verified_cache_hit=False,now=DAY)
    assert ledger.balance(OWNER)==0

def test_spend_cannot_overdraft_and_refund_requires_prior_charge(tmp_path):
    ledger=EditPointLedger(tmp_path/"credits.db")
    with pytest.raises(InsufficientCredits):
        ledger.spend_cpu_edit(OWNER,DIGEST,now=DAY)
    with pytest.raises(InvalidCredit):
        ledger.refund_cpu_edit(OWNER,DIGEST,now=DAY)
    assert ledger.balance(OWNER)==0

def test_repeated_concurrent_free_gift_stays_three(tmp_path):
    ledger=EditPointLedger(tmp_path/"credits.db")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda i:ledger.gift(OWNER,now=DAY),range(40)))
    assert all(x==3 for x in results)
    assert ledger.balance(OWNER)==3

def test_live_contract_never_confuses_points_with_paid_gpu():
    plan=funding_contract()
    assert plan["ad_networks_enabled"] is False
    assert plan["contracts_required"] is False
    assert plan["external_gpu_credit_redeemable"] is False
    assert plan["render_free_local_sqlite_durable"] is False
    assert plan["requires_durable_ledger_before_live_activation"] is True
