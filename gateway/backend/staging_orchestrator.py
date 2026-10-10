"""Staged orchestration of real business rules, with provider calls INJECTED.

No production provider transport is connected here. This composes the tested
guard, ledger, routing and feedback modules into an atomic, recoverable work
state machine. The backend owner must configure durable PostgreSQL, verified
account prices, purchased balances and video storage before enabling it.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
from decimal import Decimal

import execution_guard as guard
import operations_feedback as feedback
import staging_job_ledger as ledger
import provider_router

class RejectedBeforeAcceptance(Exception):
    """Only emitted for supplier-verified rejection with no task ID."""

class UnknownSubmission(Exception):
    """Network/timeout state: supplier may have accepted and billed the job."""

@dataclass(frozen=True)
class Submission:
    job:ledger.JobView
    provider:str|None
    outcome:str
    attempted:tuple[str,...]
    retry_safe:bool

@dataclass(frozen=True)
class Delivery:
    job:ledger.JobView
    quality:guard.QualityReport
    available_to_customer:bool

class StagingCoordinator:
    """Purely a source integration testbed: no external submit, no billing API."""
    def __init__(self,store:ledger.StagingLedger,
                 stats:feedback.Feedback|None=None):
        self.store=store
        self.stats=stats if stats is not None else feedback.Feedback()

    def _eligible(self,req:guard.VideoRequest,
                  offered:list[guard.ProviderProof])->list[guard.ProviderChoice]:
        # The offered list must be assembled by trusted server configuration
        # and provider probes, NEVER by the Android request body.
        choices=guard.choose_eligible(req,offered)
        names=self.stats.safe_order([p.name for p in choices])
        indexed={p.name:p for p in choices}
        return [indexed[n] for n in names
                if self.stats.inspect(n).action not in (
                    'pause_requests','operator_review','reconcile_provider_task')]

    def submit(self,*,owner_hash:str,idempotency_key:str,spec_digest:str,
               points:int,request:guard.VideoRequest,
               verified_providers:list[guard.ProviderProof],
               dispatch:Callable[[str],str])->Submission:
        # Reserve customer credits only if at least one supplier passes the
        # capability/consent/duration/price/quality contract.
        eligible=self._eligible(request,verified_providers)
        if not eligible:
            raise guard.GateRejected('No verified provider matches the request and budget')
        job=self.store.reserve(owner_hash,idempotency_key,spec_digest,points)
        if not job.created_new:
            # Never dispatch a duplicate; refresh only the durable receipt.
            return Submission(job,None,'existing_job',(),False)
        self.store.progress(job.id,'submitting')
        attempted=[]
        for option in eligible:
            attempted.append(option.name)
            try:
                task_id=dispatch(option.name)
            except RejectedBeforeAcceptance:
                self.stats.record(option.name,feedback.Outcome.QUEUE_FULL)
                # Explicit rejection means no task was accepted or billable.
                # Remain submitting for the next eligible provider.
                continue
            except Exception:
                self.store.progress(job.id,'unknown_acceptance')
                self.stats.record(option.name,feedback.Outcome.UNKNOWN_SUBMISSION)
                return Submission(self.store.view(job.id),option.name,
                                  'provider_acceptance_unknown',tuple(attempted),False)
            if not isinstance(task_id,str) or not 4<=len(task_id)<=150:
                # Without a valid task ID, do not resubmit. A supplier may
                # have accepted the task but returned a changed response.
                self.store.progress(job.id,'unknown_acceptance')
                self.stats.record(option.name,feedback.Outcome.UNKNOWN_SUBMISSION)
                return Submission(self.store.view(job.id),option.name,
                                  'task_id_unrecognized',tuple(attempted),False)
            self.store.progress(job.id,'accepted',provider_task_id=task_id)
            self.stats.record(option.name,feedback.Outcome.PROVIDER_ACCEPTED)
            return Submission(self.store.view(job.id),option.name,
                              'accepted',tuple(attempted),False)
        self.store.progress(job.id,'failed_refunded',rejection_verified=True)
        return Submission(self.store.view(job.id),None,
                          'all_explicitly_rejected',tuple(attempted),True)

    def recover(self,job_id:str,*,owner_hash:str,verified_rejection:bool=False,
                accepted_task_id:str|None=None)->ledger.JobView:
        """No second provider POST is triggered by a restart or API timeout."""
        job=self.store.view_for_owner(owner_hash,job_id)
        if job.state=='unknown_acceptance':
            if accepted_task_id:
                return self.store.progress(job_id,'accepted',
                                           provider_task_id=accepted_task_id)
            if verified_rejection:
                return self.store.progress(job_id,'reserved',
                        rejection_verified=True)
        return job

    def deliver(self,*,owner_hash:str,job_id:str,request:guard.VideoRequest,
                segments:list[guard.SegmentResult],
                provider:str)->Delivery:
        view=self.store.view_for_owner(owner_hash,job_id)
        if view.state=='completed':
            # An identical status query must not settle credits twice.
            quality=guard.assess_output(request,segments)
            return Delivery(view,quality,quality.verdict is guard.PublishVerdict.ACCEPT)
        if view.state=='accepted':
            self.store.progress(job_id,'validating')
        elif view.state!='validating':
            raise ledger.InvalidTransition('Provider did not accept this job')
        qa=guard.assess_output(request,segments)
        if qa.verdict is guard.PublishVerdict.REJECT:
            self.store.progress(job_id,'failed_refunded')
            self.stats.record(provider,feedback.Outcome.VIDEO_REJECTED)
            return Delivery(self.store.view(job_id),qa,False)
        if qa.verdict is guard.PublishVerdict.NEEDS_REVIEW:
            # Keep funds reserved, never publish a mismatched identity as
            # accepted. Owner/operator may verify the saved output later.
            return Delivery(self.store.view(job_id),qa,False)
        result=self.store.progress(job_id,'completed',qa_passed=True)
        self.stats.record(provider,feedback.Outcome.VIDEO_VALID)
        return Delivery(result,qa,True)
