# Kolbo Video v4.7.0 — native Hebrew Android studio

### UX fix for reported screenshot (October 2026)
- Removed the *entire* hosted Gradio WebView UI that had extremely oversized zoom, cropped text and English controls.
- Native Android RTL form includes image picker, Hebrew story field, 2–5-second selector, explicit approval, generate button, playback VideoView, and save-as MP4.
- Uses Google's official on-device ML Kit Hebrew→English translation, with automatic download of approximately 30 MB on first use. The typed story stays on-device until the translated prompt is sent to the video provider; no separate third-party translation API is used.
- Request is sent over HTTPS directly to the public Wan Fast Gradio host, not through an arbitrary English website or mobile WebView. Uses upload, one-shot event submission, SSE job response and same-origin video download.
- Handles raw `gr.Video` response shape `{video: FileData, subtitles: null}` as well as direct FileData, refusing non-HTTPS/cross-host output and non-MP4 bytes.
- Rejects unsupported singing/speaking, two independently referenced identities, and more than 5 seconds rather than pretending to render them.
- This is a public zero-cost trial, not unlimited free GPU, nor commercial, personal-photo identity-verified or native AV production.
- Different application ID `com.kolbomusic.video.hebrewstudio` avoids Android debug signing conflict with prior v4.6.8/4.6.9 `.realgpu` app.
- Launcher label: `כלבו וידאו AI`.

### Evidence
- Public Wan2.2 Fast produced a 2.062-second moving synthetic MP4 in October 2026: https://github.com/kolbomusic/kolbo-android-app/actions/runs/38442357175 .
- One test of the *native client's same REST protocol* succeeded on synthetic data: upload→submit→event_id→SSE complete, without personal photo, billing or key: https://github.com/kolbomusic/kolbo-android-app/actions/runs/38469672817 .
- Android package verification through CI build on branch `kolbo-video-v470-hebrew-action-translation-20261014`.

### Still NOT verified
- Installing/launching v4.7.0 on a physical Android device; actual end-to-end use of the compiled `WanNativeClient` from a phone.
- Prompt adherence to Hebrew actions translated by ML Kit, fidelity of the person's identity, human movements, and scene continuity.
- Two source persons, sound, dialogue, singing, lip sync, 15-second outputs or unmetered GPU capacity.
- Live commercial rights for public ZeroGPU Space are unverified; no charges, automatic paid fallbacks or distribution as commercial renderer.

### Use
Install APK; open `כלבו וידאו AI`; select one photo (use **full-body** photo for body movements); type the story in Hebrew; approve sending the selected image to Hugging Face; select 2–5s; click `צור סרטון AI`; review the output; save when appropriate. First use may take additional time for free on-device translation model download. If provider rejects for quota/login/API change, the app shows an error and doesn't invent a replacement video.
