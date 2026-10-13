package com.kolbomusic.video;

/** Offline provider error tests; do not consume GPU quota or transfer user photos. */
public final class ProviderErrorClassifierTest {
    private static void check(boolean ok,String message){
        if(!ok)throw new AssertionError(message);
    }
    public static void main(String[] args){
        ProviderErrorClassifier.Result quota=ProviderErrorClassifier.classify(
          "{\"error\":\"ZeroGPU quota exceeded: 100 seconds requested, 2 seconds remaining\"}");
        check("GPU_QUOTA".equals(quota.code),"quota classification");
        check(quota.hebrew.contains("מכסת"),"Hebrew quota explanation");
        check(quota.finalForJob,"SSE error terminal");
        check("PROVIDER_BUSY".equals(ProviderErrorClassifier.classify(
          "{\"error\":\"The upstream queue is full, too busy\"}").code),"busy");
        check("AUTH_REQUIRED".equals(ProviderErrorClassifier.classify(
          "User must login to this ZeroGPU Space").code),"login required");
        check("GPU_MEMORY".equals(ProviderErrorClassifier.classify(
          "CUDA out of memory").code),"OOM");
        check("PARAMETER_REJECTED".equals(ProviderErrorClassifier.classify(
          "Invalid duration input").code),"invalid args");
        String malicious="Internal traceback token=SUPER_SECRET_EMAIL_X";
        ProviderErrorClassifier.Result unknown=ProviderErrorClassifier.classify(malicious);
        check("PROVIDER_REJECTED".equals(unknown.code),"generic");
        check(!unknown.hebrew.contains("SUPER_SECRET_EMAIL_X"),"no raw upstream leakage");
        check(!unknown.hebrew.contains("token"),"no secret leakage");
        System.out.println("PASS: 7 provider-error safety tests");
    }
}
