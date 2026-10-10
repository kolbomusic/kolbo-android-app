package com.kolbo.videostudio;

import java.util.Locale;

final class VideoEvidenceAuditRequest {
    private VideoEvidenceAuditRequest(){}
    static boolean requiresSinging(String text){
        if(text==null)return false;
        String s=text.toLowerCase(Locale.ROOT);
        return s.contains("שרים")||s.contains("שרות")||s.contains("שרה")
            ||s.contains("לשיר")||s.contains("שירה")||s.contains("שיר ")
            ||s.contains("דואט")||s.contains("vocal")||s.contains("sing")
            ||s.contains("duet")||s.contains("song");
    }
}
