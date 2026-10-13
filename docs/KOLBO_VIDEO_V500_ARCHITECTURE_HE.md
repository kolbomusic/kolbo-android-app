# Kolbo Video v5.0.0 — Scene Contract / Source / Render / QA

## Objective
The owner should write plain Hebrew and attach an image. The app must interpret the scenario, avoid wasting free GPU on obviously unsuitable sources, generate via only approved providers, and **never confuse a valid MP4 with a successful story**.

## Original user failure
- User asked for noise/effects removal, then the reference human fighting **two lions** and defeating both.
- First trial returned a portrait whose only movement was facial expressions, shorter than selected.
- Subsequent 5.0625-second generated file contained the human touching/licking lions, **not fighting nor subduing them**.
- This is not just a dictionary or translation error. Source framing, generator limits and lack of visual QA caused an apparently successful but semantically wrong result.

## V5 modules
1. `HebrewIntentBrain` + local `HebrewActionTranslator`: words, inflection, ordering, quantifiers + offline translation. Retains the user's original free-form instruction.
2. `V5SceneContract`: formal positive and dynamic negative constraints: photo prep; physical action; exact lion count; victory; forbids kissing/licking/nuzzling. Creates a scene plan from an ordinary request, never fabricates GPU capabilities.
3. `V5SourceAudit`: before image transfer, ML Kit **bundled face detector** estimates close-up framing and flags major face crop. For extremely close faces in action requests it blocks before wasting a provider job. Cannot guarantee that full bodies are actually present; no generative outpainting is available.
4. `BasicPhotoCleaner`: existing offline mild denoising/exposure control runs if requested. Cannot restore missing image details or reverse strong visual effects.
5. `WanProviderCatalog` + `WanNativeClient`: pinned TLS allowlist to public WAN Fast / Lightning; validates live Gradio API schemas. No paid fallback, no silent resubmission, provider-id is bound to the existing queue job for recovery.
6. `V5OutputAudit`: actual MP4 decoding and sampled video frames with motion detection. Bundled ML Kit general image-labeling provides *weak, advisory* lion recognition signals. **This does not count two lions or classify fighting, victory or affectionate contact.** All complicated output is correctly marked *UNVERIFIED*, even when MP4 bytes and duration are correct.
7. `V5RetryPolicy`: separates quota, supplier, authentication, unknown acceptance, source mismatch and semantic review. Never creates a new inference job automatically.
8. `MainActivity`: native Hebrew studio, full-screen reliable Media3 playback, requested-versus-actual duration, review and save. Displays output as under review, or hard failure if duration/motion fail.

## CI validation
GitHub branch: `kolbo-video-v500-scene-verification-architecture-20261014`, workflow: `.github/workflows/kolbo-v500-architecture-apk.yml`. JDK 17+ Android SDK 35. No API keys or user images stored in source code or CI.

## Explicit unsolved blockers
- Reliable automatic semantic video understanding (e.g. a tested vision-language model that can establish **exactly two distinct lions physically fought and defeated**, with no licking) is **NOT provided by generic ML Kit image labels**.
- The public Wan AI model may still produce an incorrect scene; hard prompt constraints cannot *force* diffusion models to comply.
- One uploaded reference portrait cannot produce an accurately reconstructed full body without a separate authorized generative outpainting stage. Source-audit blocks severe cases rather than claiming success.
- GPU compute remains externally quota-limited and unguaranteed; no evidence of truly free unlimited resources.
- Two independently referenced human identities, 15-second synchronized video, singing and audio remain unsupported by this demonstrable backend.
- Android APK build and signing are checked in CI; successful end-to-end video creation *inside the installed app* is not proven until device testing.

This is a deeper architectural foundation and testable failure pipeline, **not proof of the whole originally requested world-class autonomous unlimited free video generator**.
