"""Kolbo Video business pricing and entitlement contract (STAGING ONLY).

No payments are accepted, charged or granted by this module.
Google Play Billing / verified purchase tokens and a transactional wallet
MUST be integrated server-side before launching paid entitlements.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_UP
from typing import Literal

D=Decimal

class UnpricedRender(ValueError): pass
class UnverifiedEntitlement(PermissionError): pass

@dataclass(frozen=True)
class PriceEstimate:
    seconds:int
    currency:str
    provider_cost:D
    infrastructure_cost:D
    payment_fee:D
    vat_reserve:D
    refund_reserve:D
    ad_subsidy:D
    net_revenue:D
    expected_margin:D
    profitable:bool

def amount(n)->D:
    try:
        number=D(str(n))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError('Invalid money amount') from exc
    if not number.is_finite() or number<0:
        raise ValueError('Amount must be finite and nonnegative')
    return number

def estimate(*,seconds:int,currency:str='USD',gross_price,
             provider_cost,infra_cost,platform_fee_fraction,
             vat_reserve=0,refund_reserve=0,ad_subsidy=0,
             target_margin_fraction=0.15)->PriceEstimate:
    """A planning estimate, not a provider price lookup or tax calculation.

    Costs must be independently confirmed. VAT is reserved explicitly rather
    than omitted from the margin. Ad subsidies must reflect actual recognized
    proceeds; speculative ad eCPM is NOT wallet revenue.
    """
    if isinstance(seconds,bool) or not 1<=seconds<=360:
        raise ValueError('Unsupported duration')
    if currency not in ('USD','ILS'):
        raise ValueError('Currency not configured')
    if provider_cost is None:
        raise UnpricedRender('Missing verified provider cost')
    gross=amount(gross_price)
    provider=amount(provider_cost)
    infra=amount(infra_cost)
    fee_rate=amount(platform_fee_fraction)
    target=amount(target_margin_fraction)
    if fee_rate>1 or target>=1:
        raise ValueError('Invalid fee or profit rate')
    vat=amount(vat_reserve)
    refund=amount(refund_reserve)
    ad=amount(ad_subsidy)
    # Ad subsidy cannot turn a loss-making transaction into a false $0-cost
    # guarantee; it must be real booked revenue, not ad views in flight.
    fee=gross*fee_rate
    net=gross-fee-vat-refund
    margin=net+ad-provider-infra
    return PriceEstimate(seconds,currency,provider,infra,fee,
        vat,refund,ad,net,margin,
        gross>0 and margin>=gross*target)

class AllowedOperation:
    """Server-side access gate, not an Android-originated role toggle."""
    def __init__(self,*,role:Literal['owner','member'],
                 verified_credit_balance:int=0,
                 verified_plan:Literal['free','plus','pro']='free',
                 trusted_server_evidence:bool=False):
        if not trusted_server_evidence:
            raise UnverifiedEntitlement('Entitlements must be server verified')
        if role not in ('owner','member') or verified_plan not in ('free','plus','pro'):
            raise ValueError('Unknown entitlement')
        if type(verified_credit_balance) is not int or verified_credit_balance<0:
            raise ValueError('Invalid credit balance')
        self.role=role
        self.plan=verified_plan
        self.balance=verified_credit_balance
    def may_reserve(self,credit_cost:int,*,provider_spend_approved:bool)->bool:
        if type(credit_cost) is not int or credit_cost<0:
            raise ValueError('Invalid credit cost')
        if not provider_spend_approved:
            return False
        if self.role=='owner':
            # Owner does not spend wallet credits, BUT provider budget is
            # still mandatory (even for "promotional free" API calls).
            return True
        return self.balance>=credit_cost

def pricing_status(*,has_verified_cost:bool,
                   has_store_verification:bool,
                   has_durable_ledger:bool,
                   has_funding_guard:bool)->dict:
    ready=all((has_verified_cost,has_store_verification,
               has_durable_ledger,has_funding_guard))
    return {'can_accept_real_money':ready,
            'can_grant_paid_entitlements':ready,
            'demo_only':not ready,
            'missing':[
                label for ok,label in [
                    (has_verified_cost,'verified_provider_costs'),
                    (has_store_verification,'google_play_purchase_verification'),
                    (has_durable_ledger,'persistent_credit_ledger'),
                    (has_funding_guard,'provider_budget_guard')]
                if not ok]}
