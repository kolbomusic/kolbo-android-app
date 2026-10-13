package com.kolbomusic.video;

/** Fail-closed client-side gate. The server must independently enforce all checks. */
public final class NativeReadiness {
    private NativeReadiness() {}

    public static boolean canOpenStudio(
            boolean trustedService,
            boolean supportedContract,
            boolean ownerAuthRequired,
            boolean previewOnly,
            boolean gpuReady,
            boolean durableStorageReady,
            boolean privateMediaEnabled,
            boolean realAiRenderVerified,
            boolean paidFallbackEnabled) {
        return trustedService && supportedContract && ownerAuthRequired &&
                !previewOnly && gpuReady && durableStorageReady &&
                privateMediaEnabled && realAiRenderVerified && !paidFallbackEnabled;
    }
}
