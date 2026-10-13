# Kolbo Video 4.6.7 — Durable free GPU trial bridge (staging)

**Status:** source-level integration and offline CI proof. No server was deployed,
no user media transmitted, no production GPU or zero-cost unlimited capacity
was verified in this change.

## What changed

The existing experimental endpoint `POST /v1/ai/jobs` now **optionally** uses a
private SQLite submission journal to record an opaque owner, SHA-256 request
digest, state and provider/media receipts. No original prompt, image, API
secret, email or real-name identity is stored in the journal.

- The first matching request reserves one durable ID.
- Repeated identical requests return the same ID — even after process restart.
- The journal writes `submitting` **before** the supplier call. If the process
  crashes or the supplier response is uncertain, the app sees
  `acceptance_unknown`; the server never automatically sends a second job.
- Successfully returned media passes the existing independent motion and
  integrity checks before the journal records `completed`.
- Owner-scoped status and private download can recover from the journal if
  in-memory dictionaries were lost.
- Server-wide and per-install trial submission caps are enforced inside the
  SQLite transaction as well as by existing trial guards, preventing a
  service restart from resetting the durable accounting. This does NOT
  bypass the upstream service quotas.
- No paid fallback, worker registration, or external photo transfer is
  enabled by this patch.

## Deployment prerequisites

An operator must provision a **verified persistent, private filesystem** for
*both* the journal and the MP4 files. Render's ephemeral free filesystem does
not qualify merely because these environment variables are set.

Example *only after testing volume persistence and privacy*:

```dotenv
KOLBO_V416_WORK_DIR=/private/durable-kolbo
KOLBO_FREE_GPU_JOURNAL_PATH=/private/durable-kolbo/free_gpu_jobs.sqlite3
KOLBO_FREE_GPU_PERSISTENT_VOLUME_VERIFIED=EXPLICITLY_ENABLED
```

The parent must already exist and have permissions `0700`; metadata/media
are colocated in that same directory. Existing service auth and operator
consent gates remain independently mandatory. Set no flag merely to make a
"ready" banner appear.

If the journal path is unset, the existing **non-durable** limited trial
behavior is unchanged (not production-ready).

## Supported operation

Existing API contract:

1. `POST /v1/guest/bootstrap` returns a narrowly scoped temporary guest
   token; it is not owner identity verification.
2. `POST /v1/creative/plan` checks scene feasibility without media upload.
3. `POST /v1/ai/jobs` accepts exactly one supported image, consent and a
   brief 1–5 second silent noncommercial prompt.
4. `GET /v1/jobs/{id}` reports status only to the issuing guest or master.
5. `GET /v1/jobs/{id}/result` serves an integrity-verified private MP4 only
   once the result exists.

**Not supported:** automatic voice, singing, precise 2-person photo identity,
15-second exact prompt fidelity, no-limit GPU or secure commercial rights.
`completed` means a media-draft output passed technical signal checks, not
that the user's full creative instructions have been fulfilled.

## Verification

GitHub Actions workflow:
`Kolbo 4.6.7 free GPU crash-consistent journal`.

Offline tests cover:
- same key after restarting the process;
- 5-way concurrent reservations;
- ambiguous supplier acceptance and mandatory no-resubmit;
- expired/unauthorized access rejection;
- global/per-install caps surviving restart;
- crash recovery through the FastAPI job-status endpoint;
- SHA-256 media integrity for recovered downloads;
- privacy and consent gates from the previous experiment.

For a genuine deployment, an additional documented forced service restart
**during a real authorized synthetic provider job** and a private volume
persistence check are still required.
