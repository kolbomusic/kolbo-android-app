# Kolbo Video v4.3.5 — strict face resemblance gate

## What this change does

- For every two-photo job, the server refuses to call FLUX until the locally hosted YuNet+SFace comparator detects **two distinct source faces** in the combined user reference. Embeddings are kept in RAM only for the lifetime of that one job.
- After FLUX constructs a common stage, it compares both output faces separately against the LEFT and RIGHT source faces. If either differs, disappears, is ambiguous or swaps positions, **the LTX model is not called**.
- On successful still check, LTX video/sound is generated; three sampled frames must still show both original face slots above a conservative cosine-similarity floor. Missing face, swap, drift or ambiguous comparisons all **reject the final result**. Frozen/split-screen/audio gates remain active.
- Identity QA scores may be returned as authenticated per-job evidence. They do **NOT prove absolute identity** or verify singing, exact lyrics, the Caesarea venue, crowd count, or continuity between sampled frames.
- A purely local optional original-face pixel reconstruction is available if the FLUX scene loses identity; it **rechecks both faces** before LTX. This path defaults DISABLED via `KOLBO_LOCAL_FACE_REPAIR`, pending visual validation on lawful test media.
- Android 4.3.5 requires `face_similarity_check_passed=true` plus three per-frame evidence entries before accepting a two-person MP4. No extra setup, credentials or paid service.

## Technology and privacy

- CPU only, inside isolated Free Render test server: OpenCV Zoo YuNet face detector and 9.9 MB quantized SFace 2021dec face embedding.
- Public weights are pinned by immutable Hugging Face revision and SHA-256:
  - YuNet `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`
  - SFace int8 `2b0e941e6f16cc048c20aee0c8e31f569118f65d702914540f7bfdc14048d78a`
- The third-party image editing and video models remain existing FLUX/LTX, subject to the user's previously given external transfer consent. The face QA never uses an extra public face-recognition endpoint.
- No persistent facial embeddings, cloud face database, identity enrollment or sharing of face features across users.
- Detector/embeddings can be wrong on low resolution, motion blur, occlusions or unusual angles; conservative failure is intentional. Published SFace threshold 0.363 is NOT universal calibration; this project uses stricter 0.45 + cross-ID margins but does not claim audited accuracy.
- No commercial deployment rights have been independently verified for FLUX/LTX or third-party models.
- Face restoration is designed as a separate experimental component, not assumed to produce photorealistic identity fidelity.

## Deployment controls

- `KOLBO_STRICT_FACE_GUARD=EXPLICITLY_ENABLED` must be set by server owner before actual two-person jobs are permitted; if missing, preflight blocks the job and spends no GPU credits.
- `KOLBO_LOCAL_FACE_REPAIR` remains unset/disabled by default.
- Use existing isolated Render Free service only; no new paid disks, GPU services, database, or advertisers.
- Verify server readiness via authenticated `GET /v1/health` -> `two_person_scene_builder.automated_face_similarity_guard_ready`.
- Request metadata-only `POST /v1/native-av/plan` with `image_count:1`, `requires_shared_stage_scene:true`. It must not upload photos or spend credits.
- Output should never be described as an accurate original-face performance until actual source images and final video have been checked. More capable multi-identity model conditioning may be required for reliable performance.

## Acceptance gates

1. Both source people detected separately.
2. Same two faces apparent on unified stage, matching original left/right slots.
3. Video frame 13%, 51%, 87% samples each retain the left/right face similarities.
4. Audio stream decoded and non-silent, actual AI motion; no persistent static split screen.
5. Missing/failed identity gate => job failed and no downloadable result.
6. Real physical-device end-to-end test, calibrated model thresholds and human assessment are still required.

Official source/model licenses and documentation: OpenCV Zoo `models/face_detection_yunet` and `models/face_recognition_sface`; license texts in these folders. Training-data provenance and provider rights deserve independent review before commercial distribution.
