package com.kolbo.videostudio;
public final class Evidence407Smoke {
    private static void yes(boolean pass,String description) {
        if(!pass)throw new AssertionError(description);
        System.out.println("PASS "+description);
    }
    public static void main(String[] args) {
        yes(VideoEvidenceAuditRequest.requiresSinging("שתי הדמויות שרות בבוכרית"),
            "Hebrew vocal scene triggers soundtrack QA");
        yes(VideoEvidenceAuditRequest.requiresSinging("שתי הדמויות שרים יחד שיר מזרחי"),
            "Mizrahi duet triggers soundtrack QA");
        yes(VideoEvidenceAuditRequest.requiresSinging("They sing Bukhori"),
            "English vocals trigger soundtrack QA");
        yes(!VideoEvidenceAuditRequest.requiresSinging("שתי הדמויות רוקדות ליד הים"),
            "Dance alone does not imply unsupported vocal tracks");
        yes(!VideoEvidenceAuditRequest.requiresSinging("דמות 1 עוצרת את דמות 2"),
            "Arrest action does not demand singing");
        yes(!DurationPolicy.acceptable(3041,10),
            "Regressed short returned file still blocked for ten seconds");
        yes(DurationPolicy.acceptable(10000,10),
            "Valid ten-second final file allowed");
        System.out.println("ALL 4.0.7 EVIDENCE REQUEST TESTS PASSED");
    }
}
