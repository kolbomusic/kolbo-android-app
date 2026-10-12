# Kolbo Video 4.4.2 · Android bridge

Native Android WebView client for /studio on a separately hosted Kolbo Mesh API.
- Build: JDK 17, Android SDK API 35, Gradle 8.10.2, command: gradle -p mobile-kolbo :app:assembleDebug
- HTTPS only, user-selected hostname, no bundled owner token or paid SDK.
- An APK without a running owner-controlled HTTPS hub and a verified GPU worker cannot generate real AI video.
- Debug builds are not signed for Play Store release.
- Users must not upload identifiable photographs without authorization of the people pictured.
