# Kolbo Video Android 4.4.9 — Contract and MP4 export

**Built GitHub Actions:** https://github.com/kolbomusic/kolbo-android-app/actions/runs/38241986666 (success).

New Android app verifies a server via `GET /v1/app-config` *before* loading `/studio`. Expected public payload: `{"service":"kolbo-volunteer-mesh","api_contract":449,"minimum_android_client":449,"owner_auth_required":true}`. Server-side source and studio.js matching this protocol are supplied in the full v4.4.9 integration ZIP prepared in ChatGPT; this PR currently updates the Android client only, **not** the deployed backend.

The owner-specific `KOLBO_MESH_OWNER_TOKEN` is never packaged in Android. Verified MP4 is transferred from existing authenticated blob in bounded chunks to `VideoExportBridge`, then Android's `ACTION_CREATE_DOCUMENT` picker.

This APK **cannot generate video without a separate compatible HTTPS server plus verified consenting GPU worker**. No GPU activated, no paid fallback, no production deploy, no live real-person identity proof or physical Android Save As test. The Android package is a debug build.

**Required release checks**: install on physical Android, validate HTTPS certificate and /v1/app-config handshake, connect owner token, submit a *real* rendered job on authorized GPU, validate video movement/audio/identity, approve, save via Android document picker, verify MP4 plays locally and images/tokens are not leaked.
