"""Monetization: never charge, grant, or promise video quota without source evidence."""
import pytest
from decimal import Decimal as D
import monetization_policy as billing

def test_realistic_margin_estimate_not_confused_with_gross():
    quote=billing.estimate(seconds=8,currency='USD',gross_price='1.00',
        provider_cost='0.40',infra_cost='0.10',
        platform_fee_fraction='0.15',vat_reserve='0.10',
        refund_reserve='0.05',target_margin_fraction='0.15')
    assert quote.net_revenue==D('0.70')
    assert quote.expected_margin==D('0.20')
    assert quote.profitable

def test_unpriced_video_and_expensive_video_rejected():
    with pytest.raises(billing.UnpricedRender):
        billing.estimate(seconds=8,gross_price='2',
          provider_cost=None,infra_cost='0',platform_fee_fraction='.15')
    quote=billing.estimate(seconds=8,gross_price='1',
          provider_cost='1',infra_cost='0.10',
          platform_fee_fraction='0.15')
    assert not quote.profitable

@pytest.mark.parametrize('invalid',[-1,'Infinity','NaN','xyz'])
def test_invalid_money_rejected(invalid):
    with pytest.raises(ValueError):
        billing.estimate(seconds=8,gross_price=invalid,provider_cost='0.1',
          infra_cost='0',platform_fee_fraction='.15')

def test_no_client_side_owner_or_plan_flag_authorized():
    with pytest.raises(billing.UnverifiedEntitlement):
        billing.AllowedOperation(role='owner',
            trusted_server_evidence=False)
    with pytest.raises(billing.UnverifiedEntitlement):
        billing.AllowedOperation(role='member',
            verified_plan='pro',verified_credit_balance=100,
            trusted_server_evidence=False)

def test_owner_bypass_is_only_credit_balance_not_billed_gpu_budget():
    owner=billing.AllowedOperation(role='owner',
              trusted_server_evidence=True)
    assert not owner.may_reserve(999,provider_spend_approved=False)
    assert owner.may_reserve(999,provider_spend_approved=True)

def test_paid_user_only_gets_server_verified_credits():
    subscriber=billing.AllowedOperation(role='member',
      verified_plan='plus',verified_credit_balance=10,
      trusted_server_evidence=True)
    assert subscriber.may_reserve(10,provider_spend_approved=True)
    assert not subscriber.may_reserve(11,provider_spend_approved=True)
    assert not subscriber.may_reserve(1,provider_spend_approved=False)

def test_real_payment_disabled_until_all_four_gates_are_ready():
    inputs=dict(has_verified_cost=True,has_store_verification=False,
      has_durable_ledger=False,has_funding_guard=True)
    state=billing.pricing_status(**inputs)
    assert not state['can_accept_real_money']
    assert 'google_play_purchase_verification' in state['missing']
    assert 'persistent_credit_ledger' in state['missing']
    assert billing.pricing_status(has_verified_cost=True,
      has_store_verification=True,has_durable_ledger=True,
      has_funding_guard=True)['can_accept_real_money']
