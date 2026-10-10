package com.kolbo.videostudio;
public final class Failure407Smoke {
    private static void yes(boolean ok,String why){
        if(!ok)throw new AssertionError(why);
        System.out.println("PASS "+why);
    }
    public static void main(String[] args) {
        yes(StudioFailureNotice.isFailure("שירות MSR הגיע למכסה"),"Hebrew quota rejection visible");
        yes(StudioFailureNotice.title("HTTP 429 quota exceeded").contains("מגבלת"),"Quota error has readable heading");
        yes(StudioFailureNotice.isFailure("ההפקה לא הושלמה"),"Unexpected early exit visible");
        yes(StudioFailureNotice.isFailure("הסרטון נכשל"),"Backend failure visible");
        yes(StudioFailureNotice.isFailure("הסרטון יצא קצר מדי"),"Truncated result is terminal");
        yes(!StudioFailureNotice.isFailure("מכינים את הסצנה..."),"Ordinary staging status is not a failure");
        yes(!StudioFailureNotice.isFailure("יוצרים את הסרטון..."),"Normal progress does not stop render");
        yes(!StudioFailureNotice.isFailure(null),"Null status safe");
        System.out.println("ALL FAILURE UX TESTS PASSED");
    }
}
