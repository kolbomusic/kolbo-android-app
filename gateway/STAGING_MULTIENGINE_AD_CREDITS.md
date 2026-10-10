# Kolbo Video: Multi-Engine + Rewarded Credits (STAGING)

Status 2026-10-10: **Source + unit tests only. Not deployed or wired to the Android app.**

Live Render continues with Agnes Flash. Do NOT claim that this staging branch
can already produce videos, grant paid credits, or supply unlimited GPU capacity.

## Economic model

1. Local/donated GPUs and open-source models can minimize per-video license
   charges, but GPU, energy, storage and bandwidth require real resources.
2. Account-approved promotional API models can be tried within their quotas;
   advertised zero pricing is not a contractual per-account zero-spend cap.
3. AdMob rewarded ads are optional, for genuine third-party users who opt in.
   Their owner/publisher receives revenue on its own payout schedule; AdMob
   **does not pay an external video model vendor on each view**.
4. The publisher should test with test ads, never repeatedly view/click their
   own live ads to inflate impressions: Google may classify this invalid traffic.
5. Credits for use inside Kolbo Video must be noncash and nontransferable.
   One ad view cannot be promised to pay for one clip.
6. Provider billed generation only when a separate real funding/budget gate
   explicitly verifies available money.

## Source modules

- provider_router.py: capability-checked routing, circuit breaker, and
  failover only after explicit refusal before a task ID exists. Two separate
  identity photos must not be silently reinterpreted as keyframes.
- agnes_legacy_adapter.py: different v2.0 payload; disabled until separate
  permission and pricing checks.
- rewarded_credits.py: real ECDSA AdMob SSV signature-verification helper and
  unique transaction/nonce durable PostgreSQL schema; NO callback handler,
  ad unit, wallet funding or live credit grant connected yet.
- Private job-state checkpoint helper intentionally identifies itself as
  NONPERSISTENT. Render Free filesystem does not survive redeploy reliably.

## Remaining gates before reward monetization

Create AdMob publisher account and rewarded ad unit; show opt-in ads via Google
Mobile Ads SDK and use real Google public SSV keys; configure publisher
verification callback; set up durable external PostgreSQL to persist ad intents,
verified transaction IDs, balances and spending; add proof of ad revenue and a
strict provider dollar budget. Google impression payouts are not immediate.

## Remaining gates before multi-engine video is operational

Obtain explicit consent and real capability/availability tests for each actual
provider, including its cost and reference-image semantics. Add external
persistent jobs, accepted task IDs, retries, storyboard continuity references,
audio synchronization and FFmpeg output QA. Never retry a possibly accepted
billable task or claim that incompatible models can retain precise identities.

Tests: GitHub workflow kolbo-video-gateway-render-ci.yml on the isolated branch.

Official references:
https://developers.google.com/admob/android/ssv
https://support.google.com/admob/answer/7313578
https://support.google.com/admob/answer/6213019


## Selling Kolbo Video to third-party users (STAGING)

The app will have separate permission/monetization policies for the publisher
(owner) and ordinary users. The owner may be charged zero *internal app
credits*, but the video backend still requires an independent real provider
budget and GPU capacity. An owner role must be attested by the server, never
provided as a Boolean field in an Android request.

Possible revenue channels: optional rewarded ads, prepaid in-app credit packs,
monthly Plus/Pro subscriptions with clearly bounded included credits, and
commercial video creation packages. Subscription video generation is NEVER
"unlimited" unless genuine backend capacity is contracted and paid for.

As of October 2026, Google Play-distributed applications selling digital
services normally must use Google Play Billing unless a regional exception
or approved alternative billing program applies. Play service fees vary by
market, product, developer program and install cohort. Any customer-facing
prices must be shown accurately. Paid provider usage must be controlled by
a trusted server-side budget independent of the app's local wallet balance.

Backend scaffold monetization_policy.py (and corresponding tests) supports
unit economics and strictly fails closed when real price evidence, durable
credits ledger, purchase verification, or funding authorization is missing.

Example only (not product launch prices): an 8-second output sold at $1.00,
with confirmed supplier cost $0.40, infrastructure $0.10, platform fees $0.15,
VAT reserve $0.10 and refunds reserve $0.05 leaves an estimated $0.20 margin.
This example excludes additional overhead and is not a tax calculation.

Before launch: production Play Console merchant profile; registered payment
products and subscription terms; Android BillingClient integration; server-side
Google Play Developer API purchase validation; purchase token idempotency,
refund/chargeback and subscription lifecycle handling (RTDN); durable
PostgreSQL ledger with atomic reservations and spend settlement; budgets
per user, model and calendar period; Israeli invoicing/tax compliance; explicit
content/identity consent and privacy disclosures. No production payment
credentials, merchant details or secret keys must be committed to GitHub.

Sources:
https://support.google.com/googleplay/android-developer/answer/9858738
https://support.google.com/googleplay/android-developer/answer/112622
https://developer.android.com/google/play/billing
