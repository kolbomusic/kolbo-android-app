package com.kolbo.videostudio;

import java.util.Locale;

/** User-facing terminal failure detection; detailed cause remains in diagnostics. */
public final class StudioFailureNotice {
    private StudioFailureNotice() {}
    public static boolean isFailure(String input){
        if(input==null||input.isEmpty())return false;
        String s=input.toLowerCase(Locale.ROOT);
        return s.contains("לא הושלמה")||s.contains("לא הצליח")
            ||s.contains("לא ניתן")||s.contains("נכשל")
            ||s.contains("שגיאה")||s.contains("מכסה")
            ||s.contains("מוגבל")||s.contains("עמוס")
            ||s.contains("quota")||s.contains("exhausted")
            ||s.contains("failed")||s.contains("limit reached")
            ||s.contains("http 429")||s.contains("http 503");
    }
    public static String title(String input){
        String s=input==null?"":input.toLowerCase(Locale.ROOT);
        if(s.contains("quota")||s.contains("מכסה")||s.contains("מוגבל")||s.contains("limit reached"))
            return "השירות הגיע למגבלת שימוש";
        if(s.contains("עמוס")||s.contains("http 503")||s.contains("busy"))
            return "השירות עמוס כרגע";
        if(s.contains("תרגום")||s.contains("translate"))
            return "לא הצלחנו להבין את ההנחיה";
        if(s.contains("קצר מדי")||s.contains("שניות במקום")||s.contains("משך"))
            return "הסרטון לא הגיע לאורך שביקשת";
        return "ההפקה לא הושלמה";
    }
}
