"""Staged durable orchestration against actual PostgreSQL job state.

The dispatch callback is MOCKED in CI and NEVER called in live Render. A
trusted server must supply eligible, account-priced provider proof records.
Before live use, configure provider-specific reconciliation, durable media
and a separate provider hard-spend budget.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import execution_guard as gates
import postgres_job_store as persistence
import operations_feedback as feedback

class DefinitelyRejected(Exception):pass
class PossiblyAccepted(Exception):pass

@dataclass(frozen=True)
class SubmissionReport:
    job:persistence.JobReceipt
    provider:str|None
    sent_to:tuple[str,...]
    status:str

@dataclass(frozen=True)
class DeliveryReport:
    job:persistence.JobReceipt
    quality:gates.QualityReport
    published:bool

class DurableStagingCoordinator:
    def __init__(self,store:persistence.PostgresJobStore,
                 telemetry:feedback.Feedback|None=None):
        self.store=store
        self.telemetry=telemetry if telemetry is not None else feedback.Feedback()

    def submit(self,*,owner_hash:str,request_key:str,
               spec_digest:str,credit_points:int,
               request:gates.VideoRequest,
               provider_proofs:list[gates.ProviderProof],
               provider_submit:Callable[[str],str])->SubmissionReport:
        # Never charge until compatible supplier, duration, identity, rights,
        # account price and owner budget have been verified by SERVER.
        candidates=gates.choose_eligible(request,provider_proofs)
        ordered=self.telemetry.safe_order([p.name for p in candidates])
        eligible=[p for p in ordered if
                  self.telemetry.inspect(p).action not in (
                      'pause_requests','operator_review','reconcile_provider_task')]
        if not eligible:
            raise gates.GateRejected('No verified eligible provider is ready')
        receipt=self.store.reserve(owner_hash,request_key,spec_digest,credit_points)
        if not receipt.created_new:
            return SubmissionReport(receipt,receipt.provider_name,(),'existing_job')
        attempts=[]
        for engine in eligible:
            # The provider name and submitting state are committed BEFORE POST.
            # If the server crashes after this point, no blind resend occurs.
            self.store.transition(receipt.id,owner_hash,'submitting',provider=engine)
            attempts.append(engine)
            try:
                provider_task=provider_submit(engine)
            except DefinitelyRejected:
                self.telemetry.record(engine,feedback.Outcome.QUEUE_FULL)
                self.store.transition(receipt.id,owner_hash,'reserved',
                                      verified_rejection=True)
                continue
            except Exception:
                uncertain=self.store.transition(receipt.id,owner_hash,
                                                'unknown_acceptance')
                self.telemetry.record(engine,feedback.Outcome.UNKNOWN_SUBMISSION)
                return SubmissionReport(uncertain,engine,tuple(attempts),
                                        'requires_supplier_reconciliation')
            if not isinstance(provider_task,str) or not 4<=len(provider_task)<=150:
                uncertain=self.store.transition(receipt.id,owner_hash,
                                                'unknown_acceptance')
                self.telemetry.record(engine,feedback.Outcome.UNKNOWN_SUBMISSION)
                return SubmissionReport(uncertain,engine,tuple(attempts),
                                        'requires_supplier_reconciliation')
            accepted=self.store.transition(receipt.id,owner_hash,'accepted',
                                           task_id=provider_task)
            self.telemetry.record(engine,feedback.Outcome.PROVIDER_ACCEPTED)
            return SubmissionReport(accepted,engine,tuple(attempts),'accepted')
        # Every supplier explicitly refused without accepting a task.
        returned=self.store.transition(receipt.id,owner_hash,'failed_refunded',
                                       verified_rejection=True)
        return SubmissionReport(returned,None,tuple(attempts),'no_provider_accepted')

    def review(self,*,job_id:str,owner_hash:str,request:gates.VideoRequest,
               segments:list[gates.SegmentResult])->DeliveryReport:
        state=self.store.get(job_id,owner_hash)
        if state.state=='accepted':
            state=self.store.transition(job_id,owner_hash,'validating')
        if state.state!='validating':
            raise persistence.InvalidState('Job must have a verified provider task')
        verdict=gates.assess_output(request,segments)
        if verdict.verdict is gates.PublishVerdict.REJECT:
            result=self.store.transition(job_id,owner_hash,'failed_refunded')
            if state.provider_name:
                self.telemetry.record(state.provider_name,feedback.Outcome.VIDEO_REJECTED)
            return DeliveryReport(result,verdict,False)
        if verdict.verdict is gates.PublishVerdict.NEEDS_REVIEW:
            # Review pending; not available as finished media and not charged twice.
            return DeliveryReport(self.store.get(job_id,owner_hash),verdict,False)
        done=self.store.transition(job_id,owner_hash,'completed',verified_output=True)
        if state.provider_name:
            self.telemetry.record(state.provider_name,feedback.Outcome.VIDEO_VALID)
        return DeliveryReport(done,verdict,True)

    def recover(self,*,owner_hash:str,job_id:str,
                definite_rejection:bool=False,
                accepted_task_id:str|None=None)->persistence.JobReceipt:
        current=self.store.get(job_id,owner_hash)
        if current.state in ('submitting','unknown_acceptance'):
            if accepted_task_id:
                return self.store.transition(job_id,owner_hash,
                                             'accepted',task_id=accepted_task_id)
            if definite_rejection:
                return self.store.transition(job_id,owner_hash,'reserved',
                                             verified_rejection=True)
            if current.state=='submitting':
                return self.store.transition(job_id,owner_hash,
                                             'unknown_acceptance')
        return current
